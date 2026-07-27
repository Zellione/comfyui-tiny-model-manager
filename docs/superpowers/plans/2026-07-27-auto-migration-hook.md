# Implementation Plan — F-92: Auto-migration Hook in Existing Fetch Paths

**Spec:** `docs/superpowers/specs/2026-07-27-auto-migration-hook-design.md`
**Issue:** #92 · **Branch:** `f-92-auto-migration-hook`

Backend-only. No DB migration, no new routes, no frontend changes.

---

## Step 1 — Extract `py/services/disk_scanner.py`

Move out of `py/routes/models.py`, unchanged in behaviour:

- `_BROAD_EXTENSIONS`, `_SKIP_TYPES`
- `_scan_dir` → `scan_dir`
- `_scan_registered_types` → `_scan_registered_types`
- `_scan_root_subdirs` → `_scan_root_subdirs`

Add the single entry point that reproduces exactly what `_get_unregistered_files` did
inline:

```python
def scan_all() -> dict[str, list[dict]]:
    result: dict = {}
    scanned: set[str] = set()
    _scan_registered_types(result, scanned)
    _scan_root_subdirs(result, scanned, folder_paths.models_dir, skip_types=True)
    _scan_root_subdirs(result, scanned, os.path.join(cfg.data_dir(), "models"), skip_types=False)
    return result
```

In `py/routes/models.py`:

- drop the moved symbols and now-unused imports
- `_get_unregistered_files` becomes: `scan_all()` → filter by
  `get_registered_filenames()` → `ok(...)`
- keep `_BROAD_EXTENSIONS` re-exported only if something else in the module still uses it
  (check `_scan_registered_types` was the only consumer)

`catalog.py` keeps its own copies — out of scope.

**Verify:** existing `tests/test_routes_models.py` unregistered-files tests still pass
untouched. If any test monkeypatches a moved symbol by module path, update the target.

---

## Step 2 — Expose `sha256` on HuggingFace file listings

`py/services/providers/huggingface_provider.py` → `get_model_files`, inside the result
dict append:

```python
"sha256": (f.get("lfs") or {}).get("oid", ""),
```

Additive only. `_model_files_for_storage` builds its own dict and is unaffected; the
frontend ignores unknown keys.

**Verify:** new unit test asserts the oid is surfaced and that a sibling with no `lfs`
block yields `""` rather than raising.

---

## Step 3 — `py/services/auto_migrator.py`

### Data shape

```python
@dataclass
class RemoteFile:
    filename: str
    sha256: str
    size_bytes: int = 0
    base_model: str = ""
    source_platform: str = ""
    source_id: str = ""
    civitai_model_id: str = ""
```

### Extractors

`from_civitai_versions(model_data: dict) -> list[RemoteFile]`

- iterate `model_data.get("versions", [])`
- per version: `vid = version.get("id")`, `base_model = version.get("baseModel", "")`
- iterate `version.get("files", [])`, skip `f.get("type") != "Model"`
- `sha = (f.get("hashes") or {}).get("SHA256", "")` — skip when falsy
- `size_bytes = int(f.get("sizeKB", 0) * 1024)`
- `source_platform="civitai"`, `source_id=str(vid)`,
  `civitai_model_id=str(version.get("modelId") or "")`

Note `modelId` is present on each version object in the `/models/{id}` response.

`from_hf_files(repo_id: str, files: list[dict]) -> list[RemoteFile]`

- skip entries with empty `sha256`
- `filename=f["filename"]`, `size_bytes=f.get("size", 0)`,
  `source_platform="huggingface"`, `source_id=repo_id`

### Hash cache

```python
_HASH_CACHE_MAX = 256
_hash_cache: dict[tuple[str, int, float], str] = {}

async def _hash_file(path, size, mtime) -> str   # to_thread(compute_file_hash), FIFO evict
```

### `async migrate(remote_files) -> list[str]`

