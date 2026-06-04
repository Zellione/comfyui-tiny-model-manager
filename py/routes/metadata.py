import asyncio as _asyncio
import os
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from aiohttp import web

from ..db import model_repo

_TTL_SECONDS = 300  # 5 minutes


@dataclass
class _RefetchEntry:
    fetched_at: datetime
    old: dict
    new_data: dict

    @property
    def expires_at(self) -> datetime:
        return self.fetched_at + timedelta(seconds=_TTL_SECONDS)

    @property
    def is_expired(self) -> bool:
        return datetime.now(UTC) > self.expires_at

    def expires_at_iso(self) -> str:
        return self.expires_at.strftime("%Y-%m-%dT%H:%M:%SZ")


_refetch_cache: dict[str, _RefetchEntry] = {}
_cleanup_task: _asyncio.Task | None = None


async def _cleanup_cache_loop():
    while True:
        await _asyncio.sleep(60)
        expired = [k for k, v in _refetch_cache.items() if v.is_expired]
        for k in expired:
            _refetch_cache.pop(k, None)


def _ensure_cleanup_running() -> None:
    global _cleanup_task
    if _cleanup_task is None or _cleanup_task.done():
        try:
            loop = _asyncio.get_running_loop()
            _cleanup_task = loop.create_task(_cleanup_cache_loop())
        except RuntimeError:
            pass  # no running loop — task will be started on first real request


def _parse_source_url(url: str) -> tuple[str, str, str]:
    """Return (platform, source_id, civitai_model_id) or ('', '', '') if unrecognised."""
    m = re.match(r"https?://(?:www\.)?civitai\.com/models/(\d+)", url)
    if m:
        return "civitai", "", m.group(1)
    m = re.match(r"https?://huggingface\.co/([^/?#]+/[^/?#]+)", url)
    if m:
        return "huggingface", m.group(1), ""
    return "", "", ""


def _resolve_file_size(model_type: str, path: str) -> int:
    """Return os.path.getsize for the model file, or 0 if the file cannot be found."""
    import folder_paths

    from .. import config as cfg

    candidates: list[str] = []
    dirs, _ = folder_paths.folder_names_and_paths.get(model_type, ([], {}))
    for base_dir in dirs:
        candidates.append(os.path.join(base_dir, path))
    models_dir = getattr(folder_paths, "models_dir", None)
    if models_dir:
        candidates.append(os.path.join(models_dir, model_type, path))
    candidates.append(os.path.join(cfg.data_dir(), "models", model_type, path))

    for full in candidates:
        try:
            return os.path.getsize(full)
        except OSError:
            pass
    return 0


def _find_file_on_disk(model_type: str, model_dir: str, filename: str) -> str:
    """Return the absolute path of a file if it exists, or empty string if not found."""
    import folder_paths

    from .. import config as cfg

    candidates: list[str] = []
    dirs, _ = folder_paths.folder_names_and_paths.get(model_type, ([], {}))
    for base_dir in dirs:
        candidates.append(os.path.join(base_dir, model_dir, filename))
    models_dir = getattr(folder_paths, "models_dir", None)
    if models_dir:
        candidates.append(os.path.join(models_dir, model_type, model_dir, filename))
    candidates.append(os.path.join(cfg.data_dir(), "models", model_type, model_dir, filename))
    for full in candidates:
        if os.path.isfile(full):
            return full
    return ""


def _file_exists_on_disk(model_type: str, model_dir: str, filename: str) -> bool:
    return bool(_find_file_on_disk(model_type, model_dir, filename))


def _get_file_mtime(model_type: str, model_dir: str, filename: str) -> float | None:
    full = _find_file_on_disk(model_type, model_dir, filename)
    if full:
        try:
            return os.path.getmtime(full)
        except OSError:
            pass
    return None


def _derive_source_url(source_platform: str, source_id: str, civitai_model_id: str) -> str:
    if source_platform == "civitai" and civitai_model_id:
        return f"https://civitai.com/models/{civitai_model_id}"
    if source_platform == "huggingface" and source_id:
        return f"https://huggingface.co/{source_id}"
    return ""


