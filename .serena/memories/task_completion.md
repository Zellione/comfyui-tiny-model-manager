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

Before pushing a fix, run `mcp__sonarqube__analyze_code_snippet` on the full file and
confirm `issueCount: 0`. It reports the exact complexity number, so a fix that only gets
25 → 16 is caught in seconds instead of costing another CI cycle.

Argument shape (verified 2026-07): the content parameter is **`fileContent`**, not
`codeSnippet`, and `language` is a **single short string** — `js`, `ts`, `python`, `css`
— not an array and not `javascript`/`typescript`, both of which error out with the list of
valid keys. A neat trick: put the old and new implementation in one snippet and check
which line numbers come back flagged, which proves the fix clears the rule.

**A PR annotation reflects the last completed analysis.** A fix that is committed but not
pushed keeps showing the old warning — check for unpushed commits before concluding the
fix did not work.

Long functions usually trip S3776 because a nested loop is doing two jobs. Split by
responsibility (per-item conversion helper, per-candidate match helper) rather than
shuffling conditionals around.

## CI hangs

`gh run view <id> --log | tail` — the last test file printed is the one that hung; pytest
emits a line per file as it completes. Go there before theorising. In F-92 the log
pointed at `test_routes_download.py`, which ruled out the plausible-but-wrong suspect in
a different file.

**This is a recurring, still-unresolved flake — see issue #118 and the "Backend CI hang"
entry in `mem:conventions`.** It has now appeared across F-92 and F-93, always stalling at
the same place: the end of `tests/test_routes_catalog.py`, with `test_routes_download.py`
emitting nothing (pytest buffers a file's name without a trailing newline, so the hanging
file looks absent rather than incomplete). It is intermittent — the same commit can pass in
~30 s — and has never reproduced locally.

Two things are already in place, so don't re-add them:
- `timeout-minutes` on every CI job, so a hang dies in 10 minutes rather than 6 hours.
- `faulthandler_timeout = 60` in `pyproject.toml`, so the next stall dumps every thread's
  stack into the log. **When it next hangs, read that stack first** — it names the stuck
  test and line, which is the evidence the investigation has been missing.

Beware of declaring this fixed. A queue/event-loop bug found while chasing it (#119) was
real, was fixed, and did **not** stop the hang; it was reported as resolved and then
recurred on the next PR.

## GitHub Project board

The project has automation that sets an item's Status when its PR is opened. It **overrides
a manual status change**: an item moved to Done before its PR was opened came back as
"In progress". Set the final status *after* the PR is merged, and re-check the board rather
than assuming an earlier `item-edit` stuck.

## Serena memory update

After any significant change (new service, new convention, structural refactor, new pattern), update the relevant memory before finishing:
- `mem:core` — new files, directories, or project-wide invariants
- `mem:conventions` — new coding patterns, Angular/Python conventions, test patterns
- `mem:tech_stack` — new dependencies or version changes
- `mem:task_completion` — new checklist items or tooling changes
