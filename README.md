# ComfyUI Tiny Model Manager

A ComfyUI custom node providing a web dashboard to browse, download, and manage AI models and LoRAs from CivitAI and HuggingFace.

## Getting Started

### Windows

1. Install Python dependencies:
   ```
   ..\..\..\python_embeded\python.exe -m pip install -r requirements.txt
   ```
2. Build the frontend (requires Node.js):
   ```
   cd frontend
   npm install
   npx ng build
   ```
3. Restart ComfyUI and open `http://localhost:8188/tiny-model-manager`

### Linux

Assumes ComfyUI was installed via [comfy-cli](https://comfyui-wiki.com/en/install/install-comfyui/install-comfyui-on-linux) with a venv at `../../../comfy-env` relative to this folder.

1. Install Python dependencies:
   ```bash
   source ../../../comfy-env/bin/activate
   pip install -r requirements.txt
   pip install -r requirements-dev.txt
   ```
2. Build the frontend (requires Node.js):
   ```bash
   cd frontend
   npm install
   npx ng build
   ```
3. Start ComfyUI and open `http://localhost:8188/tiny-model-manager`:
   ```bash
   comfy launch
   ```

---

## Developer Setup

After cloning, activate the git hooks once per clone so the pre-push coverage gate runs automatically:

```bash
git config core.hooksPath .githooks
```

The hook at `.githooks/pre-push` runs before every `git push` and enforces minimum coverage thresholds:

- **Backend** ≥ 88 % lines (`pytest --cov=py`, threshold set in `pyproject.toml`)
- **Frontend** ≥ 74 % lines / ≥ 62 % functions / ≥ 74 % branches (thresholds in `angular.json`)

The push is blocked if either threshold is not met.

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
| GET | `/tiny-model-manager/api/search/civitai` | Search CivitAI — params: `q`, `type`, `base_model`, `sort`, `period`, `page`, `cursor` |
| GET | `/tiny-model-manager/api/civitai/versions/{model_id}` | Get CivitAI model versions |
| GET | `/tiny-model-manager/api/civitai/resolve/{version_id}` | Resolve a CivitAI direct download URL to filename + model type |
| GET | `/tiny-model-manager/api/search/huggingface` | Search HuggingFace — params: `q`, `type`, `sort`, `direction`, `format`, `p` |
| GET | `/tiny-model-manager/api/huggingface/resolve` | Resolve a HuggingFace repo to preview image URLs |
| GET | `/tiny-model-manager/api/huggingface/readme` | Fetch README.md body (YAML front matter stripped) for a HF repo |
| GET | `/tiny-model-manager/api/search/huggingface/files` | List files in a HF repo |
| POST | `/tiny-model-manager/api/download` | Enqueue a download |
| GET | `/tiny-model-manager/api/download/status` | Get all download task statuses |
| GET | `/tiny-model-manager/api/media/{path}` | Serve a stored preview image/video |
| GET | `/tiny-model-manager/api/settings` | Get current settings |
| PUT | `/tiny-model-manager/api/settings` | Update settings |
| POST | `/tiny-model-manager/api/workflow/insert` | Enqueue a 1-click node insert |
| GET | `/tiny-model-manager/api/workflow/pending` | Pending inserts for the ComfyUI JS extension |
| POST | `/tiny-model-manager/api/workflow/ack` | Mark a pending insert consumed |

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

The dashboard's "+" button on any model card (and the "Add to Workflow" button on the detail page) creates the matching node at the centre of the currently open workflow. ComfyUI's model lists are refreshed first, so a model downloaded after the ComfyUI tab was opened is immediately selectable in the new node's dropdown without reloading the page.

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
    workflow.py               in-memory queue for 1-click node insert
  services/
    civitai.py                CivitAI API client
    huggingface.py            HuggingFace API client
    downloader.py             async download queue
    metadata_fetcher.py       post-download metadata and image fetch
    providers/
      base.py                 abstract provider interface
      civitai_provider.py     CivitAI metadata fetch implementation
      huggingface_provider.py HuggingFace metadata fetch implementation
frontend/
  src/app/
    pages/
      models/                 installed model browser (grid/list, filter, delete)
      download/               search + paste-a-link download page
      model-detail/           metadata viewer/editor
    services/
      model.ts                ModelService — installed model list & metadata API
      download.ts             DownloadService — download queue & status polling
      civitai.ts              CivitaiService — search, versions, resolve
      huggingface.ts          HuggingFaceService — search, files, readme
      workflow.ts             WorkflowService — 1-click node insert queue
      notification.ts         NotificationService — signal-based toast queue
    utils/
      link-detector.ts        parse paste-a-link URLs into typed LinkKind objects
web/                          Angular build output (git-ignored)
data/                         runtime — DB, settings, media (git-ignored)
```
