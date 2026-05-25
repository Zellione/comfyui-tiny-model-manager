from .database import get_db


async def upsert_model(filename: str, model_type: str, source_platform: str, source_id: str, description: str) -> int:
    async with get_db() as db:
        cursor = await db.execute(
            """
            INSERT INTO models (filename, model_type, source_platform, source_id, description)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(filename) DO UPDATE SET
                model_type = excluded.model_type,
                source_platform = excluded.source_platform,
                source_id = excluded.source_id,
                description = excluded.description
            """,
            (filename, model_type, source_platform, source_id, description),
        )
        await db.commit()
        if cursor.lastrowid:
            return cursor.lastrowid
        row = await (await db.execute("SELECT id FROM models WHERE filename = ?", (filename,))).fetchone()
        return row["id"]


async def set_trigger_words(model_id: int, words: list[str]):
    async with get_db() as db:
        await db.execute("DELETE FROM trigger_words WHERE model_id = ?", (model_id,))
        await db.executemany(
            "INSERT INTO trigger_words (model_id, word) VALUES (?, ?)",
            [(model_id, w) for w in words],
        )
        await db.commit()


async def set_tags(model_id: int, tags: list[str]):
    async with get_db() as db:
        await db.execute("DELETE FROM tags WHERE model_id = ?", (model_id,))
        await db.executemany(
            "INSERT INTO tags (model_id, tag) VALUES (?, ?)",
            [(model_id, t) for t in tags],
        )
        await db.commit()


async def add_media(model_id: int, media_type: str, local_path: str) -> int:
    async with get_db() as db:
        cursor = await db.execute(
            "INSERT INTO model_media (model_id, media_type, local_path) VALUES (?, ?, ?)",
            (model_id, media_type, local_path),
        )
        await db.commit()
        return cursor.lastrowid


async def get_model_by_filename(filename: str) -> dict | None:
    async with get_db() as db:
        row = await (await db.execute("SELECT * FROM models WHERE filename = ?", (filename,))).fetchone()
        if not row:
            return None
        model = dict(row)
        words = await (await db.execute(
            "SELECT word FROM trigger_words WHERE model_id = ?", (model["id"],)
        )).fetchall()
        media = await (await db.execute(
            "SELECT id, media_type, local_path FROM model_media WHERE model_id = ?", (model["id"],)
        )).fetchall()
        tags = await (await db.execute(
            "SELECT tag FROM tags WHERE model_id = ?", (model["id"],)
        )).fetchall()
        model["trigger_words"] = [r["word"] for r in words]
        model["tags"] = [r["tag"] for r in tags]
        model["media"] = [dict(r) for r in media]
        return model


async def get_metadata_by_filenames(filenames: list[str]) -> dict[str, dict]:
    if not filenames:
        return {}
    async with get_db() as db:
        placeholders = ",".join("?" * len(filenames))
        rows = await (await db.execute(
            f"SELECT * FROM models WHERE filename IN ({placeholders})", filenames
        )).fetchall()
        result = {}
        for row in rows:
            m = dict(row)
            words = await (await db.execute(
                "SELECT word FROM trigger_words WHERE model_id = ?", (m["id"],)
            )).fetchall()
            media = await (await db.execute(
                "SELECT id, media_type, local_path FROM model_media WHERE model_id = ?", (m["id"],)
            )).fetchall()
            tags = await (await db.execute(
                "SELECT tag FROM tags WHERE model_id = ?", (m["id"],)
            )).fetchall()
            m["trigger_words"] = [r["word"] for r in words]
            m["tags"] = [r["tag"] for r in tags]
            m["media"] = [dict(r) for r in media]
            result[m["filename"]] = m
        return result


async def update_model_meta(filename: str, description: str, trigger_words: list[str]):
    async with get_db() as db:
        await db.execute(
            "UPDATE models SET description = ? WHERE filename = ?", (description, filename)
        )
        row = await (await db.execute("SELECT id FROM models WHERE filename = ?", (filename,))).fetchone()
        if row:
            await db.execute("DELETE FROM trigger_words WHERE model_id = ?", (row["id"],))
            await db.executemany(
                "INSERT INTO trigger_words (model_id, word) VALUES (?, ?)",
                [(row["id"], w) for w in trigger_words],
            )
        await db.commit()
