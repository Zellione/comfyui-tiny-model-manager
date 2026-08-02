"""Integration tests for the workflow store routes (F-129)."""

import json
import os
import zipfile

import httpx
import pytest
from aiohttp import web

from py.services import workflow_store as ws

_API = "/tiny-model-manager/api/workflows"

GRAPH = {"last_node_id": 1, "nodes": [{"id": 1, "type": "KSampler"}], "links": []}

_PAGE = {
    "id": 123,
    "name": "Cool Workflow Pack",
    "description": "does things",
    "tags": ["comfyui"],
    "modelVersions": [
        {
            "id": 456,
            "name": "v1.0",
            "baseModel": "Flux.1 D",
            "files": [
                {
                    "name": "pack.zip",
                    "type": "Archive",
                    "primary": True,
                    "downloadUrl": "https://civitai.com/api/download/models/456",
                }
            ],
            "images": [{"url": "https://image.civitai.com/a.jpg", "type": "image"}],
        }
    ],
}


@pytest.fixture
async def client(aiohttp_client, ext_dir):
    from py.routes.workflow import _pending
    from py.routes.workflows import add_workflows_routes

    _pending.clear()
    app = web.Application()
    routes = web.RouteTableDef()
    add_workflows_routes(routes)
    app.router.add_routes(routes)
    return await aiohttp_client(app)


@pytest.fixture
def stub_civitai(monkeypatch):
    """Stub the provider page fetch and the archive stream (never touches the network)."""

    async def fake_page(model_id):
        return _PAGE

    async def fake_fetch(url, dest, headers):
        with zipfile.ZipFile(dest, "w") as archive:
            archive.writestr("wf.json", json.dumps(GRAPH))

    async def no_media(media_hash, urls):
        return None

    monkeypatch.setattr(ws.civitai, "get_model_page", fake_page)
    monkeypatch.setattr(ws, "_fetch_archive", fake_fetch)
    monkeypatch.setattr(ws, "_download_media", no_media)


async def _download(client) -> dict:
    resp = await client.post(f"{_API}/download", json={"model_id": "123", "version_id": "456"})
    assert resp.status == 200
    return (await resp.json())["data"]


class TestSearch:
    async def test_forces_the_workflows_type(self, client, monkeypatch):
        captured = {}

        async def fake_search(query, **kwargs):
            captured.update(kwargs)
            captured["query"] = query
            return {"items": [], "metadata": {}}

        monkeypatch.setattr(ws.civitai, "search", fake_search)
        from py.routes import workflows as route_mod

        monkeypatch.setattr(route_mod.civitai, "search", fake_search)

        resp = await client.get(f"{_API}/search?q=flux&sort=Most%20Downloaded&tags=comfyui")
        assert resp.status == 200
        assert captured["types"] == "Workflows"
        assert captured["query"] == "flux"
        assert captured["tags"] == ["comfyui"]

    async def test_reports_installed_versions(self, client, stub_civitai, monkeypatch):
        await _download(client)

        async def fake_search(query, **kwargs):
            return {"items": [], "metadata": {}}

        from py.routes import workflows as route_mod

        monkeypatch.setattr(route_mod.civitai, "search", fake_search)
        resp = await client.get(f"{_API}/search?q=x")
        data = (await resp.json())["data"]
        assert data["installed_version_ids"] == ["456"]

    async def test_provider_error_returns_503(self, client, monkeypatch):
        async def boom(query, **kwargs):
            raise httpx.ConnectError("down")

        from py.routes import workflows as route_mod

        monkeypatch.setattr(route_mod.civitai, "search", boom)
        resp = await client.get(f"{_API}/search?q=x")
        assert resp.status == 503
        assert (await resp.json())["error"] == "provider_unavailable"


