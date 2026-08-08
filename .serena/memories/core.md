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
    workflow_repo.py   # F-129 persistence for workflow_entries + workflows
    keyword_repo.py    # trigger-word persistence
  routes/              # aiohttp route handlers: catalog, download, metadata, models, settings, workflow (node insert), workflows (workflow store), images (F-130), notifications, static, tags, _helpers
  services/            # business logic: downloader, metadata_fetcher, model_paths, reconciler, reorganizer, url_guard, backend_notifier, disk_scanner, auto_migrator, workflow_store, image_recreate
    providers/         # civitai_provider, huggingface_provider (both implement base.py)
  nodes/               # ComfyUI nodes: lora_loader_with_triggers, checkpoint_loader_with_triggers, vae_loader, controlnet_loader, embedding_helper, upscale_model_loader
frontend/              # Angular SPA (builds to ../web/)
  src/app/
    pages/             # download, catalog-detail, model-detail, models, settings, workflows, images
    components/        # shared UI: toast, media-gallery, edit-meta-form, text-diff-field, tag-autocomplete-input, …
    services/          # Angular services: civitai, huggingface, download, model, keywords, settings, notification, installed-files, workflow (node insert), workflow-store (F-129), image (F-130), tags
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

## HuggingFace search & link quirks (#157, #158, #161)

