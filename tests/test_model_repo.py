"""Tests for py/db/model_repo.py — async CRUD helpers."""

import pytest


class TestUpsertModel:
    async def test_insert_returns_id(self, ext_dir):
        from py.db import model_repo

        mid = await model_repo.upsert_model(
            "m.safetensors", "checkpoints", "civitai", "123", "desc"
        )
        assert isinstance(mid, int)
        assert mid > 0

    async def test_upsert_updates_on_conflict(self, ext_dir):
        from py.db import model_repo

        id1 = await model_repo.upsert_model("m.safetensors", "checkpoints", "civitai", "123", "old")
        id2 = await model_repo.upsert_model("m.safetensors", "loras", "civitai", "999", "new")
        assert id1 == id2  # same row
        row = await model_repo.get_model_by_filename("m.safetensors")
        assert row["model_type"] == "loras"
        assert row["source_id"] == "999"
        assert row["description"] == "new"

    async def test_truncates_long_description(self, ext_dir):
        from py.db import model_repo
        from py.db.model_repo import _MAX_DESCRIPTION

        long_desc = "x" * (_MAX_DESCRIPTION + 100)
        await model_repo.upsert_model("m.safetensors", "checkpoints", "", "", long_desc)
        row = await model_repo.get_model_by_filename("m.safetensors")
        assert len(row["description"]) == _MAX_DESCRIPTION


class TestUpsertModelWithMeta:
    async def test_stores_trigger_words_and_tags(self, ext_dir):
        from py.db import model_repo

        await model_repo.upsert_model_with_meta(
            "lora.safetensors",
            "loras",
            "civitai",
            "555",
            "desc",
            trigger_words=["word1", "word2"],
            tags=["fantasy", "portrait"],
        )
        row = await model_repo.get_model_by_filename("lora.safetensors")
        assert set(row["trigger_words"]) == {"word1", "word2"}
        assert set(row["tags"]) == {"fantasy", "portrait"}

    async def test_upsert_replaces_trigger_words(self, ext_dir):
        from py.db import model_repo

        await model_repo.upsert_model_with_meta(
            "lora.safetensors",
            "loras",
            "civitai",
            "555",
            "desc",
            trigger_words=["old"],
            tags=[],
        )
        await model_repo.upsert_model_with_meta(
            "lora.safetensors",
            "loras",
            "civitai",
            "555",
            "desc",
            trigger_words=["new"],
            tags=[],
        )
        row = await model_repo.get_model_by_filename("lora.safetensors")
        assert row["trigger_words"] == ["new"]


class TestSetTriggerWords:
    async def test_replaces_words(self, ext_dir):
        from py.db import model_repo

        mid = await model_repo.upsert_model("t.safetensors", "loras", "", "", "")
        await model_repo.set_trigger_words(mid, ["a", "b"])
        row = await model_repo.get_model_by_filename("t.safetensors")
        assert set(row["trigger_words"]) == {"a", "b"}

    async def test_truncates_long_word(self, ext_dir):
        from py.db import model_repo
        from py.db.model_repo import _MAX_WORD

        mid = await model_repo.upsert_model("t.safetensors", "loras", "", "", "")
        long_word = "w" * (_MAX_WORD + 50)
        await model_repo.set_trigger_words(mid, [long_word])
        row = await model_repo.get_model_by_filename("t.safetensors")
        assert len(row["trigger_words"][0]) == _MAX_WORD


class TestSetTags:
    async def test_replaces_tags(self, ext_dir):
        from py.db import model_repo

        mid = await model_repo.upsert_model("t.safetensors", "loras", "", "", "")
        await model_repo.set_tags(mid, ["tag1", "tag2"])
        row = await model_repo.get_model_by_filename("t.safetensors")
        assert set(row["tags"]) == {"tag1", "tag2"}

    async def test_shared_tag_deduplicates_in_tags_table(self, ext_dir):
        """Two models sharing the same tag name produce a single row in the tags table."""
        import aiosqlite

        from py import config as cfg
        from py.db import model_repo

        mid1 = await model_repo.upsert_model("a.safetensors", "loras", "", "", "")
        mid2 = await model_repo.upsert_model("b.safetensors", "loras", "", "", "")
        await model_repo.set_tags(mid1, ["shared"])
        await model_repo.set_tags(mid2, ["shared"])

        async with aiosqlite.connect(cfg.db_path()) as db:
            cur = await db.execute("SELECT COUNT(*) FROM tags WHERE name = 'shared'")
            assert (await cur.fetchone())[0] == 1

    async def test_orphan_tag_pruned_after_unlink(self, ext_dir):
        """A tag name with no remaining model links is deleted from the tags table."""
        import aiosqlite

        from py import config as cfg
        from py.db import model_repo

        mid = await model_repo.upsert_model("c.safetensors", "loras", "", "", "")
        await model_repo.set_tags(mid, ["orphan"])
        await model_repo.set_tags(mid, [])  # remove the tag

        async with aiosqlite.connect(cfg.db_path()) as db:
            cur = await db.execute("SELECT COUNT(*) FROM tags WHERE name = 'orphan'")
            assert (await cur.fetchone())[0] == 0