class TestDownload:
    async def test_stores_the_graph(self, client, stub_civitai):
        data = await _download(client)
        assert len(data["workflows"]) == 1
        assert data["workflows"][0]["name"] == "wf"
        assert data["workflows"][0]["node_count"] == 1

    async def test_missing_model_id_returns_400(self, client):
        resp = await client.post(f"{_API}/download", json={})
        assert resp.status == 400

    async def test_non_numeric_model_id_returns_400(self, client):
        resp = await client.post(f"{_API}/download", json={"model_id": "../etc"})
        assert resp.status == 400

    async def test_payload_without_a_graph_returns_422(self, client, monkeypatch):
        async def fake_page(model_id):
            return _PAGE

        async def fake_fetch(url, dest, headers):
            with open(dest, "wb") as f:
                f.write(b"not a workflow at all")

        from py.routes import workflows as route_mod

        monkeypatch.setattr(route_mod.workflow_store.civitai, "get_model_page", fake_page)
        monkeypatch.setattr(route_mod.workflow_store, "_fetch_archive", fake_fetch)
        resp = await client.post(f"{_API}/download", json={"model_id": "123"})
        assert resp.status == 422
        assert (await resp.json())["error"] == "no_workflow_json"

    async def test_disallowed_host_returns_400(self, client, monkeypatch):
        page = json.loads(json.dumps(_PAGE))
        page["modelVersions"][0]["files"][0]["downloadUrl"] = "http://169.254.169.254/x"

        async def fake_page(model_id):
            return page

        from py.routes import workflows as route_mod

        monkeypatch.setattr(route_mod.workflow_store.civitai, "get_model_page", fake_page)
        resp = await client.post(f"{_API}/download", json={"model_id": "123"})
        assert resp.status == 400

    async def test_redirect_off_the_allowlist_returns_400(self, client, monkeypatch):
        """CivitAI bouncing the download to another host is a rejection, not a 500."""
        from py.services.url_guard import RedirectNotAllowed

        async def fake_page(model_id):
            return _PAGE

        async def blocked(url, dest, headers):
            raise RedirectNotAllowed("Redirect target host is not allowed: '169.254.169.254'")

        from py.routes import workflows as route_mod

        monkeypatch.setattr(route_mod.workflow_store.civitai, "get_model_page", fake_page)
        monkeypatch.setattr(route_mod.workflow_store, "_fetch_archive", blocked)
        resp = await client.post(f"{_API}/download", json={"model_id": "123"})
        assert resp.status == 400
        assert "not allowed" in (await resp.json())["error"]

    async def test_oversize_archive_returns_413(self, client, monkeypatch):
        async def fake_page(model_id):
            return _PAGE

        async def too_big(url, dest, headers):
            raise ws.WorkflowTooLargeError("archive_too_large")

        from py.routes import workflows as route_mod

        monkeypatch.setattr(route_mod.workflow_store.civitai, "get_model_page", fake_page)
        monkeypatch.setattr(route_mod.workflow_store, "_fetch_archive", too_big)
        resp = await client.post(f"{_API}/download", json={"model_id": "123"})
        assert resp.status == 413

    async def test_provider_error_returns_503(self, client, monkeypatch):
        async def boom(model_id):
            raise httpx.ConnectError("down")

        from py.routes import workflows as route_mod

        monkeypatch.setattr(route_mod.workflow_store.civitai, "get_model_page", boom)
        resp = await client.post(f"{_API}/download", json={"model_id": "123"})
        assert resp.status == 503


class TestList:
    async def test_empty_initially(self, client):
        resp = await client.get(_API)
        assert resp.status == 200
        assert (await resp.json())["data"] == []

    async def test_lists_entry_with_items_and_media(self, client, stub_civitai):
        await _download(client)
        resp = await client.get(_API)
        entries = (await resp.json())["data"]
        assert len(entries) == 1
        assert entries[0]["display_name"] == "Cool Workflow Pack"
        assert entries[0]["tags"] == ["comfyui"]
        assert len(entries[0]["items"]) == 1
        assert entries[0]["media"] == []


class TestDelete:
    async def test_removes_the_entry(self, client, stub_civitai):
        data = await _download(client)
        resp = await client.delete(f"{_API}/{data['entry_id']}")
        assert resp.status == 204
        assert (await (await client.get(_API)).json())["data"] == []

    async def test_unknown_entry_returns_404(self, client):
        resp = await client.delete(f"{_API}/999")
        assert resp.status == 404


class TestFile:
    async def test_serves_the_raw_graph(self, client, stub_civitai):
        data = await _download(client)
        resp = await client.get(f"{_API}/{data['workflows'][0]['id']}/file")
        assert resp.status == 200
        assert await resp.json() == GRAPH
        assert "attachment" in resp.headers["Content-Disposition"]

    async def test_unknown_workflow_returns_404(self, client):
        resp = await client.get(f"{_API}/999/file")
        assert resp.status == 404

    async def test_missing_file_on_disk_returns_404(self, client, stub_civitai):
        from py.db import workflow_repo

        data = await _download(client)
        workflow = await workflow_repo.get_workflow(data["workflows"][0]["id"])
        os.remove(ws.graph_path(workflow))
        resp = await client.get(f"{_API}/{workflow['id']}/file")
        assert resp.status == 404


class TestExport:
    async def test_writes_into_the_comfyui_user_dir(self, client, stub_civitai, tmp_path):
        import folder_paths

        original = folder_paths.user_directory
        folder_paths.user_directory = str(tmp_path / "comfy_user")
        try:
            data = await _download(client)
            resp = await client.post(f"{_API}/{data['workflows'][0]['id']}/export")
            assert resp.status == 200
            path = (await resp.json())["data"]["path"]
            assert path.startswith(str(tmp_path / "comfy_user"))
            with open(path, encoding="utf-8") as f:
                assert json.load(f) == GRAPH
        finally:
            folder_paths.user_directory = original

    async def test_unknown_workflow_returns_404(self, client):
        resp = await client.post(f"{_API}/999/export")
        assert resp.status == 404


class TestOpen:
    async def test_queues_a_graph_item_for_the_extension(self, client, stub_civitai):
        from py.routes.workflow import _pending

        data = await _download(client)
        workflow_id = data["workflows"][0]["id"]
        resp = await client.post(f"{_API}/{workflow_id}/open")
        assert resp.status == 200
        assert len(_pending) == 1
        assert _pending[0]["kind"] == "graph"
        assert _pending[0]["workflow_id"] == workflow_id

    async def test_unknown_workflow_returns_404(self, client):
        from py.routes.workflow import _pending

        resp = await client.post(f"{_API}/999/open")
        assert resp.status == 404
        assert _pending == []
