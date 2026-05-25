import os
import folder_paths
from aiohttp import web
from ..db import model_repo
from .metadata import _derive_source_url


def add_model_routes(routes):

    @routes.get("/tiny-model-manager/api/models")
    async def list_models(request):
        try:
            result = {}
            for folder_type, (dirs, extensions) in folder_paths.folder_names_and_paths.items():
                if folder_type == "configs":
                    continue
                models = []
                for base_dir in dirs:
                    if not os.path.isdir(base_dir):
                        continue
                    for root, _, files in os.walk(base_dir):
                        for fname in files:
                            ext = os.path.splitext(fname)[1].lower()
                            if ext in extensions:
                                full = os.path.join(root, fname)
                                rel = os.path.relpath(full, base_dir).replace("\\", "/")
                                stat = os.stat(full)
                                models.append({
                                    "filename": rel,
                                    "base_dir": base_dir,
                                    "size_bytes": stat.st_size,
                                    "modified_at": stat.st_mtime,
                                })
                if models:
                    result[folder_type] = models
            all_filenames = [f["filename"] for files in result.values() for f in files]
            meta_map = await model_repo.get_metadata_by_filenames(all_filenames)
            for files in result.values():
                for f in files:
                    m = meta_map.get(f["filename"])
                    if m:
                        source_url = _derive_source_url(
                            m.get("source_platform", ""), m.get("source_id", ""), m.get("civitai_model_id", "")
                        )
                        f["metadata"] = {
                            "description": m.get("description", ""),
                            "trigger_words": m.get("trigger_words", []),
                            "tags": m.get("tags", []),
                            "media": m.get("media", []),
                            "base_model": m.get("base_model", ""),
                            "source_platform": m.get("source_platform", ""),
                            "source_url": source_url,
                        }
            return web.json_response({"success": True, "data": result})
        except Exception as exc:
            return web.json_response({"success": False, "error": str(exc)}, status=500)

    @routes.delete("/tiny-model-manager/api/models/{model_type}/{path:.*}")
    async def delete_model(request):
        model_type = request.match_info["model_type"]
        rel_path = request.match_info["path"]
        try:
            dirs, _ = folder_paths.folder_names_and_paths.get(model_type, ([], set()))
            for base_dir in dirs:
                candidate = os.path.normpath(os.path.join(base_dir, rel_path))
                # Guard against path traversal
                if not candidate.startswith(os.path.normpath(base_dir)):
                    continue
                if os.path.isfile(candidate):
                    os.remove(candidate)
                    return web.json_response({"success": True})
            return web.json_response({"success": False, "error": "File not found"}, status=404)
        except Exception as exc:
            return web.json_response({"success": False, "error": str(exc)}, status=500)
