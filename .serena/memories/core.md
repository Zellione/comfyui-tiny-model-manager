# Core — comfyui-tiny-model-manager

ComfyUI custom node: dashboard for managing/downloading models, LORAs, workflows from CivitAI and HuggingFace.

## Source map

```
__init__.py            # ComfyUI entry: registers routes + node mappings, sets WEB_DIRECTORY=./web
py/                    # Python backend
  config.py            # ext_dir initialisation (call cfg.init(path) in tests)
  background.py        # background task runner
  db/
    database.py        # SQLite init (init_db), schema
    model_repo.py      # main persistence layer (includes search_tags)
    keyword_repo.py    # trigger-word persistence
  routes/              # aiohttp route handlers: catalog, download, metadata, models, settings, workflow, notifications, static, tags, _helpers
  services/            # business logic: downloader, metadata_fetcher, model_paths, reconciler, reorganizer, url_guard, backend_notifier
    providers/         # civitai_provider, huggingface_provider (both implement base.py)
  nodes/               # ComfyUI nodes: lora_loader_with_triggers, checkpoint_loader_with_triggers, vae_loader, controlnet_loader, embedding_helper, upscale_model_loader
frontend/              # Angular SPA (builds to ../web/)
  src/app/
    pages/             # download, catalog-detail, model-detail, models, settings
    components/        # shared UI: toast, media-gallery, edit-meta-form, text-diff-field, tag-autocomplete-input, …
    services/          # Angular services: civitai, huggingface, download, model, keywords, settings, notification, installed-files, workflow, tags
js/                    # ComfyUI JS extension (topbar button); bundled into web/ by ng build
tests/                 # pytest integration + unit tests (includes test_routes_tags.py)
conftest.py            # root conftest: installs ComfyUI stubs (server, folder_paths, comfy.sd, comfy.utils) at import time
tests/conftest.py      # ext_dir fixture: tmp_path + init_db; route tests use aiohttp_client + ext_dir
web/                   # compiled frontend output (git-ignored; each worktree has its own)
```

## Invariants

- `web/` is git-ignored → always run `npx ng build` from **main checkout's** `frontend/` before committing UI changes.
- `js/` is bundled as an ng build asset; never deploy it separately.
- ComfyUI stubs (server, folder_paths) must be installed at conftest import time, not inside fixtures.
- Python path: `PYTHONSAFEPATH=1` required (avoids `py` package collision with pytest's internal `py` lib).

See `mem:tech_stack`, `mem:conventions`, `mem:suggested_commands`, `mem:task_completion` for details.
