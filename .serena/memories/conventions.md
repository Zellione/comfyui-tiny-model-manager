# Conventions

## Frontend (Angular)

- **Zoneless**: no Zone.js; use `signal()`, `computed()`, `effect()` — never `ngZone.run()`.
- `ChangeDetectionStrategy.OnPush` on all components.
- Polling observables: `interval() + switchMap(HTTP)` — **always** add `catchError(() => of(fallback))` inside switchMap; errors terminate the stream permanently otherwise.
- Template branching: track search/load failures with a separate signal and add an `@else if (error())` branch; otherwise empty-state branch hides content on error.
- Scrollable flex children: give them their own `max-height` instead of relying on `flex: 1; min-height: 0` inside auto-height containers (collapses to 0).
- New services: mock `activeTasks$` as `of([])` and `completedTasks$` as `EMPTY` when testing components that inject `DownloadService`.
- When testing components that inject `TagService`, provide `{ provide: TagService, useValue: mockTagService }` where `mockTagService = { searchTags: vi.fn().mockReturnValue(EMPTY) }`.
- i18n: ngx-translate — all user-visible strings via translation keys.

## Image loading pattern (thumbnail cards)

When a card thumbnail's URL may fail to load (CDN auth, NSFW gate, expired URL):
- Start the `<img>` with `style="display: none"` so the browser's broken-image icon never appears.
- Reveal on success: `(load)="onImgLoad($event)"` → `(event.target as HTMLImageElement).style.display = 'block'`.
- `(error)="onImgError($event)"` → `style.display = 'none'` (already hidden, but needed for other img elements in the same template that start visible).
- Gallery / detail-panel images that start visible still rely on `onImgError` to hide on failure.

## Autocomplete / typeahead pattern (TagAutocompleteInput)

- `toObservable(inputSignal).pipe(debounceTime(200), switchMap(...), catchError(() => EMPTY), takeUntilDestroyed())` — keeps stream alive on HTTP errors.
- Click-outside and Escape dismissal via `@HostListener('document:click')` / `@HostListener('document:keydown.escape')` + `inject(ElementRef)` containment check.
- Merge search-result tags (instant, client-side) with DB suggestions (debounced HTTP), deduplicate via `Set`, cap at 5.

## CivitAI media filtering

- CivitAI image objects carry an optional `type` field (`'image'` | `'video'`). Prefer it over URL extension detection.
- To find the first non-video item: `images.find((img) => img.type !== 'video' && !isVideo(img.url))` — `type` check is primary, `isVideo(url)` from `utils/media.ts` is the fallback for items without a `type`.
- CivitAI does **not** provide a separate poster/thumbnail URL for video items — the only URL is the raw `.mp4`. When a static thumbnail is needed, skip videos and fall back to the existing placeholder.
- Videos should remain in the gallery thumbnail strip (they are playable content); the image-first filter applies only to card-level thumbnails.
- **Video-only indicator**: when `civitaiIsVideoOnly(model)` is true (all items are `type=video` or have video URLs, and there is at least one item), the card thumbnail shows a `▶` play icon (`.video-only-icon` div inside `.row-thumb`) instead of a blank dark placeholder. Pattern: `@else if (civitaiIsVideoOnly(model)) { <div class="video-only-icon">▶</div> }`.
- `civitaiIsVideoOnly()`: `images.length > 0 && images.every((img) => img.type === 'video' || isVideo(img.url))`.

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
- The return value of `quote()` must be **assigned back** (`repo_id = _validate_repo_id(repo_id)`) and used in URL construction; discarding the return value leaves the original variable tainted.
- Pattern in `huggingface_provider.py`: `_validate_repo_id()` validates with a strict regex AND returns `urllib.parse.quote(repo_id, safe="/")`.

### S2083 / S6549 — Filesystem path traversal
- **`os.path.realpath()` is the recognized S2083 sanitizer.** Applying it before `os.makedirs` / `open` breaks the taint chain.
- **S6549 fires when** `realpath()` is called on a tainted value AND a security decision (`startswith`, `is_relative_to`) follows. Avoid `realpath`/`Path.resolve()` on settings-derived values when a security check follows.
- Safe pattern: validate the segment with `re.fullmatch(r"[A-Za-z0-9_-]{1,128}", segment)` (no `.` or `/` → no traversal possible), then return `os.path.realpath(os.path.join(base_dir, segment))` — `realpath` satisfies S2083; no security decision needed so S6549 does not fire.
- Pattern in `metadata_fetcher.py`: `_media_subdir()` validates `media_hash` with regex, returns `os.path.realpath(os.path.join(cfg.media_dir(), media_hash))`.

## Testing

- Backend route tests: create `aiohttp.web.Application`, register routes, use `aiohttp_client` fixture + `ext_dir` fixture.
- Frontend unit tests: `TestBed.configureTestingModule` + `vi.fn()` mocks; assert signals via `fixture.componentInstance.signal()`.
- New spec files go beside the file under test (`foo.spec.ts` next to `foo.ts`).

## Git / Commits

- Commits and comments in English.
- Never mention Claude as co-author or use EOF in commit messages.
- Feature branches via `gh issue develop <num> --name <short> --checkout`.

## Workflow Rules

- **Serena memory commits are immediate**: any time a Serena memory file is written or updated, commit it on the current working branch right away — never defer to a later session or a separate PR.
- **Post-PR follow-up changes**: changes made after the main feature commit has been pushed/merged (UI polish, translation fixes, Serena updates, etc.) must go on a new feature branch with their own PR — never accumulated on `main` locally.
