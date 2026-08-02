"""Fetches and stores model metadata after a download completes."""

import asyncio
import hashlib
import logging
import os
import shutil
from pathlib import Path

import httpx

from .. import config as cfg
from ..db import model_repo
from ..video_poster import extract_video_poster
from . import media_cleanup
from .providers import get_provider
from .providers.base import ProviderMetadata
from .url_guard import guarded_stream, is_allowed_url

_log = logging.getLogger("tiny-model-manager")


def _compute_media_hash(platform: str, source_id: str, filename: str) -> str:
    key = f"{platform}:{source_id}" if (platform and source_id) else filename
    return hashlib.sha1(key.encode()).hexdigest()


# Shared with the cleanup service so both sides agree on the layout and the guard.
_media_subdir = media_cleanup.media_subdir


async def fetch_metadata_only(platform: str, source_id: str) -> ProviderMetadata:
    """Fetch metadata from the upstream provider without persisting anything.

    Raises RuntimeError if the provider is unknown or all 3 attempts fail.
    """
    provider = get_provider(platform)
    if not provider:
        raise RuntimeError(f"Unknown platform: {platform!r}")
    last_exc: Exception = RuntimeError("No attempts made")
    for attempt in range(3):
        try:
            return await provider.fetch_metadata(source_id)
        except Exception as exc:
            last_exc = exc
            if attempt < 2:
                await asyncio.sleep(1)
    raise last_exc


async def _fetch_provider_metadata(provider, source_id: str, filename: str) -> ProviderMetadata:
    """Fetch metadata with up to 3 attempts; notify and return empty defaults on failure."""
    for attempt in range(3):
        try:
            return await provider.fetch_metadata(source_id)
        except Exception:
            if attempt < 2:
                await asyncio.sleep(1)

    from .backend_notifier import push as notify

    notify(
        "error",
        f"Metadata fetch failed for '{filename}'. "
        "Open the model detail page and use 'Re-fetch metadata' to try again.",
    )
    return ProviderMetadata()


def _derive_catalog_source(platform: str, civitai_model_id: str, source_id: str) -> tuple[str, str]:
    """Return (source_page_id, source_page_url) for the catalog entry, or ('', '')."""
    if platform == "civitai" and civitai_model_id:
        return civitai_model_id, f"https://civitai.com/models/{civitai_model_id}"
    if platform == "huggingface" and source_id:
        return source_id, f"https://huggingface.co/{source_id}"
    return "", ""


async def _store_catalog_entry(
    filename: str,
    platform: str,
    source_page_id: str,
    source_page_url: str,
    media_hash: str,
    model_id: int,
    meta: ProviderMetadata,
) -> int:
    """Upsert the catalog entry and link the model to it; return its id (0 on failure)."""
    thumbnail_url = (await model_repo.get_first_image_path(model_id)) or ""
    try:
        catalog_entry_id = await model_repo.upsert_catalog_entry(
            source_platform=platform,
            source_page_id=source_page_id,
            source_page_url=source_page_url,
            display_name=meta.display_name,
            thumbnail_url=thumbnail_url,
            base_model=meta.base_model,
            description=meta.description,
            trigger_words=meta.trigger_words,
            tags=meta.tags,
            media_hash=media_hash,
            readme_html=meta.readme_html,
        )
        await model_repo.set_model_catalog_entry(filename, catalog_entry_id)
        return catalog_entry_id
    except Exception:
        _log.warning("Failed to store catalog entry for %s", filename, exc_info=True)
        return 0


async def fetch_and_store(
    filename: str,
    model_type: str,
    platform: str,
    source_id: str,
    skip_media: bool = False,
    hint_base_model: str = "",
):
    provider = get_provider(platform)
    if provider and source_id:
        meta = await _fetch_provider_metadata(provider, source_id, filename)
    else:
        meta = ProviderMetadata()
    if not meta.base_model and hint_base_model:
        meta.base_model = hint_base_model

    settings = cfg.load_settings()
    if settings.get("organize_into_subfolders"):
        try:
            from .reorganizer import _move_to_subfolder

            filename = _move_to_subfolder(filename, model_type, meta.base_model)
        except Exception:
            _log.warning("Failed to reorganize %s into subfolder", filename, exc_info=True)

    media_hash = _compute_media_hash(platform, source_id, filename)
    model_id = await model_repo.upsert_model_with_meta(
        filename,
        model_type,
        platform,
        source_id,
        meta.description,
        meta.trigger_words,
        meta.tags,
        base_model=meta.base_model,
        civitai_model_id=meta.civitai_model_id,
        media_hash=media_hash,
        readme_html=meta.readme_html,
        civitai_version_name=meta.civitai_version_name,
    )
    if not skip_media:
        await _download_images(model_id, media_hash, meta.image_urls)

    source_page_id, source_page_url = _derive_catalog_source(
        platform, meta.civitai_model_id, source_id
    )
    catalog_entry_id = 0
    if source_page_id:
        catalog_entry_id = await _store_catalog_entry(
            filename, platform, source_page_id, source_page_url, media_hash, model_id, meta
        )

    await _fetch_and_store_repo_files(
        filename,
        model_type,
        platform,
        source_id,
        civitai_model_id=meta.civitai_model_id,
        catalog_entry_id=catalog_entry_id,
    )


