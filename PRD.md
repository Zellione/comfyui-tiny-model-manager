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

Feature specifications have been extracted to `specs/`. Each feature is a compact YAML file with
requirements, API endpoints, and cross-feature dependencies.

```
specs/
├── 00_overview.md                      # goals, non-goals, architecture (compact reference)
├── api/
│   ├── models.yaml                     # model, media, workflow, settings endpoints
│   └── download.yaml                   # download, search, civitai endpoints
├── features/
│   ├── f01-bootstrap.yaml
│   ├── f02-dashboard.yaml
│   ├── f03-model-browser.yaml
│   ├── f04-civitai-search.yaml
│   ├── f05-huggingface-search.yaml
│   ├── f06-download-manager.yaml
│   ├── f07-metadata-fetch.yaml
│   ├── f08-sqlite-storage.yaml
│   ├── f09-model-detail.yaml
│   ├── f10-settings.yaml
│   ├── f11-lora-loader.yaml
│   ├── f12-settings-comfyui.yaml
│   ├── f13-enhanced-model-view.yaml
│   ├── f14-enhanced-download-view.yaml
│   ├── f15-huggingface-tags.yaml
│   ├── f16-civitai-tags.yaml
│   ├── f17-hf-direct-link.yaml
│   ├── f18-civitai-direct-link.yaml
│   ├── f19-hf-repo-link.yaml
│   ├── f20-civitai-model-link.yaml
│   ├── f21-loader-nodes.yaml
│   ├── f22-add-to-workflow.yaml
│   ├── f23-base-model.yaml
│   ├── f24-search-filters.yaml
│   ├── f25-library-filters.yaml
│   ├── f26-installed-badge.yaml
│   ├── f27-hashed-media.yaml
│   ├── f28-sidebyside-download.yaml
│   ├── f29-hide-hf-basemodel-filter.yaml
│   ├── f30-hf-model-type.yaml
│   ├── f31-editable-model-type.yaml
│   ├── f32-metadata-fields.yaml
│   ├── f33-model-type-selector.yaml
│   ├── f34-notifications.yaml
│   ├── f35-subfolder-organization.yaml
│   ├── f36-tag-filter-download.yaml
│   └── f37-load-more.yaml
└── data-flow.md                        # async download pipeline diagram
```

To regenerate any feature summary from source:
```bash
../../../comfy-env/bin/python tools/summarise_spec.py F-23 PRD.md
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
├── specs/                    # Feature specifications (compact YAML + overview)
│   ├── 00_overview.md
│   ├── api/
│   └── features/
├── tools/                    # Developer utilities
│   └── summarise_spec.py     # Extract single feature as compact YAML
├── web/                      # Angular build output (git-ignored)
└── data/                     # Runtime data (git-ignored)
    ├── models.db
    ├── settings.json
    └── media/
```
