import os
from aiohttp import web
from ..db import model_repo


def add_metadata_routes(routes):

    @routes.get("/tiny-model-manager/api/models/{model_type}/{path:.*}/metadata")
    async def get_metadata(request):
        path = request.match_info["path"]
        try:
            meta = await model_repo.get_model_by_filename(path)
            if not meta:
                return web.json_response(
                    {"success": True, "data": {"description": "", "trigger_words": [], "tags": [], "media": []}}
                )
            return web.json_response({"success": True, "data": {
                "description": meta.get("description", ""),
                "trigger_words": meta.get("trigger_words", []),
                "tags": meta.get("tags", []),
                "media": meta.get("media", []),
            }})
        except Exception as exc:
            return web.json_response({"success": False, "error": str(exc)}, status=500)

    @routes.put("/tiny-model-manager/api/models/{model_type}/{path:.*}/metadata")
    async def update_metadata(request):
        path = request.match_info["path"]
        try:
            body = await request.json()
            description = body.get("description", "")
            trigger_words = body.get("trigger_words", [])
            await model_repo.update_model_meta(path, description, trigger_words)
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