def _civitai_repo_files(model_data: dict, source_base: str) -> list[dict]:
    """Flatten a CivitAI model's versions into repo_file dicts (newest version first)."""
    files: list[dict] = []
    # Iterate newest-first so that when filenames collide across versions
    # the UPSERT leaves the newest version's download_url in place.
    for version in model_data.get("versions", []):
        vid = version.get("id")
        page_url = f"{source_base}?modelVersionId={vid}" if vid else source_base
        version_name = version.get("name", "")
        for f in version.get("files", []):
            if f.get("type") != "Model":
                continue
            files.append(
                {
                    "filename": f.get("name", ""),
                    "size_bytes": int(f.get("sizeKB", 0) * 1024),
                    "download_url": f.get("downloadUrl", ""),
                    "source_page_url": page_url,
                    "civitai_version_name": version_name,
                }
            )
    return files


async def _fetch_repo_files(
    platform: str, source_id: str, civitai_model_id: str
) -> list[dict] | None:
    """Fetch sibling files for the model from the upstream provider, or None if unsupported."""
    from . import auto_migrator

    if platform == "civitai":
        from .providers.civitai_provider import CivitaiProvider

        civitai = CivitaiProvider()
        if civitai_model_id:
            model_data = await civitai.get_model_versions(int(civitai_model_id))
            # F-92: this response carries per-file SHA-256 hashes; the flattened
            # get_version_files() fallback below does not, so only hook here.
            auto_migrator.schedule(auto_migrator.from_civitai_versions(model_data))
            return _civitai_repo_files(model_data, f"https://civitai.com/models/{civitai_model_id}")
        return await civitai.get_version_files(int(source_id))
    if platform == "huggingface":
        from .providers.huggingface_provider import HuggingFaceProvider

        hf = HuggingFaceProvider()
        raw = await hf.get_model_files(source_id)
        auto_migrator.schedule(auto_migrator.from_hf_files(source_id, raw))
        return hf._model_files_for_storage(source_id, raw)
    return None


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
        files = await _fetch_repo_files(platform, source_id, civitai_model_id)
        if files is None:
            return
        await model_repo.upsert_repo_files(catalog_entry_id, model_type, files)
    except Exception:
        _log.warning("Failed to fetch/store repo files for %s", source_id, exc_info=True)


def _remove_dir_if_empty(path: str | None) -> None:
    """Remove ``path`` if it exists and is an empty directory; ignore errors."""
    if not path or not os.path.isdir(path):
        return
    try:
        if not os.listdir(path):
            os.rmdir(path)
    except Exception:
        pass


async def _migrate_model_media(db, row) -> None:
    """Move one model's media files into its hash directory and update DB paths."""
    media_hash = _compute_media_hash(
        row["source_platform"] or "", row["source_id"] or "", row["filename"]
    )
    new_dir = _media_subdir(media_hash)
    os.makedirs(new_dir, exist_ok=True)

    media_rows = await (
        await db.execute("SELECT id, local_path FROM model_media WHERE model_id = ?", (row["id"],))
    ).fetchall()

    old_dir = None
    for media_row in media_rows:
        old_path = media_row["local_path"]
        filename = Path(old_path).name
        if not filename:
            continue
        new_path_candidate = os.path.realpath(os.path.join(new_dir, filename))
        if not new_path_candidate.startswith(os.path.realpath(new_dir) + os.sep):
            continue
        new_path = new_path_candidate
        if os.path.isfile(old_path) and old_path != new_path:
            try:
                shutil.move(old_path, new_path)
            except Exception:
                pass
            old_dir = os.path.dirname(old_path)
        await db.execute(
            "UPDATE model_media SET local_path = ? WHERE id = ?", (new_path, media_row["id"])
        )

    await db.execute("UPDATE models SET media_hash = ? WHERE id = ?", (media_hash, row["id"]))
    _remove_dir_if_empty(old_dir)


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
            await _migrate_model_media(db, row)

        await db.commit()


_CONTENT_TYPE_EXT: dict[str, str] = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "image/gif": "gif",
    "image/avif": "avif",
    "video/mp4": "mp4",
    "video/webm": "webm",
    "video/quicktime": "mov",
}


