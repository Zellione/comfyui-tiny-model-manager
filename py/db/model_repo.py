import json
import os
from datetime import UTC, datetime

from .database import get_db

_MAX_DESCRIPTION = 10_000
_REPO_FILE_COLS = (
    "SELECT filename, model_type, size_bytes, download_url, source_page_url, civitai_version_name"
)
_MAX_WORD = 200
_MAX_TAG = 200
_MAX_PATH = 1_000
_ALLOWED_MEDIA_TYPES = {"image", "video"}
_MEDIA_SELECT = "SELECT id, media_type, local_path FROM model_media WHERE model_id = ?"
_REPO_FILES_FROM_WHERE = " FROM repo_files WHERE catalog_entry_id = ?"
_DELETE_TRIGGER_WORDS = "DELETE FROM trigger_words WHERE model_id = ?"
_INSERT_TRIGGER_WORD = "INSERT INTO trigger_words (model_id, word) VALUES (?, ?)"


async def _prune_orphan_tags(db) -> None:
    """Remove tag names that are no longer linked to any model."""
    await db.execute("DELETE FROM tags WHERE id NOT IN (SELECT DISTINCT tag_id FROM model_tags)")


async def _set_model_tags(db, model_id: int, tags: list[str]) -> None:
    """Replace all tag links for a model, creating new tag rows as needed, then prune orphans."""
    await db.execute("DELETE FROM model_tags WHERE model_id = ?", (model_id,))
    for name in tags:
        name = name[:_MAX_TAG]
        await db.execute("INSERT OR IGNORE INTO tags(name) VALUES (?)", (name,))
        await db.execute(
            "INSERT OR IGNORE INTO model_tags(model_id, tag_id) "
            "SELECT ?, id FROM tags WHERE name = ?",
            (model_id, name),
        )
    await _prune_orphan_tags(db)


async def _upsert_model_row(
    db,
    filename: str,
    model_type: str,
    source_platform: str,
    source_id: str,
    description: str,
    base_model: str,
    civitai_model_id: str,
    media_hash: str,
    readme_html: str = "",
    civitai_version_name: str = "",
) -> int:
    """Insert/update the models row and return its id (does not commit)."""
    cursor = await db.execute(
        """
        INSERT INTO models (filename, model_type, source_platform, source_id, description, base_model, civitai_model_id, civitai_version_name, media_hash, readme_html)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(filename) DO UPDATE SET
            model_type = excluded.model_type,
            source_platform = excluded.source_platform,
            source_id = excluded.source_id,
            description = excluded.description,
            base_model = CASE WHEN excluded.base_model != '' THEN excluded.base_model ELSE base_model END,
            civitai_model_id = excluded.civitai_model_id,
            civitai_version_name = excluded.civitai_version_name,
            media_hash = excluded.media_hash,
            readme_html = excluded.readme_html
        """,
        (
            filename,
            model_type,
            source_platform,
            source_id,
            description[:_MAX_DESCRIPTION],
            base_model,
            civitai_model_id,
            civitai_version_name,
            media_hash,
            readme_html[:_MAX_DESCRIPTION],
        ),
    )
    if cursor.lastrowid:
        return cursor.lastrowid
    row = await (
        await db.execute("SELECT id FROM models WHERE filename = ?", (filename,))
    ).fetchone()
    return row["id"]


async def upsert_model(
    filename: str,
    model_type: str,
    source_platform: str,
    source_id: str,
    description: str,
    base_model: str = "",
    civitai_model_id: str = "",
    media_hash: str = "",
    readme_html: str = "",
    civitai_version_name: str = "",
) -> int:
    async with get_db() as db:
        model_id = await _upsert_model_row(
            db,
            filename,
            model_type,
            source_platform,
            source_id,
            description,
            base_model,
            civitai_model_id,
            media_hash,
            readme_html,
            civitai_version_name,
        )
        await db.commit()
        return model_id


