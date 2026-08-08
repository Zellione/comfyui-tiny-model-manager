"""Import models from another ComfyUI installation's models folder (F-154).

Two background jobs drive the feature. The *scan* job walks a foreign models root and
SHA-256s every file to decide which are already in the local library; the *import* job
copies the selected files in, registers them and enriches them from CivitAI.

Import is **copy only** by design: a move would break the source installation
irreversibly, and links need admin rights on Windows or a shared filesystem.
"""

import asyncio
import os
import shutil
import time
import uuid
from dataclasses import dataclass, field

import folder_paths

from ..background import spawn
from ..db import model_repo
from . import disk_scanner, model_paths


class ForeignRootError(ValueError):
    """The supplied source path is not a usable foreign models root.

    The message is a stable error key (``path_not_absolute``, ``path_not_found``,
    ``path_is_local_root``) that the route layer hands to the UI for translation.
    """


def _local_model_roots() -> list[str]:
    """Every directory the local library already reads models from."""
    roots: list[str] = []
    models_dir = getattr(folder_paths, "models_dir", "")
    if models_dir:
        roots.append(models_dir)
    for dirs, _ in folder_paths.folder_names_and_paths.values():
        roots.extend(d for d in dirs if d)
    return roots


def _overlaps_local_library(real_root: str) -> bool:
    """True if ``real_root`` is, contains, or sits inside a local model directory.

    A containing directory counts: scanning it would list the local library's own files
    and the import would then copy them onto themselves.
    """
    for local in _local_model_roots():
        local_real = os.path.realpath(local)
        if (
            real_root == local_real
            or real_root.startswith(local_real + os.sep)
            or local_real.startswith(real_root + os.sep)
        ):
            return True
    return False


def validate_root(path: str) -> str:
    """Resolve a user-supplied foreign models root, or raise ``ForeignRootError``.

    A path holding a ``models`` subdirectory resolves to that subdirectory, so pasting a
    ComfyUI installation root works as well as pasting its models folder.
    """
    candidate = os.path.normpath(os.path.expanduser(path.strip())) if path.strip() else ""
    if not candidate or not os.path.isabs(candidate):
        raise ForeignRootError("path_not_absolute")
    if not os.path.isdir(candidate):
        raise ForeignRootError("path_not_found")

    nested = os.path.join(candidate, "models")
    if os.path.isdir(nested):
        candidate = nested

    real_root = os.path.realpath(candidate)
    if _overlaps_local_library(real_root):
        raise ForeignRootError("path_is_local_root")
    return real_root


@dataclass
class SourceFile:
    """One model file found in the foreign root.

    ``filename`` is relative to the type folder and always uses forward slashes, matching
    what ``disk_scanner.scan_dir`` yields and what the ``models`` table stores.
    """

    model_type: str
    filename: str
    abs_path: str
    size_bytes: int
    status: str = "pending"  # pending | new | installed | unreadable
    file_hash: str = ""


def scan_source(root: str) -> list[SourceFile]:
    """List every model file under ``root``, typed by its immediate subfolder name.

    A file sitting directly in the root has no type subfolder and is skipped: guessing a
    type would risk filing a LoRA into checkpoints.
    """
    files: list[SourceFile] = []
    for name in sorted(os.listdir(root)):
        type_dir = os.path.join(root, name)
        if name in disk_scanner.SKIP_TYPES or not os.path.isdir(type_dir):
            continue
        for entry in disk_scanner.scan_dir(type_dir, disk_scanner.BROAD_EXTENSIONS):
            files.append(
                SourceFile(
                    model_type=name,
                    filename=entry["filename"],
                    abs_path=os.path.join(type_dir, entry["filename"]),
                    size_bytes=entry["size_bytes"],
                )
            )
    return files


@dataclass
class ImportJob:
    """A running scan or import. Mirrors ``downloader.DownloadTask``'s in-memory shape."""

    id: str
    kind: str  # scan | import
    source_root: str
    state: str = "running"  # running | done | error | cancelled
    progress: float = 0.0
    error: str = ""
    files: list = field(default_factory=list)  # scan only: SourceFile entries
    imported: list = field(default_factory=list)  # import only: filenames
    skipped: list = field(default_factory=list)  # import only: filenames
    failed: list = field(default_factory=list)  # import only: {filename, reason}
    cancelled: bool = False
    completed_at: float | None = None
    task: asyncio.Task | None = field(default=None, repr=False)


