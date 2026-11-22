"""Shared filesystem resolution for model files.

A model file of a given type can live in any of three kinds of location:
  1. directories registered in ComfyUI's ``folder_paths.folder_names_and_paths``
  2. ``<models_dir>/<model_type>`` (physical subfolder, even if unregistered)
  3. ``<data_dir>/models/<model_type>`` (legacy location used by older plugin versions)

Several routes and services need to locate, size, or stat such files. This module is the
single source of truth for that candidate-path logic so the search order stays consistent.
"""

import os

# pi-lens-ignore: reportMissingImports
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


def compute_file_hash(path) -> str:
    """Return the lowercase hex SHA-256 of a file. Synchronous; call via asyncio.to_thread."""
    import hashlib

    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# Media path storage (issue #176)
#
# ``model_media.local_path`` and ``catalog_entries.thumbnail_url`` are stored relative to
# ``cfg.media_dir()`` so that moving the ComfyUI folder keeps them valid. Media files
# always live in ``<media_dir>/<media_hash>/<name>``, which is the layout the repair
# below relies on.
# ---------------------------------------------------------------------------


def resolve_media_path(local_path: str) -> str:
    """Absolute path of a stored media ``local_path``.

    Relative values resolve against the media dir; legacy absolute values (a stable
    external media dir, or a not-yet-migrated row) pass through unchanged.
    """
    return os.path.join(cfg.media_dir(), local_path)


def to_stored_media_path(path: str) -> str:
    """The media-dir-relative form of a media file path, for storage in the DB.

    Absolute paths inside the current media dir come back relative (forward slashes);
    relative paths are normalised to forward slashes; anything else is returned
    unchanged so an absolute path into a stable external dir keeps working.
    """
    if os.path.isabs(path):
        root = os.path.realpath(cfg.media_dir())
        full = os.path.realpath(path)
        if full == root or full.startswith(root + os.sep):
            return os.path.relpath(full, root).replace(os.sep, "/")
        return path
    return path.replace(os.sep, "/")


def normalize_stored_media_path(stored: str) -> str | None:
    """Return the repaired media-dir-relative value for a stored media path, or None.

    Used by the startup migration: absolute values under the current media dir are
    relativised, and stale values from an old install location are rewritten when the
    ``<hash>/<name>`` tail is verifiably present in the current media dir (the whole
    tree was moved with the files still inside). Relative values and absolute values
    that match neither are returned as None — a stable external media dir must keep
    working, and a file that is simply gone must not be silently rewritten.
    """
    if not os.path.isabs(stored):
        return None
    fixed = to_stored_media_path(stored)
    if fixed != stored:
        return fixed
    parts = stored.replace("\\", "/").split("/")
    if len(parts) >= 2:
        tail = "/".join(parts[-2:])
        candidate = contained_path(cfg.media_dir(), tail)
        if candidate is not None and os.path.isfile(candidate):
            return tail
    return None
