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

## Invariants

- `web/` is git-ignored → always run `npx ng build` from **main checkout's** `frontend/` before committing UI changes.
- `js/` is bundled as an ng build asset; never deploy it separately.
- ComfyUI stubs (server, folder_paths) must be installed at conftest import time, not inside fixtures.
- Python path: `PYTHONSAFEPATH=1` required (avoids `py` package collision with pytest's internal `py` lib).

See `mem:tech_stack`, `mem:conventions`, `mem:suggested_commands`, `mem:task_completion` for details.
