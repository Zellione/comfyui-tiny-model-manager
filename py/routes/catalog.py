import os
import shutil

import folder_paths
from aiohttp import web

from .. import config as cfg
from ..db import model_repo

_MEDIA_VIDEO_EXTS = {"mp4", "webm", "mov"}
_CATALOG_NOT_FOUND = "Catalog entry not found"


def _list_catalog_media(media_hash: str) -> list[dict]:
    """List gallery media stored under the catalog entry's media_hash directory.

    These files persist on disk after a model is uninstalled, so the gallery survives
    even when no file is installed.
    """
    if not media_hash:
        return []
    base = os.path.realpath(cfg.media_dir())
    media_dir = os.path.realpath(os.path.join(base, media_hash))
    if not media_dir.startswith(base + os.sep):
        return []
    if not os.path.isdir(media_dir):
        return []
    items: list[dict] = []
    for i, name in enumerate(sorted(os.listdir(media_dir))):
        full = os.path.join(media_dir, name)
        if not os.path.isfile(full):
            continue
        ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
        media_type = "video" if ext in _MEDIA_VIDEO_EXTS else "image"
        items.append({"id": i, "media_type": media_type, "local_path": full})
    return items


def _annotate_catalog_detail(entry: dict) -> dict:
    """Compute per-file install state, is_empty, and the gallery for a catalog entry.

    Shared by the GET and refetch routes so both return a fully-resolved detail payload.
    """
    # Build basename → installed_path map from DB-linked installed files so subfolder
    # installs (e.g. Illustrious/foo.safetensors) are correctly recognised.
    installed_basename_map: dict[str, str] = {
        os.path.basename(f["filename"]): f["filename"] for f in entry["installed_files"]
    }
    for rf in entry["repo_files"]:
        basename = os.path.basename(rf["filename"])
        db_path = installed_basename_map.get(basename, "")
        rf["is_downloaded"] = bool(db_path) or _model_file_exists(rf["model_type"], rf["filename"])
        rf["installed_path"] = db_path
    entry["is_empty"] = not any(
        _model_file_exists(f["model_type"], f["filename"]) for f in entry["installed_files"]
    )
    # Catalog-owned gallery (survives uninstall); served like model media.
    entry["media"] = _list_catalog_media(entry.get("media_hash", ""))
    return entry


def _model_file_exists(model_type: str, filename: str) -> bool:
    """Return True if the model file exists on disk in any registered location."""
    candidates: list[str] = []
    dirs, _ = folder_paths.folder_names_and_paths.get(model_type, ([], {}))
    for base_dir in dirs:
        candidates.append(os.path.join(base_dir, filename))
    models_dir = getattr(folder_paths, "models_dir", None)
    if models_dir:
        candidates.append(os.path.join(models_dir, model_type, filename))
    candidates.append(os.path.join(cfg.data_dir(), "models", model_type, filename))
    return any(os.path.isfile(c) for c in candidates)


def _model_file_stat(model_type: str, filename: str) -> dict | None:
    """Return size_bytes and modified_at for the first found copy of the file."""
    candidates: list[str] = []
    dirs, _ = folder_paths.folder_names_and_paths.get(model_type, ([], {}))
    for base_dir in dirs:
        candidates.append(os.path.join(base_dir, filename))
    models_dir = getattr(folder_paths, "models_dir", None)
    if models_dir:
        candidates.append(os.path.join(models_dir, model_type, filename))
    candidates.append(os.path.join(cfg.data_dir(), "models", model_type, filename))
    for c in candidates:
        try:
            s = os.stat(c)
            return {"size_bytes": s.st_size, "modified_at": s.st_mtime}
        except OSError:
            pass
    return None


_BROAD_EXTENSIONS = {".safetensors", ".ckpt", ".pt", ".bin", ".gguf", ".pth"}
_SKIP_TYPES = {"configs", "custom_nodes"}


def _scan_registered_folders(result: dict, scanned: set) -> None:
    """Scan folders registered in folder_paths and populate result in-place."""
    for folder_type, (dirs, extensions) in folder_paths.folder_names_and_paths.items():
        if folder_type in _SKIP_TYPES:
            continue
        allowed = set(extensions) | _BROAD_EXTENSIONS
        for base_dir in dirs:
            scanned.add(os.path.normpath(base_dir))
            if not os.path.isdir(base_dir):
                continue
            for root, _, files in os.walk(base_dir):
                for fname in files:
                    if os.path.splitext(fname)[1].lower() not in allowed:
                        continue
                    full = os.path.join(root, fname)
                    rel = os.path.relpath(full, base_dir).replace("\\", "/")
                    s = os.stat(full)
                    result.setdefault(folder_type, []).append(
                        {
                            "filename": rel,
                            "base_dir": base_dir,
                            "size_bytes": s.st_size,
                            "modified_at": s.st_mtime,
                        }
                    )


def _scan_extra_models_dir(result: dict, scanned: set, models_dir: str) -> None:
    """Scan models_dir for folder types not already covered by folder_paths."""
    for name in sorted(os.listdir(models_dir)):
        if name in _SKIP_TYPES:
            continue
        physical = os.path.normpath(os.path.join(models_dir, name))
        if not os.path.isdir(physical) or physical in scanned:
            continue
        scanned.add(physical)
        for root, _, files in os.walk(physical):
            for fname in files:
                if os.path.splitext(fname)[1].lower() not in _BROAD_EXTENSIONS:
                    continue
                full = os.path.join(root, fname)
                rel = os.path.relpath(full, physical).replace("\\", "/")
                s = os.stat(full)
                result.setdefault(name, []).append(
                    {
                        "filename": rel,
                        "base_dir": physical,
                        "size_bytes": s.st_size,
                        "modified_at": s.st_mtime,
                    }
                )