async def _fetch_url_to_file(
    client: httpx.AsyncClient, url: str, dest_dir: str, index: int
) -> tuple[str, str] | None:
    """Download url to dest_dir/{index}.{ext}. Returns (dest, ext) or None on failure."""
    try:
        existing = next(Path(dest_dir).glob(f"{index}.*"), None)
        if existing:
            return str(existing), existing.suffix.lstrip(".")
        # guarded_stream re-checks every redirect hop; a media URL that bounces off the
        # allowlist raises and is swallowed below, dropping that one preview.
        async with guarded_stream(client, "GET", url) as resp:
            resp.raise_for_status()
            content_type = resp.headers.get("content-type", "").split(";")[0].strip().lower()
            content = await resp.aread()
        ext = _CONTENT_TYPE_EXT.get(content_type, "jpg")
        dest = os.path.join(dest_dir, f"{index}.{ext}")
        await asyncio.to_thread(Path(dest).write_bytes, content)
        return dest, ext
    except Exception:
        return None


async def _iter_downloaded_urls(media_hash: str, urls: list[str]) -> list[tuple[str, str]]:
    """Download up to 5 URLs into the media hash dir; return (dest, ext) pairs.

    URLs are fetched server-side, so each is confined to a trusted provider host
    (SSRF guard) before any request is made.
    """
    dest_dir = _media_subdir(media_hash)
    os.makedirs(dest_dir, exist_ok=True)
    safe_urls = [u for u in urls if is_allowed_url(u)]
    results: list[tuple[str, str]] = []
    async with httpx.AsyncClient(timeout=30) as client:
        for i, url in enumerate(safe_urls[:5]):
            result = await _fetch_url_to_file(client, url, dest_dir, i)
            if result:
                results.append(result)
    return results


async def _download_images(model_id: int, media_hash: str, urls: list[str]):
    if not urls:
        return
    results = await _iter_downloaded_urls(media_hash, urls)
    first_video: str | None = None
    has_image = False
    for dest, ext in results:
        media_type = "video" if ext in _VIDEO_EXTS else "image"
        if media_type == "image":
            has_image = True
        elif first_video is None:
            first_video = dest
        await model_repo.add_media(model_id, media_type, dest)
    if not has_image and first_video:
        poster = await asyncio.to_thread(extract_video_poster, first_video)
        if poster:
            await model_repo.add_media(model_id, "image", poster)


def catalog_media_hash(platform: str, page_id: str) -> str:
    """Stable media-hash for a catalog page (independent of any installed file)."""
    return hashlib.sha256(f"catalog:{platform}:{page_id}".encode()).hexdigest()


_VIDEO_EXTS = {"mp4", "webm", "mov"}


async def _download_catalog_images(media_hash: str, urls: list[str]) -> str:
    """Download gallery images into the catalog media dir. Returns the first image path."""
    results = await _iter_downloaded_urls(media_hash, urls)
    first_video: str | None = None
    for path, ext in results:
        if ext not in _VIDEO_EXTS:
            return path
        if first_video is None:
            first_video = path
    if first_video:
        poster = await asyncio.to_thread(extract_video_poster, first_video)
        if poster:
            return poster
    return ""


async def _fetch_hf_repo_files_safe(source_id: str) -> list[dict] | None:
    try:
        return await _fetch_repo_files("huggingface", source_id, "")
    except Exception:
        _log.warning("Failed to fetch HuggingFace repo files", exc_info=True)
        return None


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
    version_name_map: dict[str, str] = {}
    repo_files: list[dict] | None = None
    if platform == "huggingface":
        source_id = page_id
        source_page_url = f"https://huggingface.co/{page_id}"
    elif platform == "civitai":
        from .providers.civitai_provider import CivitaiProvider

        model_data = await CivitaiProvider().get_model_versions(int(page_id))
        versions = model_data.get("versions", [])
        if not versions:
            return None
        from . import auto_migrator

        auto_migrator.schedule(auto_migrator.from_civitai_versions(model_data))
        source_id = str(versions[0].get("id", ""))
        source_page_url = f"https://civitai.com/models/{page_id}"
        version_name_map = {str(v["id"]): v.get("name", "") for v in versions}
        repo_files = _civitai_repo_files(model_data, source_page_url)
    else:
        return None

    meta = await provider.fetch_metadata(source_id)
    media_hash = catalog_media_hash(platform, page_id)
    thumbnail_url = await _download_catalog_images(media_hash, meta.image_urls)

    catalog_entry_id = await model_repo.upsert_catalog_entry(
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
        readme_html=meta.readme_html,
    )

    if platform == "huggingface":
        repo_files = await _fetch_hf_repo_files_safe(source_id)

    if repo_files is not None:
        model_type = await model_repo.get_model_type_for_catalog(catalog_entry_id)
        if model_type:
            try:
                await model_repo.upsert_repo_files(catalog_entry_id, model_type, repo_files)
            except Exception:
                _log.warning("Failed to store catalog repo files", exc_info=True)

    if version_name_map:
        await model_repo.update_version_names_for_catalog(platform, page_id, version_name_map)
    return await model_repo.get_catalog_entry(platform, page_id)
