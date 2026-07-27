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
- **Form-control labeling (SonarQube `Web:InputWithoutLabelCheck`, a RELIABILITY bug)**: every `<input>` (except submit/button/image/hidden), `<select>` and `<textarea>` must have an associated label. Preferred fix is `[attr.aria-label]=\"'<key>' | translate\"` (no layout change); reuse the placeholder/header translation key where one exists, or bind a meaningful value (e.g. `[attr.aria-label]=\"f.name\"` for per-file checkboxes). Inputs wrapped in a `<label>…</label>` (implicit label) are already compliant.

## Hash-lookup UX pattern (F-90)

When a registration/edit form needs an async pre-fill from an external API (e.g. CivitAI hash lookup):

**Component signals:**
```typescript
// In RegisterForm interface:
hashStatus: 'loading' | 'found' | 'not_found' | 'error';
name: string;

// Private signals on the component:
private registerFileHash = signal<string>('');
private registerCivitaiIds = signal<{ source_id: string; civitai_model_id: string } | null>(null);
```

**openRegisterForm:** set `hashStatus: 'loading'`, then call `_runHashLookup(filename, modelType)`.

**`_runHashLookup`:** subscribes to `modelService.hashLookup()` (one-shot observable, no takeUntilDestroyed needed); on match sets `hashStatus: 'found'` and pre-fills form fields + stores hash/IDs; on no-match sets `hashStatus: 'not_found'`; error handler sets `hashStatus: 'error'`.

**`retryHashLookup`:** public method; resets `hashStatus: 'loading'`, clears error state, re-calls `_runHashLookup` from `registerFormFile()`.

**Template states (use `@if` / `@else if` / `@else`):**
- `loading`: spinner div + `| translate` key; all form inputs `[disabled]="registerForm().hashStatus === 'loading'"`; **submit button** also `[disabled]="registerForm().saving || registerForm().hashStatus === 'loading'"`
- `found`: green badge with interpolated model name (`| translate: { name: registerForm().name }`)
- `not_found`: neutral note
- `error`: red message + `<button (click)="retryHashLookup()">` with Retry label

**submitRegister:** include `file_hash`, `source_platform: 'civitai'`, `source_id`, `civitai_model_id` when `registerFileHash()` is truthy.

**Tests:** use `new Subject<HashLookupResult>()` (never resolves) to test loading state; set default `mockModelService.hashLookup.mockReturnValue(of({ hash: '', match: false, metadata: null }))` in `beforeEach` so existing tests aren't broken.

## Angular service HTTP pattern

All `ModelService` (and other services) methods that call the backend **must** wrap with the typed response and extract `.data`:
```typescript
// CORRECT
getUnregistered(): Observable<Record<string, UnregisteredFile[]>> {
  return this.http
    .get<{ success: boolean; data: Record<string, UnregisteredFile[]> }>(`${API}/models/unregistered`)
    .pipe(map((r) => r.data));
}

// WRONG — missing wrapper and map
getUnregistered(): Observable<Record<string, UnregisteredFile[]>> {
  return this.http.get<Record<string, UnregisteredFile[]>>(`${API}/models/unregistered`);
}
```
The backend always returns `{"success": true, "data": ...}` (via `ok()` helper) or `{"success": false, "error": "..."}` (via `err()` helper).

## Backend error format and frontend error field access

The backend `err(message, status)` helper returns `{"success": false, "error": message}`.

When Angular `HttpClient` receives a non-2xx response, the body lands at `httpError.error`. So to check for a specific backend error string in a component:
```typescript
// CORRECT — backend sends {"error": "file_not_found"}
err?.error?.error === 'file_not_found'

// WRONG — "detail" is not a field in the backend error response
err?.error?.detail === 'file_not_found'
```

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
- `CatalogEntry` has `is_video_only?: boolean` and `first_video_path?: string` fields (both optional to avoid breaking existing spec fixtures):
  - `is_video_only = true` when installed model has video media records but **no** image media at all.
  - `first_video_path` is set (alongside `is_video_only = true`) when lazy poster extraction in `list_catalog_entries()` fails — the frontend uses it to request the poster on-demand via `/api/media-poster/`.
  - If lazy extraction **succeeds**, `thumbnail_url` is set to the poster path and `is_video_only = false`; `first_video_path` is not included.
