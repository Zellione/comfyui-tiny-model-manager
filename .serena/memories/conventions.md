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
- **A string `redirectTo` drops the query string.** Angular's `createQueryParams` builds the
  redirect target's query params *only* from what is written into the `redirectTo` string,
  consulting the incoming URL solely for explicit `:name` back-references. So
  `{ path: 'catalog/:platform', redirectTo: 'models/:platform' }` silently loses `?pageId=`.
  When a legacy path carries query params, use a `RedirectFunction` (runs in an injection
  context; its snapshot has both `params` and `queryParams`; returning a `UrlTree` is honoured):
  ```typescript
  redirectTo: (r) =>
    inject(Router).createUrlTree(['/models', r.params['platform']], { queryParams: r.queryParams }),
  ```
- **Testing routes without instantiating pages**: map the real `routes` array onto a stub
  component (`routes.map((r) => ('component' in r ? { ...r, component: StubPage } : r))`), then
  `provideRouter(testRoutes)` + `provideLocationMocks()` (`@angular/common/testing`) +
  `RouterTestingHarness.create()` and assert `router.url` after `navigateByUrl`. Redirects and
  path matching are exercised for real; no page service mocks needed. See `app.routes.spec.ts`.
- **Form-control labeling (SonarQube `Web:InputWithoutLabelCheck`, a RELIABILITY bug)**: every `<input>` (except submit/button/image/hidden), `<select>` and `<textarea>` must have an associated label. Preferred fix is `[attr.aria-label]=\"'<key>' | translate\"` (no layout change); reuse the placeholder/header translation key where one exists, or bind a meaningful value (e.g. `[attr.aria-label]=\"f.name\"` for per-file checkboxes). Inputs wrapped in a `<label>…</label>` (implicit label) are already compliant.

## External pre-fill UX pattern (register form — F-90 hash lookup, F-91 link resolution)

When a registration/edit form pre-fills itself from an external API, the register form on the
Models page carries **two independent pre-fill paths** that share one source signal.

**Component state:**
```typescript
// In RegisterForm interface:
hashStatus: 'loading' | 'found' | 'not_found' | 'error';   // automatic, on open
linkStatus: 'idle' | 'loading' | 'found' | 'error';        // manual, on Resolve
name: string;
link: string;
linkMessage: string;                                       // resolved i18n string

// Private signals on the component:
private registerFileHash = signal<string>('');
private registerSource = signal<{
  platform: string; source_id: string; civitai_model_id: string;
} | null>(null);
```

`registerSource` is **platform-agnostic** — it is set by `_runHashLookup` (`platform: 'civitai'`)
*and* by `resolveLink` (whatever the API returns). Do not reintroduce a CivitAI-only signal.

**Hash path (automatic):** `openRegisterForm` sets `hashStatus: 'loading'` and calls
`_runHashLookup(filename, modelType)` — a one-shot observable, no `takeUntilDestroyed` needed.
On match → `hashStatus: 'found'` + pre-fill + store hash/source; no match → `'not_found'`;
error → `'error'`. `retryHashLookup()` resets to `'loading'` and re-calls from `registerFormFile()`.

**Link path (manual, F-91):** `resolveLink()` reads `registerForm().link`, no-ops when blank,
sets `linkStatus: 'loading'`, then calls `modelService.resolveLink(url)`. Success **overwrites**
`name`/`baseModel`/`description`/`tags` and replaces `registerSource` (the user asked for it).
Errors map backend codes through a module-level `LINK_ERROR_KEYS` record
(`invalid_url` / `not_found` / `provider_unavailable`) with a `link_failed` fallback, storing the
translated text in `linkMessage`.

**`model_type` is never overwritten by either path** — the file's directory fixes its type. The
API returns the provider's `model_type` for other consumers (auto-migration), not for the form.

**Template states (use `@if` / `@else if` / `@else`):**
- hash `loading`: spinner div + `| translate`; all form inputs `[disabled]="…hashStatus === 'loading'"`;
  submit also `[disabled]="registerForm().saving || registerForm().hashStatus === 'loading'"`
- hash `found`: green badge, `| translate: { name: registerForm().name }`
- hash `not_found`: neutral note; hash `error`: red message + `<button (click)="retryHashLookup()">`
- link row is **always visible** (above the metadata fields), never gated on `hashStatus`
- link `found` / `error`: `<p class="register-link-status register-link-found|error">{{ linkMessage }}</p>`

