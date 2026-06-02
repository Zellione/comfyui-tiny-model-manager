"""Integration tests for py/routes/catalog.py."""

import os

import pytest
from aiohttp import web


@pytest.fixture()
async def client(aiohttp_client, ext_dir):
    import folder_paths

    models_dir = os.path.join(ext_dir, "models")
    for folder_type in ("checkpoints", "loras"):
        folder = os.path.join(models_dir, folder_type)
        os.makedirs(folder, exist_ok=True)
        folder_paths.folder_names_and_paths[folder_type] = ([folder], {".safetensors", ".ckpt"})
    folder_paths.models_dir = models_dir

    from py.routes.catalog import add_catalog_routes

    app = web.Application()
    routes = web.RouteTableDef()
    add_catalog_routes(routes)
    app.router.add_routes(routes)
    return await aiohttp_client(app)


async def _make_entry(platform="civitai", page_id="123", display_name="Test Model"):
    from py.db import model_repo

    return await model_repo.upsert_catalog_entry(
        source_platform=platform,
        source_page_id=page_id,
        source_page_url=f"https://civitai.com/models/{page_id}",
        display_name=display_name,
        thumbnail_url="",
        base_model="SDXL",
    )


class TestListCatalog:
    async def test_empty_catalog_returns_empty_lists(self, client, ext_dir):
        resp = await client.get("/tiny-model-manager/api/catalog")
        assert resp.status == 200
        data = (await resp.json())["data"]
        assert data["entries"] == []
        assert data["unknown_files"] == {}

    async def test_catalog_entry_appears_in_list(self, client, ext_dir):
        await _make_entry()
        resp = await client.get("/tiny-model-manager/api/catalog")
        assert resp.status == 200
        entries = (await resp.json())["data"]["entries"]
        assert len(entries) == 1
        assert entries[0]["display_name"] == "Test Model"
        assert entries[0]["source_platform"] == "civitai"

    async def test_empty_entry_has_is_empty_true(self, client, ext_dir):
        await _make_entry()
        resp = await client.get("/tiny-model-manager/api/catalog")
        entry = (await resp.json())["data"]["entries"][0]
        assert entry["is_empty"] is True

    async def test_installed_file_on_disk_makes_is_empty_false(self, client, ext_dir):
        import folder_paths

        from py.db import model_repo

        entry_id = await _make_entry()
        # Write a file to disk and link it to the catalog entry
        loras_dir = folder_paths.folder_names_and_paths["loras"][0][0]
        fpath = os.path.join(loras_dir, "test.safetensors")
        open(fpath, "wb").close()
        model_id = await model_repo.upsert_model("test.safetensors", "loras", "civitai", "456", "")
        await model_repo.set_model_catalog_entry("test.safetensors", entry_id)
        _ = model_id

        resp = await client.get("/tiny-model-manager/api/catalog")
        entry = (await resp.json())["data"]["entries"][0]
        assert entry["is_empty"] is False

    async def test_file_without_catalog_entry_is_unknown(self, client, ext_dir):
        import folder_paths

        loras_dir = folder_paths.folder_names_and_paths["loras"][0][0]
        fpath = os.path.join(loras_dir, "orphan.safetensors")
        open(fpath, "wb").close()

        resp = await client.get("/tiny-model-manager/api/catalog")
        data = (await resp.json())["data"]
        assert "loras" in data["unknown_files"]
        filenames = [f["filename"] for f in data["unknown_files"]["loras"]]
        assert "orphan.safetensors" in filenames


class TestGetCatalogEntry:
    async def test_returns_404_for_missing_entry(self, client, ext_dir):
        resp = await client.get("/tiny-model-manager/api/catalog/civitai/99999")
        assert resp.status == 404

    async def test_returns_entry_detail(self, client, ext_dir):
        await _make_entry(page_id="555", display_name="Flux Dev")
        resp = await client.get("/tiny-model-manager/api/catalog/civitai/555")
        assert resp.status == 200
        data = (await resp.json())["data"]
        assert data["display_name"] == "Flux Dev"
        assert data["source_page_id"] == "555"
        assert "repo_files" in data

    async def test_repo_files_have_is_downloaded(self, client, ext_dir):
        from py.db import model_repo

        entry_id = await _make_entry(page_id="777")
        await model_repo.upsert_repo_files(
            entry_id,
            "loras",
            [
                {
                    "filename": "model.safetensors",
                    "size_bytes": 1000,
                    "download_url": "https://example.com/model.safetensors",
                    "source_page_url": "https://civitai.com/models/777",
                }
            ],
        )
        resp = await client.get("/tiny-model-manager/api/catalog/civitai/777")
        data = (await resp.json())["data"]
        assert len(data["repo_files"]) == 1
        assert "is_downloaded" in data["repo_files"][0]
        assert data["repo_files"][0]["is_downloaded"] is False


class TestDeleteCatalogEntry:
    async def test_returns_404_for_missing_entry(self, client, ext_dir):
        resp = await client.delete("/tiny-model-manager/api/catalog/civitai/00000")
        assert resp.status == 404

    async def test_deletes_entry(self, client, ext_dir):
        await _make_entry(page_id="888")
        resp = await client.delete("/tiny-model-manager/api/catalog/civitai/888")
        assert resp.status == 200
        assert (await resp.json())["success"] is True

        # Verify gone
        resp2 = await client.get("/tiny-model-manager/api/catalog/civitai/888")
        assert resp2.status == 404

    async def test_deletes_associated_repo_files(self, client, ext_dir):
        from py.db import model_repo

        entry_id = await _make_entry(page_id="999")
        await model_repo.upsert_repo_files(
            entry_id,
            "loras",
            [
                {
                    "filename": "a.safetensors",
                    "size_bytes": 100,
                    "download_url": "",
                    "source_page_url": "",
                }
            ],
        )
        await client.delete("/tiny-model-manager/api/catalog/civitai/999")
        # Entry is gone so repo_files cascade-deleted
        files = await model_repo.get_repo_files_by_catalog(entry_id)
        assert files == []

    async def test_deletes_media_from_disk(self, client, ext_dir):
        from py.db import model_repo

        entry_id = await _make_entry(page_id="111")
        # Create a fake media file
        media_path = os.path.join(ext_dir, "media", "testhash", "0.jpg")
        os.makedirs(os.path.dirname(media_path), exist_ok=True)
        open(media_path, "wb").close()
        # Insert a model linked to this entry with media
        model_id = await model_repo.upsert_model(
            "linked.safetensors", "loras", "civitai", "456", ""
        )
        await model_repo.set_model_catalog_entry("linked.safetensors", entry_id)
        await model_repo.add_media(model_id, "image", media_path)

        await client.delete("/tiny-model-manager/api/catalog/civitai/111")
        assert not os.path.isfile(media_path)
