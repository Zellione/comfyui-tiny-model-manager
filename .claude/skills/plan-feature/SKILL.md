---
name: plan-feature
description: >
  Plan a new feature for the comfyui-tiny-model-manager project. Use this skill whenever the user
  has a feature idea or says something like "I want to add X", "let's plan a feature for Y", or
  "new idea: Z". The skill interviews the user with structured questions until the requirements are
  unambiguous, then creates a GitHub issue in the project backlog. Invoke this skill even for vague
  ideas — the interview process exists precisely to sharpen them.
---

# plan-feature

You are planning a new feature for the **comfyui-tiny-model-manager** project.

The project is an Angular 21.2 + Python/aiohttp ComfyUI custom node. Models and LoRAs are
downloaded from CivitAI and HuggingFace. The UI has three main pages: Models (library browser),
Download (search + paste-a-link), and Model Detail. Settings live in ComfyUI's native settings
panel. The backend uses SQLite via aiosqlite and httpx for external API calls.

## Step 1 — Pre-interview research (do this BEFORE asking questions)

Run both commands in parallel before opening the `AskUserQuestion` dialog:

```bash
# Fetch all open enhancement issues to find candidates for related issues
gh issue list --label enhancement --limit 60 --json number,title,body

# Fetch existing milestones
gh api repos/Zellione/comfyui-tiny-model-manager/milestones \
  --jq '.[] | {number: .number, title: .title}'
```

Use the issue list to:
- **Pre-select a size suggestion** — reason about affected areas and complexity from the user's
  description and propose the most likely size as the first option in the size question.
- **Pre-select related issue candidates** — compare the feature idea against every open issue's
  title and body; include any issue that shares pages, data models, or API surface as an option
  in the related-issues question. Always propose at least one candidate if any exists; never show
  an empty related-issues question.

## Step 2 — Interview the user

Use the `AskUserQuestion` tool to run **one round** of structured questions. Aim to cover all the
dimensions below in a single round; follow up with a second round only if a critical ambiguity
remains after the first answers.

**`AskUserQuestion` accepts at most 4 questions per call.** Merge or drop lower-priority questions
to stay within the limit.

### Round 1 questions to ask

Cover these topics — adapt the wording to what the user already told you:

1. **Title & purpose** — What is the one-line name for this feature, and what user problem does it
   solve?

2. **Affected areas** — Which pages / components does this touch?
   - Models page (library)
   - Download page (search + paste-a-link)
   - Model Detail page
   - Settings panel
   - Backend only (no UI)
   - New page or panel

3. **Core behaviour** — Walk through the happy path step by step. What does the user do, what does
   the system do, and what does the user see as a result?

4. **New API endpoints** — Does this need new or changed HTTP endpoints? If yes: method, path, and
   what data goes in / comes back.

5. **Backend / DB changes** — New tables, new columns, new service logic, new external API calls?

6. **Related issues** — Present the candidates you identified in Step 1. For each candidate, label
   it with your suggested relationship type and a one-sentence rationale so the user can accept or
   correct it. Always include a "None" option. Relationship types:
   - `BLOCKED_BY` — this feature cannot be built until the other is done
   - `BLOCKS` — the other feature cannot be built until this is done
   - `RELATED_TO` — shares scope, data, or UI surface without a hard ordering dependency

7. **Edge cases & failure modes** — What should happen when inputs are invalid, the network is
   down, or the external API returns an error?

8. **Size estimate** — How big is this feature? Lead with your suggested size (derived from the
   number of affected areas, whether backend/DB changes are needed, and overall scope) as the first
   option, labelled "(Recommended)". Include a one-sentence rationale for your suggestion.
   - XS — a single small change (< 1 hour)
   - S — a focused change touching 1–2 files (half a day)
   - M — moderate scope, a few components or endpoints (1–2 days)
   - L — significant scope, multiple areas or complex logic (3–5 days)
   - XL — large feature, major new subsystem (> 1 week)

### Guidelines for asking

- Keep each question short and concrete — avoid open-ended "tell me everything" prompts.
- Where a choice is binary (yes/no), offer it as a two-option select.
- Where a choice is a pick-one from a known set (e.g. which pages), use multiSelect.
- **Always pre-fill your best guess as the first option** — for size and related issues especially,
  never present a blank slate. Reason from what the user told you and lead with a recommendation.

