# Overview

ComfyUI Tiny Model Manager is a custom node for ComfyUI that provides a web-based dashboard to browse, download, and manage AI models and LoRAs from CivitAI and HuggingFace. It also exposes ComfyUI workflow nodes that insert models with their documented trigger words.

## Goals

- Give users a single UI to discover and download models without leaving ComfyUI
- Store model metadata (description, trigger words, preview images) locally so it is available offline
- Expose workflow nodes that automatically populate trigger words for any downloaded LoRA

## Non-Goals

- Model training or fine-tuning
- Workflow management or sharing
- Support for model formats outside of `.safetensors`, `.ckpt`, `.pt`, `.bin`, `.gguf`

## Architecture

| Layer | Technology |
|---|---|
| Backend | Python, aiohttp (ComfyUI's built-in server) |
| Database | SQLite via `aiosqlite` |
| HTTP client | `httpx` (async) |
| Frontend | Angular 21.2 (zoneless, standalone components, SCSS) |
| Build output | `web/` directory served at `/tiny-model-manager` |
