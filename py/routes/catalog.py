import os
import shutil

import folder_paths
from aiohttp import web

from .. import config as cfg
from ..db import model_repo


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


def _scan_all_files() -> dict[str, list[dict]]:
    """Scan all ComfyUI model folders and return files grouped by type."""
    result: dict[str, list[dict]] = {}
    scanned: set[str] = set()

    for folder_type, (dirs, extensions) in folder_paths.folder_names_and_paths.items():
        if folder_type in _SKIP_TYPES:
            continue
        for base_dir in dirs:
            norm = os.path.normpath(base_dir)
            scanned.add(norm)
            if not os.path.isdir(base_dir):
                continue
            for root, _, files in os.walk(base_dir):
                for fname in files:
                    if os.path.splitext(fname)[1].lower() not in (
                        set(extensions) | _BROAD_EXTENSIONS
                    ):
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

    models_dir = getattr(folder_paths, "models_dir", None)
    if models_dir and os.path.isdir(models_dir):
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


def add_catalog_routes(routes):

    @routes.get("/tiny-model-manager/api/catalog")
    async def list_catalog(request):
        try:
            entries = await model_repo.list_catalog_entries()
            # Scan filesystem for all model files
            all_files = _scan_all_files()
            # Build set of filenames that belong to a catalog entry
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

            # Unknown files: on disk but not linked to any catalog entry
            unknown: dict[str, list[dict]] = {}
            for mtype, files in all_files.items():
                for f in files:
                    if f["filename"] not in cataloged:
                        unknown.setdefault(mtype, []).append(f)

            return web.json_response(
                {"success": True, "data": {"entries": entries, "unknown_files": unknown}}
            )
        except Exception as exc:
            return web.json_response({"success": False, "error": str(exc)}, status=500)

    @routes.get("/tiny-model-manager/api/catalog/{platform}/{page_id:.*}")
    async def get_catalog_entry(request):
        platform = request.match_info["platform"]
        page_id = request.match_info["page_id"]
        try:
            entry = await model_repo.get_catalog_entry(platform, page_id)
            if not entry:
                return web.json_response(
                    {"success": False, "error": "Catalog entry not found"}, status=404
                )
            # Compute is_downloaded per repo file
            for rf in entry["repo_files"]:
                rf["is_downloaded"] = _model_file_exists(rf["model_type"], rf["filename"])
            # Compute is_empty
            entry["is_empty"] = not any(
                _model_file_exists(f["model_type"], f["filename"]) for f in entry["installed_files"]
            )
            return web.json_response({"success": True, "data": entry})
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
                    {"success": False, "error": "Catalog entry not found"}, status=404
                )
            _delete_media_paths(result["media_paths"])
            return web.json_response({"success": True})
        except Exception as exc:
            return web.json_response({"success": False, "error": str(exc)}, status=500)
