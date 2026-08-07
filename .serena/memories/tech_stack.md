# Tech Stack

## Backend
- **Python 3.10+** — `requires-python = ">=3.10"` in `pyproject.toml`, proven by a CI matrix over
  3.10/3.11/3.12/3.13. An audit found no syntax above builtin generics (`list[str]`, 3.9+): no PEP 604
  unions, `match`, `tomllib`, `TaskGroup`, `StrEnum` or `typing.Optional`, and all four runtime deps
  support 3.9+. 3.10 is a deliberate safety margin, not the hard floor.
  (Dev environments: Linux comfy-env venv at `../../../comfy-env/`; Windows `python_embeded`.)
- aiohttp (ComfyUI's own server — no standalone server process)
- SQLite via custom `py/db/database.py` (no ORM)
- pytest + pytest-asyncio (`asyncio_mode = "auto"`, `addopts = "--import-mode=importlib"`)
- Ruff (lint + format): `target-version = py310`, `line-length = 100`, rules E/F/I/UP/B/A/C4/RUF;
  B008 ignored. Documented noqas: RUF001 on the CivitAI size regex (real multiplication sign),
  A002 on the HF provider's public `format` keyword arg.
  **`target-version` must track `requires-python`** — at a higher target the `UP` rules rewrite
  code into syntax the declared floor cannot parse. `tests/test_packaging.py` asserts they agree.
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

## Packaging / distribution (Comfy Registry)

The node is published to the Comfy Registry as **`tiny-model-manager`** (publisher `Zellione`),
so it installs from inside ComfyUI with no toolchain on the user's machine.

- `pyproject.toml` carries `[project]` (name, version, description, `license = { file = "LICENSE" }`,
  `requires-python`, `dependencies`, classifiers), `[project.urls]`, and `[tool.comfy]`
  (`PublisherId`, `DisplayName`, `Icon` → raw GitHub URL of `assets/icon.svg`).
  **`PublisherId` is the lowercase Registry handle `zellione`, not the display name `Zellione`** —
  `https://api.comfy.org/publishers/Zellione` 404s while `/publishers/zellione` returns 200. The
  publish action validates the token against this field, so a miscased value fails with the
  misleading `400 {"message":"Failed to validate token"}` rather than a publisher-not-found error.
  `requires-comfyui` is **deliberately omitted** — a guessed lower bound blocks installs for no gain.
- **`web/` is tracked in git** (it left `.gitignore`). The Registry archives only git-tracked files,
  and a prebuilt bundle is 892 KB versus needing Node 22 + a ~500 MB `npm ci` at install time.
  `.gitattributes` marks `web/**` as `linguist-generated` so diffs collapse.
- `install.py` is a ComfyUI-Manager post-install hook and a **fallback only**: no-op when `web/`
  exists, builds when `frontend/` and Node are both present, otherwise prints a README pointer.
  It **always exits 0** — a non-zero exit makes Manager report the whole install as failed.
- `.comfyignore` (gitignore syntax) strips `tests/`, `frontend/`, `docs/`, agent config, and CI
  files from the published archive.
- **Both `requirements.txt` and `[project] dependencies` are kept.** Manager's git-URL path reads
  the former, the Registry reads the latter; `tests/test_packaging.py` fails the build on drift.
- LICENSE: MIT.

## Serena LSP Configuration (`.serena/project.yml`)
- Languages: `typescript` (first/default), `python`
- `python` uses Pyright, auto-downloaded by Serena via `uvx` — no manual install needed
- `python_jedi` is NOT used (requires `jedi-language-server` in PATH, not installed)
- To apply language config changes, restart the Serena MCP server
