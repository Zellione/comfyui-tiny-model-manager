"""Integration tests for py/routes/catalog.py."""

import os
from pathlib import Path

import pytest
from aiohttp import web


@pytest.fixture
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
        Path(fpath).touch()
        model_id = await model_repo.upsert_model("test.safetensors", "loras", "civitai", "456", "")
        await model_repo.set_model_catalog_entry("test.safetensors", entry_id)
        _ = model_id

        resp = await client.get("/tiny-model-manager/api/catalog")
        entry = (await resp.json())["data"]["entries"][0]
        assert entry["is_empty"] is False

    async def test_installed_file_exposes_civitai_version_name(self, client, ext_dir):
        import folder_paths

        from py.db import model_repo

        entry_id = await _make_entry(page_id="vn_test")
        loras_dir = folder_paths.folder_names_and_paths["loras"][0][0]
        fpath = os.path.join(loras_dir, "versioned.safetensors")
        Path(fpath).touch()
        await model_repo.upsert_model(
            "versioned.safetensors",
            "loras",
            "civitai",
            "999",
            "",
            civitai_version_name="v2 Turbo",
        )
        await model_repo.set_model_catalog_entry("versioned.safetensors", entry_id)

        resp = await client.get("/tiny-model-manager/api/catalog")
        entries = (await resp.json())["data"]["entries"]
        entry = next(e for e in entries if e["source_page_id"] == "vn_test")
        assert entry["installed_files"][0]["civitai_version_name"] == "v2 Turbo"

    async def test_catalog_list_includes_trigger_words(self, client, ext_dir):
        from py.db import model_repo

        await model_repo.upsert_catalog_entry(
            source_platform="civitai",
            source_page_id="tw_test",
            source_page_url="https://civitai.com/models/tw_test",
            display_name="TW Model",
            thumbnail_url="",
            base_model="SDXL",
            trigger_words=["alpha", "beta"],
        )
        resp = await client.get("/tiny-model-manager/api/catalog")
        assert resp.status == 200
        entries = (await resp.json())["data"]["entries"]
        entry = next(e for e in entries if e["source_page_id"] == "tw_test")
        assert entry["trigger_words"] == ["alpha", "beta"]

    async def test_entry_is_video_only_when_all_media_are_videos(self, client, ext_dir):
        from py.db import model_repo

        entry_id = await _make_entry(page_id="vidonly")
        model_id = await model_repo.upsert_model(
            "vidonly.safetensors", "loras", "civitai", "99", ""
        )
        await model_repo.set_model_catalog_entry("vidonly.safetensors", entry_id)
        await model_repo.add_media(model_id, "video", "/tmp/clip.mp4")

        resp = await client.get("/tiny-model-manager/api/catalog")
        entry = next(
            e for e in (await resp.json())["data"]["entries"] if e["source_page_id"] == "vidonly"
        )
        assert entry["is_video_only"] is True

    async def test_entry_is_not_video_only_when_has_image(self, client, ext_dir):
        from py.db import model_repo

        entry_id = await _make_entry(page_id="withimg")
        model_id = await model_repo.upsert_model(
            "withimg.safetensors", "loras", "civitai", "100", ""
        )
        await model_repo.set_model_catalog_entry("withimg.safetensors", entry_id)
        await model_repo.add_media(model_id, "video", "/tmp/clip.mp4")
        await model_repo.add_media(model_id, "image", "/tmp/thumb.jpg")

        resp = await client.get("/tiny-model-manager/api/catalog")
        entry = next(
            e for e in (await resp.json())["data"]["entries"] if e["source_page_id"] == "withimg"
        )
        assert entry["is_video_only"] is False

    async def test_entry_is_not_video_only_when_no_media(self, client, ext_dir):
        await _make_entry(page_id="nomedia")
        resp = await client.get("/tiny-model-manager/api/catalog")
        entry = next(
            e for e in (await resp.json())["data"]["entries"] if e["source_page_id"] == "nomedia"
        )
        assert entry["is_video_only"] is False

    async def test_thumbnail_falls_back_to_image_when_catalog_url_is_video(self, client, ext_dir):
        from py.db import model_repo

        entry_id = await model_repo.upsert_catalog_entry(
            source_platform="civitai",
            source_page_id="vidfirst",
            source_page_url="https://civitai.com/models/vidfirst",
            display_name="Video First",
            thumbnail_url="/tmp/preview.mp4",
            base_model="SDXL",
        )
        model_id = await model_repo.upsert_model(
            "vidfirst.safetensors", "loras", "civitai", "vidfirst", ""
        )
        await model_repo.set_model_catalog_entry("vidfirst.safetensors", entry_id)
        await model_repo.add_media(model_id, "video", "/tmp/first.mp4")
        await model_repo.add_media(model_id, "image", "/tmp/fallback.jpg")

        resp = await client.get("/tiny-model-manager/api/catalog")
        entry = next(
            e for e in (await resp.json())["data"]["entries"] if e["source_page_id"] == "vidfirst"
        )
        assert entry["thumbnail_url"] == "/tmp/fallback.jpg"
        assert entry["is_video_only"] is False

    async def test_catalog_list_trigger_words_empty_when_none(self, client, ext_dir):
        await _make_entry()
        resp = await client.get("/tiny-model-manager/api/catalog")
        assert resp.status == 200
        entries = (await resp.json())["data"]["entries"]
        for entry in entries:
            assert "trigger_words" in entry
            assert isinstance(entry["trigger_words"], list)

    async def test_file_without_catalog_entry_is_unknown(self, client, ext_dir):
        import folder_paths

        loras_dir = folder_paths.folder_names_and_paths["loras"][0][0]
        fpath = os.path.join(loras_dir, "orphan.safetensors")
        Path(fpath).touch()

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

    async def test_repo_file_exposes_civitai_version_name_when_installed(self, client, ext_dir):
        from py.db import model_repo

        entry_id = await _make_entry(page_id="779")
        await model_repo.upsert_repo_files(
            entry_id,
            "loras",
            [
                {
                    "filename": "versioned.safetensors",
                    "size_bytes": 500,
                    "download_url": "https://example.com/versioned.safetensors",
                    "source_page_url": "https://civitai.com/models/779",
                }
            ],
        )
        await model_repo.upsert_model(
            "versioned.safetensors",
            "loras",
            "civitai",
            "779",
            "",
            civitai_version_name="v2 Turbo",
        )
        await model_repo.set_model_catalog_entry("versioned.safetensors", entry_id)

        resp = await client.get("/tiny-model-manager/api/catalog/civitai/779")
        data = (await resp.json())["data"]
        rf = data["repo_files"][0]
        assert rf["civitai_version_name"] == "v2 Turbo"

    async def test_repo_file_exposes_civitai_version_name_when_not_installed(self, client, ext_dir):
        from py.db import model_repo

        entry_id = await _make_entry(page_id="780")
        await model_repo.upsert_repo_files(
            entry_id,
            "loras",
            [
                {
                    "filename": "uninstalled.safetensors",
                    "size_bytes": 700,
                    "download_url": "https://example.com/uninstalled.safetensors",
                    "source_page_url": "https://civitai.com/models/780",
                    "civitai_version_name": "v1 Base",
                }
            ],
        )

        resp = await client.get("/tiny-model-manager/api/catalog/civitai/780")
        data = (await resp.json())["data"]
        rf = data["repo_files"][0]
        assert rf["is_downloaded"] is False
        assert rf["civitai_version_name"] == "v1 Base"

    async def test_is_downloaded_true_when_installed_in_subfolder(self, client, ext_dir):
        from py.db import model_repo

        entry_id = await _make_entry(page_id="778")
        await model_repo.upsert_repo_files(
            entry_id,
            "loras",
            [
                {
                    "filename": "model.safetensors",
                    "size_bytes": 1000,
                    "download_url": "https://example.com/model.safetensors",
                    "source_page_url": "https://civitai.com/models/778",
                }
            ],
        )
        # Simulate file installed in a base-model subfolder
        await model_repo.upsert_model(
            filename="Illustrious/model.safetensors",
            model_type="loras",
            source_platform="civitai",
            source_id="778",
            description="",
        )
        await model_repo.set_model_catalog_entry("Illustrious/model.safetensors", entry_id)

        resp = await client.get("/tiny-model-manager/api/catalog/civitai/778")
        data = (await resp.json())["data"]
        rf = data["repo_files"][0]
        assert rf["is_downloaded"] is True
        assert rf["installed_path"] == "Illustrious/model.safetensors"


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
        Path(media_path).touch()
        # Insert a model linked to this entry with media
        model_id = await model_repo.upsert_model(
            "linked.safetensors", "loras", "civitai", "456", ""
        )
        await model_repo.set_model_catalog_entry("linked.safetensors", entry_id)
        await model_repo.add_media(model_id, "image", media_path)

        await client.delete("/tiny-model-manager/api/catalog/civitai/111")
        assert not os.path.isfile(media_path)


