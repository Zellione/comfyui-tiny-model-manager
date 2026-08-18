import asyncio
import json
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
from . import model_paths
from .providers import get_provider
from .url_guard import guarded_stream

# No allowlist of model types lives here on purpose: `_get_dest_dir` resolves whatever
# ComfyUI registers in `folder_paths`, including folders added by custom nodes. A curated
# copy of that set drifts (it was missing `latent_upscale_models` and `audio_encoders`,
# among others) and silently rejects valid downloads.


class _Cancelled(Exception):
    pass


class DownloadRefused(Exception):
    """The server refused the download with a structured error (e.g. the CivitAI paywall).

    ``code`` is a machine-readable reason (``login_required`` / ``early_access`` / ``""``)
    surfaced to the frontend so it can show a translated hint; ``message`` is the
    provider's own human-readable explanation.
    """

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


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
    error_code: str = ""
    dest_path: str = ""
    cancelled: bool = False
    history_id: int | None = None
    hint_base_model: str = ""
    completed_at: float | None = None
    on_complete: Callable[["DownloadTask"], Awaitable[None]] | None = field(
        default=None, repr=False
    )


_tasks: dict[str, DownloadTask] = {}
_queue: asyncio.Queue = asyncio.Queue()
_worker_started = False


def _get_dest_dir(model_type: str) -> str:
    if not model_paths.is_safe_segment(model_type):
        raise ValueError(f"Invalid model_type: {model_type!r}")
    try:
        folders = folder_paths.get_folder_paths(model_type)
        return folders[0]
    except Exception:
        # Fall back to ComfyUI's models directory so the file is visible to ComfyUI
        # and to our own list_models endpoint (which scans folder_paths).  The old
        # fallback used cfg.data_dir() which placed files outside ComfyUI's reach.
        return os.path.join(folder_paths.models_dir, model_type)


def validate_target(model_type: str, filename: str, platform: str) -> str:
    """Resolve and validate the absolute destination path for a download.

    ``filename`` and ``model_type`` arrive from request data; an unchecked value such as
    ``../../etc/foo`` would let a download write outside the model roots (CWE-22). The
    destination is confined to ``model_type``'s download directory here, raising
    ``ValueError`` on any traversal attempt. HuggingFace filenames keep their existing
    basename normalisation (subfolder prefixes like ``split_files/`` are stripped).
    """
    if platform == "huggingface":
        filename = os.path.basename(filename)
    dest_dir = _get_dest_dir(model_type)
    safe_path = model_paths.contained_path(dest_dir, filename)
    if safe_path is None:
        raise ValueError(f"Unsafe download filename: {filename!r}")
    return safe_path


def enqueue(
    url: str,
    model_type: str,
    filename: str,
    platform: str,
    source_id: str = "",
    on_complete: Callable[[DownloadTask], Awaitable[None]] | None = None,
    history_id: int | None = None,
    hint_base_model: str = "",
) -> DownloadTask:
    # Strip subfolder prefixes from HuggingFace filenames (e.g. "split_files/model.safetensors"
    # → "model.safetensors"). The download URL is a separate field and remains untouched.
    if platform == "huggingface":
        filename = os.path.basename(filename)
    # Confine the destination to model_type's download directory; raises on traversal.
    dest_path = validate_target(model_type, filename, platform)
    task = DownloadTask(
        id=str(uuid.uuid4()),
        url=url,
        model_type=model_type,
        filename=filename,
        platform=platform,
        source_id=source_id,
        on_complete=on_complete,
        history_id=history_id,
        hint_base_model=hint_base_model,
    )
    task.dest_path = dest_path
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
        "error_code": t.error_code,
        "history_id": t.history_id,
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


# No overall deadline (model files are large and download for a long time), but a
# stalled socket must abort the worker instead of hanging the whole queue forever.
# httpx has no total timeout: the first argument is only the default for the categories
# left unset, so passing None there left `write` and `pool` unbounded. Both are now given
# explicit ceilings — a wedged write or an unavailable connection slot would otherwise park
# the single download worker forever and stall every queued download behind it.
_DOWNLOAD_TIMEOUT = httpx.Timeout(None, connect=30.0, read=120.0, write=120.0, pool=30.0)


async def _raise_refusal(resp) -> None:
    """Surface the provider's own refusal message instead of the bare HTTP status.

    CivitAI answers 401 (no/invalid key) and 403 (paywalled asset) with a JSON body whose
    ``message`` explains the refusal; falls through silently so ``raise_for_status`` keeps
    handling responses without such a body.
    """
    try:
        payload = json.loads(await resp.aread())
    except ValueError:
        return
    message = payload.get("message") if isinstance(payload, dict) else None
    if not message:
        return
    if resp.status_code == 401:
        code = "login_required"
    elif resp.status_code == 403 and payload.get("error") == "Early Access":
        code = "early_access"
    else:
        code = ""
    raise DownloadRefused(code, message)


async def _stream_file(task: DownloadTask, headers: dict) -> None:
    # No follow_redirects on the client: guarded_stream resolves the chain itself so
    # every hop is re-checked against the provider allowlist (both CivitAI and
    # HuggingFace redirect downloads to their CDNs).
    async with httpx.AsyncClient(timeout=_DOWNLOAD_TIMEOUT) as client:
        async with guarded_stream(client, "GET", task.url, headers=headers) as resp:
            if resp.is_error:
                await _raise_refusal(resp)
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


async def _run_download(task: DownloadTask):
    task.status = "downloading"
    provider = get_provider(task.platform)
    headers = provider.auth_headers() if provider else {}

    try:
        await _stream_file(task, headers)
        task.status = "done"
        task.progress = 100.0
        task.completed_at = time.time()
        if task.history_id is not None:
            await model_repo.update_download_history_status(task.history_id, "done")
        if task.on_complete:
            await task.on_complete(task)
        from .metadata_fetcher import fetch_and_store

        spawn(
            fetch_and_store(
                task.filename,
                task.model_type,
                task.platform,
                task.source_id,
                hint_base_model=task.hint_base_model,
            )
        )
    except _Cancelled:
        task.status = "cancelled"
        task.completed_at = time.time()
        if task.history_id is not None:
            await model_repo.update_download_history_status(task.history_id, "cancelled")
        if os.path.isfile(task.dest_path):
            os.remove(task.dest_path)
    except DownloadRefused as exc:
        await _fail_task(task, exc.message, exc.code)
    except Exception as exc:
        await _fail_task(task, str(exc))


async def _fail_task(task: DownloadTask, message: str, code: str = "") -> None:
    task.status = "error"
    task.error = message
    task.error_code = code
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
