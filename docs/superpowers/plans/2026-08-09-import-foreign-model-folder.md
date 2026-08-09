# Import models from a foreign ComfyUI folder — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a user point at another ComfyUI installation's models folder, see which models are new, and copy the selected ones into the local library with CivitAI metadata.

**Architecture:** A new backend service `py/services/foreign_import.py` owns two background jobs — a *scan* job (walk the foreign root, SHA-256 every file, mark each `new` or `installed`) and an *import* job (copy, register, enrich). Job state lives in an in-memory registry mirroring `py/services/downloader.py`'s `_tasks` dict. Routes in `py/routes/imports.py` start jobs and report progress; a new Angular page at `models/import` polls them.

**Tech Stack:** Python 3.12, aiohttp, aiosqlite, pytest / pytest-asyncio. Angular 21.2 zoneless (signals, `OnPush`), RxJS, ngx-translate, Vitest.

**Spec:** `docs/superpowers/specs/2026-08-09-import-foreign-model-folder-design.md`
**Issue:** https://github.com/Zellione/comfyui-tiny-model-manager/issues/154
**Branch:** `import-foreign-model-folder` (already checked out)

## Global Constraints

- **Import mode is copy only.** No move, no symlink, no hardlink. Do not add them.
- **Nothing is written or deleted by a raw request path.** Every destination goes through `model_paths.contained_path` or `model_paths.is_safe_segment`. Sonar's taint analysis (S2083/S6549) flags anything else.
- **The autouse `block_network` fixture forbids real outbound requests in tests.** Every CivitAI call must be monkeypatched at a module-level `_xxx` seam.
- **Never drain `background._background_tasks` in a test** — it holds the downloader's `while True` worker and will hang the suite. Await the specific task instead.
- **Frontend:** `ChangeDetectionStrategy.OnPush`, signals only (no Zone.js), every `.subscribe()` guarded with `takeUntilDestroyed(this.destroyRef)`, every polling `switchMap` containing its own `catchError(() => of(fallback))`, all user-visible strings via ngx-translate keys in `frontend/public/i18n/en.json`.
- **After creating any new file under `frontend/`, immediately run `npx prettier --write <file>`.** The Write tool does not format and CI's `format:check` will fail otherwise.
- **Commits and code comments in English.** Never mention Claude as co-author.
- Backend commands run from the project root: `PYTHONSAFEPATH=1 ../../../comfy-env/bin/python -m pytest`, `../../../comfy-env/bin/python -m ruff check py tests conftest.py`, `../../../comfy-env/bin/python -m ruff format py tests conftest.py`.
- Frontend commands run from `frontend/`.

## File Structure

**Create**
- `py/services/foreign_import.py` — path validation, source scan, copy, job registry, both job runners
- `py/routes/imports.py` — the five HTTP routes
- `tests/test_foreign_import.py` — service unit tests
- `tests/test_routes_imports.py` — route integration tests
- `frontend/src/app/services/model-import.ts` — HTTP client + polling
- `frontend/src/app/services/model-import.spec.ts`
- `frontend/src/app/pages/model-import/model-import.ts` / `.html` / `.css` / `.spec.ts`

**Modify**
- `py/services/disk_scanner.py` — make `_BROAD_EXTENSIONS` / `_SKIP_TYPES` public
- `py/db/model_repo.py` — add `set_file_hash`
- `py/routes/__init__.py` — register the new routes
- `frontend/src/app/services/settings.ts` — add `import_source_root?: string` to `TmmSettings`
- `frontend/src/app/app.routes.ts` — add `models/import` **before** `models/:platform`
- `frontend/src/app/pages/models/models.html` — "Import from another folder" button
- `frontend/public/i18n/en.json` — translation keys
- `README.md` — feature checklist

---

### Task 1: Foreign root validation

**Files:**
- Create: `py/services/foreign_import.py`
- Create: `tests/test_foreign_import.py`

**Interfaces:**
- Consumes: `folder_paths.models_dir`, `folder_paths.folder_names_and_paths`
- Produces: `ForeignRootError(ValueError)`, `validate_root(path: str) -> str`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_foreign_import.py`:

```python
"""Unit tests for py/services/foreign_import.py (F-154)."""

import os

import pytest


class TestValidateRoot:
    def test_relative_path_rejected(self, ext_dir):
        from py.services import foreign_import

        with pytest.raises(foreign_import.ForeignRootError) as excinfo:
            foreign_import.validate_root("some/relative/dir")
        assert str(excinfo.value) == "path_not_absolute"

    def test_blank_path_rejected(self, ext_dir):
        from py.services import foreign_import

        with pytest.raises(foreign_import.ForeignRootError):
            foreign_import.validate_root("   ")

    def test_missing_path_rejected(self, tmp_path, ext_dir):
        from py.services import foreign_import

        missing = str(tmp_path / "nope")
        with pytest.raises(foreign_import.ForeignRootError) as excinfo:
            foreign_import.validate_root(missing)
        assert str(excinfo.value) == "path_not_found"

    def test_file_is_not_a_directory(self, tmp_path, ext_dir):
        from py.services import foreign_import

        target = tmp_path / "a.txt"
        target.write_text("x")
        with pytest.raises(foreign_import.ForeignRootError) as excinfo:
            foreign_import.validate_root(str(target))
        assert str(excinfo.value) == "path_not_found"

    def test_models_subdir_is_appended(self, tmp_path, ext_dir):
        from py.services import foreign_import

        (tmp_path / "models" / "loras").mkdir(parents=True)
        resolved = foreign_import.validate_root(str(tmp_path))
        assert resolved == os.path.realpath(str(tmp_path / "models"))

    def test_models_root_used_as_is(self, tmp_path, ext_dir):
        from py.services import foreign_import

        root = tmp_path / "models"
        (root / "loras").mkdir(parents=True)
        resolved = foreign_import.validate_root(str(root))
        assert resolved == os.path.realpath(str(root))

    def test_local_models_root_rejected(self, tmp_path, monkeypatch, ext_dir):
        import folder_paths

        from py.services import foreign_import

        local = tmp_path / "local_models"
        (local / "loras").mkdir(parents=True)
        monkeypatch.setattr(folder_paths, "models_dir", str(local))
        with pytest.raises(foreign_import.ForeignRootError) as excinfo:
            foreign_import.validate_root(str(local))
        assert str(excinfo.value) == "path_is_local_root"

    def test_parent_of_local_root_rejected(self, tmp_path, monkeypatch, ext_dir):
        import folder_paths

        from py.services import foreign_import

        local = tmp_path / "comfy" / "models"
        (local / "loras").mkdir(parents=True)
        monkeypatch.setattr(folder_paths, "models_dir", str(local))
        with pytest.raises(foreign_import.ForeignRootError) as excinfo:
            foreign_import.validate_root(str(tmp_path / "comfy"))
        assert str(excinfo.value) == "path_is_local_root"

    def test_registered_folder_dir_rejected(self, tmp_path, monkeypatch, ext_dir):
        import folder_paths

        from py.services import foreign_import

        custom = tmp_path / "extra" / "loras"
        custom.mkdir(parents=True)
        monkeypatch.setattr(
            folder_paths, "folder_names_and_paths", {"loras": ([str(custom)], {".safetensors"})}
        )
        with pytest.raises(foreign_import.ForeignRootError) as excinfo:
            foreign_import.validate_root(str(custom))
        assert str(excinfo.value) == "path_is_local_root"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `PYTHONSAFEPATH=1 ../../../comfy-env/bin/python -m pytest tests/test_foreign_import.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'py.services.foreign_import'`

- [ ] **Step 3: Write the implementation**

Create `py/services/foreign_import.py`:

```python
"""Import models from another ComfyUI installation's models folder (F-154).

Two background jobs drive the feature. The *scan* job walks a foreign models root and
SHA-256s every file to decide which are already in the local library; the *import* job
copies the selected files in, registers them and enriches them from CivitAI.

Import is **copy only** by design: a move would break the source installation
irreversibly, and links need admin rights on Windows or a shared filesystem.
"""

import os

import folder_paths


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
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `PYTHONSAFEPATH=1 ../../../comfy-env/bin/python -m pytest tests/test_foreign_import.py -v`
Expected: PASS (10 tests)

- [ ] **Step 5: Lint and commit**

```bash
../../../comfy-env/bin/python -m ruff format py/services/foreign_import.py tests/test_foreign_import.py
../../../comfy-env/bin/python -m ruff check py tests conftest.py
git add py/services/foreign_import.py tests/test_foreign_import.py
git commit -m "feat(import): validate a foreign ComfyUI models root (#154)"
```

---

### Task 2: Scan the foreign folder

**Files:**
- Modify: `py/services/disk_scanner.py` (make two constants public)
- Modify: `py/services/foreign_import.py`
- Modify: `tests/test_foreign_import.py`

**Interfaces:**
- Consumes: `validate_root` from Task 1; `disk_scanner.scan_dir(base_dir, extensions)`
- Produces: `SourceFile` dataclass with fields `model_type: str`, `filename: str`, `abs_path: str`, `size_bytes: int`, `status: str = "pending"`, `file_hash: str = ""`; and `scan_source(root: str) -> list[SourceFile]`

- [ ] **Step 1: Make the disk_scanner constants public**

`_BROAD_EXTENSIONS` and `_SKIP_TYPES` in `py/services/disk_scanner.py` are needed by a second
service now, so drop the underscore. Use Serena's reference-aware rename so every usage moves
with the definition:

- `mcp__serena__rename_symbol` on `_BROAD_EXTENSIONS` in `py/services/disk_scanner.py` → `BROAD_EXTENSIONS`
- `mcp__serena__rename_symbol` on `_SKIP_TYPES` in `py/services/disk_scanner.py` → `SKIP_TYPES`

Then confirm nothing was missed:

```bash
grep -rn "_BROAD_EXTENSIONS\|_SKIP_TYPES" py/ tests/
```
Expected: no output.

- [ ] **Step 2: Write the failing tests**

Append to `tests/test_foreign_import.py`:

```python
def _make_source_tree(tmp_path):
    """Build a small foreign models root and return its path."""
    root = tmp_path / "foreign" / "models"
    (root / "checkpoints").mkdir(parents=True)
    (root / "loras" / "style").mkdir(parents=True)
    (root / "configs").mkdir(parents=True)
    (root / "checkpoints" / "sd15.safetensors").write_bytes(b"a" * 16)
    (root / "loras" / "style" / "neon.safetensors").write_bytes(b"b" * 32)
    (root / "loras" / "notes.txt").write_text("ignored")
    (root / "configs" / "cfg.safetensors").write_bytes(b"c" * 8)
    (root / "loose.safetensors").write_bytes(b"d" * 4)
    return root


