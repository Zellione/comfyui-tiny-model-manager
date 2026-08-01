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

**RESOLVED (issue #118).** Root cause: the test suite performed real DNS lookups. `getaddrinfo`
runs in asyncio's default `ThreadPoolExecutor`, and pytest-asyncio's per-test loop teardown calls
`loop.shutdown_default_executor()` **without a timeout**, joining that thread forever when a CI
resolver stalls. The hang was therefore in *teardown*, which is why the stalling test never printed
a dot and why an orphan Python process was left behind.

The fix is the autouse `block_network` fixture in `tests/conftest.py`: any non-loopback
`getaddrinfo`/`connect` raises instead of hanging. **Mock every outbound request** — see
`mem:conventions` for the two traps (tests relying on a slow real request to stay `downloading`,
and a network call hiding behind an already-mocked seam in `refetch_catalog_metadata`).

Two earlier attempts did *not* fix it and should not be retried: the queue/event-loop binding fix
(#119, a real bug but not this one) and bounding `_DOWNLOAD_TIMEOUT` (httpx timeouts cannot
interrupt a blocked `getaddrinfo` on a thread). `faulthandler_timeout = 60` (#122) is what finally
produced the decisive stack trace — when a stall is intermittent and unreproducible, invest in
instrumentation rather than another candidate fix.

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
