"""F-92: silently register on-disk files that match hashes from an upstream fetch.

Whenever the backend already fetches CivitAI or HuggingFace metadata for some other
reason, the file hashes in that response are compared against unregistered files on disk
and matches become model cards without any user action.

Hashing is the expensive part, so candidates pass a name gate and a size gate before the
file is ever read. The hash is what authorises the match; the gates only avoid pointless
I/O.
"""

import asyncio
import logging
import os
from dataclasses import dataclass, field

from ..db import model_repo
from . import disk_scanner, model_paths

_log = logging.getLogger(__name__)

# CivitAI reports sizes as a rounded `sizeKB` float, so exact comparison would produce
# false negatives. 64 KB is far below the gap between any two genuinely different models.
_SIZE_TOLERANCE_BYTES = 64 * 1024

_HASH_CACHE_MAX = 256
_hash_cache: dict[tuple[str, int, float], str] = {}


@dataclass
class RemoteFile:
    """A file advertised by a provider, with the hash needed to recognise it on disk."""

    filename: str
    sha256: str
    size_bytes: int = 0
    base_model: str = ""
    source_platform: str = ""
    source_id: str = ""
    civitai_model_id: str = ""
    tags: list[str] = field(default_factory=list)
    trigger_words: list[str] = field(default_factory=list)
    description: str = ""


def from_civitai_versions(model_data: dict | list) -> list[RemoteFile]:
    """Normalise the ``{versions, model_type}`` dict returned by ``get_model_versions``.

    A bare list of versions is accepted too: this runs directly on a provider payload,
    so it must not raise if the response is shaped differently than expected.
    """
    if isinstance(model_data, dict):
        versions = model_data.get("versions") or []
    elif isinstance(model_data, list):
        versions = model_data
    else:
        return []
    files: list[RemoteFile] = []
    for version in versions:
        if not isinstance(version, dict):
            continue
        version_id = version.get("id")
        base_model = version.get("baseModel", "")
        civitai_model_id = str(version.get("modelId") or "")
        trigger_words = [w for w in (version.get("trainedWords") or []) if w]
        description = version.get("description") or ""
        for f in version.get("files") or []:
            if f.get("type") != "Model":
                continue
            sha256 = ((f.get("hashes") or {}).get("SHA256") or "").strip()
            name = (f.get("name") or "").strip()
            if not sha256 or not name:
                continue
            files.append(
                RemoteFile(
                    filename=name,
                    sha256=sha256,
                    size_bytes=int((f.get("sizeKB") or 0) * 1024),
                    base_model=base_model,
                    source_platform="civitai",
                    source_id=str(version_id or ""),
                    civitai_model_id=civitai_model_id,
                    trigger_words=trigger_words,
                    description=description,
                )
            )
    return files


def from_hf_files(repo_id: str, files: list[dict]) -> list[RemoteFile]:
    """Normalise the output of ``HuggingFaceProvider.get_model_files``."""
    result: list[RemoteFile] = []
    for f in files or []:
        sha256 = (f.get("sha256") or "").strip()
        name = (f.get("filename") or "").strip()
        if not sha256 or not name:
            continue
        result.append(
            RemoteFile(
                filename=name,
                sha256=sha256,
                size_bytes=f.get("size") or 0,
                source_platform="huggingface",
                source_id=repo_id,
            )
        )
    return result


def _size_matches(remote_size: int, local_size: int) -> bool:
    """True when the sizes are close enough to be worth hashing (0 means unknown)."""
    if not remote_size or not local_size:
        return True
    return abs(remote_size - local_size) <= _SIZE_TOLERANCE_BYTES


async def _hash_file(path: str, size: int, mtime: float) -> str:
    """SHA-256 of ``path``, memoised on (path, size, mtime) for the process lifetime."""
    key = (path, size, mtime)
    cached = _hash_cache.get(key)
    if cached is not None:
        return cached
    digest = await asyncio.to_thread(model_paths.compute_file_hash, path)
    if len(_hash_cache) >= _HASH_CACHE_MAX:
        # Plain FIFO eviction; insertion order is guaranteed for dicts.
        del _hash_cache[next(iter(_hash_cache))]
    _hash_cache[key] = digest
    return digest


