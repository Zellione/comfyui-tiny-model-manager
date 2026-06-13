# Task Completion Checklist

Run all of the following before committing. Every check must pass with zero failures.

## Backend (from project root, Linux)

```bash
PYTHONSAFEPATH=1 ../../../comfy-env/bin/python -m pytest
../../../comfy-env/bin/python -m ruff check py tests conftest.py
../../../comfy-env/bin/python -m ruff format --check py tests conftest.py
```

## Frontend (from `frontend/`)

```bash
npx ng test --watch=false     # Vitest unit tests
npx ng lint                   # ESLint (0 errors required)
npm run format:check          # Prettier (use npm run, not npx prettier)
npx ng build                  # REQUIRED if any file under frontend/ or js/ changed
```

## New files created with Write tool

Run `npx prettier --write <file>` immediately after creating any new `frontend/` file — Write tool does not auto-format and the file will fail `format:check` otherwise.

## Coverage gates (enforced by pre-push hook)

- Backend ≥ 88% lines (`pyproject.toml`)
- Frontend ≥ 74% lines / ≥ 62% functions / ≥ 74% branches (`angular.json`)

## Serena memory update

After any significant change (new service, new convention, structural refactor, new pattern), update the relevant memory before finishing:
- `mem:core` — new files, directories, or project-wide invariants
- `mem:conventions` — new coding patterns, Angular/Python conventions, test patterns
- `mem:tech_stack` — new dependencies or version changes
- `mem:task_completion` — new checklist items or tooling changes
