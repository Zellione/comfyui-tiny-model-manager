"""Removes media files that no model or catalog entry references any more.

Media lives in ``<media_dir>/<media_hash>/`` (F-58). A model and its parent catalog
entry frequently share one hash — ``metadata_fetcher.fetch_and_store`` stores the
model's hash on the catalog entry as well — and the catalog gallery is meant to
outlive the installed file. Every deletion here is therefore gated on the hash no
longer being referenced by any ``models`` or ``catalog_entries`` row, so uninstalling
one model never empties the gallery of the item it came from.

Nothing is deleted by absolute path. Every destructive call takes the media root plus
a single entry name and resolves it through ``model_paths.contained_path``, so a name
that escapes the media directory is dropped before it can reach ``os.remove`` or
``shutil.rmtree``.
"""

import logging
import os
import re
import shutil

from .. import config as cfg
from ..db import model_repo
from . import model_paths

_log = logging.getLogger("tiny-model-manager")

_MEDIA_HASH_RE = re.compile(r"[A-Za-z0-9_-]{1,128}")

_EMPTY_RESULT = {"dirs": 0, "files": 0}


def media_subdir(media_hash: str) -> str:
    """Return the per-model media directory, guarding against path traversal."""
    if not _MEDIA_HASH_RE.fullmatch(media_hash):
        raise ValueError(f"Invalid media hash: {media_hash!r}")
    # Defense-in-depth: the allowlist above already rejects separators, but the
    # containment check confirms the resolved path stays inside the media directory
    # at the point where the path is constructed.
    resolved = model_paths.contained_path(cfg.media_dir(), media_hash)
    if resolved is None:
        raise ValueError(f"Invalid media hash: {media_hash!r}")
    return resolved


def _media_root() -> str | None:
    """Return the media root to scan, or None when the setting is not usable.

    ``media_dir`` is operator-supplied. A relative value would resolve against
    ComfyUI's working directory rather than the intended folder, so only an absolute,
    already-existing directory is ever handed to the scan.
    """
    configured = cfg.media_dir()
    if not os.path.isabs(configured):
        _log.warning("Ignoring stale-media cleanup: media_dir must be an absolute path")
        return None
    root = os.path.realpath(configured)
    return root if os.path.isdir(root) else None


def _remove_file(base: str, name: str) -> int:
    """Delete one file directly inside ``base``. Returns 1 when it was removed."""
    path = model_paths.contained_path(base, name)
    if path is None or not os.path.isfile(path):
        return 0
    try:
        os.remove(path)
        return 1
    except OSError:
        # The path is in the OSError itself; keep it out of the message so the log
        # never echoes back a name that came from outside.
        _log.warning("Could not delete a stale media file", exc_info=True)
        return 0


def _remove_tree(base: str, name: str) -> int:
    """Delete one directory inside ``base`` and return how many files it held."""
    path = model_paths.contained_path(base, name)
    if path is None or not os.path.isdir(path):
        return 0
    count = sum(len(files) for _, _, files in os.walk(path))
    shutil.rmtree(path, ignore_errors=True)
    return count


async def cleanup_model_media(media_hash: str) -> int:
    """Delete the media of a just-deleted model. Returns the number of files removed.

    Must be called *after* the ``models`` row is gone: the reference check reads the
    post-delete state, so a hash that is still listed belongs to the catalog entry or
    to another model and its files are left alone.

    A model with no hash has nothing to clean — ``migrate_existing_media`` assigns one
    on startup to every model that owns media rows, and models registered from disk
    have neither.
    """
    if not media_hash or not _MEDIA_HASH_RE.fullmatch(media_hash):
        return 0
    if media_hash in await model_repo.get_live_media_hashes():
        return 0
    return _remove_tree(cfg.media_dir(), media_hash)


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
    base = _media_root()
    if base is None:
        return dict(_EMPTY_RESULT)

    live = await model_repo.get_live_media_hashes()
    referenced = await model_repo.get_all_media_paths()
    dirs = 0
    files = 0
    for name in sorted(os.listdir(base)):
        full = model_paths.contained_path(base, name)
        if full is None:
            continue
        if os.path.isdir(full):
            if name not in live:
                files += _remove_tree(base, name)
                dirs += 1
        elif full not in referenced:
            files += _remove_file(base, name)
    _report(dirs, files)
    return {"dirs": dirs, "files": files}