def _index_by_name(remote_files: list[RemoteFile]) -> dict[str, list[RemoteFile]]:
    by_name: dict[str, list[RemoteFile]] = {}
    for rf in remote_files:
        by_name.setdefault(os.path.basename(rf.filename).lower(), []).append(rf)
    return by_name


async def _register_match(entry: dict, model_type: str, match: RemoteFile, digest: str) -> bool:
    """Create the model card from the fetched metadata. False if registration failed.

    Deliberately does NOT call ``fetch_and_store``: that would re-enter ``_fetch_repo_files``
    and schedule another migration pass, and when ``organize_into_subfolders`` is enabled it
    relocates the file and upserts under the new path, orphaning the row written here.
    The card carries the source linkage, so "Re-fetch metadata" fills in the rest on demand.
    """
    filename = entry["filename"]
    try:
        model_id = await model_repo.register_model(
            filename=filename,
            model_type=model_type,
            base_model=match.base_model,
            tags=match.tags,
            description=match.description,
            file_hash=digest,
            source_platform=match.source_platform,
            source_id=match.source_id,
            civitai_model_id=match.civitai_model_id,
        )
        if match.trigger_words:
            await model_repo.set_trigger_words(model_id, match.trigger_words)
    except Exception:
        _log.warning("Auto-migration failed to register %s", filename, exc_info=True)
        return False

    _log.info(
        "Auto-migrated '%s' (%s) from %s metadata",
        filename,
        model_type,
        match.source_platform,
    )
    from .backend_notifier import push as notify

    notify(
        "info",
        f"Registered '{os.path.basename(filename)}' automatically "
        f"from {match.source_platform} metadata.",
    )
    return True


async def migrate(remote_files: list[RemoteFile]) -> list[str]:
    """Register every unregistered on-disk file whose hash matches one of ``remote_files``.

    Returns the filenames that were migrated.
    """
    if not remote_files:
        return []
    by_name = _index_by_name(remote_files)
    if not by_name:
        return []

    scanned = disk_scanner.scan_all()
    registered = await model_repo.get_registered_filenames()
    migrated: list[str] = []

    for model_type, entries in scanned.items():
        for entry in entries:
            filename = entry["filename"]
            if filename in registered:
                continue
            candidates = by_name.get(os.path.basename(filename).lower())
            if not candidates:
                continue
            sized = [c for c in candidates if _size_matches(c.size_bytes, entry["size_bytes"])]
            if not sized:
                continue

            path = os.path.join(entry["base_dir"], filename)
            try:
                digest = await _hash_file(path, entry["size_bytes"], entry["modified_at"])
            except OSError:
                # File vanished or became unreadable between the scan and the hash.
                _log.warning("Auto-migration could not read %s", path, exc_info=True)
                continue

            digest = digest.lower()
            match = next((c for c in sized if c.sha256.lower() == digest), None)
            if match is None:
                continue

            if await _register_match(entry, model_type, match, digest):
                registered.add(filename)
                migrated.append(filename)

    return migrated


async def _run(remote_files: list[RemoteFile]) -> list[str]:
    """Background entry point: never let a migration failure escape into the event loop."""
    try:
        return await migrate(remote_files)
    except Exception:
        _log.warning("Auto-migration pass failed", exc_info=True)
        return []


def schedule(remote_files: list[RemoteFile]) -> "asyncio.Task | None":
    """Fire-and-forget a migration pass so callers never block on hashing.

    Returns the spawned task (None when there was nothing to do). Callers ignore it;
    it exists so tests can await their own task rather than the global task set, which
    also holds never-completing workers.
    """
    if not remote_files:
        return None
    from ..background import spawn

    return spawn(_run(remote_files))