class TestCatalogMetadata:
    async def test_get_returns_catalog_owned_metadata(self, client, ext_dir):
        from py.db import model_repo

        await model_repo.upsert_catalog_entry(
            source_platform="civitai",
            source_page_id="500",
            source_page_url="https://civitai.com/models/500",
            display_name="Meta Model",
            thumbnail_url="",
            base_model="Pony",
            description="A described model",
            trigger_words=["alpha", "beta"],
            tags=["anime"],
            media_hash="metahash",
        )
        resp = await client.get("/tiny-model-manager/api/catalog/civitai/500")
        assert resp.status == 200
        data = (await resp.json())["data"]
        assert data["description"] == "A described model"
        assert data["trigger_words"] == ["alpha", "beta"]
        assert data["tags"] == ["anime"]

    async def test_get_returns_gallery_from_media_hash_dir(self, client, ext_dir):
        from py import config as cfg
        from py.db import model_repo

        _base = os.path.realpath(cfg.media_dir())
        media_dir = os.path.realpath(os.path.join(_base, "gallhash"))
        assert media_dir.startswith(_base + os.sep)
        os.makedirs(media_dir, exist_ok=True)
        (Path(media_dir) / "0.jpg").touch()
        (Path(media_dir) / "1.mp4").touch()
        await model_repo.upsert_catalog_entry(
            source_platform="civitai",
            source_page_id="501",
            source_page_url="",
            display_name="Gallery",
            thumbnail_url="",
            base_model="",
            media_hash="gallhash",
        )
        resp = await client.get("/tiny-model-manager/api/catalog/civitai/501")
        media = (await resp.json())["data"]["media"]
        assert len(media) == 2
        assert media[0]["media_type"] == "image"
        assert media[1]["media_type"] == "video"

    async def test_gallery_survives_with_zero_installed_files(self, client, ext_dir):
        """The whole point: metadata + gallery still present when nothing is installed."""
        from py import config as cfg
        from py.db import model_repo

        _base = os.path.realpath(cfg.media_dir())
        media_dir = os.path.realpath(os.path.join(_base, "survivehash"))
        assert media_dir.startswith(_base + os.sep)
        os.makedirs(media_dir, exist_ok=True)
        (Path(media_dir) / "0.jpg").touch()
        await model_repo.upsert_catalog_entry(
            source_platform="civitai",
            source_page_id="502",
            source_page_url="",
            display_name="Survivor",
            thumbnail_url="",
            base_model="",
            description="still here",
            media_hash="survivehash",
        )
        resp = await client.get("/tiny-model-manager/api/catalog/civitai/502")
        data = (await resp.json())["data"]
        assert data["installed_files"] == []
        assert data["description"] == "still here"
        assert len(data["media"]) == 1

    async def test_put_metadata_updates_and_can_clear(self, client, ext_dir):
        from py.db import model_repo

        await model_repo.upsert_catalog_entry(
            source_platform="civitai",
            source_page_id="503",
            source_page_url="",
            display_name="Editable",
            thumbnail_url="",
            base_model="",
            description="old",
            trigger_words=["x"],
            tags=["t"],
        )
        resp = await client.put(
            "/tiny-model-manager/api/catalog/civitai/503/metadata",
            json={"description": "new", "trigger_words": ["a", "b"], "tags": []},
        )
        assert resp.status == 200
        entry = await model_repo.get_catalog_entry("civitai", "503")
        assert entry["description"] == "new"
        assert entry["trigger_words"] == ["a", "b"]
        assert entry["tags"] == []  # cleared

    async def test_put_metadata_returns_404_for_unknown_entry(self, client, ext_dir):
        resp = await client.put(
            "/tiny-model-manager/api/catalog/civitai/999999/metadata",
            json={"description": "x"},
        )
        assert resp.status == 404

    async def test_refetch_updates_catalog_from_source(self, client, ext_dir, monkeypatch):
        from py.db import model_repo

        await model_repo.upsert_catalog_entry(
            source_platform="huggingface",
            source_page_id="user/repo",
            source_page_url="https://huggingface.co/user/repo",
            display_name="HF Model",
            thumbnail_url="",
            base_model="",
        )

        async def fake_refetch(platform, page_id):
            await model_repo.update_catalog_metadata(
                platform, page_id, description="fetched desc", trigger_words=["fw"]
            )
            return await model_repo.get_catalog_entry(platform, page_id)

        monkeypatch.setattr("py.services.metadata_fetcher.refetch_catalog_metadata", fake_refetch)
        resp = await client.post("/tiny-model-manager/api/catalog/huggingface/user/repo/refetch")
        assert resp.status == 200
        data = (await resp.json())["data"]
        assert data["description"] == "fetched desc"
        assert data["trigger_words"] == ["fw"]

    async def test_refetch_response_annotates_repo_files(self, client, ext_dir, monkeypatch):
        """Regression: the refetch payload must carry the same per-file install state as
        GET, so the file list is accurate without a page refresh."""
        from py.db import model_repo

        entry_id = await model_repo.upsert_catalog_entry(
            source_platform="civitai",
            source_page_id="600",
            source_page_url="https://civitai.com/models/600",
            display_name="Annotated",
            thumbnail_url="",
            base_model="",
        )
        await model_repo.upsert_repo_files(
            entry_id,
            "loras",
            [
                {
                    "filename": "thefile.safetensors",
                    "size_bytes": 1000,
                    "download_url": "https://example.com/thefile.safetensors",
                    "source_page_url": "https://civitai.com/models/600",
                }
            ],
        )

        async def fake_refetch(platform, page_id):
            return await model_repo.get_catalog_entry(platform, page_id)

        monkeypatch.setattr("py.services.metadata_fetcher.refetch_catalog_metadata", fake_refetch)
        resp = await client.post("/tiny-model-manager/api/catalog/civitai/600/refetch")
        assert resp.status == 200
        data = (await resp.json())["data"]
        assert "is_empty" in data
        assert len(data["repo_files"]) == 1
        rf = data["repo_files"][0]
        assert rf["is_downloaded"] is False
        assert "installed_path" in rf


