# Audit Improvements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the 2026-08-07 project audit findings: backend event-loop/N+1 fixes, frontend subscription/i18n/a11y/bundle hygiene, SonarQube zero, Angular 22 upgrade, ruff expansion, coverage lifts.

**Architecture:** A single branch (`audit-improvements`) with one commit per task. Backend work follows the existing `asyncio.to_thread` wrapper convention and the repo pattern in `py/db/model_repo.py`. Frontend work follows the zoneless-signals conventions in `mem:conventions`. No behavior changes except where noted; every task ends with the full gate run for the side it touched.

**Tech Stack:** Python 3.12+/aiohttp/SQLite/pytest; Angular 21.2 (→22.1 in Task 10)/Vitest/ESLint/Prettier.

## Global Constraints

- All gates must pass per task before commit: backend `PYTHONSAFEPATH=1 ../../../comfy-env/bin/python -m pytest`, `ruff check py tests conftest.py`, `ruff format --check py tests conftest.py`; frontend `npx ng test --watch=false`, `npx ng lint`, `npm run format:check`, `npx ng build` (build only when `frontend/` changed).
- Commits in English; no Claude co-author mention; no EOF markers.
- Never push or open a PR without explicit user approval.
- New files written with the Write tool must be `npx prettier --write`-formatted before the format check.
- Decision (accepted): in-memory queues in `py/routes/workflow.py` and `py/services/backend_notifier.py` stay unpersisted — worst case on restart is a lost node-insert/notification.
- Task 13 (component splitting) is deliberately deferred; not part of this branch.

---

### Task 1: Housekeeping — stale branch + npm patch updates