class TestScanSource:
    def test_groups_by_type_subfolder(self, tmp_path, ext_dir):
        from py.services import foreign_import

        files = foreign_import.scan_source(str(_make_source_tree(tmp_path)))
        assert {f.model_type for f in files} == {"checkpoints", "loras"}

    def test_preserves_relative_subfolder(self, tmp_path, ext_dir):
        from py.services import foreign_import

        files = foreign_import.scan_source(str(_make_source_tree(tmp_path)))
        lora = next(f for f in files if f.model_type == "loras")
        assert lora.filename == "style/neon.safetensors"

    def test_records_absolute_path_and_size(self, tmp_path, ext_dir):
        from py.services import foreign_import

        root = _make_source_tree(tmp_path)
        files = foreign_import.scan_source(str(root))
        ckpt = next(f for f in files if f.model_type == "checkpoints")
        assert ckpt.abs_path == os.path.join(str(root), "checkpoints", "sd15.safetensors")
        assert ckpt.size_bytes == 16

    def test_non_model_extensions_ignored(self, tmp_path, ext_dir):
        from py.services import foreign_import

        files = foreign_import.scan_source(str(_make_source_tree(tmp_path)))
        assert all(not f.filename.endswith(".txt") for f in files)

    def test_skip_types_ignored(self, tmp_path, ext_dir):
        from py.services import foreign_import

        files = foreign_import.scan_source(str(_make_source_tree(tmp_path)))
        assert all(f.model_type != "configs" for f in files)

    def test_loose_files_at_root_ignored(self, tmp_path, ext_dir):
        """A file directly in the models root has no type subfolder, so it has no type."""
        from py.services import foreign_import

        files = foreign_import.scan_source(str(_make_source_tree(tmp_path)))
        assert all(f.filename != "loose.safetensors" for f in files)

    def test_files_start_pending_and_unhashed(self, tmp_path, ext_dir):
        from py.services import foreign_import

        files = foreign_import.scan_source(str(_make_source_tree(tmp_path)))
        assert {f.status for f in files} == {"pending"}
        assert all(f.file_hash == "" for f in files)
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `PYTHONSAFEPATH=1 ../../../comfy-env/bin/python -m pytest tests/test_foreign_import.py::TestScanSource -v`
Expected: FAIL — `AttributeError: module 'py.services.foreign_import' has no attribute 'scan_source'`

- [ ] **Step 4: Write the implementation**

In `py/services/foreign_import.py`, extend the imports and append the code below.

Replace the import block at the top of the file with:

```python
import os
from dataclasses import dataclass

import folder_paths

from . import disk_scanner
```

Append at the end of the file:

```python
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
```

- [ ] **Step 5: Run the whole backend suite to verify the rename broke nothing**

Run: `PYTHONSAFEPATH=1 ../../../comfy-env/bin/python -m pytest`
Expected: PASS, all tests

- [ ] **Step 6: Lint and commit**

```bash
../../../comfy-env/bin/python -m ruff format py tests conftest.py
../../../comfy-env/bin/python -m ruff check py tests conftest.py
git add py/services/disk_scanner.py py/services/foreign_import.py tests/test_foreign_import.py
git commit -m "feat(import): scan a foreign models root by type subfolder (#154)"
```

---

### Task 3: Persist a computed hash on an existing model row

**Files:**
- Modify: `py/db/model_repo.py`
- Create: `tests/test_model_repo_file_hash.py`

**Interfaces:**
- Consumes: `get_db` from `py/db/database.py` (already imported in `model_repo`)
- Produces: `async set_file_hash(filename: str, file_hash: str) -> bool` — returns True when a row was updated

- [ ] **Step 1: Write the failing tests**

Create `tests/test_model_repo_file_hash.py`:

```python
"""Unit tests for model_repo.set_file_hash (F-154)."""


class TestSetFileHash:
    async def test_updates_registered_model(self, ext_dir):
        from py.db import model_repo

        await model_repo.register_model("a.safetensors", "loras")
        updated = await model_repo.set_file_hash("a.safetensors", "abc123")
        assert updated is True
        assert await model_repo.get_file_hash_map() == {"abc123": "a.safetensors"}

    async def test_unknown_filename_is_a_no_op(self, ext_dir):
        from py.db import model_repo

        updated = await model_repo.set_file_hash("ghost.safetensors", "abc123")
        assert updated is False
        assert await model_repo.get_file_hash_map() == {}

    async def test_hash_is_lowercased(self, ext_dir):
        from py.db import model_repo

        await model_repo.register_model("b.safetensors", "loras")
        await model_repo.set_file_hash("b.safetensors", "ABC123")
        assert await model_repo.get_file_hash_map() == {"abc123": "b.safetensors"}
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `PYTHONSAFEPATH=1 ../../../comfy-env/bin/python -m pytest tests/test_model_repo_file_hash.py -v`
Expected: FAIL — `AttributeError: module 'py.db.model_repo' has no attribute 'set_file_hash'`

- [ ] **Step 3: Write the implementation**

Insert immediately after `get_file_hash_map` in `py/db/model_repo.py`:

```python
async def set_file_hash(filename: str, file_hash: str) -> bool:
    """Store a SHA-256 on an already-registered model. Returns True if a row changed.

    The foreign-folder import (F-154) hashes local files the DB does not know a hash for
    and caches the result here, so a repeated scan does not re-read the whole library.
    An unregistered on-disk file has no row, so it is silently a no-op.
    """
    async with get_db() as db:
        cursor = await db.execute(
            "UPDATE models SET file_hash = ? WHERE filename = ?",
            (file_hash.lower(), filename),
        )
        await db.commit()
        return cursor.rowcount > 0
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `PYTHONSAFEPATH=1 ../../../comfy-env/bin/python -m pytest tests/test_model_repo_file_hash.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Lint and commit**

```bash
../../../comfy-env/bin/python -m ruff format py tests conftest.py
../../../comfy-env/bin/python -m ruff check py tests conftest.py
git add py/db/model_repo.py tests/test_model_repo_file_hash.py
git commit -m "feat(db): add set_file_hash for caching computed model hashes (#154)"
```

---

### Task 4: The scan job

**Files:**
- Modify: `py/services/foreign_import.py`
- Modify: `tests/test_foreign_import.py`

**Interfaces:**
- Consumes: `scan_source` (Task 2), `model_repo.set_file_hash` (Task 3), `model_repo.get_file_hash_map`, `model_paths.compute_file_hash`, `disk_scanner.scan_all`, `background.spawn`
- Produces: `ImportJob` dataclass (`id`, `kind`, `source_root`, `state`, `progress`, `error`, `files`, `imported`, `skipped`, `failed`, `cancelled`, `completed_at`); `start_scan(root: str) -> ImportJob`; `get_job(job_id: str) -> ImportJob | None`; `cancel_job(job_id: str) -> bool`; `job_to_dict(job: ImportJob) -> dict`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_foreign_import.py`:

```python
class TestScanJob:
    async def test_marks_unknown_files_new(self, tmp_path, ext_dir):
        from py.services import foreign_import

        root = _make_source_tree(tmp_path)
        job = foreign_import.start_scan(str(root))
        await job.task
        assert job.state == "done"
        assert {f.status for f in job.files} == {"new"}
        assert job.progress == 100.0

    async def test_marks_locally_present_hash_installed(self, tmp_path, monkeypatch, ext_dir):
        from py.db import model_repo
        from py.services import foreign_import, model_paths

        root = _make_source_tree(tmp_path)
        known = model_paths.compute_file_hash(str(root / "checkpoints" / "sd15.safetensors"))
        await model_repo.register_model("sd15.safetensors", "checkpoints")
        await model_repo.set_file_hash("sd15.safetensors", known)
        monkeypatch.setattr(foreign_import, "_hash_unknown_local_files", _noop_local_hashes)

        job = foreign_import.start_scan(str(root))
        await job.task
        statuses = {f.filename: f.status for f in job.files}
        assert statuses["sd15.safetensors"] == "installed"
        assert statuses["style/neon.safetensors"] == "new"

    async def test_unreadable_file_does_not_fail_the_job(self, tmp_path, monkeypatch, ext_dir):
        from py.services import foreign_import

        root = _make_source_tree(tmp_path)
        monkeypatch.setattr(foreign_import, "_hash_unknown_local_files", _noop_local_hashes)

        def boom(path):
            if path.endswith("sd15.safetensors"):
                raise OSError("permission denied")
            return "deadbeef"

        monkeypatch.setattr(foreign_import.model_paths, "compute_file_hash", boom)
        job = foreign_import.start_scan(str(root))
        await job.task
        assert job.state == "done"
        statuses = {f.filename: f.status for f in job.files}
        assert statuses["sd15.safetensors"] == "unreadable"

    async def test_local_hashes_are_cached_back_to_the_db(self, tmp_path, monkeypatch, ext_dir):
        import folder_paths

        from py.db import model_repo
        from py.services import foreign_import, model_paths

        local = tmp_path / "local" / "models"
        (local / "loras").mkdir(parents=True)
        (local / "loras" / "known.safetensors").write_bytes(b"z" * 12)
        monkeypatch.setattr(folder_paths, "models_dir", str(local))
        await model_repo.register_model("known.safetensors", "loras")

        root = _make_source_tree(tmp_path)
        job = foreign_import.start_scan(str(root))
        await job.task

        expected = model_paths.compute_file_hash(str(local / "loras" / "known.safetensors"))
        assert await model_repo.get_file_hash_map() == {expected: "known.safetensors"}

    async def test_cancel_stops_the_scan(self, tmp_path, monkeypatch, ext_dir):
        from py.services import foreign_import

        root = _make_source_tree(tmp_path)
        monkeypatch.setattr(foreign_import, "_hash_unknown_local_files", _noop_local_hashes)
        job = foreign_import.start_scan(str(root))
        foreign_import.cancel_job(job.id)
        await job.task
        assert job.state == "cancelled"

    async def test_get_job_and_serialisation(self, tmp_path, ext_dir):
        from py.services import foreign_import

        root = _make_source_tree(tmp_path)
        job = foreign_import.start_scan(str(root))
        await job.task
        assert foreign_import.get_job(job.id) is job
        assert foreign_import.get_job("nope") is None
        payload = foreign_import.job_to_dict(job)
        assert payload["state"] == "done"
        assert payload["source_root"] == str(root)
        assert {f["status"] for f in payload["files"]} == {"new"}
        assert "abs_path" not in payload["files"][0]


async def _noop_local_hashes() -> set[str]:
    """Stand-in for the local-library hash sweep, which needs no files in most tests."""
    from py.db import model_repo

    return set(await model_repo.get_file_hash_map())
```

