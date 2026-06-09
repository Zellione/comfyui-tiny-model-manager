from .database import get_db


async def list_keywords() -> list[dict]:
    async with get_db() as db:
        cur = await db.execute(
            "SELECT id, keyword, base_model, model_type, sort_order"
            " FROM filename_keywords ORDER BY sort_order, id"
        )
        rows = await cur.fetchall()
        return [dict(r) for r in rows]


async def create_keyword(keyword: str, base_model: str | None, model_type: str | None) -> int:
    async with get_db() as db:
        max_cur = await db.execute("SELECT COALESCE(MAX(sort_order), 0) FROM filename_keywords")
        row = await max_cur.fetchone()
        max_order: int = row[0] if row else 0
        cur = await db.execute(
            "INSERT INTO filename_keywords (keyword, base_model, model_type, sort_order)"
            " VALUES (?, ?, ?, ?)",
            (keyword.lower().strip(), base_model or None, model_type or None, max_order + 10),
        )
        await db.commit()
        return cur.lastrowid or 0


async def update_keyword(
    keyword_id: int, keyword: str, base_model: str | None, model_type: str | None
) -> bool:
    async with get_db() as db:
        cur = await db.execute(
            "UPDATE filename_keywords SET keyword = ?, base_model = ?, model_type = ? WHERE id = ?",
            (keyword.lower().strip(), base_model or None, model_type or None, keyword_id),
        )
        await db.commit()
        return cur.rowcount > 0


async def delete_keyword(keyword_id: int) -> bool:
    async with get_db() as db:
        cur = await db.execute("DELETE FROM filename_keywords WHERE id = ?", (keyword_id,))
        await db.commit()
        return cur.rowcount > 0
