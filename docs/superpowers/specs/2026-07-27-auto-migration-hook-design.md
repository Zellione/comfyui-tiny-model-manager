# Feature #92: Auto-migration Hook in Existing Fetch Paths

**Issue:** #92
**Parent epic:** #88 (Migrate Disk Models to Model Cards)
**Date:** 2026-07-27

## Summary

Completes the disk-scanner epic. F-89 added the unregistered-file scan, F-90 added
hash-based CivitAI lookup and F-91 added link resolution — all of them user-initiated.
F-92 removes the user from the loop: whenever the backend already fetches CivitAI or
HuggingFace metadata for some other reason, it compares the file hashes in that response
against unregistered files on disk and silently creates model cards for the matches.

No new API endpoints, no new DB columns. The `file_hash` column added in F-89 is reused.

## Problem statement

The issue text says to "compare the returned file hash(es) against unregistered on-disk
files (using the `file_hash` index)". Two things named there do not exist:

1. `ProviderMetadata` carries no file hashes at all — only description, trigger words,
   image URLs, tags, base model and CivitAI ids.
2. There is no index of unregistered file hashes. `file_hash` lives on the `models`
   table, so by definition it only covers files that are *already* registered.

The raw hashes are available, just discarded:

- CivitAI `GET /v1/models/{id}` → `modelVersions[].files[].hashes.SHA256`. Already
  reaches our code intact, because `get_model_versions` returns raw `modelVersions`.
- HuggingFace `GET /api/models/{repo}?blobs=true` → `siblings[].lfs.oid`, which is the
  SHA-256 for LFS-backed files. `get_model_files` currently drops the `lfs` block.

So the design has to define its own matching strategy rather than consult a
non-existent index.

## Matching strategy

Hashing is the expensive part: a 6 GB checkpoint takes tens of seconds to read. Hashing
every unregistered file on every metadata fetch is not viable on a real library.

The chosen strategy narrows to a single candidate before hashing anything:

1. **Name gate.** Group the remote files by lowercase basename. Only on-disk files whose
   basename matches a remote file are considered. This is the realistic case: a user who
   downloaded a model by hand still has the upstream filename.
2. **Size gate.** Reject when both sizes are known and differ by more than 64 KB.
   CivitAI reports `sizeKB` as a rounded float, so an exact comparison would produce
   false negatives; 64 KB is far below the gap between any two genuinely different model
   files.
3. **Hash verify.** Only survivors of both gates are read from disk and SHA-256'd, then
   compared against the remote hash. The hash is what actually authorises the match —
   the gates exist purely to avoid pointless I/O.

A bounded in-process cache keyed by `(path, size, mtime)` means a given file is hashed at
most once per session, so browsing the same CivitAI model page repeatedly does not
re-read gigabytes. The cache is capped and evicts oldest-first.

Renamed files are not matched. Catching those needs a persistent hash index over the
whole library, which is a much larger feature than this issue describes.

## Architecture

### New: `py/services/disk_scanner.py`

The multi-directory model-file walk currently lives inside `py/routes/models.py` as
`_scan_dir`, `_scan_registered_types`, `_scan_root_subdirs`, `_BROAD_EXTENSIONS` and
`_SKIP_TYPES`. It moves into a service behind one entry point:

```python
def scan_all() -> dict[str, list[dict]]:
    """model_type -> [{filename, base_dir, size_bytes, modified_at}, ...]"""
```

`_get_unregistered_files` becomes a thin caller. Behaviour is unchanged.

This extraction is required, not cosmetic: auto-migration must search *all* model
directories. The HuggingFace browse endpoint has no model type in hand — the user picks
one only at download time (F-61) — so the type must be derived from whichever directory
the matching file is found in.

The near-identical scan helpers in `catalog.py` are deliberately left alone. Unifying
them is unrelated refactoring.

### New: `py/services/auto_migrator.py`

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
    tags: list[str] = field(default_factory=list)
    trigger_words: list[str] = field(default_factory=list)
    description: str = ""