def _scan_all_files() -> dict[str, list[dict]]:
    """Scan all ComfyUI model folders and return files grouped by type."""
    result: dict[str, list[dict]] = {}
    scanned: set[str] = set()
    _scan_registered_folders(result, scanned)
    models_dir = getattr(folder_paths, "models_dir", None)
    if models_dir and os.path.isdir(models_dir):
        _scan_extra_models_dir(result, scanned, models_dir)
    return result


def _delete_media_paths(paths: list[str]) -> None:
    """Remove media files and empty parent directories."""
    dirs_to_check: set[str] = set()
    for p in paths:
        try:
            if os.path.isfile(p):
                os.remove(p)
                dirs_to_check.add(os.path.dirname(p))
        except OSError:
            pass
    for d in dirs_to_check:
        try:
            if os.path.isdir(d) and not os.listdir(d):
                shutil.rmtree(d, ignore_errors=True)
        except OSError:
            pass


def _annotate_entries(entries: list) -> tuple[list, set[str]]:
    """Attach disk stats to each entry's installed_files; return (entries, cataloged filenames)."""
    cataloged: set[str] = set()
    for entry in entries:
        stat_list = []
        for f in entry["installed_files"]:
            st = _model_file_stat(f["model_type"], f["filename"])
            stat_list.append(
                {
                    "filename": f["filename"],
                    "model_type": f["model_type"],
                    **(st or {"size_bytes": 0, "modified_at": 0}),
                }
            )
            if st is not None:
                cataloged.add(f["filename"])
        entry["installed_files"] = stat_list
        entry["is_empty"] = not any(
            st["size_bytes"] > 0 or _model_file_exists(st["model_type"], st["filename"])
            for st in stat_list
        )
    return entries, cataloged


def _collect_unknown(all_files: dict, cataloged: set[str]) -> dict:
    """Return files on disk that are not linked to any catalog entry."""
    unknown: dict[str, list[dict]] = {}
    for mtype, files in all_files.items():
        for f in files:
            if f["filename"] not in cataloged:
                unknown.setdefault(mtype, []).append(f)
    return unknown


async def _handle_get_catalog_entry(platform: str, page_id: str) -> web.Response:
    entry = await model_repo.get_catalog_entry(platform, page_id)
    if not entry:
        return web.json_response({"success": False, "error": _CATALOG_NOT_FOUND}, status=404)
    return web.json_response({"success": True, "data": _annotate_catalog_detail(entry)})


async def _handle_update_catalog_metadata(platform: str, page_id: str, body: dict) -> web.Response:
    # Absent keys are left unchanged; present keys are written verbatim (so the
    # user can clear fields).
    ok = await model_repo.update_catalog_metadata(
        platform,
        page_id,
        description=body.get("description"),
        trigger_words=body.get("trigger_words"),
        tags=body.get("tags"),
        base_model=body.get("base_model"),
    )
    if not ok:
        return web.json_response({"success": False, "error": _CATALOG_NOT_FOUND}, status=404)
    return web.json_response({"success": True})


def add_catalog_routes(routes):

    @routes.get("/tiny-model-manager/api/catalog")
    async def list_catalog(request):
        try:
            entries = await model_repo.list_catalog_entries()
            all_files = _scan_all_files()
            entries, cataloged = _annotate_entries(entries)
            unknown = _collect_unknown(all_files, cataloged)
            return web.json_response(
                {"success": True, "data": {"entries": entries, "unknown_files": unknown}}
            )
        except Exception as exc:
            return web.json_response({"success": False, "error": str(exc)}, status=500)

    @routes.get("/tiny-model-manager/api/catalog/{platform}/{page_id:.*}")
    async def get_catalog_entry(request):
        try:
            return await _handle_get_catalog_entry(
                request.match_info["platform"], request.match_info["page_id"]
            )
        except Exception as exc:
            return web.json_response({"success": False, "error": str(exc)}, status=500)

    @routes.put("/tiny-model-manager/api/catalog/{platform}/{page_id:.*}/metadata")
    async def update_catalog_metadata(request):
        try:
            return await _handle_update_catalog_metadata(
                request.match_info["platform"],
                request.match_info["page_id"],
                await request.json(),
            )
        except Exception as exc:
            return web.json_response({"success": False, "error": str(exc)}, status=500)

    @routes.post("/tiny-model-manager/api/catalog/{platform}/{page_id:.*}/refetch")
    async def refetch_catalog_entry(request):
        platform = request.match_info["platform"]
        page_id = request.match_info["page_id"]
        try:
            from ..services.metadata_fetcher import refetch_catalog_metadata

            entry = await refetch_catalog_metadata(platform, page_id)
            if entry is None:
                return web.json_response(
                    {"success": False, "error": "Could not fetch metadata from source"},
                    status=502,
                )
            return web.json_response({"success": True, "data": _annotate_catalog_detail(entry)})
        except Exception as exc:
            return web.json_response({"success": False, "error": str(exc)}, status=500)

    @routes.delete("/tiny-model-manager/api/catalog/{platform}/{page_id:.*}")
    async def delete_catalog_entry(request):
        platform = request.match_info["platform"]
        page_id = request.match_info["page_id"]
        try:
            result = await model_repo.delete_catalog_entry(platform, page_id)
            if result is None:
                return web.json_response(
                    {"success": False, "error": _CATALOG_NOT_FOUND}, status=404
                )
            _delete_media_paths(result["media_paths"])
            return web.json_response({"success": True})
        except Exception as exc:
            return web.json_response({"success": False, "error": str(exc)}, status=500)
