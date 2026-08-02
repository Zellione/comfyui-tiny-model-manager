"""Download, store and export CivitAI workflows (F-129).

CivitAI never serves a bare workflow JSON: every entry of the ``Workflows`` model type
ships a ``.zip`` (file type ``Archive``), and one archive commonly holds several ComfyUI
graphs plus readme/preview files. So a download resolves to *one* ``workflow_entries``
row — the source page, owning the description, tags and gallery media — and *one*
``workflows`` row per graph found inside.

The archive is fetched with the CivitAI API key (the download endpoint 401s without one)
and written under ``<data_dir>/workflows/<media_hash>/<version_id>/``. As in F-95 nothing
is ever written or deleted through a path built directly from request data: every segment
is either a hex hash, an integer-checked version id, or a name normalised by
``_safe_graph_filename``, and the result is confirmed with ``model_paths.contained_path``.
"""

import hashlib
import json
import logging
import os
import re
import shutil
import tempfile
import zipfile

import folder_paths
import httpx

from .. import config as cfg
from ..db import workflow_repo
from . import media_cleanup, model_paths
from .providers import civitai
from .url_guard import is_allowed_url

_log = logging.getLogger("tiny-model-manager")

CIVITAI_WORKFLOW_TYPE = "Workflows"

# A workflow archive is normally 5-150 KB, but some bundle sample assets. The ceiling
# keeps a mis-tagged multi-gigabyte upload from filling the data directory, and the
# per-graph ceiling bounds the JSON we parse into memory.
_MAX_ARCHIVE_BYTES = 100 * 1024 * 1024
_MAX_GRAPH_BYTES = 8 * 1024 * 1024
_MAX_GRAPHS = 50

_HASH_RE = re.compile(r"[A-Za-z0-9]{1,128}")
_UNSAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._ -]")
_DEFAULT_USER = "default"


class WorkflowPayloadError(Exception):
    """The downloaded payload held no usable ComfyUI graph."""


class WorkflowTooLargeError(Exception):
    """The archive exceeded the size ceiling and was abandoned mid-stream."""


def workflow_media_hash(platform: str, page_id: str) -> str:
    """Stable media hash for a workflow source page.

    The ``workflow:`` prefix keeps it in a different space from
    ``metadata_fetcher.catalog_media_hash``, so a workflow page can never adopt the media
    directory of a model catalog entry.
    """
    return hashlib.sha256(f"workflow:{platform}:{page_id}".encode()).hexdigest()


def workflow_subdir(media_hash: str, *parts: str) -> str:
    """Resolve a directory under the workflow root, guarding against traversal.

    Same shape as ``media_cleanup.media_subdir``: the allowlist rejects separators, and
    the containment check confirms the result at the point the path is built.
    """
    if not _HASH_RE.fullmatch(media_hash):
        raise ValueError(f"Invalid workflow hash: {media_hash!r}")
    resolved = model_paths.contained_path(cfg.workflows_dir(), media_hash, *parts)
    if resolved is None:
        raise ValueError(f"Invalid workflow path: {media_hash!r}")
    return resolved


def _safe_graph_filename(name: str) -> str:
    """Turn an archive member name into a single safe ``.json`` filename.

    Only the basename survives, every character outside the allowlist becomes ``_``, and
    the result can neither be empty nor a traversal component.
    """
    base = os.path.basename(name.replace("\\", "/")).strip()
    if base.lower().endswith(".json"):
        base = base[: -len(".json")]
    cleaned = _UNSAFE_NAME_RE.sub("_", base).strip(" .")
    if not cleaned:
        cleaned = "workflow"
    return f"{cleaned[:120]}.json"


def _is_comfy_graph(data: object) -> bool:
    """True for a ComfyUI frontend workflow graph.

    Real payloads carry ``nodes`` plus ``links``/``last_node_id``; requiring the node list
    alone is enough to reject readme JSON, package manifests and API-format prompts.
    """
    return isinstance(data, dict) and isinstance(data.get("nodes"), list)


def _graph_from_bytes(raw: bytes) -> dict | None:
    try:
        parsed = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        return None
    return parsed if _is_comfy_graph(parsed) else None


def _extract_from_zip(path: str) -> list[tuple[str, dict]]:
    graphs: list[tuple[str, dict]] = []
    with zipfile.ZipFile(path) as archive:
        for info in archive.infolist():
            if len(graphs) >= _MAX_GRAPHS:
                break
            name = info.filename
            if info.is_dir() or not name.lower().endswith(".json"):
                continue
            if name.startswith("__MACOSX/") or os.path.basename(name).startswith("._"):
                continue
            # Zip-slip: a member named ../../x.json or /etc/x.json is dropped outright
            # rather than normalised, so a hostile archive cannot even influence a name.
            normalised = name.replace("\\", "/")
            if normalised.startswith("/") or ".." in normalised.split("/"):
                continue
            if info.file_size > _MAX_GRAPH_BYTES:
                continue
            graph = _graph_from_bytes(archive.read(info))
            if graph is not None:
                graphs.append((_safe_graph_filename(name), graph))
    return graphs


