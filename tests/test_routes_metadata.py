"""Integration tests for py/routes/metadata.py (metadata CRUD + media serving)."""

import os
from datetime import UTC
from pathlib import Path

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

    async def test_returns_size_bytes_field(self, client):
        resp = await client.get("/tiny-model-manager/api/models/loras/unknown.safetensors/metadata")
        assert resp.status == 200
        data = (await resp.json())["data"]
        assert "size_bytes" in data
        assert isinstance(data["size_bytes"], int)
        assert data["size_bytes"] == 0  # file not present on disk in test context

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

    async def test_readme_html_in_response(self, client, ext_dir):
        """F-80: readme_html is included in the metadata response."""
        from py.db import model_repo

        await model_repo.upsert_model_with_meta(
            "readme.safetensors",
            "loras",
            "huggingface",
            "user/repo",
            "",
            trigger_words=[],
            tags=[],
            readme_html="<h1>Hello</h1>",
        )
        resp = await client.get("/tiny-model-manager/api/models/loras/readme.safetensors/metadata")
        data = (await resp.json())["data"]
        assert data["readme_html"] == "<h1>Hello</h1>"


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

    async def test_returns_new_path_equal_to_original_when_no_move(self, client, ext_dir):
        from py.db import model_repo

        await model_repo.upsert_model("np.safetensors", "loras", "", "", "")
        resp = await client.put(
            "/tiny-model-manager/api/models/loras/np.safetensors/metadata",
            json={"description": "d", "trigger_words": []},
        )
        data = await resp.json()
        assert data["new_path"] == "np.safetensors"

    async def test_saves_base_model_for_file_with_no_db_row(self, client, ext_dir):
        # No upsert_model call — the file has no models row (manually-placed file)
        resp = await client.put(
            "/tiny-model-manager/api/models/loras/manual.safetensors/metadata",
            json={"base_model": "Flux.1 D"},
        )
        assert (await resp.json())["success"] is True
        from py.db import model_repo

        row = await model_repo.get_model_by_filename("manual.safetensors")
        assert row is not None
        assert row["base_model"] == "Flux.1 D"

    async def test_partial_update_does_not_clear_existing_description(self, client, ext_dir):
        from py.db import model_repo

        await model_repo.upsert_model_with_meta(
            "existing.safetensors", "loras", "", "", "keep me", ["kw"], [], base_model=""
        )
        # Send only base_model — description and trigger_words must be preserved
        resp = await client.put(
            "/tiny-model-manager/api/models/loras/existing.safetensors/metadata",
            json={"base_model": "SDXL 1.0"},
        )
        assert (await resp.json())["success"] is True
        row = await model_repo.get_model_by_filename("existing.safetensors")
        assert row["description"] == "keep me"
        assert "kw" in row["trigger_words"]
        assert row["base_model"] == "SDXL 1.0"


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
        Path(src).touch()

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
        Path(src).touch()

        await model_repo.upsert_model(
            "flat.safetensors", "loras", "", "", "", base_model="SDXL 1.0"
        )

        await client.put(
            "/tiny-model-manager/api/models/loras/flat.safetensors/metadata",
            json={"description": "", "trigger_words": [], "base_model": "Pony"},
        )

        assert os.path.exists(src)
        assert not os.path.exists(os.path.join(loras_dir, "Pony", "flat.safetensors"))

    async def test_returns_new_path_in_response_when_file_moves(self, organize_client, ext_dir):
        from py import config as cfg
        from py.db import model_repo

        client, loras_dir = organize_client
        cfg.save_settings({"organize_into_subfolders": True})

        old_subfolder = os.path.join(loras_dir, "SDXL 1.0")
        os.makedirs(old_subfolder)
        src = os.path.join(old_subfolder, "resp-test.safetensors")
        Path(src).touch()

        await model_repo.upsert_model(
            "SDXL 1.0/resp-test.safetensors", "loras", "", "", "", base_model="SDXL 1.0"
        )

        resp = await client.put(
            "/tiny-model-manager/api/models/loras/SDXL 1.0/resp-test.safetensors/metadata",
            json={"description": "", "trigger_words": [], "base_model": "Pony"},
        )
        data = await resp.json()
        assert data["new_path"] == "Pony/resp-test.safetensors"


