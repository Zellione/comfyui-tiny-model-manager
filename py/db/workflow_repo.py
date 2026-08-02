"""Persistence for downloaded workflows (F-129).

Mirrors the catalog/model split on the models side: ``workflow_entries`` is the source
page (name, description, tags, gallery media) and ``workflows`` holds the individual
ComfyUI graphs extracted from that page's archive, so several graphs downloaded together
share one set of metadata and one media directory.
"""

import json

from .database import get_db

_MAX_DESCRIPTION = 10_000
_MAX_NAME = 500
_MAX_PATH = 1_000

_SELECT_ENTRY_ID = (
    "SELECT id FROM workflow_entries WHERE source_platform = ? AND source_page_id = ?"
)
_ENTRY_COLS = (
    "SELECT id, source_platform, source_page_id, source_page_url, display_name,"
    "       description, base_model, tags, thumbnail_url, media_hash, created_at"
    " FROM workflow_entries"
)
_ITEM_COLS = (
    "SELECT id, entry_id, name, local_path, version_id, version_name, node_count, created_at"
    " FROM workflows"
)


def _parse_json_list(value: str) -> list:
    if not value:
        return []
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, list) else []
    except (ValueError, TypeError):
        return []


async def upsert_workflow_entry(
    source_platform: str,
    source_page_id: str,
    source_page_url: str = "",
    display_name: str = "",
    description: str = "",
    base_model: str = "",
    tags: list[str] | None = None,
    thumbnail_url: str = "",
    media_hash: str = "",
) -> int:
    """Insert or refresh a workflow source page; returns its entry id.

    Empty values never overwrite stored data, matching upsert_catalog_entry — a partial
    refetch must not wipe metadata that an earlier, richer fetch already stored.
    """
    tags_json = json.dumps(tags) if tags else ""
    async with get_db() as db:
        await db.execute(
            """
            INSERT INTO workflow_entries
                (source_platform, source_page_id, source_page_url, display_name,
                 description, base_model, tags, thumbnail_url, media_hash)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(source_platform, source_page_id) DO UPDATE SET
                source_page_url = CASE WHEN excluded.source_page_url != '' THEN excluded.source_page_url ELSE source_page_url END,
                display_name    = CASE WHEN excluded.display_name != ''    THEN excluded.display_name    ELSE display_name    END,
                description     = CASE WHEN excluded.description != ''     THEN excluded.description     ELSE description     END,
                base_model      = CASE WHEN excluded.base_model != ''      THEN excluded.base_model      ELSE base_model      END,
                tags            = CASE WHEN excluded.tags != ''            THEN excluded.tags            ELSE tags            END,
                thumbnail_url   = CASE WHEN excluded.thumbnail_url != ''   THEN excluded.thumbnail_url   ELSE thumbnail_url   END,
                media_hash      = CASE WHEN excluded.media_hash != ''      THEN excluded.media_hash      ELSE media_hash      END
            """,
            (
                source_platform,
                source_page_id,
                source_page_url,
                display_name[:_MAX_NAME],
                description[:_MAX_DESCRIPTION],
                base_model,
                tags_json,
                thumbnail_url,
                media_hash,
            ),
        )
        await db.commit()
        row = await (
            await db.execute(_SELECT_ENTRY_ID, (source_platform, source_page_id))
        ).fetchone()
        assert row is not None
        return row["id"]


async def upsert_workflow(
    entry_id: int,
    name: str,
    local_path: str,
    version_id: str = "",
    version_name: str = "",
    node_count: int = 0,
) -> int:
    """Insert or refresh a single graph belonging to ``entry_id``; returns its id."""
    async with get_db() as db:
        await db.execute(
            """
            INSERT INTO workflows (entry_id, name, local_path, version_id, version_name, node_count)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(entry_id, local_path) DO UPDATE SET
                name         = excluded.name,
                version_id   = excluded.version_id,
                version_name = excluded.version_name,
                node_count   = excluded.node_count
            """,
            (
                entry_id,
                name[:_MAX_NAME],
                local_path[:_MAX_PATH],
                version_id,
                version_name,
                node_count,
            ),
        )
        await db.commit()
        row = await (
            await db.execute(
                "SELECT id FROM workflows WHERE entry_id = ? AND local_path = ?",
                (entry_id, local_path[:_MAX_PATH]),
            )
        ).fetchone()
        assert row is not None
        return row["id"]


async def _hydrate_entry(db, row) -> dict:
    """Attach the parsed tag list and the entry's graphs to a workflow_entries row."""
    entry = dict(row)
    entry["tags"] = _parse_json_list(entry.get("tags", ""))
    items = await (
        await db.execute(
            _ITEM_COLS + " WHERE entry_id = ? ORDER BY name COLLATE NOCASE", (entry["id"],)
        )
    ).fetchall()
    entry["items"] = [dict(r) for r in items]
    return entry


async def list_workflow_entries() -> list[dict]:
    async with get_db() as db:
        rows = await (await db.execute(_ENTRY_COLS + " ORDER BY created_at DESC")).fetchall()
        return [await _hydrate_entry(db, row) for row in rows]


async def get_workflow_entry(entry_id: int) -> dict | None:
    async with get_db() as db:
        row = await (await db.execute(_ENTRY_COLS + " WHERE id = ?", (entry_id,))).fetchone()
        if row is None:
            return None
        return await _hydrate_entry(db, row)


async def get_workflow(workflow_id: int) -> dict | None:
    """A single graph joined with the display name and media hash of its entry."""
    async with get_db() as db:
        row = await (
            await db.execute(
                "SELECT w.id, w.entry_id, w.name, w.local_path, w.version_id, w.version_name,"
                "       w.node_count, e.display_name AS entry_name, e.media_hash"
                " FROM workflows w JOIN workflow_entries e ON e.id = w.entry_id"
                " WHERE w.id = ?",
                (workflow_id,),
            )
        ).fetchone()
        return dict(row) if row else None


async def delete_workflow_entry(entry_id: int) -> bool:
    """Delete an entry; its graphs cascade. False when the entry did not exist."""
    async with get_db() as db:
        cursor = await db.execute("DELETE FROM workflow_entries WHERE id = ?", (entry_id,))
        await db.commit()
        return cursor.rowcount > 0


async def get_installed_version_ids() -> set[str]:
    """Every CivitAI version id that has at least one stored graph.

    Drives the "already downloaded" badge on the browse page without a per-row query.
    """
    async with get_db() as db:
        rows = await (
            await db.execute("SELECT DISTINCT version_id FROM workflows WHERE version_id != ''")
        ).fetchall()
        return {r["version_id"] for r in rows}
