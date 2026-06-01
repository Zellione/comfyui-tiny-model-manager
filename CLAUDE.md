# Project
ComfyUI custom-node to manage and download models, LORAs, workflows from CivitAI and huggingface.
Goal: Dashboard to manage Models/LORAs and custom nodes to insert them with their documented trigger words

## Tech Stack
### Frontend
- Angular 21.2 (zoneless, no Zone.js)

#### Build
ComfyUI serves the compiled output in `web/` (git-ignored). Any change to `frontend/` or `js/`
requires a rebuild before it takes effect. Run from the `frontend/` directory:

```
# once, or after changing package.json dependencies
npm install

# production build → outputs to ../web/  (default configuration is production)
npx ng build

# auto-rebuild during active development
npx ng build --watch --configuration development
```

The `js/` ComfyUI extension folder is copied into `web/` as a build asset — it is bundled by
the same `ng build` call and must not be deployed separately.

The Python backend (`py/`) needs no build step; changes take effect after restarting ComfyUI.

#### Testing & Linting (frontend)

**MANDATORY — run before every commit. All checks must be clean with zero failures.**

Run from the `frontend/` directory:

```
# Unit tests (Vitest, no browser needed) — matches CI: npm run test:ci
npx ng test --watch=false

# ESLint (0 errors required; warnings allowed) — matches CI: npm run lint
npx ng lint

# Prettier format check — use npm run to match CI exactly (npx prettier may resolve a different binary)
npm run format:check

# Production build — REQUIRED after any change to frontend/ or js/
npx ng build
```

**If you changed any file under `frontend/` or `js/`, you MUST run `npx ng build` and confirm it succeeds before committing. A passing test suite does not substitute for a successful build.**

**After creating any new file under `frontend/` with the Write tool, immediately run `npx prettier --write <file>` on it before the final `npm run format:check`. The Write tool does not auto-format, so new files will fail the CI Prettier check unless explicitly formatted.**

**Build location matters:** `web/` is git-ignored, so each git worktree has its own isolated `web/` that ComfyUI never reads. Always run `npx ng build` from the **main checkout's** `frontend/` directory (`comfyui-tiny-model-manager/frontend/`), not from inside a worktree. If you develop in a worktree, copy the finished build to the main checkout after merging, or run the build from the main checkout directly.

---

