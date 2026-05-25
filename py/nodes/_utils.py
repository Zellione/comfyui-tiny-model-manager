import asyncio


def get_trigger_words_sync(filename: str) -> str:
    try:
        from ..db import model_repo

        async def _fetch():
            meta = await model_repo.get_model_by_filename(filename)
            if meta:
                return ", ".join(meta.get("trigger_words", []))
            return ""

        loop = asyncio.get_event_loop()
        if loop.is_running():
            return ""
        return loop.run_until_complete(_fetch())
    except Exception:
        return ""
