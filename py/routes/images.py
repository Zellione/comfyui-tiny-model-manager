"""Routes for browsing CivitAI images and recreating the workflow behind them (F-130).

Two things about the upstream API shape drive this module:

* ``/api/v1/images`` has **no free-text query** — a ``query`` parameter is silently
  ignored — so the page is filter-driven only.
* There is **no** ``/api/v1/images/{id}`` endpoint. Single-image detail is the collection
  endpoint with ``imageId=``, which returns exactly one item.

Recreated graphs are stored through the F-129 workflow store, so Load-in-ComfyUI, Export
and the raw-JSON download all work on them without any new code.
"""

import httpx
from aiohttp import web

from ..db import model_repo
from ..services import image_recreate, workflow_store
from ..services.providers import civitai
from ._helpers import err, json_route, ok

_PROVIDER_UNAVAILABLE = "provider_unavailable"
_IMAGE_NOT_FOUND = "image_not_found"
_NO_METADATA = "no_metadata"

# AutoV2 is the first 10 hex characters of the SHA-256 — verified against the CivitAI API.
_AUTOV2_LEN = 10

# CivitAI stores image ids in a 32-bit signed column and answers 500 ("out of range for
# type integer") for anything larger, so oversized ids are rejected here as "not found"
# rather than being forwarded and surfacing as a provider outage.
_MAX_IMAGE_ID = 2**31 - 1


# ------------------------------------------------------------------ patchable seams
# Wrapped so tests can monkeypatch the module-level name instead of the provider or httpx.


async def _civitai_image_search(**params) -> dict:
    return await civitai.search_images(**params)


async def _civitai_version_info(version_id: str) -> dict | None:
    return await civitai.version_download_info(version_id)


async def _civitai_hash_info(file_hash: str) -> dict | None:
    return await civitai.hash_download_info(file_hash)


# ------------------------------------------------------------------------- helpers


def _decorate(item: dict) -> dict:
    """Tag an image with the recreation path it supports, for the badge and filter."""
    item["recreatable"] = image_recreate.classify_meta(item.get("meta"))
    return item


def _valid_image_id(image_id: str) -> bool:
    return image_id.isdigit() and int(image_id) <= _MAX_IMAGE_ID


def _unwrap_meta(item: dict) -> dict:
    """Flatten the double-nested ``meta`` the ``imageId=`` filter returns.

    The plain feed gives ``item["meta"] = {…params…}``, but querying a single image by
    ``imageId`` wraps it once more as ``item["meta"] = {"id": …, "meta": {…params…}}``.
    Undocumented, and left unhandled it makes every single-image lookup look like it has
    no generation metadata at all.
    """
    meta = item.get("meta")
    if isinstance(meta, dict) and isinstance(meta.get("meta"), dict):
        item["meta"] = meta["meta"]
    return item


async def _fetch_image(image_id: str) -> dict | None:
    data = await _civitai_image_search(image_id=image_id, limit=1)
    items = data.get("items") or []
    return _unwrap_meta(items[0]) if items else None


def _local_match(resource: dict, hash_map: dict[str, str]) -> str:
    """Filename this resource is already installed under, or ``""``.

    CivitAI reports AutoV2, we store the full SHA-256, and AutoV2 is its 10-character
    prefix — so the comparison is a prefix match, not an equality check.
    """
    short = (resource.get("hash") or "").lower()
    if not short:
        return ""
    for full, filename in hash_map.items():
        if full[:_AUTOV2_LEN] == short[:_AUTOV2_LEN]:
            return filename
    return ""


async def _remote_info(resource: dict) -> dict | None:
    """Look the resource up on CivitAI, preferring the version id when there is one."""
    version_id = resource.get("model_version_id") or ""
    if version_id.isdigit():
        info = await _civitai_version_info(version_id)
        if info:
            return info
    file_hash = resource.get("hash") or ""
    if file_hash:
        return await _civitai_hash_info(file_hash)
    return None


async def _resolve_one(resource: dict, hash_map: dict[str, str]) -> dict:
    """Resolve a single referenced model to installed / missing / unresolvable.

    A resource that cannot be resolved is reported as such rather than raising: one dead
    LoRA must never fail the whole panel.
    """
    entry = {
        "kind": resource["kind"],
        "name": resource["name"],
        "weight": resource["weight"],
        "hash": resource["hash"],
        "model_version_id": resource["model_version_id"],
    }
    local = _local_match(resource, hash_map)
    if local:
        return {**entry, "status": "installed", "filename": local}
    try:
        info = await _remote_info(resource)
    except httpx.HTTPError:
        info = None
    if not info:
        return {**entry, "status": "unresolvable"}
    return {
        **entry,
        "status": "missing",
        "filename": info["filename"],
        "download_url": info["download_url"],
        "size_kb": info["size_kb"],
        "model_type": info["model_type"],
        "base_model": info["base_model"],
        "model_version_id": info["model_version_id"] or entry["model_version_id"],
        "name": entry["name"] or info["model_name"],
    }


