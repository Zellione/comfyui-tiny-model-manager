import os

from aiohttp import web

from ..services import model_paths


def _serve_web_file(web_dir: str, tail: str) -> web.StreamResponse:
    """Serve ``tail`` from ``web_dir``, falling back to the SPA index for unmatched paths.

    ``tail`` comes straight from the request URL; it is confined to ``web_dir`` here so a
    crafted ``../`` (or sibling-prefix) path cannot read files outside the compiled bundle.
    """
    file_path = model_paths.contained_path(web_dir, tail)
    if file_path is None:
        return web.Response(status=403)
    if os.path.isfile(file_path):
        return web.FileResponse(file_path)
    # SPA fallback: serve index.html for any unmatched in-bounds path.
    return web.FileResponse(os.path.join(web_dir, "index.html"))


def add_static_routes(routes, ext_dir: str):
    web_dir = os.path.join(ext_dir, "web")

    @routes.get("/tiny-model-manager")
    async def index(request):
        return web.FileResponse(os.path.join(web_dir, "index.html"))

    @routes.get("/tiny-model-manager/{tail:.*}")
    async def static_files(request):
        return _serve_web_file(web_dir, request.match_info.get("tail", ""))
