"""Unit tests for py/routes/static.py web-asset serving and traversal guard."""

import os

from py.routes.static import _serve_web_file


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
