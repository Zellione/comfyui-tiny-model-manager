# F-38 + F-39: Model Detail Upgrade Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign the model detail page with a modern look, separate read/edit modes, delete-with-confirmation, and (in F-39) a full "Files in this repo" listing populated from the source platform at download/refetch time.

**Architecture:** F-38 is frontend-heavy (rewrite model-detail component) with one small backend extension (add `size_bytes` to the metadata GET response). F-39 adds a new `repo_files` DB table, extends the provider/fetcher pipeline to populate it, adds a new API endpoint, and updates the frontend files section to show downloaded + available files.

**Tech Stack:** Python 3.12+ / aiohttp / aiosqlite (backend); Angular 21.2 zoneless / SCSS / Vitest (frontend); existing global design tokens in `frontend/src/styles.scss`.

---

## Phase 1 — F-38: Visual Upgrade + Delete

### Task 1: Add `size_bytes` to the metadata GET response

**Files:**
- Modify: `py/routes/metadata.py` (lines 18–58, the `get_metadata` handler)
- Modify: `tests/test_routes_metadata.py`

- [ ] **Step 1: Write failing test**

Add to `tests/test_routes_metadata.py`:

```python
async def test_size_bytes_included_in_metadata(self, client, ext_dir, tmp_path, monkeypatch):
    """size_bytes reflects the file size on disk when the file exists."""
    import folder_paths
    from py.db import model_repo

    # Create a real file of known size
    model_file = tmp_path / "sized.safetensors"
    model_file.write_bytes(b"x" * 2048)

    monkeypatch.setattr(folder_paths, "get_folder_paths", lambda _t: [str(tmp_path)])
    await model_repo.upsert_model_with_meta(
        "sized.safetensors", "loras", "civitai", "1", "", [], []
    )

    resp = await client.get(
        "/tiny-model-manager/api/models/loras/sized.safetensors/metadata"
    )
    data = (await resp.json())["data"]
    assert data["size_bytes"] == 2048

async def test_size_bytes_zero_when_file_missing(self, client, ext_dir, monkeypatch):
    """size_bytes is 0 when the file does not exist on disk."""
    import folder_paths
    from py.db import model_repo

    monkeypatch.setattr(folder_paths, "get_folder_paths", lambda _t: ["/nonexistent"])
    await model_repo.upsert_model_with_meta(
        "ghost.safetensors", "loras", "civitai", "2", "", [], []
    )

    resp = await client.get(
        "/tiny-model-manager/api/models/loras/ghost.safetensors/metadata"
    )
    data = (await resp.json())["data"]
    assert data["size_bytes"] == 0
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
PYTHONSAFEPATH=1 ../../../comfy-env/bin/python -m pytest tests/test_routes_metadata.py::TestGetMetadata::test_size_bytes_included_in_metadata tests/test_routes_metadata.py::TestGetMetadata::test_size_bytes_zero_when_file_missing -v
```

Expected: FAIL — `KeyError: 'size_bytes'`

- [ ] **Step 3: Implement — update `py/routes/metadata.py`**

In `get_metadata`, add `import os` at the top of the file (already present) and resolve the file size. Replace the existing `get_metadata` handler body:

```python
@routes.get("/tiny-model-manager/api/models/{model_type}/{path:.*}/metadata")
async def get_metadata(request):
    model_type = request.match_info["model_type"]
    path = request.match_info["path"]
    try:
        meta = await model_repo.get_model_by_filename(path)

        # Resolve file size from disk
        size_bytes = 0
        try:
            dirs = folder_paths.get_folder_paths(model_type)
            for base_dir in dirs:
                candidate = os.path.normpath(os.path.join(base_dir, path))
                if os.path.isfile(candidate):
                    size_bytes = os.path.getsize(candidate)
                    break
        except Exception:
            pass

        if not meta:
            return web.json_response(
                {
                    "success": True,
                    "data": {
                        "description": "",
                        "trigger_words": [],
                        "tags": [],
                        "media": [],
                        "base_model": "",
                        "source_platform": "",
                        "source_url": "",
                        "size_bytes": size_bytes,
                    },
                }
            )
        source_url = _derive_source_url(
            meta.get("source_platform", ""),
            meta.get("source_id", ""),
            meta.get("civitai_model_id", ""),
        )
        return web.json_response(
            {
                "success": True,
                "data": {
                    "description": meta.get("description", ""),
                    "trigger_words": meta.get("trigger_words", []),
                    "tags": meta.get("tags", []),
                    "media": meta.get("media", []),
                    "base_model": meta.get("base_model", ""),
                    "source_platform": meta.get("source_platform", ""),
                    "source_url": source_url,
                    "size_bytes": size_bytes,
                },
            }
        )
    except Exception as exc:
        return web.json_response({"success": False, "error": str(exc)}, status=500)
```

Also add `import folder_paths` at the top of `py/routes/metadata.py` (after the existing imports).

- [ ] **Step 4: Run tests to verify they pass**

```bash
PYTHONSAFEPATH=1 ../../../comfy-env/bin/python -m pytest tests/test_routes_metadata.py -v
```

Expected: All green.

- [ ] **Step 5: Commit**

```bash
git add py/routes/metadata.py tests/test_routes_metadata.py
git commit -m "feat(F-38): add size_bytes to metadata GET response"
```

---

### Task 2: Add `size_bytes` to `ModelMeta` interface and update ModelService tests

**Files:**
- Modify: `frontend/src/app/services/model.ts`
- Modify: `frontend/src/app/services/model.spec.ts`

- [ ] **Step 1: Update the interface in `model.ts`**

In `frontend/src/app/services/model.ts`, add `size_bytes?: number` to `ModelMeta`:

```typescript
export interface ModelMeta {
  description: string;
  trigger_words: string[];
  tags: string[];
  media: MediaItem[];
  base_model: string;
  source_platform: string;
  source_url: string;
  created_at?: string;
  size_bytes?: number;
}
```

Also add `getRepoFiles` stub (full implementation in F-39 Task 14 — add the interface now so the type is ready):

```typescript
export interface RepoFile {
  filename: string;
  size_bytes: number;
  download_url: string;
  source_page_url: string;
  is_downloaded: boolean;
}
```

Add `getRepoFiles` method to `ModelService`:

```typescript
getRepoFiles(modelType: string, path: string): Observable<RepoFile[]> {
  return this.http
    .get<{ success: boolean; data: RepoFile[] }>(`${API}/models/${modelType}/${path}/repo-files`)
    .pipe(map((r) => r.data));
}
```

Also add `downloadFile` method (used in F-39 template for per-file download buttons):

```typescript
downloadFile(modelType: string, filename: string, downloadUrl: string, platform: string): Observable<void> {
  return this.http.post<void>(`${API}/download`, {
    url: downloadUrl,
    model_type: modelType,
    filename,
    platform,
    source_id: '',
  });
}
```

- [ ] **Step 2: Update `model.spec.ts` — add `size_bytes` to mock response**

In the existing `getMetadata` test in `frontend/src/app/services/model.spec.ts`, add `size_bytes: 1048576` to the mock meta object:

```typescript
it('getMetadata GETs metadata URL and unwraps data', () => {
  const meta = {
    description: 'A lora',
    trigger_words: ['word'],
    tags: [],
    media: [],
    base_model: 'SDXL 1.0',
    source_platform: 'civitai',
    source_url: 'https://civitai.com/models/1',
    size_bytes: 1048576,
  };
  let result: unknown;
  service.getMetadata('loras', 'my.safetensors').subscribe((r) => (result = r));
  http
    .expectOne('/tiny-model-manager/api/models/loras/my.safetensors/metadata')
    .flush({ success: true, data: meta });
  expect(result).toEqual(meta);
});

it('getRepoFiles GETs repo-files URL and unwraps data', () => {
  const files: RepoFile[] = [
    { filename: 'a.safetensors', size_bytes: 100, download_url: 'http://x', source_page_url: 'http://y', is_downloaded: true },
  ];
  let result: unknown;
  service.getRepoFiles('loras', 'my.safetensors').subscribe((r) => (result = r));
  http
    .expectOne('/tiny-model-manager/api/models/loras/my.safetensors/repo-files')
    .flush({ success: true, data: files });
  expect(result).toEqual(files);
});
```

