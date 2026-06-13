"""Integration tests for metadata_fetcher: retry logic and subfolder organization."""

import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest


@pytest.fixture()
def loras_dir(ext_dir):
    import folder_paths

    d = os.path.join(ext_dir, "models", "loras")
    os.makedirs(d, exist_ok=True)
    folder_paths.folder_names_and_paths["loras"] = ([d], {".safetensors"})
    return d


def _make_meta(base_model: str = "SDXL 1.0") -> MagicMock:
    meta = MagicMock()
    meta.description = "desc"
    meta.trigger_words = []
    meta.image_urls = []
    meta.tags = []
    meta.base_model = base_model
    meta.civitai_model_id = ""
    meta.civitai_version_name = ""
    meta.readme_html = ""
    meta.display_name = ""
    return meta


class TestSanitizeSubfolderName:
    def test_clean_name_unchanged(self):
        from py.services.reorganizer import _sanitize_subfolder_name

        assert _sanitize_subfolder_name("SDXL 1.0") == "SDXL 1.0"

    def test_empty_returns_unknown(self):
        from py.services.reorganizer import _sanitize_subfolder_name

        assert _sanitize_subfolder_name("") == "Unknown"

    def test_invalid_chars_replaced(self):
        from py.services.reorganizer import _sanitize_subfolder_name

        assert _sanitize_subfolder_name('SD:XL "1.0"') == "SD_XL _1.0_"

    def test_all_whitespace_returns_unknown(self):
        from py.services.reorganizer import _sanitize_subfolder_name

        assert _sanitize_subfolder_name("   ") == "Unknown"

    def test_only_dots_returns_unknown(self):
        from py.services.reorganizer import _sanitize_subfolder_name

        assert _sanitize_subfolder_name("...") == "Unknown"

    def test_truncates_long_name(self):
        from py.services.reorganizer import _sanitize_subfolder_name

        long = "x" * 200
        result = _sanitize_subfolder_name(long)
        assert len(result) == 100


class TestFetchAndStoreOrganize:
    async def test_moves_file_to_base_model_subfolder_when_enabled(self, ext_dir, loras_dir):
        from py import config as cfg
        from py.services import backend_notifier
        from py.services.metadata_fetcher import fetch_and_store

        backend_notifier._pending.clear()
        cfg.save_settings({"organize_into_subfolders": True})

        model_file = os.path.join(loras_dir, "my-lora.safetensors")
        open(model_file, "wb").close()

        mock_provider = AsyncMock()
        mock_provider.fetch_metadata = AsyncMock(return_value=_make_meta("SDXL 1.0"))

        with patch("py.services.metadata_fetcher.get_provider", return_value=mock_provider):
            await fetch_and_store("my-lora.safetensors", "loras", "civitai", "123", skip_media=True)

        expected = os.path.join(loras_dir, "SDXL 1.0", "my-lora.safetensors")
        assert os.path.exists(expected), "File should be moved to base-model subfolder"
        assert not os.path.exists(model_file), "Original file should no longer exist"

        # Cleanup
        if os.path.exists(expected):
            os.remove(expected)

    async def test_does_not_move_when_setting_disabled(self, ext_dir, loras_dir):
        from py import config as cfg
        from py.services.metadata_fetcher import fetch_and_store

        cfg.save_settings({"organize_into_subfolders": False})

        model_file = os.path.join(loras_dir, "my-lora.safetensors")
        open(model_file, "wb").close()

        mock_provider = AsyncMock()
        mock_provider.fetch_metadata = AsyncMock(return_value=_make_meta("SDXL 1.0"))

        with patch("py.services.metadata_fetcher.get_provider", return_value=mock_provider):
            await fetch_and_store("my-lora.safetensors", "loras", "civitai", "123", skip_media=True)

        assert os.path.exists(model_file), "File should not be moved when setting is disabled"

        # Cleanup
        if os.path.exists(model_file):
            os.remove(model_file)

    async def test_retries_3_times_on_failure_then_shows_error_toast(self, ext_dir, loras_dir):
        from py import config as cfg
        from py.services import backend_notifier
        from py.services.metadata_fetcher import fetch_and_store

        backend_notifier._pending.clear()
        cfg.save_settings({"organize_into_subfolders": True})

        model_file = os.path.join(loras_dir, "failed-lora.safetensors")
        open(model_file, "wb").close()

        mock_provider = AsyncMock()
        mock_provider.fetch_metadata = AsyncMock(side_effect=Exception("API timeout"))

        with (
            patch("py.services.metadata_fetcher.get_provider", return_value=mock_provider),
            patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
        ):
            await fetch_and_store(
                "failed-lora.safetensors", "loras", "civitai", "123", skip_media=True
            )

        assert mock_provider.fetch_metadata.call_count == 3, "Should retry exactly 3 times"
        assert mock_sleep.call_count == 2, "Should sleep between retries (not after last)"

        notifications = backend_notifier._pending
        assert len(notifications) == 1
        assert notifications[0]["type"] == "error"
        assert "failed-lora.safetensors" in notifications[0]["message"]

        # File should be moved to Unknown/ since base_model is empty after all retries fail
        expected = os.path.join(loras_dir, "Unknown", "failed-lora.safetensors")
        assert os.path.exists(expected), "File should be moved to Unknown/ on metadata failure"
        assert not os.path.exists(model_file)

        # Cleanup
        if os.path.exists(expected):
            os.remove(expected)


