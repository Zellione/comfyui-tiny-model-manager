"""Fetches and stores model metadata after a download completes."""

import asyncio
import hashlib
import os
import shutil

import httpx

from .. import config as cfg
from ..db import model_repo
from .providers import get_provider


def _compute_media_hash(platform: str, source_id: str, filename: str) -> str:
    key = f"{platform}:{source_id}" if (platform and source_id) else filename
    return hashlib.sha1(key.encode()).hexdigest()


async def fetch_and_store(
    filename: str, model_type: str, platform: str, source_id: str, skip_media: bool = False
):
    description = ""
    trigger_words: list[str] = []
    image_urls: list[str] = []
    tags: list[str] = []
    base_model = ""
    civitai_model_id = ""

    provider = get_provider(platform)
    if provider and source_id:
        fetch_ok = False
        for attempt in range(3):
            try:
                meta = await provider.fetch_metadata(source_id)
                description = meta.description
                trigger_words = meta.trigger_words
                image_urls = meta.image_urls
                tags = meta.tags
                base_model = meta.base_model
                civitai_model_id = meta.civitai_model_id
                fetch_ok = True
                break
            except Exception:
                if attempt < 2:
                    await asyncio.sleep(1)

        if not fetch_ok:
            from .backend_notifier import push as notify

            notify(
                "error",
                f"Metadata fetch failed for '{filename}'. "
                "Open the model detail page and use 'Re-fetch metadata' to try again.",
            )

    settings = cfg.load_settings()
    if settings.get("organize_into_subfolders"):
        try:
            from .reorganizer import _move_to_subfolder

            filename = await _move_to_subfolder(filename, model_type, base_model)
        except Exception:
            pass

    media_hash = _compute_media_hash(platform, source_id, filename)
    model_id = await model_repo.upsert_model_with_meta(
        filename,
        model_type,
        platform,
        source_id,
        description,
        trigger_words,
        tags,
        base_model=base_model,
        civitai_model_id=civitai_model_id,
        media_hash=media_hash,
    )
    if not skip_media:
        await _download_images(model_id, media_hash, image_urls)


async def migrate_existing_media():
    """One-time startup migration: moves media from data/media/<basename>/ to data/media/<hash>/."""
    from ..db.database import get_db

    async with get_db() as db:
        rows = await (
            await db.execute("""
            SELECT DISTINCT m.id, m.filename, m.source_platform, m.source_id
            FROM models m
            JOIN model_media mm ON mm.model_id = m.id
            WHERE m.media_hash = ''
        """)
        ).fetchall()

        for row in rows:
            media_hash = _compute_media_hash(
                row["source_platform"] or "", row["source_id"] or "", row["filename"]
            )
            new_dir = os.path.join(cfg.media_dir(), media_hash)
            os.makedirs(new_dir, exist_ok=True)

            media_rows = await (
                await db.execute(
                    "SELECT id, local_path FROM model_media WHERE model_id = ?", (row["id"],)
                )
            ).fetchall()

            old_dir = None
            for media_row in media_rows:
                old_path = media_row["local_path"]
                new_path = os.path.join(new_dir, os.path.basename(old_path))
                if os.path.isfile(old_path) and old_path != new_path:
                    try:
                        shutil.move(old_path, new_path)
                    except Exception:
                        pass
                    old_dir = os.path.dirname(old_path)
                await db.execute(
                    "UPDATE model_media SET local_path = ? WHERE id = ?",
                    (new_path, media_row["id"]),
                )

            await db.execute(
                "UPDATE models SET media_hash = ? WHERE id = ?", (media_hash, row["id"])
            )

            if old_dir and os.path.isdir(old_dir):
                try:
                    if not os.listdir(old_dir):
                        os.rmdir(old_dir)
                except Exception:
                    pass

        await db.commit()


async def _download_images(model_id: int, media_hash: str, urls: list[str]):
    if not urls:
        return
    dest_dir = os.path.join(cfg.media_dir(), media_hash)
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
