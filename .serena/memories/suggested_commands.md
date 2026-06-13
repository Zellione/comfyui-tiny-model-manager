# Suggested Commands

All backend commands run from the **project root**. All frontend commands run from **`frontend/`**.

## Backend (Linux)

```bash
PYTHONSAFEPATH=1 ../../../comfy-env/bin/python -m pytest              # run tests
../../../comfy-env/bin/python -m ruff check py tests conftest.py      # lint
../../../comfy-env/bin/python -m ruff format --check py tests conftest.py  # format check
../../../comfy-env/bin/python -m ruff format py tests conftest.py     # auto-format
../../../comfy-env/bin/python -m pip install -r requirements-dev.txt  # install dev deps (once)
```

## Frontend

```bash
npm install                               # once, or after package.json changes
npx ng build                             # production build → web/
npx ng build --watch --configuration development  # dev watch mode
npx ng test --watch=false                # unit tests (Vitest, no browser)
npx ng lint                              # ESLint
npm run format:check                     # Prettier check (use npm run, not npx prettier)
npm run format                           # Prettier auto-fix
```

## Git hooks (one-time per clone)

```bash
git config core.hooksPath .githooks     # activates pre-push coverage gate
```
