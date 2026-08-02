import asyncio
import os
import shutil

import folder_paths
import httpx

from ..db import model_repo
from ..services import disk_scanner, link_resolver, media_cleanup, model_paths
from ..services.reorganizer import _sanitize_subfolder_name
from ._helpers import err, json_route, ok
from .metadata import _derive_source_url


def _attach_model_metadata(result: dict, meta_map: dict) -> None:
    """Attach a "metadata" block to each scanned file that has a stored DB record."""
    for files in result.values():
        for f in files:
            m = meta_map.get(f["filename"])
            if not m:
                continue
            f["metadata"] = {
                "description": m.get("description", ""),
                "trigger_words": m.get("trigger_words", []),
                "tags": m.get("tags", []),
                "media": m.get("media", []),
                "base_model": m.get("base_model", ""),
                "source_platform": m.get("source_platform", ""),
                "source_url": _derive_source_url(
                    m.get("source_platform", ""),
                    m.get("source_id", ""),
                    m.get("civitai_model_id", ""),
                ),
                "created_at": m.get("created_at", ""),
                "civitai_version_name": m.get("civitai_version_name", ""),
            }


async def _list_models(request):
    result = disk_scanner.scan_all()
    all_filenames = [f["filename"] for files in result.values() for f in files]
    meta_map = await model_repo.get_metadata_by_filenames(all_filenames)
    _attach_model_metadata(result, meta_map)
    return ok(result)


async def _delete_model(request):
    model_type = request.match_info["model_type"]
    rel_path = request.match_info["path"]
    dirs, _ = folder_paths.folder_names_and_paths.get(model_type, ([], set()))
    for base_dir in dirs:
        # Confine to base_dir (rejects ../ and sibling-prefix escapes).
        candidate = model_paths.contained_path(base_dir, rel_path)
        if candidate is None:
            continue
        if os.path.isfile(candidate):
            # Read the media info first: the rows cascade away with the model row.
            media = await model_repo.get_model_media_info(rel_path)
            os.remove(candidate)
            await model_repo.delete_model_record(rel_path)
            if media:
                await media_cleanup.cleanup_model_media(media["media_hash"], media["paths"])
            await model_repo.update_download_history_status_by_path(model_type, rel_path, "deleted")
            return ok()
    return err("File not found", status=404)


async def _list_model_types(request):
    models_dir = folder_paths.models_dir
    types = []
    if os.path.isdir(models_dir):
        for name in os.listdir(models_dir):
            if name == "configs":
                continue
            if os.path.isdir(os.path.join(models_dir, name)):
                types.append(name)
    return ok(sorted(types))


def _resolve_move_source(models_dir: str, model_type: str, rel_path: str) -> str | None:
    """Find the on-disk source file for a move, searching physical then registered dirs."""
    # The type dropdown and the move destination both use physical folder names under
    # models_dir, but some physical folders (e.g. "clip") are not registered folder_paths
    # keys; search the physical folder first so physical-only files can still be relocated.
    src_dirs = [os.path.join(models_dir, model_type)]
    registered, _ = folder_paths.folder_names_and_paths.get(model_type, ([], set()))
    src_dirs.extend(registered)
    for base_dir in src_dirs:
        candidate = model_paths.contained_path(base_dir, rel_path)
        if candidate is not None and os.path.isfile(candidate):
            return candidate
    return None


async def _move_model(request):
    model_type = request.match_info["model_type"]
    rel_path = request.match_info["path"]
    body = await request.json()
    new_type = body.get("new_type", "")

    # Validate new_type as a safe physical folder name under models_dir
    models_dir = folder_paths.models_dir
    dest_dir = os.path.normpath(os.path.join(models_dir, new_type))
    if (
        not new_type
        or new_type in ("configs", "custom_nodes")
        or not dest_dir.startswith(os.path.normpath(models_dir) + os.sep)
    ):
        return err("Unknown model type", status=400)

    src = _resolve_move_source(models_dir, model_type, rel_path)
    if not src:
        return err("File not found", status=404)

    # Destination is the literal models/<new_type> folder
    dest = os.path.normpath(os.path.join(dest_dir, rel_path))
    if not dest.startswith(dest_dir + os.sep):
        return err("Invalid destination path", status=400)
    if os.path.normpath(src) == dest:
        return ok()  # already in target folder
    if os.path.exists(dest):
        return err("Target file already exists", status=409)

    os.makedirs(os.path.dirname(dest), exist_ok=True)
    shutil.move(src, dest)

    # filename column unchanged; only model_type is updated
    await model_repo.update_model_type(rel_path, new_type)
    return ok()


def _resolve_organize_source(model_type: str, filename: str) -> tuple[str | None, str | None]:
    """Return (src_path, src_base_dir) for the model file, or (None, None) if not found."""
    try:
        base_dirs = folder_paths.get_folder_paths(model_type)
    except Exception:
        base_dirs = [os.path.join(folder_paths.models_dir, model_type)]
    for base_dir in base_dirs:
        candidate = model_paths.contained_path(base_dir, filename)
        if candidate is not None and os.path.isfile(candidate):
            return candidate, base_dir
    return None, None