Add this import at the top of `tests/test_foreign_import.py`, below the existing ones:

```python
import pytest  # already present — no change needed
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `PYTHONSAFEPATH=1 ../../../comfy-env/bin/python -m pytest tests/test_foreign_import.py::TestScanJob -v`
Expected: FAIL — `AttributeError: module 'py.services.foreign_import' has no attribute 'start_scan'`

- [ ] **Step 3: Write the implementation**

Replace the import block at the top of `py/services/foreign_import.py` with:

```python
import asyncio
import os
import time
import uuid
from dataclasses import dataclass, field

import folder_paths

from ..background import spawn
from ..db import model_repo
from . import disk_scanner, model_paths
```

Append at the end of `py/services/foreign_import.py`:

```python
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
    except Exception as exc:  # noqa: BLE001 - surfaced to the client as job.error
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
```

- [ ] **Step 4: Run the tests to verify they pass**

`background.spawn` already returns the `asyncio.Task` (verified in `py/background.py:13`), so
`job.task` is populated and the tests above can await it. No change to `background.py` is needed.

Run: `PYTHONSAFEPATH=1 ../../../comfy-env/bin/python -m pytest tests/test_foreign_import.py -v`
Expected: PASS

- [ ] **Step 5: Lint and commit**

```bash
../../../comfy-env/bin/python -m ruff format py tests conftest.py
../../../comfy-env/bin/python -m ruff check py tests conftest.py
git add py/services/foreign_import.py tests/test_foreign_import.py
git commit -m "feat(import): scan job hashes the foreign folder against the local library (#154)"
```

---

### Task 5: Destination resolution and safe copy

**Files:**
- Modify: `py/services/foreign_import.py`
- Modify: `tests/test_foreign_import.py`

**Interfaces:**
- Consumes: `model_paths.is_safe_segment`, `model_paths.candidate_dirs`, `model_paths.contained_path`
- Produces: `InsufficientSpaceError(RuntimeError)` with `.needed` and `.available`; `dest_base(model_type: str) -> str`; `resolve_destination(model_type: str, filename: str) -> str`; `copy_file(src: str, dest: str) -> str`; `ensure_space(dest_dir: str, needed_bytes: int) -> None`; `source_path(root: str, model_type: str, filename: str) -> str`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_foreign_import.py`:

```python
class TestDestinationAndCopy:
    def test_dest_base_uses_first_candidate_dir(self, tmp_path, monkeypatch, ext_dir):
        import folder_paths

        from py.services import foreign_import

        monkeypatch.setattr(folder_paths, "models_dir", str(tmp_path / "local"))
        assert foreign_import.dest_base("loras") == os.path.join(
            str(tmp_path / "local"), "loras"
        )

    def test_unsafe_model_type_rejected(self, ext_dir):
        from py.services import foreign_import

        with pytest.raises(ValueError, match="invalid_model_type"):
            foreign_import.dest_base("..")

    def test_traversing_filename_rejected(self, tmp_path, monkeypatch, ext_dir):
        import folder_paths

        from py.services import foreign_import

        monkeypatch.setattr(folder_paths, "models_dir", str(tmp_path / "local"))
        with pytest.raises(ValueError, match="unsafe_filename"):
            foreign_import.resolve_destination("loras", "../../escape.safetensors")

    def test_resolve_destination_keeps_subfolder(self, tmp_path, monkeypatch, ext_dir):
        import folder_paths

        from py.services import foreign_import

        monkeypatch.setattr(folder_paths, "models_dir", str(tmp_path / "local"))
        dest = foreign_import.resolve_destination("loras", "style/neon.safetensors")
        assert dest.endswith(os.path.join("loras", "style", "neon.safetensors"))

    def test_copy_creates_the_file(self, tmp_path, ext_dir):
        from py.services import foreign_import

        src = tmp_path / "src.safetensors"
        src.write_bytes(b"payload")
        dest = tmp_path / "out" / "dest.safetensors"
        final = foreign_import.copy_file(str(src), str(dest))
        assert final == str(dest)
        assert (tmp_path / "out" / "dest.safetensors").read_bytes() == b"payload"

    def test_copy_suffixes_on_collision(self, tmp_path, ext_dir):
        from py.services import foreign_import

        src = tmp_path / "src.safetensors"
        src.write_bytes(b"payload")
        dest = tmp_path / "dest.safetensors"
        dest.write_bytes(b"existing")
        final = foreign_import.copy_file(str(src), str(dest))
        assert final == str(tmp_path / "dest_1.safetensors")
        assert dest.read_bytes() == b"existing"

    def test_failed_copy_leaves_no_partial_file(self, tmp_path, monkeypatch, ext_dir):
        import shutil

        from py.services import foreign_import

        src = tmp_path / "src.safetensors"
        src.write_bytes(b"payload")
        dest = tmp_path / "out" / "dest.safetensors"

        def boom(source, target):
            with open(target, "wb") as handle:
                handle.write(b"half")
            raise OSError("disk fell over")

        monkeypatch.setattr(shutil, "copyfile", boom)
        with pytest.raises(OSError):
            foreign_import.copy_file(str(src), str(dest))
        assert list((tmp_path / "out").iterdir()) == []

    def test_ensure_space_raises_when_short(self, tmp_path, monkeypatch, ext_dir):
        import shutil

        from py.services import foreign_import

        monkeypatch.setattr(
            shutil, "disk_usage", lambda path: shutil._ntuple_diskusage(100, 90, 10)
        )
        with pytest.raises(foreign_import.InsufficientSpaceError) as excinfo:
            foreign_import.ensure_space(str(tmp_path), 50)
        assert excinfo.value.needed == 50
        assert excinfo.value.available == 10

    def test_ensure_space_passes_when_ample(self, tmp_path, ext_dir):
        from py.services import foreign_import

        foreign_import.ensure_space(str(tmp_path), 1)

    def test_source_path_rejects_traversal(self, tmp_path, ext_dir):
        from py.services import foreign_import

        root = _make_source_tree(tmp_path)
        with pytest.raises(ValueError, match="source_not_found"):
            foreign_import.source_path(str(root), "loras", "../../etc/passwd")

    def test_source_path_resolves_existing_file(self, tmp_path, ext_dir):
        from py.services import foreign_import

        root = _make_source_tree(tmp_path)
        resolved = foreign_import.source_path(str(root), "loras", "style/neon.safetensors")
        assert os.path.isfile(resolved)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `PYTHONSAFEPATH=1 ../../../comfy-env/bin/python -m pytest tests/test_foreign_import.py::TestDestinationAndCopy -v`
Expected: FAIL — `AttributeError: module 'py.services.foreign_import' has no attribute 'dest_base'`

- [ ] **Step 3: Write the implementation**

Add `import shutil` to the import block in `py/services/foreign_import.py` (keep the imports
alphabetically ordered: `asyncio`, `os`, `shutil`, `time`, `uuid`).

Append at the end of the file:

```python
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
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `PYTHONSAFEPATH=1 ../../../comfy-env/bin/python -m pytest tests/test_foreign_import.py -v`
Expected: PASS

- [ ] **Step 5: Lint and commit**

```bash
../../../comfy-env/bin/python -m ruff format py tests conftest.py
../../../comfy-env/bin/python -m ruff check py tests conftest.py
git add py/services/foreign_import.py tests/test_foreign_import.py
git commit -m "feat(import): resolve destinations and copy safely via a part file (#154)"
```

---

### Task 6: The import job

**Files:**
- Modify: `py/services/foreign_import.py`
- Modify: `tests/test_foreign_import.py`

