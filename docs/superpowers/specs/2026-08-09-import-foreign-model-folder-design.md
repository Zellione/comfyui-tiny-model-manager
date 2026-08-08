# Import selected models from a different ComfyUI model folder (issue #154)

Status: approved 2026-08-09
Issue: https://github.com/Zellione/comfyui-tiny-model-manager/issues/154
Milestone: 0.2.0

## Problem

A user running more than one ComfyUI installation, or migrating away from an old one, has no way
to bring existing models into the managed library. Today the only options are re-downloading
multi-gigabyte files or copying them by hand and then registering each one. This feature lets the
user point at another installation's model folder, see what is there, pick what they want, and
import it with metadata.

## Scope

The user pastes an absolute path to a foreign ComfyUI models root. The backend scans it, compares
every file against the local library by SHA-256, and reports which files are new. The user selects
files and the backend **copies** them into the matching local model folder, registers them, and
enriches them from CivitAI by hash.

Out of scope, deliberately:

- **Move and symlink/hardlink import modes.** Copy only. Move breaks the source installation
  irreversibly; symlinks need admin rights or developer mode on Windows and hardlinks need a shared
  filesystem. Either can be added later behind the same job API without reshaping this feature.
- **Per-file model-type override.** The type comes from the subfolder name. A messy folder that is
  not laid out like a ComfyUI models root is not a supported source.
- **Importing the foreign installation's own TMM database**, workflows, or custom nodes.
- **A server-side directory browser.** The path is typed or pasted.

## Import mode: copy

The source installation is left untouched and fully working. The cost is disk space and time, which
is why both phases are background jobs with progress rather than blocking requests.

## Source folder contract

The user supplies an absolute path to a models root. Each **immediate subdirectory name is the model
type** (`checkpoints`, `loras`, `vae`, ...), which is exactly how the local scanner already treats
the local roots. Relative subfolder structure inside a type is preserved on import, so
`loras/style/foo.safetensors` lands at `<local loras dir>/style/foo.safetensors`.

Convenience: if the supplied path itself contains a `models/` subdirectory, that subdirectory is
used. Pasting `D:\OtherComfyUI` therefore works as well as `D:\OtherComfyUI\models`.

A type subfolder that is not registered locally is still listed. On import its destination is
`models_dir/<type>`, guarded by `model_paths.is_safe_segment`.

## Duplicate detection: SHA-256

A file is `installed` when its SHA-256 is already present in the local library, otherwise `new`.
Filename comparison was rejected: a truncated or corrupt local copy would silently hide a good
source file.

Hashing a whole library is expensive, so three things keep it affordable:

1. **The file list is returned before hashing starts.** The directory walk is fast; the scan job
   publishes its file list immediately and fills in per-file status as hashing progresses. A large
   library shows its contents at once and resolves duplicates over the following minutes.
2. **The local side is mostly free.** `model_repo.get_file_hash_map()` already holds the SHA-256 of
   every registered model that has one. Only local files missing a hash are hashed, and the result
   is written back to `models.file_hash`, so the second scan is nearly instant.
3. **The hashes are needed anyway.** The same source-file SHA-256 that decides `installed` vs `new`
   is what CivitAI's by-hash lookup consumes for metadata enrichment. Nothing is hashed twice.

## Architecture

New service `py/services/foreign_import.py`, new routes in `py/routes/imports.py`. Job state is an
in-memory registry with a `progress` float, mirroring `services/downloader.py`'s `_tasks` shape.
Both jobs are started through `background.spawn` so no request blocks on I/O.

### Scan job

1. `validate_root(path) -> str` — the path must be absolute and an existing directory; if it holds a
   `models/` subdirectory, that is used instead. A path resolving inside the **local** model roots
   is rejected: importing from yourself is at best a no-op and at worst a self-overwrite.
2. `scan_source(root) -> list[SourceFile]` — for each immediate subdirectory, reuse
   `disk_scanner.scan_dir(subdir, extensions)` with the existing extension sets. Each entry carries
   `{model_type, filename, abs_path, size_bytes}` where `filename` is relative to the type folder.
3. The job publishes that list, then hashes each source file with
   `model_paths.compute_file_hash` via `asyncio.to_thread`, setting each entry's status to
   `installed` or `new`.
4. A file that cannot be read is marked `unreadable` and the job continues.

### Import job

Input is the selected `{model_type, filename}` list plus the validated source root.

1. **Free-space precheck.** The selection total is compared against `shutil.disk_usage` for the
   destination. A shortfall refuses the whole job upfront with needed-vs-available, rather than
   dying part-way through.
