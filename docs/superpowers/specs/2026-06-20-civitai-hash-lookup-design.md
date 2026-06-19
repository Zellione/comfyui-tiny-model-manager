# Feature #90: CivitAI Hash Lookup & Auto-fill

**Issue:** #90  
**Parent epic:** #88 (Migrate Disk Models to Model Cards)  
**Date:** 2026-06-20

## Summary

Extends the unregistered-file registration flow (added in F-89) with SHA-256 hash-based
auto-matching against CivitAI. When the user clicks "Register" on an unregistered file,
the backend hashes the file and queries CivitAI for a matching model version. If found,
the registration form is pre-filled with CivitAI metadata. The user can edit any field
before saving. If no match is found or the network is unavailable, the form opens empty
with a retry option.

## UX Flow

1. User clicks **Register** on an unregistered file row.
2. Form opens immediately in a **blocked/loading** state (spinner, all fields disabled).
3. Backend computes SHA-256 and queries CivitAI (typically 2–10 s).
4. **Match found** → green badge "Found on CivitAI: {model name}", fields pre-filled and editable.
5. **No match** → neutral "Not found on CivitAI" note, fields empty and editable.
6. **Network error** → red "CivitAI lookup failed" + **Retry** button; fields shown empty and editable for manual entry.
7. User edits as needed, clicks **Save** → `POST /api/models/register`.

## Architecture

### Approach selected: Thin route + logic in provider

CivitAI API calls are handled by `CivitaiProvider` (existing pattern). File hash computation
is a utility in `model_paths.py`. The route handler in `models.py` coordinates. This keeps
the lookup logic reusable for issue #92 (auto-migration hook).

## Backend Changes

### New: `compute_file_hash(path: Path) -> str` in `py/services/model_paths.py`

- Synchronous; reads file in 1 MB chunks; returns lowercase hex SHA-256.
- Called via `asyncio.to_thread` in the route handler to avoid blocking the event loop.

### New: `CivitaiProvider.lookup_by_hash(sha256: str) -> dict | None`

- `GET /v1/model-versions/by-hash/{sha256}` with CivitAI auth headers.
- Returns `None` on HTTP 404 (no match).
- Propagates other `httpx.HTTPError` to the caller.
- Parsed return shape:

```python
{
    "name": str,           # model display name (from modelId lookup)
    "base_model": str,
    "description": str,
    "tags": list[str],
    "trigger_words": list[str],
    "version_name": str,
    "civitai_version_id": str,
    "civitai_model_id": str,
}
```

### New route: `POST /api/models/hash-lookup`

Handler `_hash_lookup` in `py/routes/models.py`:

```
Body:   { filename: str, model_type: str }
200 ok: { hash: str, match: true,  metadata: { ... } }
200 ok: { hash: str, match: false }
404:    file_not_found
503:    civitai_unavailable
```

Steps:
1. Validate `filename` + `model_type` present.
2. `model_paths.find_file(model_type, filename)` → 404 if `None`.
3. `hash = await asyncio.to_thread(compute_file_hash, resolved_path)`.
4. `metadata = await civitai_provider.lookup_by_hash(hash)`.
5. Return match/no-match response.
6. Catch `httpx.HTTPError` → 503.

Registered as: `routes.post("/tiny-model-manager/api/models/hash-lookup")(json_route(_hash_lookup))`

### Update: `_upsert_model_row` in `py/db/model_repo.py`

- Add `file_hash: str = ""` parameter.
- Include `file_hash` in `INSERT` columns and `ON CONFLICT DO UPDATE SET`.

### Update: `register_model` in `py/db/model_repo.py`

- Add `file_hash: str = ""` parameter; pass through to `_upsert_model_row`.

### Update: `_register_model` route in `py/routes/models.py`

Accept optional body fields and pass to `register_model`:

| Field | Type | Description |
|-------|------|-------------|
| `file_hash` | `str` | SHA-256 from hash-lookup response |
| `source_platform` | `str` | `"civitai"` when hash matched |
| `source_id` | `str` | CivitAI version ID |
| `civitai_model_id` | `str` | CivitAI model ID |

