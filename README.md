# ComfyUI Tiny Model Manager

A ComfyUI custom node providing a web dashboard to browse, download, and manage AI models and LoRAs from CivitAI and HuggingFace.

## Installation

### ComfyUI-Manager / Registry (recommended)

Search for **Tiny Model Manager** in ComfyUI-Manager and click *Install*, or from a terminal:

```bash
comfy node install tiny-model-manager
```

The published package ships a prebuilt dashboard, so **no Node.js toolchain is required**.
Restart ComfyUI and open `http://localhost:8188/tiny-model-manager`.

### Install via Git URL

In ComfyUI-Manager choose **Install via Git URL** and paste:

```
https://github.com/Zellione/comfyui-tiny-model-manager
```

Python dependencies install automatically from `requirements.txt`. The repository tracks a
prebuilt `web/` bundle, so the dashboard works straight away.

### Manual installation

```bash
cd ComfyUI/custom_nodes
git clone https://github.com/Zellione/comfyui-tiny-model-manager
cd comfyui-tiny-model-manager
pip install -r requirements.txt
```

Restart ComfyUI and open `http://localhost:8188/tiny-model-manager`.

The tracked `web/` bundle is refreshed on each release, so it can lag `main` between releases.
To rebuild it from source (requires Node.js 22+):

```bash
cd frontend
npm install
npx ng build
```

If the dashboard reports that it has not been built, that rebuild is the fix — the loader nodes
work regardless.

---

## Developer Setup

### Python environment

ComfyUI runs the backend with its own interpreter, so install into that one rather than a
system Python.

**Windows (`python_embeded`)**

```powershell
..\..\..\python_embeded\python.exe -m pip install -r requirements.txt -r requirements-dev.txt
```

**Linux (comfy-cli venv at `../../../comfy-env`)**

```bash
source ../../../comfy-env/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
```

The backend supports Python 3.10+; CI runs the suite on 3.10 through 3.13.

### Frontend

`web/` holds the compiled Angular bundle and is tracked in git so the node installs without a
Node.js toolchain. Rebuild it after any change under `frontend/`:

```bash
cd frontend
npm install          # once, or after package.json changes
npx ng build         # production build → ../web/
npx ng build --watch --configuration development   # during active development
```

### Git hooks

After cloning, activate the git hooks once per clone so the pre-push coverage gate runs automatically:

```bash
git config core.hooksPath .githooks
```

The hook at `.githooks/pre-push` runs before every `git push` and enforces minimum coverage thresholds:

- **Backend** ≥ 88 % lines (`pytest --cov=py`, threshold set in `pyproject.toml`)
- **Frontend** ≥ 74 % lines / ≥ 62 % functions / ≥ 74 % branches (thresholds in `angular.json`)

The push is blocked if either threshold is not met.

### Releasing to the Comfy Registry

Bump `version` in `pyproject.toml` and merge to `main`. That is the whole release trigger:
`.github/workflows/publish.yml` rebuilds the frontend, commits the refreshed `web/` bundle, and
publishes to the Registry.

