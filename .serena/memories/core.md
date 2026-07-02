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
  services/            # business logic: downloader, metadata_fetcher, model_paths, reconciler, reorganizer, url_guard, backend_notifier
    providers/         # civitai_provider, huggingface_provider (both implement base.py)
  nodes/               # ComfyUI nodes: lora_loader_with_triggers, checkpoint_loader_with_triggers, vae_loader, controlnet_loader, embedding_helper, upscale_model_loader
frontend/              # Angular SPA (builds to ../web/)
  src/app/
    pages/             # download, catalog-detail, model-detail, models, settings
    components/        # shared UI: toast, media-gallery, edit-meta-form, text-diff-field, tag-autocomplete-input, …
    services/          # Angular services: civitai, huggingface, download, model, keywords, settings, notification, installed-files, workflow, tags
js/                    # ComfyUI JS extension (topbar button); bundled into web/ by ng build
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

## Key utility functions

- `compute_file_hash(path)` in `py/services/model_paths.py` — synchronous SHA-256 (1 MB chunks), always called via `asyncio.to_thread`.
- `CivitaiProvider.lookup_by_hash(sha256)` in `py/services/providers/civitai_provider.py` — `GET /v1/model-versions/by-hash/{sha256}`; returns parsed dict or `None` on 404; raises `httpx.HTTPError` on other failures.

## Invariants

- `web/` is git-ignored → always run `npx ng build` from **main checkout's** `frontend/` before committing UI changes.
- `js/` is bundled as an ng build asset; never deploy it separately.
- ComfyUI stubs (server, folder_paths) must be installed at conftest import time, not inside fixtures.
- Python path: `PYTHONSAFEPATH=1` required (avoids `py` package collision with pytest's internal `py` lib).

See `mem:tech_stack`, `mem:conventions`, `mem:suggested_commands`, `mem:task_completion` for details.
