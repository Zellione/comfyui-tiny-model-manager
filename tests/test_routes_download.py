"""Integration tests for py/routes/download.py (search, resolve, enqueue)."""

import pytest
from aiohttp import web


@pytest.fixture()
async def client(aiohttp_client, ext_dir):
    # Downloader state is reset per test by the autouse reset_downloader_state fixture.
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
                "url": "https://civitai.com/model.safetensors",
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

    async def test_enqueue_rejects_disallowed_url_host(self, client):
        resp = await client.post(
            "/tiny-model-manager/api/download",
            json={
                "url": "http://169.254.169.254/latest/meta-data/",
                "model_type": "checkpoints",
                "filename": "model.safetensors",
                "platform": "civitai",
            },
        )
        assert resp.status == 400
        # A rejected download must not leave a dangling history row.
        from py.db import model_repo

        entries, _ = await model_repo.get_download_history()
        assert entries == []

    async def test_enqueue_rejects_traversal_filename(self, client):
        resp = await client.post(
            "/tiny-model-manager/api/download",
            json={
                "url": "https://civitai.com/api/download/models/1",
                "model_type": "checkpoints",
                "filename": "../../../../tmp/evil.txt",
                "platform": "civitai",
            },
        )
        assert resp.status == 400
        from py.db import model_repo

        entries, _ = await model_repo.get_download_history()
        assert entries == []

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
                "url": "https://civitai.com/f.safetensors",
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
                "url": "https://civitai.com/x.safetensors",
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


class TestCancelDownload:
    async def test_cancel_returns_204(self, client):
        resp = await client.post(
            "/tiny-model-manager/api/download",
            json={
                "url": "https://civitai.com/model.safetensors",
                "model_type": "checkpoints",
                "filename": "model.safetensors",
                "platform": "civitai",
            },
        )
        task_id = (await resp.json())["data"]["task_id"]
        resp = await client.delete(f"/tiny-model-manager/api/downloads/{task_id}")
        assert resp.status == 204

    async def test_cancel_unknown_id_returns_404(self, client):
        resp = await client.delete("/tiny-model-manager/api/downloads/no-such-id")
        assert resp.status == 404

    async def test_cancel_removes_task_from_status(self, client):
        resp = await client.post(
            "/tiny-model-manager/api/download",
            json={
                "url": "https://civitai.com/model.safetensors",
                "model_type": "checkpoints",
                "filename": "model.safetensors",
                "platform": "civitai",
            },
        )
        task_id = (await resp.json())["data"]["task_id"]
        await client.delete(f"/tiny-model-manager/api/downloads/{task_id}")
        tasks = (await (await client.get("/tiny-model-manager/api/download/status")).json())["data"]
        assert not any(t["id"] == task_id for t in tasks)

    async def test_cancel_second_call_returns_404(self, client):
        resp = await client.post(
            "/tiny-model-manager/api/download",
            json={
                "url": "https://civitai.com/model.safetensors",
                "model_type": "checkpoints",
                "filename": "model.safetensors",
                "platform": "civitai",
            },
        )
        task_id = (await resp.json())["data"]["task_id"]
        await client.delete(f"/tiny-model-manager/api/downloads/{task_id}")
        resp = await client.delete(f"/tiny-model-manager/api/downloads/{task_id}")
        assert resp.status == 404