class TestAddMedia:
    async def test_add_image_media(self, ext_dir):
        from py.db import model_repo

        mid = await model_repo.upsert_model("m.safetensors", "checkpoints", "", "", "")
        media_id = await model_repo.add_media(mid, "image", "/some/path/img.jpg")
        assert isinstance(media_id, int)
        row = await model_repo.get_model_by_filename("m.safetensors")
        assert len(row["media"]) == 1
        assert row["media"][0]["media_type"] == "image"

    async def test_add_video_media(self, ext_dir):
        from py.db import model_repo

        mid = await model_repo.upsert_model("m.safetensors", "checkpoints", "", "", "")
        await model_repo.add_media(mid, "video", "/some/path/vid.mp4")
        row = await model_repo.get_model_by_filename("m.safetensors")
        assert row["media"][0]["media_type"] == "video"

    async def test_invalid_media_type_raises(self, ext_dir):
        from py.db import model_repo

        mid = await model_repo.upsert_model("m.safetensors", "checkpoints", "", "", "")
        with pytest.raises(ValueError):
            await model_repo.add_media(mid, "audio", "/path/file.mp3")


class TestGetModelByFilename:
    async def test_returns_none_for_unknown(self, ext_dir):
        from py.db import model_repo

        assert await model_repo.get_model_by_filename("nonexistent.safetensors") is None

    async def test_returns_full_record(self, ext_dir):
        from py.db import model_repo

        await model_repo.upsert_model_with_meta(
            "full.safetensors",
            "checkpoints",
            "civitai",
            "42",
            "A description",
            ["tw1"],
            ["tag_a"],
            base_model="SDXL 1.0",
        )
        row = await model_repo.get_model_by_filename("full.safetensors")
        assert row is not None
        assert row["filename"] == "full.safetensors"
        assert row["base_model"] == "SDXL 1.0"
        assert "tw1" in row["trigger_words"]
        assert "tag_a" in row["tags"]


class TestGetMetadataByFilenames:
    async def test_returns_multiple(self, ext_dir):
        from py.db import model_repo

        await model_repo.upsert_model("a.safetensors", "checkpoints", "", "", "")
        await model_repo.upsert_model("b.safetensors", "loras", "", "", "")
        result = await model_repo.get_metadata_by_filenames(["a.safetensors", "b.safetensors"])
        assert "a.safetensors" in result
        assert "b.safetensors" in result

    async def test_empty_list_returns_empty_dict(self, ext_dir):
        from py.db import model_repo

        assert await model_repo.get_metadata_by_filenames([]) == {}


class TestUpdateModelMeta:
    async def test_updates_description_and_trigger_words(self, ext_dir):
        from py.db import model_repo

        await model_repo.upsert_model("u.safetensors", "loras", "", "", "old")
        await model_repo.update_model_meta("u.safetensors", "new desc", ["w1"], ["t1"])
        row = await model_repo.get_model_by_filename("u.safetensors")
        assert row["description"] == "new desc"
        assert "w1" in row["trigger_words"]

    async def test_updates_base_model_when_provided(self, ext_dir):
        from py.db import model_repo

        await model_repo.upsert_model("u.safetensors", "loras", "", "", "")
        await model_repo.update_model_meta("u.safetensors", "", [], base_model="Pony")
        row = await model_repo.get_model_by_filename("u.safetensors")
        assert row["base_model"] == "Pony"

    async def test_does_not_update_base_model_when_none(self, ext_dir):
        from py.db import model_repo

        await model_repo.upsert_model("u.safetensors", "loras", "", "", "", base_model="Flux.1 D")
        await model_repo.update_model_meta("u.safetensors", "desc", [], base_model=None)
        row = await model_repo.get_model_by_filename("u.safetensors")
        assert row["base_model"] == "Flux.1 D"

    async def test_creates_row_when_none_exists(self, ext_dir):
        from py.db import model_repo

        # No prior upsert — file has no models row
        await model_repo.update_model_meta(
            "new.safetensors", base_model="SDXL 1.0", model_type="loras"
        )
        row = await model_repo.get_model_by_filename("new.safetensors")
        assert row is not None
        assert row["base_model"] == "SDXL 1.0"

    async def test_omitted_fields_are_not_overwritten(self, ext_dir):
        from py.db import model_repo

        await model_repo.upsert_model_with_meta(
            "partial.safetensors", "loras", "", "", "orig desc", ["kw1"], [], base_model="Pony"
        )
        # Updating only base_model must not touch description or trigger_words
        await model_repo.update_model_meta("partial.safetensors", base_model="Flux.1 D")
        row = await model_repo.get_model_by_filename("partial.safetensors")
        assert row["description"] == "orig desc"
        assert "kw1" in row["trigger_words"]
        assert row["base_model"] == "Flux.1 D"

    async def test_updates_readme_html_when_provided(self, ext_dir):
        from py.db import model_repo

        await model_repo.upsert_model("readme.safetensors", "loras", "", "", "")
        await model_repo.update_model_meta("readme.safetensors", readme_html="<h1>Hello</h1>")
        row = await model_repo.get_model_by_filename("readme.safetensors")
        assert row["readme_html"] == "<h1>Hello</h1>"


