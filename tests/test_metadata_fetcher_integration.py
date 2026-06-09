"""Integration tests for metadata_fetcher: retry logic and subfolder organization."""

import os
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
        urls = ["https://example.com/image.jpg"]

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
