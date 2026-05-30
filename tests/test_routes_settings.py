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