- **Catalog card template** (in `models.html`):
  ```
  @if (catalogThumbnailUrl(entry)) {
    <img class="thumb" ... />
  } @else if (entry.is_video_only && entry.first_video_path) {
    <div class="thumb-video-only">▶</div>
    <img class="thumb" [src]="videoPosterUrl(entry.first_video_path)" style="display: none"
         (load)="onVideoPosterLoad($event)" (error)="onImgError($event)" />
  } @else if (entry.is_video_only) {
    <div class="thumb-video-only">▶</div>
  }
  ```
  The ▶ div comes **before** the img so `previousElementSibling` works in `onVideoPosterLoad`.
- `videoPosterUrl()` and `onVideoPosterLoad()` are defined on the `Models` component (same implementation as `MediaGallery`).
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
  - `_serve_video_poster` route: on-demand extraction for any video in media_dir (see below).
- **Testing pattern**: mock `py.services.metadata_fetcher.extract_video_poster` (the imported name in the caller) — avoids coupling tests to av/ffmpeg internals. Unit tests for `_extract_with_av` and `_extract_with_ffmpeg` live in `tests/test_video_poster.py`.
- **Fallback**: when ffmpeg is unavailable or extraction fails, the ▶ play icon is shown (frontend `is_video_only` branch).

## On-demand video poster route (`GET /api/media-poster/{path}`)

- **Route**: `GET /tiny-model-manager/api/media-poster/{path:.*}` in `py/routes/metadata.py` — handled by `_serve_video_poster`.
- **Purpose**: lazily extract and serve the first video frame as a JPEG poster for **any** video inside `media_dir`, including models that have both video and image media (where pre-extraction in `_download_images` is skipped because `has_image` is true).
- **Flow**: validate path is within `media_dir()` via `contained_path()` → 403 on escape; 404 if file missing on disk; `asyncio.to_thread(extract_video_poster, full_path)` → 404 if extraction returns `None`; `web.FileResponse(poster)` on success.
- **Caching**: `extract_video_poster` saves the poster as `<stem>_poster.jpg` beside the video on first call and returns it immediately on subsequent calls — no re-extraction.
- **`extract_video_poster` is imported at module level** in `metadata.py` (unlike other cfg/service lazy imports) so the name is patchable in tests via `patch("py.routes.metadata.extract_video_poster", ...)`.
- **Frontend `videoPosterUrl(localPath)`**: returns `/tiny-model-manager/api/media-poster/${encodeURIComponent(localPath)}` — implemented on both `MediaGallery` and the `Models` page component. **Do NOT** derive the poster path by convention (`<stem>_poster.jpg`) on the frontend; the route handles extraction on demand.
- **Tests**: `TestServeVideoPoster` in `tests/test_routes_metadata.py` — 4 tests covering success (extraction succeeds), extraction failure (→ 404), missing file (→ 404), and path traversal (→ 403/404).

## Video gallery thumbnail poster pattern (`MediaGallery` and catalog cards)

- `videoPosterUrl(localPath: string)` → `/tiny-model-manager/api/media-poster/${encodeURIComponent(localPath)}`. Defined on `MediaGallery` and `Models` page component (same implementation).
- **▶ + poster img pattern** (used in both gallery thumbnail strip and catalog cards):
  - Render `▶` div first (visible by default), then an `<img style="display: none">` pointing at the poster URL.
  - `(load)="onVideoPosterLoad($event)"`: shows the img (`display: block`) and hides the preceding sibling via `img.previousElementSibling.style.display = 'none'`.
  - `(error)="onImgError($event)"`: keeps img hidden; ▶ stays visible.
  - The ▶ div **must come before** the img in the DOM — `onVideoPosterLoad` relies on `previousElementSibling`.
- **Main panel video in MediaGallery**: `[poster]="videoPosterUrl(m.local_path)"` on the `<video>` element — native HTML5 poster, no JS needed.
- **Catalog cards**: wrap is not needed (unlike `.gallery-thumb-video-wrap`); ▶ div and img are siblings inside `.thumb-link`. The `img` uses `class="thumb"` (same as normal thumbnails) so it fills the card slot.