### Backend
- Python 3.12+ (Windows ships 3.13.12 via python_embeded; Linux venv version depends on system install)
- Persistence through SQLite files in a subfolder folder
- Huggingface.co API (consult documentation: https://huggingface.co/.well-known/openapi.md)
- CivitAI API (consult documentation: https://developer.civitai.com/site/reference/)

For further information you can Check the official documentation https://docs.comfy.org/custom-nodes/overview

#### Testing & Linting (backend)

**MANDATORY — run before every commit. All checks must be clean with zero failures.**

Run from the project root.

##### Windows (python_embeded)

```powershell
# Unit + integration tests (pytest, 147 tests)
# PYTHONSAFEPATH prevents Python from prepending CWD to sys.path, which is
# required so pytest's own `import py` resolves to the installed py library
# (py.path.local) rather than the local py/ backend package.
$env:PYTHONSAFEPATH = '1'; ..\..\..\python_embeded\python.exe -m pytest

# Ruff lint (E/F/I/UP/B rules — 0 errors required)
..\..\..\python_embeded\python.exe -m ruff check py tests conftest.py

# Ruff format check
..\..\..\python_embeded\python.exe -m ruff format --check py tests conftest.py
```

Dev dependencies are in `requirements-dev.txt`; install once with:
```powershell
..\..\..\python_embeded\python.exe -m pip install -r requirements-dev.txt
```

##### Linux (comfy-cli venv)

```bash
# Unit + integration tests
PYTHONSAFEPATH=1 ../../../comfy-env/bin/python -m pytest

# Ruff lint (E/F/I/UP/B rules — 0 errors required)
../../../comfy-env/bin/python -m ruff check py tests conftest.py

# Ruff format check
../../../comfy-env/bin/python -m ruff format --check py tests conftest.py
```

Dev dependencies are in `requirements-dev.txt`; install once with:
```bash
../../../comfy-env/bin/python -m pip install -r requirements-dev.txt
```

---

## Workflow
- Commits and code comments always in english
- Claude never mentions it self as Coauthor or uses EOF in commit message
- **Claude MUST NOT push to remote or create/update a pull request without explicit user approval. Always commit locally, present the commit, and wait for the user to say "push" or "open PR" before doing so.**

### Testing discipline (MANDATORY)

**Write tests for all new behaviour. Update existing tests when behaviour changes.**

#### Frontend (Angular / Vitest)
- New signals, computed values, and method logic → add unit tests in a `*.spec.ts` file next to the component/service (e.g. `download.spec.ts` beside `download.ts`)
- Use `TestBed.configureTestingModule` + `vi.fn()` mocks for all injected services; assert signal state via `fixture.componentInstance.signal()`
- When injecting `DownloadService`, mock `activeTasks$` as `of([])` and `completedTasks$` as `EMPTY`
- Run `npx ng test --watch=false` to confirm all tests pass before committing

#### Backend (Python / pytest)
- New routes → add integration tests in `tests/test_routes_<module>.py` using the `aiohttp_client` + `ext_dir` fixtures from `conftest.py`
- New service/provider logic → add unit tests in `tests/test_<module>.py` using `pytest-asyncio` and `httpx` mocking
- Run `PYTHONSAFEPATH=1 ../../../comfy-env/bin/python -m pytest` to confirm all tests pass before committing

### Angular / RxJS gotchas

- **Polling observables must handle errors**: Any `interval() + switchMap(HTTP)` stream
  terminates permanently on first error unless `catchError` is used inside the switchMap.
  Pattern: `.pipe(map(...), catchError(() => of(fallback)))` — stream keeps ticking.

- **Template branching hides UI**: When `search()` clears results and the request also
  fails, the `@else if (results.length === 0)` branch shows "No results found" — hiding
  the entire split view and any buttons inside it. Track search failures with a separate
  `searchError` signal and add an `@else if (searchError())` branch above the empty state.

- **`flex: 1; min-height: 0` collapses in auto-height containers**: A flex child with
  `flex: 1; min-height: 0` inside a column that has no definite height (no `height`,
  only `max-height`) collapses to 0 and hides overflow content. Fix: give the scrollable
  child its own `max-height` directly instead of relying on flex grow.

### Feature branch rule (MANDATORY)

**Any time the user asks to implement a feature — whether by saying "implement F-36", "add F-12", or any request whose subject matches the pattern `F-\d+` — Claude MUST, before touching any file:**

1. Check the current branch with `git branch`
2. If not already on a correctly named feature branch (`F-<number>-<short-name>`):
   a. `git checkout main`
   b. `git fetch origin && git pull origin main`
   c. `git checkout -b F-<number>-<short-name>`
3. Only then proceed with exploration and implementation.

If there are already uncommitted changes on the wrong branch, stash them (`git stash`), perform steps 2a–2c, then restore (`git stash pop`).

### Feature

If planning and working on a new feature already specified in @PRD.md the following steps have to be executed, if not already happened:

1. **Ensure you are on a correctly named feature branch (see Feature branch rule above)**
2. Enter plan mode and plan feature
3. Wait for approval of plan
4. If plan was approved implement plan
5. **Run all tests and lint for both backend and frontend — only proceed when every check passes with zero failures**
6. **If any file under `frontend/` or `js/` was changed: run `npx ng build` from `frontend/` and confirm it succeeds**
7. If there are no bugs reported: commit changes locally and present the commit to the user
8. **Mark the feature as done (`[x]`) in `README.md` features checklist**
9. **Wait for explicit user approval before pushing to github (origin)**
10. **Wait for explicit user approval before opening a pull request**

### Bug during feature development.

If working on a bug during feature development and it was alrady pushed and a pull request created:

1. Make sure to be on feature branch, if not checkout
2. Enter plan mode
3. Analyze the bug
4. Make a plan to fix the bug
5. Wait for approval of plan
6. If plan was approved implement plan.
7. **Run all tests and lint for both backend and frontend — only proceed when every check passes with zero failures**
8. **If any file under `frontend/` or `js/` was changed: run `npx ng build` from `frontend/` and confirm it succeeds**
9. If there are no bugs reported: commit changes locally and present the commit to the user
10. **Mark the feature as done (`[x]`) in `README.md` features checklist**
11. **Wait for explicit user approval before pushing to github (origin)**
12. **Wait for explicit user approval before updating the pull request**