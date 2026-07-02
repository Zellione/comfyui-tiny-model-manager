# F-90: CivitAI Hash Lookup & Auto-fill — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When the user opens the "Register" dialog for an unregistered model file, automatically compute its SHA-256 hash, query CivitAI for a matching version, and pre-fill the registration form with CivitAI metadata.

**Architecture:** New `compute_file_hash` utility in `model_paths.py`; new `CivitaiProvider.lookup_by_hash` method; new `POST /api/models/hash-lookup` route coordinating both; frontend blocks the register form while lookup runs and pre-fills on match.

**Tech Stack:** Python 3.12+ / aiohttp / httpx / asyncio.to_thread; Angular 21.2 (zoneless signals); Vitest; pytest-asyncio.

## Global Constraints

- All backend tests run with `PYTHONSAFEPATH=1 ../../../comfy-env/bin/python -m pytest` from project root.
- All frontend commands run from `frontend/` directory.
- Ruff lint: `../../../comfy-env/bin/python -m ruff check py tests conftest.py` — 0 errors.
- ESLint: `npx ng lint` — 0 errors.
- Prettier: `npm run format:check` — must pass; new files need `npx prettier --write <file>` immediately after creation.
- Production build required after any frontend change: `npx ng build`.
- Backend coverage gate ≥ 88%; frontend ≥ 74% lines / 62% functions / 74% branches.
- No `asyncio` import exists yet in `py/routes/models.py` — must be added.
- CivitAI hash-by endpoint: `GET https://civitai.com/api/v1/model-versions/by-hash/{sha256}`.

---

### Task 1: `compute_file_hash` utility in `model_paths.py`

**Files:**
- Modify: `py/services/model_paths.py` (append at end)
- Test: `tests/test_model_paths.py`

**Interfaces:**
- Produces: `compute_file_hash(path: Path) -> str` — synchronous; returns lowercase hex SHA-256

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_model_paths.py`:

```python
def test_compute_file_hash_returns_sha256(tmp_path):
    import hashlib
    from pathlib import Path
    from py.services.model_paths import compute_file_hash

    f = tmp_path / "model.safetensors"
    f.write_bytes(b"hello world")
    result = compute_file_hash(f)
    assert result == hashlib.sha256(b"hello world").hexdigest()


def test_compute_file_hash_is_64_char_lowercase_hex(tmp_path):
    from pathlib import Path
    from py.services.model_paths import compute_file_hash

    f = tmp_path / "model.safetensors"
    f.write_bytes(b"\x00" * 64)
    result = compute_file_hash(f)
    assert len(result) == 64
    assert result == result.lower()
    assert all(c in "0123456789abcdef" for c in result)
```

- [ ] **Step 2: Run to confirm failure**

```bash
PYTHONSAFEPATH=1 ../../../comfy-env/bin/python -m pytest tests/test_model_paths.py -v -k "compute_file_hash"
```

Expected: `FAILED` with `ImportError: cannot import name 'compute_file_hash'`

- [ ] **Step 3: Implement `compute_file_hash`**

Append to the bottom of `py/services/model_paths.py`:

```python
def compute_file_hash(path) -> str:
    """Return the lowercase hex SHA-256 of a file. Synchronous; call via asyncio.to_thread."""
    import hashlib
    from pathlib import Path

    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
PYTHONSAFEPATH=1 ../../../comfy-env/bin/python -m pytest tests/test_model_paths.py -v -k "compute_file_hash"
```

Expected: 2 passed

- [ ] **Step 5: Lint check**

```bash
../../../comfy-env/bin/python -m ruff check py/services/model_paths.py
```

Expected: no output (clean)

- [ ] **Step 6: Commit**

```bash
git add py/services/model_paths.py tests/test_model_paths.py
git commit -m "feat: add compute_file_hash utility to model_paths"
```

---

### Task 2: `CivitaiProvider.lookup_by_hash`

**Files:**
- Modify: `py/services/providers/civitai_provider.py`
- Test: `tests/test_civitai_provider.py`

**Interfaces:**
- Consumes: `_BASE = "https://civitai.com/api/v1"`, `self.auth_headers() -> dict` (both exist)
- Produces: `lookup_by_hash(self, sha256: str) -> dict | None`
  - Returns `None` on HTTP 404
  - Returns dict on success: `{"name": str, "base_model": str, "description": str, "tags": list[str], "trigger_words": list[str], "version_name": str, "civitai_version_id": str, "civitai_model_id": str}`
  - Propagates `httpx.HTTPStatusError` on other HTTP errors

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_civitai_provider.py`. The file already defines `_make_transport` and `provider` fixture — use them.

