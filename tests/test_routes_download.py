"""Integration tests for py/routes/download.py (search, resolve, enqueue)."""

import pytest
from aiohttp import web


@pytest.fixture()
async def client(aiohttp_client, ext_dir):
    # Reset downloader state between tests
    import py.services.downloader as dl

    dl._tasks.clear()
    dl._worker_started = False

    from py.routes.download import add_download_routes

    app = web.Application()
    routes = web.RouteTableDef()
    add_download_routes(routes)
    app.router.add_routes(routes)
    return await aiohttp_client(app)


class TestDownloadEnqueue:
    async def test_enqueue_returns_task_id(self, client):
        resp = await client.post(
            "/tiny-model-manager/api/download",
            json={
                "url": "https://example.com/model.safetensors",
                "model_type": "checkpoints",
                "filename": "model.safetensors",
                "platform": "civitai",
                "source_id": "123",
            },
        )
        assert resp.status == 200
        data = await resp.json()
        assert data["success"] is True
        assert "task_id" in data["data"]

    async def test_enqueue_missing_url_returns_400(self, client):
        resp = await client.post(
            "/tiny-model-manager/api/download",
            json={"model_type": "loras", "filename": "m.safetensors", "platform": ""},
        )
        assert resp.status == 400

    async def test_enqueue_missing_filename_returns_400(self, client):
        resp = await client.post(
            "/tiny-model-manager/api/download",
            json={
                "url": "https://example.com/f.safetensors",
                "model_type": "loras",
                "platform": "",
            },
        )
        assert resp.status == 400


class TestDownloadStatus:
    async def test_status_returns_success(self, client):
        resp = await client.get("/tiny-model-manager/api/download/status")
        assert resp.status == 200
        data = await resp.json()
        assert data["success"] is True
        assert isinstance(data["data"], list)

    async def test_status_contains_enqueued_task(self, client):
        await client.post(
            "/tiny-model-manager/api/download",
            json={
                "url": "https://example.com/x.safetensors",
                "model_type": "loras",
                "filename": "x.safetensors",
                "platform": "huggingface",
                "source_id": "user/repo",
            },
        )
        resp = await client.get("/tiny-model-manager/api/download/status")
        tasks = (await resp.json())["data"]
        assert any(t["filename"] == "x.safetensors" for t in tasks)


class TestSearchCivitai:
    async def test_search_proxies_to_provider(self, client, monkeypatch):
        from py.services.providers import civitai as civitai_provider

        async def mock_search(q, model_type="", **kwargs):
            return {"items": [{"id": 1, "name": "Test Model"}], "metadata": {}}

        monkeypatch.setattr(civitai_provider, "search", mock_search)
        resp = await client.get("/tiny-model-manager/api/search/civitai", params={"q": "test"})
        assert resp.status == 200
        data = await resp.json()
        assert data["success"] is True

    async def test_search_error_returns_500(self, client, monkeypatch):
        from py.services.providers import civitai as civitai_provider

        async def mock_search(*a, **kw):
            raise RuntimeError("boom")

        monkeypatch.setattr(civitai_provider, "search", mock_search)
        resp = await client.get("/tiny-model-manager/api/search/civitai", params={"q": "x"})
        assert resp.status == 500


class TestSearchHuggingFace:
    async def test_search_proxies_to_provider(self, client, monkeypatch):
        from py.services.providers import huggingface as hf_provider

        async def mock_search(q, model_type="", **kwargs):
            return {"items": [], "hasMore": False, "nextPage": 1}

        monkeypatch.setattr(hf_provider, "search", mock_search)
        resp = await client.get("/tiny-model-manager/api/search/huggingface", params={"q": "lora"})
        assert resp.status == 200

    async def test_missing_repo_returns_400(self, client):
        resp = await client.get("/tiny-model-manager/api/search/huggingface/files")
        assert resp.status == 400


class TestDownloaderEnqueueHuggingFaceFilename:
    """Test that HF filenames with subfolder paths are stripped to basename."""

    def test_hf_filename_stripped_to_basename(self, ext_dir):
        import py.services.downloader as dl

        dl._tasks.clear()
        task = dl.enqueue(
            url="https://huggingface.co/user/repo/resolve/main/split/model.safetensors",
            model_type="checkpoints",
            filename="split/model.safetensors",
            platform="huggingface",
            source_id="user/repo",
        )
        assert task.filename == "model.safetensors"

    def test_non_hf_filename_not_stripped(self, ext_dir):
        import py.services.downloader as dl

        dl._tasks.clear()
        task = dl.enqueue(
            url="https://civitai.com/download/1234",
            model_type="loras",
            filename="subdir/my_lora.safetensors",
            platform="civitai",
            source_id="1234",
        )
        assert task.filename == "subdir/my_lora.safetensors"
