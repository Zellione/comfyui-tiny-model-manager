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
| Frontend | Angular 21.2 (zoneless, standalone components, SCSS) |
| Build output | `web/` directory served at `/tiny-model-manager` |

---

## Features

Feature planning and tracking is managed via the [GitHub project](https://github.com/users/Zellione/projects/1).

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
│       ├── metadata_fetcher.py
│       └── providers/
│           ├── base.py
│           ├── civitai_provider.py
│           └── huggingface_provider.py
├── frontend/                 # Angular source
│   └── src/app/
│       ├── pages/
│       │   ├── models/
│       │   ├── download/
│       │   └── model-detail/
│       ├── services/
│       │   ├── model.ts
│       │   ├── download.ts
│       │   ├── civitai.ts
│       │   ├── huggingface.ts
│       │   └── workflow.ts
│       └── utils/
│           └── link-detector.ts
├── js/                       # Hand-written ComfyUI JS extension (settings + workflow insert)
│   └── extension.js          # app.registerExtension(...)
├── web/                      # Angular build output (git-ignored)
└── data/                     # Runtime data (git-ignored)
    ├── models.db
    ├── settings.json
    └── media/
```