class TestDownloadImagesIdempotency:
    async def test_second_call_skips_existing_files(self, ext_dir):
        """_download_images must not re-download or add duplicate DB rows for files already on disk."""
        from py import config as cfg
        from py.db import model_repo
        from py.services.metadata_fetcher import _download_images

        model_id = await model_repo.upsert_model_with_meta(
            "idem.safetensors",
            "loras",
            "civitai",
            "1",
            "desc",
            trigger_words=[],
            tags=[],
        )
        media_hash = "testhash_idem"
        urls = ["https://image.civitai.com/abc/image.jpg"]

        request_count = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal request_count
            request_count += 1
            return httpx.Response(200, content=b"\xff\xd8\xff")

        transport = httpx.MockTransport(handler)
        orig = httpx.AsyncClient
        with patch.object(httpx, "AsyncClient", lambda **kw: orig(transport=transport, **kw)):
            await _download_images(model_id, media_hash, urls)
            first_count = request_count
            await _download_images(model_id, media_hash, urls)

        assert first_count == 1, "First call should make exactly 1 HTTP request"
        assert request_count == 1, "Second call must not make any HTTP requests"

        row = await model_repo.get_model_by_filename("idem.safetensors")
        assert row is not None
        assert len(row.get("media", [])) == 1, "Only one media row should exist after two calls"

        # Cleanup
        dest_dir = os.path.join(cfg.media_dir(), media_hash)
        if os.path.isdir(dest_dir):
            import shutil

            shutil.rmtree(dest_dir)