async def upsert_model_with_meta(
    filename: str,
    model_type: str,
    source_platform: str,
    source_id: str,
    description: str,
    trigger_words: list[str],
    tags: list[str],
    base_model: str = "",
    civitai_model_id: str = "",
    media_hash: str = "",
    readme_html: str = "",
    civitai_version_name: str = "",
) -> int:
    async with get_db() as db:
        model_id = await _upsert_model_row(
            db,
            filename,
            model_type,
            source_platform,
            source_id,
            description,
            base_model,
            civitai_model_id,
            media_hash,
            readme_html,
            civitai_version_name,
        )
        await db.execute(_DELETE_TRIGGER_WORDS, (model_id,))
        await db.executemany(
            _INSERT_TRIGGER_WORD,
            [(model_id, w[:_MAX_WORD]) for w in trigger_words],
        )
        await _set_model_tags(db, model_id, tags)
        await db.commit()
        return model_id


async def set_trigger_words(model_id: int, words: list[str]):
    async with get_db() as db:
        await db.execute(_DELETE_TRIGGER_WORDS, (model_id,))
        await db.executemany(
            _INSERT_TRIGGER_WORD,
            [(model_id, w[:_MAX_WORD]) for w in words],
        )
        await db.commit()


async def set_tags(model_id: int, tags: list[str]):
    async with get_db() as db:
        await _set_model_tags(db, model_id, tags)
        await db.commit()


async def add_media(model_id: int, media_type: str, local_path: str) -> int:
    if media_type not in _ALLOWED_MEDIA_TYPES:
        raise ValueError(f"Invalid media_type: {media_type!r}")
    capped = local_path[:_MAX_PATH]
    async with get_db() as db:
        existing = await (
            await db.execute(
                "SELECT id FROM model_media WHERE model_id = ? AND local_path = ?",
                (model_id, capped),
            )
        ).fetchone()
        if existing:
            return existing["id"]
        cursor = await db.execute(
            "INSERT INTO model_media (model_id, media_type, local_path) VALUES (?, ?, ?)",
            (model_id, media_type, capped),
        )
        await db.commit()
        return cursor.lastrowid


async def _hydrate_model(db, row) -> dict:
    """Attach trigger_words, tags and media lists to a models row."""
    model = dict(row)
    model_id = model["id"]
    words = await (
        await db.execute("SELECT word FROM trigger_words WHERE model_id = ?", (model_id,))
    ).fetchall()
    media = await (await db.execute(_MEDIA_SELECT, (model_id,))).fetchall()
    tags = await (
        await db.execute(
            "SELECT t.name FROM tags t JOIN model_tags mt ON mt.tag_id = t.id WHERE mt.model_id = ?",
            (model_id,),
        )
    ).fetchall()
    model["trigger_words"] = [r["word"] for r in words]
    model["tags"] = [r["name"] for r in tags]
    model["media"] = [dict(r) for r in media]
    return model


async def get_model_by_filename(filename: str) -> dict | None:
    async with get_db() as db:
        row = await (
            await db.execute("SELECT * FROM models WHERE filename = ?", (filename,))
        ).fetchone()
        return await _hydrate_model(db, row) if row else None


async def get_metadata_by_filenames(filenames: list[str]) -> dict[str, dict]:
    if not filenames:
        return {}
    async with get_db() as db:
        placeholders = ",".join("?" * len(filenames))
        rows = await (
            await db.execute(f"SELECT * FROM models WHERE filename IN ({placeholders})", filenames)
        ).fetchall()
        result = {}
        for row in rows:
            model = await _hydrate_model(db, row)
            result[model["filename"]] = model
        return result


async def update_model_meta(
    filename: str,
    description: str | None = None,
    trigger_words: list[str] | None = None,
    tags: list[str] | None = None,
    base_model: str | None = None,
    model_type: str = "",
    readme_html: str | None = None,
):
    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    async with get_db() as db:
        # Ensure a row exists for manually-placed or link-source-only files.
        await db.execute(
            "INSERT OR IGNORE INTO models (filename, model_type) VALUES (?, ?)",
            (filename[:_MAX_PATH], model_type),
        )
        sets: list[str] = []
        vals: list[object] = []
        if description is not None:
            sets.append("description = ?, description_edited_at = ?")
            vals.append(description[:_MAX_DESCRIPTION])
            vals.append(now)
        if base_model is not None:
            sets.append("base_model = ?, base_model_edited_at = ?")
            vals.append(base_model)
            vals.append(now)
        if readme_html is not None:
            sets.append("readme_html = ?")
            vals.append(readme_html[:_MAX_DESCRIPTION])
        if sets:
            await db.execute(
                f"UPDATE models SET {', '.join(sets)} WHERE filename = ?",
                (*vals, filename),
            )
        if trigger_words is not None or tags is not None:
            row = await (
                await db.execute("SELECT id FROM models WHERE filename = ?", (filename,))
            ).fetchone()
            if row:
                model_id = row["id"]
                if trigger_words is not None:
                    await db.execute(_DELETE_TRIGGER_WORDS, (model_id,))
                    await db.executemany(
                        _INSERT_TRIGGER_WORD,
                        [(model_id, w[:_MAX_WORD]) for w in trigger_words],
                    )
                    await db.execute(
                        "UPDATE models SET trigger_words_edited_at = ? WHERE id = ?",
                        (now, model_id),
                    )
                if tags is not None:
                    await _set_model_tags(db, model_id, tags)
                    await db.execute(
                        "UPDATE models SET tags_edited_at = ? WHERE id = ?",
                        (now, model_id),
                    )
        await db.commit()


