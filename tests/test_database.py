"""Tests for py/db/database.py — schema creation and migrations."""

import aiosqlite


class TestInitDb:
    async def test_creates_models_table(self, ext_dir):
        from py import config as cfg

        async with aiosqlite.connect(cfg.db_path()) as db:
            cur = await db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='models'"
            )
            assert await cur.fetchone() is not None

    async def test_creates_trigger_words_table(self, ext_dir):
        from py import config as cfg

        async with aiosqlite.connect(cfg.db_path()) as db:
            cur = await db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='trigger_words'"
            )
            assert await cur.fetchone() is not None

    async def test_creates_model_media_table(self, ext_dir):
        from py import config as cfg

        async with aiosqlite.connect(cfg.db_path()) as db:
            cur = await db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='model_media'"
            )
            assert await cur.fetchone() is not None

    async def test_creates_tags_table(self, ext_dir):
        from py import config as cfg

        async with aiosqlite.connect(cfg.db_path()) as db:
            cur = await db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='tags'"
            )
            assert await cur.fetchone() is not None

    async def test_models_table_has_base_model_column(self, ext_dir):
        from py import config as cfg

        async with aiosqlite.connect(cfg.db_path()) as db:
            cur = await db.execute("PRAGMA table_info(models)")
            cols = [row[1] for row in await cur.fetchall()]
            assert "base_model" in cols

    async def test_models_table_has_media_hash_column(self, ext_dir):
        from py import config as cfg

        async with aiosqlite.connect(cfg.db_path()) as db:
            cur = await db.execute("PRAGMA table_info(models)")
            cols = [row[1] for row in await cur.fetchall()]
            assert "media_hash" in cols

    async def test_foreign_keys_enabled(self, ext_dir):
        from py.db.database import get_db

        async with get_db() as db:
            cur = await db.execute("PRAGMA foreign_keys")
            row = await cur.fetchone()
            assert row[0] == 1


class TestMigrateDb:
    async def test_migration_is_idempotent(self, ext_dir):
        """Running _migrate_db twice must not raise an error."""
        from py.db.database import _migrate_db

        await _migrate_db()
        await _migrate_db()  # second call should be a no-op

    async def test_init_db_idempotent(self, ext_dir):
        from py.db.database import init_db

        await init_db()  # already ran via fixture; calling again must not fail
