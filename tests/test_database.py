"""Tests for py/db/database.py — schema creation and migrations."""

# pi-lens-ignore: reportMissingImports
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

    async def test_tags_table_has_name_column(self, ext_dir):
        from py import config as cfg

        async with aiosqlite.connect(cfg.db_path()) as db:
            cur = await db.execute("PRAGMA table_info(tags)")
            cols = [row[1] for row in await cur.fetchall()]
            assert "name" in cols
            assert "model_id" not in cols

    async def test_creates_model_tags_table(self, ext_dir):
        from py import config as cfg

        async with aiosqlite.connect(cfg.db_path()) as db:
            cur = await db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='model_tags'"
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

    async def test_models_table_has_civitai_version_name_column(self, ext_dir):
        from py import config as cfg

        async with aiosqlite.connect(cfg.db_path()) as db:
            cur = await db.execute("PRAGMA table_info(models)")
            cols = [row[1] for row in await cur.fetchall()]
            assert "civitai_version_name" in cols

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


class TestFileHashColumn:
    async def test_file_hash_column_exists(self, ext_dir):
        from py import config as cfg

        async with aiosqlite.connect(cfg.db_path()) as db:
            cur = await db.execute("PRAGMA table_info(models)")
            cols = [row[1] for row in await cur.fetchall()]
            assert "file_hash" in cols

    async def test_init_db_idempotent(self, ext_dir):
        from py.db.database import init_db

        await init_db()  # already ran via fixture; calling again must not fail


