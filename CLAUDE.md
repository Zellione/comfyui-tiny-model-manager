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
# Unit tests (Vitest, no browser needed)
npx ng test --watch=false

# ESLint (0 errors required; warnings allowed)
npx ng lint

# Prettier format check
npx prettier --check "src/**/*.ts" "src/**/*.html" "src/**/*.scss"

# Production build — REQUIRED after any change to frontend/ or js/
npx ng build
```

**If you changed any file under `frontend/` or `js/`, you MUST run `npx ng build` and confirm it succeeds before committing. A passing test suite does not substitute for a successful build.**

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

### Feature

If planning and working on a new feature already specified in @PRD.md the following steps have to be executed, if not already happened:

1. Change Branch to main
2. Fetch from origin and pull changes
3. Create git branch containing feature name in the format `F-12-very-short-name`
4. Enter plan mode and plan feature
5. Wait for approval of plan
6. If plan was approved implement plan
7. **Run all tests and lint for both backend and frontend — only proceed when every check passes with zero failures**
8. **If any file under `frontend/` or `js/` was changed: run `npx ng build` from `frontend/` and confirm it succeeds**
9. If there are no bugs reported: commit changes and push them to github (origin)
10. Open pull request

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
9. If there are no bugs reported: commit changes and push them to github (origin)
10. Check if pull request updated