class TestRefetchMetadata:
    @staticmethod
    def _touch_model_file(rel_path: str, model_type: str = "loras") -> None:
        """Create an empty model file on disk so refetch's disk check passes."""
        import folder_paths

        full = os.path.join(folder_paths.models_dir, model_type, rel_path)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "wb") as f:
            f.write(b"x")

    async def test_skip_media_false_when_no_existing_media(self, client, ext_dir, monkeypatch):
        """Refetch downloads images when the model has no stored media rows."""
        from py.db import model_repo

        captured: dict = {}

        async def fake_fetch(filename, model_type, platform, source_id, skip_media=False):
            captured["skip_media"] = skip_media

        monkeypatch.setattr("py.services.metadata_fetcher.fetch_and_store", fake_fetch)

        self._touch_model_file("no-media.safetensors")
        await model_repo.upsert_model_with_meta(
            "no-media.safetensors",
            "loras",
            "huggingface",
            "user/repo",
            "desc",
            trigger_words=[],
            tags=[],
        )
        resp = await client.post(
            "/tiny-model-manager/api/models/loras/no-media.safetensors/refetch"
        )
        assert resp.status == 200
        assert captured.get("skip_media") is False

    async def test_skip_media_true_when_media_exists(self, client, ext_dir, monkeypatch):
        """Refetch preserves existing images when media rows are already stored."""
        from py.db import model_repo

        captured: dict = {}

        async def fake_fetch(filename, model_type, platform, source_id, skip_media=False):
            captured["skip_media"] = skip_media

        monkeypatch.setattr("py.services.metadata_fetcher.fetch_and_store", fake_fetch)

        self._touch_model_file("has-media.safetensors")
        model_id = await model_repo.upsert_model_with_meta(
            "has-media.safetensors",
            "loras",
            "huggingface",
            "user/repo",
            "desc",
            trigger_words=[],
            tags=[],
        )
        await model_repo.add_media(model_id, "image", "/some/path/0.jpg")

        resp = await client.post(
            "/tiny-model-manager/api/models/loras/has-media.safetensors/refetch"
        )
        assert resp.status == 200
        assert captured.get("skip_media") is True

    async def test_returns_400_when_no_source_info(self, client, ext_dir):
        """Refetch returns 400 when the file exists but has no source platform/id stored."""
        self._touch_model_file("unknown.safetensors")
        resp = await client.post("/tiny-model-manager/api/models/loras/unknown.safetensors/refetch")
        assert resp.status == 400

    async def test_removes_stale_record_when_file_missing(self, client, ext_dir):
        """Refetch prunes the DB record when the file no longer exists on disk."""
        from py.db import model_repo

        await model_repo.upsert_model_with_meta(
            "ghost.safetensors",
            "loras",
            "huggingface",
            "user/repo",
            "desc",
            trigger_words=[],
            tags=[],
        )
        resp = await client.post("/tiny-model-manager/api/models/loras/ghost.safetensors/refetch")
        assert resp.status == 200
        data = (await resp.json())["data"]
        assert data["removed"] is True
        # The stale row is gone.
        assert await model_repo.get_model_by_filename("ghost.safetensors") is None


