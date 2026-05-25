"""Fetches and stores model metadata after a download completes."""
import os
import httpx
from .. import config as cfg
from ..db import model_repo
from . import civitai, huggingface


async def fetch_and_store(filename: str, model_type: str, platform: str, source_id: str):
    description = ""
    trigger_words: list[str] = []
    image_urls: list[str] = []

    try:
        if platform == "civitai" and source_id:
            meta = await civitai.get_version_metadata(int(source_id))
            description = meta["description"]
            trigger_words = meta["trigger_words"]
            image_urls = meta["image_urls"]
        elif platform == "huggingface" and source_id:
            meta = await huggingface.get_model_card(source_id)
            description = meta.get("description") or ""
            trigger_words = meta.get("trigger_words", [])
            image_urls = meta.get("image_urls", [])
    except Exception:
        pass  # metadata fetch failure should not break the download

    model_id = await model_repo.upsert_model(
        filename, model_type, platform, source_id, description
    )
    await model_repo.set_trigger_words(model_id, trigger_words)
    await _download_images(model_id, filename, image_urls)


async def _download_images(model_id: int, filename: str, urls: list[str]):
    if not urls:
        return
    base_name = os.path.splitext(os.path.basename(filename))[0]
    dest_dir = os.path.join(cfg.media_dir(), base_name)
    os.makedirs(dest_dir, exist_ok=True)

    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        for i, url in enumerate(urls[:5]):
            try:
                ext = url.rsplit(".", 1)[-1].split("?")[0] or "jpg"
                dest = os.path.join(dest_dir, f"{i}.{ext}")
                resp = await client.get(url)
                resp.raise_for_status()
                with open(dest, "wb") as f:
                    f.write(resp.content)
                media_type = "video" if ext in ("mp4", "webm", "mov") else "image"
                await model_repo.add_media(model_id, media_type, dest)
            except Exception:
                continue