```

Public surface:

| Function | Purpose |
| --- | --- |
| `from_civitai_versions(model_data)` | Normalise `{versions, model_type}` from `get_model_versions` |
| `from_hf_files(repo_id, files)` | Normalise the output of `get_model_files` |
| `async migrate(remote_files) -> list[str]` | The algorithm; returns migrated filenames |
| `schedule(remote_files) -> Task \| None` | Fire-and-forget wrapper over `background.spawn`; returns the task so tests can await their own rather than the global set |

`from_civitai_versions` walks `versions[].files[]`, keeps only `type == "Model"`, and
skips entries with no `hashes.SHA256`. Each `RemoteFile` carries the version id as
`source_id` plus `modelId` and `baseModel`, so a match can be linked back to its source.

`from_hf_files` reads the `sha256` field added to the provider (below) and uses the repo
id as `source_id`.

`migrate` calls `disk_scanner.scan_all()` and `model_repo.get_registered_filenames()`
once each, then applies the three gates per candidate. On a match it calls
`register_model(...)` with the verified `file_hash`, the source linkage, and the
base model / description / trigger words already present in the provider payload.

**It deliberately does not call `fetch_and_store`.** An earlier revision did, to enrich
the stub into a full card. That was wrong on two counts:

1. **Re-entrancy.** `fetch_and_store` → `_fetch_repo_files` → `schedule()` → `migrate` →
   `_register_match` → `fetch_and_store` is a cycle. It happens to terminate once the row
   is registered, but it is a loop that should not exist.
2. **Duplicate rows.** With `organize_into_subfolders` enabled, `fetch_and_store`
   relocates the file and upserts under the *new* path, orphaning the row written by
   `register_model` at the old path — one file, two records.

Since the card stores `source_platform` and `source_id`, the existing "Re-fetch metadata"
action fills in images and the remaining fields on demand. That keeps migration a single
cheap DB write with no side effects on the file system.

Registration is wrapped so one unreadable or unwritable file cannot abort the batch.

`schedule` short-circuits on an empty list so the common case (a model with no hashes, or
a library with nothing unregistered) costs nothing.

### Changed: `HuggingFaceProvider.get_model_files`

Gains `"sha256": (f.get("lfs") or {}).get("oid", "")`. Purely additive —
`_model_files_for_storage` and the frontend ignore the extra key. CivitAI needs no
provider change.

## Hook points

All four are fire-and-forget via `background.spawn`, so no request ever blocks on
hashing.

| Location | Trigger |
| --- | --- |
| `routes/download.py` → `civitai_versions` | User browses a CivitAI model's versions |
| `routes/download.py` → `hf_files` | User browses a HuggingFace repo's files |
| `services/metadata_fetcher.py` → `_fetch_repo_files` | Download completed, or metadata re-fetched |
| `services/metadata_fetcher.py` → `refetch_catalog_metadata` | Catalog entry re-fetched |

The two browse endpoints matter most: looking up a model you already own is exactly the
moment auto-migration should fire. `refetch_catalog_metadata` does not route through
`_fetch_repo_files`, so it needs its own hook; it already holds `model_data`, so this
costs one line.

## Error handling

- Unknown platform, missing hashes, empty file list → no-op, no log noise.
- File vanishes between scan and hash → `OSError` caught per candidate, skipped.
- `register_model` raises → logged at warning, batch continues.
- Whole migration raises → caught inside the background task; a browse request that
  already returned successfully is never retroactively failed.

## Feedback

Per migrated file: an `_log.info` line and a `backend_notifier.push("info", ...)` toast
naming the file and the platform. No prompt, no confirmation — the user simply learns
their library changed. This satisfies the issue's "log the auto-migration event"
requirement using the existing notification system.

## Scope boundaries

Deliberately excluded:

- **No settings toggle.** The issue specifies unconditional migration.
- **No persistent hash index.** Would catch renamed files, but is its own feature.
- **No frontend changes.** Backend-only, so no `ng build` is required for this feature.
- **No `catalog.py` scan unification.** Unrelated to this goal.

## Testing

`tests/test_auto_migrator.py`:

- `from_civitai_versions` extracts filename, hash, size, version id, model id and base
  model; skips non-`Model` files and files with no SHA-256
- `from_hf_files` extracts the LFS oid
- happy path: matching name + size + hash registers the file and returns it
- already-registered file is skipped
- size mismatch is rejected **without hashing** (asserts `compute_file_hash` is never
  called — this is the guard that keeps the feature affordable)
- hash mismatch does not register
- empty input short-circuits without scanning disk
- the hash cache prevents a second read of the same file
- a failing `register_model` does not abort the remaining candidates
- a successful migration pushes a notification

Hook-point coverage in the download and metadata route tests, plus an HF provider test
for the new `sha256` field.