class TestGetRepoFiles:
    _SAMPLE_FILES = [
        {
            "filename": "model-fp16.safetensors",
            "size_bytes": 2097152,
            "download_url": "https://example.com/fp16",
            "source_page_url": "https://civitai.com/models/1",
        },
        {
            "filename": "vae.safetensors",
            "size_bytes": 335544320,
            "download_url": "https://example.com/vae",
            "source_page_url": "https://civitai.com/models/1",
        },
    ]

    async def test_returns_empty_list_when_no_repo_files(self, client, ext_dir):
        resp = await client.get(
            "/tiny-model-manager/api/models/loras/my-lora.safetensors/repo-files"
        )
        assert resp.status == 200
        body = await resp.json()
        assert body["success"] is True
        assert body["data"] == []

    async def _setup_model_with_repo_files(self, filename: str, model_type: str, files: list[dict]):
        """Create a catalog entry, models row, and repo_files for testing."""
        from py.db import model_repo

        entry_id = await model_repo.upsert_catalog_entry(
            source_platform="civitai",
            source_page_id=filename,
            source_page_url="https://civitai.com/models/1",
            display_name="Test",
            thumbnail_url="",
            base_model="",
        )
        await model_repo.upsert_model(filename, model_type, "civitai", "100", "")
        await model_repo.set_model_catalog_entry(filename, entry_id)
        await model_repo.upsert_repo_files(entry_id, model_type, files)

    async def test_returns_stored_files_with_is_downloaded(self, client, ext_dir):
        await self._setup_model_with_repo_files("my-lora.safetensors", "loras", self._SAMPLE_FILES)
        resp = await client.get(
            "/tiny-model-manager/api/models/loras/my-lora.safetensors/repo-files"
        )
        assert resp.status == 200
        data = (await resp.json())["data"]
        assert len(data) == 2
        for item in data:
            assert "is_downloaded" in item
            assert item["is_downloaded"] is False  # files not on disk in test context

    async def test_is_downloaded_true_when_file_exists(self, client, ext_dir):
        import sys

        # Create the file on disk in the test models dir
        models_dir = sys.modules["folder_paths"].models_dir
        loras_dir = os.path.join(models_dir, "loras")
        os.makedirs(loras_dir, exist_ok=True)
        dummy_file = os.path.join(loras_dir, "model-fp16.safetensors")
        with open(dummy_file, "wb") as f:
            f.write(b"dummy")

        await self._setup_model_with_repo_files("my-lora.safetensors", "loras", self._SAMPLE_FILES)
        resp = await client.get(
            "/tiny-model-manager/api/models/loras/my-lora.safetensors/repo-files"
        )
        data = (await resp.json())["data"]
        fp16 = next(d for d in data if d["filename"] == "model-fp16.safetensors")
        assert fp16["is_downloaded"] is True
        vae = next(d for d in data if d["filename"] == "vae.safetensors")
        assert vae["is_downloaded"] is False

    async def test_subfolder_model_path(self, client, ext_dir):
        await self._setup_model_with_repo_files(
            "sdxl/my-lora.safetensors", "loras", self._SAMPLE_FILES
        )
        resp = await client.get(
            "/tiny-model-manager/api/models/loras/sdxl/my-lora.safetensors/repo-files"
        )
        assert resp.status == 200
        data = (await resp.json())["data"]
        assert len(data) == 2

    async def test_is_downloaded_true_via_db_when_file_in_models_table(self, client, ext_dir):
        # A sibling file exists in the models table (same catalog entry) but is NOT on disk.
        # The DB-based check should still mark it as downloaded.
        from py.db import model_repo

        files_with_sibling = [
            {
                "filename": "model-fp16.safetensors",
                "size_bytes": 4096,
                "download_url": "https://example.com/fp16",
                "source_page_url": "https://civitai.com/models/1",
            },
            {
                "filename": "model-q4.safetensors",
                "size_bytes": 2048,
                "download_url": "https://example.com/q4",
                "source_page_url": "https://civitai.com/models/1",
            },
        ]
        # Set up catalog entry and link both the current model AND the sibling
        entry_id = await model_repo.upsert_catalog_entry(
            source_platform="civitai",
            source_page_id="my-lora.safetensors",
            source_page_url="https://civitai.com/models/1",
            display_name="Test",
            thumbnail_url="",
            base_model="",
        )
        await model_repo.upsert_model("my-lora.safetensors", "loras", "civitai", "100", "")
        await model_repo.set_model_catalog_entry("my-lora.safetensors", entry_id)
        # Also mark model-fp16 as installed in the DB (same catalog entry)
        await model_repo.upsert_model("model-fp16.safetensors", "loras", "civitai", "100", "")
        await model_repo.set_model_catalog_entry("model-fp16.safetensors", entry_id)
        await model_repo.upsert_repo_files(entry_id, "loras", files_with_sibling)

        resp = await client.get(
            "/tiny-model-manager/api/models/loras/my-lora.safetensors/repo-files"
        )
        data = (await resp.json())["data"]
        fp16 = next(d for d in data if d["filename"] == "model-fp16.safetensors")
        q4 = next(d for d in data if d["filename"] == "model-q4.safetensors")
        assert fp16["is_downloaded"] is True  # in models table → DB check succeeds
        assert fp16["installed_path"] == "model-fp16.safetensors"
        assert fp16["base_model"] == ""
        assert q4["is_downloaded"] is False  # not in models table, not on disk
        assert q4["installed_path"] == ""
        assert q4["base_model"] == ""

    async def test_base_model_returned_for_downloaded_sibling(self, client, ext_dir):
        from py.db import model_repo

        entry_id = await model_repo.upsert_catalog_entry(
            source_platform="civitai",
            source_page_id="my-lora.safetensors",
            source_page_url="https://civitai.com/models/1",
            display_name="Test",
            thumbnail_url="",
            base_model="",
        )
        await model_repo.upsert_model_with_meta(
            "model-fp16.safetensors",
            "loras",
            "civitai",
            "100",
            "",
            [],
            [],
            base_model="Flux.1 D",
        )
        await model_repo.set_model_catalog_entry("model-fp16.safetensors", entry_id)
        await model_repo.upsert_model("my-lora.safetensors", "loras", "civitai", "100", "")
        await model_repo.set_model_catalog_entry("my-lora.safetensors", entry_id)
        files = [
            {
                "filename": "model-fp16.safetensors",
                "size_bytes": 4096,
                "download_url": "https://example.com/fp16",
                "source_page_url": "https://civitai.com/models/1",
            },
        ]
        await model_repo.upsert_repo_files(entry_id, "loras", files)

        resp = await client.get(
            "/tiny-model-manager/api/models/loras/my-lora.safetensors/repo-files"
        )
        data = (await resp.json())["data"]
        fp16 = next(d for d in data if d["filename"] == "model-fp16.safetensors")
        assert fp16["is_downloaded"] is True
        assert fp16["base_model"] == "Flux.1 D"