class TestDownloadHistory:
    async def test_history_empty_initially(self, client, ext_dir):
        resp = await client.get("/tiny-model-manager/api/download/history")
        assert resp.status == 200
        data = await resp.json()
        assert data["success"] is True
        assert data["data"]["entries"] == []
        assert data["data"]["total"] == 0

    async def test_history_populated_after_enqueue(self, client, ext_dir):
        await client.post(
            "/tiny-model-manager/api/download",
            json={
                "url": "https://civitai.com/model.safetensors",
                "model_type": "checkpoints",
                "filename": "model.safetensors",
                "platform": "civitai",
                "source_id": "999",
            },
        )
        resp = await client.get("/tiny-model-manager/api/download/history")
        data = await resp.json()
        assert data["data"]["total"] == 1
        entry = data["data"]["entries"][0]
        assert entry["model_name"] == "model.safetensors"
        assert entry["status"] == "downloading"
        assert entry["source"] == "civitai"

    async def test_history_filter_by_status(self, client, ext_dir):
        from py.db import model_repo

        await model_repo.insert_download_history(
            model_name="done_model.safetensors",
            source="civitai",
            model_id="",
            version_id="1",
            file_url="https://civitai.com/done.safetensors",
            dest_path="done.safetensors",
            model_type="checkpoints",
        )
        await model_repo.insert_download_history(
            model_name="error_model.safetensors",
            source="huggingface",
            model_id="user/repo",
            version_id="",
            file_url="https://civitai.com/err.safetensors",
            dest_path="err.safetensors",
            model_type="loras",
        )
        # Update one to 'done', leave other as 'downloading' (acts as 'error' stand-in)
        from py.db.database import get_db

        async with get_db() as db:
            await db.execute(
                "UPDATE download_history SET status='done' WHERE model_name='done_model.safetensors'"
            )
            await db.execute(
                "UPDATE download_history SET status='error' WHERE model_name='error_model.safetensors'"
            )
            await db.commit()

        resp = await client.get(
            "/tiny-model-manager/api/download/history", params={"status": "done"}
        )
        data = await resp.json()
        assert data["data"]["total"] == 1
        assert data["data"]["entries"][0]["status"] == "done"

    async def test_history_filter_by_query(self, client, ext_dir):
        from py.db import model_repo

        await model_repo.insert_download_history(
            model_name="realistic_vision.safetensors",
            source="civitai",
            model_id="",
            version_id="42",
            file_url="https://civitai.com/rv.safetensors",
            dest_path="rv.safetensors",
            model_type="checkpoints",
        )
        await model_repo.insert_download_history(
            model_name="anime_lora.safetensors",
            source="civitai",
            model_id="",
            version_id="7",
            file_url="https://civitai.com/al.safetensors",
            dest_path="al.safetensors",
            model_type="loras",
        )

        resp = await client.get(
            "/tiny-model-manager/api/download/history", params={"q": "realistic"}
        )
        data = await resp.json()
        assert data["data"]["total"] == 1
        assert "realistic" in data["data"]["entries"][0]["model_name"]

    async def test_history_pagination(self, client, ext_dir):
        from py.db import model_repo

        for i in range(5):
            await model_repo.insert_download_history(
                model_name=f"model_{i}.safetensors",
                source="civitai",
                model_id="",
                version_id=str(i),
                file_url=f"https://civitai.com/{i}.safetensors",
                dest_path=f"model_{i}.safetensors",
                model_type="checkpoints",
            )

        resp = await client.get(
            "/tiny-model-manager/api/download/history", params={"page": 1, "page_size": 3}
        )
        data = await resp.json()
        assert data["data"]["total"] == 5
        assert len(data["data"]["entries"]) == 3

        resp2 = await client.get(
            "/tiny-model-manager/api/download/history", params={"page": 2, "page_size": 3}
        )
        data2 = await resp2.json()
        assert len(data2["data"]["entries"]) == 2


class TestRedownload:
    async def test_redownload_unknown_id_returns_404(self, client, ext_dir):
        resp = await client.post("/tiny-model-manager/api/download/history/9999/redownload")
        assert resp.status == 404

    async def test_redownload_returns_task_id(self, client, ext_dir):
        from py.db import model_repo

        entry_id = await model_repo.insert_download_history(
            model_name="my_model.safetensors",
            source="civitai",
            model_id="",
            version_id="55",
            file_url="https://civitai.com/my_model.safetensors",
            dest_path="my_model.safetensors",
            model_type="checkpoints",
        )
        resp = await client.post(f"/tiny-model-manager/api/download/history/{entry_id}/redownload")
        assert resp.status == 200
        data = await resp.json()
        assert data["success"] is True
        assert "task_id" in data["data"]

    async def test_redownload_creates_new_history_row(self, client, ext_dir):
        from py.db import model_repo

        entry_id = await model_repo.insert_download_history(
            model_name="redo.safetensors",
            source="huggingface",
            model_id="user/repo",
            version_id="",
            file_url="https://civitai.com/redo.safetensors",
            dest_path="redo.safetensors",
            model_type="loras",
        )
        await client.post(f"/tiny-model-manager/api/download/history/{entry_id}/redownload")
        entries, total = await model_repo.get_download_history()
        assert total == 2
        names = [e["model_name"] for e in entries]
        assert names.count("redo.safetensors") == 2

    async def test_redownload_no_url_returns_400(self, client, ext_dir):
        from py.db.database import get_db

        async with get_db() as db:
            cursor = await db.execute(
                "INSERT INTO download_history"
                " (model_name, source, model_id, version_id, file_url, dest_path, model_type, status)"
                " VALUES ('nourl.safetensors', 'civitai', '', '1', '', 'nourl.safetensors', 'checkpoints', 'error')"
            )
            await db.commit()
            entry_id = cursor.lastrowid

        resp = await client.post(f"/tiny-model-manager/api/download/history/{entry_id}/redownload")
        assert resp.status == 400