2. Destination is `model_paths.candidate_dirs(model_type)[0]`, falling back to `models_dir/<type>`
   for an unknown type. The relative subfolder path is preserved and the result is validated with
   `model_paths.contained_path`, so nothing is ever written to a raw request-supplied path.
3. Each file is copied to a `.tmm-part` temporary name and then atomically renamed. An interrupted
   copy therefore never leaves a plausible-looking corrupt model in a model folder.
4. A destination name collision gets a `_1`, `_2`, ... suffix, matching
   `workflow_store.export_workflow`'s existing behaviour.
5. On success: `model_repo.register_model(filename, model_type, file_hash=<hash from the scan>)`.
6. **Enrichment:** `CivitaiProvider.lookup_by_hash(sha256)`. `register_model` is an upsert, so a hit
   simply calls it again, filling in
   `name`, `base_model`, `description`, `tags`, trigger words and source linkage from the shared
   metadata dict shape. HuggingFace exposes **no** by-hash lookup, so HF-origin models import
   without metadata; the user can still use "Re-fetch metadata" or the link resolver afterwards.
7. A per-file failure is recorded with its reason, the partial file is removed, and the job
   continues with the remaining files.

### Routes

| Route | Purpose |
|---|---|
| `POST /tiny-model-manager/api/import/scan` | body `{path}`; validates and starts a scan job; returns `{job_id, source_root}` |
| `GET /tiny-model-manager/api/import/scan/{job_id}` | `{state, progress, files: [...]}` |
| `POST /tiny-model-manager/api/import/start` | body `{source_root, files: [{model_type, filename}]}`; returns `{job_id}` |
| `GET /tiny-model-manager/api/import/jobs/{job_id}` | `{state, progress, imported, skipped, failed: [...]}` |
| `POST /tiny-model-manager/api/import/jobs/{job_id}/cancel` | stops after the current file |

## Frontend

New page `frontend/src/app/pages/model-import/` at route `models/import`, reached from an
"Import from another folder" button on the Models page.

**Route ordering is load-bearing.** `models/:platform` (catalog detail) and `models/:type/:path`
(model detail) are told apart purely by segment count, and `models/import` is two segments. It must
be declared **before** `models/:platform` in `app.routes.ts` or it resolves to catalog detail.

Flow: path input and Scan button → progress bar during hashing → results grouped by model type,
each row showing name, size and an `Already installed` / `New` badge, with a per-group select-all →
Import → progress → a summary of imported, skipped and failed files.

New `frontend/src/app/services/model-import.ts`. Per project convention: `OnPush` and signals
throughout, polling as `interval() + switchMap()` with `catchError(() => of(fallback))` **inside**
the switchMap so a transient failure cannot terminate the stream, and every subscription guarded
with `takeUntilDestroyed`. All user-visible strings go through ngx-translate keys.

The last-used source path is persisted as a new `import_source_root` setting so a long absolute
Windows path is not retyped on every use.

## Error handling

| Condition | Behaviour |
|---|---|
| Path relative, missing, or not a directory | 400 with a distinct error key |
| Path resolves inside the local model roots | 400 |
| Source file unreadable during scan | file marked `unreadable`, scan continues |
| Insufficient disk space | 409 before any copy, reporting needed vs available |
| Copy fails mid-job | file marked failed with reason, partial removed, job continues |
| CivitAI unreachable or returns no match | model is imported and registered, metadata absent |
| Unknown job id | 404 |

## Testing

**Backend unit — `tests/test_foreign_import.py`:** `validate_root` (relative path, missing path,
file-not-directory, `models/` auto-append, self-import rejection); `scan_source` type derivation and
subfolder preservation; hash-based `installed` vs `new`; destination resolution for known and
unknown types; collision suffixing; disk-space refusal; partial-file cleanup on copy failure.

**Backend integration — `tests/test_routes_imports.py`,** using the `aiohttp_client` and `ext_dir`
fixtures. The autouse `block_network` fixture forbids real requests, so the CivitAI lookup is
monkeypatched at a module-level `_xxx` seam as the project's other route tests do. Covers the full
scan → select → import → registered round trip against a temporary source tree.

**Frontend — `model-import.spec.ts` and the service spec:** `TestBed.configureTestingModule` with
`vi.fn()` mocks for injected services, asserting signal state; selection and select-all logic;
polling `catchError` fallback; the error branch rendering separately from the empty state.

## Serena memory

`mem:core` gains the new service, routes page and frontend route; the route-ordering constraint is
added to the existing warning about two-segment `models/…` routes.