class TestLinkSource:
    async def test_returns_400_for_unrecognised_url(self, client, ext_dir):
        resp = await client.post(
            "/tiny-model-manager/api/models/loras/my.safetensors/link-source",
            json={"source_url": "https://example.com/not-a-model"},
        )
        assert resp.status == 400

    async def test_links_civitai_model_url(self, client, ext_dir):
        from py.db import model_repo

        entry_id = await model_repo.upsert_catalog_entry(
            source_platform="civitai",
            source_page_id="12345",
            source_page_url="https://civitai.com/models/12345",
            display_name="Test",
            thumbnail_url="",
            base_model="",
        )
        resp = await client.post(
            "/tiny-model-manager/api/models/loras/my.safetensors/link-source",
            json={"source_url": "https://civitai.com/models/12345"},
        )
        assert resp.status == 200
        row = await model_repo.get_model_by_filename("my.safetensors")
        assert row is not None
        assert row["source_platform"] == "civitai"
        assert row["civitai_model_id"] == "12345"
        assert row["catalog_entry_id"] == entry_id

    async def test_links_huggingface_url(self, client, ext_dir):
        from py.db import model_repo

        entry_id = await model_repo.upsert_catalog_entry(
            source_platform="huggingface",
            source_page_id="user/repo",
            source_page_url="https://huggingface.co/user/repo",
            display_name="HF Model",
            thumbnail_url="",
            base_model="",
        )
        resp = await client.post(
            "/tiny-model-manager/api/models/loras/hf.safetensors/link-source",
            json={"source_url": "https://huggingface.co/user/repo"},
        )
        assert resp.status == 200
        row = await model_repo.get_model_by_filename("hf.safetensors")
        assert row is not None
        assert row["source_platform"] == "huggingface"
        assert row["source_id"] == "user/repo"
        assert row["catalog_entry_id"] == entry_id

    async def test_links_without_catalog_entry(self, client, ext_dir):
        """Linking succeeds even if no matching catalog entry exists yet."""
        resp = await client.post(
            "/tiny-model-manager/api/models/loras/lone.safetensors/link-source",
            json={"source_url": "https://civitai.com/models/99999"},
        )
        assert resp.status == 200
        from py.db import model_repo

        row = await model_repo.get_model_by_filename("lone.safetensors")
        assert row is not None
        assert row["source_platform"] == "civitai"
        assert row["civitai_model_id"] == "99999"
        assert row["catalog_entry_id"] is None


