# Tech Stack

## Backend
- Python 3.12+ (Linux: comfy-env venv at `../../../comfy-env/`; Windows: `python_embeded`)
- aiohttp (ComfyUI's own server — no standalone server process)
- SQLite via custom `py/db/database.py` (no ORM)
- pytest + pytest-asyncio (`asyncio_mode = "auto"`, `addopts = "--import-mode=importlib"`)
- Ruff (lint + format): `target-version = py313`, `line-length = 100`, rules E/F/I/UP/B; B008 ignored
- Coverage: `fail_under = 88` (lines)

## Frontend
- Angular 22.1 — **zoneless** (no Zone.js; signals). OnPush is the v22 default — components
  declare no `changeDetection` (the recommended lint rule forbids opting out via `Eager`).
- TypeScript ~6.0
- RxJS ~7.8
- ngx-translate 18 (i18n)
- Vitest 4 (unit tests via `ng test`)
- Prettier (formatting)
- angular-eslint 22 + eslint 10 (linting). Since v22 the shareable configs live in the
  `angular-eslint` meta-package (`angular.configs.tsRecommended` / `templateRecommended`);
  the individual `@angular-eslint/eslint-plugin*` packages export only rules —
  `eslint.config.js` was rewritten accordingly.
- Migrations kept v21 behavior: `provideHttpClient(withXhr())` (v22 defaults to fetch) and
  suppressed `nullishCoalescingNotNullable`/`optionalChainNotNullable` extended diagnostics
  in `tsconfig.app.json`.
- All page routes are lazy (`loadComponent`); initial bundle ~120 kB, budget warning 650 kB.
- `@hono/node-server` override still required after v22 (`@modelcontextprotocol/sdk` pins `^1.19.9`).
- Output: `frontend/` → `web/` (production by default)

## Build
- Frontend: `npx ng build` from `frontend/` directory
- Backend: no build step; changes take effect after ComfyUI restart
- `js/` extension: bundled as ng build asset (configured in `angular.json`)

## Serena LSP Configuration (`.serena/project.yml`)
- Languages: `typescript` (first/default), `python`
- `python` uses Pyright, auto-downloaded by Serena via `uvx` — no manual install needed
- `python_jedi` is NOT used (requires `jedi-language-server` in PATH, not installed)
- To apply language config changes, restart the Serena MCP server