```python
class TestLookupByHash:
    async def test_found_returns_metadata(self, provider, monkeypatch):
        version_data = {
            "id": 12345,
            "name": "v2.0",
            "modelId": 789,
            "baseModel": "SD 1.5",
            "description": "A great model",
            "trainedWords": ["portrait"],
            "images": [{"url": "https://example.com/img.jpg"}],
            "model": {"name": "Great LoRA", "tags": ["portrait", "realistic"]},
        }
        transport = _make_transport({"model-versions/by-hash": (200, version_data)})
        _orig = httpx.AsyncClient
        monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: _orig(transport=transport, **kw))
        result = await provider.lookup_by_hash("deadbeef")
        assert result is not None
        assert result["name"] == "Great LoRA"
        assert result["base_model"] == "SD 1.5"
        assert result["description"] == "A great model"
        assert result["trigger_words"] == ["portrait"]
        assert result["tags"] == ["portrait", "realistic"]
        assert result["version_name"] == "v2.0"
        assert result["civitai_version_id"] == "12345"
        assert result["civitai_model_id"] == "789"

    async def test_not_found_returns_none(self, provider, monkeypatch):
        transport = _make_transport({"model-versions/by-hash": (404, {"error": "not found"})})
        _orig = httpx.AsyncClient
        monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: _orig(transport=transport, **kw))
        result = await provider.lookup_by_hash("notexist")
        assert result is None

    async def test_server_error_propagates(self, provider, monkeypatch):
        transport = _make_transport({"model-versions/by-hash": (500, {"error": "oops"})})
        _orig = httpx.AsyncClient
        monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: _orig(transport=transport, **kw))
        with pytest.raises(httpx.HTTPStatusError):
            await provider.lookup_by_hash("abc123")

    async def test_empty_optional_fields_default(self, provider, monkeypatch):
        version_data = {
            "id": 1,
            "modelId": 2,
            "model": {},
        }
        transport = _make_transport({"model-versions/by-hash": (200, version_data)})
        _orig = httpx.AsyncClient
        monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: _orig(transport=transport, **kw))
        result = await provider.lookup_by_hash("abc")
        assert result["name"] == ""
        assert result["base_model"] == ""
        assert result["description"] == ""
        assert result["tags"] == []
        assert result["trigger_words"] == []
```

- [ ] **Step 2: Run to confirm failure**

```bash
PYTHONSAFEPATH=1 ../../../comfy-env/bin/python -m pytest tests/test_civitai_provider.py::TestLookupByHash -v
```

Expected: `FAILED` with `AttributeError: 'CivitaiProvider' object has no attribute 'lookup_by_hash'`

- [ ] **Step 3: Implement the method**

In `py/services/providers/civitai_provider.py`, append the following method inside `class CivitaiProvider` (after the existing `fetch_metadata` method):

```python
    async def lookup_by_hash(self, sha256: str) -> dict | None:
        """Look up a model version by SHA-256 hash. Returns None if not found on CivitAI."""
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                f"{_BASE}/model-versions/by-hash/{sha256}",
                headers=self.auth_headers(),
            )
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            data = resp.json()
        model = data.get("model") or {}
        return {
            "name": model.get("name", ""),
            "base_model": data.get("baseModel", ""),
            "description": data.get("description") or "",
            "tags": model.get("tags") or [],
            "trigger_words": data.get("trainedWords") or [],
            "version_name": data.get("name", ""),
            "civitai_version_id": str(data.get("id", "")),
            "civitai_model_id": str(data.get("modelId", "")),
        }
```

- [ ] **Step 4: Run tests**

```bash
PYTHONSAFEPATH=1 ../../../comfy-env/bin/python -m pytest tests/test_civitai_provider.py::TestLookupByHash -v
```

Expected: 4 passed

- [ ] **Step 5: Run all provider tests to check for regressions**

```bash
PYTHONSAFEPATH=1 ../../../comfy-env/bin/python -m pytest tests/test_civitai_provider.py -v
```

Expected: all pass

- [ ] **Step 6: Lint**

```bash
../../../comfy-env/bin/python -m ruff check py/services/providers/civitai_provider.py
```

Expected: clean

- [ ] **Step 7: Commit**

```bash
git add py/services/providers/civitai_provider.py tests/test_civitai_provider.py
git commit -m "feat: add CivitaiProvider.lookup_by_hash for SHA-256 hash matching"
```

---

### Task 3: Store `file_hash` + CivitAI IDs in `register_model`

**Files:**
- Modify: `py/db/model_repo.py` (functions `_upsert_model_row` and `register_model`)
- Test: `tests/test_model_repo.py`

**Interfaces:**
- Produces:
  - `_upsert_model_row(..., file_hash: str = "") -> int` — adds `file_hash` to INSERT/UPDATE
  - `register_model(filename, model_type, base_model="", tags=None, description="", file_hash="", source_platform="", source_id="", civitai_model_id="") -> int`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_model_repo.py`:

```python
async def test_register_model_stores_file_hash(ext_dir):
    from py.db import model_repo

    model_id = await model_repo.register_model(
        filename="hashed.safetensors",
        model_type="checkpoints",
        file_hash="aabbccddeeff00112233445566778899aabbccddeeff00112233445566778899",
    )
    assert isinstance(model_id, int)
    row = await model_repo.get_model_by_filename("hashed.safetensors")
    assert row["file_hash"] == "aabbccddeeff00112233445566778899aabbccddeeff00112233445566778899"


async def test_register_model_stores_civitai_ids(ext_dir):
    from py.db import model_repo

    await model_repo.register_model(
        filename="civitai_linked.safetensors",
        model_type="loras",
        source_platform="civitai",
        source_id="12345",
        civitai_model_id="789",
    )
    row = await model_repo.get_model_by_filename("civitai_linked.safetensors")
    assert row["source_platform"] == "civitai"
    assert row["source_id"] == "12345"
    assert row["civitai_model_id"] == "789"


async def test_register_model_file_hash_defaults_to_none(ext_dir):
    from py.db import model_repo

    await model_repo.register_model(
        filename="no_hash.safetensors",
        model_type="checkpoints",
    )
    row = await model_repo.get_model_by_filename("no_hash.safetensors")
    assert row["file_hash"] is None