_UPLOAD_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


def _upload_form(*payloads: bytes):
    from aiohttp import FormData

    form = FormData()
    for i, payload in enumerate(payloads):
        form.add_field("files", payload, filename=f"pic{i}.png", content_type="image/png")
    return form


async def test_upload_catalog_media_appears_in_the_next_detail_read(client):
    await _make_entry()

    resp = await client.post(
        "/tiny-model-manager/api/catalog/civitai/123/media", data=_upload_form(_UPLOAD_PNG)
    )

    assert resp.status == 200
    media = (await resp.json())["media"]
    assert len(media) == 1
    assert media[0]["uploaded"] is True
    assert os.path.isfile(media[0]["local_path"])

    detail = await client.get("/tiny-model-manager/api/catalog/civitai/123")
    assert len((await detail.json())["data"]["media"]) == 1


async def test_upload_catalog_media_fills_an_empty_thumbnail(client):
    from py.db import model_repo

    await _make_entry()

    resp = await client.post(
        "/tiny-model-manager/api/catalog/civitai/123/media", data=_upload_form(_UPLOAD_PNG)
    )
    stored = (await resp.json())["media"][0]["local_path"]

    entry = await model_repo.get_catalog_entry("civitai", "123")
    assert entry["thumbnail_url"] == stored
    assert entry["media_hash"] != ""


