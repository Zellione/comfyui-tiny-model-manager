# F-38: Visual Upgrade — Model Detail View + Delete

_Date: 2026-05-31_

## Overview

Redesign the model detail page to match the modern design system already used by the rest of the app. Add a separate Edit mode so the read view is clean. Add a delete-with-confirmation flow accessible directly from the detail page. No new backend tables in this feature — repo file listing (F-39) is out of scope.

## Scope

| In scope | Out of scope |
|---|---|
| Visual redesign of model-detail component | Repo files from CivitAI/HF (F-39) |
| Separate Edit / read modes | Open folder button |
| Delete model from detail page | Author metadata field |
| Gallery upgrade (16:9 main + thumbnail strip) | Bulk operations |
| Click-to-copy trigger keywords line | |
| `size_bytes` added to metadata API response | |

## Backend Changes

### `py/routes/models.py` — metadata endpoint

Add `size_bytes` (integer, bytes) to the metadata GET response. Resolved by calling `os.path.getsize(model_file_path)` at request time. Return `0` if the file does not exist (e.g. metadata exists but file was externally removed).

No other backend changes. The existing `DELETE /api/models/{type}/{path}` endpoint is already implemented and used by the frontend service.

## Frontend Changes

### `frontend/src/app/services/model.ts`

Add `size_bytes?: number` to the `ModelMeta` interface.

### `frontend/src/app/pages/model-detail/model-detail.ts`

**New signals:**

| Signal | Type | Purpose |
|---|---|---|
| `isEditing` | `signal(false)` | Toggles read / edit card |
| `showDeleteConfirm` | `signal(false)` | Shows inline delete confirmation banner |
| `deleting` | `signal(false)` | Spinner on Confirm Delete button |
| `copied` | `signal(false)` | "Copied ✓" feedback on keywords copy button |
| `galleryIdx` | `signal(0)` | Active index in media thumbnail strip |

**New methods:**

| Method | Behaviour |
|---|---|
| `toggleEdit()` | Sets `isEditing(true)`, resets `editMeta` from `meta()` |
| `cancelEdit()` | Resets `editMeta` from `meta()`, sets `isEditing(false)` |
| `startDelete()` | Sets `showDeleteConfirm(true)` |
| `confirmDelete()` | Sets `deleting(true)`, calls `modelService.deleteModel()`. On success: notification + `router.navigate(['/models'])`. On error: notification + `deleting(false)` + `showDeleteConfirm(false)` |
| `copyKeywords()` | Joins `editMeta.trigger_words` as comma-separated string, writes to clipboard via `navigator.clipboard.writeText` (falls back to `document.execCommand('copy')` when Clipboard API is unavailable), sets `copied(true)`, resets after 1400 ms |
| `setGalleryIdx(i)` | Sets `galleryIdx(i)` |
| `formattedSize()` | Formats `meta().size_bytes` as human-readable string (KB / MB / GB). Returns `''` if absent. |

Existing methods (`save`, `refetch`, `addToWorkflow`, `addTriggerWord`, `removeTriggerWord`, `addTag`, `removeTag`, `mediaUrl`) are preserved unchanged.

### `frontend/src/app/pages/model-detail/model-detail.html`

Full rewrite. Structure:

```
<div class="detail-page">

  <!-- Header bar -->
  <div class="detail-back">
    [← Back to Models]  [breadcrumbs]  <spacer>  [Edit btn]  [Uninstall btn]
  </div>

  <!-- Delete confirm banner (only when showDeleteConfirm()) -->
  <div class="delete-confirm-banner">
    "Delete this model? ..."
    [Cancel]  [Confirm Delete / Deleting…]
  </div>

  @if (loading()) { <loading state> }
  @else if (error()) { <error state> }
  @else if (meta()) {

    <!-- READ VIEW (when !isEditing()) -->
    <div class="detail-card">
      <!-- Card header: eyebrow · title · source link -->
      <!-- Gallery: 16:9 main + thumbnail strip -->
      <!-- Tags row -->
      <!-- Keywords section: copyable line + chips -->
      <!-- Files in this model section -->
      <!-- Description section -->
    </div>

    <!-- EDIT VIEW (when isEditing()) -->
    <div class="detail-card">
      <!-- Card header: title + [Cancel] [Save] -->
      <!-- Edit form: description, model type, base model, trigger words, tags, source (read-only) -->
      <!-- Secondary actions: [Re-fetch Metadata] [Add to Workflow] -->
    </div>

  }
</div>
```

**Header bar** (`display: flex; align-items: center; gap: 14px; margin-bottom: 18px`):
- Back button: `btn-secondary` style, text "← Back to Models", `routerLink="/models"`
- Breadcrumbs: `font-family: var(--font-mono); font-size: 12px; color: var(--text-3)` — `Installed / {modelType} / {modelBasename}`
- Spacer: `flex: 1`
- Edit button: `btn-secondary` — hidden when `isEditing()` or `showDeleteConfirm()` is true
- Uninstall button: ghost style with `color: var(--danger)` hover state — hidden when `showDeleteConfirm()` is true; calls `startDelete()`

**Delete confirm banner** (only rendered when `showDeleteConfirm()` is true):
- `background: var(--danger-soft); border: 1px solid var(--danger); border-radius: var(--radius-lg); padding: 16px 20px`
- Text: "Delete this model? The file and all saved metadata will be permanently removed. This cannot be undone."
- Buttons: `[Cancel]` (btn-secondary, calls `showDeleteConfirm.set(false)`) + `[Confirm Delete]` (btn-danger, calls `confirmDelete()`, disabled + text "Deleting…" when `deleting()`)