def add_metadata_routes(routes):

    @routes.get("/tiny-model-manager/api/models/{model_type}/{path:.*}/metadata")
    async def get_metadata(request):
        path = request.match_info["path"]
        model_type = request.match_info["model_type"]
        try:
            meta = await model_repo.get_model_by_filename(path)
            size_bytes = _resolve_file_size(model_type, path)
            if not meta:
                return web.json_response(
                    {
                        "success": True,
                        "data": {
                            "description": "",
                            "trigger_words": [],
                            "tags": [],
                            "media": [],
                            "base_model": "",
                            "source_platform": "",
                            "source_url": "",
                            "size_bytes": size_bytes,
                        },
                    }
                )
            source_url = _derive_source_url(
                meta.get("source_platform", ""),
                meta.get("source_id", ""),
                meta.get("civitai_model_id", ""),
            )
            return web.json_response(
                {
                    "success": True,
                    "data": {
                        "description": meta.get("description", ""),
                        "trigger_words": meta.get("trigger_words", []),
                        "tags": meta.get("tags", []),
                        "media": meta.get("media", []),
                        "base_model": meta.get("base_model", ""),
                        "source_platform": meta.get("source_platform", ""),
                        "source_url": source_url,
                        "size_bytes": size_bytes,
                    },
                }
            )
        except Exception as exc:
            return web.json_response({"success": False, "error": str(exc)}, status=500)

    @routes.put("/tiny-model-manager/api/models/{model_type}/{path:.*}/metadata")
    async def update_metadata(request):
        path = request.match_info["path"]
        model_type = request.match_info["model_type"]
        try:
            body = await request.json()
            # None means "not present in request — don't touch that field"
            description = body.get("description")
            trigger_words = body.get("trigger_words")
            tags = body.get("tags")
            new_base_model = body.get("base_model")

            if new_base_model is not None:
                from .. import config as cfg
                from ..services.reorganizer import _move_to_subfolder

                settings = cfg.load_settings()
                if settings.get("organize_into_subfolders"):
                    existing = await model_repo.get_model_by_filename(path)
                    old_base_model = (existing or {}).get("base_model", "")
                    if old_base_model != new_base_model:
                        try:
                            new_path = await _move_to_subfolder(path, model_type, new_base_model)
                            if new_path != path:
                                await model_repo.update_model_filename(path, new_path)
                                path = new_path
                        except Exception:
                            pass

            await model_repo.update_model_meta(
                path,
                description=description,
                trigger_words=trigger_words,
                tags=tags,
                base_model=new_base_model,
                model_type=model_type,
            )
            return web.json_response({"success": True, "new_path": path})
        except Exception as exc:
            return web.json_response({"success": False, "error": str(exc)}, status=500)

    @routes.post("/tiny-model-manager/api/models/{model_type}/{path:.*}/refetch")
    async def refetch_metadata(request):
        path = request.match_info["path"]
        model_type = request.match_info["model_type"]
        try:
            # If the file has been removed from disk, prune the stale DB record rather
            # than re-fetching metadata for a model that no longer exists locally.
            if not _file_exists_on_disk(model_type, os.path.dirname(path), os.path.basename(path)):
                await model_repo.delete_model_record(path)
                return web.json_response({"success": True, "data": {"removed": True}})

            info = await model_repo.get_model_source_info(path)
            if not info or not info.get("source_platform") or not info.get("source_id"):
                return web.json_response(
                    {"success": False, "error": "No source info stored for this model"}, status=400
                )
            from ..services import metadata_fetcher

            existing = await model_repo.get_model_by_filename(path)
            has_media = bool(existing and existing.get("media"))
            await metadata_fetcher.fetch_and_store(
                path,
                info["model_type"],
                info["source_platform"],
                info["source_id"],
                skip_media=has_media,
            )
            meta = await model_repo.get_model_by_filename(path) or {}
            source_url = _derive_source_url(
                meta.get("source_platform", ""),
                meta.get("source_id", ""),
                meta.get("civitai_model_id", ""),
            )
            return web.json_response(
                {
                    "success": True,
                    "data": {
                        "removed": False,
                        "description": meta.get("description", ""),
                        "trigger_words": meta.get("trigger_words", []),
                        "tags": meta.get("tags", []),
                        "media": meta.get("media", []),
                        "base_model": meta.get("base_model", ""),
                        "source_platform": meta.get("source_platform", ""),
                        "source_url": source_url,
                    },
                }
            )
        except Exception as exc:
            return web.json_response({"success": False, "error": str(exc)}, status=500)

    @routes.post("/tiny-model-manager/api/models/{model_type}/{path:.*}/refetch-preview")
    async def refetch_preview(request):
        path = request.match_info["path"]
        model_type = request.match_info["model_type"]
        _ensure_cleanup_running()
        try:
            if not _file_exists_on_disk(model_type, os.path.dirname(path), os.path.basename(path)):
                await model_repo.delete_model_record(path)
                return web.json_response({"success": True, "data": {"removed": True}})

            info = await model_repo.get_model_source_info(path)
            if not info or not info.get("source_platform") or not info.get("source_id"):
                return web.json_response(
                    {"success": False, "error": "No source info stored for this model"},
                    status=400,
                )

            existing = await model_repo.get_model_by_filename(path) or {}

            from ..services import metadata_fetcher

            try:
                meta = await metadata_fetcher.fetch_metadata_only(
                    info["source_platform"], info["source_id"]
                )
            except Exception as exc:
                return web.json_response(
                    {"success": False, "error": f"Metadata fetch failed: {exc}"}, status=500
                )

            old = {
                "description": existing.get("description", ""),
                "trigger_words": existing.get("trigger_words", []),
                "tags": existing.get("tags", []),
                "base_model": existing.get("base_model", ""),
                "media": existing.get("media", []),
                "last_edited_at": {
                    "description": existing.get("description_edited_at"),
                    "trigger_words": existing.get("trigger_words_edited_at"),
                    "tags": existing.get("tags_edited_at"),
                    "base_model": existing.get("base_model_edited_at"),
                },
            }
            new_data = {
                "description": meta.description,
                "trigger_words": meta.trigger_words,
                "tags": meta.tags,
                "base_model": meta.base_model,
                "media_urls": meta.image_urls,
            }
            no_changes = (
                old["description"] == new_data["description"]
                and sorted(old["trigger_words"]) == sorted(new_data["trigger_words"])
                and sorted(old["tags"]) == sorted(new_data["tags"])
                and old["base_model"] == new_data["base_model"]
            )

            entry = _RefetchEntry(datetime.now(UTC), old, new_data)
            _refetch_cache[path] = entry

            return web.json_response(
                {
                    "success": True,
                    "data": {
                        "old": old,
                        "new": new_data,
                        "expires_at": entry.expires_at_iso(),
                        "no_changes": no_changes,
                    },
                }
            )
        except Exception as exc:
            return web.json_response({"success": False, "error": str(exc)}, status=500)

    @routes.post("/tiny-model-manager/api/models/{model_type}/{path:.*}/refetch-apply")
    async def refetch_apply(request):
        path = request.match_info["path"]
        model_type = request.match_info["model_type"]
        _ensure_cleanup_running()

        entry = _refetch_cache.get(path)
        if entry is None:
            return web.json_response(
                {
                    "success": False,
                    "error": "No preview cache entry — call /refetch-preview first",
                },
                status=400,
            )
        if entry.is_expired:
            del _refetch_cache[path]
            return web.json_response(
                {"success": False, "error": "Preview expired — re-fetch to review again"},
                status=410,
            )

        try:
            body = await request.json()
            await model_repo.update_model_meta(
                path,
                description=body.get("description"),
                trigger_words=body.get("trigger_words"),
                tags=body.get("tags"),
                base_model=body.get("base_model"),
                model_type=model_type,
            )

            if body.get("replace_media"):
                from ..services import metadata_fetcher

                id_hash = await model_repo.get_model_id_and_hash(path)
                if id_hash:
                    model_id, media_hash = id_hash
                    keep_paths = set(body.get("keep_existing_media", []))
                    existing_media = await model_repo.get_model_media(model_id)
                    for row in existing_media:
                        if row["local_path"] not in keep_paths:
                            await model_repo.delete_media_row(row["id"])
                    await metadata_fetcher._download_images(
                        model_id, media_hash, body.get("media_urls", [])
                    )

            del _refetch_cache[path]

            meta = await model_repo.get_model_by_filename(path) or {}
            source_url = _derive_source_url(
                meta.get("source_platform", ""),
                meta.get("source_id", ""),
                meta.get("civitai_model_id", ""),
            )
            return web.json_response(
                {
                    "success": True,
                    "data": {
                        "removed": False,
                        "description": meta.get("description", ""),
                        "trigger_words": meta.get("trigger_words", []),
                        "tags": meta.get("tags", []),
                        "media": meta.get("media", []),
                        "base_model": meta.get("base_model", ""),
                        "source_platform": meta.get("source_platform", ""),
                        "source_url": source_url,
                    },
                }
            )
        except Exception as exc:
            return web.json_response({"success": False, "error": str(exc)}, status=500)

    _MODEL_EXTENSIONS = {".safetensors", ".ckpt", ".pt", ".bin", ".gguf"}

    @routes.get("/tiny-model-manager/api/models/{model_type}/{path:.*}/repo-files")
    async def get_repo_files(request):
        path = request.match_info["path"]
        model_type = request.match_info["model_type"]
        try:
            files = await model_repo.get_repo_files(model_type, path)
            installed_map = await model_repo.get_installed_basenames_for_model(path)
            model_dir = os.path.dirname(path)
            result = []
            for f in files:
                ext = os.path.splitext(f["filename"].lower())[1]
                if ext not in _MODEL_EXTENSIONS:
                    continue
                basename = os.path.basename(f["filename"])
                db_info = installed_map.get(basename, {})
                db_path = db_info.get("installed_path", "")
                fs_check = _file_exists_on_disk(
                    model_type, model_dir, f["filename"]
                ) or _file_exists_on_disk(model_type, "", basename)
                f["is_downloaded"] = bool(db_path) or fs_check
                if db_path:
                    f["installed_path"] = db_path
                    f["base_model"] = db_info.get("base_model", "")
                elif fs_check:
                    f["installed_path"] = (
                        os.path.join(model_dir, basename) if model_dir else basename
                    )
                    f["base_model"] = ""
                else:
                    f["installed_path"] = ""
                    f["base_model"] = ""
                f["added_at"] = _get_file_mtime(
                    model_type, model_dir, f["filename"]
                ) or _get_file_mtime(model_type, "", basename)
                result.append(f)
            return web.json_response({"success": True, "data": result})
        except Exception as exc:
            return web.json_response({"success": False, "error": str(exc)}, status=500)

    @routes.post("/tiny-model-manager/api/models/{model_type}/{path:.*}/link-source")
    async def link_source(request):
        model_type = request.match_info["model_type"]
        path = request.match_info["path"]
        try:
            body = await request.json()
            source_url = (body.get("source_url") or "").strip()
            platform, source_id, civitai_model_id = _parse_source_url(source_url)
            if not platform:
                return web.json_response(
                    {
                        "success": False,
                        "error": "Unrecognised URL. Paste a CivitAI model page or HuggingFace repo URL.",
                    },
                    status=400,
                )
            await model_repo.ensure_model_with_source(
                path, model_type, platform, source_id, civitai_model_id
            )
            page_id = source_id if platform == "huggingface" else civitai_model_id
            entry = await model_repo.get_catalog_entry(platform, page_id)
            if entry:
                await model_repo.set_model_catalog_entry(path, entry["id"])
            return web.json_response({"success": True})
        except Exception as exc:
            return web.json_response({"success": False, "error": str(exc)}, status=500)

    @routes.get("/tiny-model-manager/api/media/{path:.*}")
    async def serve_media(request):
        path = request.match_info["path"]
        from .. import config as cfg

        full_path = os.path.join(cfg.media_dir(), path)
        full_path = os.path.normpath(full_path)
        # Guard against path traversal
        if not full_path.startswith(os.path.normpath(cfg.media_dir())):
            return web.Response(status=403)
        if not os.path.isfile(full_path):
            return web.Response(status=404)
        return web.FileResponse(full_path)
