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

#### Git hooks (one-time per clone)

Activate the pre-push coverage gate:

```bash
git config core.hooksPath .githooks
```

The hook enforces minimum coverage before every push:
- Backend ≥ 88 % lines (`fail_under` in `pyproject.toml`)
- Frontend ≥ 74 % lines / ≥ 62 % functions / ≥ 74 % branches (`coverageThresholds` in `angular.json`)

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

### ComfyUI JS extension gotchas

- **`legacy-topbar-container` is hidden by a CSS guard**: In ComfyUI ≥0.22 (Vue frontend)
  the element `[data-testid="legacy-topbar-container"]` carries the Tailwind class
  `[&:not(:has(*>*:not(:empty)))]:hidden`. It stays `display:none` unless it holds an
  element with non-empty element children (grandchildren of the container). A plain
  `<button>text</button>` only has a text node, not element children, so the guard is
  never satisfied and the container — and anything inside it — remains invisible.
  **Pattern**: use `legacy-topbar-container` only as a landmark. Insert your element into
  its parent (`legacy?.parentElement`) which is the always-visible action-bar row, using
  `insertBefore(btn, legacy)` to place it before the legacy slot.

- **`setup()` runs before Vue mounts**: `app.registerExtension({ setup() })` is called
  during ComfyUI initialisation, before the Vue-based topbar has been added to the DOM.
  Any `document.querySelector` for Vue-rendered elements will return `null`. Use a
  `MutationObserver` on `document.body` and call your insertion function inside it;
  disconnect once the element is found and the button inserted.

### GitHub Project

- Project: "ComfyUI Tiny Model Manager", number `1`, ID `PVT_kwHOAQaKGc4BZ7ME`
- Status field ID: `PVTSSF_lAHOAQaKGc4BZ7MEzhU2a7U`
- Status option IDs: Backlog `f75ad846` | Ready `61e4505c` | In progress `47fc9ee4` | In review `df73e18b` | Done `98236657`
- Size field ID: `PVTSSF_lAHOAQaKGc4BZ7MEzhU2bF8`
- Size option IDs: XS `6c6483d2` | S `f784b110` | M `7515a9f1` | L `817d0097` | XL `db339eb2`
- Requires `project` scope — if missing: `gh auth refresh -s project`
- Issues use `enhancement` label (personal repo has no issue types)
- All issues must be assigned to a milestone. Fetch existing milestones with `gh api repos/Zellione/comfyui-tiny-model-manager/milestones --jq '.[] | {number: .number, title: .title}'`, present them to the user, and offer a "Create new milestone" option if none fit.

### Feature branch rule (MANDATORY)

**Any time the user asks to implement a feature, Claude MUST, before touching any file:**

1. Check the current branch with `git branch`
2. If not already on a correctly named feature branch:
   a. `git checkout main`
   b. `git fetch origin && git pull origin main`
   c. Find the GitHub issue: `gh issue list --search "<feature title>" --json number,title`
   d. Create and link the branch to the issue: `gh issue develop <issue-number> --name <short-name> --checkout`
3. Only then proceed with exploration and implementation.

If there are already uncommitted changes on the wrong branch, stash them (`git stash`), perform steps 2a–2d, then restore (`git stash pop`).

### Feature

If planning and working on a new feature the following steps have to be executed, if not already happened:

0. **Create a GitHub issue and add it to the project in Backlog** (skip if issue already exists):
   - `gh issue create --title "<title>" --body "<description>" --label enhancement`
   - `gh project item-add 1 --owner @me --url <issue-url>`
   - `gh project item-edit --id <item-id> --project-id PVT_kwHOAQaKGc4BZ7ME --field-id PVTSSF_lAHOAQaKGc4BZ7MEzhU2a7U --single-select-option-id f75ad846`
1. **Ensure you are on a correctly named feature branch (see Feature branch rule above)**
2. Enter plan mode and plan feature
3. Wait for approval of plan
4. If plan was approved implement plan
5. **Run all tests and lint for both backend and frontend — only proceed when every check passes with zero failures**
6. **If any file under `frontend/` or `js/` was changed: run `npx ng build` from `frontend/` and confirm it succeeds**
7. If there are no bugs reported: commit changes locally and present the commit to the user
8. **Move the GitHub project item to Done**: `gh project item-edit --id <item-id> --project-id PVT_kwHOAQaKGc4BZ7ME --field-id PVTSSF_lAHOAQaKGc4BZ7MEzhU2a7U --single-select-option-id 98236657`
9. **Wait for explicit user approval before pushing to github (origin)**
10. **Wait for explicit user approval before opening a pull request**
11. **After pushing and opening the PR, poll the SonarCloud quality gate in a loop until it passes:**
    - Check: `mcp__sonarqube__get_project_quality_gate_status` with `projectKey` and `pullRequest`
    - If `status` is `ERROR`: inspect the failing conditions, fix the code (add/improve tests for `new_coverage`, fix issues for ratings), commit, push, then re-check
    - Repeat until `status` is `OK`

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
13. **After pushing, poll the SonarCloud quality gate in a loop until it passes (same loop as in Feature step 11)**