**Card header** (padded block, `border-bottom: 1px solid var(--border)`):
- Eyebrow: monospace, 11px, `var(--text-3)`, uppercase — segments: `modelType`, `meta().base_model`, `formattedSize()` — joined by ` · `, empty segments omitted
- Title: `{modelBasename}`, 26px, weight 600, `letter-spacing: -0.02em`
- Right: "View on CivitAI ↗" / "View on HuggingFace ↗" — only when `meta().source_url` is set

**Gallery** (`padding: 20px 22px`):
- Main: `aspect-ratio: 16/9; border-radius: var(--radius); overflow: hidden`. Shows `meta().media[galleryIdx()]` image/video. If no media: placeholder div with `background: var(--surface-2)` and diagonal stripe overlay.
- Thumbnail strip (only when `meta().media.length > 1`): horizontal flex row, `gap: 6px`, `overflow-x: auto`. Each thumb 64×64, `border-radius: 6px`, `cursor: pointer`, `border: 1px solid transparent`. Active: `border-color: var(--accent)`.

**Tags row** (`padding: 0 22px 18px`): hidden when `meta().tags` is empty. "Tags" label (10px, uppercase, `var(--text-3)`) + `.badge` chips.

**Keywords section** (`padding: 0 22px; margin-bottom: 18px`):
Inner card: `background: var(--surface-2); border: 1px solid var(--border); border-radius: var(--radius); padding: 14px 16px`.
- Label: "Trigger keywords" — 10.5px, uppercase, `var(--text-3)`
- No trigger words: `"No trigger words for this model"` in `var(--text-3)`
- Has trigger words:
  - Clickable monospace line: `background: var(--bg-2); border: 1px solid var(--border); border-radius: 8px; padding: 10px 12px; cursor: pointer` — `<code>` with comma-joined words + `[Copy / Copied ✓]` button
  - Chips row: `display: flex; flex-wrap: wrap; gap: 6px; margin-top: 10px` — each chip `background: var(--accent-soft); color: var(--accent)`

**Files in this model** (`padding: 18px 22px`):
- Header: "Files in this model" label (11px, uppercase, `var(--text-3)`) + subtitle showing folder path in monospace
- One row per file (single downloaded file in F-38):
  - Green check icon (`color: var(--success)`)
  - Filename in `var(--font-mono)`
  - Size formatted
  - "Downloaded" pill (`background: color-mix(in oklch, var(--success) 14%, transparent); color: var(--success)`)

**Description** (`border-top: 1px solid var(--border); padding: 22px`): hidden when `meta().description` is empty. "About this model" label + description text in `var(--text-2)`, `line-height: 1.65`.

**Edit panel** (replaces detail card when `isEditing()` is true):
- Same outer `.detail-card` shell
- Header: title + right-side `[Cancel]` + `[Save / Saving…]` buttons
- Body: `display: flex; flex-direction: column; gap: 1rem; padding: 22px`
  - Description textarea (6 rows)
  - Model Type select
  - Base Model text input
  - Trigger Words: chips with × remove + add-word input + Add button
  - Tags: same pattern, accent-soft chip color
  - Source info (read-only badge + link)
- Secondary actions row: `[Re-fetch Metadata]` + `[Add to Workflow]`

### `frontend/src/app/pages/model-detail/model-detail.scss`

Full rewrite, scoped to component. Uses only existing global tokens. Key new classes:

- `.detail-page` — wrapper
- `.detail-back` — header bar flex row
- `.crumbs` / `.crumb-sep` / `.crumb-active` — breadcrumb typography
- `.btn-uninstall` — ghost danger button
- `.delete-confirm-banner` — danger-soft card
- `.detail-card` — main card shell
- `.card-header` — top header block with border-bottom
- `.detail-eyebrow` — monospace metadata line
- `.detail-title` — 26px model name
- `.dl-detail-source` — source link button
- `.gallery-main` — 16:9 container
- `.gallery-thumbs` / `.gallery-thumb` / `.gallery-thumb.active` — thumbnail strip
- `.keywords-card` / `.keywords-label` / `.keywords-line` / `.keywords-chips` — keywords section
- `.files-section` / `.file-row` / `.file-status` / `.pill-ok` — files section
- `.edit-panel-body` — edit form wrapper
- `.trigger-words` / `.chips` / `.chip` / `.add-word` — preserved from current, restyled

## Testing

### Backend

**`tests/test_routes_models.py`** — add:
- `size_bytes` present in metadata GET response, is an integer ≥ 0

### Frontend

**`model-detail.spec.ts`** — add/update:

| Test | Asserts |
|---|---|
| `toggleEdit()` | `isEditing()` becomes true |
| `cancelEdit()` | `isEditing()` becomes false; `editMeta` reset from `meta()` |
| `startDelete()` | `showDeleteConfirm()` becomes true |
| `confirmDelete()` success | `deleteModel()` called; `router.navigate` called with `['/models']` |
| `confirmDelete()` error | `deleting()` false; `showDeleteConfirm()` false; error notification shown |
| `copyKeywords()` | `copied()` true immediately; false after 1400 ms |
| `setGalleryIdx(2)` | `galleryIdx()` becomes 2 |
| Uninstall button hidden when `showDeleteConfirm()` | confirm banner rendered instead |

## Feature number

This feature is **F-38**. Add to `README.md` features checklist and `specs/features/f38-model-detail-upgrade.yaml`.
