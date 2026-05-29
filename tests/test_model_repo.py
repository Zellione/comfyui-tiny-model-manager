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
            cur = await db.execute("SELECT COUNT(*) FROM tags WHERE model_id = ?", (mid,))
            assert (await cur.fetchone())[0] == 0
            cur = await db.execute("SELECT COUNT(*) FROM model_media WHERE model_id = ?", (mid,))
            assert (await cur.fetchone())[0] == 0


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