class TestDownloadCatalogImages:
    """_download_catalog_images must return the first image path and skip videos."""

    def _make_transport(self, responses: list[tuple[bytes, str]]) -> httpx.MockTransport:
        """Each entry is (content, content-type) served in sequence."""
        calls = iter(responses)

        def handler(request: httpx.Request) -> httpx.Response:
            content, ct = next(calls)
            return httpx.Response(200, content=content, headers={"content-type": ct})

        return httpx.MockTransport(handler)

    async def test_returns_first_image_when_first_url_is_image(self, ext_dir):
        from py import config as cfg
        from py.services.metadata_fetcher import _download_catalog_images

        transport = self._make_transport([(b"\xff\xd8\xff", "image/jpeg")])
        orig = httpx.AsyncClient
        with patch.object(httpx, "AsyncClient", lambda **kw: orig(transport=transport, **kw)):
            path = await _download_catalog_images(
                "hash_img_first", ["https://image.civitai.com/1.jpg"]
            )

        assert path != "", "should return the image path"
        assert not path.lower().endswith((".mp4", ".webm", ".mov"))
        import shutil

        shutil.rmtree(os.path.join(cfg.media_dir(), "hash_img_first"), ignore_errors=True)

    async def test_skips_video_and_returns_first_image(self, ext_dir):
        from py import config as cfg
        from py.services.metadata_fetcher import _download_catalog_images

        transport = self._make_transport(
            [
                (b"\x00\x00\x00\x18ftyp", "video/mp4"),
                (b"\xff\xd8\xff", "image/jpeg"),
            ]
        )
        orig = httpx.AsyncClient
        with patch.object(httpx, "AsyncClient", lambda **kw: orig(transport=transport, **kw)):
            path = await _download_catalog_images(
                "hash_video_skip",
                ["https://image.civitai.com/1.mp4", "https://image.civitai.com/2.jpg"],
            )

        assert path != "", "should return second (image) path when first is a video"
        assert not path.lower().endswith(".mp4"), "returned path must not be a video"
        import shutil

        shutil.rmtree(os.path.join(cfg.media_dir(), "hash_video_skip"), ignore_errors=True)

    async def test_returns_empty_when_all_urls_are_videos_and_no_ffmpeg(self, ext_dir):
        from py import config as cfg
        from py.services.metadata_fetcher import _download_catalog_images

        transport = self._make_transport(
            [
                (b"\x00\x00\x00\x18ftyp", "video/mp4"),
                (b"\x1aE\xdf\xa3", "video/webm"),
            ]
        )
        orig = httpx.AsyncClient
        with (
            patch.object(httpx, "AsyncClient", lambda **kw: orig(transport=transport, **kw)),
            patch("py.video_poster.shutil.which", return_value=None),
        ):
            path = await _download_catalog_images(
                "hash_all_video",
                ["https://image.civitai.com/1.mp4", "https://image.civitai.com/2.webm"],
            )

        assert path == "", (
            "should return empty string when all media items are videos and no ffmpeg"
        )
        import shutil

        shutil.rmtree(os.path.join(cfg.media_dir(), "hash_all_video"), ignore_errors=True)

    async def test_returns_poster_when_all_urls_are_videos_and_ffmpeg_available(self, ext_dir):
        from py import config as cfg
        from py.services.metadata_fetcher import _download_catalog_images

        transport = self._make_transport([(b"\x00\x00\x00\x18ftyp", "video/mp4")])
        orig = httpx.AsyncClient
        with (
            patch.object(httpx, "AsyncClient", lambda **kw: orig(transport=transport, **kw)),
            patch("py.video_poster.shutil.which", return_value="/usr/bin/ffmpeg"),
            patch("py.video_poster.subprocess.run") as mock_run,
        ):
            # Simulate ffmpeg writing the poster file
            def fake_ffmpeg(cmd, **_kw):
                poster_path = cmd[cmd.index("-q:v") + 2]
                Path(poster_path).write_bytes(b"\xff\xd8\xff")
                return type("R", (), {"returncode": 0})()

            mock_run.side_effect = fake_ffmpeg
            path = await _download_catalog_images(
                "hash_all_video_ffmpeg",
                ["https://image.civitai.com/1.mp4"],
            )

        assert path.endswith("_poster.jpg"), "should return the extracted poster path"
        import shutil

        shutil.rmtree(os.path.join(cfg.media_dir(), "hash_all_video_ffmpeg"), ignore_errors=True)