## Step 3 — Confirm your understanding

Before writing anything, post a brief plain-text summary of your understanding back to the user:

```
Feature — <Title>

Summary: <2-3 sentences on what the feature does>

Requirements I'll capture:
• <req 1>
• <req 2>
• ...

API changes: <none | list of endpoints>
DB changes: <none | description>
Size: <XS | S | M | L | XL> — <one-sentence rationale>
Related issues: <none | #NN (blocked by) | #NN (blocks) | #NN (related to)>

Shall I create the GitHub issue?
```

Wait for the user to confirm (or correct) before proceeding.

## Step 4 — Create the GitHub issue and add to project backlog

Build the issue body from the confirmed requirements:

```markdown
## Summary
<2-3 sentence description>

## Requirements
- <requirement 1>
- <requirement 2>

## API changes
<none | endpoint descriptions>

## DB changes
<none | description>
```

Then run:

```bash
# Create the issue
gh issue create --title "<title>" --body "<body above>" --label enhancement

# Assign to a milestone
# 1. List existing milestones:
#    gh api repos/Zellione/comfyui-tiny-model-manager/milestones --jq '.[] | {number: .number, title: .title}'
# 2. Present them to the user via AskUserQuestion (include "Create new milestone" as an option).
# 3. If the user picks an existing one, use its number directly.
#    If the user wants a new one, create it first:
#    gh api repos/Zellione/comfyui-tiny-model-manager/milestones --method POST --field title="<name>" --jq '.number'
# 4. Assign the issue:
gh api repos/Zellione/comfyui-tiny-model-manager/issues/<number> --method PATCH --field milestone=<milestone-number>

# Add to the GitHub project
gh project item-add 1 --owner @me --url <issue-url>

# Set status to Backlog
gh project item-edit \
  --id <item-id> \
  --project-id PVT_kwHOAQaKGc4BZ7ME \
  --field-id PVTSSF_lAHOAQaKGc4BZ7MEzhU2a7U \
  --single-select-option-id f75ad846

# Set size (XS=6c6483d2 | S=f784b110 | M=7515a9f1 | L=817d0097 | XL=db339eb2)
gh project item-edit \
  --id <item-id> \
  --project-id PVT_kwHOAQaKGc4BZ7ME \
  --field-id PVTSSF_lAHOAQaKGc4BZ7MEzhU2bF8 \
  --single-select-option-id <size-option-id>
```

If there are related issues, link them using the approach that matches the relationship type.

**GitHub GraphQL API only exposes two programmable dependency types — `BLOCKED_BY` and `BLOCKS`.**
`RELATED_TO` has no dedicated mutation and can only be set via the GitHub web UI.

### BLOCKED_BY — new issue is blocked by an existing issue

```bash
NEW_ID=$(gh api repos/Zellione/comfyui-tiny-model-manager/issues/<new-number> --jq '.node_id')
OTHER_ID=$(gh api repos/Zellione/comfyui-tiny-model-manager/issues/<other-number> --jq '.node_id')

gh api graphql -f query='
mutation($issueId: ID!, $blockingIssueId: ID!) {
  addBlockedBy(input: { issueId: $issueId, blockingIssueId: $blockingIssueId }) {
    issue { url }
    blockingIssue { url }
  }
}' -f issueId="$NEW_ID" -f blockingIssueId="$OTHER_ID"
```

### BLOCKS — new issue blocks an existing issue

Swap the roles: the existing issue is blocked by the new issue.

```bash
gh api graphql -f query='
mutation($issueId: ID!, $blockingIssueId: ID!) {
  addBlockedBy(input: { issueId: $issueId, blockingIssueId: $blockingIssueId }) {
    issue { url }
    blockingIssue { url }
  }
}' -f issueId="$OTHER_ID" -f blockingIssueId="$NEW_ID"
```

### RELATED_TO — no API mutation available

Add a cross-reference comment (creates a visible timeline link) and tell the user to set the
"Related to" relationship manually via the GitHub web UI:

```bash
gh issue comment <new-number> --body "Related to #<other-number>."
```

Then inform the user: "The 'Related to' relationship must be set manually in the GitHub web UI —
open issue #<new-number>, find the relationship section, and add #<other-number> as 'Related to'."

## Step 5 — Report completion

Tell the user:
- The GitHub issue URL
- A reminder that the feature can now be implemented by saying "implement <title>"
