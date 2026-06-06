# F-44 + F-45: Copy Trigger Words & Quick-access Dashboard Button

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** F-44 adds a one-click "copy all trigger words" action to both the Model Detail page and the Models library page; F-45 adds a "TMM" toolbar button to ComfyUI's top-right menu that opens the dashboard in a new tab.

**Architecture:**
F-44 requires three changes: (1) extend the existing `/api/catalog` list endpoint to include `trigger_words` per entry (it's already stored in the DB as JSON), (2) fix `model-detail.ts` to fire toast notifications on copy success/failure, and (3) add a copy button to the models library card actions. F-45 adds a third `app.registerExtension()` call in `js/extension.js` that inserts a `<button>` into ComfyUI's `.comfyui-menu-right` toolbar during the extension `setup()` hook.

**Tech Stack:** Python/aiohttp (backend), Angular 21.2 signals + `NotificationService` (frontend), Vitest (frontend tests), pytest/aiohttp_client (backend tests), vanilla JS ComfyUI extension API.

---

## File Map

| File | Action | Purpose |
|---|---|---|
| `py/db/model_repo.py` | Modify | Add `trigger_words` to `list_catalog_entries()` query + parse |
| `tests/test_routes_catalog.py` | Modify | Test that list response includes `trigger_words` |
| `frontend/src/app/services/model.ts` | Modify | Add `trigger_words: string[]` to `CatalogEntry` interface |
| `frontend/src/app/pages/model-detail/model-detail.ts` | Modify | Fix `copyTriggerWords()` to call `notifService` on success/error |
| `frontend/src/app/pages/model-detail/model-detail.spec.ts` | Modify | Add toast notification tests |
| `frontend/src/app/pages/models/models.ts` | Modify | Add `copyTriggerWords(entry)` method |
| `frontend/src/app/pages/models/models.html` | Modify | Add copy button to catalog entry card-actions |
| `frontend/src/app/pages/models/models.spec.ts` | Modify | Add `copyTriggerWords` unit tests |
| `js/extension.js` | Modify | Add `TinyModelManager.DashboardButton` extension |

---

## Task 1: Backend — expose trigger_words in catalog list response

**Files:**
- Modify: `py/db/model_repo.py:466-499` (`list_catalog_entries`)
- Modify: `tests/test_routes_catalog.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_routes_catalog.py` in `class TestListCatalog`:

```python
async def test_catalog_list_includes_trigger_words(self, client, ext_dir):
    from py.db import model_repo

    await model_repo.upsert_catalog_entry(
        source_platform="civitai",
        source_page_id="tw_test",
        source_page_url="https://civitai.com/models/tw_test",
        display_name="TW Model",
        thumbnail_url="",
        base_model="SDXL",
        trigger_words=["alpha", "beta"],
    )
    resp = await client.get("/tiny-model-manager/api/catalog")
    assert resp.status == 200
    entries = (await resp.json())["data"]["entries"]
    entry = next(e for e in entries if e["source_page_id"] == "tw_test")
    assert entry["trigger_words"] == ["alpha", "beta"]

async def test_catalog_list_trigger_words_empty_when_none(self, client, ext_dir):
    resp = await client.get("/tiny-model-manager/api/catalog")
    assert resp.status == 200
    entries = (await resp.json())["data"]["entries"]
    for entry in entries:
        assert "trigger_words" in entry
        assert isinstance(entry["trigger_words"], list)
```

- [ ] **Step 2: Run test to confirm it fails**

```bash
PYTHONSAFEPATH=1 ../../../comfy-env/bin/python -m pytest tests/test_routes_catalog.py::TestListCatalog::test_catalog_list_includes_trigger_words -v
```

Expected: FAIL — `KeyError: 'trigger_words'` or `AssertionError`.

- [ ] **Step 3: Implement — add trigger_words to list_catalog_entries**

In `py/db/model_repo.py`, replace the `list_catalog_entries` function (lines 466-499):

```python
async def list_catalog_entries() -> list[dict]:
    async with get_db() as db:
        entries = await (
            await db.execute(
                "SELECT id, source_platform, source_page_id, source_page_url,"
                "       display_name, thumbnail_url, base_model, trigger_words, created_at"
                " FROM catalog_entries ORDER BY created_at DESC"
            )
        ).fetchall()
        result = []
        for entry in entries:
            e = dict(entry)
            e["trigger_words"] = _parse_json_list(e.get("trigger_words", ""))
            installed = list(
                await (
                    await db.execute(
                        "SELECT filename, model_type FROM models WHERE catalog_entry_id = ?",
                        (e["id"],),
                    )
                ).fetchall()
            )
            e["installed_files"] = [dict(r) for r in installed]
            if installed:
                e["model_type"] = installed[0]["model_type"] or "other"
            else:
                rf = await (
                    await db.execute(
                        "SELECT model_type FROM repo_files WHERE catalog_entry_id = ? LIMIT 1",
                        (e["id"],),
                    )
                ).fetchone()
                e["model_type"] = rf["model_type"] if rf else "other"
            result.append(e)
        return result
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
PYTHONSAFEPATH=1 ../../../comfy-env/bin/python -m pytest tests/test_routes_catalog.py -v
```

Expected: all catalog tests PASS.

- [ ] **Step 5: Lint check**

```bash
../../../comfy-env/bin/python -m ruff check py tests conftest.py
../../../comfy-env/bin/python -m ruff format --check py tests conftest.py
```

Expected: 0 errors.

- [ ] **Step 6: Commit**

```bash
git add py/db/model_repo.py tests/test_routes_catalog.py
git commit -m "feat(catalog): include trigger_words in catalog list response"
```

---

## Task 2: Frontend — update CatalogEntry type

**Files:**
- Modify: `frontend/src/app/services/model.ts:95-107`

- [ ] **Step 1: Add trigger_words to CatalogEntry**

In `frontend/src/app/services/model.ts`, update the `CatalogEntry` interface:

```typescript
export interface CatalogEntry {
  id: number;
  source_platform: string;
  source_page_id: string;
  source_page_url: string;
  display_name: string;
  thumbnail_url: string;
  base_model: string;
  created_at: string;
  model_type: string;
  is_empty: boolean;
  installed_files: InstalledFile[];
  trigger_words: string[];
}
```

- [ ] **Step 2: Check for TypeScript compile errors**

```bash
cd frontend && npx ng build 2>&1 | head -30; cd ..
```

Expected: build succeeds (or fails only for other unrelated reasons — type errors for `trigger_words` would appear here if missed anywhere).

---

## Task 3: Fix model-detail copyTriggerWords to fire toast

**Files:**
- Modify: `frontend/src/app/pages/model-detail/model-detail.ts:386-393`
- Modify: `frontend/src/app/pages/model-detail/model-detail.spec.ts`

- [ ] **Step 1: Write the failing tests**

Find the test file `frontend/src/app/pages/model-detail/model-detail.spec.ts`. Look for existing test structure. Add the following tests in a new `describe('copyTriggerWords()', ...)` block near the end of the file. The test setup already stubs `navigator.clipboard` via `vi.stubGlobal` or needs to be added — check the existing test setup first.

Add to the top of the test file (or in a `beforeEach` that scopes to this describe block):

```typescript
// Stub clipboard in the describe block
let clipboardWriteText: ReturnType<typeof vi.fn>;

describe('copyTriggerWords()', () => {
  beforeEach(() => {
    clipboardWriteText = vi.fn();
    vi.stubGlobal('navigator', {
      ...navigator,
      clipboard: { writeText: clipboardWriteText },
    });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('calls notifService.show success when clipboard write resolves', async () => {
    clipboardWriteText.mockResolvedValue(undefined);
    const fixture = TestBed.createComponent(ModelDetail);
    fixture.componentInstance['meta'].set(makeMeta({ trigger_words: ['foo', 'bar'] }));
    fixture.componentInstance['modelType'] = 'loras';
    fixture.componentInstance['modelPath'] = 'test.safetensors';
    await fixture.componentInstance.copyTriggerWords();
    expect(mockNotifService.show).toHaveBeenCalledWith('success', 'Trigger words copied');
  });

  it('calls notifService.show error when clipboard write rejects', async () => {
    clipboardWriteText.mockRejectedValue(new Error('denied'));
    const fixture = TestBed.createComponent(ModelDetail);
    fixture.componentInstance['meta'].set(makeMeta({ trigger_words: ['foo'] }));
    fixture.componentInstance['modelType'] = 'loras';
    fixture.componentInstance['modelPath'] = 'test.safetensors';
    await fixture.componentInstance.copyTriggerWords().catch(() => {});
    expect(mockNotifService.show).toHaveBeenCalledWith('error', 'Could not copy trigger words');
  });

  it('copies words as comma-separated string', async () => {
    clipboardWriteText.mockResolvedValue(undefined);
    const fixture = TestBed.createComponent(ModelDetail);
    fixture.componentInstance['meta'].set(makeMeta({ trigger_words: ['alpha', 'beta', 'gamma'] }));
    fixture.componentInstance['modelType'] = 'loras';
    fixture.componentInstance['modelPath'] = 'test.safetensors';
    await fixture.componentInstance.copyTriggerWords();
    expect(clipboardWriteText).toHaveBeenCalledWith('alpha, beta, gamma');
  });
});
```

Note: the existing mock setup in the spec file provides `mockNotifService`. Check that `NotificationService` mock is wired in the `TestBed.configureTestingModule` providers — it already is (existing tests use it).

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd frontend && npx ng test --watch=false 2>&1 | grep -A 3 "copyTriggerWords\|FAIL\|PASS" | head -30; cd ..
```

Expected: 3 new tests FAIL.

- [ ] **Step 3: Fix copyTriggerWords in model-detail.ts**

Replace `copyTriggerWords()` at lines 386-394 in `frontend/src/app/pages/model-detail/model-detail.ts`:

```typescript
async copyTriggerWords() {
  const text = (this.meta()?.trigger_words ?? []).join(', ');
  try {
    await navigator.clipboard.writeText(text);
    this.notifService.show('success', 'Trigger words copied');
  } catch {
    this.notifService.show('error', 'Could not copy trigger words');
  }
}
```

Also remove the now-unused `copied = signal(false)` field (line 57) and remove the `copied()` binding from the template. In `model-detail.html` line 131-133, change the button:

```html
<button class="btn small ghost keywords-copy" (click)="copyTriggerWords()">
  Copy
</button>
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
cd frontend && npx ng test --watch=false 2>&1 | tail -10; cd ..
```

Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/pages/model-detail/model-detail.ts \
        frontend/src/app/pages/model-detail/model-detail.html \
        frontend/src/app/pages/model-detail/model-detail.spec.ts
git commit -m "feat(model-detail): fire toast notification on trigger-word copy success/error"
```

---

## Task 4: Add copy trigger words to Models library cards

**Files:**
- Modify: `frontend/src/app/pages/models/models.ts`
- Modify: `frontend/src/app/pages/models/models.html`
- Modify: `frontend/src/app/pages/models/models.spec.ts`

- [ ] **Step 1: Write the failing tests**

Add to `frontend/src/app/pages/models/models.spec.ts` at the end, in a new `describe`:

```typescript
describe('copyTriggerWords()', () => {
  let clipboardWriteText: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    clipboardWriteText = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal('navigator', {
      ...navigator,
      clipboard: { writeText: clipboardWriteText },
    });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('copies trigger words as comma-separated string', async () => {
    const c = await getComponent();
    const entry = {
      id: 1,
      source_platform: 'civitai',
      source_page_id: '1',
      source_page_url: '',
      display_name: 'Test',
      thumbnail_url: '',
      base_model: '',
      created_at: '',
      model_type: 'loras',
      is_empty: false,
      installed_files: [],
      trigger_words: ['word1', 'word2'],
    };
    await c.copyTriggerWords(entry);
    expect(clipboardWriteText).toHaveBeenCalledWith('word1, word2');
  });

  it('shows success toast after copying', async () => {
    const mockNotif = TestBed.inject(NotificationService) as unknown as {
      show: ReturnType<typeof vi.fn>;
    };
    const c = await getComponent();
    const entry = {
      id: 1,
      source_platform: 'civitai',
      source_page_id: '1',
      source_page_url: '',
      display_name: 'Test',
      thumbnail_url: '',
      base_model: '',
      created_at: '',
      model_type: 'loras',
      is_empty: false,
      installed_files: [],
      trigger_words: ['abc'],
    };
    await c.copyTriggerWords(entry);
    expect(mockNotif.show).toHaveBeenCalledWith('success', 'Trigger words copied');
  });

  it('shows error toast when clipboard rejects', async () => {
    clipboardWriteText.mockRejectedValue(new Error('denied'));
    const mockNotif = TestBed.inject(NotificationService) as unknown as {
      show: ReturnType<typeof vi.fn>;
    };
    const c = await getComponent();
    const entry = {
      id: 1,
      source_platform: 'civitai',
      source_page_id: '1',
      source_page_url: '',
      display_name: 'Test',
      thumbnail_url: '',
      base_model: '',
      created_at: '',
      model_type: 'loras',
      is_empty: false,
      installed_files: [],
      trigger_words: ['abc'],
    };
    await c.copyTriggerWords(entry).catch(() => {});
    expect(mockNotif.show).toHaveBeenCalledWith('error', 'Could not copy trigger words');
  });
});
```

Also add `NotificationService` to imports at the top of `models.spec.ts`:
```typescript
import { NotificationService } from '../../services/notification';
```

And wire a mock `NotificationService` in the `TestBed.configureTestingModule` providers:
```typescript
const mockNotifService = { show: vi.fn() };
// ... in providers:
{ provide: NotificationService, useValue: mockNotifService }
```

Then add `vi.clearAllMocks()` call in `beforeEach` to reset `mockNotifService.show` between tests.

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd frontend && npx ng test --watch=false 2>&1 | grep -E "copyTriggerWords|FAIL" | head -10; cd ..
```

Expected: 3 new tests FAIL with `c.copyTriggerWords is not a function`.

- [ ] **Step 3: Add copyTriggerWords to models.ts**

In `frontend/src/app/pages/models/models.ts`, add the method after `organizeIntoSubfolders()`:

```typescript
async copyTriggerWords(entry: CatalogEntry) {
  const text = (entry.trigger_words ?? []).join(', ');
  try {
    await navigator.clipboard.writeText(text);
    this.notifService.show('success', 'Trigger words copied');
  } catch {
    this.notifService.show('error', 'Could not copy trigger words');
  }
}
```

- [ ] **Step 4: Add copy button to models.html**

In `frontend/src/app/pages/models/models.html`, inside `<div class="card-actions">` for catalog entries (around line 131), add the copy button after the existing "View details" `<a>` element:

```html
@if (!entry.is_empty && entry.installed_files[0]) {
  <a
    class="card-action"
    [routerLink]="cardDetailRoute(entry)"
    [queryParams]="cardDetailQuery(entry)"
    title="View details"
  >
    <svg
      width="13"
      height="13"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      stroke-width="1.75"
      stroke-linecap="round"
      stroke-linejoin="round"
    >
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
      <polyline points="14,2 14,8 20,8" />
    </svg>
  </a>
}
@if (entry.trigger_words?.length > 0) {
  <button
    class="card-action"
    (click)="copyTriggerWords(entry)"
    title="Copy trigger words"
  >
    <svg
      width="13"
      height="13"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      stroke-width="1.75"
      stroke-linecap="round"
      stroke-linejoin="round"
    >
      <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
      <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
    </svg>
  </button>
}
```

- [ ] **Step 5: Run all frontend tests**

```bash
cd frontend && npx ng test --watch=false 2>&1 | tail -15; cd ..
```

Expected: all tests PASS (including the 3 new ones).

- [ ] **Step 6: Run lint and format check**

```bash
cd frontend && npx ng lint && npm run format:check; cd ..
```

Expected: 0 lint errors.

- [ ] **Step 7: Build**

```bash
cd frontend && npx ng build; cd ..
```

Expected: build succeeds.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/app/services/model.ts \
        frontend/src/app/pages/models/models.ts \
        frontend/src/app/pages/models/models.html \
        frontend/src/app/pages/models/models.spec.ts
git commit -m "feat(models): add copy trigger words action to library card"
```

---

## Task 5: Quick-access Dashboard Button (F-45)

**Files:**
- Modify: `js/extension.js`

ComfyUI's `setup()` hook runs after the page and graph are fully initialized, so `document.querySelector` on the menu container works reliably.

- [ ] **Step 1: Add dashboard button extension to js/extension.js**

At the end of `js/extension.js`, after the closing `});` of `TinyModelManager.WorkflowInsert`, append:

```js
app.registerExtension({
  name: "TinyModelManager.DashboardButton",
  async setup() {
    const btn = document.createElement("button");
    btn.className = "comfyui-button";
    btn.title = "Open Tiny Model Manager";
    btn.textContent = "TMM";
    btn.style.cssText = "padding:4px 10px;font-size:12px;font-weight:600;cursor:pointer";
    btn.addEventListener("click", () => window.open("/tiny-model-manager", "_blank"));
    const target =
      document.querySelector(".comfyui-menu-right") ??
      document.querySelector(".comfyui-menu");
    target?.prepend(btn);
  },
});
```

- [ ] **Step 2: Build (copies extension.js into web/ as an asset)**

```bash
cd frontend && npx ng build; cd ..
```

Expected: build succeeds.

- [ ] **Step 3: Run all frontend tests**

```bash
cd frontend && npx ng test --watch=false 2>&1 | tail -10; cd ..
```

Expected: all tests PASS (extension.js is not tested by Angular — manual verification in ComfyUI is the acceptance test).

- [ ] **Step 4: Run all backend tests**

```bash
PYTHONSAFEPATH=1 ../../../comfy-env/bin/python -m pytest 2>&1 | tail -10
```

Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add js/extension.js
git commit -m "feat(extension): add TMM toolbar button that opens dashboard in new tab"
```

---

## Task 6: Mark features done and final checks

- [ ] **Step 1: Mark F-44 and F-45 done in README.md**

In `README.md`, change:
```
- [ ] F-44 — Copy Trigger Words — ...
- [ ] F-45 — Quick-access Dashboard Button — ...
```
to:
```
- [x] F-44 — Copy Trigger Words — ...
- [x] F-45 — Quick-access Dashboard Button — ...
```

- [ ] **Step 2: Run full test suite**

```bash
PYTHONSAFEPATH=1 ../../../comfy-env/bin/python -m pytest
cd frontend && npx ng test --watch=false; cd ..
```

Expected: all tests PASS with zero failures.

- [ ] **Step 3: Run all linters**

```bash
../../../comfy-env/bin/python -m ruff check py tests conftest.py
../../../comfy-env/bin/python -m ruff format --check py tests conftest.py
cd frontend && npx ng lint && npm run format:check; cd ..
```

Expected: zero errors.

- [ ] **Step 4: Final build**

```bash
cd frontend && npx ng build; cd ..
```

Expected: build succeeds.

- [ ] **Step 5: Commit**

```bash
git add README.md
git commit -m "chore: mark F-44 and F-45 as complete in README"
```

---

## Spec Coverage Self-Review

### F-44 requirements:
- ✅ Model Detail page copy button hidden when no trigger words (existing template `@if` guard, unchanged)
- ✅ Models library card action "Copy trigger words" hidden when `entry.trigger_words?.length === 0` (Task 4, Step 4 `@if` guard)
- ✅ Copies as comma-separated string (both `copyTriggerWords` implementations use `.join(', ')`)
- ✅ Toast "Trigger words copied" on success (Task 3 + Task 4)
- ✅ Toast error on Clipboard API failure (Task 3 + Task 4 catch block)
- ✅ No new API endpoints — extending existing `/api/catalog` list response
- ✅ No database changes — `trigger_words` column already exists in `catalog_entries`

### F-45 requirements:
- ✅ Button in ComfyUI top-right toolbar
- ✅ Icon (SVG-free, uses text label "TMM" per spec)
- ✅ Opens `/tiny-model-manager` in new tab
- ✅ Registered exactly once — `app.registerExtension` with unique name `TinyModelManager.DashboardButton` is called once at module load
