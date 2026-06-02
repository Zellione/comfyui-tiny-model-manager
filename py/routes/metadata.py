import os
import re

from aiohttp import web

from ..db import model_repo


def _parse_source_url(url: str) -> tuple[str, str, str]:
    """Return (platform, source_id, civitai_model_id) or ('', '', '') if unrecognised."""
    m = re.match(r"https?://(?:www\.)?civitai\.com/models/(\d+)", url)
    if m:
        return "civitai", "", m.group(1)
    m = re.match(r"https?://huggingface\.co/([^/?#]+/[^/?#]+)", url)
    if m:
        return "huggingface", m.group(1), ""
    return "", "", ""


def _resolve_file_size(model_type: str, path: str) -> int:
    """Return os.path.getsize for the model file, or 0 if the file cannot be found."""
    import folder_paths

    from .. import config as cfg

    candidates: list[str] = []
    dirs, _ = folder_paths.folder_names_and_paths.get(model_type, ([], {}))
    for base_dir in dirs:
        candidates.append(os.path.join(base_dir, path))
    models_dir = getattr(folder_paths, "models_dir", None)
    if models_dir:
        candidates.append(os.path.join(models_dir, model_type, path))
    candidates.append(os.path.join(cfg.data_dir(), "models", model_type, path))

    for full in candidates:
        try:
            return os.path.getsize(full)
        except OSError:
            pass
    return 0


def _find_file_on_disk(model_type: str, model_dir: str, filename: str) -> str:
    """Return the absolute path of a file if it exists, or empty string if not found."""
    import folder_paths

    from .. import config as cfg

    candidates: list[str] = []
    dirs, _ = folder_paths.folder_names_and_paths.get(model_type, ([], {}))
    for base_dir in dirs:
        candidates.append(os.path.join(base_dir, model_dir, filename))
    models_dir = getattr(folder_paths, "models_dir", None)
    if models_dir:
        candidates.append(os.path.join(models_dir, model_type, model_dir, filename))
    candidates.append(os.path.join(cfg.data_dir(), "models", model_type, model_dir, filename))
    for full in candidates:
        if os.path.isfile(full):
            return full
    return ""


def _file_exists_on_disk(model_type: str, model_dir: str, filename: str) -> bool:
    return bool(_find_file_on_disk(model_type, model_dir, filename))


def _get_file_mtime(model_type: str, model_dir: str, filename: str) -> float | None:
    full = _find_file_on_disk(model_type, model_dir, filename)
    if full:
        try:
            return os.path.getmtime(full)
        except OSError:
            pass
    return None


def _derive_source_url(source_platform: str, source_id: str, civitai_model_id: str) -> str:
    if source_platform == "civitai" and civitai_model_id:
        return f"https://civitai.com/models/{civitai_model_id}"
    if source_platform == "huggingface" and source_id:
        return f"https://huggingface.co/{source_id}"
    return ""