```

- [ ] **Step 2: Run to confirm failure**

```bash
PYTHONSAFEPATH=1 ../../../comfy-env/bin/python -m pytest tests/test_model_repo.py -v -k "file_hash or civitai_ids or hash_defaults"
```

Expected: FAILED — `register_model()` doesn't accept `file_hash`

- [ ] **Step 3: Update `_upsert_model_row`**

In `py/db/model_repo.py`, replace the existing `_upsert_model_row` function signature and SQL with the version that includes `file_hash`. The function currently lives at the top of the file (around line 45). Replace its entire body:

```python
async def _upsert_model_row(
    db,
    filename: str,
    model_type: str,
    source_platform: str,
    source_id: str,
    description: str,
    base_model: str,
    civitai_model_id: str,
    media_hash: str,
    readme_html: str = "",
    civitai_version_name: str = "",
    file_hash: str = "",
) -> int:
    """Insert/update the models row and return its id (does not commit)."""
    cursor = await db.execute(
        """
        INSERT INTO models (filename, model_type, source_platform, source_id, description, base_model, civitai_model_id, civitai_version_name, media_hash, readme_html, file_hash)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(filename) DO UPDATE SET
            model_type = excluded.model_type,
            source_platform = excluded.source_platform,
            source_id = excluded.source_id,
            description = excluded.description,
            base_model = CASE WHEN excluded.base_model != '' THEN excluded.base_model ELSE base_model END,
            civitai_model_id = excluded.civitai_model_id,
            civitai_version_name = excluded.civitai_version_name,
            media_hash = excluded.media_hash,
            readme_html = excluded.readme_html,
            file_hash = CASE WHEN excluded.file_hash != '' THEN excluded.file_hash ELSE file_hash END
        """,
        (
            filename,
            model_type,
            source_platform,
            source_id,
            description[:_MAX_DESCRIPTION],
            base_model,
            civitai_model_id,
            civitai_version_name,
            media_hash,
            readme_html[:_MAX_DESCRIPTION],
            file_hash,
        ),
    )
    if cursor.lastrowid:
        return cursor.lastrowid
    row = await (
        await db.execute("SELECT id FROM models WHERE filename = ?", (filename,))
    ).fetchone()
    return row["id"]
```

- [ ] **Step 4: Update `register_model`**

Replace the existing `register_model` function body:

```python
async def register_model(
    filename: str,
    model_type: str,
    base_model: str = "",
    tags: list[str] | None = None,
    description: str = "",
    file_hash: str = "",
    source_platform: str = "",
    source_id: str = "",
    civitai_model_id: str = "",
) -> int:
    """Register a model file with minimal metadata. Returns the model ID."""
    if tags is None:
        tags = []
    async with get_db() as db:
        model_id = await _upsert_model_row(
            db,
            filename=filename,
            model_type=model_type,
            source_platform=source_platform,
            source_id=source_id,
            description=description,
            base_model=base_model,
            civitai_model_id=civitai_model_id,
            media_hash="",
            readme_html="",
            civitai_version_name="",
            file_hash=file_hash,
        )
        await _set_model_tags(db, model_id, tags)
        await db.commit()
        return model_id
