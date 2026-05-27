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
- Node name: `TMMLoraLoader`, display name: `LoRA Loader (with Trigger Words)`
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

### F-15 — Import Tags from HuggingFace

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
- Model type is auto-detected from the CivitAI version response (`model.type`) and mapped to the internal type (checkpoints, loras, …); the model type dropdown is pre-filled and disabled (greyed out) since the type is known

**API:**
- `GET /tiny-model-manager/api/civitai/resolve/{version_id}` → `{ filename, model_type, size_kb }`

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

Add ComfyUI workflow loader nodes for all major model types. Only the LoRA loader surfaces trigger words; the remaining loaders expose the raw model outputs only.

**Requirements:**
- New nodes in category `tiny-model-manager`, registered in `NODE_CLASS_MAPPINGS` with `TMM` prefix to avoid conflicts with ComfyUI built-ins:
  - **`TMMCheckpointLoader`** (display: "Checkpoint Loader") → outputs `MODEL`, `CLIP`, `VAE`
  - **`TMMVaeLoader`** (display: "VAE Loader") → outputs `VAE`
  - **`TMMControlNetLoader`** (display: "ControlNet Loader") → outputs `CONTROL_NET`
  - **`TMMEmbeddingHelper`** (display: "Embedding Helper") → outputs `embedding_ref` (STRING formatted as `embedding:<stem>`)
  - **`TMMUpscaleModelLoader`** (display: "Upscale Model Loader") → outputs `UPSCALE_MODEL`
- Each model-name dropdown is populated from `folder_paths.get_filename_list(<type>)`
- Trigger words are **not** exposed on these nodes; only `LoraLoaderWithTriggers` (F-11) retains a trigger_words output

---

### F-22 — One-Click Add Model to Open Workflow

Insert the matching loader node for a model into the currently open ComfyUI graph from the dashboard.

> **Architecture note:** the dashboard runs in a separate document and cannot touch `app.graph` directly. A backend pending-insert queue bridges the SPA and a ComfyUI JS extension running inside ComfyUI's frontend.

**Requirements:**
- An Add to workflow button on the model list/detail enqueues an insert request on the backend
- A ComfyUI JS extension polls the pending-insert endpoint every 500 ms; on a pending item it calls `LiteGraph.createNode()` for the model-type's loader node, pre-selects the model in the node's dropdown, adds it via `app.graph.add()`, and acknowledges the item
- Widget value selection uses `findWidgetOption()` to handle ComfyUI's " (N)" disambiguation suffixes (appended when the same filename exists across multiple model base directories)
- Maps model type → loader node from F-21 (e.g. `loras` → LoRA loader, `checkpoints` → Checkpoint loader)

**API:**
- `POST /tiny-model-manager/api/workflow/insert` body `{ model_type, filename }` → enqueues a pending insert
- `GET /tiny-model-manager/api/workflow/pending` → returns queued inserts for the JS extension to apply
- `POST /tiny-model-manager/api/workflow/ack` body `{ id }` → marks an insert consumed

---

### F-23 — Base Model & Source Metadata

Persist and surface where a model came from and which base model it targets.

**Requirements:**
- New `base_model` column on the `models` table (e.g. `SDXL 1.0`, `Illustrious`, `Pony`,
  `Flux.1 D`, `Qwen`) — extends the F-08 schema
- On download and on re-fetch, `base_model` is auto-populated from CivitAI's version `baseModel`
  field; HuggingFace downloads leave it blank (no reliable source field)
- `base_model` is manually editable from the model detail page (see F-31) so HuggingFace models
  and corrections can be set by hand
- For LoRAs, the base model is the architecture the LoRA is trained for (same field)
- The model detail page and model cards (F-13) show: download source (CivitAI / HuggingFace, from
  `source_platform`), base model, and a clickable link to the model's page on the source platform
- The source page URL is derived from `source_platform` + `source_id` (CivitAI:
  `https://civitai.com/models/<modelId>`, resolved via the version response; HuggingFace:
  `https://huggingface.co/<repo>`)

**API:**
- Extend `GET /api/models` and `GET/PUT /api/models/{type}/{path}/metadata` to include
  `base_model` and a derived `source_url`

---

### F-24 — Search Filtering & Sorting

Add filter and sort controls to the CivitAI and HuggingFace search.

**Requirements:**
- **Filter by base model** (SDXL, Illustrious, Pony, Flux, Qwen, Z Image Turbo, Chroma, …) —
  options populated dynamically from the platform's available values; applied server-side where
  the platform supports it (CivitAI `baseModels` param), hidden for HuggingFace (see F-29)