Publishing requires the `REGISTRY_ACCESS_TOKEN` repository secret, generated from the publisher
account at [registry.comfy.org](https://registry.comfy.org).

---

## API Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/tiny-model-manager` | Serves the Angular SPA |
| GET | `/tiny-model-manager/api/models` | List all installed models by type; each entry includes `metadata` with `description`, `trigger_words`, `tags`, `media`, `base_model`, `source_platform`, `source_url` |
| DELETE | `/tiny-model-manager/api/models/{type}/{path}` | Delete a model file |
| POST | `/tiny-model-manager/api/models/organize` | Move all installed models into base-model subfolders; returns moved/skipped/error counts |
| GET | `/tiny-model-manager/api/models/{type}/{path}/metadata` | Get stored metadata — returns `description`, `trigger_words`, `tags`, `media`, `base_model`, `source_platform`, `source_url` |
| PUT | `/tiny-model-manager/api/models/{type}/{path}/metadata` | Update `description`, `trigger_words`, `tags`, and optionally `base_model` |
| POST | `/tiny-model-manager/api/models/{type}/{path}/refetch` | Re-fetch metadata/tags from the source platform; response includes `base_model` and `source_url` |
| POST | `/tiny-model-manager/api/models/{type}/{path}/media` | Upload JPEG/PNG/WebP/GIF card images (max 10 MB per file, up to 10 per request); body: `FormData` with repeated `files` field; response is the refreshed gallery `{"success": true, "media": […]}` |
| DELETE | `/tiny-model-manager/api/models/{type}/{path}/media/{media_id}` | Remove a user-uploaded card image by media row id; only accepts uploads (basename matching `upload-<12-hex>.<ext>`) |
| GET | `/tiny-model-manager/api/search/civitai` | Search CivitAI — params: `q`, `type`, `base_model`, `sort`, `period`, `page`, `cursor` |
| GET | `/tiny-model-manager/api/civitai/versions/{model_id}` | Get CivitAI model versions |
| GET | `/tiny-model-manager/api/civitai/resolve/{version_id}` | Resolve a CivitAI direct download URL to filename + model type |
| GET | `/tiny-model-manager/api/search/huggingface` | Search HuggingFace — params: `q`, `type`, `sort`, `direction`, `format`, `p` |
| GET | `/tiny-model-manager/api/huggingface/resolve` | Resolve a HuggingFace repo to preview image URLs |
| GET | `/tiny-model-manager/api/huggingface/readme` | Fetch README.md body (YAML front matter stripped) for a HF repo |
| GET | `/tiny-model-manager/api/search/huggingface/files` | List files in a HF repo |
| POST | `/tiny-model-manager/api/download` | Enqueue a download |
| POST | `/tiny-model-manager/api/download/missing` | Resolve one entry of ComfyUI's Missing Models panel (CivitAI → HuggingFace → the workflow's own URL) and enqueue it — body `{filename, directory, url?}`; answers `{task_id, …}`, `{already_installed}` or `{unresolved, search_term}` |
| GET | `/tiny-model-manager/api/download/status` | Get all download task statuses |
| GET | `/tiny-model-manager/api/media/{path}` | Serve a stored preview image/video |
| POST | `/tiny-model-manager/api/catalog/{platform}/{page_id}/media` | Upload JPEG/PNG/WebP/GIF card images for a catalog entry (max 10 MB per file, up to 10 per request); body: `FormData` with repeated `files` field; fills empty `thumbnail_url`; response is the refreshed gallery `{"success": true, "media": […]}` |
| DELETE | `/tiny-model-manager/api/catalog/{platform}/{page_id}/media/{name}` | Remove a user-uploaded card image by filename; only accepts uploads (basename matching `upload-<12-hex>.<ext>`) |
| GET | `/tiny-model-manager/api/settings` | Get current settings |
| PUT | `/tiny-model-manager/api/settings` | Update settings |
| POST | `/tiny-model-manager/api/workflow/insert` | Enqueue a 1-click node insert |
| GET | `/tiny-model-manager/api/workflow/pending` | Pending inserts for the ComfyUI JS extension |
| POST | `/tiny-model-manager/api/workflow/ack` | Mark a pending insert consumed |
| GET | `/tiny-model-manager/api/workflows/search` | Search CivitAI's `Workflows` type — params: `q`, `base_model`, `sort`, `period`, `tags`, `page`, `cursor` |
| POST | `/tiny-model-manager/api/workflows/download` | Download a workflow archive and store every ComfyUI graph inside it |
| GET | `/tiny-model-manager/api/workflows` | List stored workflow entries with their graphs and gallery media |
| DELETE | `/tiny-model-manager/api/workflows/{id}` | Delete a workflow entry, its graphs and its media |
| POST | `/tiny-model-manager/api/workflows/{id}/export` | Copy a stored graph into ComfyUI's user workflows directory |
| GET | `/tiny-model-manager/api/workflows/{id}/file` | Serve a stored graph as raw JSON |
| POST | `/tiny-model-manager/api/workflows/{id}/open` | Queue a stored graph for the JS extension to load onto the canvas |
| GET | `/tiny-model-manager/api/images/search` | Browse CivitAI's image feed — params: `sort`, `period`, `nsfw`, `base_model`, `type`, `username`, `model_id`, `cursor`, `limit` (the API has no free-text query) |
| GET | `/tiny-model-manager/api/images/{id}` | A single image with its generation metadata |
| POST | `/tiny-model-manager/api/images/{id}/recreate` | Rebuild the workflow behind an image and store it |
| POST | `/tiny-model-manager/api/images/resolve-resources` | Match an image's referenced models against the local library |

---

## Workflow Nodes

All nodes are available under the `tiny-model-manager` category in the ComfyUI node menu.

| Node | Inputs | Outputs |
|---|---|---|
| **LoRA Loader (with Trigger Words)** | `model`, `clip`, `lora_name`, `strength_model`, `strength_clip` | `model`, `clip`, `trigger_words` |
| **Checkpoint Loader** | `ckpt_name` | `model`, `clip`, `vae` |
| **VAE Loader** | `vae_name` | `vae` |
| **ControlNet Loader** | `control_net_name` | `control_net` |
| **Embedding Helper** | `embedding_name` | `embedding_ref` (formatted string for prompt use) |
| **Upscale Model Loader** | `model_name` | `upscale_model` |

