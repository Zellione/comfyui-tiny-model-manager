from contextlib import asynccontextmanager

import aiosqlite

from .. import config as cfg

_SCHEMA = """
CREATE TABLE IF NOT EXISTS models (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filename TEXT UNIQUE NOT NULL,
    model_type TEXT,
    source_platform TEXT,
    source_id TEXT,
    description TEXT DEFAULT '',
    base_model TEXT NOT NULL DEFAULT '',
    civitai_model_id TEXT,
    media_hash TEXT NOT NULL DEFAULT '',
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS trigger_words (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    model_id INTEGER NOT NULL REFERENCES models(id) ON DELETE CASCADE,
    word TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS model_media (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    model_id INTEGER NOT NULL REFERENCES models(id) ON DELETE CASCADE,
    media_type TEXT NOT NULL,
    local_path TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tags (
    id   INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS model_tags (
    model_id INTEGER NOT NULL REFERENCES models(id) ON DELETE CASCADE,
    tag_id   INTEGER NOT NULL REFERENCES tags(id)   ON DELETE CASCADE,
    PRIMARY KEY (model_id, tag_id)
);

CREATE TABLE IF NOT EXISTS deorganize_queue (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    filename   TEXT    NOT NULL,
    model_type TEXT    NOT NULL,
    status     TEXT    NOT NULL DEFAULT 'pending',
    created_at INTEGER          DEFAULT (strftime('%s','now'))
);
"""


@asynccontextmanager
async def get_db():
    async with aiosqlite.connect(cfg.db_path()) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA foreign_keys = ON")
        yield db


async def _migrate_db():
    """Add columns introduced after the initial schema; safe to re-run (ignores existing columns)."""
    migrations = [
        "ALTER TABLE models ADD COLUMN base_model TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE models ADD COLUMN civitai_model_id TEXT",
        "ALTER TABLE models ADD COLUMN media_hash TEXT NOT NULL DEFAULT ''",
    ]
    async with aiosqlite.connect(cfg.db_path()) as db:
        for sql in migrations:
            try:
                await db.execute(sql)
            except Exception:
                pass  # column already exists

        # Migrate tags from the old 1-n layout (tags: id, model_id, tag) to the new m-n layout
        # (tags: id/name UNIQUE + model_tags junction). Self-healing: also recovers DBs left
        # in the half-migrated corrupt state by a prior buggy version of this migration
        # (empty new `tags`, real rows stranded in `tags_old`, `model_tags` -> `tags_old`).
        try:
            cur = await db.execute("PRAGMA table_info(tags)")
            tags_cols = {row[1] for row in await cur.fetchall()}
            has_tags_old = bool(
                await (
                    await db.execute(
                        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='tags_old'"
                    )
                ).fetchone()
            )
            if "model_id" in tags_cols or has_tags_old:
                if "model_id" in tags_cols:
                    # Current `tags` is the legacy table — move it aside.
                    await db.execute("DROP TABLE IF EXISTS tags_old")
                    await db.execute("ALTER TABLE tags RENAME TO tags_old")
                # Drop model_tags *before* recreating tags.  SQLite's ALTER-RENAME
                # rewrites child-table FK references, so if model_tags already exists
                # at rename time its tag_id FK would point at tags_old after the rename,
                # making subsequent inserts fail.  Dropping first avoids that trap.
                await db.execute("DROP TABLE IF EXISTS model_tags")
                await db.execute("DROP TABLE IF EXISTS tags")
                await db.execute(
                    "CREATE TABLE tags"
                    " (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE)"
                )
                await db.execute(
                    "CREATE TABLE model_tags ("
                    "  model_id INTEGER NOT NULL REFERENCES models(id) ON DELETE CASCADE,"
                    "  tag_id   INTEGER NOT NULL REFERENCES tags(id)   ON DELETE CASCADE,"
                    "  PRIMARY KEY (model_id, tag_id)"
                    ")"
                )
                await db.execute(
                    "INSERT OR IGNORE INTO tags(name) SELECT DISTINCT tag FROM tags_old"
                )
                await db.execute(
                    "INSERT OR IGNORE INTO model_tags(model_id, tag_id) "
                    "SELECT o.model_id, t.id FROM tags_old o JOIN tags t ON t.name = o.tag"
                )
                await db.execute("DROP TABLE tags_old")
        except Exception as exc:
            # Surface the error rather than silently swallowing it — a silent pass was
            # the original cause of this bug.
            print(f"[tiny-model-manager] tag schema migration failed: {exc}")

        await db.commit()


async def init_db():
    async with aiosqlite.connect(cfg.db_path()) as db:
        await db.executescript(_SCHEMA)
        await db.commit()
    await _migrate_db()