async def update_model_type(filename: str, new_type: str):
    async with get_db() as db:
        await db.execute(
            "UPDATE models SET model_type = ? WHERE filename = ?", (new_type, filename)
        )
        await db.commit()


async def update_model_filename(old_filename: str, new_filename: str) -> None:
    async with get_db() as db:
        await db.execute(
            "UPDATE models SET filename = ? WHERE filename = ?",
            (new_filename[:_MAX_PATH], old_filename),
        )
        await db.commit()


async def get_all_models_slim() -> list[dict]:
    async with get_db() as db:
        rows = await (
            await db.execute("SELECT filename, model_type, base_model FROM models")
        ).fetchall()
        return [dict(row) for row in rows]


async def enqueue_reorganize(filename: str, model_type: str, direction: str) -> None:
    async with get_db() as db:
        await db.execute(
            "INSERT INTO reorganize_queue (filename, model_type, direction) VALUES (?, ?, ?)",
            (filename[:_MAX_PATH], model_type, direction),
        )
        await db.commit()


async def clear_pending_jobs(direction: str) -> None:
    async with get_db() as db:
        await db.execute(
            "DELETE FROM reorganize_queue WHERE status = 'pending' AND direction = ?", (direction,)
        )
        await db.commit()


async def get_pending_jobs(direction: str | None = None) -> list[dict]:
    async with get_db() as db:
        if direction is None:
            rows = await (
                await db.execute(
                    "SELECT id, filename, model_type, direction"
                    " FROM reorganize_queue WHERE status = 'pending'"
                )
            ).fetchall()
        else:
            rows = await (
                await db.execute(
                    "SELECT id, filename, model_type, direction"
                    " FROM reorganize_queue WHERE status = 'pending' AND direction = ?",
                    (direction,),
                )
            ).fetchall()
        return [dict(row) for row in rows]


async def complete_job(job_id: int) -> None:
    async with get_db() as db:
        await db.execute("UPDATE reorganize_queue SET status = 'done' WHERE id = ?", (job_id,))
        await db.commit()


async def upsert_catalog_entry(
    source_platform: str,
    source_page_id: str,
    source_page_url: str,
    display_name: str,
    thumbnail_url: str,
    base_model: str,
    description: str = "",
    trigger_words: list[str] | None = None,
    tags: list[str] | None = None,
    media_hash: str = "",
    readme_html: str = "",
) -> int:
    # Source-page metadata is stored on the catalog entry so it survives even when no
    # model file is installed. Empty values never overwrite existing data (so a partial
    # fetch can't wipe good metadata) — editing uses update_catalog_metadata instead.
    trigger_json = json.dumps(trigger_words) if trigger_words else ""
    tags_json = json.dumps(tags) if tags else ""
    async with get_db() as db:
        await db.execute(
            """
            INSERT INTO catalog_entries
                (source_platform, source_page_id, source_page_url, display_name, thumbnail_url,
                 base_model, description, trigger_words, tags, media_hash, readme_html)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(source_platform, source_page_id) DO UPDATE SET
                source_page_url = CASE WHEN excluded.source_page_url != '' THEN excluded.source_page_url ELSE source_page_url END,
                display_name    = CASE WHEN excluded.display_name != ''    THEN excluded.display_name    ELSE display_name    END,
                thumbnail_url   = CASE WHEN excluded.thumbnail_url != ''   THEN excluded.thumbnail_url   ELSE thumbnail_url   END,
                base_model      = CASE WHEN excluded.base_model != ''      THEN excluded.base_model      ELSE base_model      END,
                description     = CASE WHEN excluded.description != ''     THEN excluded.description     ELSE description     END,
                trigger_words   = CASE WHEN excluded.trigger_words != ''   THEN excluded.trigger_words   ELSE trigger_words   END,
                tags            = CASE WHEN excluded.tags != ''            THEN excluded.tags            ELSE tags            END,
                media_hash      = CASE WHEN excluded.media_hash != ''      THEN excluded.media_hash      ELSE media_hash      END,
                readme_html     = CASE WHEN excluded.readme_html != ''     THEN excluded.readme_html     ELSE readme_html     END
            """,
            (
                source_platform,
                source_page_id,
                source_page_url,
                display_name,
                thumbnail_url,
                base_model,
                description,
                trigger_json,
                tags_json,
                media_hash,
                readme_html[:_MAX_DESCRIPTION],
            ),
        )
        await db.commit()
        row = await (
            await db.execute(
                "SELECT id FROM catalog_entries WHERE source_platform = ? AND source_page_id = ?",
                (source_platform, source_page_id),
            )
        ).fetchone()
        assert row is not None
        return row["id"]


