"""Integration tests for py/routes/static.py (SPA bundle serving + path containment)."""

import os

import pytest
from aiohttp import web

from py.routes.static import _serve_web_file, add_static_routes


@pytest.fixture
async def client(aiohttp_client, tmp_path):
    web_dir = tmp_path / "web"
    web_dir.mkdir()
    (web_dir / "index.html").write_text("<html>spa index</html>")
    (web_dir / "main.js").write_text("console.log('bundle');")
    (tmp_path / "secret.txt").write_text("outside the web dir")

    app = web.Application()
    routes = web.RouteTableDef()
    add_static_routes(routes, str(tmp_path))
    app.router.add_routes(routes)
    return await aiohttp_client(app)


class TestStaticRoutes:
    async def test_index_serves_spa_index(self, client):
        resp = await client.get("/tiny-model-manager")
        assert resp.status == 200
        assert "spa index" in await resp.text()

    async def test_serves_existing_bundle_file(self, client):
        resp = await client.get("/tiny-model-manager/main.js")
        assert resp.status == 200
        assert "bundle" in await resp.text()

    async def test_unmatched_path_falls_back_to_index(self, client):
        resp = await client.get("/tiny-model-manager/models/some/deep/route")
        assert resp.status == 200
        assert "spa index" in await resp.text()


class TestServeWebFile:
    def test_traversal_outside_web_dir_is_forbidden(self, tmp_path):
        web_dir = tmp_path / "web"
        web_dir.mkdir()
        (web_dir / "index.html").write_text("index")
        (tmp_path / "secret.txt").write_text("secret")

        resp = _serve_web_file(str(web_dir), "../secret.txt")
        assert resp.status == 403

    def test_in_bounds_file_is_served(self, tmp_path):
        web_dir = tmp_path / "web"
        web_dir.mkdir()
        (web_dir / "app.css").write_text("body {}")

        resp = _serve_web_file(str(web_dir), "app.css")
        assert isinstance(resp, web.FileResponse)
        assert str(resp._path) == os.path.join(str(web_dir), "app.css")

    def test_missing_file_falls_back_to_index(self, tmp_path):
        web_dir = tmp_path / "web"
        web_dir.mkdir()
        (web_dir / "index.html").write_text("index")

        resp = _serve_web_file(str(web_dir), "nope.js")
        assert isinstance(resp, web.FileResponse)
        assert str(resp._path).endswith("index.html")
