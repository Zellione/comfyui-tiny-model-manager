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

## Doc-only changes skip CI entirely (#163)

`.github/workflows/ci.yml` carries a `paths-ignore` list on **both** the `push` and
`pull_request` triggers: `**/*.md`, `.serena/memories/**`, `docs/**`, `LICENSE`,
`.gitattributes`. The list is duplicated because GitHub Actions does not support YAML
anchors — keep the two copies in sync.

`paths-ignore` is exclusive: a run is skipped only when *every* changed path matches. A PR
touching a `.md` file **and** a `.py` file still runs the whole matrix. Never convert this
to a `paths:` allowlist — that would silently skip newly added file types.

Consequences for the project workflow:
- **A doc-only PR publishes no Sonar analysis, so there is no quality gate.**
  `get_project_quality_gate_status` 404s for that PR. That is expected, not a failure —
  do not poll waiting for a gate that will never appear (CLAUDE.md feature step 11).
- Safe today because `main` has **no** `required_status_checks` (verified via
  `gh api repos/Zellione/comfyui-tiny-model-manager/branches/main/protection` — the key is
  absent; only reviews / linear-history rules are set). If required checks are ever turned
  on, a skipped workflow reports no status at all and the PR would stay pending forever;
  the workaround is a companion job that reports success for the ignored paths.

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

**An open PR means `In review` (`df73e18b`), never Done.** Done (`98236657`) is for merged work
only. Setting it at commit time is wrong twice over: the work is not finished while the PR is
open, and the board automation that fires on PR-open **overrides a manual status change** — an
item moved to Done before its PR existed came back as "In progress". Re-check the board rather
than assuming an earlier `item-edit` stuck.

This was corrected by the user on F-144 after the CLAUDE.md feature checklist told Claude to set
Done right after committing; that step now reads `In review` at PR-open and Done after merge.

This silently reverted three features in a row (#130, #137, #139 — all closed and merged,
all still sitting in "In progress"). A Stop hook now catches it: see the stale-item check in
`.claude/hooks/stop-gate.sh`. Re-checking the board after the merge is still the primary fix —
the hook is only the safety net.

Move an item to Done with:
```bash
gh project item-edit --id <item-id> --project-id PVT_kwHOAQaKGc4BZ7ME \
  --field-id PVTSSF_lAHOAQaKGc4BZ7MEzhU2a7U --single-select-option-id 98236657
```
Verify with `gh project item-list 1 --owner @me --format json` — `.items[].status` must read Done.

## Claude Code Stop hooks

All project Stop-hook logic lives in **one** script, `.claude/hooks/stop-gate.sh`, wired
into `.claude/settings.json` as a single entry. Add new checks there rather than appending
another hook entry.

Design rule: **a normal turn must end silently.** Every check is gated on a condition that
is false most of the time, and the script emits at most one message (exit 2 = blocking
feedback, exit 0 = quiet). Current checks: ruff gate (backend files dirty), stale project
board item (clean tree on main, deduped via a stamp in `.git/stale-project-items`), Serena
memory nudge (code dirty and no memory touched).

Gotchas learned building it:
- Honour `.stop_hook_active` from the hook's stdin JSON or a blocking hook loops.
- Never name a shell variable `status` — it is read-only in zsh.
- Ungated hooks are the real source of reminder spam. A user-level Stop hook in
  `~/.claude/settings.json` fires on *every* turn and cannot be suppressed from project
  settings; gate it or delete it there.

## Serena memory update

After any significant change (new service, new convention, structural refactor, new pattern), update the relevant memory before finishing:
- `mem:core` — new files, directories, or project-wide invariants
- `mem:conventions` — new coding patterns, Angular/Python conventions, test patterns
- `mem:tech_stack` — new dependencies or version changes
- `mem:task_completion` — new checklist items or tooling changes
