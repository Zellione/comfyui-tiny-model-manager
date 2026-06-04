"""Startup reconciliation: prune DB records for model files that no longer exist on disk.

A user can delete model files outside the app (or while ComfyUI is stopped). The DB
then holds stale `models` rows that still appear installed. This scan removes them.

Safety: a model is only pruned when its type directory is present but the file is
absent. If none of the candidate directories exist (e.g. models live on a network
share that has not mounted yet), the file is treated as "unknown" and left untouched
so curated metadata is never lost to a transient storage outage.
"""

import os

import folder_paths

from .. import config as cfg
from ..db import model_repo


def _candidate_dirs(model_type: str) -> list[str]:
    dirs: list[str] = []
    registered, _ = folder_paths.folder_names_and_paths.get(model_type, ([], {}))
    dirs.extend(registered)
    models_dir = getattr(folder_paths, "models_dir", None)
    if models_dir:
        dirs.append(os.path.join(models_dir, model_type))
    dirs.append(os.path.join(cfg.data_dir(), "models", model_type))
    return dirs


def _file_status(model_type: str, filename: str) -> str:
    """Return 'present', 'absent', or 'unknown'.

    'absent' means at least one candidate directory exists but the file is not in any
    of them. 'unknown' means no candidate directory is accessible.
    """
    any_dir = False
    for base_dir in _candidate_dirs(model_type):
        if os.path.isdir(base_dir):
            any_dir = True
            if os.path.isfile(os.path.join(base_dir, filename)):
                return "present"
    return "absent" if any_dir else "unknown"


async def prune_stale_models() -> int:
    """Delete models rows whose file is confirmed absent from disk.

    Catalog entries and repo_files are left intact: once the model row is gone they
    correctly fall back to 'not downloaded', so the item simply becomes downloadable
    again. Returns the number of pruned records.
    """
    pruned = 0
    for m in await model_repo.get_all_models_slim():
        if _file_status(m["model_type"], m["filename"]) == "absent":
            await model_repo.delete_model_record(m["filename"])
            pruned += 1
    return pruned