**Interfaces:**
- Consumes: everything from Tasks 1–5, plus `model_repo.register_model`
- Produces: `_civitai_lookup(sha256: str) -> dict | None` (monkeypatch seam); `start_import(root: str, selections: list[dict]) -> ImportJob` where each selection is `{"model_type": str, "filename": str, "file_hash": str}`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_foreign_import.py`:

```python
class TestImportJob:
    async def test_copies_and_registers(self, tmp_path, monkeypatch, ext_dir):
        import folder_paths

        from py.db import model_repo
        from py.services import foreign_import

        monkeypatch.setattr(folder_paths, "models_dir", str(tmp_path / "local"))
        monkeypatch.setattr(foreign_import, "_civitai_lookup", _no_civitai_match)
        root = _make_source_tree(tmp_path)

        job = foreign_import.start_import(
            str(root),
            [{"model_type": "loras", "filename": "style/neon.safetensors", "file_hash": ""}],
        )
        await job.task

        assert job.state == "done"
        assert job.imported == ["style/neon.safetensors"]
        assert job.failed == []
        copied = tmp_path / "local" / "loras" / "style" / "neon.safetensors"
        assert copied.read_bytes() == b"b" * 32
        rows = await model_repo.get_file_hash_map()
        assert list(rows.values()) == ["style/neon.safetensors"]

    async def test_enriches_from_civitai(self, tmp_path, monkeypatch, ext_dir):
        import folder_paths

        from py.db import model_repo
        from py.services import foreign_import

        monkeypatch.setattr(folder_paths, "models_dir", str(tmp_path / "local"))

        async def fake_lookup(sha256):
            return {
                "base_model": "SDXL 1.0",
                "description": "A neon style",
                "tags": ["style", "neon"],
                "civitai_version_id": 4242,
                "civitai_model_id": 99,
            }

        monkeypatch.setattr(foreign_import, "_civitai_lookup", fake_lookup)
        root = _make_source_tree(tmp_path)

        job = foreign_import.start_import(
            str(root),
            [{"model_type": "loras", "filename": "style/neon.safetensors", "file_hash": ""}],
        )
        await job.task

        row = await model_repo.get_model_by_filename("style/neon.safetensors")
        assert row["base_model"] == "SDXL 1.0"
        assert row["description"] == "A neon style"
        assert row["source_platform"] == "civitai"
        assert row["source_id"] == "4242"
        assert row["civitai_model_id"] == "99"

    async def test_civitai_failure_still_imports(self, tmp_path, monkeypatch, ext_dir):
        import folder_paths
        import httpx

        from py.db import model_repo
        from py.services import foreign_import

        monkeypatch.setattr(folder_paths, "models_dir", str(tmp_path / "local"))

        async def exploding_lookup(sha256):
            raise httpx.ConnectError("offline")

        monkeypatch.setattr(foreign_import, "_civitai_lookup", exploding_lookup)
        root = _make_source_tree(tmp_path)

        job = foreign_import.start_import(
            str(root),
            [{"model_type": "loras", "filename": "style/neon.safetensors", "file_hash": ""}],
        )
        await job.task

        assert job.state == "done"
        assert job.imported == ["style/neon.safetensors"]
        assert await model_repo.get_model_by_filename("style/neon.safetensors") is not None

    async def test_missing_source_is_recorded_and_job_continues(
        self, tmp_path, monkeypatch, ext_dir
    ):
        import folder_paths

        from py.services import foreign_import

        monkeypatch.setattr(folder_paths, "models_dir", str(tmp_path / "local"))
        monkeypatch.setattr(foreign_import, "_civitai_lookup", _no_civitai_match)
        root = _make_source_tree(tmp_path)

        job = foreign_import.start_import(
            str(root),
            [
                {"model_type": "loras", "filename": "ghost.safetensors", "file_hash": ""},
                {"model_type": "checkpoints", "filename": "sd15.safetensors", "file_hash": ""},
            ],
        )
        await job.task

        assert job.state == "done"
        assert job.imported == ["sd15.safetensors"]
        assert job.failed == [{"filename": "ghost.safetensors", "reason": "source_not_found"}]
        assert job.progress == 100.0

    async def test_reuses_the_hash_from_the_scan(self, tmp_path, monkeypatch, ext_dir):
        import folder_paths

        from py.db import model_repo
        from py.services import foreign_import

        monkeypatch.setattr(folder_paths, "models_dir", str(tmp_path / "local"))
        monkeypatch.setattr(foreign_import, "_civitai_lookup", _no_civitai_match)

        def forbidden(path):
            raise AssertionError("compute_file_hash must not run when a hash is supplied")

        monkeypatch.setattr(foreign_import.model_paths, "compute_file_hash", forbidden)
        root = _make_source_tree(tmp_path)

        job = foreign_import.start_import(
            str(root),
            [
                {
                    "model_type": "loras",
                    "filename": "style/neon.safetensors",
                    "file_hash": "cafebabe",
                }
            ],
        )
        await job.task

        assert job.state == "done"
        assert await model_repo.get_file_hash_map() == {"cafebabe": "style/neon.safetensors"}

    async def test_cancel_stops_before_the_next_file(self, tmp_path, monkeypatch, ext_dir):
        import folder_paths

        from py.services import foreign_import

        monkeypatch.setattr(folder_paths, "models_dir", str(tmp_path / "local"))
        monkeypatch.setattr(foreign_import, "_civitai_lookup", _no_civitai_match)
        root = _make_source_tree(tmp_path)

        job = foreign_import.start_import(
            str(root),
            [{"model_type": "loras", "filename": "style/neon.safetensors", "file_hash": ""}],
        )
        foreign_import.cancel_job(job.id)
        await job.task
        assert job.state == "cancelled"
        assert job.imported == []


async def _no_civitai_match(sha256):
    """Stand-in for the CivitAI by-hash lookup: always a miss."""
    return None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `PYTHONSAFEPATH=1 ../../../comfy-env/bin/python -m pytest tests/test_foreign_import.py::TestImportJob -v`
Expected: FAIL — `AttributeError: module 'py.services.foreign_import' has no attribute 'start_import'`

- [ ] **Step 3: Write the implementation**

The tests read the stored row back with `model_repo.get_model_by_filename(filename)`
(`py/db/model_repo.py:233`), which is `SELECT * FROM models` and therefore carries
`base_model`, `description`, `source_platform`, `source_id` and `civitai_model_id`. Tags live
in a separate table and are deliberately not asserted here — `register_model` already has its
own tag coverage.

Append at the end of `py/services/foreign_import.py`:

```python
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
    except Exception:  # noqa: BLE001 - a provider outage must not fail the import
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
    except Exception as exc:  # noqa: BLE001 - surfaced to the client as job.error
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
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `PYTHONSAFEPATH=1 ../../../comfy-env/bin/python -m pytest tests/test_foreign_import.py -v`
Expected: PASS

- [ ] **Step 5: Run the whole backend suite, lint, and commit**

```bash
PYTHONSAFEPATH=1 ../../../comfy-env/bin/python -m pytest
../../../comfy-env/bin/python -m ruff format py tests conftest.py
../../../comfy-env/bin/python -m ruff check py tests conftest.py
git add py/services/foreign_import.py tests/test_foreign_import.py
git commit -m "feat(import): copy, register and enrich the selected models (#154)"
```

---

### Task 7: HTTP routes

**Files:**
- Create: `py/routes/imports.py`
- Modify: `py/routes/__init__.py`
- Create: `tests/test_routes_imports.py`

**Interfaces:**
- Consumes: `foreign_import.validate_root / start_scan / start_import / get_job / cancel_job / job_to_dict / ensure_space / dest_base / InsufficientSpaceError / ForeignRootError`; `_helpers.ok / err / json_route`
- Produces: `add_imports_routes(routes)`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_routes_imports.py`:

```python
"""Integration tests for py/routes/imports.py (F-154)."""

import os

import pytest
from aiohttp import web


@pytest.fixture
async def client(aiohttp_client, ext_dir):
    from py.routes.imports import add_imports_routes

    app = web.Application()
    routes = web.RouteTableDef()
    add_imports_routes(routes)
    app.router.add_routes(routes)
    return await aiohttp_client(app)


@pytest.fixture
def source_root(tmp_path):
    root = tmp_path / "foreign" / "models"
    (root / "loras").mkdir(parents=True)
    (root / "loras" / "neon.safetensors").write_bytes(b"n" * 24)
    return root


@pytest.fixture(autouse=True)
def local_models_dir(tmp_path, monkeypatch):
    import folder_paths

    local = tmp_path / "local" / "models"
    local.mkdir(parents=True)
    monkeypatch.setattr(folder_paths, "models_dir", str(local))
    return local


@pytest.fixture(autouse=True)
def no_civitai(monkeypatch):
    async def miss(sha256):
        return None

    from py.services import foreign_import

    monkeypatch.setattr(foreign_import, "_civitai_lookup", miss)


API = "/tiny-model-manager/api/import"


class TestScanRoute:
    async def test_relative_path_is_400(self, client):
        resp = await client.post(f"{API}/scan", json={"path": "relative/dir"})
        assert resp.status == 400
        assert (await resp.json())["error"] == "path_not_absolute"

    async def test_missing_path_is_400(self, client, tmp_path):
        resp = await client.post(f"{API}/scan", json={"path": str(tmp_path / "nope")})
        assert resp.status == 400
        assert (await resp.json())["error"] == "path_not_found"

    async def test_scan_returns_job_id_and_resolved_root(self, client, source_root):
        resp = await client.post(f"{API}/scan", json={"path": str(source_root.parent)})
        assert resp.status == 200
        body = await resp.json()
        assert body["success"] is True
        assert body["data"]["job_id"]
        assert body["data"]["source_root"] == os.path.realpath(str(source_root))

    async def test_scan_progress_reports_the_file(self, client, source_root):
        from py.services import foreign_import

        start = await client.post(f"{API}/scan", json={"path": str(source_root)})
        job_id = (await start.json())["data"]["job_id"]
        await foreign_import.get_job(job_id).task

        resp = await client.get(f"{API}/scan/{job_id}")
        assert resp.status == 200
        data = (await resp.json())["data"]
        assert data["state"] == "done"
        assert data["files"] == [
            {
                "model_type": "loras",
                "filename": "neon.safetensors",
                "size_bytes": 24,
                "status": "new",
                "file_hash": data["files"][0]["file_hash"],
            }
        ]

    async def test_unknown_scan_job_is_404(self, client):
        resp = await client.get(f"{API}/scan/does-not-exist")
        assert resp.status == 404


class TestImportRoute:
    async def _scanned_root(self, client, source_root):
        from py.services import foreign_import

        start = await client.post(f"{API}/scan", json={"path": str(source_root)})
        job_id = (await start.json())["data"]["job_id"]
        await foreign_import.get_job(job_id).task
        return (await start.json())["data"]["source_root"]

    async def test_full_round_trip_registers_the_model(
        self, client, source_root, local_models_dir
    ):
        from py.db import model_repo
        from py.services import foreign_import

        root = await self._scanned_root(client, source_root)
        resp = await client.post(
            f"{API}/start",
            json={
                "source_root": root,
                "files": [{"model_type": "loras", "filename": "neon.safetensors"}],
            },
        )
        assert resp.status == 200
        job_id = (await resp.json())["data"]["job_id"]
        await foreign_import.get_job(job_id).task

        progress = await client.get(f"{API}/jobs/{job_id}")
        data = (await progress.json())["data"]
        assert data["state"] == "done"
        assert data["imported"] == ["neon.safetensors"]
        assert (local_models_dir / "loras" / "neon.safetensors").exists()
        assert await model_repo.get_registered_filenames() == {"neon.safetensors"}

    async def test_empty_selection_is_400(self, client, source_root):
        root = await self._scanned_root(client, source_root)
        resp = await client.post(f"{API}/start", json={"source_root": root, "files": []})
        assert resp.status == 400
        assert (await resp.json())["error"] == "no_files_selected"

    async def test_unvalidated_root_is_400(self, client, tmp_path):
        resp = await client.post(
            f"{API}/start",
            json={
                "source_root": str(tmp_path / "never-scanned"),
                "files": [{"model_type": "loras", "filename": "x.safetensors"}],
            },
        )
        assert resp.status == 400

    async def test_insufficient_space_is_409(self, client, source_root, monkeypatch):
        import shutil

        root = await self._scanned_root(client, source_root)
        monkeypatch.setattr(
            shutil, "disk_usage", lambda path: shutil._ntuple_diskusage(100, 99, 1)
        )
        resp = await client.post(
            f"{API}/start",
            json={
                "source_root": root,
                "files": [{"model_type": "loras", "filename": "neon.safetensors"}],
            },
        )
        assert resp.status == 409
        body = await resp.json()
        assert body["error"] == "insufficient_space"
        assert body["needed"] == 24
        assert body["available"] == 1

    async def test_unknown_job_is_404(self, client):
        resp = await client.get(f"{API}/jobs/nope")
        assert resp.status == 404

    async def test_cancel_unknown_job_is_404(self, client):
        resp = await client.post(f"{API}/jobs/nope/cancel")
        assert resp.status == 404
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `PYTHONSAFEPATH=1 ../../../comfy-env/bin/python -m pytest tests/test_routes_imports.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'py.routes.imports'`

- [ ] **Step 3: Write the implementation**

Create `py/routes/imports.py`:

```python
"""Routes for importing models from another ComfyUI installation (F-154).

The module is named ``imports`` rather than ``import`` because the latter is a Python
keyword. It owns two job kinds, both defined in ``services/foreign_import``.
"""

