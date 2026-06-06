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

## Step 1 — Interview the user

Use the `AskUserQuestion` tool to run **one round** of structured questions. Aim to cover all the
dimensions below in a single round; follow up with a second round only if a critical ambiguity
remains after the first answers.

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

6. **Edge cases & failure modes** — What should happen when inputs are invalid, the network is
   down, or the external API returns an error?

### Guidelines for asking

- Keep each question short and concrete — avoid open-ended "tell me everything" prompts.
- Where a choice is binary (yes/no), offer it as a two-option select.
- Where a choice is a pick-one from a known set (e.g. which pages), use multiSelect.
- It is fine to pre-fill a reasonable guess as the first option and let the user correct it.

## Step 2 — Confirm your understanding

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

Shall I create the GitHub issue?
```

Wait for the user to confirm (or correct) before proceeding.

## Step 3 — Create the GitHub issue and add to project backlog

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

# Add to the GitHub project
gh project item-add 1 --owner @me --url <issue-url>

# Set status to Backlog
gh project item-edit \
  --id <item-id> \
  --project-id PVT_kwHOAQaKGc4BZ7ME \
  --field-id PVTSSF_lAHOAQaKGc4BZ7MEzhU2a7U \
  --single-select-option-id f75ad846
```

## Step 4 — Report completion

Tell the user:
- The GitHub issue URL
- A reminder that the feature can now be implemented by saying "implement <title>"
