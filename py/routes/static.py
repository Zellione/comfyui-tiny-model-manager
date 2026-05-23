import os
from aiohttp import web


def add_static_routes(routes, ext_dir: str):
    web_dir = os.path.join(ext_dir, "web")

    @routes.get("/tiny-model-manager")
    async def index(request):
        return web.FileResponse(os.path.join(web_dir, "index.html"))

    @routes.get("/tiny-model-manager/{tail:.*}")
    async def static_files(request):
        tail = request.match_info.get("tail", "")
        file_path = os.path.join(web_dir, tail)
        if os.path.isfile(file_path):
            return web.FileResponse(file_path)
        # SPA fallback: serve index.html for any unmatched path
        return web.FileResponse(os.path.join(web_dir, "index.html"))