```

- [ ] **Step 5: Run the new tests**

```bash
PYTHONSAFEPATH=1 ../../../comfy-env/bin/python -m pytest tests/test_model_repo.py -v -k "file_hash or civitai_ids or hash_defaults"
```

Expected: 3 passed

- [ ] **Step 6: Run full test suite to check for regressions**

```bash
PYTHONSAFEPATH=1 ../../../comfy-env/bin/python -m pytest -v
```

Expected: all pass (the `_upsert_model_row` change is backward-compatible — `file_hash` defaults to `""`)

- [ ] **Step 7: Lint**

```bash
../../../comfy-env/bin/python -m ruff check py/db/model_repo.py
```

Expected: clean

- [ ] **Step 8: Commit**

```bash
git add py/db/model_repo.py tests/test_model_repo.py
git commit -m "feat: store file_hash and CivitAI IDs via register_model"
```

---

### Task 4: `POST /api/models/hash-lookup` route + update `/register`

**Files:**
- Modify: `py/routes/models.py`
- Test: `tests/test_routes_models.py`

**Interfaces:**
- Consumes:
  - `model_paths.find_file(model_type, filename) -> str | None`
  - `model_paths.compute_file_hash(path) -> str`
  - `CivitaiProvider().lookup_by_hash(sha256) -> dict | None`
  - `model_repo.register_model(..., file_hash, source_platform, source_id, civitai_model_id)`
- Produces:
  - `POST /tiny-model-manager/api/models/hash-lookup` → `{hash, match, metadata | null}`
  - Updated `POST /tiny-model-manager/api/models/register` → accepts `file_hash`, `source_platform`, `source_id`, `civitai_model_id`

- [ ] **Step 1: Write the failing route tests**

Append the following test class to `tests/test_routes_models.py`:

```python
class TestHashLookup:
    async def test_match_returns_hash_and_metadata(self, client, checkpoints_dir, monkeypatch):
        model_file = os.path.join(checkpoints_dir, "model.safetensors")
        open(model_file, "wb").close()

        monkeypatch.setattr(
            "py.routes.models.asyncio.to_thread",
            lambda fn, *args: _async_return("deadbeefdeadbeef"),
        )
        monkeypatch.setattr(
            "py.routes.models._civitai_lookup",
            lambda sha256: _async_return(
                {
                    "name": "Cool Model",
                    "base_model": "SD 1.5",
                    "description": "Desc",
                    "tags": ["tag1"],
                    "trigger_words": ["word"],
                    "version_name": "v1",
                    "civitai_version_id": "111",
                    "civitai_model_id": "222",
                }
            ),
        )

        resp = await client.post(
            "/tiny-model-manager/api/models/hash-lookup",
            json={"filename": "model.safetensors", "model_type": "checkpoints"},
        )
        assert resp.status == 200
        data = (await resp.json())["data"]
        assert data["match"] is True
        assert data["hash"] == "deadbeefdeadbeef"
        assert data["metadata"]["name"] == "Cool Model"
        assert data["metadata"]["base_model"] == "SD 1.5"

    async def test_no_match_returns_match_false(self, client, checkpoints_dir, monkeypatch):
        model_file = os.path.join(checkpoints_dir, "nohit.safetensors")
        open(model_file, "wb").close()

        monkeypatch.setattr(
            "py.routes.models.asyncio.to_thread",
            lambda fn, *args: _async_return("aaaa"),
        )
        monkeypatch.setattr(
            "py.routes.models._civitai_lookup",
            lambda sha256: _async_return(None),
        )

        resp = await client.post(
            "/tiny-model-manager/api/models/hash-lookup",
            json={"filename": "nohit.safetensors", "model_type": "checkpoints"},
        )
        assert resp.status == 200
        data = (await resp.json())["data"]
        assert data["match"] is False
        assert data["hash"] == "aaaa"
        assert data.get("metadata") is None

    async def test_file_not_found_returns_404(self, client):
        resp = await client.post(
            "/tiny-model-manager/api/models/hash-lookup",
            json={"filename": "missing.safetensors", "model_type": "checkpoints"},
        )
        assert resp.status == 404

    async def test_missing_fields_returns_400(self, client):
        resp = await client.post(
            "/tiny-model-manager/api/models/hash-lookup",
            json={"filename": "model.safetensors"},
        )
        assert resp.status == 400

    async def test_civitai_unavailable_returns_503(self, client, checkpoints_dir, monkeypatch):
        import httpx as _httpx

        model_file = os.path.join(checkpoints_dir, "err.safetensors")
        open(model_file, "wb").close()

        monkeypatch.setattr(
            "py.routes.models.asyncio.to_thread",
            lambda fn, *args: _async_return("bbbb"),
        )

        async def _raise(_):
            raise _httpx.HTTPError("network error")

        monkeypatch.setattr("py.routes.models._civitai_lookup", _raise)

        resp = await client.post(
            "/tiny-model-manager/api/models/hash-lookup",
            json={"filename": "err.safetensors", "model_type": "checkpoints"},
        )
        assert resp.status == 503


async def _async_return(value):
    return value
```

Also append a test for the updated `/register` route inside the existing `TestRegisterModel` class:

```python
    async def test_register_stores_file_hash_and_civitai_ids(self, client, checkpoints_dir):
        from py.db import model_repo

        model_file = os.path.join(checkpoints_dir, "linked.safetensors")
        open(model_file, "wb").close()

        resp = await client.post(
            "/tiny-model-manager/api/models/register",
            json={
                "filename": "linked.safetensors",
                "model_type": "checkpoints",
                "file_hash": "abc123",
                "source_platform": "civitai",
                "source_id": "9999",
                "civitai_model_id": "8888",
            },
        )
        assert resp.status == 200
        row = await model_repo.get_model_by_filename("linked.safetensors")
        assert row["file_hash"] == "abc123"
        assert row["source_platform"] == "civitai"
        assert row["source_id"] == "9999"
```

- [ ] **Step 2: Run to confirm failure**

```bash
PYTHONSAFEPATH=1 ../../../comfy-env/bin/python -m pytest tests/test_routes_models.py::TestHashLookup -v
```

Expected: errors about missing route and `_async_return` / `_civitai_lookup`

- [ ] **Step 3: Implement the route**

Add `import asyncio` and the civitai import, plus the new handler and helper. Edit `py/routes/models.py`:

**At the top** (after existing imports on line ~11), add:

```python
import asyncio
import httpx
```

**After the existing `_register_model` function** (before `add_model_routes`), add:

```python
async def _civitai_lookup(sha256: str) -> dict | None:
    """Thin wrapper so tests can monkeypatch the CivitAI call without touching the provider."""
    from ..services.providers.civitai_provider import CivitaiProvider

    return await CivitaiProvider().lookup_by_hash(sha256)


async def _hash_lookup(request):
    """Compute SHA-256 of a model file and look it up on CivitAI."""
    body = await request.json()
    filename = body.get("filename", "").strip()
    model_type = body.get("model_type", "").strip()
    if not filename or not model_type:
        return err("filename and model_type are required", 400)

    resolved = model_paths.find_file(model_type, filename)
    if resolved is None:
        return err("file_not_found", 404)

    file_hash = await asyncio.to_thread(model_paths.compute_file_hash, resolved)

    try:
        metadata = await _civitai_lookup(file_hash)
    except httpx.HTTPError:
        return err("civitai_unavailable", 503)

    if metadata is None:
        return ok({"hash": file_hash, "match": False})
    return ok({"hash": file_hash, "match": True, "metadata": metadata})