import os

from ..services import foreign_import
from ._helpers import err, json_route, ok


def _selection_size(source_root: str, files: list[dict]) -> int:
    """Total bytes of the selected source files, skipping any that vanished."""
    total = 0
    for item in files:
        try:
            path = foreign_import.source_path(
                source_root, item.get("model_type", ""), item.get("filename", "")
            )
        except ValueError:
            continue
        total += os.path.getsize(path)
    return total


def add_imports_routes(routes):

    @routes.post("/tiny-model-manager/api/import/scan")
    @json_route
    async def start_scan(request):
        body = await request.json()
        try:
            root = foreign_import.validate_root(body.get("path", ""))
        except foreign_import.ForeignRootError as exc:
            return err(str(exc), status=400)
        job = foreign_import.start_scan(root)
        return ok({"job_id": job.id, "source_root": root})

    @routes.get("/tiny-model-manager/api/import/scan/{job_id}")
    @json_route
    async def get_scan(request):
        job = foreign_import.get_job(request.match_info["job_id"])
        if job is None or job.kind != "scan":
            return err("job_not_found", status=404)
        return ok(foreign_import.job_to_dict(job))

    @routes.post("/tiny-model-manager/api/import/start")
    @json_route
    async def start_import(request):
        body = await request.json()
        files = body.get("files") or []
        if not files:
            return err("no_files_selected", status=400)

        # Re-validate rather than trusting the client's root: this value came back from a
        # previous response, but it still arrives as request data and it becomes a path.
        try:
            root = foreign_import.validate_root(body.get("source_root", ""))
        except foreign_import.ForeignRootError as exc:
            return err(str(exc), status=400)

        first_type = files[0].get("model_type", "")
        try:
            base = foreign_import.dest_base(first_type)
            foreign_import.ensure_space(base, _selection_size(root, files))
        except ValueError as exc:
            return err(str(exc), status=400)
        except foreign_import.InsufficientSpaceError as exc:
            return err("insufficient_space", status=409, needed=exc.needed, available=exc.available)

        job = foreign_import.start_import(root, files)
        return ok({"job_id": job.id})

    @routes.get("/tiny-model-manager/api/import/jobs/{job_id}")
    @json_route
    async def get_import_job(request):
        job = foreign_import.get_job(request.match_info["job_id"])
        if job is None or job.kind != "import":
            return err("job_not_found", status=404)
        return ok(foreign_import.job_to_dict(job))

    @routes.post("/tiny-model-manager/api/import/jobs/{job_id}/cancel")
    @json_route
    async def cancel_import_job(request):
        job = foreign_import.get_job(request.match_info["job_id"])
        if job is None:
            return err("job_not_found", status=404)
        return ok({"cancelled": foreign_import.cancel_job(job.id)})
```

`err()` takes only `(message, status)`. The 409 above passes extra fields, so extend the
helper in `py/routes/_helpers.py`:

```python
def err(message: str, status: int = 500, **extra) -> web.Response:
    """Build a failure envelope with the given HTTP status.

    ``extra`` carries structured detail a client can act on — the import's
    ``needed``/``available`` byte counts, for example — alongside the error key.
    """
    payload: dict = {"success": False, "error": message}
    payload.update(extra)
    return web.json_response(payload, status=status)
```

- [ ] **Step 4: Register the routes**

In `py/routes/__init__.py`, add the import alongside the others (alphabetical, after `.images`):

```python
from .imports import add_imports_routes
```

and call it inside `register_routes`, after `add_images_routes(routes)`:

```python
    add_imports_routes(routes)
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `PYTHONSAFEPATH=1 ../../../comfy-env/bin/python -m pytest tests/test_routes_imports.py -v`
Expected: PASS

- [ ] **Step 6: Run the whole backend suite, lint, and commit**

```bash
PYTHONSAFEPATH=1 ../../../comfy-env/bin/python -m pytest
../../../comfy-env/bin/python -m ruff format py tests conftest.py
../../../comfy-env/bin/python -m ruff check py tests conftest.py
git add py/routes/imports.py py/routes/__init__.py py/routes/_helpers.py tests/test_routes_imports.py
git commit -m "feat(import): expose scan and import job routes (#154)"
```

---

### Task 8: Frontend service

**Files:**
- Create: `frontend/src/app/services/model-import.ts`
- Create: `frontend/src/app/services/model-import.spec.ts`

**Interfaces:**
- Consumes: the five routes from Task 7
- Produces: `ImportSourceFile`, `ImportJobState`, `ScanStartResult` interfaces; `ModelImportService` with `startScan(path)`, `pollScan(jobId)`, `startImport(sourceRoot, files)`, `pollJob(jobId)`, `cancelJob(jobId)`

- [ ] **Step 1: Write the failing tests**

Create `frontend/src/app/services/model-import.spec.ts`:

```typescript
import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import {
  HttpTestingController,
  provideHttpClientTesting,
} from '@angular/common/http/testing';
import { ModelImportService } from './model-import';

describe('ModelImportService', () => {
  let service: ModelImportService;
  let httpMock: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [ModelImportService, provideHttpClient(), provideHttpClientTesting()],
    });
    service = TestBed.inject(ModelImportService);
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => httpMock.verify());

  it('posts the path to start a scan', () => {
    let result: unknown;
    service.startScan('/mnt/other/models').subscribe((r) => (result = r));

    const req = httpMock.expectOne('/tiny-model-manager/api/import/scan');
    expect(req.request.method).toBe('POST');
    expect(req.request.body).toEqual({ path: '/mnt/other/models' });
    req.flush({ success: true, data: { job_id: 'j1', source_root: '/mnt/other/models' } });

    expect(result).toEqual({ job_id: 'j1', source_root: '/mnt/other/models' });
  });

  it('unwraps the scan job payload', () => {
    let state: unknown;
    service.pollScan('j1').subscribe((s) => (state = s));

    const req = httpMock.expectOne('/tiny-model-manager/api/import/scan/j1');
    expect(req.request.method).toBe('GET');
    req.flush({
      success: true,
      data: { id: 'j1', state: 'done', progress: 100, files: [], imported: [], failed: [] },
    });

    expect((state as { state: string }).state).toBe('done');
  });

  it('posts the source root and selection to start an import', () => {
    const files = [{ model_type: 'loras', filename: 'a.safetensors', file_hash: 'ff' }];
    service.startImport('/mnt/other/models', files).subscribe();

    const req = httpMock.expectOne('/tiny-model-manager/api/import/start');
    expect(req.request.body).toEqual({ source_root: '/mnt/other/models', files });
    req.flush({ success: true, data: { job_id: 'j2' } });
  });

  it('polls an import job', () => {
    service.pollJob('j2').subscribe();
    const req = httpMock.expectOne('/tiny-model-manager/api/import/jobs/j2');
    expect(req.request.method).toBe('GET');
    req.flush({ success: true, data: { id: 'j2', state: 'running', progress: 50 } });
  });

  it('cancels a job', () => {
    service.cancelJob('j2').subscribe();
    const req = httpMock.expectOne('/tiny-model-manager/api/import/jobs/j2/cancel');
    expect(req.request.method).toBe('POST');
    req.flush({ success: true, data: { cancelled: true } });
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run from `frontend/`: `npx ng test --watch=false -- model-import`
Expected: FAIL — cannot resolve `./model-import`

- [ ] **Step 3: Write the implementation**

Create `frontend/src/app/services/model-import.ts`:

```typescript
import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { map } from 'rxjs/operators';