_jobs: dict[str, ImportJob] = {}


def get_job(job_id: str) -> ImportJob | None:
    return _jobs.get(job_id)


def cancel_job(job_id: str) -> bool:
    """Ask a running job to stop after its current file. Returns False if it already ended."""
    job = _jobs.get(job_id)
    if job is None or job.state != "running":
        return False
    job.cancelled = True
    return True


def job_to_dict(job: ImportJob) -> dict:
    """Serialise a job for the API.

    ``abs_path`` is deliberately omitted: it is a filesystem path on the operator's machine
    and the client never needs it — the import route rebuilds it from the validated root.
    """
    return {
        "id": job.id,
        "kind": job.kind,
        "source_root": job.source_root,
        "state": job.state,
        "progress": job.progress,
        "error": job.error,
        "files": [
            {
                "model_type": f.model_type,
                "filename": f.filename,
                "size_bytes": f.size_bytes,
                "status": f.status,
                "file_hash": f.file_hash,
            }
            for f in job.files
        ],
        "imported": job.imported,
        "skipped": job.skipped,
        "failed": job.failed,
    }


async def _hash_unknown_local_files() -> set[str]:
    """Every SHA-256 in the local library, hashing what the DB does not already know.

    Hashes computed for a *registered* model are written back with ``set_file_hash`` so the
    next scan is nearly free. An unregistered on-disk file has no row to cache into and is
    therefore re-hashed each time; registering it is what makes it cheap.
    """
    known = await model_repo.get_file_hash_map()
    hashes = set(known)
    hashed_filenames = set(known.values())

    scanned = await asyncio.to_thread(disk_scanner.scan_all)
    for entries in scanned.values():
        for entry in entries:
            if entry["filename"] in hashed_filenames:
                continue
            path = os.path.join(entry["base_dir"], entry["filename"])
            try:
                digest = await asyncio.to_thread(model_paths.compute_file_hash, path)
            except OSError:
                continue
            hashes.add(digest)
            await model_repo.set_file_hash(entry["filename"], digest)
    return hashes


async def _run_scan(job: ImportJob) -> None:
    try:
        job.files = await asyncio.to_thread(scan_source, job.source_root)
        local_hashes = await _hash_unknown_local_files()
        total = len(job.files)
        if not total:
            job.progress = 100.0
        for index, source in enumerate(job.files):
            if job.cancelled:
                job.state = "cancelled"
                return
            try:
                source.file_hash = await asyncio.to_thread(
                    model_paths.compute_file_hash, source.abs_path
                )
            except OSError:
                source.status = "unreadable"
            else:
                source.status = "installed" if source.file_hash in local_hashes else "new"
            job.progress = (index + 1) / total * 100
        job.state = "done"
    except Exception as exc:
        job.state = "error"
        job.error = str(exc)
    finally:
        job.completed_at = time.time()


def start_scan(root: str) -> ImportJob:
    """Begin scanning an already-validated foreign models root."""
    job = ImportJob(id=str(uuid.uuid4()), kind="scan", source_root=root)
    _jobs[job.id] = job
    job.task = spawn(_run_scan(job))
    return job


class InsufficientSpaceError(RuntimeError):
    """Not enough free space on the destination filesystem for the selected files."""

    def __init__(self, needed: int, available: int):
        super().__init__("insufficient_space")
        self.needed = needed
        self.available = available


def dest_base(model_type: str) -> str:
    """The local directory an imported model of ``model_type`` belongs in."""
    if not model_paths.is_safe_segment(model_type):
        raise ValueError("invalid_model_type")
    dirs = model_paths.candidate_dirs(model_type)
    if dirs:
        return dirs[0]
    return os.path.join(folder_paths.models_dir, model_type)


def resolve_destination(model_type: str, filename: str) -> str:
    """Absolute destination for ``filename``, confined to the type's local directory."""
    dest = model_paths.contained_path(dest_base(model_type), filename)
    if dest is None:
        raise ValueError("unsafe_filename")
    return dest


def source_path(root: str, model_type: str, filename: str) -> str:
    """Absolute path of a selected source file, confined to ``root/model_type``."""
    if not model_paths.is_safe_segment(model_type):
        raise ValueError("invalid_model_type")
    path = model_paths.contained_path(os.path.join(root, model_type), filename)
    if path is None or not os.path.isfile(path):
        raise ValueError("source_not_found")
    return path