def extract_graphs(path: str) -> list[tuple[str, dict]]:
    """Every ComfyUI graph in a downloaded payload, as ``(filename, graph)`` pairs.

    Handles both shapes CivitAI can return: a zip archive (the normal case) and a bare
    JSON graph. Raises ``WorkflowPayloadError`` when neither yields a usable graph.
    """
    if zipfile.is_zipfile(path):
        try:
            graphs = _extract_from_zip(path)
        except (zipfile.BadZipFile, OSError) as exc:
            raise WorkflowPayloadError("corrupt_archive") from exc
    else:
        if os.path.getsize(path) > _MAX_GRAPH_BYTES:
            raise WorkflowPayloadError("no_workflow_json")
        with open(path, "rb") as f:
            graph = _graph_from_bytes(f.read())
        graphs = [(_safe_graph_filename(os.path.basename(path)), graph)] if graph else []
    if not graphs:
        raise WorkflowPayloadError("no_workflow_json")
    return graphs


async def _fetch_archive(url: str, dest: str, headers: dict) -> None:
    """Stream ``url`` to ``dest``, aborting past the archive ceiling.

    Wrapped in its own coroutine so tests can monkeypatch this module-level name instead
    of the HTTP client.
    """
    written = 0
    async with httpx.AsyncClient(timeout=httpx.Timeout(120.0), follow_redirects=True) as client:
        async with client.stream("GET", url, headers=headers) as resp:
            resp.raise_for_status()
            with open(dest, "wb") as f:
                async for chunk in resp.aiter_bytes(65536):
                    written += len(chunk)
                    if written > _MAX_ARCHIVE_BYTES:
                        raise WorkflowTooLargeError("archive_too_large")
                    f.write(chunk)


def _pick_version(page: dict, version_id: str) -> dict | None:
    versions = page.get("modelVersions") or []
    if version_id:
        match = next((v for v in versions if str(v.get("id")) == str(version_id)), None)
        if match:
            return match
    return versions[0] if versions else None


def _pick_archive_file(version: dict) -> dict | None:
    """The file to download for a workflow version.

    Workflow files carry CivitAI type ``Archive``, not ``Model``, so the primary flag is
    the only reliable signal; the first file is the fallback.
    """
    files = version.get("files") or []
    return next((f for f in files if f.get("primary")), None) or (files[0] if files else None)


def _version_image_urls(version: dict) -> list[str]:
    return [img["url"] for img in (version.get("images") or [])[:5] if img.get("url")]


async def _store_graphs(entry_id: int, media_hash: str, version: dict, graphs: list) -> list[dict]:
    """Write each graph to disk and upsert its row; returns the stored graph records."""
    version_id = str(version.get("id") or "")
    version_name = version.get("name", "")
    # The version id comes from the provider payload, but it reaches a filesystem path,
    # so it is normalised to digits before being used as a directory name.
    version_dir = version_id if version_id.isdigit() else "0"
    dest_dir = workflow_subdir(media_hash, version_dir)
    os.makedirs(dest_dir, exist_ok=True)
    stored: list[dict] = []
    for filename, graph in graphs:
        dest = os.path.join(dest_dir, filename)
        with open(dest, "w", encoding="utf-8") as f:
            json.dump(graph, f)
        workflow_id = await workflow_repo.upsert_workflow(
            entry_id=entry_id,
            name=filename[: -len(".json")],
            local_path=os.path.join(media_hash, version_dir, filename),
            version_id=version_id,
            version_name=version_name,
            node_count=len(graph.get("nodes") or []),
        )
        stored.append(
            {
                "id": workflow_id,
                "name": filename[: -len(".json")],
                "version_id": version_id,
                "version_name": version_name,
                "node_count": len(graph.get("nodes") or []),
            }
        )
    return stored


async def download_workflow(model_id: str, version_id: str = "") -> dict:
    """Download a CivitAI workflow page, store every graph it contains, return the entry.

    Re-downloading the same version upserts rather than duplicating: the entry is keyed on
    (platform, page id) and each graph on (entry, relative path).
    """
    page = await civitai.get_model_page(int(model_id))
    version = _pick_version(page, version_id)
    if not version:
        raise WorkflowPayloadError("no_version")
    archive = _pick_archive_file(version)
    if not archive or not archive.get("downloadUrl"):
        raise WorkflowPayloadError("no_download_url")
    url = archive["downloadUrl"]
    if not is_allowed_url(url):
        raise ValueError("Download URL host is not allowed")

    media_hash = workflow_media_hash("civitai", str(model_id))
    with tempfile.TemporaryDirectory() as tmp:
        payload = os.path.join(tmp, "payload.bin")
        await _fetch_archive(url, payload, civitai.auth_headers())
        graphs = extract_graphs(payload)

    image_urls = _version_image_urls(version)
    entry_id = await workflow_repo.upsert_workflow_entry(
        source_platform="civitai",
        source_page_id=str(model_id),
        source_page_url=f"https://civitai.com/models/{model_id}",
        display_name=page.get("name", ""),
        description=page.get("description") or version.get("description") or "",
        base_model=version.get("baseModel", ""),
        tags=page.get("tags") or [],
        thumbnail_url=image_urls[0] if image_urls else "",
        media_hash=media_hash,
    )
    stored = await _store_graphs(entry_id, media_hash, version, graphs)
    await _download_media(media_hash, image_urls)
    return {"entry_id": entry_id, "workflows": stored}