class TestUpsertPreservesBaseModel:
    async def test_upsert_does_not_overwrite_existing_base_model_with_empty(self, ext_dir):
        from py.db import model_repo

        await model_repo.upsert_model(
            "hf.safetensors", "loras", "huggingface", "user/repo", "", base_model="Flux.1 D"
        )
        # Simulate HF refetch that returns no base_model
        await model_repo.upsert_model(
            "hf.safetensors", "loras", "huggingface", "user/repo", "new desc", base_model=""
        )
        row = await model_repo.get_model_by_filename("hf.safetensors")
        assert row["base_model"] == "Flux.1 D"  # preserved

    async def test_upsert_sets_base_model_when_previously_empty(self, ext_dir):
        from py.db import model_repo

        await model_repo.upsert_model("hf2.safetensors", "loras", "", "", "", base_model="")
        await model_repo.upsert_model("hf2.safetensors", "loras", "", "", "", base_model="SDXL 1.0")
        row = await model_repo.get_model_by_filename("hf2.safetensors")
        assert row["base_model"] == "SDXL 1.0"


class TestCascadeDelete:
    async def test_delete_model_cascades_to_child_rows(self, ext_dir):
        import aiosqlite

        from py import config as cfg
        from py.db import model_repo

        mid = await model_repo.upsert_model_with_meta(
            "del.safetensors",
            "loras",
            "",
            "",
            "desc",
            trigger_words=["tw"],
            tags=["t"],
        )
        await model_repo.add_media(mid, "image", "/p/img.jpg")

        async with aiosqlite.connect(cfg.db_path()) as db:
            await db.execute("PRAGMA foreign_keys = ON")
            await db.execute("DELETE FROM models WHERE id = ?", (mid,))
            await db.commit()
            cur = await db.execute("SELECT COUNT(*) FROM trigger_words WHERE model_id = ?", (mid,))
            assert (await cur.fetchone())[0] == 0
            cur = await db.execute("SELECT COUNT(*) FROM model_tags WHERE model_id = ?", (mid,))
            assert (await cur.fetchone())[0] == 0
            cur = await db.execute("SELECT COUNT(*) FROM model_media WHERE model_id = ?", (mid,))
            assert (await cur.fetchone())[0] == 0


class TestFieldSeparation:
    """F-32: base_model, trigger_words, and tags are stored as distinct first-class fields."""

    async def test_base_model_never_stored_in_tags(self, ext_dir):
        import aiosqlite

        from py import config as cfg
        from py.db import model_repo

        await model_repo.upsert_model_with_meta(
            "sep.safetensors",
            "loras",
            "civitai",
            "1",
            "desc",
            trigger_words=["word"],
            tags=["portrait"],
            base_model="SDXL 1.0",
        )
        async with aiosqlite.connect(cfg.db_path()) as db:
            cur = await db.execute("SELECT COUNT(*) FROM tags WHERE name = 'SDXL 1.0'")
            assert (await cur.fetchone())[0] == 0

    async def test_trigger_words_never_stored_in_tags(self, ext_dir):
        import aiosqlite

        from py import config as cfg
        from py.db import model_repo

        await model_repo.upsert_model_with_meta(
            "sep2.safetensors",
            "loras",
            "civitai",
            "2",
            "desc",
            trigger_words=["masterpiece", "best quality"],
            tags=["fantasy"],
            base_model="",
        )
        async with aiosqlite.connect(cfg.db_path()) as db:
            cur = await db.execute(
                "SELECT COUNT(*) FROM tags WHERE name IN ('masterpiece', 'best quality')"
            )
            assert (await cur.fetchone())[0] == 0

    async def test_get_model_returns_three_distinct_fields(self, ext_dir):
        from py.db import model_repo

        await model_repo.upsert_model_with_meta(
            "dist.safetensors",
            "loras",
            "civitai",
            "3",
            "desc",
            trigger_words=["tw1"],
            tags=["portrait"],
            base_model="Pony",
        )
        row = await model_repo.get_model_by_filename("dist.safetensors")
        assert row["base_model"] == "Pony"
        assert row["trigger_words"] == ["tw1"]
        assert row["tags"] == ["portrait"]
        assert "Pony" not in row["trigger_words"]
        assert "Pony" not in row["tags"]
        assert "tw1" not in row["tags"]
        assert "portrait" not in row["trigger_words"]