- **Filter by file format** (`.safetensors`, `.gguf`, `.ckpt`, `.pt`, `.bin`)
- **Sort (CivitAI):** Most Downloaded / Highest Rated / Newest, plus a time period
  (Day / Week / Month / Year / All Time) — maps to CivitAI's `sort` + `period` params
- **Sort (HuggingFace):** Downloads / Likes / Trending / Recently Updated / Recently Created —
  maps to HuggingFace's `sort` (`downloads`, `likes`, `trending`, `lastModified`, `createdAt`)
  + `direction`
- Defaults preserve current behaviour (HuggingFace defaults to downloads, descending)
- Filter and sort changes auto-trigger a new search immediately (no need to press Search again),
  provided at least one explicit search has already been performed
- For HuggingFace, when `.gguf` format is selected the search uses `filter=gguf`
  server-side (replacing the `pipeline_tag` restriction) so that GGUF repositories
  are discoverable

**API:**
- Extend `GET /api/search/civitai` with `base_model`, `format`, `sort`, `period` query params
- Extend `GET /api/search/huggingface` with `sort`, `direction`, `format` query params

---

### F-25 — Library Filtering & Sorting

Add the same filtering and sorting to the installed-model browser.

**Requirements:**
- **Filter by base model** (built dynamically from the distinct `base_model` values present in
  the library), **by file format** (file extension), and **by source platform** (CivitAI /
  HuggingFace / Unknown / all) — "Unknown" covers models installed before the tool was set up
  that have no source record, in addition to the existing grouping-by-type
- An **"Unknown" base model option** in the dropdown shows all models where no base model has
  been set
- **Filter by tags** (multi-select): an input field with autocomplete from tags present in the
  library; each added tag appears as a removable chip; models must carry all active tags
  (AND matching)
- **Sort by** name, file size, date added (`created_at`), or recently modified
- A **"Reset all filters"** button clears every active filter simultaneously; it is always
  visible but disabled when no filters are active
- Applied client-side over the data already returned by `GET /api/models` — no new endpoint

---

### F-26 — Mark Already-Installed Models in Download View

Indicate which search results and pasted links are already in the library and suppress their
download action.

**Requirements:**
- For each search-result file/version, and for resolved paste-a-link targets, compare the target
  filename against installed models; if present, show an "In library" badge and hide/disable the
  Download button
- Applies to CivitAI search, HuggingFace search, and the paste-a-link flows (F-17–F-20)
- Matching is by the resolved filename (the name the file would be saved as on disk)
- The Download button reflects live download state: shows "Downloading…" (disabled) while the task
  is queued or in progress; reverts to "Download" on error (allowing retry); switches to "In library"
  on success without requiring a page reload
- The "In library" indicator is the same size as the Download button (matching padding, font-size,
  and border-radius) so the row layout does not shift between states

**API:**
- Reuses installed-model filenames from `GET /api/models` client-side; no new endpoint
- Reuses the existing download-status poll (`GET /api/download/status`) to drive live button state

---

### F-27 — Hashed Media Folder Names

Store preview media under a hashed folder name instead of the model basename to avoid collisions.

**Requirements:**
- Media is saved to `data/media/<hash>/`, where `<hash>` is derived deterministically (e.g.
  SHA-1 of the filename, or of `source_platform` + `source_id`)
- The hash is stored on the model's row (new `media_hash` column — extends the F-08 schema) so the
  detail page and gallery can locate the media
- Replaces the current `data/media/<model_basename>/` scheme (F-07), preventing collisions between
  different models that share the same display name
- `model_media.local_path` continues to point at the actual stored file (now under the hashed
  folder); the `GET /api/media/{path}` path-traversal guard is retained

---

### F-28 — Side-by-Side Download View

Rework the search-results area into a master–detail layout.

**Requirements:**
- **Left outer pane** — a narrow scrollable list (max-height capped, internal scroll); each row
  shows a thumbnail, the name, the model type (checkpoint, lora, …), the base model (for LoRAs
  and wherever known), and a truncated tag list (≤ 2 tags shown inline)
- **Right outer pane** — a detail view for the selected item, itself split into two inner columns:
  - **Inner left** — image/video gallery (large main view + scrollable thumbnail strip), name,
    tags as chips, trigger words as chips, and formatted description
  - **Inner right** — version + file picker with batch-download checkboxes and a link to the
    model on its source platform