async def test_upload_catalog_media_keeps_an_existing_thumbnail(client):
    from py.db import model_repo

    await _make_entry()
    await model_repo.set_catalog_media_fields("civitai", "123", thumbnail_url="/media/x/0.jpg")

    await client.post(
        "/tiny-model-manager/api/catalog/civitai/123/media", data=_upload_form(_UPLOAD_PNG)
    )

    entry = await model_repo.get_catalog_entry("civitai", "123")
    assert entry["thumbnail_url"] == "/media/x/0.jpg"


async def test_upload_catalog_media_404s_for_an_unknown_entry(client):
    resp = await client.post(
        "/tiny-model-manager/api/catalog/civitai/999/media", data=_upload_form(_UPLOAD_PNG)
    )

    assert resp.status == 404


async def test_upload_catalog_media_rejects_a_non_image(client):
    await _make_entry()

    resp = await client.post(
        "/tiny-model-manager/api/catalog/civitai/123/media",
        data=_upload_form(b"<html>not an image</html>"),
    )

    assert resp.status == 400


async def test_delete_catalog_media_removes_the_file_and_clears_the_thumbnail(client):
    from py.db import model_repo

    await _make_entry()
    upload = await client.post(
        "/tiny-model-manager/api/catalog/civitai/123/media", data=_upload_form(_UPLOAD_PNG)
    )
    stored = (await upload.json())["media"][0]["local_path"]

    resp = await client.delete(
        f"/tiny-model-manager/api/catalog/civitai/123/media/{os.path.basename(stored)}"
    )

    assert resp.status == 200
    assert (await resp.json())["media"] == []
    assert not os.path.exists(stored)
    entry = await model_repo.get_catalog_entry("civitai", "123")
    assert entry["thumbnail_url"] == ""


async def test_delete_catalog_media_refuses_a_name_that_is_not_an_upload(client):
    await _make_entry()

    resp = await client.delete("/tiny-model-manager/api/catalog/civitai/123/media/0.jpg")

    assert resp.status == 400


async def test_upload_catalog_media_rolls_back_on_invalid_second_file(client):
    """Failed multipart upload leaves earlier parts on disk (F-159 regression test)."""
    await _make_entry()

    resp = await client.post(
        "/tiny-model-manager/api/catalog/civitai/123/media",
        data=_upload_form(_UPLOAD_PNG, b"<html>not an image</html>"),
    )

    assert resp.status == 400
    # Verify nothing was stored on disk
    detail = await client.get("/tiny-model-manager/api/catalog/civitai/123")
    assert len((await detail.json())["data"]["media"]) == 0
