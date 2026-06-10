"""Integration tests for py/routes/settings.py (GET/PUT settings)."""

import pytest
from aiohttp import web


@pytest.fixture()
async def client(aiohttp_client, ext_dir):
    from py.routes.settings import add_settings_routes

    app = web.Application()
    routes = web.RouteTableDef()
    add_settings_routes(routes)
    app.router.add_routes(routes)
    return await aiohttp_client(app)


class TestGetSettings:
    async def test_get_returns_success(self, client):
        resp = await client.get("/tiny-model-manager/api/settings")
        assert resp.status == 200
        data = await resp.json()
        assert data["success"] is True

    async def test_get_returns_empty_strings_when_no_settings(self, client):
        data = (await (await client.get("/tiny-model-manager/api/settings")).json())["data"]
        assert data["civitai_api_key"] == ""
        assert data["hf_token"] == ""

    async def test_get_masks_civitai_key(self, client, ext_dir):
        from py import config as cfg

        cfg.save_settings({"civitai_api_key": "real-secret-key"})
        data = (await (await client.get("/tiny-model-manager/api/settings")).json())["data"]
        assert data["civitai_api_key"] == "***"
        assert "real-secret-key" not in str(data)

    async def test_get_masks_hf_token(self, client, ext_dir):
        from py import config as cfg

        cfg.save_settings({"hf_token": "hf_XXXX"})
        data = (await (await client.get("/tiny-model-manager/api/settings")).json())["data"]
        assert data["hf_token"] == "***"

    async def test_get_returns_media_dir_default(self, client, ext_dir):
        import os

        from py import config as cfg

        data = (await (await client.get("/tiny-model-manager/api/settings")).json())["data"]
        expected = os.path.join(cfg.data_dir(), "media")
        assert data["media_dir_default"] == expected

    async def test_get_returns_organize_into_subfolders_default_false(self, client):
        data = (await (await client.get("/tiny-model-manager/api/settings")).json())["data"]
        assert data["organize_into_subfolders"] is False


class TestPutSettings:
    async def test_put_saves_civitai_key(self, client, ext_dir):
        from py import config as cfg

        await client.put(
            "/tiny-model-manager/api/settings",
            json={"civitai_api_key": "new-key"},
        )
        assert cfg.load_settings().get("civitai_api_key") == "new-key"

    async def test_put_saves_hf_token(self, client, ext_dir):
        from py import config as cfg

        await client.put("/tiny-model-manager/api/settings", json={"hf_token": "hf_NEW"})
        assert cfg.load_settings().get("hf_token") == "hf_NEW"

    async def test_put_ignores_mask_placeholder(self, client, ext_dir):
        from py import config as cfg

        cfg.save_settings({"civitai_api_key": "original"})
        await client.put(
            "/tiny-model-manager/api/settings",
            json={"civitai_api_key": "***"},
        )
        assert cfg.load_settings().get("civitai_api_key") == "original"

    async def test_put_ignores_empty_key(self, client, ext_dir):
        from py import config as cfg

        cfg.save_settings({"hf_token": "keep-me"})
        await client.put("/tiny-model-manager/api/settings", json={"hf_token": ""})
        assert cfg.load_settings().get("hf_token") == "keep-me"

    async def test_put_updates_media_dir(self, client, ext_dir):
        from py import config as cfg

        await client.put(
            "/tiny-model-manager/api/settings",
            json={"media_dir": "/custom/path"},
        )
        assert cfg.load_settings().get("media_dir") == "/custom/path"

    async def test_put_returns_success(self, client):
        resp = await client.put("/tiny-model-manager/api/settings", json={})
        assert resp.status == 200
        assert (await resp.json())["success"] is True

    async def test_toggling_organize_off_enqueues_deorganize_jobs(self, client, ext_dir):
        from unittest.mock import patch

        from py import config as cfg
        from py.db import model_repo

        cfg.save_settings({"organize_into_subfolders": True})
        await model_repo.upsert_model("SDXL 1.0/a.safetensors", "loras", "", "", "")
        await model_repo.upsert_model("b.safetensors", "loras", "", "", "")

        with patch("py.services.reorganizer.process_pending_jobs", return_value=None):
            await client.put(
                "/tiny-model-manager/api/settings",
                json={"organize_into_subfolders": False},
            )

        jobs = await model_repo.get_pending_jobs("deorganize")
        filenames = [j["filename"] for j in jobs]
        assert "SDXL 1.0/a.safetensors" in filenames
        assert "b.safetensors" not in filenames

    async def test_toggling_organize_on_enqueues_organize_jobs(self, client, ext_dir):
        from unittest.mock import patch

        from py import config as cfg
        from py.db import model_repo

        cfg.save_settings({"organize_into_subfolders": False})
        await model_repo.upsert_model("flat.safetensors", "loras", "", "", "")
        await model_repo.upsert_model("SDXL 1.0/sub.safetensors", "loras", "", "", "")

        with patch("py.services.reorganizer.process_pending_jobs", return_value=None):
            await client.put(
                "/tiny-model-manager/api/settings",
                json={"organize_into_subfolders": True},
            )

        jobs = await model_repo.get_pending_jobs("organize")
        filenames = [j["filename"] for j in jobs]
        assert "flat.safetensors" in filenames
        assert "SDXL 1.0/sub.safetensors" not in filenames

    async def test_toggling_organize_on_blocked_when_deorganize_queue_pending(
        self, client, ext_dir
    ):
        from py import config as cfg
        from py.db import model_repo

        cfg.save_settings({"organize_into_subfolders": False})
        await model_repo.enqueue_reorganize("SDXL 1.0/x.safetensors", "loras", "deorganize")

        resp = await client.put(
            "/tiny-model-manager/api/settings",
            json={"organize_into_subfolders": True},
        )
        assert resp.status == 409
        body = await resp.json()
        assert body["success"] is False

    async def test_toggling_organize_on_blocked_when_organize_queue_pending(self, client, ext_dir):
        from py import config as cfg
        from py.db import model_repo

        cfg.save_settings({"organize_into_subfolders": False})
        await model_repo.enqueue_reorganize("flat.safetensors", "loras", "organize")

        resp = await client.put(
            "/tiny-model-manager/api/settings",
            json={"organize_into_subfolders": True},
        )
        assert resp.status == 409
        body = await resp.json()
        assert body["success"] is False

    async def test_toggling_organize_on_allowed_when_queue_empty(self, client, ext_dir):
        from unittest.mock import patch

        from py import config as cfg

        cfg.save_settings({"organize_into_subfolders": False})

        with patch("py.services.reorganizer.process_pending_jobs", return_value=None):
            resp = await client.put(
                "/tiny-model-manager/api/settings",
                json={"organize_into_subfolders": True},
            )
        assert resp.status == 200
        assert (await resp.json())["success"] is True


