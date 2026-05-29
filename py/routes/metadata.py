import os

from aiohttp import web

from ..db import model_repo


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
        try:
            meta = await model_repo.get_model_by_filename(path)
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
                    },
                }
            )
        except Exception as exc:
            return web.json_response({"success": False, "error": str(exc)}, status=500)

    @routes.put("/tiny-model-manager/api/models/{model_type}/{path:.*}/metadata")
    async def update_metadata(request):
        path = request.match_info["path"]
        try:
            body = await request.json()
            description = body.get("description", "")
            trigger_words = body.get("trigger_words", [])
            tags = body.get("tags", [])
            base_model = body.get("base_model")  # None means "not provided, don't update"
            await model_repo.update_model_meta(
                path, description, trigger_words, tags, base_model=base_model
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

            await metadata_fetcher.fetch_and_store(
                path,
                info["model_type"],
                info["source_platform"],
                info["source_id"],
                skip_media=True,
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
