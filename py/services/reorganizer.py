"""Unified reorganizer: moves models into base-model subfolders or back to flat directories.

The module-level asyncio.Lock ensures only one pass runs at a time.  If a new call arrives
while the lock is held, it returns immediately — new jobs enqueued during the run are picked
up in the next loop iteration before the lock is released.

Ordering guarantee: organize jobs always complete before deorganize jobs begin within a single
run, preventing file-move conflicts when the toggle is flipped back quickly.
"""

import asyncio
import os
import re
import shutil

import folder_paths

from ..db import model_repo

_MAX_SUBFOLDER_LEN = 100
_INVALID_PATH_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_lock = asyncio.Lock()


def _sanitize_subfolder_name(name: str) -> str:
    if not name:
        return "Unknown"
    sanitized = _INVALID_PATH_CHARS.sub("_", name).strip(". ")
    return sanitized[:_MAX_SUBFOLDER_LEN] if sanitized else "Unknown"


def _remove_empty_dir(path: str) -> None:
    try:
        if os.path.isdir(path) and not os.listdir(path):
            os.rmdir(path)
    except Exception:
        pass


def _move_to_subfolder(filename: str, model_type: str, base_model: str) -> str:
    """Move the model file into a base-model subfolder; return the new relative filename."""
    try:
        base_dirs = folder_paths.get_folder_paths(model_type)
    except Exception:
        base_dirs = [os.path.join(folder_paths.models_dir, model_type)]

    src = None
    src_base_dir = None
    for base_dir in base_dirs:
        candidate = os.path.normpath(os.path.join(base_dir, filename))
        if os.path.isfile(candidate):
            src = candidate
            src_base_dir = base_dir
            break

    if not src or not src_base_dir:
        return filename

    basename = os.path.basename(filename)
    subfolder = _sanitize_subfolder_name(base_model)
    new_rel = subfolder + "/" + basename

    if new_rel == filename:
        return filename

    dest = os.path.join(src_base_dir, new_rel)
    if os.path.exists(dest):
        return filename

    os.makedirs(os.path.dirname(dest), exist_ok=True)
    shutil.move(src, dest)
    _remove_empty_dir(os.path.dirname(src))
    return new_rel


async def _process_organize_job(job: dict) -> None:
    job_id: int = job["id"]
    filename: str = job["filename"]
    model_type: str = job["model_type"]

    if "/" in filename or "\\" in filename:
        await model_repo.complete_job(job_id)
        return

    try:
        model_info = await model_repo.get_model_by_filename(filename)
        base_model = (model_info or {}).get("base_model", "")
        if not base_model:
            base_model = await model_repo.get_effective_base_model(filename)
            if base_model:
                await model_repo.update_model_base_model(filename, base_model)
        new_fn = _move_to_subfolder(filename, model_type, base_model)
        if new_fn != filename:
            await model_repo.update_model_filename(filename, new_fn)
    except Exception:
        pass

    await model_repo.complete_job(job_id)


async def _process_deorganize_job(job: dict) -> None:
    job_id: int = job["id"]
    filename: str = job["filename"]
    model_type: str = job["model_type"]

    if "/" not in filename and "\\" not in filename:
        await model_repo.complete_job(job_id)
        return

    try:
        base_dirs = folder_paths.get_folder_paths(model_type)
    except Exception:
        base_dirs = [os.path.join(folder_paths.models_dir, model_type)]

    src = None
    src_base_dir = None
    for base_dir in base_dirs:
        candidate = os.path.normpath(os.path.join(base_dir, filename))
        if os.path.isfile(candidate):
            src = candidate
            src_base_dir = base_dir
            break

    if not src or not src_base_dir:
        await model_repo.complete_job(job_id)
        return

    basename = os.path.basename(filename)
    dest = os.path.join(src_base_dir, basename)

    if os.path.exists(dest) and os.path.normpath(dest) != os.path.normpath(src):
        await model_repo.complete_job(job_id)
        return

    try:
        shutil.move(src, dest)
        _remove_empty_dir(os.path.dirname(src))
        await model_repo.update_model_filename(filename, basename)
    except Exception:
        pass

    await model_repo.complete_job(job_id)


async def process_pending_jobs() -> None:
    """Process all pending reorganize jobs.  Organize runs before deorganize in each pass."""
    if _lock.locked():
        return
    async with _lock:
        while True:
            organize_jobs = await model_repo.get_pending_jobs("organize")
            for job in organize_jobs:
                await _process_organize_job(job)

            deorganize_jobs = await model_repo.get_pending_jobs("deorganize")
            for job in deorganize_jobs:
                await _process_deorganize_job(job)

            if not await model_repo.get_pending_jobs():
                break
