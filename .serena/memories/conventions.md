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
- **Do NOT use `loading="lazy"` on images that start with `display: none`.** `loading="lazy"` requires the element to have a layout position (viewport proximity) to trigger loading. A `display:none` element has no position, so the browser defers loading forever and the `load` event never fires — images stay permanently hidden even when they would load successfully. Use eager loading (omit `loading="lazy"`) for thumbnails that start hidden.
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
- **Video-only indicator (download search page)**: when `civitaiIsVideoOnly(model)` is true (all items are `type=video` or have video URLs, and there is at least one item), the card thumbnail shows a `▶` play icon (`.video-only-icon` div inside `.row-thumb`) instead of a blank dark placeholder. Pattern: `@else if (civitaiIsVideoOnly(model)) { <div class="video-only-icon">▶</div> }`.
- `civitaiIsVideoOnly()`: `images.length > 0 && images.every((img) => img.type === 'video' || isVideo(img.url))`.

## Catalog page thumbnail fallback (installed models)

- `catalog_entries.thumbnail_url` can contain a stale video path (`.mp4`/`.webm`/`.mov`) if it was stored before the video-skip fix in `_download_catalog_images`.
- `list_catalog_entries()` in `model_repo.py` handles this at read time:
  1. Clears `thumbnail_url` if it ends with a video extension.
  2. If `thumbnail_url` is still empty, queries `model_media` (joined via `models.catalog_entry_id`) for the first `media_type = 'image'` local path and uses that.
- `CatalogEntry` has an `is_video_only?: boolean` field (optional to avoid breaking existing spec fixtures). Set to `true` only when the installed model has video media records but **no** image media records at all.
- Catalog card template: `@else if (entry.is_video_only) { <div class="thumb-video-only">▶</div> }` after the `@if (catalogThumbnailUrl(entry))` block.
- `_download_catalog_images` in `metadata_fetcher.py` always skips video files (`_VIDEO_EXTS = {"mp4", "webm", "mov"}`) and returns the first image path; falls back to poster extraction when all URLs are videos.

## Video poster extraction (`py/video_poster.py`)

- **Location**: `py/video_poster.py` — stdlib-only imports at module level; `av` is imported lazily inside `_extract_with_av`. No circular imports.
- **Public API**: `extract_video_poster(video_path: str) -> str | None`
  - Idempotent: returns existing `<stem>_poster.jpg` immediately if it already exists.
  - Tries `_extract_with_av` first, then `_extract_with_ffmpeg` as fallback.
  - Returns `None` if both fail; caller falls back to the ▶ icon.
  - Run from async code with `await asyncio.to_thread(extract_video_poster, path)`.
- **`_extract_with_av`**: uses the `av` package (PyAV, already in comfy-env, bundles libav — no system ffmpeg needed). Iterates `container.decode(stream)`, calls `frame.to_image()` on the first video frame, saves as JPEG. `av` is imported inside the function so the module stays importable even without it.
- **`_extract_with_ffmpeg`**: subprocess fallback — only runs if `shutil.which("ffmpeg")` finds a system binary. Uses `-vframes 1 -q:v 2`.
- **Where used**:
  - `_download_catalog_images`: poster extraction when all downloaded files are videos; returns poster path instead of `""`.
  - `_download_images`: poster extraction when no image files downloaded; stored via `add_media(model_id, "image", poster)`.
  - `list_catalog_entries()`: lazy extraction for existing video-only entries; stored via `INSERT OR IGNORE INTO model_media` so the next request finds the image record normally.
- **Testing pattern**: mock `py.services.metadata_fetcher.extract_video_poster` (the imported name in the caller) — avoids coupling tests to av/ffmpeg internals. Unit tests for `_extract_with_av` and `_extract_with_ffmpeg` live in `tests/test_video_poster.py`.

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
