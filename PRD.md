# Product Requirements Document — ComfyUI Tiny Model Manager

## Overview

ComfyUI Tiny Model Manager is a custom node for ComfyUI that provides a web-based dashboard to browse, download, and manage AI models and LoRAs from CivitAI and HuggingFace. It also exposes ComfyUI workflow nodes that insert models with their documented trigger words.

---

## Goals

- Give users a single UI to discover and download models without leaving ComfyUI
- Store model metadata (description, trigger words, preview images) locally so it is available offline
- Expose workflow nodes that automatically populate trigger words for any downloaded LoRA

---

## Non-Goals

- Model training or fine-tuning
- Workflow management or sharing
- Support for model formats outside of `.safetensors`, `.ckpt`, `.pt`, `.bin`, `.gguf`

---

## Architecture

| Layer | Technology |
|---|---|
| Backend | Python, aiohttp (ComfyUI's built-in server) |
| Database | SQLite via `aiosqlite` |
| HTTP client | `httpx` (async) |
| Frontend | Angular 19+ (standalone components, SCSS) |
| Build output | `web/` directory served at `/tiny-model-manager` |

---

## Features

### F-01 — Custom Node Bootstrap

The extension registers itself into ComfyUI on startup with no manual steps.

**Requirements:**
- `__init__.py` exports `NODE_CLASS_MAPPINGS`, `NODE_DISPLAY_NAME_MAPPINGS`, and `WEB_DIRECTORY`
- Routes are registered into `PromptServer.instance.routes` at import time
- SQLite database schema is created on first run if it does not exist
- `data/` directory (DB + settings + media) is created automatically

---

### F-02 — Standalone Web Dashboard

A dark-themed Angular SPA served at `/tiny-model-manager` inside ComfyUI's web server.

**Requirements:**
- Navigable via top nav bar: Models | Download | Settings
- Angular router handles client-side navigation; all unknown paths fall back to `index.html`
- `base href` set to `/tiny-model-manager/` so Angular assets resolve correctly
- Frontend build output goes directly into `web/` (no subdirectory)

---

### F-03 — Installed Model Browser

Users can view all models currently installed in ComfyUI's model folders.

**Requirements:**
- Lists models grouped by type (checkpoints, loras, embeddings, vae, controlnet, upscale_models, clip, unet, and any other type registered in `folder_paths`)
- Shows filename, file size, and a link to the model detail page
- Each model entry has a Delete button (with confirmation dialog)
- Deletion removes only the model file; metadata in the DB is preserved

**API:**
- `GET /tiny-model-manager/api/models` → `{ type: ModelFile[] }`
- `DELETE /tiny-model-manager/api/models/{type}/{path}` → removes the file from disk

---

### F-04 — Model Search (CivitAI)

Users can search for models on CivitAI and browse version details.

**Requirements:**
- Search by keyword, filterable by model type (checkpoints, loras, embeddings, vae, controlnet)
- Results show model name, type, and creator
- Selecting a result fetches available versions with file size
- Each version has a Download button
- Optional CivitAI API key (stored in settings) is sent as a Bearer token for authenticated requests

**API:**
- `GET /tiny-model-manager/api/search/civitai?q=&type=&page=`
- `GET /tiny-model-manager/api/civitai/versions/{model_id}`

---

### F-05 — Model Search (HuggingFace)

Users can search for models on HuggingFace and browse individual files.

**Requirements:**
- Search by keyword, filtered to `text-to-image` pipeline by default
- Results show model ID and download count
- Selecting a result lists available model files (`.safetensors`, `.ckpt`, `.pt`, `.bin`, `.gguf`)
- Each file has a Download button
- Optional HuggingFace token sent as a Bearer token for gated model access

**API:**
- `GET /tiny-model-manager/api/search/huggingface?q=&type=`
- `GET /tiny-model-manager/api/search/huggingface/files?repo=`

---

### F-06 — Async Download Manager

Files are downloaded in the background with live progress feedback in the UI.

**Requirements:**
- Downloads are queued; each runs one at a time
- Progress (percentage, downloaded/total bytes) is updated as the file streams
- Status values: `queued`, `downloading`, `done`, `error`
- On error the partial file is removed from disk
- The download panel polls `/api/download/status` every 2 seconds and displays progress bars for all active tasks
- Download destination is the first path registered in ComfyUI's `folder_paths` for the selected model type

**API:**
- `POST /tiny-model-manager/api/download` body `{ url, model_type, filename, platform, source_id }`
- `GET /tiny-model-manager/api/download/status`

---

### F-07 — Automatic Metadata Fetch

After a download completes, metadata is fetched from the source platform and stored locally.

**Requirements:**
- For CivitAI: fetches description, trigger words, and up to 5 preview images from the first model version
- For HuggingFace: fetches description, trigger words, and tags from the model card
- Metadata failures are silent and do not affect the downloaded file
- Preview images and videos are saved to `data/media/<model_basename>/`
- Media type is inferred from file extension (`mp4`, `webm`, `mov` → video; everything else → image)

---

### F-08 — SQLite Metadata Storage

All model metadata is persisted in a local SQLite database at `data/models.db`.

**Schema:**

| Table | Columns |
|---|---|
| `models` | id, filename, model_type, source_platform, source_id, description, created_at |
| `trigger_words` | id, model_id (FK), word |
| `model_media` | id, model_id (FK), media_type, local_path |
| `tags` | id, model_id (FK), tag |

**Requirements:**
- `ON CONFLICT DO UPDATE` upsert so re-downloading a model refreshes its metadata
- `ON DELETE CASCADE` so deleting a model record also removes its trigger words and media rows
- Foreign keys enforced via `PRAGMA foreign_keys = ON`

---

### F-09 — Model Detail Page

Users can view and edit metadata for any installed model.

**Requirements:**
- Accessed by clicking a model filename in the Models list
- Shows description (editable textarea), trigger words (editable chip list), and a media gallery
- Trigger words can be added (Enter key or Add button) and removed (× on each chip)
- Save button PUTs updated metadata to the backend
- Media gallery renders images inline and videos with native controls

**API:**
- `GET /tiny-model-manager/api/models/{type}/{path}/metadata`
- `PUT /tiny-model-manager/api/models/{type}/{path}/metadata` body `{ description, trigger_words }`
- `GET /tiny-model-manager/api/media/{path}` — serves files from `data/media/` (path traversal protected)

---

### F-10 — Settings Page

Users can configure API credentials and the media storage directory.

**Requirements:**
- Fields: CivitAI API Key, HuggingFace Token, Media Storage Directory
- Credentials are stored in `data/settings.json`
- GET endpoint masks stored credentials (returns `***` instead of the actual value)
- PUT endpoint only updates a credential if the submitted value is non-empty and not `***`
- Leaving Media Storage Directory blank uses the default path `data/media/`

**API:**
- `GET /tiny-model-manager/api/settings`
- `PUT /tiny-model-manager/api/settings`

---

### F-11 — LoRA Loader with Trigger Words (Workflow Node)

A ComfyUI workflow node that loads a LoRA and outputs its stored trigger words as a string.

**Requirements:**
- Node name: `LoraLoaderWithTriggers`, display name: `LoRA Loader (with Trigger Words)`
- Category: `tiny-model-manager`
- Inputs: `model`, `clip`, `lora_name` (dropdown from installed loras), `strength_model`, `strength_clip`
- Outputs: `model`, `clip`, `trigger_words` (comma-separated string from the DB)
- Falls back to an empty string if the LoRA has no stored metadata

---

### F-12 — Settings in ComfyUI Settings Panel

Move credential/config management out of the standalone dashboard and into ComfyUI's native settings UI.

> **Architecture note:** ComfyUI's settings panel API (`app.registerExtension`) only runs inside ComfyUI's own frontend, which is a separate document from the standalone SPA. This feature introduces a small hand-written ComfyUI JS extension loaded from `WEB_DIRECTORY`.

**Requirements:**
- A ComfyUI JS extension (`app.registerExtension`) registers settings entries under a "Tiny Model Manager" category: CivitAI API Key, HuggingFace Token, Media Storage Directory
- Entries read from and write to the existing backend `GET/PUT /api/settings` (single source of truth: `data/settings.json`); masking rules (`***`) are preserved
- The standalone Angular Settings page and its nav link are removed; the `/settings` route is dropped
- The JS extension file lives outside the Angular build output so it is not overwritten on rebuild (see Directory Structure: `js/`)

---

### F-13 — Enhanced Model View

Upgrade the installed-model browser from a plain table to a richer, card-based view.

**Requirements:**
- Card/grid layout per model showing a preview thumbnail sourced from the model's stored media (first image; placeholder when none)
- Each card shows stored tags and trigger words inline (depends on F-15/F-16 persisting tags)
- Bulk multi-select via per-card checkboxes with a batch Delete selected action (single confirmation dialog covering all selected files)
- Existing grouping-by-type and per-model delete/detail navigation are retained

**API:**
- Reuses `GET /api/models` — extend each `ModelFile` with `metadata` (including `tags`) so cards render without N extra calls

---

### F-14 — Enhanced Download View

Improve search browsing and allow downloading multiple files at once.

**Requirements:**
- Result pagination: "Load more" for CivitAI (cursor-based) and HuggingFace (page-based) instead of a single result page
- Inline preview thumbnails on search result cards before a result is selected
- Batch download: select multiple versions/files and enqueue them in one action; each becomes an independent task in the existing download queue

**API:**
- Reuses existing search endpoints (ensure they surface a preview image URL and a pagination cursor/page token)
- Reuses `POST /api/download` per selected file (batch issued client-side)

---

### F-15 — Import Tags from HuggingFace ✓

Persist tags fetched from HuggingFace and make them visible/editable.

**Requirements:**
- `metadata_fetcher` stores `huggingface.get_model_card()` tags in the new `tags` table (see F-08)
- Tags surface in metadata responses and on the model detail page

---

### F-16 — Import Tags from CivitAI

Persist tags fetched from CivitAI and make them visible/editable, and allow backfilling existing models.

**Requirements:**
- `metadata_fetcher` stores `civitai.get_model_metadata()` tags in the `tags` table (see F-08)
- A Re-fetch metadata action backfills description, trigger words, and tags for an already-installed model from its stored `source_platform` + `source_id`

**API (shared with F-15):**
- Extend `GET/PUT /api/models/{type}/{path}/metadata` to include a `tags` array
- `POST /api/models/{type}/{path}/refetch` → re-pulls metadata from the source platform and upserts

---

### F-17 — Direct Download Link (HuggingFace)

Paste a HuggingFace file URL to download without searching.

**Requirements:**
- Paste-a-link section on the Download page accepts a `https://huggingface.co/<repo>/resolve/<rev>/<file>` URL
- Frontend parses repo, revision, and filename; user picks the target model type; submit calls `POST /api/download` with `platform="huggingface"` and `source_id=<repo>`

---

### F-18 — Direct Download Link (CivitAI)

Paste a CivitAI direct / model-version download URL to download without searching.

**Requirements:**
- Accepts CivitAI download URLs (`.../api/download/models/<versionId>`); parses the version ID
- Resolves filename / model type via existing version metadata; submits to `POST /api/download` with `platform="civitai"` and `source_id=<versionId>`

---

### F-19 — Model Repository Link (HuggingFace)

Paste a HuggingFace repository page URL and pick a file to download.

**Requirements:**
- Accepts `https://huggingface.co/<repo>`; parses repo id
- Calls existing `GET /api/search/huggingface/files?repo=` to list files; user selects file + model type, then downloads

---

### F-20 — Model Link (CivitAI)

Paste a CivitAI model page URL and pick a version to download.

**Requirements:**
- Accepts `https://civitai.com/models/<modelId>...`; parses model id
- Calls existing `GET /api/civitai/versions/{model_id}` to list versions/files; user selects file + model type, then downloads

> F-17–F-20 share one "Paste a link" section on the Download page that auto-detects the link kind (direct file vs repo/model page, CivitAI vs HuggingFace) and routes to the matching flow above.

---

### F-21 — Loader Nodes for Other Model Types

Add ComfyUI workflow loader nodes mirroring `LoraLoaderWithTriggers`, each surfacing stored trigger words.

**Requirements:**
- New nodes in category `tiny-model-manager`, registered in `NODE_CLASS_MAPPINGS`:
  - **Checkpoint Loader (with Trigger Words)** → outputs `MODEL`, `CLIP`, `VAE`, `trigger_words`
  - **VAE Loader** → outputs `VAE` (+ `trigger_words` where applicable)
  - **ControlNet Loader** → outputs `CONTROL_NET` (+ `trigger_words`)
  - **Embedding helper** → outputs the embedding's `trigger_words` string for prompt insertion
  - **Upscale Model Loader** → outputs `UPSCALE_MODEL`
- Each model-name dropdown is populated from `folder_paths.get_filename_list(<type>)`
- Trigger words read from the DB via `model_repo.get_model_by_filename()`; empty string when absent

---

### F-22 — One-Click Add Model to Open Workflow

Insert the matching loader node for a model into the currently open ComfyUI graph from the dashboard.

> **Architecture note:** the dashboard runs in a separate document and cannot touch `app.graph` directly. A backend pending-insert queue bridges the SPA and a ComfyUI JS extension running inside ComfyUI's frontend.

**Requirements:**
- An Add to workflow button on the model list/detail enqueues an insert request on the backend
- A ComfyUI JS extension polls the pending-insert endpoint; on a pending item it calls `LiteGraph.createNode()` for the model-type's loader node, pre-selects the model in the node's dropdown, adds it via `app.graph.add()`, and acknowledges the item
- Maps model type → loader node from F-21 (e.g. `loras` → LoRA loader, `checkpoints` → Checkpoint loader)

**API:**
- `POST /tiny-model-manager/api/workflow/insert` body `{ model_type, filename }` → enqueues a pending insert
- `GET /tiny-model-manager/api/workflow/pending` → returns queued inserts for the JS extension to apply
- `POST /tiny-model-manager/api/workflow/ack` body `{ id }` → marks an insert consumed

---

### F-23 - Save additional parameters and show it in model view

- save download source (huggingface or civitai) in database and show it in model view.
- save model type (sdxl, illustrious, anima, qwen, ...) and in case of lora the model type its for.
- the link to the model page on civitai or huggingface

---

### F-24 - Make search filterable and orderable

#### Filter
- by model type (SDXL, Illustrious, Anima, qwen, z image turbo, flux, chroma and so on)...
- by file format (safetensors, GGUF, ...)

#### Order
- have a look what filters are offered by civitai and huggingface

---

### F-25 - Make model view filterable and orderable

#### Filter
- by model type (SDXL, Illustrious, Anima, qwen, z image turbo, flux, chroma and so on)...
- by file format (safetensors, GGUF, ...)

#### Order
- have a look what filters are offered by civitai and huggingface

---

### F-26 - Download view: Mark models already in library

If a model is already in library we mark it as already downloaded and do not show download option.
This goes for search and for url pasting.

---

### F-27 - save images in hashed folder names

Images should be saved in hashed folder names. The hash can be stored in database.
This way we won't have collisions with models that have the same name.

---

### F-28 - Move download overview to a side-by-side view

Download view should be side-by-side:
- Left side has a list style layout. It shows a thumbnail, the name, the model type (checkpoint, lora, ...), the base model type in case of lora (SDXL, Anima, ...), and a truncated tag list
- The right side shows a detail view, containing a formatted view of the description, the image gallery, the name, the tags, the trigger words, the download button and a link to view the model on the website (huggingface, civitai)
- Clicking on a list item on the left side will open its detail view on the right side.
- By default the detail view of the first result item is opened
- In case of no search results do not show the side-by-side view, instead show a box containing a message explaining that there were no search results.

---

### F-29 - Omit search filter for huggingface

In case of hugging face do not show the search filter for model type.

---

## Data Flow

```
User clicks Download
       │
       ▼
POST /api/download
       │
       ▼
downloader.enqueue()  ──►  asyncio.Queue
                                  │
                                  ▼
                         _run_download()
                           streams file
                                  │
                         file write complete
                                  │
                                  ▼
                    metadata_fetcher.fetch_and_store()
                    ├── civitai/hf API call
                    ├── image download → data/media/
                    └── upsert into SQLite
```

---

## Directory Structure

```
comfyui-tiny-model-manager/
├── __init__.py               # ComfyUI entry point
├── requirements.txt          # aiosqlite, httpx
├── .gitignore
├── py/
│   ├── config.py             # paths, settings load/save
│   ├── db/
│   │   ├── database.py       # schema creation, connection factory
│   │   └── model_repo.py     # async CRUD helpers
│   ├── nodes/
│   │   ├── lora_loader_with_triggers.py
│   │   ├── checkpoint_loader_with_triggers.py
│   │   ├── vae_loader.py
│   │   ├── controlnet_loader.py
│   │   ├── embedding_helper.py
│   │   └── upscale_model_loader.py
│   ├── routes/
│   │   ├── __init__.py       # register_routes() wires all sub-routers
│   │   ├── static.py         # SPA serving + fallback
│   │   ├── models.py         # list + delete models
│   │   ├── download.py       # search + download endpoints
│   │   ├── metadata.py       # metadata CRUD + media serving + re-fetch
│   │   ├── settings.py       # settings CRUD
│   │   └── workflow.py       # pending-insert queue for 1-click add
│   └── services/
│       ├── civitai.py
│       ├── huggingface.py
│       ├── downloader.py
│       └── metadata_fetcher.py
├── frontend/                 # Angular source
│   └── src/app/
│       ├── pages/
│       │   ├── models/
│       │   ├── download/
│       │   ├── model-detail/
│       │   └── settings/
│       └── services/
│           ├── model.ts
│           └── download.ts
├── js/                       # Hand-written ComfyUI JS extension (settings + workflow insert)
│   └── extension.js          # app.registerExtension(...)
├── web/                      # Angular build output (git-ignored)
└── data/                     # Runtime data (git-ignored)
    ├── models.db
    ├── settings.json
    └── media/
```
