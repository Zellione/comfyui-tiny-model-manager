from contextlib import asynccontextmanager

import aiosqlite

from .. import config as cfg

_SCHEMA = """
CREATE TABLE IF NOT EXISTS catalog_entries (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    source_platform  TEXT NOT NULL,
    source_page_id   TEXT NOT NULL,
    source_page_url  TEXT NOT NULL DEFAULT '',
    display_name     TEXT NOT NULL DEFAULT '',
    thumbnail_url    TEXT NOT NULL DEFAULT '',
    base_model       TEXT NOT NULL DEFAULT '',
    created_at       TEXT DEFAULT (datetime('now')),
    UNIQUE (source_platform, source_page_id)
);

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
    created_at TEXT DEFAULT (datetime('now')),
    catalog_entry_id INTEGER REFERENCES catalog_entries(id)
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

CREATE TABLE IF NOT EXISTS reorganize_queue (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    filename   TEXT    NOT NULL,
    model_type TEXT    NOT NULL,
    direction  TEXT    NOT NULL DEFAULT 'deorganize',
    status     TEXT    NOT NULL DEFAULT 'pending',
    created_at INTEGER          DEFAULT (strftime('%s','now'))
);

CREATE TABLE IF NOT EXISTS repo_files (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    catalog_entry_id INTEGER REFERENCES catalog_entries(id) ON DELETE CASCADE,
    model_type       TEXT NOT NULL,
    filename         TEXT NOT NULL,
    size_bytes       INTEGER,
    download_url     TEXT,
    source_page_url  TEXT,
    UNIQUE (catalog_entry_id, filename)
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

        # Migrate deorganize_queue → reorganize_queue (adds direction column)
        try:
            has_deorg = bool(
                await (
                    await db.execute(
                        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='deorganize_queue'"
                    )
                ).fetchone()
            )
            has_reorg = bool(
                await (
                    await db.execute(
                        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='reorganize_queue'"
                    )
                ).fetchone()
            )
            if has_deorg and not has_reorg:
                await db.execute(
                    "CREATE TABLE reorganize_queue ("
                    "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
                    "  filename TEXT NOT NULL,"
                    "  model_type TEXT NOT NULL,"
                    "  direction TEXT NOT NULL DEFAULT 'deorganize',"
                    "  status TEXT NOT NULL DEFAULT 'pending',"
                    "  created_at INTEGER DEFAULT (strftime('%s','now'))"
                    ")"
                )
                await db.execute(
                    "INSERT INTO reorganize_queue (filename, model_type, direction, status, created_at)"
                    " SELECT filename, model_type, 'deorganize', status, created_at FROM deorganize_queue"
                )
                await db.execute("DROP TABLE deorganize_queue")
        except Exception as exc:
            print(f"[tiny-model-manager] reorganize_queue migration failed: {exc}")

        # Create repo_files table for installations predating F-39
        try:
            await db.execute(
                "CREATE TABLE IF NOT EXISTS repo_files ("
                "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
                "  model_type TEXT NOT NULL,"
                "  model_path TEXT NOT NULL,"
                "  filename TEXT NOT NULL,"
                "  size_bytes INTEGER,"
                "  download_url TEXT,"
                "  source_page_url TEXT,"
                "  UNIQUE (model_type, model_path, filename)"
                ")"
            )
        except Exception as exc:
            print(f"[tiny-model-manager] repo_files migration failed: {exc}")

        # F-40: catalog_entries table (fresh installs already have it from _SCHEMA)
        try:
            await db.execute(
                "CREATE TABLE IF NOT EXISTS catalog_entries ("
                "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
                "  source_platform TEXT NOT NULL,"
                "  source_page_id TEXT NOT NULL,"
                "  source_page_url TEXT NOT NULL DEFAULT '',"
                "  display_name TEXT NOT NULL DEFAULT '',"
                "  thumbnail_url TEXT NOT NULL DEFAULT '',"
                "  base_model TEXT NOT NULL DEFAULT '',"
                "  created_at TEXT DEFAULT (datetime('now')),"
                "  UNIQUE (source_platform, source_page_id)"
                ")"
            )
        except Exception as exc:
            print(f"[tiny-model-manager] catalog_entries creation failed: {exc}")

        # F-40: catalog_entry_id on models
        try:
            await db.execute(
                "ALTER TABLE models ADD COLUMN"
                " catalog_entry_id INTEGER REFERENCES catalog_entries(id)"
            )
        except Exception:
            pass  # column already exists

        # F-40: seed catalog_entries from existing models, link models, and migrate repo_files
        try:
            await db.execute(
                "INSERT OR IGNORE INTO catalog_entries"
                " (source_platform, source_page_id, source_page_url, display_name, thumbnail_url, base_model)"
                " SELECT 'civitai', civitai_model_id,"
                "        'https://civitai.com/models/' || civitai_model_id, '', '', base_model"
                " FROM models"
                " WHERE source_platform = 'civitai'"
                "   AND civitai_model_id IS NOT NULL AND civitai_model_id != ''"
            )
            await db.execute(
                "INSERT OR IGNORE INTO catalog_entries"
                " (source_platform, source_page_id, source_page_url, display_name, thumbnail_url, base_model)"
                " SELECT 'huggingface', source_id,"
                "        'https://huggingface.co/' || source_id, '', '', base_model"
                " FROM models"
                " WHERE source_platform = 'huggingface'"
                "   AND source_id IS NOT NULL AND source_id != ''"
            )
            # Populate thumbnail_url from first image in model_media
            await db.execute(
                "UPDATE catalog_entries SET thumbnail_url = COALESCE(("
                "  SELECT mm.local_path"
                "  FROM model_media mm"
                "  JOIN models m ON mm.model_id = m.id"
                "  WHERE mm.media_type = 'image'"
                "    AND ("
                "      (catalog_entries.source_platform = 'civitai'"
                "       AND m.source_platform = 'civitai'"
                "       AND m.civitai_model_id = catalog_entries.source_page_id)"
                "      OR"
                "      (catalog_entries.source_platform = 'huggingface'"
                "       AND m.source_platform = 'huggingface'"
                "       AND m.source_id = catalog_entries.source_page_id)"
                "    )"
                "  LIMIT 1"
                "), '') WHERE thumbnail_url = ''"
            )
            # Link models rows to their catalog entries
            await db.execute(
                "UPDATE models SET catalog_entry_id = ("
                "  SELECT ce.id FROM catalog_entries ce"
                "  WHERE (models.source_platform = 'civitai'"
                "         AND ce.source_platform = 'civitai'"
                "         AND models.civitai_model_id IS NOT NULL"
                "         AND models.civitai_model_id != ''"
                "         AND ce.source_page_id = models.civitai_model_id)"
                "     OR (models.source_platform = 'huggingface'"
                "         AND ce.source_platform = 'huggingface'"
                "         AND models.source_id IS NOT NULL"
                "         AND models.source_id != ''"
                "         AND ce.source_page_id = models.source_id)"
                ") WHERE catalog_entry_id IS NULL"
            )
            # Migrate repo_files from model_path-keyed to catalog_entry_id-keyed
            cur = await db.execute("PRAGMA table_info(repo_files)")
            rf_cols = {row[1] for row in await cur.fetchall()}
            if "model_path" in rf_cols and "catalog_entry_id" not in rf_cols:
                await db.execute(
                    "CREATE TABLE repo_files_f40 ("
                    "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
                    "  catalog_entry_id INTEGER REFERENCES catalog_entries(id) ON DELETE CASCADE,"
                    "  model_type TEXT NOT NULL,"
                    "  filename TEXT NOT NULL,"
                    "  size_bytes INTEGER,"
                    "  download_url TEXT,"
                    "  source_page_url TEXT,"
                    "  UNIQUE (catalog_entry_id, filename)"
                    ")"
                )
                await db.execute(
                    "INSERT OR IGNORE INTO repo_files_f40"
                    " (catalog_entry_id, model_type, filename, size_bytes, download_url, source_page_url)"
                    " SELECT m.catalog_entry_id, rf.model_type, rf.filename,"
                    "        rf.size_bytes, rf.download_url, rf.source_page_url"
                    " FROM repo_files rf"
                    " JOIN models m ON m.filename = rf.model_path"
                    " WHERE m.catalog_entry_id IS NOT NULL"
                )
                await db.execute("DROP TABLE repo_files")
                await db.execute("ALTER TABLE repo_files_f40 RENAME TO repo_files")
        except Exception as exc:
            print(f"[tiny-model-manager] F-40 catalog migration failed: {exc}")

        await db.commit()


async def init_db():
    async with aiosqlite.connect(cfg.db_path()) as db:
        await db.executescript(_SCHEMA)
        await db.commit()
    await _migrate_db()
