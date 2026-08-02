# Core — comfyui-tiny-model-manager

ComfyUI custom node: dashboard for managing/downloading models, LORAs, workflows from CivitAI and HuggingFace.

## Source map

```
__init__.py            # ComfyUI entry: registers routes + node mappings, sets WEB_DIRECTORY=./web
py/                    # Python backend
  config.py            # ext_dir initialisation (call cfg.init(path) in tests)
  background.py        # background task runner
  db/
    database.py        # SQLite init (init_db), schema, _COLUMN_ADDITIONS list (idempotent ALTER TABLE)
    model_repo.py      # main persistence layer (includes search_tags, get_registered_filenames, register_model)
    keyword_repo.py    # trigger-word persistence
  routes/              # aiohttp route handlers: catalog, download, metadata, models, settings, workflow, notifications, static, tags, _helpers
  services/            # business logic: downloader, metadata_fetcher, model_paths, reconciler, reorganizer, url_guard, backend_notifier, disk_scanner, auto_migrator
    providers/         # civitai_provider, huggingface_provider (both implement base.py)
  nodes/               # ComfyUI nodes: lora_loader_with_triggers, checkpoint_loader_with_triggers, vae_loader, controlnet_loader, embedding_helper, upscale_model_loader
frontend/              # Angular SPA (builds to ../web/)
  src/app/
    pages/             # download, catalog-detail, model-detail, models, settings
    components/        # shared UI: toast, media-gallery, edit-meta-form, text-diff-field, tag-autocomplete-input, …
    services/          # Angular services: civitai, huggingface, download, model, keywords, settings, notification, installed-files, workflow, tags
js/                    # ComfyUI JS extension; whole folder copied into web/ by ng build
  extension.js         # registerExtension wiring: settings, topbar button, workflow-insert poll
  workflow-insert.js   # dependency-injected insert logic (no ComfyUI imports) — unit-testable;
                       # spec lives at frontend/src/comfy-extension/workflow-insert.spec.ts
tests/                 # pytest integration + unit tests (includes test_routes_tags.py)
conftest.py            # root conftest: installs ComfyUI stubs (server, folder_paths, comfy.sd, comfy.utils) at import time
tests/conftest.py      # ext_dir fixture: tmp_path + init_db; route tests use aiohttp_client + ext_dir
web/                   # compiled frontend output (git-ignored; each worktree has its own)
```

## Database schema notes

- `models` table has a `file_hash TEXT DEFAULT NULL` column (added in F-89 via `_COLUMN_ADDITIONS`).
- New columns go in `py/db/database.py` → `_COLUMN_ADDITIONS` list as `"ALTER TABLE models ADD COLUMN ..."` — processed idempotently by `_add_new_columns()` (silently ignores "column already exists").

## Key model_repo functions

- `get_registered_filenames() -> set[str]` — returns all `filename` values from the `models` table as a set; O(1) membership checks.
- `register_model(filename, model_type, base_model, tags, description, file_hash, source_platform, source_id, civitai_model_id) -> int` — upserts via `_upsert_model_row` + `_set_model_tags`; returns `model_id`. All new fields default to `""`. ON CONFLICT uses `CASE WHEN excluded.field != '' THEN excluded.field ELSE field END` (preserves existing value when new value is empty — same pattern as `base_model`).

## Key routes (models)

- `GET /tiny-model-manager/api/models/unregistered` — scans all model dirs and returns files not in `models` table, grouped by type.
- `POST /tiny-model-manager/api/models/register` — body: `{filename, model_type, base_model?, tags?, description?, file_hash?, source_platform?, source_id?, civitai_model_id?}`; validates file existence via `model_paths.find_file()`; returns `ok({model_id})`.
- `POST /tiny-model-manager/api/models/hash-lookup` — body: `{filename, model_type}`; computes SHA-256 via `asyncio.to_thread(compute_file_hash, path)`, queries CivitAI; returns `ok({hash, match: true, metadata: {...}})` or `ok({hash, match: false})`; 404 on file not found, 503 on CivitAI error.
- `POST /tiny-model-manager/api/models/resolve-link` — body: `{url}`; parses a CivitAI/HuggingFace model URL and fetches its metadata (F-91). Returns `ok({platform, source_id, metadata})`. Errors: 400 `invalid_url`, 404 `not_found`, 503 `provider_unavailable`. Test seam: monkeypatch `py.routes.models._resolve_model_link`.

## Key utility functions

- `compute_file_hash(path)` in `py/services/model_paths.py` — synchronous SHA-256 (1 MB chunks), always called via `asyncio.to_thread`.
- `CivitaiProvider.lookup_by_hash(sha256)` in `py/services/providers/civitai_provider.py` — `GET /v1/model-versions/by-hash/{sha256}`; returns parsed dict or `None` on 404; raises `httpx.HTTPError` on other failures.

## Registration metadata lookup (shared shape)

All three provider lookups return the **same dict shape**, so the register form has one
contract to handle: `{name, base_model, description, tags, trigger_words, version_name,
civitai_version_id, civitai_model_id, model_type, thumbnail}`.

- `civitai_provider._version_to_metadata(data)` — module-level flattener for any CivitAI
  model-version response; every CivitAI lookup goes through it.
- `CivitaiProvider.lookup_by_hash / lookup_by_version_id / lookup_by_model_id(model_id, version_id="")`
  — `lookup_by_model_id` picks the requested version (or `modelVersions[0]`) and splices the
  model-level `{name, tags, type, description}` back in before flattening.