def _unique_path(dest: str) -> str:
    """``dest``, or the first ``_1``/``_2``… variant that does not exist yet."""
    if not os.path.exists(dest):
        return dest
    stem, ext = os.path.splitext(dest)
    counter = 1
    while os.path.exists(f"{stem}_{counter}{ext}"):
        counter += 1
    return f"{stem}_{counter}{ext}"


def copy_file(src: str, dest: str) -> str:
    """Copy ``src`` to ``dest``, returning the path actually written.

    The copy lands on a ``.tmm-part`` temporary name and is renamed into place only once
    complete, so an interrupted copy never leaves a truncated file that looks like a
    working model. Synchronous; call via ``asyncio.to_thread``.
    """
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    final = _unique_path(dest)
    part = final + ".tmm-part"
    try:
        shutil.copyfile(src, part)
        os.replace(part, final)
    except Exception:
        if os.path.exists(part):
            os.remove(part)
        raise
    return final


def ensure_space(dest_dir: str, needed_bytes: int) -> None:
    """Raise ``InsufficientSpaceError`` unless ``dest_dir`` has room for ``needed_bytes``."""
    os.makedirs(dest_dir, exist_ok=True)
    available = shutil.disk_usage(dest_dir).free
    if available < needed_bytes:
        raise InsufficientSpaceError(needed_bytes, available)


async def _civitai_lookup(sha256: str) -> dict | None:
    """Patchable seam: the CivitAI by-hash lookup used to enrich an imported model.

    HuggingFace exposes no by-hash endpoint, so enrichment is CivitAI-only; an HF-origin
    model imports without metadata and the user can re-fetch it from the detail page.
    """
    from .providers.civitai_provider import CivitaiProvider

    return await CivitaiProvider().lookup_by_hash(sha256)


async def _register_imported(final_path: str, model_type: str, file_hash: str) -> None:
    """Register a freshly copied file, then fill in CivitAI metadata if the hash matches."""
    relative = os.path.relpath(final_path, dest_base(model_type)).replace("\\", "/")
    if not file_hash:
        file_hash = await asyncio.to_thread(model_paths.compute_file_hash, final_path)
    await model_repo.register_model(relative, model_type, file_hash=file_hash)

    try:
        metadata = await _civitai_lookup(file_hash)
    except Exception:
        metadata = None
    if not metadata:
        return

    # register_model is an upsert, so this fills in the fields the first call left empty.
    await model_repo.register_model(
        relative,
        model_type,
        base_model=metadata.get("base_model", ""),
        tags=metadata.get("tags", []),
        description=metadata.get("description", ""),
        file_hash=file_hash,
        source_platform="civitai",
        source_id=str(metadata.get("civitai_version_id", "") or ""),
        civitai_model_id=str(metadata.get("civitai_model_id", "") or ""),
    )


async def _import_one(job: ImportJob, selection: dict) -> None:
    relative = selection.get("filename", "")
    model_type = selection.get("model_type", "")
    try:
        src = source_path(job.source_root, model_type, relative)
        dest = resolve_destination(model_type, relative)
        final = await asyncio.to_thread(copy_file, src, dest)
    except ValueError as exc:
        job.failed.append({"filename": relative, "reason": str(exc)})
        return
    except OSError as exc:
        job.failed.append({"filename": relative, "reason": exc.strerror or "copy_failed"})
        return
    await _register_imported(final, model_type, selection.get("file_hash", ""))
    job.imported.append(relative)


async def _run_import(job: ImportJob, selections: list[dict]) -> None:
    try:
        total = len(selections)
        if not total:
            job.progress = 100.0
        for index, selection in enumerate(selections):
            if job.cancelled:
                job.state = "cancelled"
                return
            await _import_one(job, selection)
            job.progress = (index + 1) / total * 100
        job.state = "done"
    except Exception as exc:
        job.state = "error"
        job.error = str(exc)
    finally:
        job.completed_at = time.time()


def start_import(root: str, selections: list[dict]) -> ImportJob:
    """Begin copying ``selections`` out of an already-validated foreign root.

    Each selection is ``{"model_type", "filename", "file_hash"}``; ``file_hash`` carries the
    digest the scan already computed so the file is never hashed twice.
    """
    job = ImportJob(id=str(uuid.uuid4()), kind="import", source_root=root)
    _jobs[job.id] = job
    job.task = spawn(_run_import(job, selections))
    return job