async def _organize_one_model(model: dict) -> str:
    """Move one model into its base-model subfolder; return 'moved', 'skipped' or 'errors'."""
    filename = model["filename"]
    src, src_base_dir = _resolve_organize_source(model.get("model_type") or "", filename)
    if not src or not src_base_dir:
        return "skipped"

    subfolder = _sanitize_subfolder_name(model.get("base_model") or "")
    target_rel = subfolder + "/" + os.path.basename(filename)
    if filename == target_rel:
        return "skipped"

    target_abs = os.path.join(src_base_dir, target_rel)
    if os.path.exists(target_abs):
        return "skipped"

    try:
        os.makedirs(os.path.dirname(target_abs), exist_ok=True)
        shutil.move(src, target_abs)
        await model_repo.update_model_filename(filename, target_rel)
        return "moved"
    except Exception:
        return "errors"


async def _organize_models(request):
    models = await model_repo.get_all_models_slim()
    counts = {"moved": 0, "skipped": 0, "errors": 0}
    for model in models:
        counts[await _organize_one_model(model)] += 1
    return ok(counts)


async def _get_pending_reorganize(request):
    jobs = await model_repo.get_pending_jobs()
    return ok([j["filename"] for j in jobs])


async def _get_unregistered_files(request):
    """Scan all model dirs and return files not yet in the models table."""
    result = disk_scanner.scan_all()
    registered = await model_repo.get_registered_filenames()
    unregistered: dict = {}
    for mtype, files in result.items():
        hits = [f for f in files if f["filename"] not in registered]
        if hits:
            unregistered[mtype] = hits
    return ok(unregistered)


async def _register_model(request):
    """Register a model file manually with optional metadata."""
    body = await request.json()
    filename = body.get("filename", "").strip()
    model_type = body.get("model_type", "").strip()
    if not filename or not model_type:
        return err("filename and model_type are required", 400)

    base_model = body.get("base_model", "").strip()
    tags = body.get("tags") or []
    description = body.get("description", "")
    file_hash = body.get("file_hash", "").strip()
    source_platform = body.get("source_platform", "").strip()
    source_id = body.get("source_id", "").strip()
    civitai_model_id = body.get("civitai_model_id", "").strip()

    resolved = model_paths.find_file(model_type, filename)
    if resolved is None:
        return err("file_not_found", 404)

    model_id = await model_repo.register_model(
        filename=filename,
        model_type=model_type,
        base_model=base_model,
        tags=tags,
        description=description,
        file_hash=file_hash,
        source_platform=source_platform,
        source_id=source_id,
        civitai_model_id=civitai_model_id,
    )
    return ok({"model_id": model_id})


async def _civitai_lookup(sha256: str) -> dict | None:
    """Thin wrapper so tests can monkeypatch the CivitAI call without touching the provider."""
    from ..services.providers.civitai_provider import CivitaiProvider

    return await CivitaiProvider().lookup_by_hash(sha256)


async def _hash_file(path: str) -> str:
    """Thin wrapper so tests can monkeypatch file hashing without patching asyncio globally."""
    return await asyncio.to_thread(model_paths.compute_file_hash, path)


async def _hash_lookup(request):
    """Compute SHA-256 of a model file and look it up on CivitAI."""
    body = await request.json()
    filename = body.get("filename", "").strip()
    model_type = body.get("model_type", "").strip()
    if not filename or not model_type:
        return err("filename and model_type are required", 400)

    resolved = model_paths.find_file(model_type, filename)
    if resolved is None:
        return err("file_not_found", 404)

    file_hash = await _hash_file(resolved)

    try:
        metadata = await _civitai_lookup(file_hash)
    except httpx.HTTPError:
        return err("civitai_unavailable", 503)

    if metadata is None:
        return ok({"hash": file_hash, "match": False})
    return ok({"hash": file_hash, "match": True, "metadata": metadata})


async def _resolve_model_link(parsed):
    """Thin wrapper so tests can monkeypatch the provider call without touching the resolver."""
    return await link_resolver.resolve(parsed)


async def _resolve_link(request):
    """Resolve a pasted CivitAI/HuggingFace model URL into registration metadata."""
    body = await request.json()
    url = (body.get("url") or "").strip()
    if not url:
        return err("url is required", 400)

    parsed = link_resolver.parse_model_link(url)
    if parsed is None:
        return err("invalid_url", 400)

    try:
        metadata = await _resolve_model_link(parsed)
    except httpx.HTTPError:
        return err("provider_unavailable", 503)

    if metadata is None:
        return err("not_found", 404)

    if parsed.platform == link_resolver.HUGGINGFACE:
        source_id = parsed.repo_id
    else:
        source_id = metadata.get("civitai_version_id") or parsed.version_id
    return ok({"platform": parsed.platform, "source_id": source_id, "metadata": metadata})


def add_model_routes(routes):
    routes.get("/tiny-model-manager/api/models")(json_route(_list_models))
    routes.get("/tiny-model-manager/api/models/unregistered")(json_route(_get_unregistered_files))
    routes.post("/tiny-model-manager/api/models/register")(json_route(_register_model))
    routes.post("/tiny-model-manager/api/models/hash-lookup")(json_route(_hash_lookup))
    routes.post("/tiny-model-manager/api/models/resolve-link")(json_route(_resolve_link))
    routes.delete("/tiny-model-manager/api/models/{model_type}/{path:.*}")(
        json_route(_delete_model)
    )
    routes.get("/tiny-model-manager/api/model-types")(json_route(_list_model_types))
    routes.post("/tiny-model-manager/api/models/{model_type}/{path:.*}/move")(
        json_route(_move_model)
    )
    routes.post("/tiny-model-manager/api/models/organize")(json_route(_organize_models))
    routes.get("/tiny-model-manager/api/reorganize/pending")(json_route(_get_pending_reorganize))
