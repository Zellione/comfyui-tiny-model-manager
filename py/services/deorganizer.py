"""Processes the deorganize queue: moves models from base-model subfolders back to flat dirs."""

import os
import shutil

import folder_paths

from ..db import model_repo
from .metadata_fetcher import _remove_empty_dir


async def process_pending_jobs() -> None:
    """Process all pending deorganize jobs, flattening files back into their type root dir."""
    jobs = await model_repo.get_pending_deorganize_jobs()
    for job in jobs:
        job_id: int = job["id"]
        filename: str = job["filename"]
        model_type: str = job["model_type"]

        if "/" not in filename and "\\" not in filename:
            await model_repo.complete_deorganize_job(job_id)
            continue

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
            await model_repo.complete_deorganize_job(job_id)
            continue

        basename = os.path.basename(filename)
        dest = os.path.join(src_base_dir, basename)

        if os.path.exists(dest) and os.path.normpath(dest) != os.path.normpath(src):
            await model_repo.complete_deorganize_job(job_id)
            continue

        try:
            shutil.move(src, dest)
            _remove_empty_dir(os.path.dirname(src))
            await model_repo.update_model_filename(filename, basename)
        except Exception:
            pass

        await model_repo.complete_deorganize_job(job_id)