Add `import { RepoFile } from './model';` if not already in the test file imports (it's in the same file so just reference it).

- [ ] **Step 3: Run frontend tests**

```bash
cd frontend && npx ng test --watch=false 2>&1 | tail -20
```

Expected: All green.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/app/services/model.ts frontend/src/app/services/model.spec.ts
git commit -m "feat(F-38): add size_bytes and RepoFile types to ModelService"
```

---

### Task 3: Add new signals and methods to `model-detail.ts`

**Files:**
- Modify: `frontend/src/app/pages/model-detail/model-detail.ts`

- [ ] **Step 1: Replace the component file**

Replace the entire contents of `frontend/src/app/pages/model-detail/model-detail.ts`:

```typescript
import { Component, OnInit, computed, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { of } from 'rxjs';
import { switchMap } from 'rxjs/operators';
import { ModelService, ModelMeta, RepoFile } from '../../services/model';
import { WorkflowService } from '../../services/workflow';
import { NotificationService } from '../../services/notification';

@Component({
  selector: 'app-model-detail',
  imports: [CommonModule, FormsModule, RouterLink],
  templateUrl: './model-detail.html',
  styleUrl: './model-detail.scss',
})
export class ModelDetail implements OnInit {
  modelType = '';
  modelPath = '';
  get modelBasename(): string {
    return this.modelPath.split('/').pop() ?? this.modelPath;
  }
  editType = '';
  modelTypes = signal<string[]>([]);
  meta = signal<ModelMeta | null>(null);
  editMeta: Partial<ModelMeta> = {};
  newTriggerWord = '';
  newTag = '';

  // F-38 new signals
  isEditing = signal(false);
  showDeleteConfirm = signal(false);
  deleting = signal(false);
  copied = signal(false);
  galleryIdx = signal(0);

  // F-39 new signals
  repoFiles = signal<RepoFile[]>([]);

  // Derived
  formattedSize = computed(() => {
    const bytes = this.meta()?.size_bytes;
    if (!bytes) return '';
    if (bytes < 1_048_576) return `${(bytes / 1024).toFixed(1)} KB`;
    if (bytes < 1_073_741_824) return `${(bytes / 1_048_576).toFixed(1)} MB`;
    return `${(bytes / 1_073_741_824).toFixed(2)} GB`;
  });

  loading = signal(true);
  saving = signal(false);
  refetching = signal(false);
  error = signal('');

  constructor(
    private route: ActivatedRoute,
    private router: Router,
    private modelService: ModelService,
    private workflowService: WorkflowService,
    private notifService: NotificationService,
  ) {}

  ngOnInit() {
    this.modelType = this.route.snapshot.paramMap.get('type') ?? '';
    this.modelPath = this.route.snapshot.paramMap.get('path') ?? '';
    this.editType = this.modelType;
    this.modelService.getModelTypes().subscribe((types) => this.modelTypes.set(types));
    this.loadMeta();
  }

  loadMeta() {
    this.loading.set(true);
    this.modelService.getMetadata(this.modelType, this.modelPath).subscribe({
      next: (m) => {
        this.meta.set(m);
        this._syncEditMeta(m);
        this.loading.set(false);
        this.loadRepoFiles();
      },
      error: (err) => {
        this.error.set((err as Error).message);
        this.loading.set(false);
      },
    });
  }

  private _syncEditMeta(m: ModelMeta) {
    this.editMeta = {
      description: m.description,
      trigger_words: [...m.trigger_words],
      tags: [...m.tags],
      base_model: m.base_model ?? '',
    };
    this.editType = this.modelType;
  }

  loadRepoFiles() {
    this.modelService.getRepoFiles(this.modelType, this.modelPath).subscribe({
      next: (files) => this.repoFiles.set(files),
      error: () => this.repoFiles.set([]),
    });
  }

  // ── Edit mode ────────────────────────────────────────────────────────────────

  toggleEdit() {
    this._syncEditMeta(this.meta()!);
    this.isEditing.set(true);
  }

  cancelEdit() {
    this._syncEditMeta(this.meta()!);
    this.isEditing.set(false);
  }

  // ── Delete ───────────────────────────────────────────────────────────────────

  startDelete() {
    this.showDeleteConfirm.set(true);
  }

  confirmDelete() {
    this.deleting.set(true);
    this.modelService.deleteModel(this.modelType, this.modelPath).subscribe({
      next: () => {
        this.notifService.show('success', 'Model deleted.');
        this.router.navigate(['/models']);
      },
      error: (err) => {
        this.deleting.set(false);
        this.showDeleteConfirm.set(false);
        this.notifService.show('error', (err as Error).message);
      },
    });
  }

  // ── Keywords copy ────────────────────────────────────────────────────────────

  copyKeywords() {
    const text = (this.meta()?.trigger_words ?? []).join(', ');
    const done = () => {
      this.copied.set(true);
      setTimeout(() => this.copied.set(false), 1400);
    };
    if (navigator.clipboard) {
      navigator.clipboard.writeText(text).then(done).catch(() => this._execCopy(text, done));
    } else {
      this._execCopy(text, done);
    }
  }

  private _execCopy(text: string, done: () => void) {
    const ta = document.createElement('textarea');
    ta.value = text;
    document.body.appendChild(ta);
    ta.select();
    try { document.execCommand('copy'); } finally { document.body.removeChild(ta); }
    done();
  }

  // ── Gallery ──────────────────────────────────────────────────────────────────

  setGalleryIdx(i: number) {
    this.galleryIdx.set(i);
  }

  // ── Repo file download (F-39) ────────────────────────────────────────────────

  downloadRepoFile(f: RepoFile) {
    this.modelService.downloadFile(this.modelType, f.filename, f.download_url, this.meta()?.source_platform ?? '').subscribe({
      next: () => this.notifService.show('success', `${f.filename} queued for download.`),
      error: () => this.notifService.show('error', `Failed to queue ${f.filename}.`),
    });
  }

  formatFileSize(bytes: number): string {
    if (bytes < 1_048_576) return `${(bytes / 1024).toFixed(1)} KB`;
    if (bytes < 1_073_741_824) return `${(bytes / 1_048_576).toFixed(1)} MB`;
    return `${(bytes / 1_073_741_824).toFixed(2)} GB`;
  }

  // ── Existing methods (preserved) ─────────────────────────────────────────────

  addTriggerWord() {
    const w = this.newTriggerWord.trim();
    if (!w) return;
    this.editMeta.trigger_words = [...(this.editMeta.trigger_words ?? []), w];
    this.newTriggerWord = '';
  }

  removeTriggerWord(word: string) {
    this.editMeta.trigger_words = (this.editMeta.trigger_words ?? []).filter((w) => w !== word);
  }

  addTag() {
    const t = this.newTag.trim();
    if (!t) return;
    this.editMeta.tags = [...(this.editMeta.tags ?? []), t];
    this.newTag = '';
  }

  removeTag(tag: string) {
    this.editMeta.tags = (this.editMeta.tags ?? []).filter((t) => t !== tag);
  }

  save() {
    this.saving.set(true);
    this.error.set('');
    const typeChanged = !!this.editType && this.editType !== this.modelType;
    const move$ = typeChanged
      ? this.modelService.moveModel(this.modelType, this.modelPath, this.editType)
      : of(undefined as void);
    move$
      .pipe(
        switchMap(() => {
          if (typeChanged) this.modelType = this.editType;
          return this.modelService.updateMetadata(this.modelType, this.modelPath, this.editMeta);
        }),
      )
      .subscribe({
        next: () => {
          this.saving.set(false);
          this.isEditing.set(false);
          this.notifService.show('success', 'Metadata saved.');
          if (typeChanged) {
            this.router.navigate(['/models', this.modelType, this.modelPath]);
          }
        },
        error: (err) => {
          this.saving.set(false);
          this.error.set((err as Error).message);
          this.notifService.show('error', (err as Error).message);
        },
      });
  }

  refetch() {
    this.refetching.set(true);
    this.error.set('');
    this.modelService.refetchMetadata(this.modelType, this.modelPath).subscribe({
      next: (m) => {
        this.meta.set(m);
        this._syncEditMeta(m);
        this.refetching.set(false);
        this.notifService.show('success', 'Metadata re-fetched.');
        this.loadRepoFiles();
      },
      error: (err) => {
        this.error.set((err as Error).message);
        this.refetching.set(false);
        this.notifService.show('error', (err as Error).message);
      },
    });
  }

  addToWorkflow() {
    this.workflowService.addToWorkflow(this.modelType, this.modelPath).subscribe({
      next: () => this.notifService.show('success', 'Model queued for workflow insertion.'),
      error: () =>
        this.notifService.show('error', 'Failed to enqueue model for workflow insertion.'),
    });
  }

  mediaUrl(path: string): string {
    return `/tiny-model-manager/api/media/${encodeURIComponent(path)}`;
  }
}
```

- [ ] **Step 2: Run lint to catch type errors early**

```bash
cd frontend && npx ng lint 2>&1 | tail -20
```

Expected: 0 errors.

---

### Task 4: Write unit tests for `model-detail.ts`

**Files:**
- Create: `frontend/src/app/pages/model-detail/model-detail.spec.ts`

- [ ] **Step 1: Create the spec file**

```typescript
import { ComponentFixture, TestBed, fakeAsync, tick } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { ActivatedRoute, Router } from '@angular/router';
import { of, throwError } from 'rxjs';
import { vi } from 'vitest';
import { ModelDetail } from './model-detail';
import { ModelService, ModelMeta, RepoFile } from '../../services/model';
import { WorkflowService } from '../../services/workflow';
import { NotificationService } from '../../services/notification';

const MOCK_META: ModelMeta = {
  description: 'A test model',
  trigger_words: ['word1', 'word2'],
  tags: ['tag1'],
  media: [],
  base_model: 'SDXL 1.0',
  source_platform: 'civitai',
  source_url: 'https://civitai.com/models/1',
  size_bytes: 6_946_734_080,
};

const MOCK_REPO_FILES: RepoFile[] = [
  { filename: 'my.safetensors', size_bytes: 6_946_734_080, download_url: '', source_page_url: '', is_downloaded: true },
];

function makeRoute(type = 'loras', path = 'my.safetensors') {
  return { snapshot: { paramMap: { get: (k: string) => (k === 'type' ? type : path) } } };
}

describe('ModelDetail', () => {
  let fixture: ComponentFixture<ModelDetail>;
  let comp: ModelDetail;
  let modelSvc: Record<string, ReturnType<typeof vi.fn>>;
  let router: { navigate: ReturnType<typeof vi.fn> };
  let notifSvc: { show: ReturnType<typeof vi.fn> };

  beforeEach(async () => {
    modelSvc = {
      getMetadata: vi.fn().mockReturnValue(of(MOCK_META)),
      updateMetadata: vi.fn().mockReturnValue(of(undefined)),
      getModelTypes: vi.fn().mockReturnValue(of(['loras', 'checkpoints'])),
      deleteModel: vi.fn().mockReturnValue(of(undefined)),
      refetchMetadata: vi.fn().mockReturnValue(of(MOCK_META)),
      moveModel: vi.fn().mockReturnValue(of(undefined)),
      getRepoFiles: vi.fn().mockReturnValue(of(MOCK_REPO_FILES)),
      downloadFile: vi.fn().mockReturnValue(of(undefined)),
    };
    router = { navigate: vi.fn() };
    notifSvc = { show: vi.fn() };

    await TestBed.configureTestingModule({
      imports: [ModelDetail],
      providers: [
        { provide: ModelService, useValue: modelSvc },
        { provide: WorkflowService, useValue: { addToWorkflow: vi.fn().mockReturnValue(of(undefined)) } },
        { provide: NotificationService, useValue: notifSvc },
        { provide: Router, useValue: router },
        { provide: ActivatedRoute, useValue: makeRoute() },
      ],
    }).compileComponents();

    fixture = TestBed.createComponent(ModelDetail);
    comp = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('loads meta on init and populates editMeta', () => {
    expect(modelSvc['getMetadata']).toHaveBeenCalledWith('loras', 'my.safetensors');
    expect(comp.meta()).toEqual(MOCK_META);
    expect(comp.editMeta.description).toBe('A test model');
  });

  it('formattedSize converts bytes to GB string', () => {
    expect(comp.formattedSize()).toContain('GB');
  });

  describe('edit mode', () => {
    it('toggleEdit sets isEditing to true', () => {
      expect(comp.isEditing()).toBe(false);
      comp.toggleEdit();
      expect(comp.isEditing()).toBe(true);
    });

    it('cancelEdit sets isEditing to false and resets editMeta', () => {
      comp.toggleEdit();
      comp.editMeta.description = 'changed';
      comp.cancelEdit();
      expect(comp.isEditing()).toBe(false);
      expect(comp.editMeta.description).toBe('A test model');
    });
  });

  describe('delete flow', () => {
    it('startDelete shows confirm banner', () => {
      comp.startDelete();
      expect(comp.showDeleteConfirm()).toBe(true);
    });

    it('confirmDelete calls deleteModel and navigates on success', () => {
      comp.confirmDelete();
      expect(modelSvc['deleteModel']).toHaveBeenCalledWith('loras', 'my.safetensors');
      expect(router.navigate).toHaveBeenCalledWith(['/models']);
      expect(notifSvc.show).toHaveBeenCalledWith('success', 'Model deleted.');
    });

    it('confirmDelete on error clears deleting and confirm banner, shows error', () => {
      modelSvc['deleteModel'].mockReturnValue(throwError(() => new Error('disk full')));
      comp.confirmDelete();
      expect(comp.deleting()).toBe(false);
      expect(comp.showDeleteConfirm()).toBe(false);
      expect(notifSvc.show).toHaveBeenCalledWith('error', 'disk full');
    });
  });

  describe('keywords copy', () => {
    it('copyKeywords sets copied to true and resets after 1400ms', fakeAsync(() => {
      Object.defineProperty(navigator, 'clipboard', {
        value: { writeText: vi.fn().mockResolvedValue(undefined) },
        configurable: true,
      });
      comp.copyKeywords();
      tick(0); // resolve promise
      expect(comp.copied()).toBe(true);
      tick(1400);
      expect(comp.copied()).toBe(false);
    }));
  });

  describe('gallery', () => {
    it('setGalleryIdx updates galleryIdx signal', () => {
      comp.setGalleryIdx(2);
      expect(comp.galleryIdx()).toBe(2);
    });
  });

  describe('repo files', () => {
    it('loads repo files on init', () => {
      expect(modelSvc['getRepoFiles']).toHaveBeenCalledWith('loras', 'my.safetensors');
      expect(comp.repoFiles()).toEqual(MOCK_REPO_FILES);
    });

    it('repoFiles falls back to empty array on error', async () => {
      modelSvc['getRepoFiles'].mockReturnValue(throwError(() => new Error('net')));
      comp.loadRepoFiles();
      expect(comp.repoFiles()).toEqual([]);
    });
  });
});
```

- [ ] **Step 2: Run tests**

```bash
cd frontend && npx ng test --watch=false 2>&1 | tail -30
```

Expected: All tests pass including new spec file.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/app/pages/model-detail/model-detail.ts frontend/src/app/pages/model-detail/model-detail.spec.ts
git commit -m "feat(F-38): new signals, methods, and unit tests for model-detail component"
```

---

### Task 5: Rewrite `model-detail.html`

**Files:**
- Rewrite: `frontend/src/app/pages/model-detail/model-detail.html`

- [ ] **Step 1: Replace the template**

```html
<div class="detail-page">

  <!-- ── Header bar ─────────────────────────────────────────────────────── -->
  <div class="detail-back">
    <a routerLink="/models" class="btn-secondary">← Back to Models</a>
    <span class="crumbs">
      <span>Installed</span>
      <span class="crumb-sep">/</span>
      <span>{{ modelType }}</span>
      <span class="crumb-sep">/</span>
      <span class="crumb-active">{{ modelBasename }}</span>
    </span>
    <div class="detail-spacer"></div>
    @if (!isEditing() && !showDeleteConfirm()) {
      <button class="btn-secondary" (click)="toggleEdit()">Edit</button>
      <button class="btn-uninstall" (click)="startDelete()">Uninstall</button>
    }
  </div>

  <!-- ── Delete confirmation banner ────────────────────────────────────── -->
  @if (showDeleteConfirm()) {
    <div class="delete-confirm-banner">
      <p>
        Delete this model? The file and all saved metadata will be permanently removed.
        This cannot be undone.
      </p>
      <div class="confirm-actions">
        <button class="btn-secondary" (click)="showDeleteConfirm.set(false)">Cancel</button>
        <button class="btn-danger" (click)="confirmDelete()" [disabled]="deleting()">
          {{ deleting() ? 'Deleting…' : 'Confirm Delete' }}
        </button>
      </div>
    </div>
  }

  <!-- ── Loading / error states ─────────────────────────────────────────── -->
  @if (loading()) {
    <p class="loading-state">Loading metadata…</p>
  } @else if (error()) {
    <p class="error">{{ error() }}</p>
  } @else if (meta()) {

    <!-- ── READ VIEW ──────────────────────────────────────────────────────── -->
    @if (!isEditing()) {
      <div class="detail-card">

        <!-- Card header -->
        <div class="card-header">
          <div>
            <div class="detail-eyebrow">
              @if (modelType) {<span>{{ modelType }}</span>}
              @if (meta()!.base_model) {
                <span class="dot">·</span><span>{{ meta()!.base_model }}</span>
              }
              @if (formattedSize()) {
                <span class="dot">·</span><span>{{ formattedSize() }}</span>
              }
            </div>
            <h2 class="detail-title" [title]="modelPath">{{ modelBasename }}</h2>
          </div>
          @if (meta()!.source_url) {
            <a
              [href]="meta()!.source_url"
              target="_blank"
              rel="noopener"
              class="dl-detail-source"
            >
              View on
              {{ meta()!.source_platform === 'civitai' ? 'CivitAI' : 'HuggingFace' }} ↗
            </a>
          }
        </div>

        <!-- Gallery -->
        <div class="gallery">
          <div class="gallery-main">
            @if (meta()!.media && meta()!.media.length > 0) {
              @if (meta()!.media[galleryIdx()].media_type === 'image') {
                <img [src]="mediaUrl(meta()!.media[galleryIdx()].local_path)" alt="preview" />
              } @else {
                <video
                  [src]="mediaUrl(meta()!.media[galleryIdx()].local_path)"
                  controls
                ></video>
              }
            } @else {
              <div class="gallery-placeholder">
                <div class="gallery-stripes"></div>
              </div>
            }
          </div>
          @if (meta()!.media && meta()!.media.length > 1) {
            <div class="gallery-thumbs">
              @for (m of meta()!.media; track m.id; let i = $index) {
                <div
                  class="gallery-thumb"
                  [class.active]="galleryIdx() === i"
                  (click)="setGalleryIdx(i)"
                >
                  @if (m.media_type === 'image') {
                    <img [src]="mediaUrl(m.local_path)" alt="thumb {{ i }}" />
                  } @else {
                    <div class="thumb-video-icon">▶</div>
                  }
                </div>
              }
            </div>
          }
        </div>

        <!-- Tags -->
        @if (meta()!.tags && meta()!.tags.length > 0) {
          <div class="dl-tags">
            <span class="dl-tags-label">Tags</span>
            @for (t of meta()!.tags; track t) {
              <span class="badge">{{ t }}</span>
            }
          </div>
        }

        <!-- Keywords -->
        <div class="detail-section">
          <div class="keywords-card">
            <div class="keywords-label">Trigger keywords</div>
            @if (!meta()!.trigger_words || meta()!.trigger_words.length === 0) {
              <div class="keywords-empty">No trigger words for this model</div>
            } @else {
              <div
                class="keywords-line"
                (click)="copyKeywords()"
                role="button"
                title="Click to copy"
              >
                <code>{{ meta()!.trigger_words.join(', ') }}</code>
                <button
                  class="btn-secondary btn-small"
                  (click)="$event.stopPropagation(); copyKeywords()"
                >
                  {{ copied() ? '✓ Copied' : 'Copy' }}
                </button>
              </div>
              <div class="keywords-chips">
                @for (w of meta()!.trigger_words; track w) {
                  <span class="chip-keyword">{{ w }}</span>
                }
              </div>
            }
          </div>
        </div>

        <!-- Files in this model -->
        <div class="files-section">
          <div class="files-header">
            <div class="files-title">Files in this model</div>
            @if (repoFiles().length > 0) {
              <div class="files-subtitle">
                {{ repoFiles().filter(f => f.is_downloaded).length }} of
                {{ repoFiles().length }} downloaded
              </div>
            }
          </div>
          @if (repoFiles().length > 0) {
            @for (f of repoFiles(); track f.filename) {
              <div class="file-row" [class.not-downloaded]="!f.is_downloaded">
                @if (f.is_downloaded) {
                  <div class="file-status ok">✓</div>
                  <span class="file-name">{{ f.filename }}</span>
                  @if (f.size_bytes) {
                    <span class="file-size">{{ formatFileSize(f.size_bytes) }}</span>
                  }
                  <span class="pill-ok">Downloaded</span>
                } @else {
                  <div class="file-status avail">↓</div>
                  <span class="file-name">{{ f.filename }}</span>
                  @if (f.size_bytes) {
                    <span class="file-size">{{ formatFileSize(f.size_bytes) }}</span>
                  }
                  <span class="pill">Not downloaded</span>
                  <button class="btn-primary btn-small" (click)="downloadRepoFile(f)">
                    Download
                  </button>
                }
              </div>
            }
          } @else {
            <!-- Fallback: primary file only (before F-39 data is available) -->
            <div class="file-row">
              <div class="file-status ok">✓</div>
              <span class="file-name">{{ modelBasename }}</span>
              @if (formattedSize()) {
                <span class="file-size">{{ formattedSize() }}</span>
              }
              <span class="pill-ok">Downloaded</span>
            </div>
          }
        </div>

        <!-- Description -->
        @if (meta()!.description) {
          <div class="description">
            <h3>About this model</h3>
            <p>{{ meta()!.description }}</p>
          </div>
        }

      </div>
    }

    <!-- ── EDIT VIEW ───────────────────────────────────────────────────────── -->
    @if (isEditing()) {
      <div class="detail-card">

        <div class="card-header">
          <h2 class="detail-title" [title]="modelPath">{{ modelBasename }}</h2>
          <div class="edit-header-actions">
            <button class="btn-secondary" (click)="cancelEdit()">Cancel</button>
            <button class="btn-primary" (click)="save()" [disabled]="saving()">
              {{ saving() ? 'Saving…' : 'Save' }}
            </button>
          </div>
        </div>

        <div class="edit-panel-body">

          <label>
            <span>Description</span>
            <textarea [(ngModel)]="editMeta.description" rows="6"></textarea>
          </label>

          <label>
            <span>Model Type</span>
            <select [(ngModel)]="editType">
              @for (t of modelTypes(); track t) {
                <option [value]="t">{{ t }}</option>
              }
            </select>
          </label>

          <label>
            <span>Base Model</span>
            <input
              type="text"
              [(ngModel)]="editMeta.base_model"
              placeholder="e.g. SDXL 1.0, Flux.1 D, Pony"
            />
          </label>

          <div class="trigger-words">
            <span class="label">Trigger Words</span>
            <div class="chips">
              @for (w of editMeta.trigger_words; track w) {
                <span class="chip"
                  >{{ w }}<button (click)="removeTriggerWord(w)">×</button></span
                >
              }
            </div>
            <div class="add-word">
              <input
                [(ngModel)]="newTriggerWord"
                placeholder="Add trigger word"
                (keyup.enter)="addTriggerWord()"
              />
              <button class="btn-secondary" (click)="addTriggerWord()">Add</button>
            </div>
          </div>

          <div class="trigger-words">
            <span class="label">Tags</span>
            <div class="chips">
              @for (t of editMeta.tags; track t) {
                <span class="chip chip-tag"
                  >{{ t }}<button (click)="removeTag(t)">×</button></span
                >
              }
            </div>
            <div class="add-word">
              <input [(ngModel)]="newTag" placeholder="Add tag" (keyup.enter)="addTag()" />
              <button class="btn-secondary" (click)="addTag()">Add</button>
            </div>
          </div>

          @if (meta()!.source_platform || meta()!.source_url) {
            <div class="source-info">
              @if (meta()!.source_platform) {
                <span class="badge source-badge">{{
                  meta()!.source_platform === 'civitai' ? 'CivitAI' : 'HuggingFace'
                }}</span>
              }
              @if (meta()!.source_url) {
                <a
                  [href]="meta()!.source_url"
                  target="_blank"
                  rel="noopener"
                  class="source-link"
                  >View on source ↗</a
                >
              }
            </div>
          }

          <div class="edit-secondary-actions">
            <button class="btn-secondary" (click)="refetch()" [disabled]="refetching()">
              {{ refetching() ? 'Fetching…' : 'Re-fetch Metadata' }}
            </button>
            <button class="btn-workflow" (click)="addToWorkflow()">Add to Workflow</button>
          </div>

        </div>
      </div>
    }

  }
</div>
```

- [ ] **Step 2: Run lint**

```bash
cd frontend && npx ng lint 2>&1 | tail -10
```

Expected: 0 errors.

---

### Task 6: Rewrite `model-detail.scss`

**Files:**
- Rewrite: `frontend/src/app/pages/model-detail/model-detail.scss`

- [ ] **Step 1: Replace the stylesheet**

```scss
// ── Page wrapper ──────────────────────────────────────────────────────────────

.detail-page {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

// ── Header bar ────────────────────────────────────────────────────────────────

.detail-back {
  display: flex;
  align-items: center;
  gap: 14px;
  flex-wrap: wrap;
}

.crumbs {
  display: flex;
  align-items: center;
  gap: 8px;
  font-family: var(--font-mono);
  font-size: 12px;
  color: var(--text-3);
}

.crumb-sep {
  opacity: 0.5;
}

.crumb-active {
  color: var(--text-2);
}

.detail-spacer {
  flex: 1;
}

.btn-uninstall {
  appearance: none;
  background: transparent;
  border: 1px solid transparent;
  border-radius: var(--radius-sm);
  padding: 0.4rem 0.9rem;
  font-size: 0.85rem;
  cursor: pointer;
  color: var(--text-3);
  transition: background var(--dur), color var(--dur), border-color var(--dur);

  &:hover {
    background: var(--danger-soft);
    color: var(--danger);
    border-color: var(--danger);
  }
}

// ── Delete confirmation banner ────────────────────────────────────────────────

.delete-confirm-banner {
  background: var(--danger-soft);
  border: 1px solid var(--danger);
  border-radius: var(--radius-lg);
  padding: 16px 20px;
  display: flex;
  align-items: center;
  gap: 1.5rem;
  flex-wrap: wrap;

  p {
    flex: 1;
    margin: 0;
    color: var(--text);
    font-size: 0.9rem;
  }
}

.confirm-actions {
  display: flex;
  gap: 0.5rem;
  flex-shrink: 0;
}

// ── State text ────────────────────────────────────────────────────────────────

.loading-state {
  color: var(--text-3);
  margin: 0;
}

.error {
  color: var(--danger);
  margin: 0;
}

// ── Detail card ───────────────────────────────────────────────────────────────

.detail-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  overflow: hidden;
}

// ── Card header ───────────────────────────────────────────────────────────────

.card-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  padding: 20px 22px;
  border-bottom: 1px solid var(--border);
}

.detail-eyebrow {
  display: flex;
  align-items: center;
  gap: 6px;
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--text-3);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin-bottom: 6px;

  .dot {
    width: 3px;
    height: 3px;
    border-radius: 50%;
    background: var(--text-3);
    flex-shrink: 0;
  }
}

.detail-title {
  font-size: 22px;
  font-weight: 600;
  letter-spacing: -0.02em;
  margin: 0;
  color: var(--text);
  word-break: break-all;
}

.edit-header-actions {
  display: flex;
  gap: 0.5rem;
  flex-shrink: 0;
}

.dl-detail-source {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  color: var(--text-3);
  font-size: 12px;
  padding: 5px 10px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--border);
  white-space: nowrap;
  flex-shrink: 0;

  &:hover {
    color: var(--text);
    border-color: var(--border-strong);
  }
}

// ── Gallery ───────────────────────────────────────────────────────────────────

.gallery {
  padding: 20px 22px;
}

.gallery-main {
  aspect-ratio: 16 / 9;
  border-radius: var(--radius);
  overflow: hidden;
  background: var(--surface-2);
  position: relative;

  img,
  video {
    width: 100%;
    height: 100%;
    object-fit: cover;
    display: block;
  }
}

.gallery-placeholder {
  width: 100%;
  height: 100%;
  background: var(--surface-2);
  position: relative;
  overflow: hidden;
}

.gallery-stripes {
  position: absolute;
  inset: 0;
  background: repeating-linear-gradient(
    135deg,
    transparent 0 12px,
    rgba(255, 255, 255, 0.04) 12px 24px
  );
}

.gallery-thumbs {
  display: flex;
  gap: 6px;
  margin-top: 10px;
  overflow-x: auto;
}

.gallery-thumb {
  width: 64px;
  height: 64px;
  flex: 0 0 64px;
  border-radius: var(--radius-sm);
  overflow: hidden;
  cursor: pointer;
  border: 1px solid transparent;
  background: var(--surface-2);
  transition: border-color var(--dur);
  position: relative;
  display: grid;
  place-items: center;

  img {
    width: 100%;
    height: 100%;
    object-fit: cover;
    display: block;
  }

  &.active {
    border-color: var(--accent);
  }

  &:hover:not(.active) {
    border-color: var(--border-strong);
  }
}

.thumb-video-icon {
  color: var(--text-3);
  font-size: 1.2rem;
}

// ── Tags row ──────────────────────────────────────────────────────────────────

.dl-tags {
  padding: 0 22px 18px;
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.dl-tags-label {
  font-size: 10px;
  color: var(--text-3);
  text-transform: uppercase;
  letter-spacing: 0.1em;
  margin-right: 4px;
}

// ── Keywords section ──────────────────────────────────────────────────────────

.detail-section {
  padding: 0 22px 18px;
}

.keywords-card {
  background: var(--surface-2);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 14px 16px;
}

.keywords-label {
  font-size: 10.5px;
  text-transform: uppercase;
  letter-spacing: 0.12em;
  color: var(--text-3);
  font-weight: 600;
  margin-bottom: 8px;
}

.keywords-empty {
  color: var(--text-3);
  font-size: 12.5px;
}

.keywords-line {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  background: var(--bg-2);
  border: 1px solid var(--border);
  border-radius: 8px;
  cursor: pointer;
  transition: border-color var(--dur);

  &:hover {
    border-color: var(--border-strong);
  }

  code {
    flex: 1;
    font-family: var(--font-mono);
    font-size: 12.5px;
    color: var(--text);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
}

.keywords-chips {
  display: flex;
  gap: 6px;
  margin-top: 10px;
  flex-wrap: wrap;
}

.chip-keyword {
  background: var(--accent-soft);
  color: var(--accent);
  font-size: 10.5px;
  padding: 2px 8px;
  border-radius: 4px;
  font-weight: 500;
}

// ── Files section ─────────────────────────────────────────────────────────────

.files-section {
  padding: 18px 22px;
  border-top: 1px solid var(--border);
}

.files-header {
  display: flex;
  align-items: baseline;
  gap: 10px;
  margin-bottom: 10px;
}

.files-title {
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.1em;
  color: var(--text-3);
  font-weight: 600;
}

.files-subtitle {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--text-3);
}

.file-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 14px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--surface-2);
  margin-bottom: 6px;
  flex-wrap: wrap;

  &.not-downloaded {
    border-style: dashed;
    background: var(--surface);
  }
}

.file-status {
  width: 24px;
  height: 24px;
  border-radius: 6px;
  display: grid;
  place-items: center;
  font-size: 12px;
  flex-shrink: 0;

  &.ok {
    background: color-mix(in oklch, var(--success) 16%, transparent);
    color: var(--success);
  }

  &.avail {
    background: var(--accent-soft);
    color: var(--accent);
  }
}

.file-name {
  font-family: var(--font-mono);
  font-size: 12px;
  color: var(--text);
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.file-size {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--text-3);
  flex-shrink: 0;
}

.pill-ok {
  font-size: 10.5px;
  padding: 3px 8px;
  border-radius: 5px;
  background: color-mix(in oklch, var(--success) 14%, transparent);
  color: var(--success);
  font-family: var(--font-mono);
  letter-spacing: 0.03em;
  flex-shrink: 0;
}

.pill {
  font-size: 10.5px;
  padding: 3px 8px;
  border-radius: 5px;
  background: var(--surface-hi);
  color: var(--text-2);
  font-family: var(--font-mono);
  letter-spacing: 0.03em;
  flex-shrink: 0;
}

// ── Description ───────────────────────────────────────────────────────────────

.description {
  padding: 18px 22px 22px;
  border-top: 1px solid var(--border);

  h3 {
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    color: var(--text-3);
    margin: 0 0 10px;
    font-weight: 600;
  }

  p {
    color: var(--text-2);
    line-height: 1.65;
    font-size: 13px;
    margin: 0;
  }
}

// ── Edit panel ────────────────────────────────────────────────────────────────

.edit-panel-body {
  display: flex;
  flex-direction: column;
  gap: 1rem;
  padding: 22px;

  label {
    display: flex;
    flex-direction: column;
    gap: 0.3rem;

    span {
      font-size: 0.85rem;
      color: var(--text-2);
    }

    textarea {
      resize: vertical;
      width: 100%;
    }

    input[type='text'],
    select {
      width: 100%;
    }
  }
}

.edit-secondary-actions {
  display: flex;
  gap: 0.5rem;
  flex-wrap: wrap;
  padding-top: 0.5rem;
  border-top: 1px solid var(--border);
}

// ── Trigger words / tags (edit mode) ─────────────────────────────────────────

.trigger-words {
  .label {
    font-size: 0.85rem;
    color: var(--text-2);
    display: block;
    margin-bottom: 0.4rem;
  }
}

.chips {
  display: flex;
  flex-wrap: wrap;
  gap: 0.4rem;
  margin-bottom: 0.5rem;
}

.chip {
  background: var(--surface-hi);
  border-radius: 4px;
  padding: 0.2rem 0.5rem;
  font-size: 0.8rem;
  display: flex;
  align-items: center;
  gap: 0.3rem;
  color: var(--text-2);

  button {
    background: none;
    color: var(--text-3);
    padding: 0;
    font-size: 0.9rem;
    border: none;

    &:hover {
      color: var(--text);
    }
  }
}

.chip-tag {
  background: #2a1a4a;
  color: #b07df7;
}

.add-word {
  display: flex;
  gap: 0.5rem;

  input {
    flex: 1;
  }
}

// ── Source info (edit mode) ───────────────────────────────────────────────────

.source-info {
  display: flex;
  align-items: center;
  gap: 0.6rem;
  font-size: 0.85rem;
}

.source-badge {
  background: #1a3a5c;
  color: #4f9eff;
  padding: 0.15rem 0.5rem;
  border-radius: 4px;
  font-size: 0.78rem;
  font-weight: 500;
}

.source-link {
  color: var(--accent);
  text-decoration: none;

  &:hover {
    text-decoration: underline;
  }
}
```

- [ ] **Step 2: Run lint + format check + build**

```bash
cd frontend && npx ng lint 2>&1 | tail -5
npx prettier --check . 2>&1 | tail -5
npx ng build 2>&1 | tail -10
```

Expected: 0 lint errors, 0 format errors, build succeeds.

If prettier reports format issues, run `npx prettier --write .` and re-check.

- [ ] **Step 3: Run all frontend tests**

```bash
npx ng test --watch=false 2>&1 | tail -20
```

Expected: All green.

- [ ] **Step 4: Commit F-38**

```bash
git add frontend/src/app/pages/model-detail/
git commit -m "feat(F-38): visual upgrade and delete for model detail page"
```

- [ ] **Step 5: Run backend tests**

```bash
cd .. && PYTHONSAFEPATH=1 ../../../comfy-env/bin/python -m pytest -v 2>&1 | tail -20
```

Expected: All green.

---

## Phase 2 — F-39: Repo Files Listing

### Task 7: Add `repo_files` table to the DB schema

**Files:**
- Modify: `py/db/database.py`

- [ ] **Step 1: Add table to `_SCHEMA`**

In `py/db/database.py`, append the `repo_files` table to `_SCHEMA` (before the closing `"""`):

```python
_SCHEMA = """
...existing tables...

CREATE TABLE IF NOT EXISTS repo_files (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    model_type       TEXT    NOT NULL,
    model_path       TEXT    NOT NULL,
    filename         TEXT    NOT NULL,
    size_bytes       INTEGER DEFAULT 0,
    download_url     TEXT    NOT NULL DEFAULT '',
    source_page_url  TEXT    NOT NULL DEFAULT '',
    UNIQUE (model_type, model_path, filename)
);
"""
```

- [ ] **Step 2: Add migration for existing DBs**

In `_migrate_db()`, add a new migration block at the end (before `await db.commit()`):

```python
        # Create repo_files table if not present (F-39)
        try:
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS repo_files (
                    id               INTEGER PRIMARY KEY AUTOINCREMENT,
                    model_type       TEXT    NOT NULL,
                    model_path       TEXT    NOT NULL,
                    filename         TEXT    NOT NULL,
                    size_bytes       INTEGER DEFAULT 0,
                    download_url     TEXT    NOT NULL DEFAULT '',
                    source_page_url  TEXT    NOT NULL DEFAULT '',
                    UNIQUE (model_type, model_path, filename)
                )
                """
            )
        except Exception as exc:
            print(f"[tiny-model-manager] repo_files migration failed: {exc}")
```

- [ ] **Step 3: Write a test to verify the table is created**

In `tests/test_routes_metadata.py` (or create `tests/test_db_schema.py`):

```python
"""tests/test_db_schema.py — verifies schema migrations create expected tables."""
import pytest


@pytest.mark.asyncio
async def test_repo_files_table_created(ext_dir):
    """repo_files table must exist after init_db."""
    from py.db.database import get_db

    async with get_db() as db:
        row = await (
            await db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='repo_files'"
            )
        ).fetchone()
    assert row is not None, "repo_files table was not created"
```

- [ ] **Step 4: Run the test**

```bash
PYTHONSAFEPATH=1 ../../../comfy-env/bin/python -m pytest tests/test_db_schema.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add py/db/database.py tests/test_db_schema.py
git commit -m "feat(F-39): add repo_files table to DB schema"
```

---

### Task 8: Add CRUD helpers for `repo_files`

**Files:**
- Modify: `py/db/model_repo.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_db_schema.py`:

```python
@pytest.mark.asyncio
async def test_upsert_and_get_repo_files(ext_dir):
    from py.db import model_repo

    files = [
        {
            "filename": "model.safetensors",
            "size_bytes": 1024,
            "download_url": "https://civitai.com/dl/1",
            "source_page_url": "https://civitai.com/models/1",
        },
        {
            "filename": "vae.safetensors",
            "size_bytes": 512,
            "download_url": "https://civitai.com/dl/2",
            "source_page_url": "https://civitai.com/models/1",
        },
    ]
    await model_repo.upsert_repo_files("loras", "my.safetensors", files)
    rows = await model_repo.get_repo_files("loras", "my.safetensors")
    assert len(rows) == 2
    assert {r["filename"] for r in rows} == {"model.safetensors", "vae.safetensors"}

@pytest.mark.asyncio
async def test_upsert_repo_files_updates_on_conflict(ext_dir):
    from py.db import model_repo

    await model_repo.upsert_repo_files("loras", "x.safetensors", [
        {"filename": "a.safetensors", "size_bytes": 100, "download_url": "u1", "source_page_url": "p1"}
    ])
    await model_repo.upsert_repo_files("loras", "x.safetensors", [
        {"filename": "a.safetensors", "size_bytes": 200, "download_url": "u2", "source_page_url": "p2"}
    ])
    rows = await model_repo.get_repo_files("loras", "x.safetensors")
    assert len(rows) == 1
    assert rows[0]["size_bytes"] == 200
    assert rows[0]["download_url"] == "u2"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
PYTHONSAFEPATH=1 ../../../comfy-env/bin/python -m pytest tests/test_db_schema.py::test_upsert_and_get_repo_files -v
```

Expected: FAIL — `AttributeError: module 'py.db.model_repo' has no attribute 'upsert_repo_files'`

- [ ] **Step 3: Implement the helpers in `py/db/model_repo.py`**

Append to the end of `py/db/model_repo.py`:

```python
async def upsert_repo_files(model_type: str, model_path: str, files: list[dict]) -> None:
    async with get_db() as db:
        for f in files:
            await db.execute(
                """
                INSERT INTO repo_files
                    (model_type, model_path, filename, size_bytes, download_url, source_page_url)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(model_type, model_path, filename) DO UPDATE SET
                    size_bytes      = excluded.size_bytes,
                    download_url    = excluded.download_url,
                    source_page_url = excluded.source_page_url
                """,
                (
                    model_type,
                    model_path[:_MAX_PATH],
                    f.get("filename", "")[:_MAX_PATH],
                    f.get("size_bytes", 0),
                    f.get("download_url", ""),
                    f.get("source_page_url", ""),
                ),
            )
        await db.commit()


async def get_repo_files(model_type: str, model_path: str) -> list[dict]:
    async with get_db() as db:
        rows = await (
            await db.execute(
                """
                SELECT filename, size_bytes, download_url, source_page_url
                FROM repo_files
                WHERE model_type = ? AND model_path = ?
                ORDER BY filename
                """,
                (model_type, model_path),
            )
        ).fetchall()
        return [dict(row) for row in rows]
```

- [ ] **Step 4: Run all DB tests**

```bash
PYTHONSAFEPATH=1 ../../../comfy-env/bin/python -m pytest tests/test_db_schema.py -v
```

Expected: All green.

- [ ] **Step 5: Commit**

```bash
git add py/db/model_repo.py tests/test_db_schema.py
git commit -m "feat(F-39): add upsert_repo_files and get_repo_files CRUD helpers"
```

---

### Task 9: Extend `ProviderMetadata` and CivitAI provider

**Files:**
- Modify: `py/services/providers/base.py`
- Modify: `py/services/providers/civitai_provider.py`

- [ ] **Step 1: Add `RepoFileInfo` and update `ProviderMetadata` in `base.py`**

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class RepoFileInfo:
    filename: str
    size_bytes: int = 0
    download_url: str = ""
    source_page_url: str = ""


@dataclass
class ProviderMetadata:
    description: str = ""
    trigger_words: list[str] = field(default_factory=list)
    image_urls: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    base_model: str = ""
    civitai_model_id: str = ""
    repo_files: list[RepoFileInfo] = field(default_factory=list)


class ModelProvider(ABC):
    name: str

    @abstractmethod
    def auth_headers(self) -> dict: ...

    @abstractmethod
    async def search(self, query: str, model_type: str = "", **kwargs) -> dict: ...

    @abstractmethod
    async def fetch_metadata(self, source_id: str) -> ProviderMetadata: ...
```

- [ ] **Step 2: Populate `repo_files` in `civitai_provider.py` `fetch_metadata`**

In `CivitaiProvider.fetch_metadata`, after extracting `civitai_model_id`, build `repo_files` from the version's `files` array (already fetched in the response). Add the import for `RepoFileInfo` and update the return:

```python
    async def fetch_metadata(self, source_id: str) -> ProviderMetadata:
        version_id = int(source_id)
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                f"{_BASE}/model-versions/{version_id}", headers=self.auth_headers()
            )
            resp.raise_for_status()
            data = resp.json()
        image_urls = [img["url"] for img in data.get("images", [])[:5] if img.get("url")]
        description = data.get("description") or ""
        base_model = data.get("baseModel", "")
        tags: list[str] = []
        model_id = data.get("modelId")
        civitai_model_id = str(model_id) if model_id else ""
        if model_id:
            async with httpx.AsyncClient(timeout=15) as client:
                model_resp = await client.get(
                    f"{_BASE}/models/{model_id}", headers=self.auth_headers()
                )
                if model_resp.is_success:
                    model_data = model_resp.json()
                    description = description or model_data.get("description") or ""
                    tags = model_data.get("tags", [])

        source_page_url = f"https://civitai.com/models/{civitai_model_id}" if civitai_model_id else ""
        repo_files = [
            RepoFileInfo(
                filename=f["name"],
                size_bytes=int(f.get("sizeKB", 0) * 1024),
                download_url=f.get("downloadUrl", ""),
                source_page_url=source_page_url,
            )
            for f in data.get("files", [])
            if f.get("name")
        ]

        return ProviderMetadata(
            description=description,
            trigger_words=data.get("trainedWords", []),
            image_urls=image_urls,
            tags=tags,
            base_model=base_model,
            civitai_model_id=civitai_model_id,
            repo_files=repo_files,
        )
```

Add `from .base import ModelProvider, ProviderMetadata, RepoFileInfo` to the imports.

- [ ] **Step 3: Run existing provider tests (if any)**

```bash
PYTHONSAFEPATH=1 ../../../comfy-env/bin/python -m pytest tests/ -k "civitai" -v 2>&1 | tail -20
```

Expected: All green (or no matching tests — either is fine).

- [ ] **Step 4: Commit**

```bash
git add py/services/providers/base.py py/services/providers/civitai_provider.py
git commit -m "feat(F-39): add RepoFileInfo to ProviderMetadata; populate from CivitAI version files"
```

---

### Task 10: Extend HuggingFace provider

**Files:**
- Modify: `py/services/providers/huggingface_provider.py`

- [ ] **Step 1: Update `fetch_metadata` to populate `repo_files`**

In `HuggingFaceProvider.fetch_metadata`, after fetching the existing metadata, also call `GET /api/models/{source_id}` to get the `siblings` list and build `repo_files`. Add the import `from .base import ModelProvider, ProviderMetadata, RepoFileInfo`.

Find the `fetch_metadata` method and add repo_files logic. The full method should end with:

```python
        # Build repo file listing from HF siblings
        repo_files: list[RepoFileInfo] = []
        try:
            async with httpx.AsyncClient(timeout=15, headers=self.auth_headers()) as client:
                repo_resp = await client.get(f"{_API}/models/{source_id}")
                if repo_resp.is_success:
                    repo_data = repo_resp.json()
                    source_page_url = f"https://huggingface.co/{source_id}"
                    for sibling in repo_data.get("siblings", []):
                        fname = sibling.get("rfilename", "")
                        ext = os.path.splitext(fname)[1].lower()
                        if ext in MODEL_EXTENSIONS:
                            repo_files.append(
                                RepoFileInfo(
                                    filename=fname,
                                    size_bytes=sibling.get("size", 0),
                                    download_url=f"https://huggingface.co/{source_id}/resolve/main/{fname}",
                                    source_page_url=source_page_url,
                                )
                            )
        except Exception:
            pass  # repo file listing is best-effort

```

The change is surgical: (a) add `import os` at the top if not already present, (b) add `from .base import ModelProvider, ProviderMetadata, RepoFileInfo` to the imports, (c) paste the siblings-fetching block immediately before the final `return ProviderMetadata(...)` statement, and (d) add `repo_files=repo_files` as the last keyword argument in that `ProviderMetadata(...)` call. All other fields in the return stay exactly as they are in the current file — do not change them.

- [ ] **Step 2: Run full backend test suite**

```bash
PYTHONSAFEPATH=1 ../../../comfy-env/bin/python -m pytest -v 2>&1 | tail -20
```

Expected: All green.

- [ ] **Step 3: Commit**

```bash
git add py/services/providers/huggingface_provider.py
git commit -m "feat(F-39): populate repo_files from HuggingFace siblings in fetch_metadata"
```

---

### Task 11: Store repo files in `metadata_fetcher.py`

**Files:**
- Modify: `py/services/metadata_fetcher.py`

- [ ] **Step 1: Write failing test**

Add to `tests/test_routes_metadata.py` or create `tests/test_metadata_fetcher.py`:

```python
"""tests/test_metadata_fetcher.py — tests for metadata_fetcher.fetch_and_store."""
import pytest
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
async def test_fetch_and_store_saves_repo_files(ext_dir):
    from py.services.providers.base import ProviderMetadata, RepoFileInfo
    from py.services.metadata_fetcher import fetch_and_store
    from py.db import model_repo

    mock_meta = ProviderMetadata(
        description="test",
        trigger_words=[],
        image_urls=[],
        tags=[],
        base_model="SDXL",
        repo_files=[
            RepoFileInfo(
                filename="a.safetensors",
                size_bytes=1024,
                download_url="https://civitai.com/dl/1",
                source_page_url="https://civitai.com/models/1",
            )
        ],
    )

    with (
        patch("py.services.metadata_fetcher.get_provider") as mock_get_provider,
        patch("py.services.metadata_fetcher._download_images", new_callable=AsyncMock),
    ):
        mock_provider = AsyncMock()
        mock_provider.fetch_metadata.return_value = mock_meta
        mock_get_provider.return_value = mock_provider

        await fetch_and_store("my.safetensors", "loras", "civitai", "123")

    rows = await model_repo.get_repo_files("loras", "my.safetensors")
    assert len(rows) == 1
    assert rows[0]["filename"] == "a.safetensors"
    assert rows[0]["size_bytes"] == 1024
```

- [ ] **Step 2: Run test to verify it fails**

```bash
PYTHONSAFEPATH=1 ../../../comfy-env/bin/python -m pytest tests/test_metadata_fetcher.py -v
```

Expected: FAIL — repo_files not saved.

- [ ] **Step 3: Implement — update `fetch_and_store` in `metadata_fetcher.py`**

After the `model_id = await model_repo.upsert_model_with_meta(...)` call, add:

```python
    if meta and meta.repo_files:
        await model_repo.upsert_repo_files(
            model_type,
            filename,
            [
                {
                    "filename": f.filename,
                    "size_bytes": f.size_bytes,
                    "download_url": f.download_url,
                    "source_page_url": f.source_page_url,
                }
                for f in meta.repo_files
            ],
        )
```

Note: `meta` is the `ProviderMetadata` object; `fetch_ok` indicates whether it was populated. Guard with `if fetch_ok and meta.repo_files:` to avoid storing empty lists on failure.

The full relevant section of `fetch_and_store` after the fix:

```python
    fetch_ok = False
    meta = None   # declare before try block
    provider = get_provider(platform)
    if provider and source_id:
        for attempt in range(3):
            try:
                meta = await provider.fetch_metadata(source_id)
                description = meta.description
                trigger_words = meta.trigger_words
                image_urls = meta.image_urls
                tags = meta.tags
                base_model = meta.base_model
                civitai_model_id = meta.civitai_model_id
                fetch_ok = True
                break
            except Exception:
                if attempt < 2:
                    await asyncio.sleep(1)
        if not fetch_ok:
            from .backend_notifier import push as notify
            notify("error", f"Metadata fetch failed for '{filename}'. ...")

    # ... (organize_into_subfolders block unchanged) ...

    model_id = await model_repo.upsert_model_with_meta(...)

    if fetch_ok and meta and meta.repo_files:
        await model_repo.upsert_repo_files(
            model_type,
            filename,
            [
                {
                    "filename": f.filename,
                    "size_bytes": f.size_bytes,
                    "download_url": f.download_url,
                    "source_page_url": f.source_page_url,
                }
                for f in meta.repo_files
            ],
        )

    if not skip_media:
        await _download_images(model_id, media_hash, image_urls)
```

- [ ] **Step 4: Run tests**

```bash
PYTHONSAFEPATH=1 ../../../comfy-env/bin/python -m pytest tests/test_metadata_fetcher.py tests/test_db_schema.py -v
```

Expected: All green.

- [ ] **Step 5: Commit**

```bash
git add py/services/metadata_fetcher.py tests/test_metadata_fetcher.py
git commit -m "feat(F-39): store repo_files from provider metadata after download/refetch"
```

---

### Task 12: Add `GET /api/models/{type}/{path}/repo-files` endpoint

**Files:**
- Modify: `py/routes/metadata.py`

- [ ] **Step 1: Write failing test**

Add to `tests/test_routes_metadata.py`:

```python
class TestGetRepoFiles:
    @pytest.fixture()
    async def client(self, aiohttp_client, ext_dir):
        from py.routes.metadata import add_metadata_routes
        app = web.Application()
        routes = web.RouteTableDef()
        add_metadata_routes(routes)
        app.router.add_routes(routes)
        return await aiohttp_client(app)

    async def test_returns_empty_list_when_no_repo_files(self, client):
        resp = await client.get(
            "/tiny-model-manager/api/models/loras/my.safetensors/repo-files"
        )
        assert resp.status == 200
        data = (await resp.json())["data"]
        assert data == []

    async def test_returns_repo_files_with_is_downloaded(
        self, client, ext_dir, tmp_path, monkeypatch
    ):
        import folder_paths
        from py.db import model_repo

        # Create the file on disk to test is_downloaded=True
        (tmp_path / "a.safetensors").write_bytes(b"x")
        monkeypatch.setattr(folder_paths, "get_folder_paths", lambda _t: [str(tmp_path)])

        await model_repo.upsert_repo_files("loras", "primary.safetensors", [
            {"filename": "a.safetensors", "size_bytes": 1, "download_url": "u1", "source_page_url": "p1"},
            {"filename": "b.safetensors", "size_bytes": 2, "download_url": "u2", "source_page_url": "p1"},
        ])

        resp = await client.get(
            "/tiny-model-manager/api/models/loras/primary.safetensors/repo-files"
        )
        data = (await resp.json())["data"]
        assert len(data) == 2
        a = next(f for f in data if f["filename"] == "a.safetensors")
        b = next(f for f in data if f["filename"] == "b.safetensors")
        assert a["is_downloaded"] is True
        assert b["is_downloaded"] is False
```

- [ ] **Step 2: Run to verify tests fail**

```bash
PYTHONSAFEPATH=1 ../../../comfy-env/bin/python -m pytest tests/test_routes_metadata.py::TestGetRepoFiles -v
```

Expected: FAIL — 404 (route not registered).

- [ ] **Step 3: Implement endpoint in `py/routes/metadata.py`**

Add inside `add_metadata_routes(routes)`:

```python
    @routes.get("/tiny-model-manager/api/models/{model_type}/{path:.*}/repo-files")
    async def get_repo_files(request):
        model_type = request.match_info["model_type"]
        path = request.match_info["path"]
        try:
            files = await model_repo.get_repo_files(model_type, path)

            # Compute is_downloaded by checking the filesystem
            model_dir = os.path.dirname(path)
            base_dirs: list[str] = []
            try:
                base_dirs = folder_paths.get_folder_paths(model_type)
            except Exception:
                pass

            for f in files:
                f["is_downloaded"] = False
                for base_dir in base_dirs:
                    candidate = os.path.normpath(
                        os.path.join(base_dir, model_dir, f["filename"])
                    )
                    if os.path.isfile(candidate):
                        f["is_downloaded"] = True
                        break

            return web.json_response({"success": True, "data": files})
        except Exception as exc:
            return web.json_response({"success": False, "error": str(exc)}, status=500)
```

- [ ] **Step 4: Run all backend tests**

```bash
PYTHONSAFEPATH=1 ../../../comfy-env/bin/python -m pytest -v 2>&1 | tail -20
```

Expected: All green.

- [ ] **Step 5: Commit**

```bash
git add py/routes/metadata.py tests/test_routes_metadata.py
git commit -m "feat(F-39): add GET /repo-files endpoint with is_downloaded computed from disk"
```

---

### Task 13: Build, lint, final checks, and commit F-39

- [ ] **Step 1: Run full backend test suite**

```bash
PYTHONSAFEPATH=1 ../../../comfy-env/bin/python -m pytest -v 2>&1 | tail -10
```

Expected: All green, 0 failures.

- [ ] **Step 2: Run backend ruff checks**

```bash
../../../comfy-env/bin/python -m ruff check py tests conftest.py
../../../comfy-env/bin/python -m ruff format --check py tests conftest.py
```

Expected: 0 errors.

- [ ] **Step 3: Run frontend tests + lint + format + build**

```bash
cd frontend
npx ng test --watch=false 2>&1 | tail -10
npx ng lint 2>&1 | tail -5
npx prettier --check . 2>&1 | tail -5
npx ng build 2>&1 | tail -10
```

Expected: All green, build succeeds.

- [ ] **Step 4: Update README.md**

Mark both features done in `README.md` features checklist:
- `[x] F-38: Visual Upgrade — Model Detail View + Delete`
- `[x] F-39: Repo Files Listing in Model Detail`

- [ ] **Step 5: Final commit**

```bash
git add README.md
git commit -m "feat(F-39): mark F-38 and F-39 complete in README"
```