def add_metadata_routes(routes):

    @routes.get("/tiny-model-manager/api/models/{model_type}/{path:.*}/metadata")
    async def get_metadata(request):
        path = request.match_info["path"]
        model_type = request.match_info["model_type"]
        try:
            meta = await model_repo.get_model_by_filename(path)
            size_bytes = _resolve_file_size(model_type, path)
            if not meta:
                return web.json_response(
                    {
                        "success": True,
                        "data": {
                            "description": "",
                            "trigger_words": [],
                            "tags": [],
                            "media": [],
                            "base_model": "",
                            "source_platform": "",
                            "source_url": "",
                            "size_bytes": size_bytes,
                        },
                    }
                )
            source_url = _derive_source_url(
                meta.get("source_platform", ""),
                meta.get("source_id", ""),
                meta.get("civitai_model_id", ""),
            )
            return web.json_response(
                {
                    "success": True,
                    "data": {
                        "description": meta.get("description", ""),
                        "trigger_words": meta.get("trigger_words", []),
                        "tags": meta.get("tags", []),
                        "media": meta.get("media", []),
                        "base_model": meta.get("base_model", ""),
                        "source_platform": meta.get("source_platform", ""),
                        "source_url": source_url,
                        "size_bytes": size_bytes,
                    },
                }
            )
        except Exception as exc:
            return web.json_response({"success": False, "error": str(exc)}, status=500)

    @routes.put("/tiny-model-manager/api/models/{model_type}/{path:.*}/metadata")
    async def update_metadata(request):
        path = request.match_info["path"]
        model_type = request.match_info["model_type"]
        try:
            body = await request.json()
            description = body.get("description", "")
            trigger_words = body.get("trigger_words", [])
            tags = body.get("tags", [])
            new_base_model = body.get("base_model")  # None means "not provided, don't update"

            if new_base_model is not None:
                from .. import config as cfg
                from ..services.reorganizer import _move_to_subfolder

                settings = cfg.load_settings()
                if settings.get("organize_into_subfolders"):
                    existing = await model_repo.get_model_by_filename(path)
                    old_base_model = (existing or {}).get("base_model", "")
                    if old_base_model != new_base_model:
                        try:
                            new_path = await _move_to_subfolder(path, model_type, new_base_model)
                            if new_path != path:
                                await model_repo.update_model_filename(path, new_path)
                                path = new_path
                        except Exception:
                            pass

            await model_repo.update_model_meta(
                path, description, trigger_words, tags, base_model=new_base_model
            )
            return web.json_response({"success": True})
        except Exception as exc:
            return web.json_response({"success": False, "error": str(exc)}, status=500)

    @routes.post("/tiny-model-manager/api/models/{model_type}/{path:.*}/refetch")
    async def refetch_metadata(request):
        path = request.match_info["path"]
        try:
            info = await model_repo.get_model_source_info(path)
            if not info or not info.get("source_platform") or not info.get("source_id"):
                return web.json_response(
                    {"success": False, "error": "No source info stored for this model"}, status=400
                )
            from ..services import metadata_fetcher

            existing = await model_repo.get_model_by_filename(path)
            has_media = bool(existing and existing.get("media"))
            await metadata_fetcher.fetch_and_store(
                path,
                info["model_type"],
                info["source_platform"],
                info["source_id"],
                skip_media=has_media,
            )
            meta = await model_repo.get_model_by_filename(path) or {}
            source_url = _derive_source_url(
                meta.get("source_platform", ""),
                meta.get("source_id", ""),
                meta.get("civitai_model_id", ""),
            )
            return web.json_response(
                {
                    "success": True,
                    "data": {
                        "description": meta.get("description", ""),
                        "trigger_words": meta.get("trigger_words", []),
                        "tags": meta.get("tags", []),
                        "media": meta.get("media", []),
                        "base_model": meta.get("base_model", ""),
                        "source_platform": meta.get("source_platform", ""),
                        "source_url": source_url,
                    },
                }
            )
        except Exception as exc:
            return web.json_response({"success": False, "error": str(exc)}, status=500)

    _MODEL_EXTENSIONS = {".safetensors", ".ckpt", ".pt", ".bin", ".gguf"}

    @routes.get("/tiny-model-manager/api/models/{model_type}/{path:.*}/repo-files")
    async def get_repo_files(request):
        path = request.match_info["path"]
        model_type = request.match_info["model_type"]
        try:
            files = await model_repo.get_repo_files(model_type, path)
            model_dir = os.path.dirname(path)
            result = []
            for f in files:
                ext = os.path.splitext(f["filename"].lower())[1]
                if ext not in _MODEL_EXTENSIONS:
                    continue
                f["is_downloaded"] = _file_exists_on_disk(model_type, model_dir, f["filename"])
                f["added_at"] = _get_file_mtime(model_type, model_dir, f["filename"])
                result.append(f)
            return web.json_response({"success": True, "data": result})
        except Exception as exc:
            return web.json_response({"success": False, "error": str(exc)}, status=500)

    @routes.post("/tiny-model-manager/api/models/{model_type}/{path:.*}/link-source")
    async def link_source(request):
        model_type = request.match_info["model_type"]
        path = request.match_info["path"]
        try:
            body = await request.json()
            source_url = (body.get("source_url") or "").strip()
            platform, source_id, civitai_model_id = _parse_source_url(source_url)
            if not platform:
                return web.json_response(
                    {
                        "success": False,
                        "error": "Unrecognised URL. Paste a CivitAI model page or HuggingFace repo URL.",
                    },
                    status=400,
                )
            await model_repo.ensure_model_with_source(
                path, model_type, platform, source_id, civitai_model_id
            )
            page_id = source_id if platform == "huggingface" else civitai_model_id
            entry = await model_repo.get_catalog_entry(platform, page_id)
            if entry:
                await model_repo.set_model_catalog_entry(path, entry["id"])
            return web.json_response({"success": True})
        except Exception as exc:
            return web.json_response({"success": False, "error": str(exc)}, status=500)

    @routes.get("/tiny-model-manager/api/media/{path:.*}")
    async def serve_media(request):
        path = request.match_info["path"]
        from .. import config as cfg

        full_path = os.path.join(cfg.media_dir(), path)
        full_path = os.path.normpath(full_path)
        # Guard against path traversal
        if not full_path.startswith(os.path.normpath(cfg.media_dir())):
            return web.Response(status=403)
        if not os.path.isfile(full_path):
            return web.Response(status=404)
        return web.FileResponse(full_path)