async def update_catalog_metadata(
    source_platform: str,
    source_page_id: str,
    description: str | None = None,
    trigger_words: list[str] | None = None,
    tags: list[str] | None = None,
    base_model: str | None = None,
) -> bool:
    """Edit catalog-owned metadata. Unlike upsert, a provided value is always written
    (so the user can clear fields). None means 'leave unchanged'. Returns True if a row
    matched."""
    if description is None and trigger_words is None and tags is None and base_model is None:
        return True
    desc = description[:_MAX_DESCRIPTION] if description is not None else None
    tw_json = json.dumps(trigger_words) if trigger_words is not None else None
    tags_json = json.dumps(tags) if tags is not None else None
    async with get_db() as db:
        cur = await db.execute(
            """
            UPDATE catalog_entries SET
                description   = CASE WHEN ? IS NOT NULL THEN ? ELSE description   END,
                trigger_words = CASE WHEN ? IS NOT NULL THEN ? ELSE trigger_words END,
                tags          = CASE WHEN ? IS NOT NULL THEN ? ELSE tags          END,
                base_model    = CASE WHEN ? IS NOT NULL THEN ? ELSE base_model    END
            WHERE source_platform = ? AND source_page_id = ?
            """,
            (
                desc,
                desc,
                tw_json,
                tw_json,
                tags_json,
                tags_json,
                base_model,
                base_model,
                source_platform,
                source_page_id,
            ),
        )
        await db.commit()
        return cur.rowcount > 0


async def set_model_catalog_entry(filename: str, catalog_entry_id: int) -> None:
    async with get_db() as db:
        await db.execute(
            "UPDATE models SET catalog_entry_id = ? WHERE filename = ?",
            (catalog_entry_id, filename),
        )
        await db.commit()


async def update_version_names_for_catalog(
    source_platform: str, source_page_id: str, version_name_map: dict[str, str]
) -> None:
    """Update civitai_version_name for installed files whose source_id is in the map."""
    async with get_db() as db:
        row = await (
            await db.execute(
                "SELECT id FROM catalog_entries WHERE source_platform = ? AND source_page_id = ?",
                (source_platform, source_page_id),
            )
        ).fetchone()
        if not row:
            return
        installed = await (
            await db.execute(
                "SELECT filename, source_id FROM models WHERE catalog_entry_id = ?",
                (row["id"],),
            )
        ).fetchall()
        for file_row in installed:
            source_id = file_row["source_id"] or ""
            if source_id in version_name_map:
                await db.execute(
                    "UPDATE models SET civitai_version_name = ? WHERE filename = ?",
                    (version_name_map[source_id], file_row["filename"]),
                )
        await db.commit()


async def get_first_image_path(model_id: int) -> str | None:
    async with get_db() as db:
        row = await (
            await db.execute(
                "SELECT local_path FROM model_media WHERE model_id = ? AND media_type = 'image' LIMIT 1",
                (model_id,),
            )
        ).fetchone()
        return row["local_path"] if row else None