- The detail pane header (title, badges, source link, stats) spans both inner columns
- HuggingFace inner left shows: gallery images sourced from the repo's root image siblings
  (`.jpg`, `.png`, `.webp`, `.gif`) when available, plus tags chips; inner right shows: files
  list (auto-fetched); README description is loaded lazily and displayed full-width below the body
- Tags, trigger words (CivitAI), and description are placed full-width below the two-column body;
  the versions/files column is height-capped to the gallery height (320 px) with internal scroll
- The **image/video gallery** shows a large main view with a scrollable thumbnail strip below;
  clicking a thumbnail promotes it to the main view; video items (`.mp4`, `.webm`, `.mov`)
  render in a `<video controls>` element in the main view and show a play-icon overlay on
  their thumbnail; the thumbnail strip is vertical on the left of the main image
- Clicking a row in the left list opens its detail in the right pane; gallery index resets
- The first result is selected by default (auto-select after every new search)
- **"Load more"** button lives at the bottom of the left list pane
- When no search has been performed, show a centered prompt card with instructions
- When there are no results, the side-by-side view is hidden and replaced by a message box
  explaining that there were no search results
- Works for both CivitAI and HuggingFace result sets
- **Responsive**: outer split stacks at ≤ 768 px (list on top, detail below); inner detail split
  stacks at ≤ 900 px (gallery/info on top, download list below)
- **Modern visual design**: refined hover/selected states, clean typography hierarchy, subtle
  depth on the detail pane

---

### F-29 — Hide Base-Model Filter for HuggingFace

HuggingFace search has no base-model facet, so the filter is not offered there.

**Requirements:**
- The base-model filter control (F-24) is shown for CivitAI and hidden whenever the active search
  platform is HuggingFace
- The remaining controls (keyword, sort, file format) stay available

---

### F-30 — Choose Model Type Before HuggingFace Download

HuggingFace does not expose the target folder type, so the user picks it before downloading.

**Requirements:**
- Before enqueuing a HuggingFace download (a search-result file or a pasted repo link), the user
  selects the target model type (checkpoints, loras, embeddings, vae, controlnet, …)
- The selected type is sent as `model_type` to `POST /api/download` and determines the destination
  folder
- For CivitAI the type is auto-detected from the version response (existing F-18 behaviour) and
  need not be chosen — though F-33 still allows overriding it

---

### F-31 — Editable Model Type (relocates file)

Allow changing a model's folder type from the detail page, moving the file on disk.

**Requirements:**
- The model detail page shows the model type as an editable dropdown (checkpoints, loras,
  embeddings, vae, controlnet, …)
- Changing it moves the model file from its current folder to the first registered `folder_paths`
  directory for the new type
- The `models.model_type` row is updated; trigger words, tags, media (hashed folder, F-27),
  description, and source info are preserved
- The base model (F-23) is editable from the same page

**API:**
- `POST /api/models/{type}/{path}/move` body `{ new_type }` → relocates the file on disk and
  updates the DB row

---

### F-32 — First-Class Metadata Fields (not tags)

Store structured metadata as dedicated fields rather than folding it into the generic tag list.

**Requirements:**
- Base model is stored in its own `models.base_model` column (F-23), never as a tag
- Trigger words remain in the dedicated `trigger_words` table (already the case) and are never
  mixed into `tags`
- The generic `tags` table holds only descriptive tags fetched from the source platform
- Metadata responses expose `base_model`, `trigger_words`, and `tags` as distinct fields

---

### F-33 — Model Type Selectable for Every Model

Let the user pick or override the target folder type for any downloadable model — from search
results and from pasted links alike.

**Requirements:**
- A model-type dropdown is available for every downloadable item: CivitAI search results,
  HuggingFace search results, and all paste-a-link flows (F-17–F-20)
- Where the type is auto-detected (CivitAI), the dropdown is pre-filled with the detected type but
  remains changeable — this relaxes F-18's "pre-filled and disabled (greyed out)" behaviour
- For HuggingFace, selection is required (F-30)
- The chosen type is passed as `model_type` to `POST /api/download`

---

### F-34 — Notification System

Toast notifications surface action outcomes across the dashboard.

**Requirements:**
- Toasts appear at the top-center of the dashboard
- **Green (success)** toasts for: metadata or settings saved, a model added to the workflow
  (F-22), a download enqueued from a link, and a download completing
- **Red (error)** toasts for any failed action (failed save, failed download, API error)
- Toasts auto-dismiss after a few seconds and can be manually dismissed
- A shared Angular notification service is used by all pages; download-completion toasts are raised
  when the download-status poll (F-06) observes a task transitioning to `done` or `error`

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
