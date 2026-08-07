import os

from aiohttp import web

from ..services import model_paths

_UNBUILT_MESSAGE = (
    '<!doctype html><html lang="en"><head><meta charset="utf-8">'
    "<title>Tiny Model Manager &mdash; dashboard not built</title></head><body>"
    "<h1>Dashboard not built</h1>"
    "<p>The compiled web bundle is missing. The loader nodes still work; only this "
    "dashboard is unavailable.</p>"
    "<p>To build it, install Node.js 22+ and run "
    "<code>cd frontend &amp;&amp; npm install &amp;&amp; npx ng build</code>, or reinstall "
    "the node from the ComfyUI Registry, which ships a prebuilt bundle.</p>"
    "</body></html>"
)


def _serve_index(web_dir: str) -> web.StreamResponse:
    """Serve the SPA entry point, or an explanatory 503 when the bundle was never built.

    Without this guard aiohttp raises ``FileNotFoundError`` on a missing ``index.html``,
    turning a plainly diagnosable setup problem into an opaque 500 traceback.
    """
    index_path = os.path.join(web_dir, "index.html")
    if not os.path.isfile(index_path):
        return web.Response(status=503, text=_UNBUILT_MESSAGE, content_type="text/html")
    return web.FileResponse(index_path)


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
    return _serve_index(web_dir)


def add_static_routes(routes, ext_dir: str):
    web_dir = os.path.join(ext_dir, "web")

    @routes.get("/tiny-model-manager")
    async def index(request):
        return _serve_index(web_dir)

    @routes.get("/tiny-model-manager/{tail:.*}")
    async def static_files(request):
        return _serve_web_file(web_dir, request.match_info.get("tail", ""))