async def _download_media(media_hash: str, image_urls: list[str]) -> None:
    """Populate the entry's gallery, reusing the models-side download helper.

    Failures are swallowed: a missing preview must never fail a download whose graphs are
    already on disk.
    """
    if not image_urls:
        return
    try:
        from .metadata_fetcher import _iter_downloaded_urls

        await _iter_downloaded_urls(media_hash, image_urls)
    except Exception:
        _log.warning("Could not download workflow preview media", exc_info=True)


def list_entry_media(media_hash: str) -> list[dict]:
    """Gallery items stored under the entry's media hash, in MediaGallery's shape."""
    if not media_hash or not _HASH_RE.fullmatch(media_hash):
        return []
    try:
        media_dir = media_cleanup.media_subdir(media_hash)
    except ValueError:
        return []
    if not os.path.isdir(media_dir):
        return []
    items: list[dict] = []
    for i, name in enumerate(sorted(os.listdir(media_dir))):
        full = os.path.join(media_dir, name)
        if not os.path.isfile(full):
            continue
        ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
        items.append(
            {
                "id": i,
                "media_type": "video" if ext in ("mp4", "webm", "mov") else "image",
                "local_path": full,
            }
        )
    return items


def graph_path(workflow: dict) -> str | None:
    """Absolute path of a stored graph, or None when it escapes the workflow root."""
    return model_paths.contained_path(cfg.workflows_dir(), workflow["local_path"])


def read_graph(workflow: dict) -> dict:
    """Load a stored graph from disk. Raises FileNotFoundError when it is gone."""
    path = graph_path(workflow)
    if path is None or not os.path.isfile(path):
        raise FileNotFoundError(workflow["local_path"])
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _user_workflows_dir() -> str:
    """ComfyUI's own workflow browser directory.

    ``get_user_directory`` exists on current ComfyUI; the ``base_path`` fallback keeps
    export working on older builds that only expose the base path.
    """
    get_user_dir = getattr(folder_paths, "get_user_directory", None)
    if callable(get_user_dir):
        user_dir = str(get_user_dir())
    else:
        user_dir = os.path.join(str(getattr(folder_paths, "base_path", cfg.data_dir())), "user")
    return os.path.join(user_dir, _DEFAULT_USER, "workflows")


def _unique_export_path(base_dir: str, filename: str) -> str | None:
    """A free path for ``filename`` inside ``base_dir``, suffixed on collision."""
    stem, ext = os.path.splitext(filename)
    for suffix in range(100):
        candidate = filename if suffix == 0 else f"{stem}_{suffix}{ext}"
        path = model_paths.contained_path(base_dir, candidate)
        if path is None:
            return None
        if not os.path.exists(path):
            return path
    return None


async def export_workflow(workflow_id: int) -> str:
    """Copy a stored graph into ComfyUI's user workflows directory; returns its path.

    The file lands where ComfyUI's native workflow browser looks, so the workflow shows up
    there without an import step.
    """
    workflow = await workflow_repo.get_workflow(workflow_id)
    if workflow is None:
        raise FileNotFoundError("workflow_not_found")
    source = graph_path(workflow)
    if source is None or not os.path.isfile(source):
        raise FileNotFoundError("graph_missing")
    dest_dir = _user_workflows_dir()
    os.makedirs(dest_dir, exist_ok=True)
    dest = _unique_export_path(dest_dir, _safe_graph_filename(workflow["name"]))
    if dest is None:
        raise FileNotFoundError("export_target_unavailable")
    shutil.copyfile(source, dest)
    return dest


async def delete_entry(entry_id: int) -> bool:
    """Delete a workflow entry, its graphs on disk and its media. False when unknown."""
    entry = await workflow_repo.get_workflow_entry(entry_id)
    if entry is None:
        return False
    media_hash = entry.get("media_hash", "")
    if media_hash and _HASH_RE.fullmatch(media_hash):
        # Removed by (root, single validated segment), never by a stored absolute path.
        target = model_paths.contained_path(cfg.workflows_dir(), media_hash)
        if target is not None and os.path.isdir(target):
            shutil.rmtree(target, ignore_errors=True)
    await workflow_repo.delete_workflow_entry(entry_id)
    # Runs after the row is gone so the live-hash check sees the post-delete state.
    await media_cleanup.cleanup_model_media(media_hash)
    return True