class TestFetchRepoFilesAllVersions:
    _MODEL_DATA = {
        "type": "LORA",
        "modelVersions": [
            {
                "id": 200,
                "files": [
                    {
                        "name": "model-v2-fp16.safetensors",
                        "type": "Model",
                        "sizeKB": 512,
                        "downloadUrl": "https://civitai.com/dl/v2-fp16",
                    },
                    {
                        "name": "dataset.zip",
                        "type": "Training Data",
                        "sizeKB": 100,
                        "downloadUrl": "https://civitai.com/dl/v2-data",
                    },
                ],
            },
            {
                "id": 100,
                "files": [
                    {
                        "name": "model-v1.safetensors",
                        "type": "Model",
                        "sizeKB": 1024,
                        "downloadUrl": "https://civitai.com/dl/v1",
                    },
                ],
            },
        ],
    }

    def _make_civitai_mock(self, versions):
        mock_cls = MagicMock()
        instance = AsyncMock()
        instance.get_model_versions = AsyncMock(
            return_value={"versions": versions, "model_type": "loras"}
        )
        mock_cls.return_value = instance
        return mock_cls, instance

    async def _make_catalog_entry(self, source_page_id: str) -> int:
        from py.db import model_repo

        return await model_repo.upsert_catalog_entry(
            source_platform="civitai",
            source_page_id=source_page_id,
            source_page_url=f"https://civitai.com/models/{source_page_id}",
            display_name="Test",
            thumbnail_url="",
            base_model="SDXL",
        )

    async def test_stores_files_from_all_versions(self, ext_dir):
        from py.db import model_repo
        from py.services.metadata_fetcher import _fetch_and_store_repo_files

        catalog_entry_id = await self._make_catalog_entry("42")
        mock_cls, _ = self._make_civitai_mock(self._MODEL_DATA["modelVersions"])
        with patch("py.services.providers.civitai_provider.CivitaiProvider", mock_cls):
            await _fetch_and_store_repo_files(
                "all-versions.safetensors",
                "loras",
                "civitai",
                "100",
                civitai_model_id="42",
                catalog_entry_id=catalog_entry_id,
            )

        files = await model_repo.get_repo_files_by_catalog(catalog_entry_id)
        filenames = {f["filename"] for f in files}
        assert "model-v2-fp16.safetensors" in filenames
        assert "model-v1.safetensors" in filenames
        assert "dataset.zip" not in filenames

    async def test_source_page_url_includes_version_id(self, ext_dir):
        from py.db import model_repo
        from py.services.metadata_fetcher import _fetch_and_store_repo_files

        catalog_entry_id = await self._make_catalog_entry("43")
        mock_cls, _ = self._make_civitai_mock(self._MODEL_DATA["modelVersions"])
        with patch("py.services.providers.civitai_provider.CivitaiProvider", mock_cls):
            await _fetch_and_store_repo_files(
                "version-url.safetensors",
                "loras",
                "civitai",
                "100",
                civitai_model_id="43",
                catalog_entry_id=catalog_entry_id,
            )

        files = await model_repo.get_repo_files_by_catalog(catalog_entry_id)
        v2_file = next(f for f in files if f["filename"] == "model-v2-fp16.safetensors")
        assert "modelVersionId=200" in v2_file["source_page_url"]
        v1_file = next(f for f in files if f["filename"] == "model-v1.safetensors")
        assert "modelVersionId=100" in v1_file["source_page_url"]

    async def test_falls_back_to_version_files_without_model_id(self, ext_dir):
        from py.db import model_repo
        from py.services.metadata_fetcher import _fetch_and_store_repo_files

        catalog_entry_id = await self._make_catalog_entry("44")
        mock_cls = MagicMock()
        instance = AsyncMock()
        instance.get_version_files = AsyncMock(
            return_value=[
                {
                    "filename": "fallback.safetensors",
                    "size_bytes": 1024,
                    "download_url": "https://civitai.com/dl/fallback",
                    "source_page_url": "https://civitai.com/models/42",
                }
            ]
        )
        mock_cls.return_value = instance
        with patch("py.services.providers.civitai_provider.CivitaiProvider", mock_cls):
            await _fetch_and_store_repo_files(
                "fallback.safetensors",
                "loras",
                "civitai",
                "100",
                civitai_model_id="",
                catalog_entry_id=catalog_entry_id,
            )

        files = await model_repo.get_repo_files_by_catalog(catalog_entry_id)
        assert any(f["filename"] == "fallback.safetensors" for f in files)