```

- [ ] **Step 4: Update `_register_model` to pass the new optional fields**

Replace the existing `_register_model` function body:

```python
async def _register_model(request):
    """Register a model file manually with optional metadata."""
    body = await request.json()
    filename = body.get("filename", "").strip()
    model_type = body.get("model_type", "").strip()
    if not filename or not model_type:
        return err("filename and model_type are required", 400)

    base_model = body.get("base_model", "").strip()
    tags = body.get("tags") or []
    description = body.get("description", "")
    file_hash = body.get("file_hash", "").strip()
    source_platform = body.get("source_platform", "").strip()
    source_id = body.get("source_id", "").strip()
    civitai_model_id = body.get("civitai_model_id", "").strip()

    resolved = model_paths.find_file(model_type, filename)
    if resolved is None:
        return err("file_not_found", 404)

    model_id = await model_repo.register_model(
        filename=filename,
        model_type=model_type,
        base_model=base_model,
        tags=tags,
        description=description,
        file_hash=file_hash,
        source_platform=source_platform,
        source_id=source_id,
        civitai_model_id=civitai_model_id,
    )
    return ok({"model_id": model_id})
```

- [ ] **Step 5: Register the new route in `add_model_routes`**

In `add_model_routes`, add after the `/register` route:

```python
    routes.post("/tiny-model-manager/api/models/hash-lookup")(json_route(_hash_lookup))
```

- [ ] **Step 6: Run the new tests**

```bash
PYTHONSAFEPATH=1 ../../../comfy-env/bin/python -m pytest tests/test_routes_models.py::TestHashLookup tests/test_routes_models.py::TestRegisterModel::test_register_stores_file_hash_and_civitai_ids -v
```

Expected: all pass

- [ ] **Step 7: Run the full test suite**

```bash
PYTHONSAFEPATH=1 ../../../comfy-env/bin/python -m pytest -v
```

Expected: all pass

- [ ] **Step 8: Lint**

```bash
../../../comfy-env/bin/python -m ruff check py/routes/models.py
```

Expected: clean

- [ ] **Step 9: Commit**

```bash
git add py/routes/models.py tests/test_routes_models.py
git commit -m "feat: add POST /api/models/hash-lookup route and store CivitAI IDs on register"
```

---

### Task 5: Frontend — `ModelService` interfaces + `hashLookup` method

**Files:**
- Modify: `frontend/src/app/services/model.ts`
- Test: `frontend/src/app/services/model.spec.ts`

**Interfaces:**
- Produces:
  ```typescript
  interface HashLookupMetadata { name: string; base_model: string; description: string; tags: string[]; trigger_words: string[]; version_name: string; civitai_version_id: string; civitai_model_id: string; }
  interface HashLookupResult { hash: string; match: boolean; metadata: HashLookupMetadata | null; }
  // RegisterModelRequest gains optional: file_hash?, source_platform?, source_id?, civitai_model_id?
  // ModelService.hashLookup(filename, modelType): Observable<HashLookupResult>
  ```

- [ ] **Step 1: Write failing service tests**

In `frontend/src/app/services/model.spec.ts`, find the test block for `ModelService` and append:

```typescript
describe('hashLookup', () => {
  it('calls POST /hash-lookup and returns result', () => {
    const service = TestBed.inject(ModelService);
    const http = TestBed.inject(HttpTestingController);

    const mockResult: HashLookupResult = {
      hash: 'abc123',
      match: true,
      metadata: {
        name: 'Cool LoRA',
        base_model: 'SD 1.5',
        description: 'A description',
        tags: ['portrait'],
        trigger_words: ['portrait, detailed'],
        version_name: 'v2',
        civitai_version_id: '111',
        civitai_model_id: '222',
      },
    };

    service.hashLookup('model.safetensors', 'loras').subscribe((result) => {
      expect(result).toEqual(mockResult);
    });

    const req = http.expectOne('/tiny-model-manager/api/models/hash-lookup');
    expect(req.request.method).toBe('POST');
    expect(req.request.body).toEqual({ filename: 'model.safetensors', model_type: 'loras' });
    req.flush({ success: true, data: mockResult });
  });
});
```

Also add import at the top of the test file (if not already present):
```typescript
import { HashLookupResult } from './model';
```

- [ ] **Step 2: Run to confirm failure**

```bash
npx ng test --watch=false 2>&1 | grep -A3 "hashLookup"
```

Expected: compile error — `HashLookupResult` not found

- [ ] **Step 3: Add interfaces and method to `model.ts`**

In `frontend/src/app/services/model.ts`:

After the existing `UnregisteredFile` interface, add:

```typescript
export interface HashLookupMetadata {
  name: string;
  base_model: string;
  description: string;
  tags: string[];
  trigger_words: string[];
  version_name: string;
  civitai_version_id: string;
  civitai_model_id: string;
}

