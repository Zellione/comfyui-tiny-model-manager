#!/usr/bin/env bash
# Single Stop gate for this repo.
#
# Design rule: a normal turn must end SILENTLY. Every check below is gated on a
# condition that is false most of the time, and the script emits at most one
# message. Exit 2 = blocking feedback to Claude, exit 0 = quiet.
set -uo pipefail

input=$(cat)

# Never re-fire while Claude is already reacting to a previous stop-hook block.
printf '%s' "$input" | jq -e '.stop_hook_active == true' >/dev/null 2>&1 && exit 0

cd "${CLAUDE_PROJECT_DIR:-$PWD}" 2>/dev/null || exit 0
git rev-parse --git-dir >/dev/null 2>&1 || exit 0

# ---------------------------------------------------------------------------
# 1. Ruff gate - backend lint/format must be clean before finishing.
#    Fires only when backend files are actually dirty.
# ---------------------------------------------------------------------------
PY=../../../comfy-env/bin/python
if [ -x "$PY" ] && [ -n "$(git status --porcelain -- py tests conftest.py 2>/dev/null)" ]; then
  strip_noise() { printf '%s\n' "$1" | grep -vE 'RuntimeWarning|<frozen site>'; }

  if ! out=$("$PY" -m ruff check py tests conftest.py 2>&1); then
    { echo "Stop gate: ruff check failed. Fix before finishing."; strip_noise "$out"; } >&2
    exit 2
  fi
  if ! out=$("$PY" -m ruff format --check py tests conftest.py 2>&1); then
    { echo "Stop gate: ruff format check failed. Run ruff format."; strip_noise "$out"; } >&2
    exit 2
  fi
fi

git_status=$(git status --porcelain 2>/dev/null)
branch=$(git symbolic-ref --quiet --short HEAD 2>/dev/null || echo "")

# ---------------------------------------------------------------------------
# 2. Stale project board items - issue closed but still "In progress".
#    Only checked once work has landed (on main, clean tree), so feature
#    branches stay quiet, and only warned once per distinct set of offenders.
# ---------------------------------------------------------------------------
if [ -z "$git_status" ] && [ "$branch" = "main" ] && command -v gh >/dev/null 2>&1; then
  stamp="$(git rev-parse --git-dir)/stale-project-items"

  in_progress=$(gh project item-list 1 --owner @me --format json --limit 200 2>/dev/null |
    jq -r '.items[] | select(.status == "In progress") | .content.number // empty' 2>/dev/null)

  stale=""
  for issue in $in_progress; do
    if [ "$(gh issue view "$issue" --json state --jq .state 2>/dev/null)" = "CLOSED" ]; then
      stale="$stale $issue"
    fi
  done
  stale=$(printf '%s' "$stale" | tr -s ' ' | sed 's/^ //')

  if [ -z "$stale" ]; then
    rm -f "$stamp"
  elif [ "$stale" != "$(cat "$stamp" 2>/dev/null)" ]; then
    printf '%s' "$stale" >"$stamp"
    echo "Stop gate: issue(s) $stale are closed but still 'In progress' on the project board. Move them to Done (Feature workflow step 8) before finishing." >&2
    exit 2
  fi
fi

# ---------------------------------------------------------------------------
# 3. Serena memory nudge - non-blocking, only when code is dirty and no
#    memory file was touched this turn.
# ---------------------------------------------------------------------------
if printf '%s\n' "$git_status" | awk '{print $NF}' | grep -qE '\.(py|ts|tsx|js|jsx|html|scss|css)$' &&
  ! printf '%s\n' "$git_status" | grep -q '\.serena/memories/'; then
  echo '{"hookSpecificOutput":{"hookEventName":"Stop","additionalContext":"Uncommitted code changes are present and no Serena memory was touched. If this turn introduced new conventions, patterns, services, or structural changes, update the relevant memory (mem:core, mem:conventions, mem:tech_stack, mem:task_completion) via mcp__serena__write_memory."}}'
fi

exit 0