**Files:**
- Modify: `frontend/package-lock.json` (via `npm update`), possibly `frontend/package.json` (dompurify is a direct dep at `3.4.12` → `3.4.13` if in-range)
- Delete: local git branch `images-recreate` (stale pre-squash copy of merged PR #136)

- [x] **Step 1:** `git branch -D images-recreate` (its content is merged as squash commit `8cb733c`).
- [x] **Step 2:** From `frontend/`: `npm update` → pulls `@angular/build`/`@angular/cli` 21.2.20, `dompurify` 3.4.13, `typescript-eslint` 8.66.0 (all in-range).
- [x] **Step 3:** `npm audit` — expect the 3 undici findings to remain (fixed only by Angular 22, Task 10). Record output.
- [x] **Step 4:** Full frontend gate run (test, lint, format:check, build).
- [x] **Step 5:** Commit `chore(deps): npm update to latest in-range patches`.

### Task 2: SonarQube zero — python:S9083 decorator parens

**Files:**
- Modify (remove empty parens from decorators, e.g. `@pytest.fixture()` → `@pytest.fixture`):
  `tests/test_media_cleanup.py:8`, `tests/test_auto_migrator.py:21`, `tests/test_video_poster.py:10`, `tests/test_routes_tags.py:7`, `tests/test_routes_catalog.py:10`, `tests/test_metadata_fetcher_integration.py:11`, `tests/test_reorganizer.py:9`, `tests/test_routes_metadata.py:11,194`, `tests/conftest.py:107`, `tests/test_config.py:9`, `tests/test_routes_download.py:26`, `tests/test_routes_models.py:9,30,37`, `tests/test_routes_settings.py:7`, `tests/test_routes_workflow.py:7` (line numbers are SonarQube's, 1-based)

- [x] **Step 1:** Sweep with `grep -rn '@pytest.fixture()' tests/ conftest.py` (and any other zero-arg decorator Sonar flagged) and strip the parens at the 17 flagged sites.
- [x] **Step 2:** Backend gate run (pytest + ruff check + ruff format --check).
- [x] **Step 3:** Commit `test: drop empty decorator parentheses (SonarQube S9083)`.

### Task 3: Backend — unblock the event loop

**Files:**
- Modify: `py/routes/catalog.py` (blocking `_scan_all_files()` call site ~line 220), `py/routes/models.py` (`shutil.move` at ~124 and ~162, `disk_scanner.scan_all()` at ~184)
- Test: `tests/test_routes_models.py`, `tests/test_routes_catalog.py`

**Interfaces:**
- Produces: module-level patchable wrappers per the monkeypatch-wrapper convention in `mem:conventions` (never patch `asyncio.to_thread` directly), e.g. in `py/routes/models.py`:
  `async def _move_file(src: str, dest: str) -> None` (wraps `asyncio.to_thread(shutil.move, src, dest)`) and
  `async def _scan_disk() -> dict` (wraps `asyncio.to_thread(disk_scanner.scan_all)`); equivalent wrapper in `py/routes/catalog.py` for its own scan helper.

- [x] **Step 1:** Read the four call sites via Serena; add the wrapper coroutines next to the existing `_hash_file`-style seams.
- [x] **Step 2:** Replace the direct calls with `await <wrapper>(...)`.
- [x] **Step 3:** Existing route tests must still pass unchanged (they exercise the same handlers); where a test monkeypatches the old sync path, patch the new wrapper instead.
- [x] **Step 4:** Backend gate run.
- [x] **Step 5:** Commit `perf: run blocking file IO through asyncio.to_thread in route handlers`.

### Task 4: Backend — batch hydration in get_metadata_by_filenames

**Files:**
- Modify: `py/db/model_repo.py` (`get_metadata_by_filenames`, ~lines 234–246)
- Test: `tests/test_model_repo.py` (or wherever its existing tests live)

**Interfaces:**
- Produces: same public signature/return shape as today (list/dict of hydrated model metadata) — callers unaffected.

- [x] **Step 1:** Write/extend a regression test asserting the exact current output shape for 3 models with trigger words, media, and tags (run against current impl → green baseline).
- [x] **Step 2:** Rewrite hydration: one `SELECT ... WHERE model_id IN (…)` per child table (trigger_words, media, tags), group rows by `model_id` in Python, stitch into the parent dicts. 1+3N queries → 4.
- [x] **Step 3:** Re-run the regression test + full backend gate.
- [x] **Step 4:** Commit `perf: batch child-table hydration in get_metadata_by_filenames`.

### Task 5: Backend — log swallowed exceptions

**Files:**
- Modify: `py/routes/metadata.py` (~140: `_maybe_reorganize_for_base_model`), `py/services/metadata_fetcher.py` (~254 `_remove_dir_if_empty`, ~283 `_migrate_model_media`)

- [x] **Step 1:** Replace each `except Exception: pass` with logging via the module's existing logger (add `logger = logging.getLogger(__name__)` if absent), e.g. `logger.warning("reorganize failed for %s", path, exc_info=True)`. Behavior (fallback path) unchanged. `py/video_poster.py` stays as-is (deliberate fallback chain).
- [x] **Step 2:** Backend gate run.
- [x] **Step 3:** Commit `fix: log swallowed exceptions in reorganize/media-cleanup paths`.

### Task 6: Frontend — subscription hygiene (takeUntilDestroyed)

**Files:**
- Modify: `pages/model-detail/model-detail.ts`, `pages/models/models.ts`, `pages/download/download-search.ts`, `pages/images/images.ts`, `pages/workflows/workflows-browse.ts`, `pages/workflows/workflows-installed.ts`, `pages/settings/settings.ts`, `pages/catalog-detail/catalog-detail.ts`, `services/backend-notification.ts` (all under `frontend/src/app/`)
- Test: existing specs must stay green; no new specs required (no behavior change)

**Interfaces:**
- Produces: each component gains `private readonly destroyRef = inject(DestroyRef);` and every `.subscribe(` gains a preceding `.pipe(takeUntilDestroyed(this.destroyRef))` (or the existing pipe is extended). `BackendNotificationService` drops `Subscription`/`ngOnDestroy` for `takeUntilDestroyed()` in the constructor context.

- [x] **Step 1:** Sweep each file: `grep -n '\.subscribe(' frontend/src/app` → for each site not already guarded, add `takeUntilDestroyed(this.destroyRef)`. Rationale: one-shot HTTP observables complete anyway; the guard prevents late callbacks writing to destroyed components.
- [x] **Step 2:** Modernize `backend-notification.ts` (remove manual `ngOnDestroy` unsubscribe).
- [x] **Step 3:** Full frontend gate run (test, lint, format:check, build).
- [x] **Step 4:** Commit `refactor: guard all subscriptions with takeUntilDestroyed`.
- [x] **Step 5:** Append the convention to `mem:conventions` (Serena) and commit the memory file immediately (project rule).

### Task 7: Frontend — shared media load/error handlers

**Files:**
- Create: `frontend/src/app/utils/media-events.ts`
- Modify: the 6 duplicating components (`components/media-gallery/media-gallery.ts`, `pages/download/download-search.ts`, `pages/models/models.ts`, `pages/images/images.ts`, `pages/workflows/workflows-browse.ts`, `pages/workflows/workflows-installed.ts`) to delegate to it
- Test: `frontend/src/app/utils/media-events.spec.ts`

**Interfaces:**
- Produces:
  ```typescript
  export function showOnLoad(event: Event): void;      // display img, hide preceding ▶ sibling if present
  export function hideOnError(event: Event): void;     // display:none the failing img
  export function videoPosterUrl(localPath: string): string; // /tiny-model-manager/api/media-poster/<enc>
  ```

- [x] **Step 1:** Write the spec first: create real `<img>` elements, dispatch synthetic events, assert `style.display` transitions and the `previousElementSibling` ▶-hiding contract (per `mem:conventions` video-poster pattern); assert `videoPosterUrl` encoding.
- [x] **Step 2:** Run spec → fails (module missing).
- [x] **Step 3:** Implement `media-events.ts`; components keep thin methods (`onImgLoad(e) { showOnLoad(e); }`) so templates don't change.
- [x] **Step 4:** Delete the 6 duplicated bodies; `npx prettier --write` the new files.
- [x] **Step 5:** Full frontend gate run; commit `refactor: extract shared media load/error/poster helpers`.

### Task 8: Frontend — i18n + a11y sweep

**Files:**
- Modify: `components/text-diff-field/text-diff-field.html:11`, `components/array-field-merge/array-field-merge.html` (titles at 7,17,28,50,62 + 6 buttons), `components/edit-meta-form/edit-meta-form.html` (× buttons at 6, 28), `pages/models/models.html:333` (+ delete confirm flow in `models.ts:353`), `pages/model-detail/model-detail.html` (base-model placeholder), plus every locale JSON present (locate via the ngx-translate loader config)
- Test: affected component specs

- [x] **Step 1:** Add translation keys (e.g. `common.manually_edited`, `common.click_to_toggle`, `common.click_to_add`, `common.delete`, `models.confirm_delete_bulk` with `{count}` param, `model_detail.base_model_placeholder`) to every locale file present.
- [x] **Step 2:** Replace hardcoded `title="..."`/`placeholder="..."` with `[title]="'key' | translate"` / `[placeholder]="'key' | translate"`; add `[attr.aria-label]` mirroring the title on the icon-only buttons (×, delete) per the form-control-labeling convention.
- [x] **Step 3:** Replace the native `confirm()` in `models.ts:353` with the existing `app-confirm-popover` component (same pattern as single-delete).
- [x] **Step 4:** Update/extend specs where they assert on the old strings; full frontend gate run.
- [x] **Step 5:** Commit `fix: translate hardcoded UI strings and add aria-labels (i18n/a11y)`.

### Task 9: Frontend — lazy-loaded routes

**Files:**
- Modify: `frontend/src/app/app.routes.ts` (all 7 page routes → `loadComponent: () => import('./pages/...').then(m => m.X)`)
- Test: `frontend/src/app/app.routes.spec.ts` (existing harness; adjust stub-mapping helper to handle `loadComponent` entries)

- [x] **Step 1:** Convert each eager `component:` to `loadComponent:`; keep redirects (incl. the `RedirectFunction` for `catalog/:platform`) untouched.
- [x] **Step 2:** Fix the route-spec stub mapper to also stub `loadComponent` routes.
- [x] **Step 3:** `npx ng build` — verify the initial bundle shrinks; if comfortably under 650 kB, lower `maximumWarning` in `angular.json` back to 650 kB.
- [x] **Step 4:** Full frontend gate run; commit `perf: lazy-load all page routes`.

### Task 10: Angular 22 upgrade (fixes undici advisory)

**Files:**
- Modify: `frontend/package.json`, `frontend/package-lock.json`, possibly `frontend/angular.json` / TS config / code touched by migrations

- [x] **Step 1:** `npx ng update @angular/core@22 @angular/cli@22`, then `npx ng update @angular-eslint/schematics@22` (angular-eslint 22 for ESLint compat); bump `typescript-eslint` only if peer ranges require it.
- [x] **Step 2:** Re-check the two standing gotchas from `mem:conventions`: whether the `@hono/node-server` override is still needed, and that the `frontend/js` asset-path rule still holds under the v22 builder.
- [x] **Step 3:** `npm audit` — verify the undici findings are gone.
- [x] **Step 4:** Full frontend gate run incl. build; fix any migration fallout (API renames, builder options).
- [x] **Step 5:** Commit `chore(deps): upgrade to Angular 22.1 (fixes undici advisory)`; update `mem:tech_stack` (Angular version) and commit the memory immediately.

### Task 11: Ruff rule expansion

**Files:**
- Modify: `pyproject.toml` (`[tool.ruff.lint] select` += `"A", "C4", "RUF"`), plus whatever the new rules flag in `py/`, `tests/`, `conftest.py`

- [x] **Step 1:** Add the three families; run `ruff check` → triage. Auto-fix with `--fix` where safe; hand-fix the rest. Add per-rule ignores only with a documented reason (e.g. mutable class attributes in ComfyUI node definitions if RUF012 fires on them).
- [x] **Step 2:** Backend gate run (pytest + format check still clean).
- [x] **Step 3:** Commit `chore: enable ruff A/C4/RUF rule families`; note the new families in `mem:tech_stack` and commit the memory immediately.

### Task 12: Coverage lifts

**Files:**
- Create/extend: `tests/test_nodes_utils.py` (py/nodes/_utils.py, 13%), `tests/test_routes_notifications.py` (43%), `tests/test_routes_static.py` (61%), extend `tests/test_metadata_fetcher*.py` (66%) and `tests/test_civitai_provider.py` (71%) for the largest uncovered branches
- Create: frontend `HttpTestingController` specs — `services/keywords.spec.ts`, `services/tags.spec.ts`, `services/settings.spec.ts`, `services/backend-notification.spec.ts`

- [x] **Step 1:** Backend: for each target, list uncovered lines (`pytest --cov=py --cov-report=term-missing`), write unit tests for the biggest contiguous gaps (nodes utils, notifications routes, static path guards, metadata_fetcher error paths, civitai provider parsing branches).
- [x] **Step 2:** Frontend: one spec per untested service using `provideHttpClientTesting` + `expectOne(...).flush(...)` per `mem:conventions` (protects the ≥62% function-coverage gate).
- [x] **Step 3:** Full gates both sides; confirm backend stays ≥88% and improves.
- [x] **Step 4:** Commit `test: lift coverage on nodes utils, notification/static routes, providers, frontend services`.

---

## Self-Review Notes

- Spec coverage: audit steps 1–12 all mapped (Task N == audit step N); audit step 13 explicitly deferred (Global Constraints).
- Exact line numbers for Tasks 3–5 come from the audit agents and are re-verified via Serena at implementation time; the wrapper/batching approaches are fixed, the surrounding code is read before editing.
- In-memory queue persistence: decided as "accept" — recorded in Global Constraints so no task implements it.
