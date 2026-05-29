from aiohttp import web

from .. import config as cfg


def add_settings_routes(routes):

    @routes.get("/tiny-model-manager/api/settings")
    async def get_settings(request):
        try:
            data = cfg.load_settings()
            # Never send raw keys back — mask them
            safe = {
                "civitai_api_key": "***" if data.get("civitai_api_key") else "",
                "hf_token": "***" if data.get("hf_token") else "",
                "media_dir": data.get("media_dir", ""),
            }
            return web.json_response({"success": True, "data": safe})
        except Exception as exc:
            return web.json_response({"success": False, "error": str(exc)}, status=500)

    @routes.put("/tiny-model-manager/api/settings")
    async def update_settings(request):
        try:
            body = await request.json()
            existing = cfg.load_settings()
            # Only update keys that aren't the mask placeholder
            if body.get("civitai_api_key", "") not in ("", "***"):
                existing["civitai_api_key"] = body["civitai_api_key"]
            if body.get("hf_token", "") not in ("", "***"):
                existing["hf_token"] = body["hf_token"]
            if "media_dir" in body:
                existing["media_dir"] = body["media_dir"]
            cfg.save_settings(existing)
            return web.json_response({"success": True})
        except Exception as exc:
            return web.json_response({"success": False, "error": str(exc)}, status=500)
