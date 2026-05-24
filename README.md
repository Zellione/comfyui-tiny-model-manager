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
| F-11 | `LoraLoaderWithTriggers` ComfyUI workflow node — loads a LoRA and outputs its trigger words | Done |
| F-12 | Settings moved into ComfyUI's native settings panel (standalone page removed) | TODO |
| F-13 | Enhanced model view — card/grid + thumbnails, inline tags/triggers, bulk delete | TODO |
| F-14 | Enhanced download view — result pagination, inline previews, batch download | TODO |
| F-15 | Import & store tags from HuggingFace | TODO |
| F-16 | Import & store tags from CivitAI + re-fetch metadata for installed models | TODO |
| F-17 | Paste a direct HuggingFace file download link | TODO |
| F-18 | Paste a direct CivitAI download link | TODO |
| F-19 | Paste a HuggingFace repository link and pick a file | TODO |
| F-20 | Paste a CivitAI model link and pick a version | TODO |
| F-21 | Loader nodes for checkpoints, VAE, ControlNet, embeddings, upscale models | TODO |
| F-22 | One-click insert of a model's loader node into the open workflow | TODO |

---

## API Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/tiny-model-manager` | Serves the Angular SPA |
| GET | `/tiny-model-manager/api/models` | List all installed models by type |
| DELETE | `/tiny-model-manager/api/models/{type}/{path}` | Delete a model file |
| GET | `/tiny-model-manager/api/models/{type}/{path}/metadata` | Get stored metadata (incl. tags) |
| PUT | `/tiny-model-manager/api/models/{type}/{path}/metadata` | Update description, trigger words, tags |
| POST | `/tiny-model-manager/api/models/{type}/{path}/refetch` | Re-fetch metadata/tags from the source (TODO) |
| GET | `/tiny-model-manager/api/search/civitai` | Search CivitAI |
| GET | `/tiny-model-manager/api/civitai/versions/{model_id}` | Get CivitAI model versions |
| GET | `/tiny-model-manager/api/search/huggingface` | Search HuggingFace |
| GET | `/tiny-model-manager/api/search/huggingface/files` | List files in a HF repo |
| POST | `/tiny-model-manager/api/download` | Enqueue a download |
| GET | `/tiny-model-manager/api/download/status` | Get all download task statuses |
| GET | `/tiny-model-manager/api/media/{path}` | Serve a stored preview image/video |
| GET | `/tiny-model-manager/api/settings` | Get current settings |
| PUT | `/tiny-model-manager/api/settings` | Update settings |
| POST | `/tiny-model-manager/api/workflow/insert` | Enqueue a 1-click node insert (TODO) |
| GET | `/tiny-model-manager/api/workflow/pending` | Pending inserts for the ComfyUI JS extension (TODO) |
| POST | `/tiny-model-manager/api/workflow/ack` | Mark a pending insert consumed (TODO) |

---

## Workflow Node

**LoRA Loader (with Trigger Words)** — available under the `tiny-model-manager` category in the ComfyUI node menu.

Inputs: `model`, `clip`, `lora_name`, `strength_model`, `strength_clip`
Outputs: `model`, `clip`, `trigger_words` (comma-separated string)

---

## Project Structure

```
py/
  config.py                   paths and settings helpers
  db/
    database.py               SQLite schema and connection factory
    model_repo.py             async CRUD helpers
  nodes/
    lora_loader_with_triggers.py
  routes/
    static.py                 SPA serving
    models.py                 model list/delete
    download.py               search and download
    metadata.py               metadata CRUD and media serving
    settings.py               settings CRUD
  services/
    civitai.py                CivitAI API client
    huggingface.py            HuggingFace API client
    downloader.py             async download queue
    metadata_fetcher.py       post-download metadata and image fetch
frontend/
  src/app/
    pages/                    Models, Download, ModelDetail, Settings
    services/                 ModelService, DownloadService
web/                          Angular build output
data/                         runtime — DB, settings, media (git-ignored)
```