```
if not remote_files: return []
by_name = {}  # lowercase basename -> [RemoteFile]
scanned = disk_scanner.scan_all()
registered = await model_repo.get_registered_filenames()
migrated = []
for model_type, entries in scanned.items():
    for entry in entries:
        if entry["filename"] in registered: continue
        remotes = by_name.get(basename(entry["filename"]).lower())
        if not remotes: continue
        sized = [r for r in remotes if _size_matches(r.size_bytes, entry["size_bytes"])]
        if not sized: continue
        digest = await _hash_file(...)          # OSError -> skip
        match = next((r for r in sized if r.sha256.lower() == digest), None)
        if not match: continue
        register + notify + log                 # wrapped
        registered.add(entry["filename"])
        migrated.append(entry["filename"])
return migrated
```

`_size_matches(remote, local)` → `True` when either is 0 (unknown), else
`abs(remote - local) <= 65536`.

Registration:

```python
await model_repo.register_model(
    filename=entry["filename"], model_type=model_type,
    base_model=match.base_model, tags=[], description="",
    file_hash=digest, source_platform=match.source_platform,
    source_id=match.source_id, civitai_model_id=match.civitai_model_id,
)
```

Trigger words go in via `model_repo.set_trigger_words(model_id, ...)`.

**No `fetch_and_store` enrichment.** Calling it from here re-enters `_fetch_repo_files`
and schedules another migration pass (a cycle), and with `organize_into_subfolders`
enabled it relocates the file and upserts under the new path, orphaning the row written
above. The stored `source_platform`/`source_id` mean "Re-fetch metadata" can fill in the
rest on demand.

### `schedule(remote_files) -> asyncio.Task | None`

Returns `None` on empty, otherwise `background.spawn(_run(remote_files))` where `_run`
wraps `migrate` in try/except so a failure never escapes into the event loop. Returning
the task lets tests await their own work instead of draining
`background._background_tasks`, which also holds the downloader's `while True` worker.

---

## Step 4 — Hook points

`py/routes/download.py`:

```python
# civitai_versions, after `versions = await civitai.get_model_versions(model_id)`
auto_migrator.schedule(auto_migrator.from_civitai_versions(versions))

# hf_files, after `files = await huggingface.get_model_files(repo_id)`
auto_migrator.schedule(auto_migrator.from_hf_files(repo_id, files))
```

`py/services/metadata_fetcher.py`:

- `_fetch_repo_files` — schedule from whichever branch produced data. CivitAI has two
  branches (`get_model_versions` when `civitai_model_id` is known, else
  `get_version_files`); `get_version_files` does not currently return hashes, so schedule
  only from the `get_model_versions` branch and from the HF branch (which now carries
  `sha256`).
- `refetch_catalog_metadata` — after `model_data = await ...get_model_versions(...)`,
  schedule from `model_data`.

Imports stay local to the function, matching the deferred-import style the module already
uses.

---

## Step 5 — Tests

`tests/test_auto_migrator.py` — see spec's Testing section for the full list. Key
fixtures: `ext_dir` for the DB, a real temp file with known content so the SHA-256 is
genuinely computed, and a `loras_dir`-style fixture so `scan_all()` finds it.

The size-gate test is the important one: monkeypatch
`py.services.model_paths.compute_file_hash` with a spy that raises if called, then assert
`migrate` returns `[]` for a same-name-different-size file.

Hook tests: monkeypatch `auto_migrator.schedule` with a recorder and assert the browse
endpoints call it with the right normalised payload.

---

## Step 6 — Verification

From project root:

```bash
PYTHONSAFEPATH=1 ../../../comfy-env/bin/python -m pytest
../../../comfy-env/bin/python -m ruff check py tests conftest.py
../../../comfy-env/bin/python -m ruff format --check py tests conftest.py
```

All three clean, zero failures. No `ng build` — nothing under `frontend/` or `js/`
changed.

Then: commit locally, update `mem:core` with the two new services and the hook points,
commit that too, move project item #92 to Done, and wait for explicit approval before
pushing or opening a PR.
