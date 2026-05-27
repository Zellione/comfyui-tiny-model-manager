# ComfyUI Tiny Model Manager

A ComfyUI custom node providing a web dashboard to browse, download, and manage AI models and LoRAs from CivitAI and HuggingFace.

## Getting Started

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

---

## Features

| # | Feature | Status |
|---|---|---|
| F-01 | Custom node bootstrap — auto-registers routes and creates DB on startup | Done |
| F-02 | Standalone web dashboard at `/tiny-model-manager` (Angular SPA, dark theme) | Done |
| F-03 | Installed model browser — list, filter by type, delete | Done |
| F-04 | CivitAI search — keyword + type filter, version picker, download | Done |
| F-05 | HuggingFace search — keyword search, file picker, download | Done |
| F-06 | Async download manager — queue, live progress bars, error handling | Done |
| F-07 | Automatic metadata fetch — description, trigger words, preview images/videos saved after download | Done |
| F-08 | SQLite metadata storage — models, trigger words, media paths persisted in `data/models.db` | Done |
| F-09 | Model detail page — view/edit description, trigger word chips, media gallery | Done |
| F-10 | Settings page — CivitAI API key, HuggingFace token, custom media directory | Done |
| F-11 | `TMMLoraLoader` ComfyUI workflow node — loads a LoRA and outputs its trigger words | Done |
| F-12 | Settings moved into ComfyUI's native settings panel (standalone page removed) | Done |
| F-13 | Enhanced model view — card/grid + thumbnails, inline tags/triggers, bulk delete | Done |
| F-14 | Enhanced download view — result pagination, inline previews, batch download | Done |
| F-15 | Import & store tags from HuggingFace | Done |
| F-16 | Import & store tags from CivitAI + re-fetch metadata for installed models | Done |
| F-17 | Paste a direct HuggingFace file download link | Done |
| F-18 | Paste a direct CivitAI download link | Done |
| F-19 | Paste a HuggingFace repository link and pick a file | Done |
| F-20 | Paste a CivitAI model link and pick a version | Done |
| F-21 | Loader nodes for checkpoints, VAE, ControlNet, embeddings, upscale models | Done |
| F-22 | One-click insert of a model's loader node into the open workflow | Done |
| F-23 | Base model & source metadata — store base model (SDXL, Flux, …), source link; show on cards and detail page | Done |
| F-24 | Search filtering & sorting — filter by base model and file format; sort by downloads, rating, date (per platform); auto-applies on change; GGUF repos discoverable via HF `filter=gguf` | Done |
| F-25 | Library filtering & sorting — filter by base model, source, format, and tags; sort by name, size, or date | Done |
| F-26 | Mark already-installed models in download view — live button states: "Downloading…" while in progress, "In library" on success, retry on error | Done |
| F-27 | Hashed media folder names — store preview images under a deterministic hash to avoid basename collisions | Done |
| F-28 | Side-by-Side Download View — master–detail layout, vertical gallery with thumbnail strip, batch-download checkboxes, HuggingFace gallery + README description, responsive | Done |
| F-29 | Hide base-model filter for HuggingFace — filter not available on HF, so omit it | TODO |
| F-30 | Choose model type before HuggingFace download — user selects folder type since HF cannot auto-detect it | TODO |
| F-31 | Editable model type — change folder type in detail page, moves file on disk | TODO |
| F-32 | First-class metadata fields — base model stored as its own column, never as a tag | TODO |
| F-33 | Model type selectable for every model — override folder type for any download, including CivitAI auto-detected | TODO |
| F-34 | Notification system — green/red toast popups for save, download, workflow-insert, and error events | TODO |
| F-35 | Automatic subfolder organization by base model — toggle to store/reorganize models into `<type>/<base_model>/` subfolders (`Unknown` when none) | TODO |
| F-36 | Filter download search results by tags — server-side tag query (HuggingFace AND-multi, CivitAI single tag) | TODO |
| F-37 | Always-visible "Load more" with empty/error states — button below the list, red + disabled with the failure reason | TODO |

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

The dashboard's "+" button on any model card (and the "Add to Workflow" button on the detail page) creates the matching node at the centre of the currently open workflow.

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
          │  │ local_path │ TEXT  (abs path on disk)  │
          │  └───────────────────────────────────────┘
          │  N
          │
          └──────────────────────────────────────────┐
                             tags                     │
             ├───────────────────────────────────────┤
             │ id        │ INTEGER  PK AUTOINCREMENT  │
             │ model_id  │ INTEGER  FK → models.id   │
             │ tag       │ TEXT NOT NULL              │
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

The schema is created on first run. Two columns added after the initial release (`base_model`, `civitai_model_id`) are applied automatically on every startup via `ALTER TABLE … ADD COLUMN` (idempotent — existing columns are silently skipped).

---

## Project Structure

```
py/
  config.py                   paths and settings helpers
  db/
    database.py               SQLite schema and connection factory
    model_repo.py             async CRUD helpers
  nodes/
    _utils.py                 shared DB helper (trigger word lookup)
    lora_loader_with_triggers.py
    checkpoint_loader_with_triggers.py
    vae_loader_with_triggers.py
    controlnet_loader_with_triggers.py
    embedding_helper.py
    upscale_model_loader.py
  routes/
    static.py                 SPA serving
    models.py                 model list/delete
    download.py               search and download
    metadata.py               metadata CRUD and media serving
    settings.py               settings CRUD
    workflow.py               in-memory queue for 1-click node insert
  services/
    civitai.py                CivitAI API client
    huggingface.py            HuggingFace API client
    downloader.py             async download queue
    metadata_fetcher.py       post-download metadata and image fetch
frontend/
  src/app/
    pages/                    Models, Download, ModelDetail
    services/                 ModelService, DownloadService, WorkflowService
web/                          Angular build output
data/                         runtime — DB, settings, media (git-ignored)
```