export interface HashLookupResult {
  hash: string;
  match: boolean;
  metadata: HashLookupMetadata | null;
}
```

Update `RegisterModelRequest` — add optional fields:

```typescript
export interface RegisterModelRequest {
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

Add `hashLookup` method to `ModelService`:

```typescript
hashLookup(filename: string, modelType: string): Observable<HashLookupResult> {
  return this.http
    .post<{ success: boolean; data: HashLookupResult }>(
      `${API}/models/hash-lookup`,
      { filename, model_type: modelType },
    )
    .pipe(map((r) => r.data));
}
```

- [ ] **Step 4: Run tests**

```bash
npx ng test --watch=false 2>&1 | tail -20
```

Expected: all pass

- [ ] **Step 5: Lint and format**

```bash
npx ng lint && npm run format:check
```

Expected: clean

- [ ] **Step 6: Commit**

```bash
git add frontend/src/app/services/model.ts frontend/src/app/services/model.spec.ts
git commit -m "feat: add HashLookupResult interfaces and ModelService.hashLookup"
```

---

### Task 6: Frontend — component logic, i18n keys, and tests

**Files:**
- Modify: `frontend/src/app/pages/models/models.ts`
- Modify: `frontend/src/app/pages/models/models.spec.ts`
- Modify: `frontend/public/i18n/en.json`

**Interfaces:**
- Consumes:
  - `ModelService.hashLookup(filename, modelType): Observable<HashLookupResult>`
  - `HashLookupMetadata` (from model.ts)
- Produces:
  - `RegisterForm.hashStatus: 'loading' | 'found' | 'not_found' | 'error'`
  - `RegisterForm.name: string`
  - `Models.retryHashLookup(): void`
  - Updated `openRegisterForm` — triggers hash lookup, updates form signals
  - Updated `submitRegister` — sends `file_hash`, CivitAI IDs when available

- [ ] **Step 1: Add new i18n keys**

In `frontend/public/i18n/en.json`, inside the `"unregistered"` object, add these keys:

```json
"lookup_loading": "Looking up on CivitAI…",
"lookup_found": "Found on CivitAI: {{name}}",
"lookup_not_found": "Not found on CivitAI — fill in details manually.",
"lookup_error": "CivitAI lookup failed.",
"lookup_retry": "Retry"
```

- [ ] **Step 2: Write the failing component tests**

In `frontend/src/app/pages/models/models.spec.ts`:

Add `hashLookup: vi.fn()` to the `mockModelService` object:

```typescript
const mockModelService = {
  listCatalog: vi.fn(),
  deleteModel: vi.fn(),
  organizeIntoSubfolders: vi.fn(),
  getModelTypes: vi.fn(),
  moveModel: vi.fn(),
  getPendingQueue: vi.fn(),
  getUnregistered: vi.fn(),
  registerModel: vi.fn(),
  hashLookup: vi.fn(),   // ADD THIS LINE
};
```

Then add these tests inside the `describe('Unregistered files section')` block (or append near the existing register tests):

```typescript
it('openRegisterForm() triggers hash lookup and sets hashStatus found on match', async () => {
  const { HashLookupResult } = await import('../../services/model');
  const matchResult = {
    hash: 'abc123',
    match: true,
    metadata: {
      name: 'Great LoRA',
      base_model: 'SD 1.5',
      description: 'A great model',
      tags: ['portrait'],
      trigger_words: ['portrait'],
      version_name: 'v2',
      civitai_version_id: '111',
      civitai_model_id: '222',
    },
  };
  mockModelService.hashLookup.mockReturnValue(of(matchResult));

  const component = await getComponent();
  const file = { filename: 'model.safetensors', base_dir: '/models', size_bytes: 100, modified_at: 0 };
  component.openRegisterForm('loras', file);

  expect(component.registerForm().hashStatus).toBe('found');
  expect(component.registerForm().name).toBe('Great LoRA');
  expect(component.registerForm().baseModel).toBe('SD 1.5');
  expect(component.registerForm().description).toBe('A great model');
  expect(component.registerForm().tags).toBe('portrait');
});

it('openRegisterForm() sets hashStatus not_found when no match', async () => {
  mockModelService.hashLookup.mockReturnValue(of({ hash: 'xyz', match: false, metadata: null }));

  const component = await getComponent();
  const file = { filename: 'model.safetensors', base_dir: '/models', size_bytes: 100, modified_at: 0 };
  component.openRegisterForm('loras', file);

  expect(component.registerForm().hashStatus).toBe('not_found');
  expect(component.registerForm().name).toBe('');
});

it('openRegisterForm() sets hashStatus error on lookup failure', async () => {
  mockModelService.hashLookup.mockReturnValue(throwError(() => new Error('network')));

  const component = await getComponent();
  const file = { filename: 'model.safetensors', base_dir: '/models', size_bytes: 100, modified_at: 0 };
  component.openRegisterForm('loras', file);

  expect(component.registerForm().hashStatus).toBe('error');
});

it('retryHashLookup() re-runs the lookup', async () => {
  mockModelService.hashLookup.mockReturnValue(of({ hash: 'xyz', match: false, metadata: null }));

  const component = await getComponent();
  const file = { filename: 'model.safetensors', base_dir: '/models', size_bytes: 100, modified_at: 0 };
  component.openRegisterForm('loras', file);
  const callsBefore = mockModelService.hashLookup.mock.calls.length;
  component.retryHashLookup();

  expect(mockModelService.hashLookup.mock.calls.length).toBe(callsBefore + 1);
});

it('submitRegister() includes file_hash and CivitAI IDs when a match was found', async () => {
  mockModelService.hashLookup.mockReturnValue(
    of({
      hash: 'abc123',
      match: true,
      metadata: {
        name: 'Great LoRA',
        base_model: 'SD 1.5',
        description: '',
        tags: [],
        trigger_words: [],
        version_name: 'v2',
        civitai_version_id: '111',
        civitai_model_id: '222',
      },
    }),
  );
  mockModelService.registerModel.mockReturnValue(of({ model_id: 1 }));
  mockModelService.listCatalog.mockReturnValue(of(emptyCatalog));

  const component = await getComponent();
  const file = { filename: 'model.safetensors', base_dir: '/models', size_bytes: 100, modified_at: 0 };
  component.unregisteredFiles.set({ loras: [file] });
  component.openRegisterForm('loras', file);
  component.submitRegister();

  expect(mockModelService.registerModel).toHaveBeenCalledWith(
    expect.objectContaining({
      file_hash: 'abc123',
      source_platform: 'civitai',
      source_id: '111',
      civitai_model_id: '222',
    }),
  );
});
```

- [ ] **Step 3: Run to confirm failure**

```bash
npx ng test --watch=false 2>&1 | grep -E "FAIL|hashStatus|retryHashLookup"
```

Expected: compile or test failures

- [ ] **Step 4: Update `RegisterForm` interface in `models.ts`**

Replace the existing `RegisterForm` interface:

```typescript
interface RegisterForm {
  modelType: string;
  baseModel: string;
  description: string;
  tags: string;
  saving: boolean;
  error: string;
  hashStatus: 'loading' | 'found' | 'not_found' | 'error';
  name: string;
}
```

- [ ] **Step 5: Add private signals to the `Models` class**

Inside the `Models` class (after existing signal declarations), add:

```typescript
private readonly registerFileHash = signal<string>('');
private readonly registerCivitaiIds = signal<{
  source_id: string;
  civitai_model_id: string;
} | null>(null);
```

- [ ] **Step 6: Add `DestroyRef` import and update `openRegisterForm`**

Ensure `takeUntilDestroyed` is imported (already likely present — check the existing imports in `models.ts`). Then replace `openRegisterForm`:

```typescript
openRegisterForm(type: string, file: UnregisteredFile): void {
  this.registerFormFile.set({ type, file });
  this.registerForm.set({
    modelType: type,
    baseModel: '',
    description: '',
    tags: '',
    saving: false,
    error: '',
    hashStatus: 'loading',
    name: '',
  });
  this.registerFileHash.set('');
  this.registerCivitaiIds.set(null);
  this._runHashLookup(file.filename, type);
}
```

- [ ] **Step 7: Add `_runHashLookup` and `retryHashLookup` methods**

```typescript
private _runHashLookup(filename: string, modelType: string): void {
  this.modelService.hashLookup(filename, modelType).subscribe({
    next: (result) => {
      this.registerFileHash.set(result.hash);
      if (result.match && result.metadata) {
        const m = result.metadata;
        this.registerCivitaiIds.set({
          source_id: m.civitai_version_id,
          civitai_model_id: m.civitai_model_id,
        });
        this.registerForm.update((f) => ({
          ...f,
          hashStatus: 'found',
          name: m.name,
          baseModel: m.base_model,
          description: m.description,
          tags: m.tags.join(', '),
        }));
      } else {
        this.registerForm.update((f) => ({ ...f, hashStatus: 'not_found' }));
      }
    },
    error: () => {
      this.registerForm.update((f) => ({ ...f, hashStatus: 'error' }));
    },
  });
}

retryHashLookup(): void {
  const formFile = this.registerFormFile();
  if (!formFile) return;
  this.registerForm.update((f) => ({ ...f, hashStatus: 'loading', error: '' }));
  this._runHashLookup(formFile.file.filename, formFile.type);
}
```

- [ ] **Step 8: Update `submitRegister` to send hash + CivitAI IDs**

Replace the existing `submitRegister` method:

```typescript
submitRegister(): void {
  const formFile = this.registerFormFile();
  if (!formFile) return;
  const form = this.registerForm();
  const req: RegisterModelRequest = {
    filename: formFile.file.filename,
    model_type: form.modelType,
  };
  if (form.baseModel) req.base_model = form.baseModel;
  if (form.description) req.description = form.description;
  const tags = form.tags
    .split(',')
    .map((t) => t.trim())
    .filter(Boolean);
  if (tags.length > 0) req.tags = tags;

  const hash = this.registerFileHash();
  const ids = this.registerCivitaiIds();
  if (hash) {
    req.file_hash = hash;
    if (ids) {
      req.source_platform = 'civitai';
      req.source_id = ids.source_id;
      req.civitai_model_id = ids.civitai_model_id;
    }
  }

  this.registerForm.update((f) => ({ ...f, saving: true, error: '' }));
  this.modelService.registerModel(req).subscribe({
    next: () => {
      const mtype = formFile.type;
      const fname = formFile.file.filename;
      this.unregisteredFiles.update((prev) => {
        const updated = { ...prev };
        updated[mtype] = (updated[mtype] ?? []).filter((f) => f.filename !== fname);
        if (updated[mtype].length === 0) delete updated[mtype];
        return updated;
      });
      this.registerFormFile.set(null);
      this.load();
    },
    error: (err) => {
      const msg =
        err?.error?.error === 'file_not_found'
          ? this.translate.instant('models.unregistered.file_gone')
          : this.translate.instant('models.unregistered.register_failed');
      this.registerForm.update((f) => ({ ...f, saving: false, error: msg }));
    },
  });
}
```

- [ ] **Step 9: Update existing `openRegisterForm` test**

The existing test `'openRegisterForm() sets registerFormFile with type and file'` in `models.spec.ts` will now fail because `openRegisterForm` calls `hashLookup`. Fix it by ensuring `mockModelService.hashLookup` has a default return value. In the `getComponent` helper (or `beforeEach` block), add:

```typescript
mockModelService.hashLookup.mockReturnValue(of({ hash: '', match: false, metadata: null }));
```

- [ ] **Step 10: Run all frontend tests**

```bash
npx ng test --watch=false
```

Expected: all pass

- [ ] **Step 11: Lint and format**

```bash
npx ng lint && npm run format:check
```

Expected: clean. If Prettier reports issues, run `npm run format:write` (or `npx prettier --write frontend/src/app/pages/models/models.ts frontend/public/i18n/en.json`).

- [ ] **Step 12: Commit**

```bash
git add frontend/src/app/pages/models/models.ts frontend/src/app/pages/models/models.spec.ts frontend/public/i18n/en.json
git commit -m "feat: hash lookup logic in Models component with retry and CivitAI pre-fill"
```

---

### Task 7: Frontend — template hash-status states + production build

**Files:**
- Modify: `frontend/src/app/pages/models/models.html`
- Modify: `frontend/src/app/pages/models/models.scss` (if spinner styling needed)

- [ ] **Step 1: Locate the inline register form block in the template**

The register form is inside `@if (registerFormFile()?.file?.filename === file.filename)` (around line 359 of `models.html`). The current content is `<div class="register-form-inline">` with `<div class="register-form-fields">`.

- [ ] **Step 2: Add a hash-status header above the form fields**

Inside `<div class="register-form-inline">`, before `<div class="register-form-fields">`, insert:

```html
<!-- Hash lookup status banner -->
@if (registerForm().hashStatus === 'loading') {
  <div class="register-lookup-status register-lookup-loading">
    <span class="lookup-spinner"></span>
    {{ 'models.unregistered.lookup_loading' | translate }}
  </div>
} @else if (registerForm().hashStatus === 'found') {
  <div class="register-lookup-status register-lookup-found">
    {{ 'models.unregistered.lookup_found' | translate: { name: registerForm().name } }}
  </div>
} @else if (registerForm().hashStatus === 'not_found') {
  <div class="register-lookup-status register-lookup-not-found">
    {{ 'models.unregistered.lookup_not_found' | translate }}
  </div>
} @else if (registerForm().hashStatus === 'error') {
  <div class="register-lookup-status register-lookup-error">
    {{ 'models.unregistered.lookup_error' | translate }}
    <button class="btn-retry" (click)="retryHashLookup()">
      {{ 'models.unregistered.lookup_retry' | translate }}
    </button>
  </div>
}
```

- [ ] **Step 3: Disable form fields while loading**

In each form `<input>` and `<textarea>` inside `<div class="register-form-fields">`, add `[disabled]="registerForm().hashStatus === 'loading'"`.

The fields are:
1. Base model input (near the `[value]="registerForm().baseModel"` binding)
2. Tags input
3. Description textarea

For example, the base model input becomes:
```html
<input
  class="input-field"
  [value]="registerForm().baseModel"
  [disabled]="registerForm().hashStatus === 'loading'"
  (input)="registerForm.update((f) => ({ ...f, baseModel: $any($event.target).value }))"
/>
```

Apply the same `[disabled]="registerForm().hashStatus === 'loading'"` to the tags and description fields.

- [ ] **Step 4: Add minimal spinner and status styles**

In `frontend/src/app/pages/models/models.scss`, append:

```scss
.register-lookup-status {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-radius: 4px;
  font-size: 0.85rem;
  margin-bottom: 8px;
}

.register-lookup-loading {
  background: color-mix(in srgb, var(--p-surface-100) 80%, transparent);
  color: var(--p-text-color-secondary);
}

.register-lookup-found {
  background: color-mix(in srgb, var(--p-green-100) 60%, transparent);
  color: var(--p-green-700);
}

.register-lookup-not-found {
  background: color-mix(in srgb, var(--p-surface-100) 80%, transparent);
  color: var(--p-text-color-secondary);
}

.register-lookup-error {
  background: color-mix(in srgb, var(--p-red-100) 60%, transparent);
  color: var(--p-red-700);
  justify-content: space-between;
}

.lookup-spinner {
  display: inline-block;
  width: 12px;
  height: 12px;
  border: 2px solid currentColor;
  border-top-color: transparent;
  border-radius: 50%;
  animation: spin 0.6s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.btn-retry {
  font-size: 0.8rem;
  padding: 2px 8px;
  border: 1px solid currentColor;
  border-radius: 4px;
  background: transparent;
  color: inherit;
  cursor: pointer;
}
```

- [ ] **Step 5: Run all frontend tests again**

```bash
npx ng test --watch=false
```

Expected: all pass (template changes don't affect unit tests unless signals are tested)

- [ ] **Step 6: Run full lint and format check**

```bash
npx ng lint && npm run format:check
```

- [ ] **Step 7: Production build**

```bash
npx ng build
```

Expected: Build complete with no errors.

- [ ] **Step 8: Run full backend suite one final time**

```bash
PYTHONSAFEPATH=1 ../../../comfy-env/bin/python -m pytest
```

Expected: all pass

- [ ] **Step 9: Commit**

```bash
git add frontend/src/app/pages/models/models.html frontend/src/app/pages/models/models.scss
git commit -m "feat: register form shows hash lookup status with spinner, badge, and retry"
```

---

## Completion Checklist

- [ ] All backend tests pass (`pytest`)
- [ ] Ruff lint clean on all changed Python files
- [ ] All frontend tests pass (`npx ng test --watch=false`)
- [ ] ESLint clean (`npx ng lint`)
- [ ] Prettier clean (`npm run format:check`)
- [ ] Production build succeeds (`npx ng build`)
- [ ] Coverage gates met (backend ≥ 88%, frontend ≥ 74%/62%/74%)