- `HuggingFaceProvider.lookup_by_repo_id(repo_id)` — `GET /api/models/{repo}`; maps `cardData`
  (`base_model`, `description`, `instance_prompt`/`trigger`) into the same shape; `None` on 404.
- `py/services/link_resolver.py` — `parse_model_link(url) -> ParsedLink | None` (gated on
  `url_guard.is_allowed_url`; handles `civitai.com/models/{id}[?modelVersionId=]`,
  `/api/download/models/{vid}`, `/model-versions/{vid}`, and `huggingface.co/{owner}/{repo}`
  with `/tree|/blob|/resolve|/raw|…` suffixes stripped) plus `async resolve(parsed)`.
  The pasted URL is never fetched — only the extracted IDs are sent to a provider API.
- `huggingface_provider.validate_repo_id` is **public** (was `_validate_repo_id`) so
  `link_resolver` can reuse it.

## Disk scanning & auto-migration (F-92)

- `py/services/disk_scanner.py` — `scan_all() -> {model_type: [{filename, base_dir,
  size_bytes, modified_at}]}`. Extracted from `routes/models.py`; `_list_models` and
  `_get_unregistered_files` are now thin callers. `catalog.py` still has its own
  near-duplicate scan helpers (deliberately not unified).
- `py/services/auto_migrator.py` — silently registers unregistered on-disk files whose
  SHA-256 matches a hash returned by a CivitAI/HF fetch.
  - `RemoteFile` dataclass + `from_civitai_versions(dict | list)` /
    `from_hf_files(repo_id, files)` normalisers. `from_civitai_versions` tolerates a bare
    version list because it runs directly on a provider payload.
  - Matching is **name gate → size gate (64 KB tolerance) → SHA-256 verify**. Never hash
    a file that failed the first two gates — that guard is what keeps the feature
    affordable on a large library, and there is a test asserting `compute_file_hash` is
    not called on a size mismatch.
  - Bounded FIFO hash cache keyed by `(path, size, mtime)`, cap `_HASH_CACHE_MAX = 256`.
  - On match: `register_model(...)` with the verified `file_hash`, source linkage, and the
    base_model/description/trigger_words already in the provider payload.
  - **Never call `fetch_and_store` from the migrator.** It re-enters `_fetch_repo_files`
    → `schedule` → `migrate` (a cycle), and with `organize_into_subfolders` on it
    relocates the file and upserts under the new path, orphaning the row `register_model`
    just wrote (one file, two records). The stored source linkage means "Re-fetch
    metadata" fills in the rest on demand.
  - `schedule(files)` is fire-and-forget via `background.spawn`; no request blocks on
    hashing. Returns `None` on an empty list, else the `asyncio.Task` — tests must await
    that task, never drain `background._background_tasks` (it holds the downloader's
    `while True` worker, which never completes and will hang the suite).
- **Hook points** (4): `routes/download.py` → `civitai_versions`, `hf_files`;
  `services/metadata_fetcher.py` → `_fetch_repo_files` (only the `get_model_versions`
  branch — `get_version_files` returns no hashes) and `refetch_catalog_metadata`.
- `HuggingFaceProvider.get_model_files` exposes `sha256` from `siblings[].lfs.oid`
  (`""` for non-LFS blobs, whose `blob_id` is a SHA-1 and unusable).

## Workflow insertion (F-94)

- Pipeline is frontend → backend queue → JS extension: `POST /workflow/insert` appends to the
  in-memory `_pending` list in `py/routes/workflow.py`; `js/workflow-insert.js` polls
  `/workflow/pending`, maps `model_type` via `NODE_TYPE_MAP`, creates the node, then acks.
- **A queued item of a type missing from `NODE_TYPE_MAP` is skipped and never acked**, so it
  stays in `_pending` forever and the Models page keeps that card under the "processing"
  overlay (`pendingFilenames`). Hence `WORKFLOW_INSERTABLE_TYPES` / `isWorkflowInsertable()`
  in `frontend/src/app/services/workflow.ts`: the UI only offers insertion for those 6 types.
  The frontend cannot import the extension module at runtime, so `workflow.spec.ts` asserts
  the constant equals `Object.keys(NODE_TYPE_MAP)` — specs *can* import `js/workflow-insert.js`
  (see `comfy-extension/workflow-insert.spec.ts`), so drift fails the suite instead of silently
  shipping.
- Models page cards: 1 insertable file → direct insert; 2+ → `app-file-picker-popover`. Always
  use the **file's** `model_type`, never the entry's — one catalog entry can mix types.

## Popovers

- `services/popover.service.ts` → `PopoverService` (renamed from `ConfirmPopoverService` in
  F-94): single-`activeId` registry so only one popover is open at a time, across all types.
- Two consumers: `components/confirm-popover/` and `components/file-picker-popover/`. Both
  project their trigger via `<ng-content>`, toggle on host click, and close on outside click
  and Escape. Copy that shape for any new popover rather than hand-rolling the listeners.
- `FilePickerPopover` types its input as the structural `PickableFile`
  (`{filename, model_type}`), so `InstalledFile` and `RepoFile` both fit without an import.

## Invariants

- `web/` is git-ignored → always run `npx ng build` from **main checkout's** `frontend/` before committing UI changes.
- `js/` is bundled as an ng build asset; never deploy it separately.
- ComfyUI stubs (server, folder_paths) must be installed at conftest import time, not inside fixtures.
- Python path: `PYTHONSAFEPATH=1` required (avoids `py` package collision with pytest's internal `py` lib).

See `mem:tech_stack`, `mem:conventions`, `mem:suggested_commands`, `mem:task_completion` for details.