**submitRegister:** attach `file_hash` when `registerFileHash()` is truthy, and attach
`source_platform` / `source_id` / `civitai_model_id` from `registerSource()` **independently** —
a link-resolved source must be sent even when the hash lookup found nothing.

**Tests:** use `new Subject<HashLookupResult>()` (never resolves) for the loading state; set a
default `mockModelService.hashLookup.mockReturnValue(of({ hash: '', match: false, metadata: null }))`
in `beforeEach` so existing tests aren't broken; `it.each` over the error codes covers the
`LINK_ERROR_KEYS` mapping (the real `en.json` is loaded by `provideTranslateServiceForTests`, so
assert the actual English string).

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

## CivitAI response shapes — description and tags (PR #133)

`GET /model-versions/{id}` and `GET /model-versions/by-hash/{hash}` do **not** contain the model
description or its tags:

- top-level `description` is the **version changelog** (often `null`), not the model description
- the nested `model` object holds only `{name, type, nsfw, poi}` — no `description`, no `tags`

Both live on the model page (`GET /models/{modelId}`) and need a **second request**. This is why
`lookup_by_hash` / `lookup_by_version_id` call `_fetch_model_page(data["modelId"])` and splice
`description` + `tags` into the version payload via `_enrich_version` before handing it to
`_version_to_metadata`. A failed model page degrades to the version payload — never raises.

`_compose_description(model_description, version_description)` is the single place that joins the
two: model description first, changelog appended after `<hr><h3>Version notes</h3>`, either side
alone when the other is missing. **Never write `data["description"] or model["description"]`** —
that precedence is the bug PR #133 fixed (changelog shadowed the real description, or the field
came back empty).

The heading is baked into stored text at import time, so it cannot go through ngx-translate — it
is English regardless of UI language. Descriptions render through `[innerHTML] | safeHtml`, so the
markup displays correctly on model-detail and catalog-detail.

Only `lookup_by_model_id` starts from the model page and already has both fields; it still routes
through `_compose_description` so the changelog is appended rather than dropped.

## CivitAI images API — `/api/v1/images` (F-130)

Everything below was verified against the **live** API while planning #130; the issue text and
the public docs were wrong or silent on all of it. Do not "simplify" these away.

1. **No free-text search.** `?query=cat` is accepted and silently ignored (returns unrelated
   results). The feed is filter-only: `sort`, `period`, `nsfw`, `baseModels`, `type`,
   `username`, `modelId`, `postId`, `imageId`, `limit`, `cursor`. That is why the Images page
   has no search box.
2. **No `GET /api/v1/images/{id}`.** Single-image detail is `?imageId=<id>`, returning one item.
3. **That single-image response double-nests the metadata.** The feed gives
   `item["meta"] = {…params…}`; the `imageId=` query gives
   `item["meta"] = {"id": <image id>, "meta": {…params…}}`. Undocumented. Unhandled, it makes
   *every* single-image lookup look like it has no metadata — which is precisely how Recreate
   failed until `routes/images.py::_unwrap_meta` was added. Regression tests cover both routes.
4. **Image ids are a 32-bit signed column.** Anything above `2**31 - 1` gets a CivitAI **500**
   (`value "…" is out of range for type integer`), which would surface a bad id as a provider
   outage. `_valid_image_id()` bounds it so it is a 404.
5. **`withMeta=true` is mandatory.** Without it `meta` comes back empty on many items.
6. **`meta.comfy` is a JSON string** holding `{"prompt": …, "workflow": …}`, where `workflow`
   is a complete ComfyUI frontend graph. This is how the embedded graph is obtained — CivitAI
   re-encodes uploads to `.jpeg` on its CDN, so the PNG tEXt chunks are gone from the file and
   **there is nothing to parse; no image download and no Pillow dependency is needed.**
7. **`meta.hashes` values are AutoV2, and AutoV2 is exactly `SHA256[:10]`** (verified:
   `AutoV2: EB4DD8C612` vs `SHA256[:10]: EB4DD8C612`). Local matching is therefore a prefix
   compare against the existing `models.file_hash` — no new column, no re-hashing.
   `/model-versions/by-hash/<AutoV2>` also returns 200, so `lookup_by_hash` accepts it directly.
8. Auth is **not** required for the images feed (an API key still works and is sent).

