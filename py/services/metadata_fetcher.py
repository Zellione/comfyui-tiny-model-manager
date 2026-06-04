"""Fetches and stores model metadata after a download completes."""

import asyncio
import hashlib
import os
import re
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
    display_name = ""

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
                display_name = meta.display_name
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

    # Derive catalog entry fields
    if platform == "civitai" and civitai_model_id:
        source_page_id = civitai_model_id
        source_page_url = f"https://civitai.com/models/{civitai_model_id}"
    elif platform == "huggingface" and source_id:
        source_page_id = source_id
        source_page_url = f"https://huggingface.co/{source_id}"
    else:
        source_page_id = ""
        source_page_url = ""

    if source_page_id:
        thumbnail_url = (await model_repo.get_first_image_path(model_id)) or ""
        try:
            catalog_entry_id = await model_repo.upsert_catalog_entry(
                source_platform=platform,
                source_page_id=source_page_id,
                source_page_url=source_page_url,
                display_name=display_name,
                thumbnail_url=thumbnail_url,
                base_model=base_model,
                description=description,
                trigger_words=trigger_words,
                tags=tags,
                media_hash=media_hash,
            )
            await model_repo.set_model_catalog_entry(filename, catalog_entry_id)
        except Exception:
            catalog_entry_id = 0

        await _fetch_and_store_repo_files(
            filename,
            model_type,
            platform,
            source_id,
            civitai_model_id=civitai_model_id,
            catalog_entry_id=catalog_entry_id if source_page_id else 0,
        )
    else:
        await _fetch_and_store_repo_files(
            filename, model_type, platform, source_id, civitai_model_id=civitai_model_id
        )


async def _fetch_and_store_repo_files(
    _filename: str,
    model_type: str,
    platform: str,
    source_id: str,
    civitai_model_id: str = "",
    catalog_entry_id: int = 0,
):
    """Fetches sibling files from the upstream API and stores them in repo_files. Silent on failure."""
    if not catalog_entry_id:
        return
    provider = get_provider(platform)
    if not provider or not source_id:
        return
    try:
        if platform == "civitai":
            from .providers.civitai_provider import CivitaiProvider

            civitai = CivitaiProvider()
            if civitai_model_id:
                model_data = await civitai.get_model_versions(int(civitai_model_id))
                source_base = f"https://civitai.com/models/{civitai_model_id}"
                files = []
                # Iterate newest-first so that when filenames collide across versions
                # the UPSERT leaves the newest version's download_url in place.
                for version in model_data.get("versions", []):
                    vid = version.get("id")
                    page_url = f"{source_base}?modelVersionId={vid}" if vid else source_base
                    for f in version.get("files", []):
                        if f.get("type") != "Model":
                            continue
                        files.append(
                            {
                                "filename": f.get("name", ""),
                                "size_bytes": int(f.get("sizeKB", 0) * 1024),
                                "download_url": f.get("downloadUrl", ""),
                                "source_page_url": page_url,
                            }
                        )
            else:
                files = await civitai.get_version_files(int(source_id))
        elif platform == "huggingface":
            from .providers.huggingface_provider import HuggingFaceProvider

            hf = HuggingFaceProvider()
            raw = await hf.get_model_files(source_id)
            files = hf._model_files_for_storage(source_id, raw)
        else:
            return
        await model_repo.upsert_repo_files(catalog_entry_id, model_type, files)
    except Exception:
        pass


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


_SAFE_EXT = re.compile(r"[^a-z0-9]")


async def _fetch_url_to_file(
    client: httpx.AsyncClient, url: str, dest_dir: str, index: int
) -> tuple[str, str] | None:
    """Download url to dest_dir/{index}.{ext}. Returns (dest, ext) or None on failure.

    The extension is sanitised to alphanumeric characters only so that a
    crafted URL cannot inject path separators into dest_dir.
    """
    try:
        raw = url.rsplit(".", 1)[-1].split("?")[0].lower()
        ext = _SAFE_EXT.sub("", raw)[:10] or "jpg"
        dest = os.path.join(dest_dir, f"{index}.{ext}")
        if not os.path.isfile(dest):
            resp = await client.get(url)
            resp.raise_for_status()
            with open(dest, "wb") as f:  # noqa: S603
                f.write(resp.content)
        return dest, ext
    except Exception:
        return None


async def _iter_downloaded_urls(media_hash: str, urls: list[str]) -> list[tuple[str, str]]:
    """Download up to 5 URLs into the media hash dir; return (dest, ext) pairs."""
    dest_dir = os.path.join(cfg.media_dir(), media_hash)
    os.makedirs(dest_dir, exist_ok=True)
    results: list[tuple[str, str]] = []
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        for i, url in enumerate(urls[:5]):
            result = await _fetch_url_to_file(client, url, dest_dir, i)
            if result:
                results.append(result)
    return results


async def _download_images(model_id: int, media_hash: str, urls: list[str]):
    if not urls:
        return
    for dest, ext in await _iter_downloaded_urls(media_hash, urls):
        media_type = "video" if ext in ("mp4", "webm", "mov") else "image"
        await model_repo.add_media(model_id, media_type, dest)


def catalog_media_hash(platform: str, page_id: str) -> str:
    """Stable media-hash for a catalog page (independent of any installed file)."""
    return hashlib.sha256(f"catalog:{platform}:{page_id}".encode()).hexdigest()


async def _download_catalog_images(media_hash: str, urls: list[str]) -> str:
    """Download gallery images into the catalog media dir. Returns the first image path."""
    results = await _iter_downloaded_urls(media_hash, urls)
    return results[0][0] if results else ""


async def refetch_catalog_metadata(platform: str, page_id: str) -> dict | None:
    """Re-fetch source-page metadata for a catalog entry independent of installed files.

    Works with zero files installed. Returns the refreshed catalog entry, or None if the
    platform/page could not be resolved.
    """
    provider = get_provider(platform)
    if not provider:
        return None

    source_id = ""
    source_page_url = ""
    if platform == "huggingface":
        source_id = page_id
        source_page_url = f"https://huggingface.co/{page_id}"
    elif platform == "civitai":
        from .providers.civitai_provider import CivitaiProvider

        versions = (await CivitaiProvider().get_model_versions(int(page_id))).get("versions", [])
        if not versions:
            return None
        source_id = str(versions[0].get("id", ""))
        source_page_url = f"https://civitai.com/models/{page_id}"
    else:
        return None

    meta = await provider.fetch_metadata(source_id)
    media_hash = catalog_media_hash(platform, page_id)
    thumbnail_url = await _download_catalog_images(media_hash, meta.image_urls)

    await model_repo.upsert_catalog_entry(
        source_platform=platform,
        source_page_id=page_id,
        source_page_url=source_page_url,
        display_name=meta.display_name,
        thumbnail_url=thumbnail_url,
        base_model=meta.base_model,
        description=meta.description,
        trigger_words=meta.trigger_words,
        tags=meta.tags,
        media_hash=media_hash,
    )
    return await model_repo.get_catalog_entry(platform, page_id)
