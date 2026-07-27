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

## SonarQube: verify locally, don't round-trip through CI

The quality gate can pass while `python:S3776` (cognitive complexity > 15) and other
issues sit OPEN — a green gate is not "zero issues". After a PR analysis lands, check
both:

- `mcp__sonarqube__get_project_quality_gate_status` (projectKey + pullRequest)
- `mcp__sonarqube__search_sonar_issues_in_projects` (pullRequestId, issueStatuses
  OPEN/CONFIRMED) — plus `search_security_hotspots`

Before pushing a fix, run `mcp__sonarqube__analyze_code_snippet` on the full file
(`language: ["python"]`, `scope: ["MAIN"]`) and confirm `issueCount: 0`. It reports the
exact complexity number, so a fix that only gets 25 → 16 is caught in seconds instead of
costing another CI cycle.

Long functions usually trip S3776 because a nested loop is doing two jobs. Split by
responsibility (per-item conversion helper, per-candidate match helper) rather than
shuffling conditionals around.

## CI hangs

`gh run view <id> --log | tail` — the last test file printed is the one that hung; pytest
emits a line per file as it completes. Go there before theorising. In F-92 the log
pointed at `test_routes_download.py`, which ruled out the plausible-but-wrong suspect in
a different file.

## Serena memory update

After any significant change (new service, new convention, structural refactor, new pattern), update the relevant memory before finishing:
- `mem:core` — new files, directories, or project-wide invariants
- `mem:conventions` — new coding patterns, Angular/Python conventions, test patterns
- `mem:tech_stack` — new dependencies or version changes
- `mem:task_completion` — new checklist items or tooling changes
