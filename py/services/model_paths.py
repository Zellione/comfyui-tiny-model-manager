"""Shared filesystem resolution for model files.

A model file of a given type can live in any of three kinds of location:
  1. directories registered in ComfyUI's ``folder_paths.folder_names_and_paths``
  2. ``<models_dir>/<model_type>`` (physical subfolder, even if unregistered)
  3. ``<data_dir>/models/<model_type>`` (legacy location used by older plugin versions)

Several routes and services need to locate, size, or stat such files. This module is the
single source of truth for that candidate-path logic so the search order stays consistent.
"""

import os

import folder_paths

from .. import config as cfg


def candidate_dirs(model_type: str) -> list[str]:
    """All base directories a model file of ``model_type`` might live in, in search order."""
    dirs: list[str] = []
    registered, _ = folder_paths.folder_names_and_paths.get(model_type, ([], {}))
    dirs.extend(registered)
    models_dir = getattr(folder_paths, "models_dir", None)
    if models_dir:
        dirs.append(os.path.join(models_dir, model_type))
    dirs.append(os.path.join(cfg.data_dir(), "models", model_type))
    return dirs


def candidate_paths(model_type: str, *parts: str) -> list[str]:
    """Candidate absolute paths for ``parts`` joined under each base dir."""
    return [os.path.join(base, *parts) for base in candidate_dirs(model_type)]


def find_file(model_type: str, *parts: str) -> str | None:
    """Return the first existing candidate path for ``parts``, or None."""
    for full in candidate_paths(model_type, *parts):
        if os.path.isfile(full):
            return full
    return None


def file_exists(model_type: str, *parts: str) -> bool:
    return find_file(model_type, *parts) is not None


def file_size(model_type: str, *parts: str) -> int:
    """Return the size of the first found copy, or 0 if not found."""
    full = find_file(model_type, *parts)
    if full:
        try:
            return os.path.getsize(full)
        except OSError:
            pass
    return 0


def file_mtime(model_type: str, *parts: str) -> float | None:
    full = find_file(model_type, *parts)
    if full:
        try:
            return os.path.getmtime(full)
        except OSError:
            pass
    return None


def file_stat(model_type: str, *parts: str) -> dict | None:
    """Return ``{"size_bytes", "modified_at"}`` for the first found copy, or None."""
    full = find_file(model_type, *parts)
    if full:
        try:
            s = os.stat(full)
            return {"size_bytes": s.st_size, "modified_at": s.st_mtime}
        except OSError:
            pass
    return None
