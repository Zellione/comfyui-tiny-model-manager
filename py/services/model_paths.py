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


def is_safe_segment(segment: str) -> bool:
    """True if ``segment`` is a single, non-traversing path component.

    ``model_type`` reaches these helpers straight from a URL route parameter; a value
    such as ``..`` or ``a/b`` must never be treated as a physical subfolder name, or it
    could redirect the search outside the model roots.
    """
    return (
        bool(segment) and segment not in (".", "..") and "/" not in segment and "\\" not in segment
    )


def candidate_dirs(model_type: str) -> list[str]:
    """All base directories a model file of ``model_type`` might live in, in search order."""
    dirs: list[str] = []
    registered, _ = folder_paths.folder_names_and_paths.get(model_type, ([], {}))
    dirs.extend(registered)
    if is_safe_segment(model_type):
        models_dir = getattr(folder_paths, "models_dir", None)
        if models_dir:
            dirs.append(os.path.join(models_dir, model_type))
        dirs.append(os.path.join(cfg.data_dir(), "models", model_type))
    return dirs


def contained_path(base: str, *parts: str) -> str | None:
    """Resolve ``parts`` under ``base``; return the real path only if it stays inside ``base``.

    ``parts`` is built from untrusted request data (filenames, relative model paths). A
    value containing ``../`` that escapes the base directory is a filesystem-oracle vector
    (CWE-22) and is rejected here by canonical-path validation.
    """
    base_real = os.path.realpath(base)
    full_real = os.path.realpath(os.path.join(base, *parts))
    if full_real == base_real or full_real.startswith(base_real + os.sep):
        return full_real
    return None


def candidate_paths(model_type: str, *parts: str) -> list[str]:
    """Candidate real paths for ``parts`` under each base dir, excluding any that escape it."""
    resolved: list[str] = []
    for base in candidate_dirs(model_type):
        full = contained_path(base, *parts)
        if full is not None:
            resolved.append(full)
    return resolved


def find_file(model_type: str, *parts: str) -> str | None:
    """Return the first existing, in-bounds candidate path for ``parts``, or None."""
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
