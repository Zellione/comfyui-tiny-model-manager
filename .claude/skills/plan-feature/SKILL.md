---
name: plan-feature
description: >
  Plan a new feature for the comfyui-tiny-model-manager project. Use this skill whenever the user
  has a feature idea or says something like "I want to add X", "let's plan a feature for Y", or
  "new idea: Z". The skill interviews the user with structured questions until the requirements are
  unambiguous, then writes a YAML spec file into specs/features/ (with the next free F-number) and
  adds an unchecked entry to the README.md features checklist. Invoke this skill even for vague
  ideas — the interview process exists precisely to sharpen them.
---

# plan-feature

You are planning a new feature for the **comfyui-tiny-model-manager** project.

The project is an Angular 21.2 + Python/aiohttp ComfyUI custom node. Models and LoRAs are
downloaded from CivitAI and HuggingFace. The UI has three main pages: Models (library browser),
Download (search + paste-a-link), and Model Detail. Settings live in ComfyUI's native settings
panel. The backend uses SQLite via aiosqlite and httpx for external API calls.

## Step 1 — Determine the next feature number

Run:
```bash
ls specs/features/ | sort | tail -1
```
Parse the highest `fNN` prefix and add 1. That is the new feature ID (e.g. `F-38`).

## Step 2 — Interview the user

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

6. **Dependencies** — Does this build on an existing feature? (Reference the README checklist for
   known F-numbers.)

7. **Edge cases & failure modes** — What should happen when inputs are invalid, the network is
   down, or the external API returns an error?

### Guidelines for asking

- Keep each question short and concrete — avoid open-ended "tell me everything" prompts.
- Where a choice is binary (yes/no), offer it as a two-option select.
- Where a choice is a pick-one from a known set (e.g. which pages), use multiSelect.
- It is fine to pre-fill a reasonable guess as the first option and let the user correct it.

## Step 3 — Confirm your understanding

Before writing anything, post a brief plain-text summary of your understanding back to the user:

```
Feature F-NN — <Title>

Summary: <2-3 sentences on what the feature does>

Requirements I'll capture:
• <req 1>
• <req 2>
• ...

API changes: <none | list of endpoints>
DB changes: <none | description>
Depends on: <none | F-XX, F-YY>

Shall I write the spec?
```

Wait for the user to confirm (or correct) before proceeding.

## Step 4 — Write the YAML spec

Create `specs/features/fNN-<kebab-title>.yaml` following the existing format exactly:

```yaml
feature_id: F-NN
title: "Human-readable title"
requirements:
  - "Requirement phrased as an observable behaviour, not an implementation detail"
  - "Use present tense: 'The button shows…', 'When the user…', 'The backend returns…'"
  - "Quote strings that contain colons, pipes, or markdown — YAML is picky"
api:                          # omit section if no API changes
  - "METHOD /path → description of request/response"
depends_on:                   # omit section if no dependencies
  - F-XX
```

**Requirement writing rules:**
- Describe *what* the system does, not *how* to implement it.
- One requirement = one observable behaviour or invariant.
- Include failure / edge-case handling as explicit requirements.
- Keep each bullet to 1-2 sentences; split if longer.

## Step 5 — Update README.md

Add an **unchecked** entry at the end of the features checklist (before the `---` separator after
the list):

```markdown
- [ ] F-NN — <Title> — <one-line description matching the spec title>
```

## Step 6 — Report completion

Tell the user:
- The path to the new spec file
- The README.md line that was added
- A reminder that the feature can now be implemented by saying "implement F-NN"