The dashboard's "+" button on any model card (and the "Add to Workflow" button on the detail page) creates the matching node at the centre of the currently open workflow. When a card covers several installed files, the button opens a picker listing them and inserts the one you choose. Files of a type no loader node exists for do not get the button. ComfyUI's model lists are refreshed first, so a model downloaded after the ComfyUI tab was opened is immediately selectable in the new node's dropdown without reloading the page.

---

## Database Schema

All metadata is stored in `data/models.db` (SQLite). Foreign keys are enforced (`PRAGMA foreign_keys = ON`). Child rows are removed automatically when their parent model row is deleted (`ON DELETE CASCADE`).

```
┌─────────────────────────────────────────────────────┐
│                       models                        │
├──────────────────┬──────────────────────────────────┤
│ id               │ INTEGER  PK AUTOINCREMENT        │
│ filename         │ TEXT     UNIQUE NOT NULL         │  ← relative path from the model type's base dir
│ model_type       │ TEXT                             │  ← checkpoints | loras | vae | …
│ source_platform  │ TEXT                             │  ← "civitai" | "huggingface"
│ source_id        │ TEXT                             │  ← CivitAI version ID or HuggingFace repo
│ description      │ TEXT     DEFAULT ''              │
│ base_model       │ TEXT     NOT NULL DEFAULT ''     │  ← e.g. "SDXL 1.0", "Flux.1 D", "Pony"
│ civitai_model_id │ TEXT                             │  ← CivitAI model page ID (used to build source_url)
│ media_hash       │ TEXT     NOT NULL DEFAULT ''     │  ← deterministic hash used as media subfolder name
│ created_at       │ TEXT     DEFAULT datetime('now') │
└──────────────────┴──────────────────────────────────┘
          │  1
          │
          │  N
          ├──────────────────────────────────────────┐
          │                trigger_words              │
          │  ├───────────────────────────────────────┤
          │  │ id        │ INTEGER  PK AUTOINCREMENT  │
          │  │ model_id  │ INTEGER  FK → models.id   │
          │  │ word      │ TEXT NOT NULL              │
          │  └───────────────────────────────────────┘
          │  N
          │
          ├──────────────────────────────────────────┐
          │                 model_media               │
          │  ├───────────────────────────────────────┤
          │  │ id         │ INTEGER  PK AUTOINCREMENT │
          │  │ model_id   │ INTEGER  FK → models.id  │
          │  │ media_type │ TEXT  ("image" | "video") │
          │  │ local_path │ TEXT  (path within media) │
          │  └───────────────────────────────────────┘
          │  N:M  (via junction table)
          │
          ├──────────────────────────────────────────┐
          │                 model_tags                │
          │  ├───────────────────────────────────────┤
          │  │ model_id  │ INTEGER  FK → models.id   │
          │  │ tag_id    │ INTEGER  FK → tags.id     │
          │  │ PK (model_id, tag_id)                 │
          │  └───────────────────────────────────────┘
          │  N
          │
          └──────────────────────────────────────────┐
                              tags                    │
             ├───────────────────────────────────────┤
             │ id        │ INTEGER  PK AUTOINCREMENT  │
             │ name      │ TEXT UNIQUE NOT NULL       │
             └───────────────────────────────────────┘
```

Workflows downloaded from CivitAI — and workflows recreated from a CivitAI image — live in
their own pair of tables, mirroring the same parent/child split. A CivitAI workflow archive usually contains more than one ComfyUI graph, so
one `workflow_entries` row (the source page, owning the description, tags and gallery media) has
many `workflows` rows:

```
┌─────────────────────────────────────────────────────┐
│                  workflow_entries                   │
├──────────────────┬──────────────────────────────────┤
│ id               │ INTEGER  PK AUTOINCREMENT        │
│ source_platform  │ TEXT     NOT NULL                │  ← "civitai" | "civitai-image"
│ source_page_id   │ TEXT     NOT NULL                │  ← CivitAI model page ID
│ display_name     │ TEXT     NOT NULL DEFAULT ''     │
│ description      │ TEXT     NOT NULL DEFAULT ''     │
│ base_model       │ TEXT     NOT NULL DEFAULT ''     │
│ tags             │ TEXT     NOT NULL DEFAULT ''     │  ← JSON array
│ thumbnail_url    │ TEXT     NOT NULL DEFAULT ''     │
│ media_hash       │ TEXT     NOT NULL DEFAULT ''     │  ← media subfolder, as for models
│ created_at       │ TEXT     DEFAULT datetime('now') │
│ UNIQUE (source_platform, source_page_id)            │
└──────────────────┴──────────────────────────────────┘
          │  1
          │  N
          └──────────────────────────────────────────┐
                            workflows                 │
             ├───────────────────────────────────────┤
             │ id          │ INTEGER PK AUTOINCREMENT │
             │ entry_id    │ INTEGER FK → …entries.id │  ← ON DELETE CASCADE
             │ name        │ TEXT NOT NULL            │  ← graph name inside the archive
             │ local_path  │ TEXT NOT NULL            │  ← relative to data/workflows/
             │ version_id  │ TEXT NOT NULL DEFAULT '' │
             │ version_name│ TEXT NOT NULL DEFAULT '' │
             │ node_count  │ INTEGER NOT NULL DEF. 0  │
             │ UNIQUE (entry_id, local_path)          │  ← re-download upserts
             └───────────────────────────────────────┘
```

Graph files are stored under `data/workflows/<media_hash>/<version_id>/<name>.json`. Exporting a
graph copies it into ComfyUI's own `user/default/workflows/` directory so it shows up in ComfyUI's
native workflow browser.

### Field notes

| Field | Source | Notes |
|---|---|---|
| `source_id` | CivitAI: version ID; HuggingFace: repo path (`user/repo`) | Used to re-fetch metadata |
| `civitai_model_id` | CivitAI version API response (`modelId`) | Combined with `source_platform` to derive `source_url` at read time: `https://civitai.com/models/<id>` |
| `base_model` | CivitAI: `baseModel` field on the version; HuggingFace: blank (user-editable) | Displayed on cards and the detail page; editable in the UI |
| `source_url` | Derived — not stored | Computed by the API from `source_platform` + `source_id`/`civitai_model_id`; HuggingFace: `https://huggingface.co/<source_id>` |

### Migration

The schema is created on first run. Three columns added after the initial release (`base_model`, `civitai_model_id`, `media_hash`) are applied automatically on every startup via `ALTER TABLE … ADD COLUMN` (idempotent — existing columns are silently skipped). Tags were also migrated from the original 1-N layout (column on the `tags` table) to the current m-n layout (`tags` + `model_tags` junction); the migration is self-healing and runs automatically.

---

## Project Structure

```
py/
  config.py                   paths and settings helpers
  db/
    database.py               SQLite schema, migrations, and connection factory
    model_repo.py             async CRUD helpers
    workflow_repo.py          async CRUD helpers for stored workflows
  nodes/
    _utils.py                 shared DB helper (trigger word lookup)
    lora_loader_with_triggers.py
    checkpoint_loader_with_triggers.py
    vae_loader.py
    controlnet_loader.py
    embedding_helper.py
    upscale_model_loader.py
  routes/
    __init__.py               register_routes() wires all sub-routers
    static.py                 SPA serving
    models.py                 model list/delete/move
    download.py               search and download endpoints
    metadata.py               metadata CRUD and media serving
    settings.py               settings CRUD
    workflow.py               in-memory queue for 1-click node insert / graph load
    workflows.py              workflow store: search, download, list, export
  services/
    civitai.py                CivitAI API client
    huggingface.py            HuggingFace API client
    downloader.py             async download queue
    metadata_fetcher.py       post-download metadata and image fetch
    missing_model_resolver.py resolve a workflow's missing model to a download source
    workflow_store.py         workflow archive fetch, graph extraction, export
    providers/
      base.py                 abstract provider interface
      civitai_provider.py     CivitAI metadata fetch implementation
      huggingface_provider.py HuggingFace metadata fetch implementation
frontend/
  src/app/
    pages/
      models/                 installed model browser (grid/list, filter, delete)
      workflows/              browse CivitAI workflows + stored workflow library
      download/               search + paste-a-link download page
      model-detail/           metadata viewer/editor
    services/
      model.ts                ModelService — installed model list & metadata API
      download.ts             DownloadService — download queue & status polling
      civitai.ts              CivitaiService — search, versions, resolve
      huggingface.ts          HuggingFaceService — search, files, readme
      workflow.ts             WorkflowService — 1-click node insert queue
      workflow-store.ts       WorkflowStoreService — workflow search, download, export
      notification.ts         NotificationService — signal-based toast queue
    utils/
      link-detector.ts        parse paste-a-link URLs into typed LinkKind objects
web/                          Angular build output (git-ignored)
data/                         runtime — DB, settings, media (git-ignored)
```