/**
 * Importing models from another ComfyUI installation's models folder (F-154).
 *
 * Both phases are backend jobs: a scan hashes the foreign folder against the local
 * library, an import copies the selected files in. The caller polls; this service only
 * starts jobs and reads their state.
 */

/** One model file found in the foreign folder. */
export interface ImportSourceFile {
  model_type: string;
  filename: string;
  size_bytes: number;
  /** pending | new | installed | unreadable */
  status: string;
  file_hash: string;
}

/** A file the user picked for import. */
export interface ImportSelection {
  model_type: string;
  filename: string;
  file_hash: string;
}

export interface ImportJobState {
  id: string;
  kind: string;
  source_root: string;
  /** running | done | error | cancelled */
  state: string;
  progress: number;
  error: string;
  files: ImportSourceFile[];
  imported: string[];
  skipped: string[];
  failed: { filename: string; reason: string }[];
}

export interface ScanStartResult {
  job_id: string;
  source_root: string;
}

const API = '/tiny-model-manager/api/import';

@Injectable({ providedIn: 'root' })
export class ModelImportService {
  private readonly http = inject(HttpClient);

  startScan(path: string): Observable<ScanStartResult> {
    return this.http
      .post<{ data: ScanStartResult }>(`${API}/scan`, { path })
      .pipe(map((r) => r.data));
  }

  pollScan(jobId: string): Observable<ImportJobState> {
    return this.http
      .get<{ data: ImportJobState }>(`${API}/scan/${jobId}`)
      .pipe(map((r) => r.data));
  }

  startImport(sourceRoot: string, files: ImportSelection[]): Observable<{ job_id: string }> {
    return this.http
      .post<{ data: { job_id: string } }>(`${API}/start`, { source_root: sourceRoot, files })
      .pipe(map((r) => r.data));
  }

  pollJob(jobId: string): Observable<ImportJobState> {
    return this.http
      .get<{ data: ImportJobState }>(`${API}/jobs/${jobId}`)
      .pipe(map((r) => r.data));
  }

  cancelJob(jobId: string): Observable<{ cancelled: boolean }> {
    return this.http
      .post<{ data: { cancelled: boolean } }>(`${API}/jobs/${jobId}/cancel`, {})
      .pipe(map((r) => r.data));
  }
}
```

- [ ] **Step 4: Format, then run the tests to verify they pass**

```bash
npx prettier --write src/app/services/model-import.ts src/app/services/model-import.spec.ts
npx ng test --watch=false -- model-import
```
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/services/model-import.ts frontend/src/app/services/model-import.spec.ts
git commit -m "feat(frontend): add the model-import service (#154)"
```

---

### Task 9: The import page

**Files:**
- Create: `frontend/src/app/pages/model-import/model-import.ts`
- Create: `frontend/src/app/pages/model-import/model-import.html`
- Create: `frontend/src/app/pages/model-import/model-import.css`
- Create: `frontend/src/app/pages/model-import/model-import.spec.ts`
- Modify: `frontend/src/app/services/settings.ts`
- Modify: `frontend/public/i18n/en.json`

**Interfaces:**
- Consumes: `ModelImportService` (Task 8), `SettingsService`, `formatSize` from `../../utils/format`
- Produces: exported class `ModelImport`

- [ ] **Step 1: Add the translation keys**

