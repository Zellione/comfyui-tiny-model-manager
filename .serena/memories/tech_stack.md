# Tech Stack

## Backend
- Python 3.12+ (Linux: comfy-env venv at `../../../comfy-env/`; Windows: `python_embeded`)
- aiohttp (ComfyUI's own server — no standalone server process)
- SQLite via custom `py/db/database.py` (no ORM)
- pytest + pytest-asyncio (`asyncio_mode = "auto"`, `addopts = "--import-mode=importlib"`)
- Ruff (lint + format): `target-version = py313`, `line-length = 100`, rules E/F/I/UP/B; B008 ignored
- Coverage: `fail_under = 88` (lines)

## Frontend
- Angular 21.2 — **zoneless** (no Zone.js; uses signals + `ChangeDetectionStrategy.OnPush`)
- TypeScript ~5.9
- RxJS ~7.8
- ngx-translate 18 (i18n)
- Vitest 4 (unit tests via `ng test`)
- Prettier (formatting)
- angular-eslint 21 + eslint 10 (linting)
- Output: `frontend/` → `web/` (production by default)

## Build
- Frontend: `npx ng build` from `frontend/` directory
- Backend: no build step; changes take effect after ComfyUI restart
- `js/` extension: bundled as ng build asset (configured in `angular.json`)