class TestKeywords:
    async def test_list_returns_list(self, client, ext_dir):
        resp = await client.get("/tiny-model-manager/api/filename-keywords")
        assert resp.status == 200
        data = await resp.json()
        assert data["success"] is True
        assert isinstance(data["data"], list)

    async def test_create_returns_id(self, client, ext_dir):
        resp = await client.post(
            "/tiny-model-manager/api/filename-keywords",
            json={
                "keyword": "xl-turbo",
                "base_model": "SDXL Turbo",
                "model_type": "checkpoints",
            },
        )
        assert resp.status == 200
        data = await resp.json()
        assert data["success"] is True
        assert isinstance(data["data"]["id"], int)

    async def test_create_requires_keyword(self, client, ext_dir):
        resp = await client.post(
            "/tiny-model-manager/api/filename-keywords",
            json={"base_model": "SDXL 1.0"},
        )
        assert resp.status == 400

    async def test_created_keyword_appears_in_list(self, client, ext_dir):
        await client.post(
            "/tiny-model-manager/api/filename-keywords",
            json={"keyword": "animatediff"},
        )
        resp = await client.get("/tiny-model-manager/api/filename-keywords")
        keywords = [kw["keyword"] for kw in (await resp.json())["data"]]
        assert "animatediff" in keywords

    async def test_update_keyword(self, client, ext_dir):
        create = await client.post(
            "/tiny-model-manager/api/filename-keywords",
            json={"keyword": "test-update-kw", "base_model": "SD 1.5"},
        )
        kw_id = (await create.json())["data"]["id"]
        resp = await client.put(
            f"/tiny-model-manager/api/filename-keywords/{kw_id}",
            json={"keyword": "test-update-kw", "base_model": "SD 1.5", "model_type": "loras"},
        )
        assert resp.status == 200
        assert (await resp.json())["success"] is True

    async def test_update_nonexistent_returns_404(self, client, ext_dir):
        resp = await client.put(
            "/tiny-model-manager/api/filename-keywords/99999",
            json={"keyword": "x"},
        )
        assert resp.status == 404

    async def test_update_requires_keyword(self, client, ext_dir):
        create = await client.post(
            "/tiny-model-manager/api/filename-keywords",
            json={"keyword": "sd15v2"},
        )
        kw_id = (await create.json())["data"]["id"]
        resp = await client.put(
            f"/tiny-model-manager/api/filename-keywords/{kw_id}",
            json={"base_model": "SD 1.5"},
        )
        assert resp.status == 400

    async def test_delete_keyword(self, client, ext_dir):
        create = await client.post(
            "/tiny-model-manager/api/filename-keywords",
            json={"keyword": "toremove"},
        )
        kw_id = (await create.json())["data"]["id"]
        resp = await client.delete(f"/tiny-model-manager/api/filename-keywords/{kw_id}")
        assert resp.status == 200
        assert (await resp.json())["success"] is True

    async def test_delete_nonexistent_returns_404(self, client, ext_dir):
        resp = await client.delete("/tiny-model-manager/api/filename-keywords/99999")
        assert resp.status == 404

    async def test_deleted_keyword_absent_from_list(self, client, ext_dir):
        create = await client.post(
            "/tiny-model-manager/api/filename-keywords",
            json={"keyword": "gone"},
        )
        kw_id = (await create.json())["data"]["id"]
        await client.delete(f"/tiny-model-manager/api/filename-keywords/{kw_id}")
        resp = await client.get("/tiny-model-manager/api/filename-keywords")
        keywords = [kw["keyword"] for kw in (await resp.json())["data"]]
        assert "gone" not in keywords