class TestTagMigration:
    """Regression tests for the legacy-tags migration path.

    The ext_dir fixture calls init_db(), so these tests must build the legacy or corrupt
    DB state *before* init_db runs.  We do that by calling cfg.init() directly (which only
    creates the data dir) and writing the old schema by hand via raw aiosqlite.
    """

    async def test_migrates_legacy_tags_to_m_n(self, tmp_path):
        """Old 1-n tags table is migrated; tags round-trip; no FK error on set_tags."""
        from py import config as cfg
        from py.db import model_repo
        from py.db.database import init_db

        cfg.init(str(tmp_path))

        # Build a legacy DB with old-style tags(id, model_id, tag)
        async with aiosqlite.connect(cfg.db_path()) as db:
            await db.executescript("""
                CREATE TABLE models (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    filename TEXT UNIQUE NOT NULL,
                    model_type TEXT, source_platform TEXT, source_id TEXT,
                    description TEXT DEFAULT '', base_model TEXT NOT NULL DEFAULT '',
                    civitai_model_id TEXT, media_hash TEXT NOT NULL DEFAULT '',
                    created_at TEXT DEFAULT (datetime('now'))
                );
                CREATE TABLE trigger_words (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    model_id INTEGER NOT NULL REFERENCES models(id) ON DELETE CASCADE,
                    word TEXT NOT NULL
                );
                CREATE TABLE model_media (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    model_id INTEGER NOT NULL REFERENCES models(id) ON DELETE CASCADE,
                    media_type TEXT NOT NULL, local_path TEXT NOT NULL
                );
                CREATE TABLE tags (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    model_id INTEGER NOT NULL REFERENCES models(id) ON DELETE CASCADE,
                    tag TEXT NOT NULL
                );
                INSERT INTO models(filename, model_type) VALUES ('a.safetensors', 'loras');
                INSERT INTO tags(model_id, tag)
                    SELECT id, 'anime' FROM models WHERE filename='a.safetensors';
                INSERT INTO tags(model_id, tag)
                    SELECT id, 'portrait' FROM models WHERE filename='a.safetensors';
            """)
            await db.commit()

        # Migration should succeed
        await init_db()

        # Tags are recoverable
        row = await model_repo.get_model_by_filename("a.safetensors")
        assert set(row["tags"]) == {"anime", "portrait"}

        # set_tags must not raise a FK error (the original 500 regression)
        mid = row["id"]
        await model_repo.set_tags(mid, ["anime", "fantasy"])
        row2 = await model_repo.get_model_by_filename("a.safetensors")
        assert set(row2["tags"]) == {"anime", "fantasy"}

    async def test_recovers_half_migrated_corrupt_db(self, tmp_path):
        """Self-healing: recovers the state left by the prior buggy migration.

        Corrupt state: empty new tags(id,name), real data in tags_old(id, model_id, tag),
        and model_tags whose tag_id FK references tags_old.
        """
        from py import config as cfg
        from py.db import model_repo
        from py.db.database import init_db

        cfg.init(str(tmp_path))

        # Reproduce the exact corrupted schema
        async with aiosqlite.connect(cfg.db_path()) as db:
            await db.executescript("""
                CREATE TABLE models (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    filename TEXT UNIQUE NOT NULL,
                    model_type TEXT, source_platform TEXT, source_id TEXT,
                    description TEXT DEFAULT '', base_model TEXT NOT NULL DEFAULT '',
                    civitai_model_id TEXT, media_hash TEXT NOT NULL DEFAULT '',
                    created_at TEXT DEFAULT (datetime('now'))
                );
                CREATE TABLE trigger_words (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    model_id INTEGER NOT NULL REFERENCES models(id) ON DELETE CASCADE,
                    word TEXT NOT NULL
                );
                CREATE TABLE model_media (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    model_id INTEGER NOT NULL REFERENCES models(id) ON DELETE CASCADE,
                    media_type TEXT NOT NULL, local_path TEXT NOT NULL
                );
                CREATE TABLE tags (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE
                );
                CREATE TABLE tags_old (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    model_id INTEGER NOT NULL,
                    tag TEXT NOT NULL
                );
                CREATE TABLE model_tags (
                    model_id INTEGER NOT NULL REFERENCES models(id) ON DELETE CASCADE,
                    tag_id   INTEGER NOT NULL REFERENCES tags_old(id) ON DELETE CASCADE,
                    PRIMARY KEY (model_id, tag_id)
                );
                INSERT INTO models(filename, model_type) VALUES ('b.safetensors', 'checkpoints');
                INSERT INTO tags_old(model_id, tag)
                    SELECT id, 'lora' FROM models WHERE filename='b.safetensors';
                INSERT INTO tags_old(model_id, tag)
                    SELECT id, 'flux' FROM models WHERE filename='b.safetensors';
            """)
            await db.commit()

        # Recovery must succeed silently
        await init_db()

        # tags_old must be gone
        async with aiosqlite.connect(cfg.db_path()) as db:
            cur = await db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='tags_old'"
            )
            assert await cur.fetchone() is None

            # model_tags DDL must reference `tags`, not `tags_old`
            cur = await db.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name='model_tags'"
            )
            ddl = (await cur.fetchone())[0]
            assert "tags_old" not in ddl

        # Tags are recovered and writable
        row = await model_repo.get_model_by_filename("b.safetensors")
        assert set(row["tags"]) == {"lora", "flux"}

        mid = row["id"]
        await model_repo.set_tags(mid, ["lora"])
        row2 = await model_repo.get_model_by_filename("b.safetensors")
        assert row2["tags"] == ["lora"]