async def list_catalog_entries() -> list[dict]:
    async with get_db() as db:
        entries = await (
            await db.execute(
                "SELECT id, source_platform, source_page_id, source_page_url,"
                "       display_name, thumbnail_url, base_model, trigger_words, created_at"
                " FROM catalog_entries ORDER BY created_at DESC"
            )
        ).fetchall()
        result = []
        for entry in entries:
            e = dict(entry)
            e["trigger_words"] = _parse_json_list(e.get("trigger_words", ""))
            installed = list(
                await (
                    await db.execute(
                        "SELECT filename, model_type, civitai_version_name FROM models WHERE catalog_entry_id = ?",
                        (e["id"],),
                    )
                ).fetchall()
            )
            e["installed_files"] = [dict(r) for r in installed]
            # Derive a model_type for section grouping (from installed files or repo_files)
            if installed:
                e["model_type"] = installed[0]["model_type"] or "other"
            else:
                rf = await (
                    await db.execute(
                        "SELECT model_type FROM repo_files WHERE catalog_entry_id = ? LIMIT 1",
                        (e["id"],),
                    )
                ).fetchone()
                e["model_type"] = rf["model_type"] if rf else "other"
            result.append(e)
        return result


def _parse_json_list(value: str) -> list:
    if not value:
        return []
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, list) else []
    except (ValueError, TypeError):
        return []


async def get_catalog_entry(source_platform: str, source_page_id: str) -> dict | None:
    async with get_db() as db:
        row = await (
            await db.execute(
                "SELECT id, source_platform, source_page_id, source_page_url,"
                "       display_name, thumbnail_url, base_model, description,"
                "       trigger_words, tags, media_hash, readme_html, created_at"
                " FROM catalog_entries WHERE source_platform = ? AND source_page_id = ?",
                (source_platform, source_page_id),
            )
        ).fetchone()
        if not row:
            return None
        entry = dict(row)
        entry["trigger_words"] = _parse_json_list(entry.get("trigger_words", ""))
        entry["tags"] = _parse_json_list(entry.get("tags", ""))
        repo_files = await (
            await db.execute(
                _REPO_FILE_COLS + _REPO_FILES_FROM_WHERE,
                (entry["id"],),
            )
        ).fetchall()
        entry["repo_files"] = [dict(r) for r in repo_files]
        installed = await (
            await db.execute(
                "SELECT filename, model_type, civitai_version_name FROM models WHERE catalog_entry_id = ?",
                (entry["id"],),
            )
        ).fetchall()
        entry["installed_files"] = [dict(r) for r in installed]
        return entry


async def delete_catalog_entry(source_platform: str, source_page_id: str) -> dict | None:
    """Deletes the catalog entry and returns media info needed for disk cleanup."""
    async with get_db() as db:
        row = await (
            await db.execute(
                "SELECT id FROM catalog_entries WHERE source_platform = ? AND source_page_id = ?",
                (source_platform, source_page_id),
            )
        ).fetchone()
        if not row:
            return None
        entry_id = row["id"]
        # Collect model IDs and media paths before unlinking.
        linked_models = list(
            await (
                await db.execute("SELECT id FROM models WHERE catalog_entry_id = ?", (entry_id,))
            ).fetchall()
        )
        model_ids = [r["id"] for r in linked_models]
        media_paths: list[str] = []
        if model_ids:
            placeholders = ",".join("?" * len(model_ids))
            media_rows = await (
                await db.execute(
                    f"SELECT local_path FROM model_media WHERE model_id IN ({placeholders})",
                    model_ids,
                )
            ).fetchall()
            media_paths = [r["local_path"] for r in media_rows]
            # Delete model_media rows (not covered by any CASCADE).
            await db.execute(
                f"DELETE FROM model_media WHERE model_id IN ({placeholders})", model_ids
            )
            # Unlink models so they appear as "unknown" after catalog removal.
            await db.execute(
                "UPDATE models SET catalog_entry_id = NULL WHERE catalog_entry_id = ?",
                (entry_id,),
            )
        # ON DELETE CASCADE handles repo_files when catalog_entry is deleted.
        await db.execute("DELETE FROM catalog_entries WHERE id = ?", (entry_id,))
        await db.commit()
        return {"media_paths": media_paths}


