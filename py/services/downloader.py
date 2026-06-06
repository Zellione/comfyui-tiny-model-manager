import asyncio
import os
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

import aiofiles
import folder_paths
import httpx

from ..background import spawn
from ..db import model_repo
from .providers import get_provider

SUPPORTED_TYPES = {
    "checkpoints": "checkpoints",
    "loras": "loras",
    "embeddings": "embeddings",
    "vae": "vae",
    "controlnet": "controlnet",
    "upscale_models": "upscale_models",
    "hypernetworks": "hypernetworks",
    "clip_vision": "clip_vision",
    "style_models": "style_models",
    "gligen": "gligen",
    "diffusion_models": "diffusion_models",
    "text_encoders": "text_encoders",
    "photomaker": "photomaker",
    "vae_approx": "vae_approx",
    # Legacy names kept for backward compatibility (no longer registered ComfyUI folders)
    "unet": "unet",
    "clip": "clip",
}


class _Cancelled(Exception):
    pass


@dataclass
class DownloadTask:
    id: str
    url: str
    model_type: str
    filename: str
    platform: str
    source_id: str = ""
    status: str = "queued"  # queued | downloading | done | error | cancelled
    progress: float = 0.0
    downloaded_bytes: int = 0
    total_bytes: int = 0
    error: str | None = None
    dest_path: str = ""
    cancelled: bool = False
    history_id: int | None = None
    completed_at: float | None = None
    on_complete: Callable[["DownloadTask"], Awaitable[None]] | None = field(
        default=None, repr=False
    )


_tasks: dict[str, DownloadTask] = {}
_queue: asyncio.Queue = asyncio.Queue()
_worker_started = False


def _get_dest_dir(model_type: str) -> str:
    try:
        folders = folder_paths.get_folder_paths(model_type)
        return folders[0]
    except Exception:
        # Fall back to ComfyUI's models directory so the file is visible to ComfyUI
        # and to our own list_models endpoint (which scans folder_paths).  The old
        # fallback used cfg.data_dir() which placed files outside ComfyUI's reach.
        return os.path.join(folder_paths.models_dir, model_type)


def enqueue(
    url: str,
    model_type: str,
    filename: str,
    platform: str,
    source_id: str = "",
    on_complete: Callable[[DownloadTask], Awaitable[None]] | None = None,
    history_id: int | None = None,
) -> DownloadTask:
    # Strip subfolder prefixes from HuggingFace filenames (e.g. "split_files/model.safetensors"
    # → "model.safetensors"). The download URL is a separate field and remains untouched.
    if platform == "huggingface":
        filename = os.path.basename(filename)
    task = DownloadTask(
        id=str(uuid.uuid4()),
        url=url,
        model_type=model_type,
        filename=filename,
        platform=platform,
        source_id=source_id,
        on_complete=on_complete,
        history_id=history_id,
    )
    dest_dir = _get_dest_dir(model_type)
    task.dest_path = os.path.join(dest_dir, filename)
    os.makedirs(os.path.dirname(task.dest_path), exist_ok=True)
    _tasks[task.id] = task
    _queue.put_nowait(task)
    _ensure_worker()
    return task


def get_all_tasks() -> list[dict]:
    now = time.time()
    return [
        _task_to_dict(t)
        for t in _tasks.values()
        if t.status not in ("done", "error", "cancelled")
        or (t.completed_at is not None and now - t.completed_at < 60)
    ]


def cancel_task(task_id: str) -> bool:
    task = _tasks.get(task_id)
    if task is None or task.status in ("done", "error", "cancelled"):
        return False
    task.cancelled = True
    task.status = "cancelled"
    return True


def _task_to_dict(t: DownloadTask) -> dict:
    return {
        "id": t.id,
        "url": t.url,
        "model_type": t.model_type,
        "filename": t.filename,
        "platform": t.platform,
        "source_id": t.source_id,
        "status": t.status,
        "progress": t.progress,
        "downloaded_bytes": t.downloaded_bytes,
        "total_bytes": t.total_bytes,
        "error": t.error,
    }


def _ensure_worker():
    global _worker_started
    if not _worker_started:
        _worker_started = True
        spawn(_worker())


async def _worker():
    while True:
        task = await _queue.get()
        if not task.cancelled:
            await _run_download(task)
        _queue.task_done()


async def _run_download(task: DownloadTask):
    task.status = "downloading"
    provider = get_provider(task.platform)
    headers = provider.auth_headers() if provider else {}

    try:
        async with httpx.AsyncClient(timeout=None, follow_redirects=True) as client:
            async with client.stream("GET", task.url, headers=headers) as resp:
                resp.raise_for_status()
                total = int(resp.headers.get("content-length", 0))
                task.total_bytes = total
                downloaded = 0
                async with aiofiles.open(task.dest_path, "wb") as f:
                    async for chunk in resp.aiter_bytes(65536):
                        if task.cancelled:
                            raise _Cancelled()
                        await f.write(chunk)
                        downloaded += len(chunk)
                        task.downloaded_bytes = downloaded
                        task.progress = (downloaded / total * 100) if total else 0.0
        task.status = "done"
        task.progress = 100.0
        task.completed_at = time.time()
        if task.history_id is not None:
            await model_repo.update_download_history_status(task.history_id, "done")
        if task.on_complete:
            await task.on_complete(task)
        from .metadata_fetcher import fetch_and_store

        spawn(fetch_and_store(task.filename, task.model_type, task.platform, task.source_id))
    except _Cancelled:
        task.status = "cancelled"
        task.completed_at = time.time()
        if task.history_id is not None:
            await model_repo.update_download_history_status(task.history_id, "cancelled")
        if os.path.isfile(task.dest_path):
            os.remove(task.dest_path)
    except Exception as exc:
        task.status = "error"
        task.error = str(exc)
        task.completed_at = time.time()
        if task.history_id is not None:
            await model_repo.update_download_history_status(task.history_id, "error")
        if os.path.isfile(task.dest_path):
            os.remove(task.dest_path)


async def resume_interrupted_downloads() -> None:
    """On startup, detect history rows still marked 'downloading', clean partial files, re-enqueue."""
    interrupted = await model_repo.get_interrupted_downloads()
    for entry in interrupted:
        dest_path_abs = os.path.join(_get_dest_dir(entry["model_type"]), entry["dest_path"])
        if os.path.isfile(dest_path_abs):
            os.remove(dest_path_abs)
        enqueue(
            url=entry["file_url"],
            model_type=entry["model_type"],
            filename=entry["dest_path"],
            platform=entry["source"],
            source_id=entry["version_id"] or entry["model_id"],
            history_id=entry["id"],
        )
