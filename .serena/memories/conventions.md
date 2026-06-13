# Conventions

## Frontend (Angular)

- **Zoneless**: no Zone.js; use `signal()`, `computed()`, `effect()` — never `ngZone.run()`.
- `ChangeDetectionStrategy.OnPush` on all components.
- Polling observables: `interval() + switchMap(HTTP)` — **always** add `catchError(() => of(fallback))` inside switchMap; errors terminate the stream permanently otherwise.
- Template branching: track search/load failures with a separate signal and add an `@else if (error())` branch; otherwise empty-state branch hides content on error.
- Scrollable flex children: give them their own `max-height` instead of relying on `flex: 1; min-height: 0` inside auto-height containers (collapses to 0).
- New services: mock `activeTasks$` as `of([])` and `completedTasks$` as `EMPTY` when testing components that inject `DownloadService`.
- i18n: ngx-translate — all user-visible strings via translation keys.

## JS Extension (js/)

- `setup()` runs before Vue mounts → use `MutationObserver` on `document.body` for Vue-rendered elements.
- `legacy-topbar-container` stays hidden unless it has non-empty element grandchildren — insert buttons into its **parent** (`legacy?.parentElement`) using `insertBefore`.

## Backend (Python)

- Route handler pattern: register with `aiohttp` router via `add_catalog_routes(app.router)` etc.; handlers are `async def`.
- SQLite access only through `py/db/model_repo.py` and `py/db/keyword_repo.py`.
- `cfg.init(path)` must be called before `init_db()` in any test that touches the DB.
- ComfyUI `INPUT_TYPES` default-arg pattern intentionally violates B008 (ignored in ruff config).
- Ruff quote-style: double; indent: space.

## Security Patterns (SonarQube-compliant)

### S7044 — URL path traversal (SSRF)
- **Only `urllib.parse.quote(value, safe="/")` is recognized** as a sanitizer by SonarQube's taint engine. Custom regex validators alone are NOT sufficient.
- The return value of `quote()` must be **assigned back** (`repo_id = _validate_repo_id(repo_id)`) and then used in URL construction; discarding the return value leaves the original variable tainted.
- Pattern used in `huggingface_provider.py`: `_validate_repo_id()` validates with a strict regex AND returns `urllib.parse.quote(repo_id, safe="/")`.

### S2083 — Filesystem path traversal
- **`os.path.realpath()` is the recognized sanitizer** for path traversal. Using it on a tainted path before passing to `os.makedirs` / `open` / etc. breaks the taint chain.
- **S6549 (filesystem oracle) fires when**: `realpath()` on a tainted value + a security decision (`startswith`, `is_relative_to`) is made on the result. Avoid calling `realpath` on settings-derived (tainted) values when a security check follows.
- Safe approach: validate individual path segment with regex `[A-Za-z0-9_-]{1,128}` (no `.` or `/` possible → no traversal), then return `os.path.realpath(os.path.join(base_dir, validated_segment))` from the helper. No security decision on the result needed.
- Pattern used in `metadata_fetcher.py`: `_media_subdir()` validates `media_hash` with regex, then returns `os.path.realpath(os.path.join(cfg.media_dir(), media_hash))`.

## Testing

- Backend route tests: create `aiohttp.web.Application`, register routes, use `aiohttp_client` fixture + `ext_dir` fixture.
- Frontend unit tests: `TestBed.configureTestingModule` + `vi.fn()` mocks; assert signals via `fixture.componentInstance.signal()`.
- New spec files go beside the file under test (`foo.spec.ts` next to `foo.ts`).

## Git / Commits

- Commits and comments in English.
- Never mention Claude as co-author or use EOF in commit messages.
- Feature branches via `gh issue develop <num> --name <short> --checkout`.