Add this block to `frontend/public/i18n/en.json`, as a sibling of the existing top-level
sections (keep the file's alphabetical ordering if it has one):

```json
  "import": {
    "title": "Import from another folder",
    "intro": "Paste the path to another ComfyUI installation's models folder. Files already in your library are detected by content, not by name.",
    "path_label": "Source folder",
    "path_placeholder": "D:\\OtherComfyUI\\models",
    "scan": "Scan",
    "scanning": "Hashing files…",
    "cancel": "Cancel",
    "back": "Back to models",
    "import_selected": "Import selected",
    "importing": "Copying files…",
    "select_all": "Select all",
    "status_new": "New",
    "status_installed": "Already installed",
    "status_unreadable": "Unreadable",
    "no_files": "No model files found in that folder.",
    "summary": "Imported {{imported}}, failed {{failed}}.",
    "errors": {
      "path_not_absolute": "Enter an absolute path, for example D:\\OtherComfyUI\\models.",
      "path_not_found": "That folder does not exist.",
      "path_is_local_root": "That is this installation's own models folder.",
      "no_files_selected": "Select at least one model to import.",
      "insufficient_space": "Not enough free disk space for the selected models.",
      "generic": "The import failed. Check the ComfyUI console for details."
    }
  },
```

Also add a key for the Models-page button, inside the existing `"models"` section:

```json
    "import_from_folder": "Import from another folder",
```

- [ ] **Step 2: Write the failing tests**

Create `frontend/src/app/pages/model-import/model-import.spec.ts`:

```typescript
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { of, throwError } from 'rxjs';
import { vi } from 'vitest';
import { provideTranslateServiceForTests } from '../../../test-helpers/translate-testing';
import { ModelImport } from './model-import';
import { ModelImportService, ImportJobState } from '../../services/model-import';
import { SettingsService } from '../../services/settings';

function jobState(over: Partial<ImportJobState> = {}): ImportJobState {
  return {
    id: 'j1',
    kind: 'scan',
    source_root: '/src/models',
    state: 'done',
    progress: 100,
    error: '',
    files: [],
    imported: [],
    skipped: [],
    failed: [],
    ...over,
  };
}

describe('ModelImport', () => {
  let fixture: ComponentFixture<ModelImport>;
  let component: ModelImport;
  let importService: {
    startScan: ReturnType<typeof vi.fn>;
    pollScan: ReturnType<typeof vi.fn>;
    startImport: ReturnType<typeof vi.fn>;
    pollJob: ReturnType<typeof vi.fn>;
    cancelJob: ReturnType<typeof vi.fn>;
  };

  beforeEach(async () => {
    importService = {
      startScan: vi.fn().mockReturnValue(of({ job_id: 'j1', source_root: '/src/models' })),
      pollScan: vi.fn().mockReturnValue(of(jobState())),
      startImport: vi.fn().mockReturnValue(of({ job_id: 'j2' })),
      pollJob: vi.fn().mockReturnValue(of(jobState({ kind: 'import' }))),
      cancelJob: vi.fn().mockReturnValue(of({ cancelled: true })),
    };

    await TestBed.configureTestingModule({
      imports: [ModelImport],
      providers: [
        { provide: ModelImportService, useValue: importService },
        {
          provide: SettingsService,
          useValue: {
            getSettings: vi.fn().mockReturnValue(of({ import_source_root: '/remembered' })),
            updateSettings: vi.fn().mockReturnValue(of(undefined)),
          },
        },
        provideTranslateServiceForTests(),
      ],
    }).compileComponents();

    fixture = TestBed.createComponent(ModelImport);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('prefills the remembered source path', () => {
    expect(component.sourcePath()).toBe('/remembered');
  });

  it('starts a scan and stores the resolved root', async () => {
    component.sourcePath.set('/src');
    component.scan();
    await Promise.resolve();
    expect(importService.startScan).toHaveBeenCalledWith('/src');
    expect(component.sourceRoot()).toBe('/src/models');
  });

  it('surfaces a backend error key', async () => {
    importService.startScan.mockReturnValue(
      throwError(() => ({ error: { error: 'path_not_found' } })),
    );
    component.sourcePath.set('/gone');
    component.scan();
    await Promise.resolve();
    expect(component.errorKey()).toBe('import.errors.path_not_found');
  });

  it('falls back to a generic error key for an unknown failure', async () => {
    importService.startScan.mockReturnValue(throwError(() => ({ status: 500 })));
    component.scan();
    await Promise.resolve();
    expect(component.errorKey()).toBe('import.errors.generic');
  });

  it('groups scanned files by model type', () => {
    component.applyScanState(
      jobState({
        files: [
          { model_type: 'loras', filename: 'a', size_bytes: 1, status: 'new', file_hash: 'a' },
          { model_type: 'loras', filename: 'b', size_bytes: 2, status: 'new', file_hash: 'b' },
          {
            model_type: 'checkpoints',
            filename: 'c',
            size_bytes: 3,
            status: 'installed',
            file_hash: 'c',
          },
        ],
      }),
    );
    expect(component.groups().map((g) => g.modelType)).toEqual(['checkpoints', 'loras']);
    expect(component.groups()[1].files.length).toBe(2);
  });

  it('only counts selectable new files in select-all', () => {
    component.applyScanState(
      jobState({
        files: [
          { model_type: 'loras', filename: 'a', size_bytes: 1, status: 'new', file_hash: 'a' },
          {
            model_type: 'loras',
            filename: 'b',
            size_bytes: 2,
            status: 'installed',
            file_hash: 'b',
          },
        ],
      }),
    );
    component.toggleGroup('loras', true);
    expect(component.selectedCount()).toBe(1);
  });

  it('sends only the selected files to the import', async () => {
    component.applyScanState(
      jobState({
        files: [
          { model_type: 'loras', filename: 'a', size_bytes: 1, status: 'new', file_hash: 'h1' },
          { model_type: 'loras', filename: 'b', size_bytes: 2, status: 'new', file_hash: 'h2' },
        ],
      }),
    );
    component.sourceRoot.set('/src/models');
    component.toggleFile('loras', 'a', true);
    component.startImport();
    await Promise.resolve();
    expect(importService.startImport).toHaveBeenCalledWith('/src/models', [
      { model_type: 'loras', filename: 'a', file_hash: 'h1' },
    ]);
  });

  it('does not start an import with nothing selected', () => {
    component.startImport();
    expect(importService.startImport).not.toHaveBeenCalled();
    expect(component.errorKey()).toBe('import.errors.no_files_selected');
  });
});
```

- [ ] **Step 3: Run the tests to verify they fail**

Run from `frontend/`: `npx ng test --watch=false -- model-import`
Expected: FAIL — cannot resolve `./model-import`

- [ ] **Step 4: Extend the settings interface**

The component remembers the source path through `SettingsService`, whose payload is typed.
Add the field to `TmmSettings` in `frontend/src/app/services/settings.ts`, after
`missing_models_integration`:

```typescript
  /** Last foreign models root used by the import page (F-154); absent until first used. */
  import_source_root?: string;
```

The backend needs no change: `GET/PUT /api/settings` round-trips whatever keys the settings
file holds, so a new key needs no registration.

- [ ] **Step 5: Write the component**

Create `frontend/src/app/pages/model-import/model-import.ts`:

```typescript
import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  OnInit,
  computed,
  inject,
  signal,
} from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { CommonModule } from '@angular/common';
import { RouterLink } from '@angular/router';
import { EMPTY, interval, of } from 'rxjs';
import { catchError, switchMap, takeWhile } from 'rxjs/operators';
import { TranslatePipe } from '@ngx-translate/core';
import {
  ImportJobState,
  ImportSourceFile,
  ModelImportService,
} from '../../services/model-import';
import { SettingsService } from '../../services/settings';
import { formatSize } from '../../utils/format';

/** Scanned files of one model type, ready to render as a section. */
interface TypeGroup {
  modelType: string;
  files: ImportSourceFile[];
}

const POLL_MS = 1000;

/** Backend error keys the page has its own copy for; anything else is generic. */
const KNOWN_ERRORS = new Set([
  'path_not_absolute',
  'path_not_found',
  'path_is_local_root',
  'no_files_selected',
  'insufficient_space',
]);

@Component({
  selector: 'app-model-import',
  standalone: true,
  imports: [CommonModule, RouterLink, TranslatePipe],
  templateUrl: './model-import.html',
  styleUrl: './model-import.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ModelImport implements OnInit {
  private readonly importService = inject(ModelImportService);
  private readonly settings = inject(SettingsService);
  private readonly destroyRef = inject(DestroyRef);

  readonly sourcePath = signal('');
  readonly sourceRoot = signal('');
  readonly errorKey = signal('');
  readonly scanning = signal(false);
  readonly importing = signal(false);
  readonly progress = signal(0);
  readonly scanned = signal(false);
  readonly files = signal<ImportSourceFile[]>([]);
  readonly summary = signal<{ imported: number; failed: number } | null>(null);

  /** Keys are `${model_type}\u0000${filename}` — a NUL cannot occur in either half. */
  private readonly selection = signal<Set<string>>(new Set());

  readonly groups = computed<TypeGroup[]>(() => {
    const byType = new Map<string, ImportSourceFile[]>();
    for (const file of this.files()) {
      const bucket = byType.get(file.model_type) ?? [];
      bucket.push(file);
      byType.set(file.model_type, bucket);
    }
    return [...byType.entries()]
      .sort((a, b) => a[0].localeCompare(b[0]))
      .map(([modelType, files]) => ({ modelType, files }));
  });

  readonly selectedCount = computed(() => this.selection().size);

  readonly busy = computed(() => this.scanning() || this.importing());

  ngOnInit(): void {
    this.settings
      .getSettings()
      .pipe(
        catchError(() => EMPTY),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe((s) => {
        if (s.import_source_root) {
          this.sourcePath.set(s.import_source_root);
        }
      });
  }

  formatSize = formatSize;

  key(modelType: string, filename: string): string {
    return `${modelType}\u0000${filename}`;
  }

  isSelected(modelType: string, filename: string): boolean {
    return this.selection().has(this.key(modelType, filename));
  }

  toggleFile(modelType: string, filename: string, checked: boolean): void {
    const next = new Set(this.selection());
    const entry = this.key(modelType, filename);
    if (checked) {
      next.add(entry);
    } else {
      next.delete(entry);
    }
    this.selection.set(next);
  }

  /** Select or clear every *importable* file of a type — `installed` rows are not offered. */
  toggleGroup(modelType: string, checked: boolean): void {
    const next = new Set(this.selection());
    for (const file of this.files()) {
      if (file.model_type !== modelType || file.status !== 'new') {
        continue;
      }
      const entry = this.key(modelType, file.filename);
      if (checked) {
        next.add(entry);
      } else {
        next.delete(entry);
      }
    }
    this.selection.set(next);
  }

  scan(): void {
    this.errorKey.set('');
    this.summary.set(null);
    this.files.set([]);
    this.selection.set(new Set());
    this.scanned.set(false);
    this.scanning.set(true);
    this.progress.set(0);

    this.importService
      .startScan(this.sourcePath())
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (result) => {
          this.sourceRoot.set(result.source_root);
          this.rememberPath(result.source_root);
          this.pollScan(result.job_id);
        },
        error: (err) => {
          this.scanning.set(false);
          this.errorKey.set(this.translateError(err));
        },
      });
  }

  startImport(): void {
    const selected = this.selectedSelections();
    if (!selected.length) {
      this.errorKey.set('import.errors.no_files_selected');
      return;
    }
    this.errorKey.set('');
    this.importing.set(true);
    this.progress.set(0);

    this.importService
      .startImport(this.sourceRoot(), selected)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (result) => this.pollImport(result.job_id),
        error: (err) => {
          this.importing.set(false);
          this.errorKey.set(this.translateError(err));
        },
      });
  }

  /** Exposed for tests and for the poll callbacks; renders one scan snapshot. */
  applyScanState(state: ImportJobState): void {
    this.files.set(state.files ?? []);
    this.progress.set(state.progress ?? 0);
    if (state.state !== 'running') {
      this.scanning.set(false);
      this.scanned.set(true);
    }
  }

  private pollScan(jobId: string): void {
    interval(POLL_MS)
      .pipe(
        switchMap(() => this.importService.pollScan(jobId).pipe(catchError(() => of(null)))),
        takeWhile((state) => state === null || state.state === 'running', true),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe((state) => {
        if (state) {
          this.applyScanState(state);
        }
      });
  }

  private pollImport(jobId: string): void {
    interval(POLL_MS)
      .pipe(
        switchMap(() => this.importService.pollJob(jobId).pipe(catchError(() => of(null)))),
        takeWhile((state) => state === null || state.state === 'running', true),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe((state) => {
        if (!state) {
          return;
        }
        this.progress.set(state.progress ?? 0);
        if (state.state !== 'running') {
          this.importing.set(false);
          this.summary.set({
            imported: state.imported?.length ?? 0,
            failed: state.failed?.length ?? 0,
          });
        }
      });
  }

  private selectedSelections() {
    const chosen = this.selection();
    return this.files()
      .filter((f) => chosen.has(this.key(f.model_type, f.filename)))
      .map((f) => ({
        model_type: f.model_type,
        filename: f.filename,
        file_hash: f.file_hash,
      }));
  }

  private rememberPath(root: string): void {
    this.settings
      .updateSettings({ import_source_root: root })
      .pipe(
        catchError(() => EMPTY),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe();
  }

  private translateError(err: unknown): string {
    const key = (err as { error?: { error?: string } })?.error?.error ?? '';
    return KNOWN_ERRORS.has(key) ? `import.errors.${key}` : 'import.errors.generic';
  }
}
```

- [ ] **Step 6: Write the template**

Create `frontend/src/app/pages/model-import/model-import.html`:

```html
<div class="page">
  <div class="page-head">
    <div>
      <h1 class="page-title">{{ 'import.title' | translate }}</h1>
      <p class="page-subtitle">{{ 'import.intro' | translate }}</p>
    </div>
    <div class="page-head-actions">
      <a class="btn-secondary btn-small" routerLink="/models">
        {{ 'import.back' | translate }}
      </a>
    </div>
  </div>

  <div class="import-source">
    <label class="import-label" for="import-path">{{ 'import.path_label' | translate }}</label>
    <input
      id="import-path"
      class="import-path"
      type="text"
      [value]="sourcePath()"
      (input)="sourcePath.set($any($event.target).value)"
      [placeholder]="'import.path_placeholder' | translate"
      [disabled]="busy()"
    />
    <button class="btn-primary btn-small" (click)="scan()" [disabled]="busy()">
      {{ 'import.scan' | translate }}
    </button>
  </div>

  @if (errorKey()) {
    <p class="import-error">{{ errorKey() | translate }}</p>
  }

  @if (busy()) {
    <div class="import-progress">
      <span>{{ (scanning() ? 'import.scanning' : 'import.importing') | translate }}</span>
      <progress [value]="progress()" max="100"></progress>
      <span>{{ progress() | number: '1.0-0' }}%</span>
    </div>
  }

  @if (summary(); as done) {
    <p class="import-summary">
      {{ 'import.summary' | translate: { imported: done.imported, failed: done.failed } }}
    </p>
  }

  @if (scanned() && groups().length === 0) {
    <p class="import-empty">{{ 'import.no_files' | translate }}</p>
  }

  @for (group of groups(); track group.modelType) {
    <section class="import-group">
      <header class="import-group-head">
        <h2>{{ group.modelType }}</h2>
        <button
          class="btn-secondary btn-small"
          (click)="toggleGroup(group.modelType, true)"
          [disabled]="busy()"
        >
          {{ 'import.select_all' | translate }}
        </button>
      </header>
      <ul class="import-list">
        @for (file of group.files; track file.filename) {
          <li class="import-row" [class.is-installed]="file.status !== 'new'">
            <label>
              <input
                type="checkbox"
                [checked]="isSelected(group.modelType, file.filename)"
                (change)="
                  toggleFile(group.modelType, file.filename, $any($event.target).checked)
                "
                [disabled]="file.status !== 'new' || busy()"
              />
              <span class="import-name">{{ file.filename }}</span>
            </label>
            <span class="import-size">{{ formatSize(file.size_bytes) }}</span>
            <span class="import-status">
              @switch (file.status) {
                @case ('new') {
                  {{ 'import.status_new' | translate }}
                }
                @case ('installed') {
                  {{ 'import.status_installed' | translate }}
                }
                @case ('unreadable') {
                  {{ 'import.status_unreadable' | translate }}
                }
              }
            </span>
          </li>
        }
      </ul>
    </section>
  }

  @if (scanned() && groups().length > 0) {
    <div class="import-actions">
      <button
        class="btn-primary"
        (click)="startImport()"
        [disabled]="busy() || selectedCount() === 0"
      >
        {{ 'import.import_selected' | translate }} ({{ selectedCount() }})
      </button>
    </div>
  }
</div>
```

- [ ] **Step 7: Write the stylesheet**

Create `frontend/src/app/pages/model-import/model-import.css`:

```css
.import-source {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  margin-bottom: 1rem;
}

.import-path {
  flex: 1;
  min-width: 0;
  padding: 0.45rem 0.6rem;
}

.import-error {
  color: var(--tmm-danger, #d9534f);
}

.import-progress {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  margin-bottom: 1rem;
}

.import-progress progress {
  flex: 1;
}

.import-group {
  margin-bottom: 1.5rem;
}

.import-group-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
}

.import-list {
  list-style: none;
  margin: 0;
  padding: 0;
  /* An explicit max-height, not `flex: 1; min-height: 0` — the latter collapses to zero
     inside an auto-height column and would hide every row. */
  max-height: 22rem;
  overflow-y: auto;
}

.import-row {
  display: grid;
  grid-template-columns: 1fr auto auto;
  align-items: center;
  gap: 0.75rem;
  padding: 0.3rem 0;
}

.import-row.is-installed {
  opacity: 0.55;
}

.import-name {
  word-break: break-all;
}

.import-actions {
  margin-top: 1rem;
}
```

- [ ] **Step 8: Format and run the tests**

```bash
npx prettier --write src/app/pages/model-import/model-import.ts src/app/pages/model-import/model-import.html src/app/pages/model-import/model-import.css src/app/pages/model-import/model-import.spec.ts
npx ng test --watch=false -- model-import
```
Expected: PASS (9 tests)

- [ ] **Step 9: Commit**

```bash
git add frontend/src/app/services/settings.ts frontend/src/app/pages/model-import frontend/public/i18n/en.json
git commit -m "feat(frontend): add the model import page (#154)"
```

---

### Task 10: Wire the route and the entry point

**Files:**
- Modify: `frontend/src/app/app.routes.ts`
- Modify: `frontend/src/app/pages/models/models.html`
- Modify: `frontend/src/app/pages/models/models.ts` (only if `RouterLink` is not already imported)

**Interfaces:**
- Consumes: `ModelImport` (Task 9)
- Produces: the `models/import` route

- [ ] **Step 1: Add the route before `models/:platform`**

In `frontend/src/app/app.routes.ts`, insert this entry **directly after** the `models` entry
and **before** the `models/:platform` entry:

```typescript
  // MUST precede `models/:platform`: catalog detail and model detail are told apart purely
  // by segment count, so this two-segment literal would otherwise resolve to catalog detail
  // with platform === 'import'.
  {
    path: 'models/import',
    loadComponent: () => import('./pages/model-import/model-import').then((m) => m.ModelImport),
  },
```

- [ ] **Step 2: Add the entry-point button**

In `frontend/src/app/pages/models/models.html`, inside the existing
`<div class="page-head-actions">`, add as the last child:

```html
      <a class="btn-secondary btn-small" routerLink="/models/import">
        {{ 'models.import_from_folder' | translate }}
      </a>
```

`models.ts` already imports `RouterLink` — confirm with
`grep -n "RouterLink" src/app/pages/models/models.ts` and add it to the component's `imports`
array only if it is missing.

- [ ] **Step 3: Verify the route resolves rather than falling through to catalog detail**

Add this test to `frontend/src/app/pages/model-import/model-import.spec.ts`:

```typescript
describe('models/import routing', () => {
  it('is declared before the catalog-detail wildcard', async () => {
    const { routes } = await import('../../app.routes');
    const importIndex = routes.findIndex((r) => r.path === 'models/import');
    const platformIndex = routes.findIndex((r) => r.path === 'models/:platform');
    expect(importIndex).toBeGreaterThanOrEqual(0);
    expect(importIndex).toBeLessThan(platformIndex);
  });
});
```

- [ ] **Step 4: Format and run the frontend checks**

```bash
npx prettier --write src/app/app.routes.ts src/app/pages/models/models.html src/app/pages/model-import/model-import.spec.ts
npx ng test --watch=false
npx ng lint
npm run format:check
```
Expected: all pass, 0 ESLint errors

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/app.routes.ts frontend/src/app/pages/models/models.html frontend/src/app/pages/models/models.ts frontend/src/app/pages/model-import/model-import.spec.ts
git commit -m "feat(frontend): route models/import and link it from the Models page (#154)"
```

---

### Task 11: Full verification, bundle, docs and memory

**Files:**
- Modify: `web/**` (build output)
- Modify: `README.md`
- Modify: `.serena/memories/core.md` (via `mcp__serena__write_memory`)

- [ ] **Step 1: Run every backend check**

From the project root:

```bash
PYTHONSAFEPATH=1 ../../../comfy-env/bin/python -m pytest
../../../comfy-env/bin/python -m ruff check py tests conftest.py
../../../comfy-env/bin/python -m ruff format --check py tests conftest.py
```
Expected: all pass, zero failures. Backend coverage must stay ≥ 88 % lines.

- [ ] **Step 2: Run every frontend check**

From `frontend/`:

```bash
npx ng test --watch=false
npx ng lint
npm run format:check
```
Expected: all pass. Frontend coverage must stay ≥ 74 % lines / ≥ 62 % functions / ≥ 74 % branches.

- [ ] **Step 3: Build the bundle from the main checkout**

From `frontend/` in the **main checkout** (not a worktree — ComfyUI serves the main checkout's
`web/`):

```bash
npx ng build
```
Expected: build succeeds.

- [ ] **Step 4: Update the README feature checklist**

Find the features checklist in `README.md` and add (or tick, if the issue is already listed):

```markdown
- [x] Import selected models from another ComfyUI installation's model folder
```

- [ ] **Step 5: Update the Serena memory**

Use `mcp__serena__write_memory` on `core` to add a section after the "Card-image upload (F-159)"
block. Keep the existing content intact and add:

```markdown
## Foreign folder import (F-154)

Copies models out of another ComfyUI installation's models folder into the local library.

- `py/services/foreign_import.py` owns both phases. Job state is an in-memory `_jobs` dict of
  `ImportJob`, mirroring `downloader._tasks`; `start_scan` / `start_import` return the job and
  its `.task` so tests can await it — **never drain `background._background_tasks`**.
- **Copy only, by design.** Move breaks the source installation irreversibly and links need
  admin rights on Windows or a shared filesystem. Do not add them without a new decision.
- **The type comes from the immediate subfolder name**; a file sitting directly in the models
  root has no type and is skipped rather than guessed at. `validate_root` appends a `models`
  subdirectory when it finds one, so pasting a ComfyUI root works too, and it rejects a path
  that is, contains, or sits inside a local model directory — scanning a parent of the local
  library would copy files onto themselves.
- **Duplicates are decided by SHA-256, never by filename**: a truncated local copy must not
  hide a good source file. The local side starts from `model_repo.get_file_hash_map()` and
  `model_repo.set_file_hash()` caches anything newly hashed, so a second scan is nearly free.
  An *unregistered* local file has no row to cache into and is re-hashed each time.
- The scan publishes its file list **before** hashing starts and fills in per-file status as it
  goes, so a large library is browsable within a second.
- **The same hash is reused for enrichment** — `_civitai_lookup` (the monkeypatch seam) is
  CivitAI-only because HuggingFace exposes no by-hash endpoint. A provider outage leaves the
  model registered without metadata; it never fails the import.
- Copies land on a `.tmm-part` name and are `os.replace`d into position, so an interrupted copy
  never leaves a truncated file that looks like a working model. Collisions get a `_1`/`_2`
  suffix. Destinations always go through `contained_path` / `is_safe_segment`.
- `py/routes/imports.py` — named `imports` because `import` is a keyword. It **re-validates the
  client's `source_root`** on the import call: the value came from a previous response but it
  still arrives as request data and it becomes a filesystem path.
- `_helpers.err()` now takes `**extra`, used for the 409's `needed`/`available` byte counts.
- Frontend: `pages/model-import/` at **`models/import`, declared before `models/:platform`** —
  two segments, so the catalog-detail route would otherwise swallow it. The last-used path is
  remembered in the `import_source_root` setting.
```

- [ ] **Step 6: Commit the bundle, README and memory together**

```bash
git add web README.md .serena/memories/core.md
git commit -m "chore: rebuild bundle and record the foreign folder import (#154)"
```

- [ ] **Step 7: Present the commits to the user**

Run `git log --oneline main..HEAD` and show the result. **Do not push and do not open a pull
request** — CLAUDE.md requires explicit user approval for both.

---

## Notes for the implementer

- Issue #154's acceptance criteria map to tasks as follows: "select/enter a path" → Task 9;
  "folder is scanned and detected models listed with type and size" → Tasks 2, 4, 9;
  "select individual models" → Task 9; "imported models are copied and indexed" → Tasks 5, 6;
  "metadata enrichment runs where possible" → Task 6.
- The AC's "(or moved/linked — to be decided during planning)" was decided: **copy only**.
- Signatures the plan depends on were verified while writing it: `background.spawn` returns the
  `asyncio.Task`, the model row accessor is `model_repo.get_model_by_filename`, `SettingsService`
  exposes `getSettings()` / `updateSettings()`, and `formatSize(bytes: number): string` lives in
  `frontend/src/app/utils/format.ts`. Component specs use `provideTranslateServiceForTests()` from
  `src/test-helpers/translate-testing`; `describe`/`it`/`expect` are Vitest globals and only `vi`
  is imported.