## Cognitive complexity (SonarQube S3776)

- SonarQube enforces a max cognitive complexity of **15** per function (rule `python:S3776`).
- When a Python async function exceeds 15, extract private helper coroutines (`async def _helper(db, e: dict) -> None`) that each own a single responsibility. The caller becomes a thin orchestrator.
- **Pattern used in `model_repo.py`** (`list_catalog_entries`): extracted `_fill_thumbnail`, `_fill_model_type`, `_fill_video_status` — each is `async`, accepts `db` and the mutable entry dict `e`, mutates `e` in place, returns `None`.
- Module-level constants shared by helpers (e.g. `_VIDEO_PATH_EXTS`) go alongside the other `_UPPER_CASE` constants at the top of the file.
- Private helpers are not tested directly; coverage comes from route/integration tests that exercise the public function.

## JS Extension (js/)

- `setup()` runs before Vue mounts → use `MutationObserver` on `document.body` for Vue-rendered elements.
- `legacy-topbar-container` stays hidden unless it has non-empty element grandchildren — insert buttons into its **parent** (`legacy?.parentElement`) using `insertBefore`.

## Backend (Python)

- Route handler pattern: register with `aiohttp` router via `add_catalog_routes(app.router)` etc.; handlers are `async def`.
- SQLite access only through `py/db/model_repo.py` and `py/db/keyword_repo.py`.
- `cfg.init(path)` must be called before `init_db()` in any test that touches the DB.
- ComfyUI `INPUT_TYPES` default-arg pattern intentionally violates B008 (ignored in ruff config).
- Ruff quote-style: double; indent: space.
- **`asyncio.to_thread` for sync IO**: synchronous file operations (e.g. `compute_file_hash`) must be called via `await asyncio.to_thread(fn, arg)` inside async route handlers to avoid blocking the event loop.
- **Monkeypatch wrapper for external HTTP calls and sync IO**: wrap CivitAI/HuggingFace calls AND `asyncio.to_thread` calls in dedicated module-level `async def _xxx()` functions (e.g. `_civitai_lookup`, `_hash_file` in `models.py`) so tests can monkeypatch the module-level name. **NEVER patch `asyncio.to_thread` directly** — it modifies the global `asyncio` module object, corrupting the `pytest-asyncio` event loop in CI and causing the entire test run to hang indefinitely. Pattern:
  ```python
  # In models.py — patchable wrapper around asyncio.to_thread
  async def _hash_file(path: str) -> str:
      return await asyncio.to_thread(model_paths.compute_file_hash, path)

  # In tests — patch the wrapper, not asyncio.to_thread
  monkeypatch.setattr("py.routes.models._hash_file", lambda path: _async_return("deadbeef"))
  ```
  The lambda for `_hash_file` takes `path: str`; the lambda for `_civitai_lookup` takes `sha256: str`.

## Security Patterns (SonarQube-compliant)

### S7044 — URL path traversal (SSRF)
- **For string parameters**: `urllib.parse.quote(value, safe="/")` is recognized as a sanitizer by SonarQube's taint engine. Custom regex validators alone are NOT sufficient. The return value of `quote()` must be **assigned back** and used in URL construction.
- **For integer parameters**: assign `safe_id = int(model_id)` before using in the f-string; the explicit `int()` cast breaks the taint chain. Example in `civitai_provider.py::get_model_versions`:
  ```python
  safe_id = int(model_id)
  resp = await client.get(f"{_BASE}/models/{safe_id}", ...)
  ```
- Pattern in `huggingface_provider.py`: `validate_repo_id()` validates with a strict regex AND returns `urllib.parse.quote(repo_id, safe="/")`.