class TestMediaPathMigration:
    """issue #176: stored media paths are rewritten from absolute to media_dir-relative.

    The ext_dir fixture already ran init_db(), so these tests seed the legacy absolute
    values after the fact and call the migration step directly — the same way it runs on
    every startup for databases created by older versions.
    """

    async def _seed(self, media_rows: list[str], thumbnails: list[str]) -> None:
        from py import config as cfg

        async with aiosqlite.connect(cfg.db_path()) as db:
            await db.execute(
                "INSERT INTO models (filename, model_type) VALUES ('m.safetensors', 'loras')"
            )
            await db.commit()
            for path in media_rows:
                await db.execute(
                    "INSERT INTO model_media (model_id, media_type, local_path)"
                    " VALUES (1, 'image', ?)",
                    (path,),
                )
            await db.execute(
                "INSERT INTO catalog_entries (source_platform, source_page_id, thumbnail_url)"
                " VALUES ('civitai', '77', ?)",
                (thumbnails[0] if thumbnails else "",),
            )
            await db.commit()

    async def _read(self) -> tuple[list[str], str]:
        from py import config as cfg

        async with aiosqlite.connect(cfg.db_path()) as db:
            db.row_factory = aiosqlite.Row
            media = await (await db.execute("SELECT local_path FROM model_media")).fetchall()
            thumb = await (await db.execute("SELECT thumbnail_url FROM catalog_entries")).fetchone()
        return [r["local_path"] for r in media], thumb["thumbnail_url"]

    async def test_relativises_absolute_paths_under_the_media_dir(self, ext_dir):
        """A DB whose absolute values still point inside the (unchanged) media dir is
        rewritten to the relative form."""
        import os

        from py import config as cfg
        from py.db.database import _migrate_media_paths

        abs_path = os.path.join(cfg.media_dir(), "abc123", "0.jpg")
        await self._seed([abs_path], [abs_path])

        async with aiosqlite.connect(cfg.db_path()) as db:
            await _migrate_media_paths(db)
            await db.commit()

        media, thumb = await self._read()
        assert media == ["abc123/0.jpg"]
        assert thumb == "abc123/0.jpg"

    async def test_repairs_stale_absolute_paths_when_the_file_moved_with_the_tree(self, ext_dir):
        """The moved-folder case: the stored absolute path is dead, but the
        <hash>/<name> file exists in the current media dir, so the row is repaired."""
        import os

        from py import config as cfg
        from py.db.database import _migrate_media_paths

        target = os.path.join(cfg.media_dir(), "abc123", "0.jpg")
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "wb") as f:
            f.write(b"x")
        stale = "/old/root/ComfyUI/custom_nodes/comfyui-tiny-model-manager/data/media/abc123/0.jpg"
        await self._seed([stale], [])

        async with aiosqlite.connect(cfg.db_path()) as db:
            await _migrate_media_paths(db)
            await db.commit()

        media, _ = await self._read()
        assert media == ["abc123/0.jpg"]

    async def test_leaves_unverifiable_stale_paths_in_place(self, ext_dir):
        """A stale path whose file did not survive the move is not rewritten: it keeps
        working if the location is real (e.g. a stable external media dir) and 404s
        gracefully otherwise, instead of being silently pointed at the wrong file."""
        from py import config as cfg
        from py.db.database import _migrate_media_paths

        stale = "/old/root/somewhere/abc123/gone.jpg"
        await self._seed([stale], [])

        async with aiosqlite.connect(cfg.db_path()) as db:
            await _migrate_media_paths(db)
            await db.commit()

        media, _ = await self._read()
        assert media == [stale]

    async def test_relative_values_are_untouched(self, ext_dir):
        from py import config as cfg
        from py.db.database import _migrate_media_paths

        await self._seed(["abc123/0.jpg"], ["abc123/1.jpg"])

        async with aiosqlite.connect(cfg.db_path()) as db:
            await _migrate_media_paths(db)
            await db.commit()

        media, thumb = await self._read()
        assert media == ["abc123/0.jpg"]
        assert thumb == "abc123/1.jpg"

    async def test_migration_is_idempotent(self, ext_dir):
        """A second pass over an already-relative DB changes nothing."""
        import os

        from py import config as cfg
        from py.db.database import _migrate_media_paths

        abs_path = os.path.join(cfg.media_dir(), "abc123", "0.jpg")
        await self._seed([abs_path], [])

        async with aiosqlite.connect(cfg.db_path()) as db:
            await _migrate_media_paths(db)
            await db.commit()
            await _migrate_media_paths(db)
            await db.commit()

        media, _ = await self._read()
        assert media == ["abc123/0.jpg"]
