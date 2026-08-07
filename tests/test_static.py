"""Tests for py/routes/static.py web-asset serving, traversal guard, and route wiring."""

import os

import pytest
from aiohttp import web

from py.routes.static import _serve_index, _serve_web_file, add_static_routes


class TestServeWebFile:
    def test_serves_existing_file(self, tmp_path):
        web_dir = tmp_path / "web"
        web_dir.mkdir()
        (web_dir / "app.js").write_text("console.log(1)")

        resp = _serve_web_file(str(web_dir), "app.js")
        assert resp.status == 200

    def test_missing_file_falls_back_to_index(self, tmp_path):
        web_dir = tmp_path / "web"
        web_dir.mkdir()
        (web_dir / "index.html").write_text("<html></html>")

        resp = _serve_web_file(str(web_dir), "some/spa/route")
        # SPA fallback serves index.html (a FileResponse, status 200).
        assert resp.status == 200

    def test_sibling_directory_escape_blocked(self, tmp_path):
        web_dir = tmp_path / "web"
        web_dir.mkdir()
        sibling = tmp_path / "web_evil"
        sibling.mkdir()
        (sibling / "secret.txt").write_text("secret")

        rel = os.path.join("..", "web_evil", "secret.txt")
        resp = _serve_web_file(str(web_dir), rel)
        assert resp.status == 403

    def test_unbuilt_bundle_falls_back_to_hint(self, tmp_path):
        # Without index.html the SPA fallback would otherwise raise FileNotFoundError.
        web_dir = tmp_path / "web"
        web_dir.mkdir()

        resp = _serve_web_file(str(web_dir), "some/spa/route")
        assert resp.status == 503
        assert "npx ng build" in resp.text


class TestServeIndex:
    def test_serves_index_when_built(self, tmp_path):
        web_dir = tmp_path / "web"
        web_dir.mkdir()
        (web_dir / "index.html").write_text("<html></html>")

        assert _serve_index(str(web_dir)).status == 200

    def test_returns_503_when_web_dir_absent(self, tmp_path):
        resp = _serve_index(str(tmp_path / "never-built"))

        assert resp.status == 503
        assert resp.content_type == "text/html"


@pytest.fixture()
def make_client(aiohttp_client):
    """Build a client for the static routes rooted at an arbitrary extension directory."""

    async def _make(ext_dir):
        app = web.Application()
        routes = web.RouteTableDef()
        add_static_routes(routes, str(ext_dir))
        app.router.add_routes(routes)
        return await aiohttp_client(app)

    return _make


class TestStaticRoutes:
    async def test_index_served_when_built(self, make_client, tmp_path):
        web_dir = tmp_path / "web"
        web_dir.mkdir()
        (web_dir / "index.html").write_text("<html>dashboard</html>")

        resp = await (await make_client(tmp_path)).get("/tiny-model-manager")

        assert resp.status == 200
        assert "dashboard" in await resp.text()

    async def test_index_returns_503_when_unbuilt(self, make_client, tmp_path):
        resp = await (await make_client(tmp_path)).get("/tiny-model-manager")

        assert resp.status == 503
        assert "npx ng build" in await resp.text()

    async def test_asset_is_served(self, make_client, tmp_path):
        web_dir = tmp_path / "web"
        web_dir.mkdir()
        (web_dir / "main.js").write_text("console.log(1)")

        resp = await (await make_client(tmp_path)).get("/tiny-model-manager/main.js")

        assert resp.status == 200
        assert "console.log(1)" in await resp.text()

    async def test_unknown_path_falls_back_to_index(self, make_client, tmp_path):
        web_dir = tmp_path / "web"
        web_dir.mkdir()
        (web_dir / "index.html").write_text("<html>spa</html>")

        resp = await (await make_client(tmp_path)).get("/tiny-model-manager/models/42")

        assert resp.status == 200
        assert "spa" in await resp.text()