### S2083 / S6549 — Filesystem path traversal
- **`os.path.realpath()` is the recognized S2083 sanitizer.** Applying it before `os.makedirs` / `open` breaks the taint chain.
- **S6549 fires when** `realpath()` is called on a tainted value AND a security decision (`startswith`, `is_relative_to`) follows. Avoid `realpath`/`Path.resolve()` on settings-derived values when a security check follows.
- Safe pattern: validate the segment with `re.fullmatch(r"[A-Za-z0-9_-]{1,128}", segment)` (no `.` or `/` → no traversal possible), then return `os.path.realpath(os.path.join(base_dir, segment))` — `realpath` satisfies S2083; no security decision needed so S6549 does not fire.
- Pattern in `metadata_fetcher.py`: `_media_subdir()` validates `media_hash` with regex, then resolves `base = os.path.realpath(cfg.media_dir())` and `resolved = os.path.realpath(os.path.join(base, media_hash))`, and raises `ValueError` unless `resolved == base or resolved.startswith(base + os.sep)` (defense-in-depth containment). The realpath+`startswith` containment pattern is also used in `_migrate_model_media` and has **not** triggered S6549 in practice (the regex already untaints the segment), so it is safe to enforce the boundary explicitly here.
- Two historical `pythonsecurity:S2083` BLOCKERs on the `os.makedirs` sinks fed by `_media_subdir()` (lines ~261/349) were stale taint false positives — the path is fully validated — and are marked **False Positive** in SonarQube. If they reappear after a re-scan, re-mark rather than mutating the already-safe code.

## Testing

- Backend route tests: create `aiohttp.web.Application`, register routes, use `aiohttp_client` fixture + `ext_dir` fixture.
- Frontend unit tests: `TestBed.configureTestingModule` + `vi.fn()` mocks; assert signals via `fixture.componentInstance.signal()`.
- New spec files go beside the file under test (`foo.spec.ts` next to `foo.ts`)
- Path traversal tests: add `test_*_path_traversal_rejected` to route test classes that accept user-supplied filenames (e.g. `TestRegisterModel.test_path_traversal_rejected`).
- Whitespace input tests: add `test_*_whitespace_only_*_returns_400` when handler strips required fields.
- **`_async_return` helper**: define at module level in test files that need to return coroutines from monkeypatched lambdas:
  ```python
  async def _async_return(value):
      return value
  ```
  Use as `lambda path: _async_return("hash")` — NOT `lambda fn, *args: _async_return(...)` (the latter is the asyncio.to_thread signature, which we no longer patch).
- **V8 function coverage for service methods**: Angular services are fully mocked in component tests, so their method bodies get 0% V8 function coverage. **Each new service method must have a dedicated test in `<service>.spec.ts` using `HttpTestingController`** — e.g., `provideHttpClientTesting()` + `TestBed.inject(HttpTestingController)` → `ctrl.expectOne(url).flush(response)`. Without this, the frontend function-coverage gate (≥62%) will fail.
- **V8 coverage for computed signal callbacks**: `computed(() => expr)` arrow functions are separate function entries in V8. Access each computed signal at least once in a test to execute its callback and count it as covered.
- **Reassigning Observable mock properties without `no-explicit-any`**: when a spec-file mock object has a typed `obs$: Observable<T>` property and a test needs to swap it for a `Subject<T>`, use `as unknown as typeof mockX.obs$` instead of `(mockX as any).obs$ = ...`:
  ```typescript
  // CORRECT — type-safe, ESLint clean
  mockDownloadService.completedTasks$ = completedTasks$ as unknown as typeof mockDownloadService.completedTasks$;
  mockDownloadService.completedTasks$ = of([]) as unknown as typeof mockDownloadService.completedTasks$;

  // WRONG — triggers @typescript-eslint/no-explicit-any
  (mockDownloadService as any).completedTasks$ = completedTasks$;
  ```
- **Assigning private/computed signals on a component under test**: use `Object.assign` instead of `(component as any)`:
  ```typescript
  // CORRECT
  Object.assign(component, { keywords: signal([sdxlKeyword]) });

  // WRONG — triggers @typescript-eslint/no-explicit-any
  (component as any).keywords = signal([sdxlKeyword]);
  ```

## Git / Commits

- Commits and comments in English.
- Never mention Claude as co-author or use EOF in commit messages.
- Feature branches via `gh issue develop <num> --name <short> --checkout`.

## Workflow Rules

- **Serena memory commits are immediate**: any time a Serena memory file is written or updated, commit it on the current working branch right away — never defer to a later session or a separate PR.
- **Post-PR follow-up changes**: changes made after the main feature commit has been pushed/merged (UI polish, translation fixes, Serena updates, etc.) must go on a new feature branch with their own PR — never accumulated on `main` locally.
