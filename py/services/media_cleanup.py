"""Removes media files that no model or catalog entry references any more.

Media lives in ``<media_dir>/<media_hash>/`` (F-58). A model and its parent catalog
entry frequently share one hash — ``metadata_fetcher.fetch_and_store`` stores the
model's hash on the catalog entry as well — and the catalog gallery is meant to
outlive the installed file. Every deletion here is therefore gated on the hash no
longer being referenced by any ``models`` or ``catalog_entries`` row, so uninstalling
one model never empties the gallery of the item it came from.
"""

import logging
import os
import re
import shutil
from collections.abc import Iterable

from .. import config as cfg
from ..db import model_repo

_log = logging.getLogger("tiny-model-manager")

_MEDIA_HASH_RE = re.compile(r"[A-Za-z0-9_-]{1,128}")

_EMPTY_RESULT = {"dirs": 0, "files": 0}


def media_subdir(media_hash: str) -> str:
    """Return the per-model media directory, guarding against path traversal."""
    if not _MEDIA_HASH_RE.fullmatch(media_hash):
        raise ValueError(f"Invalid media hash: {media_hash!r}")
    base = os.path.realpath(cfg.media_dir())
    resolved = os.path.realpath(os.path.join(base, media_hash))
    # Defense-in-depth: the allowlist above already rejects separators, but
    # explicitly confirm the resolved path stays inside the media directory so
    # the safe boundary is enforced at the point where the path is constructed.
    if resolved != base and not resolved.startswith(base + os.sep):
        raise ValueError(f"Invalid media hash: {media_hash!r}")
    return resolved


def _remove_files(paths: Iterable[str]) -> int:
    """Delete the given files, ignoring the ones already gone. Returns the count removed."""
    removed = 0
    for path in paths:
        try:
            if os.path.isfile(path):
                os.remove(path)
                removed += 1
        except OSError:
            _log.warning("Could not delete media file %s", path, exc_info=True)
    return removed


def _remove_tree(path: str) -> int:
    """Delete a media directory and return how many files it held."""
    if not os.path.isdir(path):
        return 0
    count = sum(len(files) for _, _, files in os.walk(path))
    shutil.rmtree(path, ignore_errors=True)
    return count


async def cleanup_model_media(media_hash: str, media_paths: list[str]) -> int:
    """Delete the media of a just-deleted model. Returns the number of files removed.

    Must be called *after* the ``models`` row is gone: the reference check reads the
    post-delete state, so a hash that is still listed belongs to the catalog entry or
    to another model and its files are left alone.
    """
    if media_hash:
        if media_hash in await model_repo.get_live_media_hashes():
            return 0
        try:
            target = media_subdir(media_hash)
        except ValueError:
            _log.warning("Refusing to clean up invalid media hash %r", media_hash)
            return 0
        return _remove_tree(target)
    # Rows predating F-58 have no hash — fall back to the individual files, keeping
    # any path another model still references.
    referenced = await model_repo.get_all_media_paths()
    return _remove_files(p for p in media_paths if os.path.realpath(p) not in referenced)


def _report(dirs: int, files: int) -> None:
    """Log and toast the cleanup result; stay quiet when nothing was removed."""
    if not dirs and not files:
        return
    _log.info("Stale media cleanup removed %d file(s) from %d folder(s)", files, dirs)
    from .backend_notifier import push

    push("info", f"Cleaned up {files} stale media file(s) from {dirs} folder(s).")


async def cleanup_stale_media() -> dict:
    """Delete media the DB no longer references. Returns ``{"dirs", "files"}`` counts.

    Opt-in via the ``cleanup_stale_media_on_start`` setting. A directory is stale when
    its name matches no live ``media_hash``; a loose file directly in the media root is
    stale when no ``model_media`` row points at it.
    """
    if not cfg.load_settings().get("cleanup_stale_media_on_start"):
        return dict(_EMPTY_RESULT)
    base = os.path.realpath(cfg.media_dir())
    if not os.path.isdir(base):
        return dict(_EMPTY_RESULT)

    live = await model_repo.get_live_media_hashes()
    referenced = await model_repo.get_all_media_paths()
    dirs = 0
    files = 0
    for name in sorted(os.listdir(base)):
        full = os.path.join(base, name)
        if os.path.isdir(full):
            if name not in live:
                files += _remove_tree(full)
                dirs += 1
        elif os.path.realpath(full) not in referenced:
            files += _remove_files([full])
    _report(dirs, files)
    return {"dirs": dirs, "files": files}