async def upsert_repo_files(catalog_entry_id: int, model_type: str, files: list[dict]) -> None:
    async with get_db() as db:
        for f in files:
            await db.execute(
                """
                INSERT INTO repo_files (catalog_entry_id, model_type, filename, size_bytes, download_url, source_page_url, civitai_version_name)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(catalog_entry_id, filename) DO UPDATE SET
                    model_type           = excluded.model_type,
                    size_bytes           = excluded.size_bytes,
                    download_url         = excluded.download_url,
                    source_page_url      = excluded.source_page_url,
                    civitai_version_name = excluded.civitai_version_name
                """,
                (
                    catalog_entry_id,
                    model_type,
                    f.get("filename", "")[:_MAX_PATH],
                    f.get("size_bytes"),
                    f.get("download_url", ""),
                    f.get("source_page_url", ""),
                    f.get("civitai_version_name", ""),
                ),
            )
        await db.commit()


async def get_model_type_for_catalog(catalog_entry_id: int) -> str:
    """Returns the model_type for a catalog entry, falling back to installed models."""
    async with get_db() as db:
        row = await (
            await db.execute(
                "SELECT model_type FROM repo_files WHERE catalog_entry_id = ? LIMIT 1",
                (catalog_entry_id,),
            )
        ).fetchone()
        if row:
            return row["model_type"]
        row = await (
            await db.execute(
                "SELECT model_type FROM models WHERE catalog_entry_id = ? LIMIT 1",
                (catalog_entry_id,),
            )
        ).fetchone()
        return row["model_type"] if row else ""


async def get_repo_files_by_catalog(catalog_entry_id: int) -> list[dict]:
    async with get_db() as db:
        rows = await (
            await db.execute(
                _REPO_FILE_COLS + _REPO_FILES_FROM_WHERE,
                (catalog_entry_id,),
            )
        ).fetchall()
        return [dict(r) for r in rows]


async def get_repo_files(_model_type: str, model_path: str) -> list[dict]:
    """Returns repo_files for a model file, looked up via its catalog entry."""
    async with get_db() as db:
        row = await (
            await db.execute(
                "SELECT catalog_entry_id FROM models WHERE filename = ?",
                (model_path,),
            )
        ).fetchone()
        if not row or not row["catalog_entry_id"]:
            return []
        rows = await (
            await db.execute(
                _REPO_FILE_COLS + _REPO_FILES_FROM_WHERE,
                (row["catalog_entry_id"],),
            )
        ).fetchall()
        return [dict(r) for r in rows]


async def get_installed_basenames_for_model(model_path: str) -> dict[str, dict]:
    """Return {basename: {installed_path, base_model}} for all models sharing the same catalog entry."""
    async with get_db() as db:
        row = await (
            await db.execute(
                "SELECT catalog_entry_id FROM models WHERE filename = ?",
                (model_path,),
            )
        ).fetchone()
        if not row or not row["catalog_entry_id"]:
            return {}
        installed = await (
            await db.execute(
                "SELECT filename, base_model FROM models WHERE catalog_entry_id = ?",
                (row["catalog_entry_id"],),
            )
        ).fetchall()
        return {
            os.path.basename(r["filename"]): {
                "installed_path": r["filename"],
                "base_model": r["base_model"] or "",
            }
            for r in installed
        }


async def get_effective_base_model(filename: str) -> str:
    """Return base_model from models row, falling back to catalog_entries.base_model."""
    async with get_db() as db:
        row = await (
            await db.execute(
                """
                SELECT COALESCE(NULLIF(m.base_model, ''), NULLIF(ce.base_model, ''), '') AS base_model
                FROM models m
                LEFT JOIN catalog_entries ce ON m.catalog_entry_id = ce.id
                WHERE m.filename = ?
                """,
                (filename,),
            )
        ).fetchone()
        return row["base_model"] if row else ""


async def update_model_base_model(filename: str, base_model: str) -> None:
    """Set base_model on a models row only when it is currently empty."""
    async with get_db() as db:
        await db.execute(
            "UPDATE models SET base_model = ? WHERE filename = ? AND (base_model IS NULL OR base_model = '')",
            (base_model, filename),
        )
        await db.commit()


async def delete_model_record(filename: str) -> None:
    """Remove a model row from the DB after its file has been deleted from disk."""
    async with get_db() as db:
        await db.execute("DELETE FROM models WHERE filename = ?", (filename,))
        await db.commit()


