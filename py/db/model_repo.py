from .database import get_db

_MAX_DESCRIPTION = 10_000
_MAX_WORD = 200
_MAX_TAG = 200
_MAX_PATH = 1_000
_ALLOWED_MEDIA_TYPES = {"image", "video"}


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


async def upsert_model(
    filename: str,
    model_type: str,
    source_platform: str,
    source_id: str,
    description: str,
    base_model: str = "",
    civitai_model_id: str = "",
    media_hash: str = "",
) -> int:
    async with get_db() as db:
        cursor = await db.execute(
            """
            INSERT INTO models (filename, model_type, source_platform, source_id, description, base_model, civitai_model_id, media_hash)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(filename) DO UPDATE SET
                model_type = excluded.model_type,
                source_platform = excluded.source_platform,
                source_id = excluded.source_id,
                description = excluded.description,
                base_model = excluded.base_model,
                civitai_model_id = excluded.civitai_model_id,
                media_hash = excluded.media_hash
            """,
            (
                filename,
                model_type,
                source_platform,
                source_id,
                description[:_MAX_DESCRIPTION],
                base_model,
                civitai_model_id,
                media_hash,
            ),
        )
        await db.commit()
        if cursor.lastrowid:
            return cursor.lastrowid
        row = await (
            await db.execute("SELECT id FROM models WHERE filename = ?", (filename,))
        ).fetchone()
        return row["id"]


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
) -> int:
    async with get_db() as db:
        cursor = await db.execute(
            """
            INSERT INTO models (filename, model_type, source_platform, source_id, description, base_model, civitai_model_id, media_hash)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(filename) DO UPDATE SET
                model_type = excluded.model_type,
                source_platform = excluded.source_platform,
                source_id = excluded.source_id,
                description = excluded.description,
                base_model = excluded.base_model,
                civitai_model_id = excluded.civitai_model_id,
                media_hash = excluded.media_hash
            """,
            (
                filename,
                model_type,
                source_platform,
                source_id,
                description[:_MAX_DESCRIPTION],
                base_model,
                civitai_model_id,
                media_hash,
            ),
        )
        if cursor.lastrowid:
            model_id = cursor.lastrowid
        else:
            row = await (
                await db.execute("SELECT id FROM models WHERE filename = ?", (filename,))
            ).fetchone()
            model_id = row["id"]

        await db.execute("DELETE FROM trigger_words WHERE model_id = ?", (model_id,))
        await db.executemany(
            "INSERT INTO trigger_words (model_id, word) VALUES (?, ?)",
            [(model_id, w[:_MAX_WORD]) for w in trigger_words],
        )
        await _set_model_tags(db, model_id, tags)
        await db.commit()
        return model_id


async def set_trigger_words(model_id: int, words: list[str]):
    async with get_db() as db:
        await db.execute("DELETE FROM trigger_words WHERE model_id = ?", (model_id,))
        await db.executemany(
            "INSERT INTO trigger_words (model_id, word) VALUES (?, ?)",
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
    async with get_db() as db:
        cursor = await db.execute(
            "INSERT INTO model_media (model_id, media_type, local_path) VALUES (?, ?, ?)",
            (model_id, media_type, local_path[:_MAX_PATH]),
        )
        await db.commit()
        return cursor.lastrowid


async def get_model_by_filename(filename: str) -> dict | None:
    async with get_db() as db:
        row = await (
            await db.execute("SELECT * FROM models WHERE filename = ?", (filename,))
        ).fetchone()
        if not row:
            return None
        model = dict(row)
        words = await (
            await db.execute("SELECT word FROM trigger_words WHERE model_id = ?", (model["id"],))
        ).fetchall()
        media = await (
            await db.execute(
                "SELECT id, media_type, local_path FROM model_media WHERE model_id = ?",
                (model["id"],),
            )
        ).fetchall()
        tags = await (
            await db.execute(
                "SELECT t.name FROM tags t JOIN model_tags mt ON mt.tag_id = t.id WHERE mt.model_id = ?",
                (model["id"],),
            )
        ).fetchall()
        model["trigger_words"] = [r["word"] for r in words]
        model["tags"] = [r["name"] for r in tags]
        model["media"] = [dict(r) for r in media]
        return model


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
            m = dict(row)
            words = await (
                await db.execute("SELECT word FROM trigger_words WHERE model_id = ?", (m["id"],))
            ).fetchall()
            media = await (
                await db.execute(
                    "SELECT id, media_type, local_path FROM model_media WHERE model_id = ?",
                    (m["id"],),
                )
            ).fetchall()
            tags = await (
                await db.execute(
                    "SELECT t.name FROM tags t JOIN model_tags mt ON mt.tag_id = t.id WHERE mt.model_id = ?",
                    (m["id"],),
                )
            ).fetchall()
            m["trigger_words"] = [r["word"] for r in words]
            m["tags"] = [r["name"] for r in tags]
            m["media"] = [dict(r) for r in media]
            result[m["filename"]] = m
        return result


async def update_model_meta(
    filename: str,
    description: str,
    trigger_words: list[str],
    tags: list[str] | None = None,
    base_model: str | None = None,
):
    if tags is None:
        tags = []
    async with get_db() as db:
        if base_model is not None:
            await db.execute(
                "UPDATE models SET description = ?, base_model = ? WHERE filename = ?",
                (description[:_MAX_DESCRIPTION], base_model, filename),
            )
        else:
            await db.execute(
                "UPDATE models SET description = ? WHERE filename = ?",
                (description[:_MAX_DESCRIPTION], filename),
            )
        row = await (
            await db.execute("SELECT id FROM models WHERE filename = ?", (filename,))
        ).fetchone()
        if row:
            model_id = row["id"]
            await db.execute("DELETE FROM trigger_words WHERE model_id = ?", (model_id,))
            await db.executemany(
                "INSERT INTO trigger_words (model_id, word) VALUES (?, ?)",
                [(model_id, w[:_MAX_WORD]) for w in trigger_words],
            )
            await _set_model_tags(db, model_id, tags)
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


async def upsert_repo_files(model_type: str, model_path: str, files: list[dict]) -> None:
    async with get_db() as db:
        for f in files:
            await db.execute(
                """
                INSERT INTO repo_files (model_type, model_path, filename, size_bytes, download_url, source_page_url)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(model_type, model_path, filename) DO UPDATE SET
                    size_bytes = excluded.size_bytes,
                    download_url = excluded.download_url,
                    source_page_url = excluded.source_page_url
                """,
                (
                    model_type,
                    model_path[:_MAX_PATH],
                    f.get("filename", "")[:_MAX_PATH],
                    f.get("size_bytes"),
                    f.get("download_url", ""),
                    f.get("source_page_url", ""),
                ),
            )
        await db.commit()


async def get_repo_files(model_type: str, model_path: str) -> list[dict]:
    async with get_db() as db:
        rows = await (
            await db.execute(
                "SELECT filename, size_bytes, download_url, source_page_url"
                " FROM repo_files WHERE model_type = ? AND model_path = ?",
                (model_type, model_path),
            )
        ).fetchall()
        return [dict(r) for r in rows]


async def get_model_source_info(filename: str) -> dict | None:
    async with get_db() as db:
        row = await (
            await db.execute(
                "SELECT source_platform, source_id, model_type FROM models WHERE filename = ?",
                (filename,),
            )
        ).fetchone()
        return dict(row) if row else None