class TestRefetchPreview:
    @staticmethod
    def _touch_model_file(rel_path: str, model_type: str = "loras") -> None:
        import folder_paths

        full = os.path.join(folder_paths.models_dir, model_type, rel_path)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "wb") as f:
            f.write(b"x")

    @staticmethod
    def _make_fake_metadata(**kwargs):
        from unittest.mock import AsyncMock

        from py.services.providers.base import ProviderMetadata

        defaults = {
            "description": "New desc",
            "trigger_words": ["new_word"],
            "tags": ["new_tag"],
            "base_model": "Flux.1 D",
            "image_urls": ["https://image.civitai.com/abc/img.jpg"],
            "civitai_model_id": "",
            "display_name": "Model",
        }
        defaults.update(kwargs)
        return AsyncMock(return_value=ProviderMetadata(**defaults))

    async def test_returns_old_and_new_data(self, client, ext_dir, monkeypatch):
        from py.db import model_repo

        self._touch_model_file("preview-model.safetensors")
        await model_repo.upsert_model_with_meta(
            "preview-model.safetensors",
            "loras",
            "huggingface",
            "user/repo",
            "Old desc",
            trigger_words=["old_word"],
            tags=["old_tag"],
            base_model="SDXL 1.0",
        )
        monkeypatch.setattr(
            "py.services.metadata_fetcher.fetch_metadata_only",
            self._make_fake_metadata(),
        )
        resp = await client.post(
            "/tiny-model-manager/api/models/loras/preview-model.safetensors/refetch-preview"
        )
        assert resp.status == 200
        data = (await resp.json())["data"]
        assert "old" in data
        assert "new" in data
        assert "expires_at" in data
        assert "no_changes" in data
        assert data["no_changes"] is False

    async def test_no_changes_flag(self, client, ext_dir, monkeypatch):
        from py.db import model_repo

        self._touch_model_file("same-model.safetensors")
        await model_repo.upsert_model_with_meta(
            "same-model.safetensors",
            "loras",
            "huggingface",
            "user/repo",
            "Same desc",
            trigger_words=["word"],
            tags=["tag"],
            base_model="SDXL 1.0",
        )
        monkeypatch.setattr(
            "py.services.metadata_fetcher.fetch_metadata_only",
            self._make_fake_metadata(
                description="Same desc",
                trigger_words=["word"],
                tags=["tag"],
                base_model="SDXL 1.0",
                image_urls=[],
            ),
        )
        resp = await client.post(
            "/tiny-model-manager/api/models/loras/same-model.safetensors/refetch-preview"
        )
        data = (await resp.json())["data"]
        assert data["no_changes"] is True

    async def test_returns_400_when_no_source_info(self, client, ext_dir):
        self._touch_model_file("no-source.safetensors")
        resp = await client.post(
            "/tiny-model-manager/api/models/loras/no-source.safetensors/refetch-preview"
        )
        assert resp.status == 400

    async def test_removes_stale_record_when_file_missing(self, client, ext_dir, monkeypatch):
        from py.db import model_repo

        await model_repo.upsert_model_with_meta(
            "ghost-preview.safetensors",
            "loras",
            "huggingface",
            "user/repo",
            "",
            trigger_words=[],
            tags=[],
        )
        monkeypatch.setattr(
            "py.services.metadata_fetcher.fetch_metadata_only",
            self._make_fake_metadata(),
        )
        resp = await client.post(
            "/tiny-model-manager/api/models/loras/ghost-preview.safetensors/refetch-preview"
        )
        assert resp.status == 200
        data = (await resp.json())["data"]
        assert data.get("removed") is True

    async def test_cache_entry_created(self, client, ext_dir, monkeypatch):
        from py.db import model_repo
        from py.routes.metadata import _refetch_cache

        self._touch_model_file("cached-model.safetensors")
        await model_repo.upsert_model_with_meta(
            "cached-model.safetensors",
            "loras",
            "huggingface",
            "user/repo",
            "desc",
            trigger_words=[],
            tags=[],
        )
        monkeypatch.setattr(
            "py.services.metadata_fetcher.fetch_metadata_only",
            self._make_fake_metadata(),
        )
        await client.post(
            "/tiny-model-manager/api/models/loras/cached-model.safetensors/refetch-preview"
        )
        assert "cached-model.safetensors" in _refetch_cache

    async def test_apply_returns_400_when_no_cache(self, client, ext_dir):
        resp = await client.post(
            "/tiny-model-manager/api/models/loras/no-cache.safetensors/refetch-apply",
            json={
                "description": "d",
                "trigger_words": [],
                "tags": [],
                "base_model": "",
                "replace_media": False,
                "media_urls": [],
                "keep_existing_media": [],
            },
        )
        assert resp.status == 400

    async def test_apply_returns_410_when_expired(self, client, ext_dir):
        from datetime import datetime as dt
        from datetime import timedelta

        from py.routes.metadata import _refetch_cache, _RefetchEntry

        expired_entry = _RefetchEntry(
            fetched_at=dt.now(UTC) - timedelta(seconds=400),
            old={},
            new_data={},
        )
        _refetch_cache["expired.safetensors"] = expired_entry

        resp = await client.post(
            "/tiny-model-manager/api/models/loras/expired.safetensors/refetch-apply",
            json={
                "description": "d",
                "trigger_words": [],
                "tags": [],
                "base_model": "",
                "replace_media": False,
                "media_urls": [],
                "keep_existing_media": [],
            },
        )
        assert resp.status == 410
        assert "expired.safetensors" not in _refetch_cache

    async def test_apply_writes_selected_values(self, client, ext_dir, monkeypatch):
        from datetime import datetime

        from py.db import model_repo
        from py.routes.metadata import _refetch_cache, _RefetchEntry

        self._touch_model_file("apply-test.safetensors")
        await model_repo.upsert_model_with_meta(
            "apply-test.safetensors",
            "loras",
            "huggingface",
            "user/repo",
            "old",
            trigger_words=[],
            tags=[],
        )
        _refetch_cache["apply-test.safetensors"] = _RefetchEntry(
            fetched_at=datetime.now(UTC),
            old={"description": "old", "trigger_words": [], "tags": [], "base_model": ""},
            new_data={
                "description": "new",
                "trigger_words": ["w1"],
                "tags": ["t1"],
                "base_model": "Flux.1 D",
            },
        )

        resp = await client.post(
            "/tiny-model-manager/api/models/loras/apply-test.safetensors/refetch-apply",
            json={
                "description": "new",
                "trigger_words": ["w1"],
                "tags": ["t1"],
                "base_model": "Flux.1 D",
                "replace_media": False,
                "media_urls": [],
                "keep_existing_media": [],
            },
        )
        assert resp.status == 200
        row = await model_repo.get_model_by_filename("apply-test.safetensors")
        assert row["description"] == "new"
        assert row["trigger_words"] == ["w1"]
        assert row["tags"] == ["t1"]
        assert row["base_model"] == "Flux.1 D"

    async def test_apply_sets_edited_at(self, client, ext_dir, monkeypatch):
        from datetime import datetime

        from py.db import model_repo
        from py.db.database import get_db
        from py.routes.metadata import _refetch_cache, _RefetchEntry

        self._touch_model_file("edited-at.safetensors")
        await model_repo.upsert_model_with_meta(
            "edited-at.safetensors",
            "loras",
            "huggingface",
            "user/repo",
            "",
            trigger_words=[],
            tags=[],
        )
        _refetch_cache["edited-at.safetensors"] = _RefetchEntry(
            fetched_at=datetime.now(UTC),
            old={},
            new_data={},
        )

        await client.post(
            "/tiny-model-manager/api/models/loras/edited-at.safetensors/refetch-apply",
            json={
                "description": "desc",
                "trigger_words": ["w"],
                "tags": ["t"],
                "base_model": "Pony",
                "replace_media": False,
                "media_urls": [],
                "keep_existing_media": [],
            },
        )

        async with get_db() as db:
            row = await (
                await db.execute(
                    "SELECT description_edited_at, trigger_words_edited_at, tags_edited_at,"
                    " base_model_edited_at FROM models WHERE filename = ?",
                    ("edited-at.safetensors",),
                )
            ).fetchone()
        assert row is not None
        assert row["description_edited_at"] is not None
        assert row["trigger_words_edited_at"] is not None
        assert row["tags_edited_at"] is not None
        assert row["base_model_edited_at"] is not None

    async def test_apply_clears_cache(self, client, ext_dir, monkeypatch):
        from datetime import datetime

        from py.db import model_repo
        from py.routes.metadata import _refetch_cache, _RefetchEntry

        self._touch_model_file("clear-cache.safetensors")
        await model_repo.upsert_model_with_meta(
            "clear-cache.safetensors",
            "loras",
            "huggingface",
            "user/repo",
            "",
            trigger_words=[],
            tags=[],
        )
        _refetch_cache["clear-cache.safetensors"] = _RefetchEntry(
            fetched_at=datetime.now(UTC),
            old={},
            new_data={},
        )

        await client.post(
            "/tiny-model-manager/api/models/loras/clear-cache.safetensors/refetch-apply",
            json={
                "description": "d",
                "trigger_words": [],
                "tags": [],
                "base_model": "",
                "replace_media": False,
                "media_urls": [],
                "keep_existing_media": [],
            },
        )
        assert "clear-cache.safetensors" not in _refetch_cache

    async def test_apply_replace_media(self, client, ext_dir, monkeypatch):
        from datetime import datetime
        from unittest.mock import AsyncMock

        from py.db import model_repo
        from py.routes.metadata import _refetch_cache, _RefetchEntry

        self._touch_model_file("media-replace.safetensors")
        model_id = await model_repo.upsert_model_with_meta(
            "media-replace.safetensors",
            "loras",
            "huggingface",
            "user/repo",
            "",
            trigger_words=[],
            tags=[],
        )
        old_media_id = await model_repo.add_media(model_id, "image", "/old/path/0.jpg")

        _refetch_cache["media-replace.safetensors"] = _RefetchEntry(
            fetched_at=datetime.now(UTC),
            old={},
            new_data={},
        )
        monkeypatch.setattr(
            "py.services.metadata_fetcher._download_images",
            AsyncMock(),
        )
        resp = await client.post(
            "/tiny-model-manager/api/models/loras/media-replace.safetensors/refetch-apply",
            json={
                "description": "",
                "trigger_words": [],
                "tags": [],
                "base_model": "",
                "replace_media": True,
                "media_urls": ["https://example.com/new.jpg"],
                "keep_existing_media": [],
            },
        )
        assert resp.status == 200
        remaining = await model_repo.get_model_media(model_id)
        assert not any(r["id"] == old_media_id for r in remaining)


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

    async def test_sibling_directory_escape_blocked(self, ext_dir):
        import types

        from py import config as cfg
        from py.routes.metadata import _serve_media

        # A sibling of the media dir that shares its name prefix must not be reachable
        # (a plain str.startswith guard would wrongly allow "<media>_evil").
        media_dir = cfg.media_dir()
        sibling = media_dir + "_evil"
        os.makedirs(sibling, exist_ok=True)
        with open(os.path.join(sibling, "secret.txt"), "wb") as f:
            f.write(b"top secret")

        rel = os.path.join("..", os.path.basename(sibling), "secret.txt")
        req = types.SimpleNamespace(match_info={"path": rel})
        resp = await _serve_media(req)
        assert resp.status == 403