async def ensure_model_with_source(
    filename: str,
    model_type: str,
    platform: str,
    source_id: str,
    civitai_model_id: str,
) -> None:
    """Ensure a models row exists for filename and update its source fields."""
    async with get_db() as db:
        await db.execute(
            "INSERT OR IGNORE INTO models (filename, model_type, description) VALUES (?, ?, '')",
            (filename, model_type),
        )
        await db.execute(
            "UPDATE models SET source_platform = ?, source_id = ?, civitai_model_id = ?"
            " WHERE filename = ?",
            (platform, source_id or None, civitai_model_id or None, filename),
        )
        await db.commit()


async def get_model_source_info(filename: str) -> dict | None:
    async with get_db() as db:
        row = await (
            await db.execute(
                "SELECT source_platform, source_id, model_type FROM models WHERE filename = ?",
                (filename,),
            )
        ).fetchone()
        return dict(row) if row else None


async def get_model_id_and_hash(filename: str) -> tuple[int, str] | None:
    async with get_db() as db:
        row = await (
            await db.execute("SELECT id, media_hash FROM models WHERE filename = ?", (filename,))
        ).fetchone()
        return (row["id"], row["media_hash"]) if row else None


async def get_model_media(model_id: int) -> list[dict]:
    async with get_db() as db:
        rows = await (
            await db.execute(
                _MEDIA_SELECT,
                (model_id,),
            )
        ).fetchall()
        return [dict(r) for r in rows]


async def delete_media_row(media_id: int) -> None:
    async with get_db() as db:
        await db.execute("DELETE FROM model_media WHERE id = ?", (media_id,))
        await db.commit()


# ---------------------------------------------------------------------------
# F-47 Download History
# ---------------------------------------------------------------------------


async def insert_download_history(
    model_name: str,
    source: str,
    model_id: str,
    version_id: str,
    file_url: str,
    dest_path: str,
    model_type: str,
) -> int:
    async with get_db() as db:
        cursor = await db.execute(
            "INSERT INTO download_history"
            " (model_name, source, model_id, version_id, file_url, dest_path, model_type, status)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, 'downloading')",
            (model_name, source, model_id, version_id, file_url, dest_path, model_type),
        )
        await db.commit()
        assert cursor.lastrowid is not None
        return cursor.lastrowid


async def update_download_history_status(history_id: int, status: str) -> None:
    async with get_db() as db:
        await db.execute(
            "UPDATE download_history SET status = ?, updated_at = datetime('now') WHERE id = ?",
            (status, history_id),
        )
        await db.commit()


async def update_download_history_status_by_path(
    model_type: str, dest_path: str, new_status: str
) -> None:
    async with get_db() as db:
        await db.execute(
            "UPDATE download_history SET status = ?, updated_at = datetime('now')"
            " WHERE model_type = ? AND dest_path = ?",
            (new_status, model_type, dest_path),
        )
        await db.commit()


async def get_download_history(
    status: str = "", q: str = "", page: int = 1, page_size: int = 20
) -> tuple[list[dict], int]:
    conditions: list[str] = []
    params: list[object] = []
    if status:
        conditions.append("status = ?")
        params.append(status)
    if q:
        conditions.append("model_name LIKE ?")
        params.append(f"%{q}%")
    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    offset = (page - 1) * page_size
    async with get_db() as db:
        total_row = await (
            await db.execute(f"SELECT COUNT(*) AS cnt FROM download_history {where}", params)
        ).fetchone()
        total = total_row["cnt"] if total_row else 0
        rows = await (
            await db.execute(
                f"SELECT * FROM download_history {where}"
                " ORDER BY updated_at DESC, id DESC LIMIT ? OFFSET ?",
                [*params, page_size, offset],
            )
        ).fetchall()
        return [dict(r) for r in rows], total


async def get_download_history_entry(entry_id: int) -> dict | None:
    async with get_db() as db:
        row = await (
            await db.execute("SELECT * FROM download_history WHERE id = ?", (entry_id,))
        ).fetchone()
        return dict(row) if row else None


async def get_interrupted_downloads() -> list[dict]:
    async with get_db() as db:
        rows = await (
            await db.execute("SELECT * FROM download_history WHERE status = 'downloading'")
        ).fetchall()
        return [dict(r) for r in rows]