Metadata distribution, sampled over 200 live images (Week/SFW) — worth knowing before assuming
a path is rare: `meta.comfy` ~11 %, A1111-style params only ~56 %, no `meta` at all ~33 %. The
"Recreatable only" filter defaults to on because of that last third.

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

## Other recurring SonarQube rules

### Validate a rule fix locally before pushing
`mcp__sonarqube__analyze_code_snippet` runs the real analyzer on a snippet, so a fix can be
confirmed without a push → CI → analysis round trip. Put the old and new versions in one snippet
and check which lines come back flagged:

```
analyze_code_snippet(fileContent="<old impl>\n<new impl>", language="js")
→ issues: [{ruleKey: "javascript:S8786", textRange: {startLine: 6}}]   # only the old one
```

Arguments are `fileContent` (not `codeSnippet`) and a short `language` key — `js`/`ts`, **not**
`javascript`/`typescript`, which errors out.

Also remember that PR annotations reflect the **last completed analysis**: a fix that is committed
but not pushed will keep showing the old warning. Check for unpushed commits before assuming a fix
did not work.



### S5906 — assert length with the dedicated matcher
In specs use `expect(x).toHaveLength(n)`, never `expect(x.length).toBe(n)` — the matcher reports
the actual contents on failure instead of just a number. All 25 pre-existing call sites were
converted (issue #120); don't reintroduce the old form.

### css:S1874 — `word-break: break-word` is deprecated
Use `overflow-wrap: break-word`. The deprecated keyword was always defined as an alias for it, so
rendering is identical. Typically paired with `white-space: pre-wrap` to break long unbreakable
strings (URLs, hashes).

### S8786 — non-linear regex backtracking
An **unanchored** pattern is retried at every position, so an unbounded quantifier next to it turns
into O(n²). `/\s*\(\d+\)$/` in `stripSuffix` was flagged for exactly this.

Fix with a **bounded** quantifier (`\d{1,9}`) and handle any variable-length run outside the regex
— `trimEnd()` is linear and covers the same whitespace set as `\s*`.

**Trap:** bounding the whitespace instead (`\s{0,4}\(\d+\)$`) looks equivalent and is not. Because
the pattern is unanchored, a run longer than the bound still matches further along and leaves stray
characters behind: `"model     (2)"` became `"model "`. A test caught this — always cover a run
longer than the bound when tightening a quantifier on an unanchored pattern.

## Cognitive complexity (SonarQube S3776)

- SonarQube enforces a max cognitive complexity of **15** per function (rule `python:S3776`).
- When a Python async function exceeds 15, extract private helper coroutines (`async def _helper(db, e: dict) -> None`) that each own a single responsibility. The caller becomes a thin orchestrator.
- **Pattern used in `model_repo.py`** (`list_catalog_entries`): extracted `_fill_thumbnail`, `_fill_model_type`, `_fill_video_status` — each is `async`, accepts `db` and the mutable entry dict `e`, mutates `e` in place, returns `None`.
- Module-level constants shared by helpers (e.g. `_VIDEO_PATH_EXTS`) go alongside the other `_UPPER_CASE` constants at the top of the file.
- Private helpers are not tested directly; coverage comes from route/integration tests that exercise the public function.

## JS Extension (frontend/js/)

- `setup()` runs before Vue mounts → use `MutationObserver` on `document.body` for Vue-rendered elements.
- `legacy-topbar-container` stays hidden unless it has non-empty element grandchildren — insert buttons into its **parent** (`legacy?.parentElement`) using `insertBefore`.
- The whole `frontend/js/` folder is copied to `web/` by `ng build` (angular.json asset entry `input: "js", output: "/"`), so sibling modules can be split out freely and imported with plain relative paths (`./workflow-insert.js`).
- **The folder must stay inside `frontend/`.** `@angular/build` ≥ 21.2.13 rejects any asset whose `input` escapes the Angular workspace root (`The ../js asset path must be within the workspace root.`), so the pre-21.2.13 layout with `js/` at the repo root can never be restored — see "Dependency maintenance" below.
- Because `frontend/js/` is inside the Prettier scope, `js/*.js` **is** format-checked by `npm run format:check`. ESLint still ignores it (the `ng lint` config only targets `src/`).

### Testable logic modules (F-93 pattern)

`extension.js` imports `../../scripts/app.js`, which resolves only inside ComfyUI, and calls
`app.registerExtension()` at module scope — so it can never be imported by a test. Put any logic
worth testing in a **separate `frontend/js/*.js` module with injected dependencies and no side effects on
load**; `extension.js` stays a thin wiring layer that passes the real globals:

```js
// frontend/js/workflow-insert.js — no ComfyUI imports
export function createPendingProcessor({ app, liteGraph, api, fetchFn = fetch }) { … }

// frontend/js/extension.js
const processPending = createPendingProcessor({ app, liteGraph: LiteGraph, api: API });
setInterval(processPending, 500);
```

Specs for these modules live under `frontend/src/comfy-extension/*.spec.ts` (the
`@angular/build:unit-test` builder only discovers specs under the frontend project root) and import
the module by relative path (`../../js/workflow-insert.js`). Since the module now lives inside the
frontend project, `frontend/tsconfig.spec.json` needs only:

```jsonc
"allowJs": true,   // consume the plain-JS module
```

(The former `"rootDir": ".."` escape hatch was required only while `js/` sat at the repo root; it
was removed when the folder moved under `frontend/`.)

### Coverage for frontend/js/ is waived in Sonar

History: while the folder lived at the repo root, `@vitest/coverage-v8` could not report on it at
all — `coverageInclude` entries reaching into `../js` (broad `../js/**` or the single
`../js/workflow-insert.js`) failed with `RollupError: Expression expected` / `PARSE_ERROR, pos: 0`
inside `V8CoverageProvider.getCoverageMapForUncoveredFiles`, because the provider cannot pull a
file from outside the Vitest root through the Vite transform pipeline. That produced no lcov entry,
so SonarCloud scored the fully tested `workflow-insert.js` as 0% and failed the
`new_coverage ≥ 80` gate on PR #117.

The fix at the time was `sonar.coverage.exclusions=js/**`, now
`sonar.coverage.exclusions=frontend/js/**`. `frontend/js` stays in `sonar.sources`, so it is still
analysed for bugs, smells and security hotspots — only the coverage metric is waived, and the specs
still run in CI.

**The original blocker no longer applies**: the folder now sits *inside* the Vitest root, so a
`coverageInclude` of `js/**` would likely work. This has not been tried. If the coverage waiver ever
becomes a problem, that is the first thing to attempt — but expect the added file to shift the
`new_coverage` numbers, so do it as its own change, not as a rider on something else.

### ComfyUI model-list refresh

`app.refreshComboInNodes()` (comfyui_frontend_package ≥0.24) re-fetches `/object_info` and rewrites
every COMBO widget's option list. Call it before inserting a loader node so a model downloaded after
the ComfyUI tab loaded is selectable without a page reload. Always best-effort — guard with
`typeof app?.refreshComboInNodes === "function"` and try/catch, since older frontends lack it and a
failed refresh must never block the insert.

The `/workflow/pending` poll needs a **re-entrancy guard** (`let running = false`): pending items are
only dropped on ack, and the refresh can outlast the 500 ms interval, so an overlapping tick would
insert the same node twice.

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
  `_resolve_model_link(parsed)` in `models.py` is the same seam for `link_resolver.resolve()`.
- **Never fetch a user-supplied URL server-side.** For pasted provider links, parse the URL,
  gate it on `url_guard.is_allowed_url()`, extract only the IDs, and call the provider API with
  those IDs (see `py/services/link_resolver.py`). The pasted URL itself is never requested.

## Security Patterns (SonarQube-compliant)

### Redirect hops are validated, not just the initial URL (F-129)

`url_guard.guarded_stream(client, method, url, headers=...)` is the **only** way outbound
file/media fetches should be made. It follows redirects by hand and re-runs `is_allowed_url`
on every `Location` before issuing the next request, bounded at 5 hops
(`RedirectNotAllowed` otherwise). Three call sites: `downloader._stream_file`,
`metadata_fetcher._fetch_url_to_file`, `workflow_store._fetch_archive`. **None of their
clients may set `follow_redirects=True`** — that would skip the per-hop check; there is a
test asserting the downloader's client doesn't.

**The trap:** with `follow_redirects=False` + manual re-issue, httpx's *own* `Authorization`
stripping (`_client.py::_redirect_headers`) no longer runs, so replaying the caller's headers
verbatim would leak the CivitAI API key to whatever host a redirect names.
`url_guard._redirect_headers` reproduces httpx's rule — drop `Authorization` unless the hop is
same-origin or a plain http→https upgrade on the same host. Do not "simplify" that away.

Both providers redirect and both land inside the allowlist, verified live:
`civitai.com` → `b2.civitai.com`, `huggingface.co` → `us.aws.cdn.hf.co`. Auth is only needed on
the first hop (the CDN URL is pre-signed via query param), so stripping it is safe — confirmed
by a real download through the hardened path. If a provider moves its CDN off these suffixes,
downloads fail with the blocked host named; add the suffix to `_ALLOWED_HOST_SUFFIXES` rather
than relaxing the check.

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
- **Never reset downloader state by hand in a test.** `tests/conftest.py` owns it via the autouse
  `reset_downloader_state` fixture. `downloader._queue` is built at import time, and
  `asyncio.Queue` binds to the first event loop that uses it and refuses any other one after
  that; `_worker` is an uncancelled `while True` task parked on `await _queue.get()`, and
  pytest-asyncio (`asyncio_mode = "auto"`, function-scoped loops) hands every test a fresh loop.
  The old two-line reset (`_tasks.clear()` + `_worker_started = False`) left the stale worker
  holding a getter on a closed loop, so the queue silently stopped draining.
  **This was a real bug and is fixed, but it was NOT the cause of the CI hang** — the hang
  recurred on PR #117 with this fixture in place. The actual cause was real DNS in the test
  suite; see the `block_network` entry below.
  The fixture additionally rebinds
  `dl._queue = asyncio.Queue()`, which is the load-bearing part, and cancels leftover
  `background._background_tasks` under `try/except RuntimeError` (their loop is usually already
  closed, which makes `cancel()` raise). It is deliberately **synchronous** — an async autouse
  fixture would force a loop onto every test, and `asyncio.Queue()` binds lazily so building it
  in a sync fixture correctly attaches it to the loop of the test about to run.
- **Testing loop-binding behaviour**: `asyncio.Queue.get()` only calls `_get_loop()` on the
  **empty** path — a pre-filled queue short-circuits through `get_nowait()` and never binds. A
  test that does `put_nowait(x)` then `await get()` therefore proves nothing. Schedule the put
  instead (`asyncio.get_running_loop().call_later(0.01, q.put_nowait, x)`) so `get()` is awaited
  on an empty queue, and wrap it in `asyncio.wait_for(..., timeout=1)` so a regression fails fast
  instead of hanging. See `TestQueueLoopBinding` in `tests/test_downloader.py`.
- **CI has `timeout-minutes` on every job** (`.github/workflows/ci.yml`: backend 10, frontend 15,
  sonarcloud 15). Without it a hung async test runs to GitHub's 6-hour default. Keep new jobs
  bounded.
- **Tests must never touch the real network — enforced by `block_network` (issue #118, RESOLVED)**.
  This was the cause of the long-running intermittent backend CI hang. Root cause, confirmed with
  a captured stack trace and a deterministic reproduction:

  A real DNS lookup is performed by `loop.getaddrinfo`, which runs in asyncio's **default
  `ThreadPoolExecutor`**. pytest-asyncio tears down its per-test loop with
  `asyncio.Runner.close()`, which calls `loop.shutdown_default_executor()` **without a timeout**,
  so it `join()`s that worker thread forever. When a CI runner's resolver stalls on a name, the
  suite wedges *in teardown* — which is why no dot was ever printed for the hanging test, why the
  process survived as an orphan, and why the 10-minute job ceiling was the only thing ending it.
  `httpx`'s `connect=30.0` cannot interrupt it: the block is inside a C call on a thread, not on
  the event loop, so no asyncio timeout applies.

  `tests/conftest.py` now has an autouse `block_network` fixture that raises
  `RealNetworkAccessError` on any non-loopback `getaddrinfo` / `connect` / `connect_ex`. Loopback
  stays open so aiohttp's test server keeps working. `tests/test_network_isolation.py` guards the
  guard.

  **Mock every outbound request.** Two traps found while fixing this:
  - The download tests relied on a real request to `civitai.com` being slow enough that the task
    was still `downloading` when they asserted on it. `tests/test_routes_download.py` now has an
    autouse `stub_transfer` fixture replacing `downloader._stream_file` with a coroutine that
    never completes, which reproduces that state deterministically and offline.
  - A network call can hide behind a mocked seam: `refetch_catalog_metadata` had
    `get_provider` patched, but `_fetch_hf_repo_files_safe` calls the HuggingFace API directly and
    its "safe" wrapper swallows the failure, so a real request went out with the test still green.
    Patch the *called* function, and re-check with a socket spy rather than trusting a passing test.

  Ruled out along the way (don't re-investigate): the queue/loop-binding bug (#119, real and fixed
  but not the cause), the Python 3.13-vs-3.14 difference (22 clean local runs on 3.13), coverage
  instrumentation, blocking loop teardown on in-flight sockets, and retry loops in the downloader.
- **`faulthandler_timeout = 60` in `[tool.pytest.ini_options]`** is instrumentation, not a fix —
  and it is what finally cracked #118: it produced the teardown stack naming
  `shutdown_default_executor`. Keep it. pytest dumps every thread's stack to stderr when a single test overruns, then lets it
  continue, so the next stall records exactly where it is stuck. Verified against a deliberately
  stalling test — the dump names the test function and line. The whole suite runs in ~7 s, so 60 s
  cannot fire on a healthy run. **When adding a diagnostic, prove it fires** before relying on it;
  a check that silently never triggers is worse than none.
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

## Frontend bundle budget

`angular.json`'s initial-bundle `maximumWarning` was raised 650kB → 750kB in F-129 (the Workflows
page added ~35 kB to a 634 kB baseline). `maximumError` stays at 1MB. Raise the warning again
rather than letting every build print a budget warning.

## Template coverage on new pages

Component specs that only call methods leave the template at ~10-30% line coverage, which drags a
new page's directory below SonarCloud's `new_coverage ≥ 80`. Add a `describe('template')` block
using a `render()` helper (`fixture.detectChanges()` → `await fixture.whenStable()` →
`detectChanges()`), then assert on `fixture.nativeElement.querySelector(...)` and click real
buttons. F-129's two page specs went from 54% → 94% lines this way.

## Dependency maintenance (Dependabot / npm audit)

All Dependabot alerts so far have been in `frontend/package-lock.json` (transitive dev deps);
`dompurify` is the only direct runtime dependency that has ever been flagged. The backend has no
alerts — `requirements*.txt` is not tracked by Dependabot.

Routine sweep, from `frontend/`:

```bash
npm audit           # see what is open
npm audit fix       # non-breaking transitive bumps
npm update          # pull in-range Angular patch releases (the usual real fix)
npm audit           # confirm
```

Most alerts resolve via `npm update`, because Angular pins its tooling deps (`vite`, `piscina`,
`undici`, `@babel/core`, `esbuild`) to **exact** versions — the patched versions only arrive with a
new `@angular/build` patch release, not through `npm audit fix` alone.

Two standing gotchas:

- **`@angular/build` ≥ 21.2.13 enforces that asset `input` paths stay within the Angular workspace
  root** (`frontend/`). This is what forced `js/` → `frontend/js/`. There is no version that has
  both the security fixes and the old permissive behaviour (21.2.12 is the last permissive one and
  still ships vulnerable `vite` 7.3.2 / `piscina` 5.1.4), and no config escape hatch. Never move an
  asset source back outside `frontend/`.
- **`@hono/node-server` is force-upgraded via an `overrides` entry in `frontend/package.json`.**
  It reaches the tree as `@angular/cli` → `@modelcontextprotocol/sdk` → `@hono/node-server`, and
  the advisory (Windows `serve-static` path traversal, GHSA-frvp-7c67-39w9) needs a major bump to
  ≥ 2.0.5 that no Angular release provides — npm's own suggestion is to *downgrade* the CLI. The
  override was verified against `ng build`, `ng test`, `ng lint`, `format:check` and `ng mcp --help`.
  Re-check whether it is still needed after each major Angular upgrade and drop it once upstream
  catches up.

## Git / Commits

- Commits and comments in English.
- Never mention Claude as co-author or use EOF in commit messages.
- Feature branches via `gh issue develop <num> --name <short> --checkout`.

## Workflow Rules

- **Serena memory commits are immediate**: any time a Serena memory file is written or updated, commit it on the current working branch right away — never defer to a later session or a separate PR.
- **Post-PR follow-up changes**: changes made after the main feature commit has been pushed/merged (UI polish, translation fixes, Serena updates, etc.) must go on a new feature branch with their own PR — never accumulated on `main` locally.
