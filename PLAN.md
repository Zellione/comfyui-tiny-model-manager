# F-47: Route Restructuring + HuggingFace base_model Persistence Fix

## Context

Two related improvements:

1. **Route restructuring**: The current `/models/:type/:path` URL exposes the internal model type
   ("checkpoints", "loras") as a visible URL segment. For catalog-linked models this is redundant —
   platform + pageId already uniquely identify the model. Additionally, uninstalled catalog entries
   use a simpler `CatalogDetail` page while installed models use the richer `ModelDetail`, causing an
   inconsistent experience when browsing.

2. **HuggingFace base_model not persisting**: When `organize_into_subfolders = true` and the user
   changes `base_model`, the backend moves the file into a subfolder and updates `models.filename`.
   The PUT `/metadata` response returns only `{success: true}` without the new path. The frontend
   retains the old URL, so subsequent loads request the now-nonexistent DB record and show empty
   metadata — making it appear the change was not saved.

---

## Part 1: Route Restructuring

### Goals

- Rename "Models" tab → "Catalog"; main list URL `/models` → `/catalog`
- All catalog-linked models (installed **or** uninstalled): detail URL `/catalog/:platform?pageId=X`
  — **no model_type** in the URL
- Unlinked local models (manually placed, no source): keep `/models/:type/:path` as a fallback
- `CatalogDetail` enhanced to show the same rich layout as `ModelDetail` when the entry has
  installed files (gallery, trigger words, description, tags, edit mode)

### Route Table (after change)

| URL | Component | When used |
|---|---|---|
| `/catalog` | `Models` | Main catalog list (renamed) |
| `/catalog/:platform?pageId=X` | `CatalogDetail` | All catalog-linked models |
| `/models/:type/:path` | `ModelDetail` | Unlinked local models only |
| `/download` | `Download` | Download queue |

Add `{ path: 'models', redirectTo: 'catalog', pathMatch: 'full' }` for backward compatibility.

### Files to Change

#### `frontend/src/app/app.routes.ts`
- Change `path: 'models'` → `path: 'catalog'` for the `Models` component
- Add redirect: `{ path: 'models', redirectTo: 'catalog', pathMatch: 'full' }`
- Keep `catalog/:platform` and `models/:type/:path` unchanged

#### `frontend/src/app/app.html`
- `routerLink="/models"` → `routerLink="/catalog"` in the nav tab
- Tab label "Models" → "Catalog"

#### `frontend/src/app/pages/models/models.ts` — `cardDetailRoute` + `cardDetailQuery`

```typescript
cardDetailRoute(entry: CatalogEntry): string[] {
  if (entry.source_platform && entry.source_page_id) {
    return ['/catalog', entry.source_platform]; // installed + uninstalled
  }
  // Fallback: unlinked local model (no catalog source)
  if (entry.installed_files[0]) {
    return ['/models', entry.installed_files[0].model_type, entry.installed_files[0].filename];
  }
  return ['/catalog'];
}

cardDetailQuery(entry: CatalogEntry): Record<string, string> | null {
  if (entry.source_platform && entry.source_page_id) {
    return { pageId: entry.source_page_id };
  }
  return null;
}
```

Remove the previous `is_empty` branch — route is now uniform for all catalog-linked entries.

#### `frontend/src/app/pages/catalog-detail/catalog-detail.ts` (main enhancement)

New signals/state to add:

```typescript
primaryMeta  = signal<ModelMeta | null>(null);
primaryPath  = '';    // installed_files[0].filename
primaryType  = '';    // installed_files[0].model_type
editMode     = signal(false);
saving       = signal(false);
refetching   = signal(false);
editMeta: Partial<ModelMeta> = {};
newTriggerWord = '';
newTag = '';
copied       = signal(false);
galleryIdx   = signal(0);
lightboxOpen = signal(false);
```

Load flow — after catalog entry loads:

```typescript
if (entry.installed_files.length > 0) {
  this.primaryType = entry.installed_files[0].model_type;
  this.primaryPath = entry.installed_files[0].filename;
  this.modelService.getMetadata(this.primaryType, this.primaryPath).subscribe(
    (meta) => { this.primaryMeta.set(meta); this.syncEditMeta(meta); }
  );
}
```

Methods to add (mirror `ModelDetail`): `enterEdit()`, `cancelEdit()`, `save()`, `syncEditMeta()`,
`refetch()`, `addTriggerWord()`, `removeTriggerWord()`, `addTag()`, `removeTag()`,
`copyTriggerWords()`, `mediaUrl()`, `addFileToWorkflow()`, `uninstall()`.

`save()` calls `modelService.updateMetadata(this.primaryType, this.primaryPath, this.editMeta)` and
handles a `new_path` in the response (see Part 2).

#### `frontend/src/app/pages/catalog-detail/catalog-detail.html` (significant rework)

Structure mirrors `model-detail.html`:

- **Header bar**: back link, breadcrumb, Re-fetch / Edit buttons (when installed), Remove from Catalog
- **Remove / uninstall confirmation banner**
- **Card**: eyebrow (platform · base_model), title, source link
- **Gallery** (`primaryMeta()` media when installed; thumbnail or placeholder otherwise)
- **Tags** (from `primaryMeta()` when installed)
- **Trigger words** (from `primaryMeta()` when installed)
- **Files in this model** — `entry().repo_files` with download/installed status rows
- **Description** (from `primaryMeta()` when installed)
- **Edit panel** (when `editMode()`) — same fields as `model-detail.html`

Behavior matrix:

| State | Gallery | Trigger words | Edit button | Files |
|---|---|---|---|---|
| Not installed | Thumbnail / placeholder | Hidden | Hidden | Download buttons |
| Installed, read | Full gallery | Shown | Shown | Installed + Download |
| Installed, edit | Gallery | Edit fields | Save / Cancel | — |

#### `frontend/src/app/pages/catalog-detail/catalog-detail.spec.ts`

- Update existing tests for new signal/load flow
- Add: `loads primaryMeta when entry has installed files`
- Add: `shows edit button when installed`
- Add: `save() calls updateMetadata with primaryType and primaryPath`

---

## Part 2: HuggingFace base_model Persistence Fix

### Root Cause

`py/routes/metadata.py` `update_metadata` handler:

1. When `organize_into_subfolders = true` and `base_model` changes, `_move_to_subfolder()` moves the
   file on disk.
2. `model_repo.update_model_filename(old, new)` renames the `models.filename` DB record.
3. Local variable `path` is updated to the new path.
4. `update_model_meta(new_path, ...)` correctly saves `base_model` to the renamed record.
5. Response returns `{"success": true}` — **new path is never sent to the frontend**.
6. Frontend keeps `this.modelPath = old_path`; next load returns null metadata, appearing as if the
   save did nothing.

### Fix

#### `py/routes/metadata.py` — `update_metadata`

Change success response:

```python
return web.json_response({"success": True, "new_path": path})
```

`path` is the original value when no move happened, or the new subfolder path when the file moved.

#### `frontend/src/app/services/model.ts` — `updateMetadata`

```typescript
updateMetadata(
  modelType: string,
  path: string,
  meta: Partial<ModelMeta>,
): Observable<{ new_path: string }> {
  return this.http
    .put<{ success: boolean; new_path: string }>(
      `${this.api}/models/${modelType}/${path}/metadata`,
      meta,
    )
    .pipe(map((r) => ({ new_path: r.new_path ?? path })));
}
```

#### `frontend/src/app/pages/model-detail/model-detail.ts` — `save()`

After success, detect path change and navigate:

```typescript
next: (result) => {
  this.saving.set(false);
  this.notifService.show('success', 'Metadata saved.');
  this.saveSiblingBaseModels();
  const newPath = result.new_path ?? this.modelPath;
  if (typeChanged || newPath !== this.modelPath) {
    this.modelPath = newPath;
    this.router.navigate(['/models', this.modelType, newPath]);
  } else {
    this.editMode.set(false);
    const current = this.meta()!;
    this.meta.set({
      ...current,
      description:    this.editMeta.description    ?? current.description,
      trigger_words:  this.editMeta.trigger_words  ?? current.trigger_words,
      tags:           this.editMeta.tags           ?? current.tags,
      base_model:     this.editMeta.base_model     ?? current.base_model,
    });
  }
},
```

Apply the same `new_path` handling to `CatalogDetail.save()`.

#### Test to add — `tests/test_routes_metadata.py`

```python
async def test_base_model_change_returns_new_path_when_reorganized(aiohttp_client, ext_dir):
    """When organize_into_subfolders is on and base_model changes, response includes new_path."""
    # Setup: create model record, mock settings to enable subfolders,
    # mock _move_to_subfolder to return a new path
    # PUT metadata with new base_model
    # Assert response["new_path"] differs from the original path
    # Assert DB filename matches the new path
```

---

## Verification

From `frontend/`:

```bash
npx ng test --watch=false
npx ng lint
npm run format:check
npx ng build
```

From project root:

```bash
PYTHONSAFEPATH=1 ../../../comfy-env/bin/python -m pytest
../../../comfy-env/bin/python -m ruff check py tests conftest.py
../../../comfy-env/bin/python -m ruff format --check py tests conftest.py
```

Manual checks:

1. `/catalog` loads the main list (renamed from `/models`)
2. Clicking a CivitAI model card → URL is `/catalog/civitai?pageId=…` (no type segment)
3. Clicking a HuggingFace model card → URL is `/catalog/huggingface?pageId=user/repo`
4. Clicking an unlinked local model → URL is `/models/:type/:path` (fallback unchanged)
5. In `CatalogDetail` for an installed model: gallery, trigger words, description are visible; Edit
   button appears
6. Editing `base_model` and saving → success notification; if file was moved, URL navigates to the
   new path and metadata reloads correctly
7. Hard-refresh at the new URL → `base_model` value is retained

---

## Branch

Create `F-47-catalog-routes` from `main` before starting.

## Out of Scope

- Changing backend API route prefixes (`/tiny-model-manager/api/models/…` stays unchanged)
- Multi-file selection or bulk editing in the detail view
- Keyboard navigation in the gallery lightbox
