import aiosqlite
from contextlib import asynccontextmanager
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
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    model_id INTEGER NOT NULL REFERENCES models(id) ON DELETE CASCADE,
    tag TEXT NOT NULL
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
        await db.commit()


async def init_db():
    async with aiosqlite.connect(cfg.db_path()) as db:
        await db.executescript(_SCHEMA)
        await db.commit()
    await _migrate_db()