async def _resolve_all(meta: dict) -> list[dict]:
    hash_map = await model_repo.get_file_hash_map()
    resources = image_recreate.referenced_resources(meta)
    return [await _resolve_one(r, hash_map) for r in resources]


def _installed_filenames(resolved: list[dict]) -> dict[str, str]:
    """Lowercased resource name -> local filename, for pointing the template at real files."""
    return {
        r["name"].lower(): r["filename"]
        for r in resolved
        if r["status"] == "installed" and r["name"] and r.get("filename")
    }


# -------------------------------------------------------------------------- routes


async def _search(request: web.Request) -> web.Response:
    query = request.rel_url.query
    try:
        limit = min(max(int(query.get("limit", 50)), 1), 200)
    except ValueError:
        limit = 50
    try:
        data = await _civitai_image_search(
            sort=query.get("sort", ""),
            period=query.get("period", ""),
            nsfw=query.get("nsfw", ""),
            base_model=query.get("base_model", ""),
            media_type=query.get("type", ""),
            username=query.get("username", ""),
            model_id=query.get("model_id", ""),
            cursor=query.get("cursor", ""),
            limit=limit,
        )
    except httpx.HTTPError:
        return err(_PROVIDER_UNAVAILABLE, status=503)
    data["items"] = [_decorate(i) for i in data.get("items") or []]
    return ok(data)


async def _detail(request: web.Request) -> web.Response:
    image_id = request.match_info["id"]
    if not _valid_image_id(image_id):
        return err(_IMAGE_NOT_FOUND, status=404)
    try:
        item = await _fetch_image(image_id)
    except httpx.HTTPError:
        return err(_PROVIDER_UNAVAILABLE, status=503)
    if item is None:
        return err(_IMAGE_NOT_FOUND, status=404)
    return ok(_decorate(item))


async def _recreate(request: web.Request) -> web.Response:
    """Rebuild and store the workflow behind an image.

    The graph is always stored, even when referenced models are missing locally — the
    resolution panel reports those separately and ComfyUI surfaces them itself on load.
    """
    image_id = request.match_info["id"]
    if not _valid_image_id(image_id):
        return err(_IMAGE_NOT_FOUND, status=404)
    try:
        item = await _fetch_image(image_id)
    except httpx.HTTPError:
        return err(_PROVIDER_UNAVAILABLE, status=503)
    if item is None:
        return err(_IMAGE_NOT_FOUND, status=404)

    meta = item.get("meta") or {}
    kind = image_recreate.classify_meta(meta)
    if kind == image_recreate.RECREATE_NONE:
        return err(_NO_METADATA, status=422)

    base_model = item.get("baseModel", "")
    resolved: list[dict] = []
    if kind == image_recreate.RECREATE_GRAPH:
        graph = image_recreate.graph_from_comfy(meta)
        template_warning = False
    else:
        try:
            resolved = await _resolve_all(meta)
        except httpx.HTTPError:
            return err(_PROVIDER_UNAVAILABLE, status=503)
        graph = image_recreate.build_template_graph(meta, _installed_filenames(resolved))
        template_warning = image_recreate.needs_template_warning(base_model)

    stored = await workflow_store.store_recreated_graph(
        image_id=image_id,
        name=f"CivitAI image {image_id}",
        graph=graph,
        base_model=base_model,
        thumbnail_url=item.get("url", ""),
        description=str(meta.get("prompt") or ""),
    )
    return ok(
        {
            **stored,
            "source": kind,
            "base_model": base_model,
            "template_warning": template_warning,
            "resources": resolved,
        }
    )


async def _resolve_resources(request: web.Request) -> web.Response:
    body = await request.json()
    image_id = str(body.get("image_id", "")).strip()
    if not _valid_image_id(image_id):
        return err(_IMAGE_NOT_FOUND, status=404)
    try:
        item = await _fetch_image(image_id)
        if item is None:
            return err(_IMAGE_NOT_FOUND, status=404)
        resources = await _resolve_all(item.get("meta") or {})
    except httpx.HTTPError:
        return err(_PROVIDER_UNAVAILABLE, status=503)
    return ok({"resources": resources})


def add_images_routes(routes) -> None:
    routes.get("/tiny-model-manager/api/images/search")(json_route(_search))
    routes.post("/tiny-model-manager/api/images/resolve-resources")(json_route(_resolve_resources))
    routes.post("/tiny-model-manager/api/images/{id}/recreate")(json_route(_recreate))
    routes.get("/tiny-model-manager/api/images/{id}")(json_route(_detail))