class TestHfFilesRoute:
    async def test_returns_files_list(self, client, monkeypatch):
        from py.services.providers import huggingface as hf_provider

        async def mock_get_files(repo_id):
            return [{"filename": "model.safetensors", "size": 1000}]

        monkeypatch.setattr(hf_provider, "get_model_files", mock_get_files)
        resp = await client.get(
            "/tiny-model-manager/api/search/huggingface/files", params={"repo": "user/myrepo"}
        )
        assert resp.status == 200
        data = await resp.json()
        assert data["success"] is True
        assert len(data["data"]) == 1
        assert data["data"][0]["filename"] == "model.safetensors"

    async def test_missing_repo_returns_400(self, client):
        resp = await client.get("/tiny-model-manager/api/search/huggingface/files")
        assert resp.status == 400

    async def test_schedules_auto_migration(self, client, monkeypatch):
        """F-92: browsing a repo's files hands its LFS hashes to the auto-migrator."""
        from py.services import auto_migrator
        from py.services.providers import huggingface as hf_provider

        scheduled = []

        async def mock_get_files(repo_id):
            return [{"filename": "model.safetensors", "size": 1000, "sha256": "abc"}]

        monkeypatch.setattr(hf_provider, "get_model_files", mock_get_files)
        monkeypatch.setattr(auto_migrator, "schedule", scheduled.append)

        resp = await client.get(
            "/tiny-model-manager/api/search/huggingface/files", params={"repo": "user/myrepo"}
        )
        assert resp.status == 200
        assert len(scheduled) == 1
        assert [f.sha256 for f in scheduled[0]] == ["abc"]
        assert scheduled[0][0].source_id == "user/myrepo"


class TestCivitaiVersionsRoute:
    async def test_returns_versions_list(self, client, monkeypatch):
        from py.services.providers import civitai as civitai_provider

        async def mock_get_versions(model_id):
            return [{"id": 1, "name": "v1"}]

        monkeypatch.setattr(civitai_provider, "get_model_versions", mock_get_versions)
        resp = await client.get("/tiny-model-manager/api/civitai/versions/42")
        assert resp.status == 200
        data = await resp.json()
        assert data["success"] is True
        assert data["data"][0]["id"] == 1

    async def test_schedules_auto_migration(self, client, monkeypatch):
        """F-92: browsing versions hands their per-file hashes to the auto-migrator."""
        from py.services import auto_migrator
        from py.services.providers import civitai as civitai_provider

        scheduled = []

        async def mock_get_versions(model_id):
            return {
                "versions": [
                    {
                        "id": 9,
                        "modelId": 42,
                        "files": [
                            {
                                "type": "Model",
                                "name": "v.safetensors",
                                "hashes": {"SHA256": "abc"},
                            }
                        ],
                    }
                ]
            }

        monkeypatch.setattr(civitai_provider, "get_model_versions", mock_get_versions)
        monkeypatch.setattr(auto_migrator, "schedule", scheduled.append)

        resp = await client.get("/tiny-model-manager/api/civitai/versions/42")
        assert resp.status == 200
        assert len(scheduled) == 1
        assert [f.filename for f in scheduled[0]] == ["v.safetensors"]
        assert scheduled[0][0].source_id == "9"


class TestHfReadmeRoute:
    async def test_returns_readme_text(self, client, monkeypatch):
        from py.services.providers import huggingface as hf_provider

        async def mock_get_readme(repo_id):
            return "# My Model\nGreat model."

        monkeypatch.setattr(hf_provider, "get_readme", mock_get_readme)
        resp = await client.get(
            "/tiny-model-manager/api/huggingface/readme", params={"repo": "user/myrepo"}
        )
        assert resp.status == 200
        data = await resp.json()
        assert data["success"] is True
        assert "Great model" in data["data"]["description"]

    async def test_missing_repo_returns_400(self, client):
        resp = await client.get("/tiny-model-manager/api/huggingface/readme")
        assert resp.status == 400


class TestHfResolveRoute:
    async def test_returns_resolved_link(self, client, monkeypatch):
        from py.services.providers import huggingface as hf_provider

        async def mock_resolve(repo_id):
            return {"url": "https://huggingface.co/user/repo/resolve/main/model.safetensors"}

        monkeypatch.setattr(hf_provider, "resolve_direct_link", mock_resolve)
        resp = await client.get(
            "/tiny-model-manager/api/huggingface/resolve", params={"repo": "user/myrepo"}
        )
        assert resp.status == 200
        data = await resp.json()
        assert data["success"] is True
        assert "url" in data["data"]

    async def test_missing_repo_returns_400(self, client):
        resp = await client.get("/tiny-model-manager/api/huggingface/resolve")
        assert resp.status == 400


class TestCivitaiResolveVersionRoute:
    async def test_returns_resolved_version(self, client, monkeypatch):
        from py.services.providers import civitai as civitai_provider

        async def mock_resolve(version_id):
            return {"url": "https://civitai.com/download/99", "filename": "model.safetensors"}

        monkeypatch.setattr(civitai_provider, "resolve_direct_link", mock_resolve)
        resp = await client.get("/tiny-model-manager/api/civitai/resolve/99")
        assert resp.status == 200
        data = await resp.json()
        assert data["success"] is True
        assert data["data"]["filename"] == "model.safetensors"


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
