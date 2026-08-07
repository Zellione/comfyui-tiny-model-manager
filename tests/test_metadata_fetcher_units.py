"""Unit tests for metadata_fetcher retry, catalog-entry storage and media migration."""

import os
from unittest.mock import AsyncMock, patch

import pytest

from py.db import model_repo
from py.services.metadata_fetcher import (
    _compute_media_hash,
    _store_catalog_entry,
    fetch_metadata_only,
    migrate_existing_media,
)
from py.services.providers.base import ProviderMetadata


class TestFetchMetadataOnly:
    async def test_unknown_platform_raises(self, ext_dir):
        with pytest.raises(RuntimeError, match="Unknown platform"):
            await fetch_metadata_only("nope", "1")

    async def test_retries_then_succeeds(self, ext_dir):
        meta = ProviderMetadata(display_name="Retried Model")
        provider = AsyncMock()
        provider.fetch_metadata = AsyncMock(side_effect=[RuntimeError("flaky"), meta])

        with patch("py.services.metadata_fetcher.get_provider", return_value=provider):
            result = await fetch_metadata_only("civitai", "42")

        assert result is meta
        assert provider.fetch_metadata.await_count == 2

    async def test_raises_after_three_failures(self, ext_dir):
        provider = AsyncMock()
        provider.fetch_metadata = AsyncMock(side_effect=RuntimeError("down"))

        with (
            patch("py.services.metadata_fetcher.get_provider", return_value=provider),
            pytest.raises(RuntimeError, match="down"),
        ):
            await fetch_metadata_only("civitai", "42")

        assert provider.fetch_metadata.await_count == 3


class TestStoreCatalogEntry:
    async def test_upserts_and_links_model(self, ext_dir):
        model_id = await model_repo.upsert_model("cat.safetensors", "loras", "", "", "")
        meta = ProviderMetadata(
            display_name="Catalog Model",
            base_model="SDXL 1.0",
            description="desc",
            trigger_words=["tw"],
            tags=["tag"],
        )

        entry_id = await _store_catalog_entry(
            filename="cat.safetensors",
            platform="civitai",
            source_page_id="7",
            source_page_url="https://civitai.com/models/7",
            media_hash="abc123",
            model_id=model_id,
            meta=meta,
        )

        assert entry_id > 0
        row = await model_repo.get_model_by_filename("cat.safetensors")
        assert row["catalog_entry_id"] == entry_id

    async def test_returns_zero_on_failure(self, ext_dir):
        model_id = await model_repo.upsert_model("bad.safetensors", "loras", "", "", "")

        with patch(
            "py.db.model_repo.upsert_catalog_entry", AsyncMock(side_effect=RuntimeError("db"))
        ):
            entry_id = await _store_catalog_entry(
                filename="bad.safetensors",
                platform="civitai",
                source_page_id="8",
                source_page_url="https://civitai.com/models/8",
                media_hash="def456",
                model_id=model_id,
                meta=ProviderMetadata(display_name="X"),
            )

        assert entry_id == 0


class TestMigrateExistingMedia:
    async def test_moves_media_into_hash_dir_and_updates_db(self, ext_dir):
        from py import config as cfg

        model_id = await model_repo.upsert_model("mig.safetensors", "loras", "civitai", "55", "")
        old_dir = os.path.join(cfg.media_dir(), "mig")
        os.makedirs(old_dir, exist_ok=True)
        old_path = os.path.join(old_dir, "preview.jpg")
        with open(old_path, "wb") as fh:
            fh.write(b"img")
        await model_repo.add_media(model_id, "image", old_path)

        await migrate_existing_media()

        media_hash = _compute_media_hash("civitai", "55", "mig.safetensors")
        new_path = os.path.join(cfg.media_dir(), media_hash, "preview.jpg")
        assert os.path.isfile(new_path)
        assert not os.path.exists(old_path)
        assert not os.path.exists(old_dir), "emptied old dir should be removed"
        row = await model_repo.get_model_by_filename("mig.safetensors")
        assert row["media_hash"] == media_hash
        assert [m["local_path"] for m in row["media"]] == [new_path]

    async def test_missing_file_updates_db_without_moving(self, ext_dir):
        from py import config as cfg

        model_id = await model_repo.upsert_model("ghost.safetensors", "loras", "civitai", "56", "")
        phantom = os.path.join(cfg.media_dir(), "ghost", "gone.jpg")
        await model_repo.add_media(model_id, "image", phantom)

        await migrate_existing_media()

        media_hash = _compute_media_hash("civitai", "56", "ghost.safetensors")
        row = await model_repo.get_model_by_filename("ghost.safetensors")
        assert row["media_hash"] == media_hash
        expected = os.path.join(cfg.media_dir(), media_hash, "gone.jpg")
        assert [m["local_path"] for m in row["media"]] == [expected]