## Frontend Changes

### `frontend/src/app/services/model.ts`

New interfaces:

```typescript
interface HashLookupMetadata {
  name: string;
  base_model: string;
  description: string;
  tags: string[];
  trigger_words: string[];
  civitai_version_id: string;
  civitai_model_id: string;
}

interface HashLookupResult {
  hash: string;
  match: boolean;
  metadata: HashLookupMetadata | null;
}
```

Update `RegisterModelRequest`:

```typescript
interface RegisterModelRequest {
  filename: string;
  model_type: string;
  base_model?: string;
  description?: string;
  tags?: string[];
  file_hash?: string;
  source_platform?: string;
  source_id?: string;
  civitai_model_id?: string;
}
```

New `ModelService` method:

```typescript
hashLookup(filename: string, modelType: string): Observable<HashLookupResult>
// POST /tiny-model-manager/api/models/hash-lookup
```

### `frontend/src/app/pages/models/models.ts`

Update `RegisterForm` interface — add:

```typescript
hashStatus: 'loading' | 'found' | 'not_found' | 'error';
name: string;
```

New private signals:

```typescript
private registerFileHash = signal<string>('');
private registerCivitaiIds = signal<{ source_id: string; civitai_model_id: string } | null>(null);
```

`openRegisterForm(type, file)`:
- Sets `hashStatus: 'loading'`, opens form in blocked state.
- Calls `modelService.hashLookup(file.filename, type)`.
- On match: updates `hashStatus: 'found'`, pre-fills `name`, `baseModel`, `description`, `tags`; stores hash + CivitAI IDs.
- On no match: sets `hashStatus: 'not_found'`.
- On error: sets `hashStatus: 'error'`.

New `retryHashLookup()`:
- Resets `hashStatus: 'loading'` and re-runs the lookup from the current `registerFormFile`.

`submitRegister()`:
- Includes `file_hash`, `source_platform: 'civitai'`, `source_id`, `civitai_model_id` in the request when `registerFileHash()` is set.

### `frontend/src/app/pages/models/models.html`

Register form block states:

| `hashStatus` | UI |
|---|---|
| `loading` | Spinner row; all fields `[disabled]="true"` |
| `found` | Green badge "Found on CivitAI: {name}"; fields pre-filled, editable |
| `not_found` | Neutral note "Not found on CivitAI"; fields empty, editable |
| `error` | Red "CivitAI lookup failed" + **Retry** button; fields editable for manual entry |

## Error Handling

| Scenario | Backend response | Frontend behaviour |
|----------|-----------------|-------------------|
| File deleted between scan and lookup | 404 `file_not_found` | Shows existing "file gone" message |
| Hash not in CivitAI | 200 `{match: false}` | `hashStatus: 'not_found'` |
| CivitAI network/timeout | 503 `civitai_unavailable` | `hashStatus: 'error'` + Retry button |
| File not found during register | 404 `file_not_found` | Existing "file gone" message |

## Testing

### Backend — `tests/test_routes_models.py`

- `test_hash_lookup_match` — mock `compute_file_hash` + `lookup_by_hash`; assert 200 + full metadata shape
- `test_hash_lookup_no_match` — `lookup_by_hash` returns `None`; assert `{match: false}`
- `test_hash_lookup_file_not_found` — invalid filename; assert 404
- `test_hash_lookup_network_error` — `lookup_by_hash` raises `httpx.HTTPError`; assert 503
- `test_register_model_with_hash` — pass `file_hash` in body; query DB and assert `file_hash` stored

### Backend unit — `tests/test_civitai_provider.py`

- `test_lookup_by_hash_found` — mock HTTP response; assert all parsed metadata fields
- `test_lookup_by_hash_not_found` — mock 404; assert `None` returned

### Frontend — `models.spec.ts`

- Mock `hashLookup()` returning a match → assert `hashStatus === 'found'`, form fields pre-filled
- Mock `hashLookup()` returning no match → assert `hashStatus === 'not_found'`, fields empty
- Mock `hashLookup()` returning error → assert `hashStatus === 'error'`, retry button in DOM