- **`_build_search_params` only sends `pipeline_tag` when `HF_TYPE_MAP` maps the model type**
  (`checkpoints`, `loras`, `embeddings` → `text-to-image`). It used to default *every* other
  type to `text-to-image` too, which silently hid nearly every genuinely matching repo for
  `vae`, `text_encoders`, `controlnet`, `unet`, `upscale_models`, `diffusion_models`, … —
  those repos are not tagged `text-to-image` on the Hub (#161). Do not reintroduce the
  default: an unmapped type must search unfiltered. The GGUF branch (`filter=gguf`) never
  sent a `pipeline_tag` and is untouched; tag filters still ride along in both branches.
- Even for a *mapped* type the filter can hide a repo the user pasted by exact id. Verified
  against the live API: `?search=huihui-ai/Huihui-Qwen3-VL-4B-Instruct-abliterated`
  returns the repo, the same query `&pipeline_tag=text-to-image` returns `[]`. The `search`
  param itself handles `owner/repo` fine, so **the query string was never the problem**.
  Fix: `HuggingFaceProvider._lookup_exact_repo()` does an *unfiltered*
  `GET /api/models/{owner}/{repo}` and `search()` prepends the hit. Guards that matter —
  `_EXACT_REPO_ID_RE` requires both halves (a keyword query must not cost an extra request),
  page 0 only, dedupe by `id`/`modelId`, every failure maps to `None`, and **`hasMore` is read
  before the prepend** or the extra item makes the page `limit + 1` and kills "Load more".
- **A HuggingFace `/blob/` URL serves the HTML file-viewer page, not the file.** It is what the
  repo file browser's copy-link gives you, so it is what users paste. `detectLink`
  (`frontend/src/app/utils/link-detector.ts`) matches both markers via `HF_FILE_RE` and the
  `hf-resolve` kind carries `downloadUrl`, always rewritten to `/resolve/`; `submitDirectLink()`
  enqueues that, never `pasteUrl()`. Backend has the same rewrite in
  `missing_model_resolver.direct_download_url()` — do not re-solve this in a third place.
- **Subfolder paths in HF filenames are already handled end to end**: `downloader.enqueue()`
  and `validate_target()` both basename HuggingFace filenames, and
  `InstalledFilesService.fileStatus()` compares on the basename. So a
  `text_encoders/model.safetensors` link needs no special casing — keep the full path in
  `filename` (matches what the HF repo-file listing yields) and let the backend reduce it.

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

## Media cleanup (F-95)

- `py/services/media_cleanup.py` owns the canonical `media_subdir(media_hash)` (path-traversal
  guard); `metadata_fetcher._media_subdir` is now just an alias to it — do not re-implement.
- **A model and its catalog entry usually share one media directory.** `fetch_and_store` passes
  the model's `media_hash` straight into `_store_catalog_entry`, and `_list_catalog_media` lists
  the whole directory so the gallery survives uninstall. Therefore every deletion is gated on
  `model_repo.get_live_media_hashes()` (union of `models.media_hash` + `catalog_entries.media_hash`)
  read **after** the model row is gone. For CivitAI, extra versions get their own hash
  (`sha1("civitai:<version_id>")`) and *are* cleaned; the one the catalog adopted is not.
- `cleanup_model_media(media_hash)` — called from `routes/models.py::_delete_model` after
  `delete_model_record`. The hash must be read *before* the delete (`get_model_media_hash`).
  A hash-less model is a no-op: `migrate_existing_media` assigns a hash on startup to every
  model owning media rows, and disk-registered models have neither.
- **Nothing is deleted by absolute path.** Every destructive call takes `(base, name)` and
  resolves it through `model_paths.contained_path` — Sonar's taint analysis (S2083/S6549)
  flags `os.remove`/`shutil.rmtree`/`os.walk` reached by a path built from request or
  settings data, and that guard is the sanitizer it accepts (same shape as `_delete_model`).
  Do not reintroduce a "delete these DB paths" helper.
- `_media_root()` validates the operator-supplied `media_dir` (absolute + existing) before the
  scan enumerates it. The two remaining S6549 findings on that enumeration
  (`os.path.isdir` / `os.listdir`) are **Accepted in SonarCloud** — read-only calls on
  admin-controlled config, inherent to the feature; rationale is in PR #127. Relocating the
  scan does not help: Sonar's new-code scope is line-based, not file-based.
- `cleanup_stale_media()` — opt-in via the `cleanup_stale_media_on_start` setting, run from
  `routes/__init__.py::_startup` right after `prune_stale_models()` so records that vanished
  free their media in the same pass. Directory granularity (a dir whose name is no live hash),
  which is what also sweeps cached `*_poster.jpg` files — they have no `model_media` row.
  Loose files in the media root go only if unreferenced. Logs + pushes a backend notification.
- There are **no metadata sidecar files** in this project; all metadata is in SQLite and the
  child rows already cascade. "Metadata cleanup" means the media files only.
- The `cleanup_stale_media_on_start` toggle lives in the **ComfyUI settings panel**
  (`js/extension.js`) only. (No longer a blanket rule: F-144's `missing_models_integration`
  is deliberately surfaced in *both* the ComfyUI panel and the Angular Settings page, kept in
  sync over `BroadcastChannel('tmm')`. The Angular page is therefore no longer keyword-only.)

## Workflow store (F-129)

Browsing/downloading CivitAI's `Workflows` model type. **`routes/workflow.py` (singular) is the
ComfyUI node-insert queue; `routes/workflows.py` (plural) is this feature** — both are registered
in `routes/__init__.py` and must not be conflated.

- **CivitAI never serves bare workflow JSON.** Every `types=Workflows` entry ships a `.zip`
  (CivitAI file type `Archive`), often holding *several* ComfyUI graphs, sized 5 KB–66 MB, and the
  download endpoint **401s without an API key** (`civitai.auth_headers()` is mandatory). The
  issue text assumed plain JSON; it was wrong. Don't "simplify" the extraction away.
- Data model mirrors catalog/model: `workflow_entries` (the source page — description, tags,
  base_model, media) 1→N `workflows` (one row per extracted graph). `UNIQUE (entry_id, local_path)`
  is what makes a re-download an upsert. Graphs live at
  `data/workflows/<media_hash>/<version_id>/<name>.json` (`cfg.workflows_dir()`).
- `services/workflow_store.py`:
  - `extract_graphs(path)` — sync + pure, the main unit-test target. Zip → skip non-`.json`,
    `__MACOSX`, absolute/`..` member names (zip-slip), oversized members; keep only dicts with a
    `nodes` list. Non-zip → parse whole file. Empty → `WorkflowPayloadError("no_workflow_json")`.
  - `_fetch_archive(url, dest, headers)` is the monkeypatch seam (never patch httpx directly).
    It streams through `url_guard.guarded_stream`, which validates every redirect hop — see
    the redirect-guard entry in `mem:conventions`. A blocked hop is remapped to `ValueError`
    so the route answers 400 rather than 500.
  - `workflow_subdir()` copies `media_cleanup.media_subdir`'s guard shape; the version id is
    forced to digits before it becomes a directory name. Nothing is written/deleted by a raw
    request path.
  - `workflow_media_hash()` uses a `workflow:` prefix so it can never collide with
    `metadata_fetcher.catalog_media_hash`.
  - `export_workflow()` copies into `folder_paths.get_user_directory()/default/workflows`, so it
    appears in ComfyUI's native workflow browser; suffixes `_1`, `_2`… on collision.
- **`model_repo.get_live_media_hashes()` unions `workflow_entries` too.** Without it
  `cleanup_stale_media()` (directory-granularity) deletes every workflow thumbnail on startup.
- `CivitaiProvider.search(types=…)` takes the raw CivitAI filter value. **Do not add
  `"workflows"` to `CIVITAI_TYPE_MAP`** — it feeds `CIVITAI_REVERSE_TYPE_MAP`, which fills
  `model_type` for the register form, and "workflows" is not a model folder.
  `get_model_page(model_id)` returns the raw page payload (`resolve_direct_link` /
  `get_version_files` both filter `type == "Model"` and return nothing for archives).
- **Load in ComfyUI** reuses the pending queue: `workflow.enqueue_graph(id)` pushes
  `{kind: "graph", workflow_id}`; `js/workflow-insert.js` branches on `kind` (absent ⇒ `"node"`,
  so old items still work) and calls `app.loadGraphData()`. A graph item is **acked even on
  failure** — unlike node items, leaving one pending wedges the whole poll loop.
- Test stubs: both conftests' `folder_paths` stub now has `base_path`, `user_directory` and
  `get_user_directory()`; patch the `user_directory` attribute to redirect an export.

## Images → workflow recreation (F-130)

Browse CivitAI's image feed and rebuild the generating ComfyUI workflow. **No image is ever
downloaded and no PNG metadata is parsed** — see the CivitAI images API section in
`mem:conventions` for the four API facts that shape this whole feature.

- `services/image_recreate.py` — sync + pure, the main unit-test target, and deliberately
  **free of ComfyUI imports** so it is importable without the `folder_paths` stub. That is
  why `is_comfy_graph` lives here and `workflow_store` re-exports it (heavy → light, never
  the reverse). Public API: `classify_meta` (`"graph"`/`"params"`/`""`), `graph_from_comfy`,
  `parse_lora_tags`, `referenced_resources`, `build_template_graph`, `needs_template_warning`.
- `build_template_graph` emits the **UI graph format** (`nodes`/`links`/`last_node_id`), not
  the API/prompt format — both `loadGraphData()` and `is_comfy_graph` want that one. Layout is
  `CheckpointLoaderSimple → LoraLoader ×N → CLIPTextEncode ×2 → EmptyLatentImage → KSampler →
  VAEDecode → SaveImage`. It is emitted for **every** base model by decision; callers surface
  `needs_template_warning(base_model)` so the UI can say it will not run unmodified outside
  SD/SDXL.
- `referenced_resources` merges four sources with different vocabularies. **The legacy
  `resources` array types the checkpoint as `"model"` while `civitaiResources` says
  `"checkpoint"`** — `_kind_of` folds them, otherwise the same checkpoint is listed twice.
  `weight` stays `None` until a source actually states one (coerced to 1.0 at the end):
  defaulting it early lets weightless `hashes` win the merge over the prompt tag that carries
  the real strength. There is a regression test for exactly that.
- `workflow_store.store_recreated_graph(image_id, name, graph, …)` reuses the F-129 tables with
  `source_platform="civitai-image"`, so recreated graphs appear under **Workflows → Installed**
  with Load/Export/JSON for free, and `UNIQUE (entry_id, local_path)` makes re-recreating an
  upsert. `get_live_media_hashes()` already unions `workflow_entries`, so their thumbnails
  survive `cleanup_stale_media()` — there is a test asserting it.
- `routes/images.py` — `GET /api/images/search`, `GET /api/images/{id}`,
  `POST /api/images/{id}/recreate`, `POST /api/images/resolve-resources`. Seams to monkeypatch:
  `_civitai_image_search`, `_civitai_version_info`, `_civitai_hash_info`.
- **Resource resolution never fails the batch.** Per resource: local hit (AutoV2 prefix vs
  `model_repo.get_file_hash_map()`) → `installed`; else CivitAI lookup → `missing` with a
  download URL; lookup returns nothing or raises → `unresolvable`. Missing models are
  downloaded only on an explicit click, through the existing `POST /api/download`.
- `CivitaiProvider.version_download_info` / `hash_download_info` are **single-request** lookups
  (no model-page enrichment, unlike `lookup_by_*`): one recreated workflow can reference a
  dozen LoRAs and doubling the request count per resource is not worth a description nobody
  shows.

## Missing Models integration (F-144)

Adds TMM buttons to ComfyUI's **Missing Models** right side panel so a workflow's missing models
download through TMM (correct folder + full model card) instead of ComfyUI's own path.

- **There is no hook to intercept.** ComfyUI's `downloadModel()` sits in a lazily-loaded ESM chunk
  and `useMissingModelStore` (Pinia) is on neither `window` nor `app`; `window.comfyAPI` only
  carries a few unrelated legacy modules. Injecting our own buttons is the *only* option — do not
  go looking for the hook again. Evidence: the frontend package ships **sourcemaps**
  (`comfyui_frontend_package/static/assets/*.js.map`, `sourcesContent` holds the original
  TS/Vue), which is the fastest way to answer any future "how does ComfyUI do X" question.
- **Outside Electron the native button is useless**: `missingModelDownload.ts` only writes into the
  models folder on desktop; in a browser it clicks an `<a download>` and the file lands in the
  user's Downloads folder. That is the whole justification for the feature.
- `py/services/missing_model_resolver.py` — `resolve(filename, model_type, url="") -> Resolution |
  None`. Chain: parse the panel's URL for provider IDs → CivitAI search → HuggingFace search
  (≤ `_HF_MAX_CANDIDATE_REPOS` = 5 repos) → the raw URL if `is_allowed_url` passes → `None`.
  **Exact filename match only** (`_same_file`: basename, case-insensitive) except for a CivitAI
  *version* link, which is authoritative and takes its primary file regardless of name. Provider
  outages are caught in `_try` and fall through instead of 500ing. All six provider calls are
  module-level `_xxx` seams; tests monkeypatch those.
- `POST /api/download/missing` in `py/routes/download.py`. Body `{filename, directory, url?}`.
  Answers 200 with `{task_id, platform, source_id, model_type, filename}` /
  `{already_installed: true}` / `{unresolved: true, search_term, model_type}`, and 400 for a
  `directory` that is not a safe path segment, or a traversal filename. **Do not gate the
  directory on a curated allowlist** — `downloader.SUPPORTED_TYPES` used to be one and was
  deleted for this reason: it listed 16 folders while ComfyUI 0.24 registers 26, so
  `latent_upscale_models`, `audio_encoders` and `model_patches` were rejected outright.
  `_get_dest_dir` already resolves any folder through `folder_paths`, including ones custom
  nodes register. **`unresolved` is a 200 on
  purpose** — the UI turns the button into "Search in TMM", it is not a failure.
  `_queue_download(...)` is the shared helper extracted from `_start_download`
  (validate_target → insert_download_history → enqueue); use it for any new download entry point.
- `frontend/js/missing-models.js` — F-93 factory module
  (`createMissingModelsIntegration({app, api, fetchFn, doc, openWindow})` → `{start, stop, sync}`).
- **The panel DOM is rewritten between frontend releases, and ComfyUI pins the frontend to an
  exact version (`comfyui-frontend-package==1.48.7` in `ComfyUI/requirements.txt`), so an older
  install stays on an older DOM indefinitely.** 1.48 dropped *every* anchor 1.45 offered except
  `missing-model-actions`, which broke the whole integration (#148): the row anchor
  `missing-model-copy-name` no longer exists, so no row button was injected and "Download all
  with TMM" looped over an empty list. The reader therefore tries each shape in turn instead of
  detecting a version — both paths stay live and testable.
  - Rows, `>= 1.48`: no per-row testid exists at all (`expand`, `download`, `locate`,
    `reference-count` are each behind a `v-if`). Anchor on the containers
    `missing-model-importable-rows` / `missing-model-import-not-supported-section`; a row is a
    direct child and its header is that child's first element child.
  - Rows, `<= 1.45`: the `missing-model-copy-name` button, header two levels up.
  - `collectRowHeaders(doc)` returns headers for both; `readRow(header, index)` reads either.
    Rows are deduped by `taskKey` so a frontend answering to both anchors cannot yield two
    buttons or two downloads.
- **Directory: three strategies, first valid wins** — 1.48 row metadata line
  (`"checkpoints · 6.86 GB"`, from `modelTypeLabel = directory ?? t(unknownCategory)`) → 1.45
  group heading `"<dir> (N)"` → `buildModelIndex()` lookup.
  **The two scraped-text sources are held to `SCRAPED_FOLDER_NAME = /^[a-z][a-z0-9_]{0,63}$/`,
  not `FOLDER_NAME = /^\w{1,64}$/`.** The panel prints a *localized* placeholder in the same slot
  when it does not know the folder — `Unknown`, `Desconocido`, `Inconnu`, `Bilinmeyen`,
  `Неизвестно`, … — and `\w` accepts the Latin ones, which would misfile a model into a folder
  literally named `Unknown`. Every shipped translation is capitalised or non-ASCII, so requiring
  ASCII lowercase snake_case rejects all of them. The index keeps the looser check: it carries
  real workflow data, not rendered text, so an unusual folder a custom node registers still works.
- `buildModelIndex()` is **graph-only** (`node.properties.models`) but walks the **whole graph
  hierarchy, subgraphs included** — Comfy-Org's templates have moved their loaders into subgraphs,
  and a root-only walk found nothing in them (#150). The Wan 2.2 T2V template's root graph holds
  two notes, one subgraph instance and SaveVideo; all six models sit in
  `definitions.subgraphs[0].nodes[].properties.models`. Every row was then posted with `url: ''`,
  which skips the resolver's URL stage *and* its raw-URL last resort, leaving only provider
  searches that cannot match a Comfy-Org repack (HF-only, and HF full-text search does not find a
  stem like `wan2.2_t2v_lightx2v_4steps_lora_v1.1_high_noise`) → "Search in TMM" for models whose
  exact URL the workflow was carrying all along. `graphHierarchy()` mirrors ComfyUI's own scanner
  (`missingModelScan.ts` → `collectAllNodes` → `forEachNode` in `graphTraversalUtil.ts`) and keeps
  **both** routes in live at once, for the usual pinned-frontend reason:
  `graph.subgraphs` when it is a `Map` (`LGraph.get subgraphs()` returns `rootGraph._subgraphs`, the
  registry of every subgraph at any depth) **and** recursion through
  `node.isSubgraphNode?.() && node.subgraph`. The `seen` set is load-bearing twice: a
  self-instantiating subgraph would hang the browser, and both routes reach the same object —
  `lookupModel` returns `entries[0]`, so a doubled entry list misleads rather than merely wastes.
  Deliberately *not* copied from ComfyUI: `getSelectedModelsMetadata`'s filter to models present in
  `widgets_values` (the index is looked up by filename, so an unselected extra is never read) and
  the bypassed-node skip (a bypassed node yields no panel row to key against).
  Two other sources are dead ends and must not be re-added:
  - `graph.extra.models` — `LGraph.configure()` does `this.extra = data.extra` and a workflow's
    `models` array is a *sibling* of `extra`, so it is dropped on load. Reading it there looked
    right and always found nothing.
  - `app.extensionManager.workflow.activeWorkflow.pendingWarnings.missingModelCandidates` — the
    1.45 cache. 1.48 removed `pendingWarnings` entirely (zero occurrences in the bundle) and moved
    the list into a Pinia `missingModelStore`. There is a test pinning each.
  A row with no URL is simply left to the backend, which resolves through CivitAI/HF anyway.
- **`app.extensionManager` IS ComfyUI's workspace store** (`U.extensionManager = useWorkspaceStore()`
  in `App.vue`), so `.toast`, `.workflow`, `.setting`, `.command` and `.sidebarTab` are reachable
  from an extension. Only the stores workspaceStore does *not* re-export (e.g. `useMissingModelStore`)
  are out of reach — the earlier blanket "Pinia is unreachable" note was too broad.
- **"Download all" reads the row list at click time**, not at injection time. `ACTIONS_MARK` stops
  the button being re-injected, so a list captured when the actions bar rendered ahead of the rows
  would stay empty for the panel's lifetime.
- `missing_model_resolver.direct_download_url()` rewrites a HuggingFace `/blob/` link to
  `/resolve/` before the raw fallback downloads it. `/blob/` serves the HTML file-viewer page, and
  both workflows and ComfyUI's "copy URL" button hand out that form — taking it verbatim stores a
  web page under a `.safetensors` name that only fails at load time.
  **A row whose directory cannot be established gets no button** (guessing puts a LoRA in
  checkpoints). Injection is made idempotent by the `data-tmm-missing` /
  `data-tmm-missing-all` markers plus a `syncing` re-entrancy flag, since our own `appendChild`
  calls are mutations the observer would otherwise re-fire on.
- Setting `missing_models_integration` (default **true**) lives in `py/routes/settings.py`, in the
  ComfyUI settings panel *and* on the Angular Settings page; both post
  `{key: 'missing_models_integration', value}` on `BroadcastChannel('tmm')` so the other side
  reacts live.
- Unresolved models deep-link to `/tiny-model-manager/download?q=<stem>&platform=civitai&type=<dir>`;
  `pages/download/download-search.ts::applyDeepLink()` reads that from
  `route.snapshot.queryParamMap` in the constructor and calls `search()`.

## Frontend routes (F-128, F-129, F-130)

The nav tab set is **Models / Workflows / Images / Download / Settings**
(`frontend/src/app/app.html`). `frontend/src/app/app.routes.ts`:

| path | component |
|---|---|
| `''` | → `models` |
| `models` | `Models` (the library page) |
| `models/:platform` | `CatalogDetail` — takes `?pageId=` |
| `models/:type/:path` | `ModelDetail` (`:path` is a filename that may contain `/`, so `routerLink` array form encodes it) |
| `workflows` | `Workflows` — shell with a `browse`/`installed` toggle over `WorkflowsBrowse` + `WorkflowsInstalled` |
| `images` | `Images` (F-130) — single page; the installed side lives in Workflows → Installed |
| `download`, `settings` | `Download`, `Settings` |
| `catalog`, `catalog/:platform` | legacy redirects → `models…` |

Catalog detail and model detail are told apart purely by **segment count** (2 vs 3) — do not add a
two-segment `models/…` route without checking that.

The **"Catalog" name still means the catalog-entry domain concept everywhere else** and was
deliberately not renamed: `/tiny-model-manager/api/catalog/*`, `py/routes/catalog.py`, the
`catalog_entries` table, `CatalogEntry*` in `services/model.ts`, and the `pages/catalog-detail/`
component. Only the tab label, the routes and the two user-visible strings moved.

## Popovers

- `services/popover.service.ts` → `PopoverService` (renamed from `ConfirmPopoverService` in
  F-94): single-`activeId` registry so only one popover is open at a time, across all types.
- Two consumers: `components/confirm-popover/` and `components/file-picker-popover/`. Both
  project their trigger via `<ng-content>`, toggle on host click, and close on outside click
  and Escape. Copy that shape for any new popover rather than hand-rolling the listeners.
- `FilePickerPopover` types its input as the structural `PickableFile`
  (`{filename, model_type}`), so `InstalledFile` and `RepoFile` both fit without an import.

## Invariants

- `web/` is **intentionally tracked**, not git-ignored (see the comment at `.gitignore:5`: the
  committed bundle is what makes the node installable without a Node.js toolchain). So `npx ng build`
  output is part of the commit — run it from the **main checkout's** `frontend/` before committing UI
  changes and stage the changed `web/` files with them. A frontend-only edit usually shows up as just
  the one changed asset, because the Angular chunk hashes only move when `src/` changes.
- `js/` is bundled as an ng build asset; never deploy it separately.
- ComfyUI stubs (server, folder_paths) must be installed at conftest import time, not inside fixtures.
- Python path: `PYTHONSAFEPATH=1` required (avoids `py` package collision with pytest's internal `py` lib).

See `mem:tech_stack`, `mem:conventions`, `mem:suggested_commands`, `mem:task_completion` for details.