class TestUpdateModelType:
    async def test_updates_type(self, ext_dir):
        from py.db import model_repo

        await model_repo.upsert_model("move.safetensors", "checkpoints", "", "", "")
        await model_repo.update_model_type("move.safetensors", "loras")
        row = await model_repo.get_model_by_filename("move.safetensors")
        assert row["model_type"] == "loras"


class TestGetModelSourceInfo:
    async def test_returns_source_info(self, ext_dir):
        from py.db import model_repo

        await model_repo.upsert_model("src.safetensors", "loras", "civitai", "777", "")
        info = await model_repo.get_model_source_info("src.safetensors")
        assert info["source_platform"] == "civitai"
        assert info["source_id"] == "777"

    async def test_returns_none_for_unknown(self, ext_dir):
        from py.db import model_repo

        assert await model_repo.get_model_source_info("nope.safetensors") is None


class TestRepoFiles:
    _FILES = [
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

    async def _make_entry(self, source_page_id: str = "1") -> int:
        from py.db import model_repo

        return await model_repo.upsert_catalog_entry(
            source_platform="civitai",
            source_page_id=source_page_id,
            source_page_url=f"https://civitai.com/models/{source_page_id}",
            display_name="Test",
            thumbnail_url="",
            base_model="",
        )

    async def test_upsert_and_get(self, ext_dir):
        from py.db import model_repo

        eid = await self._make_entry("1")
        await model_repo.upsert_repo_files(eid, "loras", self._FILES)
        rows = await model_repo.get_repo_files_by_catalog(eid)
        assert len(rows) == 2
        filenames = {r["filename"] for r in rows}
        assert filenames == {"model-fp16.safetensors", "vae.safetensors"}

    async def test_upsert_is_idempotent(self, ext_dir):
        from py.db import model_repo

        eid = await self._make_entry("2")
        await model_repo.upsert_repo_files(eid, "loras", self._FILES)
        await model_repo.upsert_repo_files(eid, "loras", self._FILES)
        rows = await model_repo.get_repo_files_by_catalog(eid)
        assert len(rows) == 2

    async def test_upsert_updates_size_on_conflict(self, ext_dir):
        from py.db import model_repo

        eid = await self._make_entry("3")
        await model_repo.upsert_repo_files(eid, "loras", self._FILES)
        updated = [{**self._FILES[0], "size_bytes": 999}]
        await model_repo.upsert_repo_files(eid, "loras", updated)
        rows = await model_repo.get_repo_files_by_catalog(eid)
        fp16 = next(r for r in rows if r["filename"] == "model-fp16.safetensors")
        assert fp16["size_bytes"] == 999

    async def test_get_returns_empty_for_unknown_catalog_entry(self, ext_dir):
        from py.db import model_repo

        rows = await model_repo.get_repo_files_by_catalog(99999)
        assert rows == []

    async def test_scoped_by_catalog_entry(self, ext_dir):
        from py.db import model_repo

        eid_loras = await self._make_entry("lora-source")
        eid_ckpts = await self._make_entry("ckpt-source")
        await model_repo.upsert_repo_files(eid_loras, "loras", [self._FILES[0]])
        await model_repo.upsert_repo_files(eid_ckpts, "checkpoints", [self._FILES[1]])
        lora_rows = await model_repo.get_repo_files_by_catalog(eid_loras)
        ckpt_rows = await model_repo.get_repo_files_by_catalog(eid_ckpts)
        assert len(lora_rows) == 1
        assert lora_rows[0]["filename"] == "model-fp16.safetensors"
        assert len(ckpt_rows) == 1
        assert ckpt_rows[0]["filename"] == "vae.safetensors"

    async def test_get_repo_files_by_model_path_uses_catalog_entry(self, ext_dir):
        """get_repo_files(type, path) delegates to the model's catalog_entry_id."""
        from py.db import model_repo

        eid = await self._make_entry("5")
        await model_repo.upsert_repo_files(eid, "loras", self._FILES)
        # Link a model to this catalog entry
        await model_repo.upsert_model("my-lora.safetensors", "loras", "civitai", "100", "")
        await model_repo.set_model_catalog_entry("my-lora.safetensors", eid)
        rows = await model_repo.get_repo_files("loras", "my-lora.safetensors")
        assert len(rows) == 2

    async def test_get_repo_files_returns_empty_without_catalog_link(self, ext_dir):
        from py.db import model_repo

        await model_repo.upsert_model("orphan.safetensors", "loras", "", "", "")
        rows = await model_repo.get_repo_files("loras", "orphan.safetensors")
        assert rows == []
