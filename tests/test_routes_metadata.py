"""Integration tests for py/routes/metadata.py (metadata CRUD + media serving)."""

import os

import pytest
from aiohttp import web


@pytest.fixture()
async def client(aiohttp_client, ext_dir):
    from py.routes.metadata import add_metadata_routes

    app = web.Application()
    routes = web.RouteTableDef()
    add_metadata_routes(routes)
    app.router.add_routes(routes)
    return await aiohttp_client(app)


class TestGetMetadata:
    async def test_returns_empty_when_no_record(self, client):
        resp = await client.get("/tiny-model-manager/api/models/loras/unknown.safetensors/metadata")
        assert resp.status == 200
        data = (await resp.json())["data"]
        assert data["description"] == ""
        assert data["trigger_words"] == []
        assert data["tags"] == []

    async def test_returns_stored_metadata(self, client, ext_dir):
        from py.db import model_repo

        await model_repo.upsert_model_with_meta(
            "my.safetensors",
            "loras",
            "civitai",
            "42",
            "A nice lora",
            trigger_words=["word1"],
            tags=["portrait"],
            base_model="SDXL 1.0",
        )
        resp = await client.get("/tiny-model-manager/api/models/loras/my.safetensors/metadata")
        data = (await resp.json())["data"]
        assert data["description"] == "A nice lora"
        assert "word1" in data["trigger_words"]
        assert data["base_model"] == "SDXL 1.0"

    async def test_civitai_source_url_derived(self, client, ext_dir):
        from py.db import model_repo

        await model_repo.upsert_model_with_meta(
            "civ.safetensors",
            "loras",
            "civitai",
            "999",
            "",
            trigger_words=[],
            tags=[],
            civitai_model_id="1234",
        )
        resp = await client.get("/tiny-model-manager/api/models/loras/civ.safetensors/metadata")
        data = (await resp.json())["data"]
        assert data["source_url"] == "https://civitai.com/models/1234"

    async def test_response_exposes_three_fields_distinctly(self, client, ext_dir):
        """F-32: GET metadata must expose base_model, trigger_words, and tags as distinct fields."""
        from py.db import model_repo

        await model_repo.upsert_model_with_meta(
            "f32.safetensors",
            "loras",
            "civitai",
            "99",
            "desc",
            trigger_words=["tw1"],
            tags=["portrait"],
            base_model="SDXL 1.0",
        )
        resp = await client.get("/tiny-model-manager/api/models/loras/f32.safetensors/metadata")
        data = (await resp.json())["data"]
        assert data["base_model"] == "SDXL 1.0"
        assert data["trigger_words"] == ["tw1"]
        assert data["tags"] == ["portrait"]
        assert "SDXL 1.0" not in data["trigger_words"]
        assert "SDXL 1.0" not in data["tags"]
        assert "tw1" not in data["tags"]


class TestPutMetadata:
    async def test_update_description_and_trigger_words(self, client, ext_dir):
        from py.db import model_repo

        await model_repo.upsert_model("upd.safetensors", "loras", "", "", "old desc")
        await client.put(
            "/tiny-model-manager/api/models/loras/upd.safetensors/metadata",
            json={"description": "new desc", "trigger_words": ["w1", "w2"]},
        )
        row = await model_repo.get_model_by_filename("upd.safetensors")
        assert row["description"] == "new desc"
        assert set(row["trigger_words"]) == {"w1", "w2"}

    async def test_update_base_model(self, client, ext_dir):
        from py.db import model_repo

        await model_repo.upsert_model("bm.safetensors", "loras", "", "", "")
        await client.put(
            "/tiny-model-manager/api/models/loras/bm.safetensors/metadata",
            json={"description": "", "trigger_words": [], "base_model": "Pony"},
        )
        row = await model_repo.get_model_by_filename("bm.safetensors")
        assert row["base_model"] == "Pony"

    async def test_returns_success(self, client, ext_dir):
        from py.db import model_repo

        await model_repo.upsert_model("r.safetensors", "loras", "", "", "")
        resp = await client.put(
            "/tiny-model-manager/api/models/loras/r.safetensors/metadata",
            json={"description": "d", "trigger_words": []},
        )
        assert (await resp.json())["success"] is True


class TestPutMetadataOrganize:
    @pytest.fixture()
    async def organize_client(self, aiohttp_client, ext_dir):
        import folder_paths

        from py.routes.metadata import add_metadata_routes

        models_dir = os.path.join(ext_dir, "models")
        loras_dir = os.path.join(models_dir, "loras")
        os.makedirs(loras_dir, exist_ok=True)
        folder_paths.models_dir = models_dir
        folder_paths.folder_names_and_paths["loras"] = ([loras_dir], {".safetensors"})

        app = web.Application()
        routes = web.RouteTableDef()
        add_metadata_routes(routes)
        app.router.add_routes(routes)
        return await aiohttp_client(app), loras_dir

    async def test_moves_file_on_base_model_change_when_organize_enabled(
        self, organize_client, ext_dir
    ):
        from py import config as cfg
        from py.db import model_repo

        client, loras_dir = organize_client
        cfg.save_settings({"organize_into_subfolders": True})

        old_subfolder = os.path.join(loras_dir, "SDXL 1.0")
        os.makedirs(old_subfolder)
        src = os.path.join(old_subfolder, "move-me.safetensors")
        open(src, "wb").close()

        await model_repo.upsert_model(
            "SDXL 1.0/move-me.safetensors", "loras", "", "", "", base_model="SDXL 1.0"
        )

        resp = await client.put(
            "/tiny-model-manager/api/models/loras/SDXL 1.0/move-me.safetensors/metadata",
            json={"description": "", "trigger_words": [], "base_model": "Pony"},
        )
        assert resp.status == 200

        assert os.path.exists(os.path.join(loras_dir, "Pony", "move-me.safetensors"))
        assert not os.path.exists(src)
        # Old empty dir removed
        assert not os.path.isdir(old_subfolder)

    async def test_does_not_move_when_organize_disabled(self, organize_client, ext_dir):
        from py import config as cfg
        from py.db import model_repo

        client, loras_dir = organize_client
        cfg.save_settings({"organize_into_subfolders": False})

        src = os.path.join(loras_dir, "flat.safetensors")
        open(src, "wb").close()

        await model_repo.upsert_model(
            "flat.safetensors", "loras", "", "", "", base_model="SDXL 1.0"
        )

        await client.put(
            "/tiny-model-manager/api/models/loras/flat.safetensors/metadata",
            json={"description": "", "trigger_words": [], "base_model": "Pony"},
        )

        assert os.path.exists(src)
        assert not os.path.exists(os.path.join(loras_dir, "Pony", "flat.safetensors"))


class TestServeMedia:
    async def test_serve_existing_file(self, client, ext_dir):
        from py import config as cfg

        media_subdir = os.path.join(cfg.media_dir(), "testhash")
        os.makedirs(media_subdir, exist_ok=True)
        img_path = os.path.join(media_subdir, "0.jpg")
        with open(img_path, "wb") as f:
            f.write(b"\xff\xd8\xff")  # minimal JPEG bytes

        resp = await client.get("/tiny-model-manager/api/media/testhash/0.jpg")
        assert resp.status == 200

    async def test_serve_nonexistent_returns_404(self, client, ext_dir):
        resp = await client.get("/tiny-model-manager/api/media/nope/nope.jpg")
        assert resp.status == 404

    async def test_path_traversal_returns_403(self, client, ext_dir):
        resp = await client.get("/tiny-model-manager/api/media/../../etc/passwd")
        assert resp.status in (403, 404)