class TestRefetchCatalogMetadata:
    async def test_hf_updates_readme_html(self, ext_dir):
        """F-80: refetch_catalog_metadata persists readme_html from provider."""
        from py.db import model_repo
        from py.services.metadata_fetcher import refetch_catalog_metadata
        from py.services.providers.base import ProviderMetadata

        await model_repo.upsert_catalog_entry(
            source_platform="huggingface",
            source_page_id="user/repo",
            source_page_url="https://huggingface.co/user/repo",
            display_name="Test",
            thumbnail_url="",
            base_model="",
        )

        mock_meta = ProviderMetadata(
            description="desc",
            trigger_words=[],
            image_urls=[],
            tags=[],
            display_name="Test",
            readme_html="<h1>Hello</h1>",
        )
        mock_provider = AsyncMock()
        mock_provider.fetch_metadata = AsyncMock(return_value=mock_meta)

        with patch("py.services.metadata_fetcher.get_provider", return_value=mock_provider):
            result = await refetch_catalog_metadata("huggingface", "user/repo")

        assert result is not None
        assert result["readme_html"] == "<h1>Hello</h1>"

    async def test_unknown_platform_returns_none(self, ext_dir):
        from py.services.metadata_fetcher import refetch_catalog_metadata

        result = await refetch_catalog_metadata("unknown", "some/id")
        assert result is None

    async def test_civitai_updates_version_names_on_refetch(self, ext_dir, loras_dir):
        """F-96: refetch_catalog_metadata updates civitai_version_name for installed files."""
        from unittest.mock import AsyncMock, MagicMock, patch

        from py.db import model_repo
        from py.services.metadata_fetcher import refetch_catalog_metadata
        from py.services.providers.base import ProviderMetadata

        catalog_id = await model_repo.upsert_catalog_entry(
            source_platform="civitai",
            source_page_id="77",
            source_page_url="https://civitai.com/models/77",
            display_name="Test",
            thumbnail_url="",
            base_model="SDXL",
        )
        await model_repo.upsert_model_with_meta(
            "refetch-lora.safetensors",
            "loras",
            "civitai",
            "300",
            "desc",
            trigger_words=[],
            tags=[],
        )
        await model_repo.set_model_catalog_entry("refetch-lora.safetensors", catalog_id)

        mock_civitai_cls = MagicMock()
        mock_civitai_inst = AsyncMock()
        mock_civitai_inst.get_model_versions = AsyncMock(
            return_value={"versions": [{"id": 300, "name": "Refetch V2"}], "model_type": "loras"}
        )
        mock_civitai_cls.return_value = mock_civitai_inst

        mock_provider = AsyncMock()
        mock_provider.fetch_metadata = AsyncMock(
            return_value=ProviderMetadata(description="", trigger_words=[], image_urls=[], tags=[])
        )

        with (
            patch("py.services.providers.civitai_provider.CivitaiProvider", mock_civitai_cls),
            patch("py.services.metadata_fetcher.get_provider", return_value=mock_provider),
        ):
            result = await refetch_catalog_metadata("civitai", "77")

        assert result is not None
        installed = result["installed_files"]
        assert len(installed) == 1
        assert installed[0]["civitai_version_name"] == "Refetch V2"

    async def test_civitai_refetch_updates_repo_file_version_names(self, ext_dir):
        """Refetch writes civitai_version_name into repo_files for non-installed files."""
        from unittest.mock import AsyncMock, MagicMock, patch

        from py.db import model_repo
        from py.services.metadata_fetcher import refetch_catalog_metadata
        from py.services.providers.base import ProviderMetadata

        catalog_id = await model_repo.upsert_catalog_entry(
            source_platform="civitai",
            source_page_id="88",
            source_page_url="https://civitai.com/models/88",
            display_name="RF Version Test",
            thumbnail_url="",
            base_model="",
        )
        await model_repo.upsert_repo_files(
            catalog_id,
            "loras",
            [
                {
                    "filename": "rf.safetensors",
                    "size_bytes": 512,
                    "download_url": "https://example.com/rf.safetensors",
                    "source_page_url": "https://civitai.com/models/88",
                }
            ],
        )

        mock_civitai_cls = MagicMock()
        mock_civitai_inst = AsyncMock()
        mock_civitai_inst.get_model_versions = AsyncMock(
            return_value={
                "versions": [
                    {
                        "id": 99,
                        "name": "v1 Test",
                        "files": [
                            {
                                "type": "Model",
                                "name": "rf.safetensors",
                                "sizeKB": 0.5,
                                "downloadUrl": "https://example.com/rf.safetensors",
                            }
                        ],
                    }
                ]
            }
        )
        mock_civitai_cls.return_value = mock_civitai_inst

        mock_provider = AsyncMock()
        mock_provider.fetch_metadata = AsyncMock(
            return_value=ProviderMetadata(description="", trigger_words=[], image_urls=[], tags=[])
        )

        with (
            patch("py.services.providers.civitai_provider.CivitaiProvider", mock_civitai_cls),
            patch("py.services.metadata_fetcher.get_provider", return_value=mock_provider),
        ):
            result = await refetch_catalog_metadata("civitai", "88")

        assert result is not None
        rf = result["repo_files"][0]
        assert rf["civitai_version_name"] == "v1 Test"


class TestCivitaiVersionName:
    async def test_fetch_and_store_persists_civitai_version_name(self, ext_dir, loras_dir):
        """F-96: civitai_version_name from ProviderMetadata is stored in the models table."""
        import os
        from unittest.mock import AsyncMock, patch

        from py.db import model_repo
        from py.services.metadata_fetcher import fetch_and_store

        model_file = os.path.join(loras_dir, "versioned-lora.safetensors")
        open(model_file, "wb").close()

        meta = _make_meta("SDXL 1.0")
        meta.civitai_version_name = "V5.1 (VAE)"

        mock_provider = AsyncMock()
        mock_provider.fetch_metadata = AsyncMock(return_value=meta)

        with patch("py.services.metadata_fetcher.get_provider", return_value=mock_provider):
            await fetch_and_store(
                "versioned-lora.safetensors", "loras", "civitai", "999", skip_media=True
            )

        stored = await model_repo.get_model_by_filename("versioned-lora.safetensors")
        assert stored is not None
        assert stored["civitai_version_name"] == "V5.1 (VAE)"
