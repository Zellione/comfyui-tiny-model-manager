# Upload a model card image — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the user upload their own preview images for a model or catalog entry that has none, and remove those uploads again.

**Architecture:** Uploaded files are written into the existing per-model media directory `data/media/<media_hash>/` under the reserved name `upload-<12 hex>.<ext>`. The filename is the only marker — catalog media has no database rows (it is a directory listing), so a `model_media` column could not have covered both halves. A new leaf service `py/services/media_upload.py` owns the name format, magic-byte sniffing, the size cap, and the guarded write/delete. Four routes (two per domain) wrap it, and the route layer annotates every gallery item with `uploaded: bool`. On the frontend a new presentational `MediaUploadZone` feeds `MediaGallery`, which the two detail pages drive.

**Tech Stack:** Python 3.12 / aiohttp / aiosqlite / pytest; Angular 21.2 zoneless / signals / Vitest / ngx-translate.

Spec: `docs/superpowers/specs/2026-08-08-upload-model-card-image-design.md`
Issue: https://github.com/Zellione/comfyui-tiny-model-manager/issues/159
Branch: `upload-model-card-image` (already checked out)

## Global Constraints

- Commits and code comments in English. Never add a Co-authored-by trailer.
- Backend commands run from the repo root with `PYTHONSAFEPATH=1 ../../../comfy-env/bin/python -m …`.
- Frontend commands run from `frontend/`.
- Ruff rules E/F/I/UP/B, 0 errors. ESLint 0 errors. Prettier must pass `npm run format:check`.
- Every new file under `frontend/` gets `npx prettier --write <file>` immediately after creation.
- Angular: `ChangeDetectionStrategy.OnPush`, signals only (no Zone.js), every `.subscribe()` carries `takeUntilDestroyed(this.destroyRef)`.
- All user-visible strings go through ngx-translate keys in `frontend/public/i18n/en.json` (the only locale file).
- Accepted image types: JPEG, PNG, WebP, GIF. `MAX_UPLOAD_BYTES = 10 * 1024 * 1024`. `MAX_FILES = 10`.
- Reserved upload name: `UPLOAD_NAME_RE = re.compile(r"upload-[0-9a-f]{12}\.(?:jpg|png|webp|gif)")`.
- Nothing is written or deleted by a raw request path: directories go through `media_cleanup.media_subdir()`, entry names through `UPLOAD_NAME_RE` and `model_paths.contained_path()`.
- Do NOT push, open a PR, or edit the GitHub project board — the user does that.

---

### Task 1: `media_upload` service

**Files:**
- Create: `py/services/media_upload.py`
- Test: `tests/test_media_upload.py`

**Interfaces:**
- Consumes: `py.services.media_cleanup.media_subdir`, `py.services.model_paths.contained_path`, the `ext_dir` fixture from `tests/conftest.py`.
- Produces:
  - `MAX_UPLOAD_BYTES: int`, `MAX_FILES: int`, `UPLOAD_NAME_RE: re.Pattern`
  - `class UploadTooLarge(Exception)`, `class UnsupportedImage(Exception)`
  - `sniff_image_ext(head: bytes) -> str | None`
  - `upload_name(ext: str) -> str`
  - `is_uploaded(path: str) -> bool`
  - `async store_upload(media_hash: str, part) -> str` (returns the absolute stored path)
  - `delete_upload(media_hash: str, name: str) -> bool`

- [ ] **Step 1: Write the failing test**

Create `tests/test_media_upload.py`:

```python
"""Unit tests for py/services/media_upload.py."""

import os

import pytest

_JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 32
_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
_WEBP = b"RIFF\x00\x00\x00\x00WEBP" + b"\x00" * 32
_GIF = b"GIF89a" + b"\x00" * 32


class _FakePart:
    """Minimal stand-in for aiohttp's BodyPartReader."""

    def __init__(self, data: bytes, chunk_size: int = 8):
        self._data = data
        self._chunk = chunk_size
        self._pos = 0

    async def read_chunk(self, size: int) -> bytes:
        step = min(size, self._chunk)
        out = self._data[self._pos : self._pos + step]
        self._pos += len(out)
        return out


@pytest.mark.parametrize(
    ("data", "expected"),
    [(_JPEG, "jpg"), (_PNG, "png"), (_WEBP, "webp"), (_GIF, "gif")],
)
def test_sniff_image_ext_recognises_supported_types(data, expected):
    from py.services import media_upload

    assert media_upload.sniff_image_ext(data) == expected


@pytest.mark.parametrize("data", [b"", b"not an image at all", b"%PDF-1.7\n%\xe2\xe3\xcf\xd3"])
def test_sniff_image_ext_rejects_everything_else(data):
    from py.services import media_upload

    assert media_upload.sniff_image_ext(data) is None


def test_upload_name_round_trips_through_is_uploaded():
    from py.services import media_upload

    name = media_upload.upload_name("png")
    assert media_upload.UPLOAD_NAME_RE.fullmatch(name)
    assert media_upload.is_uploaded(os.path.join("/media", "abc", name))


def test_upload_name_is_unique_per_call():
    from py.services import media_upload

    names = {media_upload.upload_name("jpg") for _ in range(20)}
    assert len(names) == 20


@pytest.mark.parametrize(
    "path",
    ["/media/abc/0.jpg", "/media/abc/1.webp", "/media/abc/0_poster.jpg", "/media/abc/uploads.jpg"],
)
def test_is_uploaded_is_false_for_fetched_media(path):
    from py.services import media_upload

    assert media_upload.is_uploaded(path) is False


async def test_store_upload_writes_a_sniffed_name(ext_dir):
    from py.services import media_upload

    dest = await media_upload.store_upload("deadbeef", _FakePart(_PNG))

    assert os.path.isfile(dest)
    assert dest.endswith(".png")
    assert media_upload.is_uploaded(dest)
    with open(dest, "rb") as fh:
        assert fh.read() == _PNG


async def test_store_upload_ignores_the_declared_type_and_uses_the_bytes(ext_dir):
    from py.services import media_upload

    # A part whose filename claims .png but whose bytes are JPEG must be stored as .jpg.
    dest = await media_upload.store_upload("deadbeef", _FakePart(_JPEG))

    assert dest.endswith(".jpg")


async def test_store_upload_rejects_a_non_image(ext_dir):
    from py.services import media_upload

    with pytest.raises(media_upload.UnsupportedImage):
        await media_upload.store_upload("deadbeef", _FakePart(b"<html>nope</html>" * 4))


async def test_store_upload_rejects_an_oversized_part_without_writing(ext_dir):
    from py.services import media_upload
    from py.services import media_cleanup

    oversized = _JPEG + b"\x00" * (media_upload.MAX_UPLOAD_BYTES + 1)
    with pytest.raises(media_upload.UploadTooLarge):
        await media_upload.store_upload("deadbeef", _FakePart(oversized, chunk_size=65536))

    target = media_cleanup.media_subdir("deadbeef")
    assert not os.path.isdir(target) or os.listdir(target) == []


async def test_delete_upload_removes_the_file(ext_dir):
    from py.services import media_upload

    dest = await media_upload.store_upload("deadbeef", _FakePart(_PNG))

    assert media_upload.delete_upload("deadbeef", os.path.basename(dest)) is True
    assert not os.path.exists(dest)


@pytest.mark.parametrize("name", ["0.jpg", "../../etc/passwd", "upload-zzzzzzzzzzzz.png", ""])
async def test_delete_upload_refuses_anything_but_an_upload_name(ext_dir, name):
    from py.services import media_upload

    assert media_upload.delete_upload("deadbeef", name) is False


async def test_delete_upload_returns_false_for_a_missing_file(ext_dir):
    from py.services import media_upload

    assert media_upload.delete_upload("deadbeef", media_upload.upload_name("png")) is False


async def test_delete_upload_returns_false_for_an_invalid_media_hash(ext_dir):
    from py.services import media_upload

    assert media_upload.delete_upload("../escape", media_upload.upload_name("png")) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONSAFEPATH=1 ../../../comfy-env/bin/python -m pytest tests/test_media_upload.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'py.services.media_upload'`

- [ ] **Step 3: Write the implementation**

Create `py/services/media_upload.py`:

```python
"""User-uploaded model card images (F-159).

An upload is written into the existing per-model media directory as
``upload-<12 hex>.<ext>``. **The filename is the marker.** Catalog media has no database
rows at all — ``routes/catalog._list_catalog_media`` enumerates the directory — so a
``model_media`` column could only ever have covered the model half of the feature. The
same regex that recognises an upload doubles as the sanitizer on the delete routes.

Nothing reaches the filesystem by a raw request path: the directory is resolved through
``media_cleanup.media_subdir`` and every entry name is matched against ``UPLOAD_NAME_RE``
and then ``model_paths.contained_path``.

``media_cleanup`` and ``model_paths`` are imported inside the functions that need them,
not at module top. ``media_cleanup`` imports ``model_repo``, and the route layer imports
this module to annotate gallery items; keeping the top-level imports to the standard
library keeps this a leaf module and rules out an import cycle.
"""

import asyncio
import os
import re
import uuid
from pathlib import Path

# Per-file and per-request ceilings. The read aborts the moment the running byte count
# passes the cap, so an oversized upload never allocates more than it.
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_FILES = 10

_CHUNK = 64 * 1024

UPLOAD_PREFIX = "upload-"
UPLOAD_NAME_RE = re.compile(r"upload-[0-9a-f]{12}\.(?:jpg|png|webp|gif)")


class UploadTooLarge(Exception):
    """A part exceeded ``MAX_UPLOAD_BYTES``."""


class UnsupportedImage(Exception):
    """A part's bytes matched none of the accepted image signatures."""


def sniff_image_ext(head: bytes) -> str | None:
    """Return the extension for the image the bytes actually are, or None.

    The client-supplied filename and Content-Type are never consulted: a caller that
    trusts them will happily store an HTML page under a ``.png`` name.
    """
    if head.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "webp"
    if head[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    return None


def upload_name(ext: str) -> str:
    """Build a reserved upload filename.

    Fetched media is named ``0.jpg``, ``1.jpg``, … by ``metadata_fetcher``, so this
    namespace can never collide with a later re-fetch.
    """
    return f"{UPLOAD_PREFIX}{uuid.uuid4().hex[:12]}.{ext}"


def is_uploaded(path: str) -> bool:
    """True when the path's basename is a reserved upload name."""
    return bool(UPLOAD_NAME_RE.fullmatch(os.path.basename(path)))


async def store_upload(media_hash: str, part) -> str:
    """Store one multipart part in the media dir; return the absolute path written.

    Raises ``UploadTooLarge`` past the cap and ``UnsupportedImage`` when the bytes are
    not one of the four accepted formats. Neither case touches the filesystem, so there
    is no partial file to clean up.
    """
    from . import media_cleanup

    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await part.read_chunk(_CHUNK)
        if not chunk:
            break
        total += len(chunk)
        if total > MAX_UPLOAD_BYTES:
            raise UploadTooLarge(f"Upload exceeds {MAX_UPLOAD_BYTES} bytes")
        chunks.append(chunk)

    data = b"".join(chunks)
    ext = sniff_image_ext(data[:12])
    if ext is None:
        raise UnsupportedImage("Unsupported image type")

    dest_dir = media_cleanup.media_subdir(media_hash)
    os.makedirs(dest_dir, exist_ok=True)
    dest = os.path.join(dest_dir, upload_name(ext))
    await asyncio.to_thread(Path(dest).write_bytes, data)
    return dest


def delete_upload(media_hash: str, name: str) -> bool:
    """Remove one uploaded file. Returns False for anything that is not an upload."""
    from . import media_cleanup, model_paths

    if not UPLOAD_NAME_RE.fullmatch(name):
        return False
    try:
        dest_dir = media_cleanup.media_subdir(media_hash)
    except ValueError:
        return False
    full = model_paths.contained_path(dest_dir, name)
    if full is None or not os.path.isfile(full):
        return False
    os.remove(full)
    return True
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONSAFEPATH=1 ../../../comfy-env/bin/python -m pytest tests/test_media_upload.py -v`
Expected: PASS (all cases)

- [ ] **Step 5: Lint and commit**

```bash
PYTHONSAFEPATH=1 ../../../comfy-env/bin/python -m ruff check py tests conftest.py
PYTHONSAFEPATH=1 ../../../comfy-env/bin/python -m ruff format --check py tests conftest.py
git add py/services/media_upload.py tests/test_media_upload.py
git commit -m "feat(media): add the media_upload service for user-supplied card images (#159)"
```

---

### Task 2: Model-side upload and delete routes

**Files:**
- Modify: `py/routes/metadata.py` (add handlers, extend `_meta_response_data` at lines 92-111, register routes in `add_metadata_routes` at lines 412-422)
- Test: `tests/test_routes_metadata.py`

**Interfaces:**
- Consumes: `media_upload.{store_upload, delete_upload, is_uploaded, MAX_FILES, UploadTooLarge, UnsupportedImage}` from Task 1; existing `model_repo.{get_model_by_filename, add_media, get_model_media, delete_media_row}`; `metadata_fetcher._compute_media_hash`.
- Produces:
  - `POST /tiny-model-manager/api/models/{model_type}/{path:.*}/media` → `ok({"media": [...]})`
  - `DELETE /tiny-model-manager/api/models/{model_type}/{path:.*}/media/{media_id}` → `ok({"media": [...]})`
  - `_meta_response_data` now emits `media` items carrying `uploaded: bool`
  - new module-level helper `async _ensure_model_media_hash(meta: dict) -> str`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_routes_metadata.py` (reuse the existing `client` fixture in that file):

```python
_UPLOAD_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


def _upload_form(*payloads: bytes):
    """Build a multipart body with one `files` part per payload."""
    from aiohttp import FormData

    form = FormData()
    for i, payload in enumerate(payloads):
        form.add_field("files", payload, filename=f"pic{i}.png", content_type="image/png")
    return form


async def test_upload_media_stores_the_file_and_returns_the_gallery(client):
    from py.db import model_repo

    await model_repo.register_model(filename="a.safetensors", model_type="checkpoints")

    resp = await client.post(
        "/tiny-model-manager/api/models/checkpoints/a.safetensors/media",
        data=_upload_form(_UPLOAD_PNG),
    )

    assert resp.status == 200
    body = await resp.json()
    assert body["success"] is True
    assert len(body["media"]) == 1
    item = body["media"][0]
    assert item["media_type"] == "image"
    assert item["uploaded"] is True
    assert os.path.isfile(item["local_path"])


async def test_upload_media_assigns_a_media_hash_when_the_model_has_none(client):
    from py.db import model_repo

    await model_repo.register_model(filename="a.safetensors", model_type="checkpoints")
    assert await model_repo.get_model_media_hash("a.safetensors") == ""

    await client.post(
        "/tiny-model-manager/api/models/checkpoints/a.safetensors/media",
        data=_upload_form(_UPLOAD_PNG),
    )

    assert await model_repo.get_model_media_hash("a.safetensors") != ""


async def test_upload_media_accepts_several_files_at_once(client):
    from py.db import model_repo

    await model_repo.register_model(filename="a.safetensors", model_type="checkpoints")

    resp = await client.post(
        "/tiny-model-manager/api/models/checkpoints/a.safetensors/media",
        data=_upload_form(_UPLOAD_PNG, _UPLOAD_PNG, _UPLOAD_PNG),
    )

    body = await resp.json()
    assert len(body["media"]) == 3
    assert len({m["local_path"] for m in body["media"]}) == 3


async def test_upload_media_rejects_a_non_image(client):
    from py.db import model_repo

    await model_repo.register_model(filename="a.safetensors", model_type="checkpoints")

    resp = await client.post(
        "/tiny-model-manager/api/models/checkpoints/a.safetensors/media",
        data=_upload_form(b"<html>definitely not an image</html>"),
    )

    assert resp.status == 400
    assert (await resp.json())["success"] is False


async def test_upload_media_404s_for_an_unknown_model(client):
    resp = await client.post(
        "/tiny-model-manager/api/models/checkpoints/ghost.safetensors/media",
        data=_upload_form(_UPLOAD_PNG),
    )

    assert resp.status == 404


async def test_upload_media_rejects_more_than_max_files(client):
    from py.db import model_repo
    from py.services import media_upload

    await model_repo.register_model(filename="a.safetensors", model_type="checkpoints")

    resp = await client.post(
        "/tiny-model-manager/api/models/checkpoints/a.safetensors/media",
        data=_upload_form(*([_UPLOAD_PNG] * (media_upload.MAX_FILES + 1))),
    )

    assert resp.status == 400


async def test_delete_media_removes_the_upload_and_its_row(client):
    from py.db import model_repo

    await model_repo.register_model(filename="a.safetensors", model_type="checkpoints")
    upload = await client.post(
        "/tiny-model-manager/api/models/checkpoints/a.safetensors/media",
        data=_upload_form(_UPLOAD_PNG),
    )
    item = (await upload.json())["media"][0]

    resp = await client.delete(
        f"/tiny-model-manager/api/models/checkpoints/a.safetensors/media/{item['id']}"
    )

    assert resp.status == 200
    assert (await resp.json())["media"] == []
    assert not os.path.exists(item["local_path"])


async def test_delete_media_refuses_a_fetched_image(client):
    from py.db import model_repo

    model_id = await model_repo.register_model(filename="a.safetensors", model_type="checkpoints")
    media_id = await model_repo.add_media(model_id, "image", "/media/deadbeef/0.jpg")

    resp = await client.delete(
        f"/tiny-model-manager/api/models/checkpoints/a.safetensors/media/{media_id}"
    )

    assert resp.status == 400
    assert len(await model_repo.get_model_media(model_id)) == 1


async def test_metadata_marks_fetched_media_as_not_uploaded(client):
    from py.db import model_repo

    model_id = await model_repo.register_model(filename="a.safetensors", model_type="checkpoints")
    await model_repo.add_media(model_id, "image", "/media/deadbeef/0.jpg")

    resp = await client.get("/tiny-model-manager/api/models/checkpoints/a.safetensors/metadata")

    media = (await resp.json())["data"]["media"]
    assert media[0]["uploaded"] is False
```

Check the top of `tests/test_routes_metadata.py`: if `import os` is absent, add it.

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONSAFEPATH=1 ../../../comfy-env/bin/python -m pytest tests/test_routes_metadata.py -v -k "upload or delete_media or not_uploaded"`
Expected: FAIL — 404s from aiohttp for the unregistered routes, and `KeyError: 'uploaded'`

- [ ] **Step 3: Write the implementation**

In `py/routes/metadata.py`, add to the imports near the other service imports:

```python
from ..services import media_upload
```

Replace the `"media"` line in `_meta_response_data` (currently line 101) so the payload carries the flag:

```python
        "media": [
            {**item, "uploaded": media_upload.is_uploaded(item.get("local_path", ""))}
            for item in meta.get("media", [])
        ],
```

Add these handlers above `add_metadata_routes`:

```python
async def _ensure_model_media_hash(meta: dict) -> str:
    """Return the model's media_hash, assigning one first when the column is empty.

    Disk-registered models start with ``''``. ``_compute_media_hash`` is deterministic,
    so re-deriving it later yields the same directory.
    """
    from ..db.database import get_db
    from ..services.metadata_fetcher import _compute_media_hash

    existing = meta.get("media_hash") or ""
    if existing:
        return existing
    media_hash = _compute_media_hash(
        meta.get("source_platform") or "",
        meta.get("source_id") or "",
        meta["filename"],
    )
    async with get_db() as db:
        await db.execute(
            "UPDATE models SET media_hash = ? WHERE id = ?", (media_hash, meta["id"])
        )
        await db.commit()
    return media_hash


async def _model_gallery(model_id: int) -> list[dict]:
    """The model's media rows in the same shape the metadata route returns."""
    rows = await model_repo.get_model_media(model_id)
    return [{**r, "uploaded": media_upload.is_uploaded(r["local_path"])} for r in rows]


async def _upload_model_media(request):
    meta = await model_repo.get_model_by_filename(request.match_info["path"])
    if not meta:
        return err("Model not found", status=404)
    media_hash = await _ensure_model_media_hash(meta)

    stored = 0
    reader = await request.multipart()
    async for part in reader:
        if part.name != "files":
            continue
        if stored >= media_upload.MAX_FILES:
            return err(f"At most {media_upload.MAX_FILES} files per upload", status=400)
        try:
            dest = await media_upload.store_upload(media_hash, part)
        except media_upload.UploadTooLarge:
            return err("Image too large", status=413)
        except media_upload.UnsupportedImage:
            return err("Unsupported image type", status=400)
        await model_repo.add_media(meta["id"], "image", dest)
        stored += 1

    if not stored:
        return err("No image supplied", status=400)
    return ok(media=await _model_gallery(meta["id"]))


async def _delete_model_media(request):
    meta = await model_repo.get_model_by_filename(request.match_info["path"])
    if not meta:
        return err("Model not found", status=404)
    try:
        media_id = int(request.match_info["media_id"])
    except ValueError:
        return err("Invalid media id", status=400)

    row = next((m for m in meta.get("media", []) if m["id"] == media_id), None)
    if row is None:
        return err("Media not found", status=404)
    if not media_upload.is_uploaded(row["local_path"]):
        return err("Only uploaded images can be removed", status=400)

    media_upload.delete_upload(
        meta.get("media_hash") or "", os.path.basename(row["local_path"])
    )
    await model_repo.delete_media_row(media_id)
    return ok(media=await _model_gallery(meta["id"]))
```

Register both in `add_metadata_routes`, after the `link-source` line:

```python
    routes.post(f"{base}/media")(json_route(_upload_model_media))
    routes.delete(f"{base}/media/{{media_id}}")(json_route(_delete_model_media))
```

> Route-order note: `base` ends in `{path:.*}`, which is greedy, but aiohttp resolves the
> longer literal suffix first exactly as it already does for `/metadata` and `/repo-files`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTHONSAFEPATH=1 ../../../comfy-env/bin/python -m pytest tests/test_routes_metadata.py -v`
Expected: PASS (new cases and every pre-existing one)

- [ ] **Step 5: Lint and commit**

```bash
PYTHONSAFEPATH=1 ../../../comfy-env/bin/python -m ruff check py tests conftest.py
PYTHONSAFEPATH=1 ../../../comfy-env/bin/python -m ruff format --check py tests conftest.py
git add py/routes/metadata.py tests/test_routes_metadata.py
git commit -m "feat(models): upload and remove model card images (#159)"
```

---

### Task 3: Catalog-side upload and delete routes

**Files:**
- Modify: `py/routes/catalog.py` (extend `_list_catalog_media` at lines 17-39, add handlers, register routes in `add_catalog_routes` at lines 215-263)
- Modify: `py/db/model_repo.py` (new `set_catalog_media_fields`)
- Test: `tests/test_routes_catalog.py`, `tests/test_model_repo.py`

**Interfaces:**
- Consumes: `media_upload.*` from Task 1; `metadata_fetcher.catalog_media_hash`; existing `model_repo.get_catalog_entry`.
- Produces:
  - `POST /tiny-model-manager/api/catalog/{platform}/{page_id:.*}/media` → `ok({"media": [...]})`
  - `DELETE /tiny-model-manager/api/catalog/{platform}/{page_id:.*}/media/{name}` → `ok({"media": [...]})`
  - `_list_catalog_media` items now carry `uploaded: bool`
  - `async model_repo.set_catalog_media_fields(platform: str, page_id: str, media_hash: str | None = None, thumbnail_url: str | None = None) -> bool`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_model_repo.py`:

```python
async def test_set_catalog_media_fields_updates_only_what_is_given(ext_dir):
    from py.db import model_repo

    await model_repo.upsert_catalog_entry(
        source_platform="civitai",
        source_page_id="77",
        source_page_url="https://civitai.com/models/77",
        display_name="Seventy Seven",
        thumbnail_url="",
        base_model="SDXL",
    )

    assert await model_repo.set_catalog_media_fields("civitai", "77", media_hash="abc") is True
    entry = await model_repo.get_catalog_entry("civitai", "77")
    assert entry["media_hash"] == "abc"
    assert entry["thumbnail_url"] == ""

    await model_repo.set_catalog_media_fields("civitai", "77", thumbnail_url="/media/abc/x.png")
    entry = await model_repo.get_catalog_entry("civitai", "77")
    assert entry["media_hash"] == "abc"
    assert entry["thumbnail_url"] == "/media/abc/x.png"


async def test_set_catalog_media_fields_reports_a_missing_entry(ext_dir):
    from py.db import model_repo

    assert await model_repo.set_catalog_media_fields("civitai", "nope", media_hash="abc") is False
```

Append to `tests/test_routes_catalog.py`:

```python
_UPLOAD_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


def _upload_form(*payloads: bytes):
    from aiohttp import FormData

    form = FormData()
    for i, payload in enumerate(payloads):
        form.add_field("files", payload, filename=f"pic{i}.png", content_type="image/png")
    return form


async def test_upload_catalog_media_appears_in_the_next_detail_read(client):
    await _make_entry()

    resp = await client.post(
        "/tiny-model-manager/api/catalog/civitai/123/media", data=_upload_form(_UPLOAD_PNG)
    )

    assert resp.status == 200
    media = (await resp.json())["media"]
    assert len(media) == 1
    assert media[0]["uploaded"] is True
    assert os.path.isfile(media[0]["local_path"])

    detail = await client.get("/tiny-model-manager/api/catalog/civitai/123")
    assert len((await detail.json())["data"]["media"]) == 1


async def test_upload_catalog_media_fills_an_empty_thumbnail(client):
    from py.db import model_repo

    await _make_entry()

    resp = await client.post(
        "/tiny-model-manager/api/catalog/civitai/123/media", data=_upload_form(_UPLOAD_PNG)
    )
    stored = (await resp.json())["media"][0]["local_path"]

    entry = await model_repo.get_catalog_entry("civitai", "123")
    assert entry["thumbnail_url"] == stored
    assert entry["media_hash"] != ""


async def test_upload_catalog_media_keeps_an_existing_thumbnail(client):
    from py.db import model_repo

    await _make_entry()
    await model_repo.set_catalog_media_fields("civitai", "123", thumbnail_url="/media/x/0.jpg")

    await client.post(
        "/tiny-model-manager/api/catalog/civitai/123/media", data=_upload_form(_UPLOAD_PNG)
    )

    entry = await model_repo.get_catalog_entry("civitai", "123")
    assert entry["thumbnail_url"] == "/media/x/0.jpg"


async def test_upload_catalog_media_404s_for_an_unknown_entry(client):
    resp = await client.post(
        "/tiny-model-manager/api/catalog/civitai/999/media", data=_upload_form(_UPLOAD_PNG)
    )

    assert resp.status == 404


async def test_upload_catalog_media_rejects_a_non_image(client):
    await _make_entry()

    resp = await client.post(
        "/tiny-model-manager/api/catalog/civitai/123/media",
        data=_upload_form(b"<html>not an image</html>"),
    )

    assert resp.status == 400


async def test_delete_catalog_media_removes_the_file_and_clears_the_thumbnail(client):
    from py.db import model_repo

    await _make_entry()
    upload = await client.post(
        "/tiny-model-manager/api/catalog/civitai/123/media", data=_upload_form(_UPLOAD_PNG)
    )
    stored = (await upload.json())["media"][0]["local_path"]

    resp = await client.delete(
        f"/tiny-model-manager/api/catalog/civitai/123/media/{os.path.basename(stored)}"
    )

    assert resp.status == 200
    assert (await resp.json())["media"] == []
    assert not os.path.exists(stored)
    entry = await model_repo.get_catalog_entry("civitai", "123")
    assert entry["thumbnail_url"] == ""


async def test_delete_catalog_media_refuses_a_name_that_is_not_an_upload(client):
    await _make_entry()

    resp = await client.delete("/tiny-model-manager/api/catalog/civitai/123/media/0.jpg")

    assert resp.status == 400
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONSAFEPATH=1 ../../../comfy-env/bin/python -m pytest tests/test_routes_catalog.py tests/test_model_repo.py -v -k "catalog_media or upload"`
Expected: FAIL — `AttributeError: module 'py.db.model_repo' has no attribute 'set_catalog_media_fields'` and 404s for the unregistered routes

- [ ] **Step 3: Write the implementation**

In `py/db/model_repo.py`, add next to the other catalog helpers (after `get_catalog_entry`):

```python
async def set_catalog_media_fields(
    source_platform: str,
    source_page_id: str,
    media_hash: str | None = None,
    thumbnail_url: str | None = None,
) -> bool:
    """Update a catalog entry's media_hash and/or thumbnail_url. None leaves a field alone."""
    assignments = []
    params: list[str] = []
    if media_hash is not None:
        assignments.append("media_hash = ?")
        params.append(media_hash)
    if thumbnail_url is not None:
        assignments.append("thumbnail_url = ?")
        params.append(thumbnail_url)
    if not assignments:
        return False
    params.extend([source_platform, source_page_id])
    async with get_db() as db:
        cursor = await db.execute(
            f"UPDATE catalog_entries SET {', '.join(assignments)}"
            " WHERE source_platform = ? AND source_page_id = ?",
            params,
        )
        await db.commit()
        return cursor.rowcount > 0
```

In `py/routes/catalog.py`, add to the imports:

```python
from ..services import media_upload
```

In `_list_catalog_media`, replace the `items.append(...)` line so each item carries the flag:

```python
        items.append(
            {
                "id": i,
                "media_type": media_type,
                "local_path": full,
                "uploaded": media_upload.is_uploaded(full),
            }
        )
```

Add these handlers above `add_catalog_routes`:

```python
async def _ensure_catalog_media_hash(platform: str, page_id: str, entry: dict) -> str:
    """Return the entry's media_hash, assigning the deterministic one when it is empty."""
    from ..services.metadata_fetcher import catalog_media_hash

    existing = entry.get("media_hash") or ""
    if existing:
        return existing
    media_hash = catalog_media_hash(platform, page_id)
    await model_repo.set_catalog_media_fields(platform, page_id, media_hash=media_hash)
    return media_hash


async def _handle_upload_catalog_media(request, platform: str, page_id: str) -> web.Response:
    entry = await model_repo.get_catalog_entry(platform, page_id)
    if not entry:
        return err(_CATALOG_NOT_FOUND, status=404)
    media_hash = await _ensure_catalog_media_hash(platform, page_id, entry)

    stored: list[str] = []
    reader = await request.multipart()
    async for part in reader:
        if part.name != "files":
            continue
        if len(stored) >= media_upload.MAX_FILES:
            return err(f"At most {media_upload.MAX_FILES} files per upload", status=400)
        try:
            stored.append(await media_upload.store_upload(media_hash, part))
        except media_upload.UploadTooLarge:
            return err("Image too large", status=413)
        except media_upload.UnsupportedImage:
            return err("Unsupported image type", status=400)

    if not stored:
        return err("No image supplied", status=400)
    # _fill_thumbnail only joins through model_media, so a catalog entry with no installed
    # model would keep a blank card without this.
    if not entry.get("thumbnail_url"):
        await model_repo.set_catalog_media_fields(platform, page_id, thumbnail_url=stored[0])
    return ok(media=_list_catalog_media(media_hash))


async def _handle_delete_catalog_media(platform: str, page_id: str, name: str) -> web.Response:
    entry = await model_repo.get_catalog_entry(platform, page_id)
    if not entry:
        return err(_CATALOG_NOT_FOUND, status=404)
    media_hash = entry.get("media_hash") or ""
    if not media_upload.delete_upload(media_hash, name):
        return err("Only uploaded images can be removed", status=400)
    if os.path.basename(entry.get("thumbnail_url") or "") == name:
        await model_repo.set_catalog_media_fields(platform, page_id, thumbnail_url="")
    return ok(media=_list_catalog_media(media_hash))
```

Register both inside `add_catalog_routes`, before the `delete_catalog_entry` route (a longer literal suffix must be declared before the bare `{page_id:.*}` delete):

```python
    @routes.post("/tiny-model-manager/api/catalog/{platform}/{page_id:.*}/media")
    @json_route
    async def upload_catalog_media(request):
        return await _handle_upload_catalog_media(
            request, request.match_info["platform"], request.match_info["page_id"]
        )

    @routes.delete("/tiny-model-manager/api/catalog/{platform}/{page_id:.*}/media/{name}")
    @json_route
    async def delete_catalog_media(request):
        return await _handle_delete_catalog_media(
            request.match_info["platform"],
            request.match_info["page_id"],
            request.match_info["name"],
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTHONSAFEPATH=1 ../../../comfy-env/bin/python -m pytest tests/test_routes_catalog.py tests/test_model_repo.py -v`
Expected: PASS

If `test_delete_catalog_media_*` returns 404 instead of 200/400, the greedy `{page_id:.*}` swallowed `/media/<name>`. Move the two new registrations above every other `{page_id:.*}` route in `add_catalog_routes` and re-run.

- [ ] **Step 5: Run the whole backend suite, lint, commit**

```bash
PYTHONSAFEPATH=1 ../../../comfy-env/bin/python -m pytest
PYTHONSAFEPATH=1 ../../../comfy-env/bin/python -m ruff check py tests conftest.py
PYTHONSAFEPATH=1 ../../../comfy-env/bin/python -m ruff format --check py tests conftest.py
git add py/routes/catalog.py py/db/model_repo.py tests/test_routes_catalog.py tests/test_model_repo.py
git commit -m "feat(catalog): upload and remove catalog card images (#159)"
```

---

### Task 4: `ModelService` methods and the `uploaded` field

**Files:**
- Modify: `frontend/src/app/services/model.ts` (`MediaItem` at lines 28-32; new methods next to the other catalog methods)
- Test: `frontend/src/app/services/model.spec.ts`

**Interfaces:**
- Consumes: the four routes from Tasks 2 and 3.
- Produces:
  - `MediaItem` gains `uploaded: boolean`
  - `uploadModelMedia(modelType: string, path: string, files: File[]): Observable<MediaItem[]>`
  - `deleteModelMedia(modelType: string, path: string, mediaId: number): Observable<MediaItem[]>`
  - `uploadCatalogMedia(platform: string, pageId: string, files: File[]): Observable<MediaItem[]>`
  - `deleteCatalogMedia(platform: string, pageId: string, name: string): Observable<MediaItem[]>`

- [ ] **Step 1: Write the failing tests**

Append inside the existing top-level `describe` in `frontend/src/app/services/model.spec.ts`:

```typescript
  it('uploadModelMedia posts a FormData with one files part per file', () => {
    const files = [
      new File(['a'], 'a.png', { type: 'image/png' }),
      new File(['b'], 'b.png', { type: 'image/png' }),
    ];
    let result: MediaItem[] | undefined;
    service.uploadModelMedia('checkpoints', 'a.safetensors', files).subscribe((m) => {
      result = m;
    });

    const req = http.expectOne('/tiny-model-manager/api/models/checkpoints/a.safetensors/media');
    expect(req.request.method).toBe('POST');
    expect(req.request.body instanceof FormData).toBe(true);
    expect((req.request.body as FormData).getAll('files').length).toBe(2);

    req.flush({ success: true, media: [{ id: 1, media_type: 'image', local_path: '/m/u.png', uploaded: true }] });
    expect(result?.length).toBe(1);
    expect(result?.[0].uploaded).toBe(true);
  });

  it('deleteModelMedia deletes by media id and returns the refreshed gallery', () => {
    let result: MediaItem[] | undefined;
    service.deleteModelMedia('checkpoints', 'a.safetensors', 7).subscribe((m) => {
      result = m;
    });

    const req = http.expectOne('/tiny-model-manager/api/models/checkpoints/a.safetensors/media/7');
    expect(req.request.method).toBe('DELETE');

    req.flush({ success: true, media: [] });
    expect(result).toEqual([]);
  });

  it('uploadCatalogMedia posts a FormData to the catalog media route', () => {
    const files = [new File(['a'], 'a.png', { type: 'image/png' })];
    service.uploadCatalogMedia('civitai', '123', files).subscribe();

    const req = http.expectOne('/tiny-model-manager/api/catalog/civitai/123/media');
    expect(req.request.method).toBe('POST');
    expect((req.request.body as FormData).getAll('files').length).toBe(1);
    req.flush({ success: true, media: [] });
  });

  it('deleteCatalogMedia deletes by basename', () => {
    service.deleteCatalogMedia('civitai', '123', 'upload-0123456789ab.png').subscribe();

    const req = http.expectOne(
      '/tiny-model-manager/api/catalog/civitai/123/media/upload-0123456789ab.png',
    );
    expect(req.request.method).toBe('DELETE');
    req.flush({ success: true, media: [] });
  });
```

Add `MediaItem` to the `import type` list at the top of that spec if it is not already imported.

- [ ] **Step 2: Run tests to verify they fail**

Run (from `frontend/`): `npx ng test --watch=false -- model.spec`
Expected: FAIL — `service.uploadModelMedia is not a function`

- [ ] **Step 3: Write the implementation**

In `frontend/src/app/services/model.ts`, extend the interface:

```typescript
export interface MediaItem {
  id: number;
  media_type: string;
  local_path: string;
  /** True when the file is a user upload (`upload-<hex>.<ext>`), so it can be removed. */
  uploaded: boolean;
}
```

Add the four methods next to `updateCatalogMetadata`:

```typescript
  private mediaForm(files: File[]): FormData {
    const form = new FormData();
    for (const file of files) form.append('files', file, file.name);
    return form;
  }

  uploadModelMedia(modelType: string, path: string, files: File[]): Observable<MediaItem[]> {
    return this.http
      .post<{
        success: boolean;
        media: MediaItem[];
      }>(`${API}/models/${modelType}/${path}/media`, this.mediaForm(files))
      .pipe(map((r) => r.media));
  }

  deleteModelMedia(modelType: string, path: string, mediaId: number): Observable<MediaItem[]> {
    return this.http
      .delete<{
        success: boolean;
        media: MediaItem[];
      }>(`${API}/models/${modelType}/${path}/media/${mediaId}`)
      .pipe(map((r) => r.media));
  }

  uploadCatalogMedia(platform: string, pageId: string, files: File[]): Observable<MediaItem[]> {
    return this.http
      .post<{
        success: boolean;
        media: MediaItem[];
      }>(`${API}/catalog/${platform}/${pageId}/media`, this.mediaForm(files))
      .pipe(map((r) => r.media));
  }

  deleteCatalogMedia(platform: string, pageId: string, name: string): Observable<MediaItem[]> {
    return this.http
      .delete<{
        success: boolean;
        media: MediaItem[];
      }>(`${API}/catalog/${platform}/${pageId}/media/${name}`)
      .pipe(map((r) => r.media));
  }
```

> Do **not** set a `Content-Type` header: the browser must add the multipart boundary itself.

Fix the compile errors this causes: `uploaded` is now required on `MediaItem`, so every literal in existing specs that builds one needs the field. Run the suite and add `uploaded: false` wherever the compiler points.

- [ ] **Step 4: Run tests to verify they pass**

Run (from `frontend/`): `npx ng test --watch=false`
Expected: PASS across the whole suite

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/services/model.ts frontend/src/app/services/model.spec.ts frontend/src/app
git commit -m "feat(frontend): add media upload and delete calls to ModelService (#159)"
```

---

### Task 5: `MediaUploadZone` component

**Files:**
- Create: `frontend/src/app/components/media-upload-zone/media-upload-zone.ts`
- Create: `frontend/src/app/components/media-upload-zone/media-upload-zone.html`
- Create: `frontend/src/app/components/media-upload-zone/media-upload-zone.scss`
- Create: `frontend/src/app/components/media-upload-zone/media-upload-zone.spec.ts`
- Modify: `frontend/public/i18n/en.json`

**Interfaces:**
- Consumes: nothing from earlier tasks (purely presentational).
- Produces: `MediaUploadZone` with inputs `busy = input(false)`, `error = input('')` and output `filesSelected = output<File[]>()`. Exported constants `ACCEPTED_TYPES: readonly string[]`, `MAX_FILE_BYTES = 10 * 1024 * 1024`, `MAX_FILES = 10`.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/app/components/media-upload-zone/media-upload-zone.spec.ts`:

```typescript
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideTranslateServiceForTests } from '../../../test-helpers/translate-testing';
import { MAX_FILE_BYTES, MAX_FILES, MediaUploadZone } from './media-upload-zone';

const makeFile = (name: string, type: string, size = 10): File => {
  const file = new File([new Uint8Array(size)], name, { type });
  return file;
};

describe('MediaUploadZone', () => {
  let fixture: ComponentFixture<MediaUploadZone>;
  let component: MediaUploadZone;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [MediaUploadZone],
      providers: [provideTranslateServiceForTests()],
    }).compileComponents();

    fixture = TestBed.createComponent(MediaUploadZone);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('emits the accepted files', () => {
    const emitted: File[][] = [];
    component.filesSelected.subscribe((f) => emitted.push(f));

    component.accept([makeFile('a.png', 'image/png'), makeFile('b.jpg', 'image/jpeg')]);

    expect(emitted.length).toBe(1);
    expect(emitted[0].map((f) => f.name)).toEqual(['a.png', 'b.jpg']);
    expect(component.localError()).toBe('');
  });

  it('rejects an unsupported type and emits nothing', () => {
    const emitted: File[][] = [];
    component.filesSelected.subscribe((f) => emitted.push(f));

    component.accept([makeFile('a.pdf', 'application/pdf')]);

    expect(emitted.length).toBe(0);
    expect(component.localError()).toBe('media_gallery.upload_error_type');
  });

  it('rejects a file over the size cap', () => {
    const emitted: File[][] = [];
    component.filesSelected.subscribe((f) => emitted.push(f));

    component.accept([makeFile('big.png', 'image/png', MAX_FILE_BYTES + 1)]);

    expect(emitted.length).toBe(0);
    expect(component.localError()).toBe('media_gallery.upload_error_size');
  });

  it('rejects more than MAX_FILES at once', () => {
    const emitted: File[][] = [];
    component.filesSelected.subscribe((f) => emitted.push(f));

    component.accept(
      Array.from({ length: MAX_FILES + 1 }, (_, i) => makeFile(`f${i}.png`, 'image/png')),
    );

    expect(emitted.length).toBe(0);
    expect(component.localError()).toBe('media_gallery.upload_error_count');
  });

  it('ignores an empty selection', () => {
    const emitted: File[][] = [];
    component.filesSelected.subscribe((f) => emitted.push(f));

    component.accept([]);

    expect(emitted.length).toBe(0);
  });

  it('does not accept files while busy', () => {
    const emitted: File[][] = [];
    fixture.componentRef.setInput('busy', true);
    fixture.detectChanges();
    component.filesSelected.subscribe((f) => emitted.push(f));

    component.accept([makeFile('a.png', 'image/png')]);

    expect(emitted.length).toBe(0);
  });

  it('tracks the drag state', () => {
    const over = new DragEvent('dragover');
    component.onDragOver(over);
    expect(component.dragging()).toBe(true);

    component.onDragLeave();
    expect(component.dragging()).toBe(false);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run (from `frontend/`): `npx ng test --watch=false -- media-upload-zone`
Expected: FAIL — cannot resolve `./media-upload-zone`

- [ ] **Step 3: Write the implementation**

Create `frontend/src/app/components/media-upload-zone/media-upload-zone.ts`:

```typescript
import { ChangeDetectionStrategy, Component, input, output, signal } from '@angular/core';
import { TranslatePipe } from '@ngx-translate/core';

/** Mirrors the four signatures the backend sniffs in `py/services/media_upload.py`. */
export const ACCEPTED_TYPES: readonly string[] = [
  'image/jpeg',
  'image/png',
  'image/webp',
  'image/gif',
];
export const MAX_FILE_BYTES = 10 * 1024 * 1024;
export const MAX_FILES = 10;

/**
 * Drop target and file picker for user-supplied card images.
 *
 * Presentational only: it validates locally for immediate feedback and emits the files.
 * The server re-validates everything — it sniffs magic bytes rather than trusting the
 * browser's `type` — so this check is a convenience, never the guard.
 */
@Component({
  selector: 'app-media-upload-zone',
  imports: [TranslatePipe],
  templateUrl: './media-upload-zone.html',
  styleUrl: './media-upload-zone.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class MediaUploadZone {
  /** Set while an upload is in flight; blocks further selections. */
  busy = input(false);
  /** Server-side error message from the parent, rendered under the zone. */
  error = input('');

  readonly filesSelected = output<File[]>();

  readonly dragging = signal(false);
  /** Translation key for the last client-side rejection, or '' when there is none. */
  readonly localError = signal('');

  readonly acceptAttr = ACCEPTED_TYPES.join(',');

  accept(files: File[]) {
    if (this.busy()) return;
    if (!files.length) return;
    if (files.length > MAX_FILES) {
      this.localError.set('media_gallery.upload_error_count');
      return;
    }
    if (files.some((f) => !ACCEPTED_TYPES.includes(f.type))) {
      this.localError.set('media_gallery.upload_error_type');
      return;
    }
    if (files.some((f) => f.size > MAX_FILE_BYTES)) {
      this.localError.set('media_gallery.upload_error_size');
      return;
    }
    this.localError.set('');
    this.filesSelected.emit(files);
  }

  onPicked(event: Event) {
    const input = event.target as HTMLInputElement;
    this.accept(Array.from(input.files ?? []));
    // Clear so picking the same file twice in a row still fires a change event.
    input.value = '';
  }

  onDragOver(event: DragEvent) {
    event.preventDefault();
    this.dragging.set(true);
  }

  onDragLeave() {
    this.dragging.set(false);
  }

  onDrop(event: DragEvent) {
    event.preventDefault();
    this.dragging.set(false);
    this.accept(Array.from(event.dataTransfer?.files ?? []));
  }
}
```

Create `frontend/src/app/components/media-upload-zone/media-upload-zone.html`:

```html
<div class="upload-zone" [class.dragging]="dragging()" [class.busy]="busy()">
  <label class="upload-drop" (dragover)="onDragOver($event)" (dragleave)="onDragLeave()" (drop)="onDrop($event)">
    <input
      type="file"
      class="upload-input"
      multiple
      [accept]="acceptAttr"
      [disabled]="busy()"
      (change)="onPicked($event)"
    />
    @if (busy()) {
      <span class="upload-text">{{ 'media_gallery.uploading' | translate }}</span>
    } @else {
      <span class="upload-text">{{ 'media_gallery.upload_hint' | translate }}</span>
      <span class="upload-browse">{{ 'media_gallery.upload_browse' | translate }}</span>
    }
  </label>
  @if (localError()) {
    <p class="upload-error">{{ localError() | translate }}</p>
  } @else if (error()) {
    <p class="upload-error">{{ error() }}</p>
  }
</div>
```

Create `frontend/src/app/components/media-upload-zone/media-upload-zone.scss`:

```scss
.upload-zone {
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
  width: 100%;
}

.upload-drop {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 0.35rem;
  padding: 1.25rem 1rem;
  border: 1px dashed var(--tmm-border, #4a4a4a);
  border-radius: 4px;
  cursor: pointer;
  text-align: center;
  transition: border-color 0.15s ease;
}

.upload-zone.dragging .upload-drop {
  border-color: var(--tmm-accent, #7aa2f7);
}

.upload-zone.busy .upload-drop {
  cursor: progress;
  opacity: 0.6;
}

.upload-input {
  position: absolute;
  width: 1px;
  height: 1px;
  opacity: 0;
  pointer-events: none;
}

.upload-text {
  font-size: 0.75rem;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  opacity: 0.7;
}

.upload-browse {
  font-size: 0.7rem;
  text-decoration: underline;
  opacity: 0.85;
}

.upload-error {
  margin: 0;
  font-size: 0.72rem;
  color: var(--tmm-danger, #f7768e);
}
```

Add to `frontend/public/i18n/en.json` under the existing `media_gallery` object:

```json
    "upload_hint": "DROP AN IMAGE HERE",
    "upload_browse": "or click to browse",
    "uploading": "UPLOADING…",
    "remove_image": "Remove image",
    "upload_error_type": "Only JPEG, PNG, WebP and GIF images are accepted.",
    "upload_error_size": "Images must be 10 MB or smaller.",
    "upload_error_count": "At most 10 images at a time.",
    "upload_failed": "Upload failed."
```

- [ ] **Step 4: Format, then run tests to verify they pass**

```bash
npx prettier --write src/app/components/media-upload-zone/media-upload-zone.ts src/app/components/media-upload-zone/media-upload-zone.html src/app/components/media-upload-zone/media-upload-zone.scss src/app/components/media-upload-zone/media-upload-zone.spec.ts ../frontend/public/i18n/en.json
npx ng test --watch=false -- media-upload-zone
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/components/media-upload-zone frontend/public/i18n/en.json
git commit -m "feat(frontend): add the media upload drop zone component (#159)"
```

---

### Task 6: `MediaGallery` upload and remove affordances

**Files:**
- Modify: `frontend/src/app/components/media-gallery/media-gallery.ts` (lines 13-19 for `GalleryMedia`, 37-63 for the inputs and `items`)
- Modify: `frontend/src/app/components/media-gallery/media-gallery.html`
- Modify: `frontend/src/app/components/media-gallery/media-gallery.scss`
- Test: `frontend/src/app/components/media-gallery/media-gallery.spec.ts`

**Interfaces:**
- Consumes: `MediaUploadZone` from Task 5; `MediaItem.uploaded` from Task 4.
- Produces:
  - `GalleryMedia` gains `uploaded: boolean`, `mediaId: number`, `localPath: string`
  - `MediaGallery` gains `uploadable = input(false)`, `uploadBusy = input(false)`, `uploadError = input('')`, outputs `filesSelected = output<File[]>()` and `removeRequested = output<GalleryMedia>()`, and `readonly showUploadZone = computed<boolean>()`

- [ ] **Step 1: Write the failing tests**

Append to `frontend/src/app/components/media-gallery/media-gallery.spec.ts`. Update the file's existing `makeItem` helper to include `uploaded: false` in its defaults first:

```typescript
  describe('upload affordances', () => {
    it('hides the upload zone when uploadable is false', () => {
      fixture.componentRef.setInput('media', []);
      fixture.detectChanges();

      expect(component.showUploadZone()).toBe(false);
    });

    it('shows the upload zone for an empty gallery when uploadable', () => {
      fixture.componentRef.setInput('media', []);
      fixture.componentRef.setInput('uploadable', true);
      fixture.detectChanges();

      expect(component.showUploadZone()).toBe(true);
    });

    it('shows the upload zone while every item is an upload', () => {
      fixture.componentRef.setInput('media', [
        makeItem({ id: 1, local_path: '/m/h/upload-0123456789ab.png', uploaded: true }),
      ]);
      fixture.componentRef.setInput('uploadable', true);
      fixture.detectChanges();

      expect(component.showUploadZone()).toBe(true);
    });

    it('hides the upload zone once a fetched image is present', () => {
      fixture.componentRef.setInput('media', [
        makeItem({ id: 1, local_path: '/m/h/upload-0123456789ab.png', uploaded: true }),
        makeItem({ id: 2, local_path: '/m/h/0.jpg', uploaded: false }),
      ]);
      fixture.componentRef.setInput('uploadable', true);
      fixture.detectChanges();

      expect(component.showUploadZone()).toBe(false);
    });

    it('never shows the upload zone for remote urls', () => {
      fixture.componentRef.setInput('urls', ['https://example.test/a.jpg']);
      fixture.componentRef.setInput('uploadable', true);
      fixture.detectChanges();

      expect(component.showUploadZone()).toBe(false);
      expect(component.items()[0].uploaded).toBe(false);
    });

    it('carries mediaId and localPath on each local item', () => {
      fixture.componentRef.setInput('media', [
        makeItem({ id: 42, local_path: '/m/h/upload-0123456789ab.png', uploaded: true }),
      ]);
      fixture.detectChanges();

      expect(component.items()[0].mediaId).toBe(42);
      expect(component.items()[0].localPath).toBe('/m/h/upload-0123456789ab.png');
    });

    it('re-emits a remove request for the given item', () => {
      const emitted: unknown[] = [];
      fixture.componentRef.setInput('media', [
        makeItem({ id: 42, local_path: '/m/h/upload-0123456789ab.png', uploaded: true }),
      ]);
      fixture.detectChanges();
      component.removeRequested.subscribe((v) => emitted.push(v));

      component.requestRemove(component.items()[0]);

      expect(emitted.length).toBe(1);
      expect((emitted[0] as { mediaId: number }).mediaId).toBe(42);
    });

    it('re-emits selected files', () => {
      const emitted: File[][] = [];
      component.filesSelected.subscribe((f) => emitted.push(f));

      component.onFilesSelected([new File(['a'], 'a.png', { type: 'image/png' })]);

      expect(emitted.length).toBe(1);
    });
  });
```

- [ ] **Step 2: Run tests to verify they fail**

Run (from `frontend/`): `npx ng test --watch=false -- media-gallery`
Expected: FAIL — `component.showUploadZone is not a function`

- [ ] **Step 3: Write the implementation**

In `media-gallery.ts`, extend `GalleryMedia`:

```typescript
/** A gallery entry, normalised from either a local MediaItem or a remote URL. */
export interface GalleryMedia {
  src: string;
  isVideo: boolean;
  /** Poster image for videos; null when none can be derived (remote URLs). */
  poster: string | null;
  /** True for user uploads, which are the only removable items. */
  uploaded: boolean;
  /** `model_media` row id; 0 for remote URLs and for catalog items, which delete by name. */
  mediaId: number;
  /** Stored path; the parent takes its basename when deleting catalog media. */
  localPath: string;
}
```

Add the import and the new members:

```typescript
import { MediaUploadZone } from '../media-upload-zone/media-upload-zone';
```

Add `MediaUploadZone` to the component's `imports` array, and add `changeDetection: ChangeDetectionStrategy.OnPush` if the decorator lacks it (import `ChangeDetectionStrategy` from `@angular/core`).

Extend the `items` computed so both branches fill the new fields:

```typescript
  readonly items = computed<GalleryMedia[]>(() => {
    const local = this.media();
    if (local.length) {
      return local.map((m) => ({
        src: mediaUrl(m.local_path),
        isVideo: m.media_type === 'video',
        poster: m.media_type === 'video' ? buildVideoPosterUrl(m.local_path) : null,
        uploaded: m.uploaded === true,
        mediaId: m.id,
        localPath: m.local_path,
      }));
    }
    return this.urls().map((url) => ({
      src: url,
      isVideo: isVideo(url),
      // Remote videos have no poster route — the ▶ fallback stands alone.
      poster: null,
      // Remote previews are not ours to remove or replace.
      uploaded: false,
      mediaId: 0,
      localPath: '',
    }));
  });
```

Add after `lightboxOpen`:

```typescript
  /** Set by the page when this gallery may accept uploads. */
  uploadable = input(false);
  /** Forwarded to the zone while the page's upload request is in flight. */
  uploadBusy = input(false);
  /** Server-side error message from the page. */
  uploadError = input('');

  readonly filesSelected = output<File[]>();
  readonly removeRequested = output<GalleryMedia>();

  /**
   * The zone appears while nothing but the user's own uploads is on show — an empty
   * gallery counts, which is the "model has no images" case from the issue. A single
   * fetched preview hides it again.
   */
  readonly showUploadZone = computed(
    () => this.uploadable() && this.items().every((i) => i.uploaded),
  );

  onFilesSelected(files: File[]) {
    this.filesSelected.emit(files);
  }

  requestRemove(item: GalleryMedia) {
    this.removeRequested.emit(item);
  }
```

Import `output` from `@angular/core` alongside the existing imports.

In `media-gallery.html`, replace the empty-state `@else` block and add the zone plus the remove buttons:

```html
} @else {
  <div class="gallery">
    @if (!showUploadZone()) {
      <div class="gallery-main gallery-placeholder">
        {{ 'media_gallery.no_preview' | translate }}
      </div>
    }
  </div>
}

@if (showUploadZone()) {
  <app-media-upload-zone
    [busy]="uploadBusy()"
    [error]="uploadError()"
    (filesSelected)="onFilesSelected($event)"
  />
}
```

Place the `@if (showUploadZone())` block after the whole `@if (items().length > 0) { … } @else { … }` structure and before the lightbox block, so it renders in both the empty and the all-uploads case.

Inside the thumbnail `@for` loop, add the remove control as a sibling of the thumb button (a `<button>` must not nest inside another `<button>`), wrapping each entry:

```html
        @for (thumb of items(); track thumb.src; let i = $index) {
          <div class="gallery-thumb-wrap">
            <button
              type="button"
              class="gallery-thumb"
              [class.active]="i === galleryIdx()"
              (click)="galleryIdx.set(i)"
            >
              <!-- existing thumb content, unchanged -->
            </button>
            @if (thumb.uploaded) {
              <button
                type="button"
                class="gallery-thumb-remove"
                [attr.aria-label]="'media_gallery.remove_image' | translate"
                (click)="requestRemove(thumb)"
              >
                ✕
              </button>
            }
          </div>
        }
```

Add to `media-gallery.scss`:

```scss
.gallery-thumb-wrap {
  position: relative;
  display: inline-flex;
}

.gallery-thumb-remove {
  position: absolute;
  top: 2px;
  right: 2px;
  width: 16px;
  height: 16px;
  padding: 0;
  line-height: 1;
  font-size: 0.6rem;
  border: none;
  border-radius: 2px;
  background: rgb(0 0 0 / 65%);
  color: #fff;
  cursor: pointer;
}

.gallery-thumb-remove:hover {
  background: var(--tmm-danger, #f7768e);
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run (from `frontend/`): `npx ng test --watch=false -- media-gallery`
Expected: PASS

- [ ] **Step 5: Format and commit**

```bash
npx prettier --write src/app/components/media-gallery/media-gallery.ts src/app/components/media-gallery/media-gallery.html src/app/components/media-gallery/media-gallery.scss src/app/components/media-gallery/media-gallery.spec.ts
npx ng test --watch=false
git add frontend/src/app/components/media-gallery
git commit -m "feat(frontend): let MediaGallery accept and remove uploaded images (#159)"
```

---

### Task 7: Wire Model Detail

**Files:**
- Modify: `frontend/src/app/pages/model-detail/model-detail.ts`
- Modify: `frontend/src/app/pages/model-detail/model-detail.html` (line 119)
- Test: `frontend/src/app/pages/model-detail/model-detail.spec.ts`

**Interfaces:**
- Consumes: `ModelService.{uploadModelMedia, deleteModelMedia}` (Task 4); `MediaGallery` inputs/outputs (Task 6).
- Produces: `ModelDetail` gains `uploadBusy`, `uploadError`, `canUpload`, `uploadImages(files: File[])`, `removeImage(item: GalleryMedia)`.

- [ ] **Step 1: Write the failing tests**

Append to `frontend/src/app/pages/model-detail/model-detail.spec.ts` inside the existing top-level describe. Add `uploadModelMedia: vi.fn()` and `deleteModelMedia: vi.fn()` to the file's existing `mockModelService` object first.

```typescript
  describe('image upload', () => {
    const media = (over: Partial<MediaItem> = {}): MediaItem => ({
      id: 1,
      media_type: 'image',
      local_path: '/m/h/0.jpg',
      uploaded: false,
      ...over,
    });

    it('canUpload is true when the model has no media', () => {
      component.meta.set({ ...baseMeta, media: [] });
      expect(component.canUpload()).toBe(true);
    });

    it('canUpload stays true while every image is an upload', () => {
      component.meta.set({
        ...baseMeta,
        media: [media({ local_path: '/m/h/upload-0123456789ab.png', uploaded: true })],
      });
      expect(component.canUpload()).toBe(true);
    });

    it('canUpload is false once a fetched image exists', () => {
      component.meta.set({ ...baseMeta, media: [media()] });
      expect(component.canUpload()).toBe(false);
    });

    it('uploadImages replaces the media from the response', () => {
      const stored = media({ id: 9, local_path: '/m/h/upload-0123456789ab.png', uploaded: true });
      mockModelService.uploadModelMedia.mockReturnValue(of([stored]));
      component.meta.set({ ...baseMeta, media: [] });

      component.uploadImages([new File(['a'], 'a.png', { type: 'image/png' })]);

      expect(mockModelService.uploadModelMedia).toHaveBeenCalled();
      expect(component.meta()!.media).toEqual([stored]);
      expect(component.uploadBusy()).toBe(false);
      expect(component.uploadError()).toBe('');
    });

    it('uploadImages surfaces a failure and clears busy', () => {
      mockModelService.uploadModelMedia.mockReturnValue(throwError(() => new Error('boom')));
      component.meta.set({ ...baseMeta, media: [] });

      component.uploadImages([new File(['a'], 'a.png', { type: 'image/png' })]);

      expect(component.uploadError()).toBe('media_gallery.upload_failed');
      expect(component.uploadBusy()).toBe(false);
    });

    it('removeImage deletes by media id and replaces the media', () => {
      mockModelService.deleteModelMedia.mockReturnValue(of([]));
      component.meta.set({
        ...baseMeta,
        media: [media({ id: 9, local_path: '/m/h/upload-0123456789ab.png', uploaded: true })],
      });

      component.removeImage({
        src: '',
        isVideo: false,
        poster: null,
        uploaded: true,
        mediaId: 9,
        localPath: '/m/h/upload-0123456789ab.png',
      });

      expect(mockModelService.deleteModelMedia).toHaveBeenCalledWith(
        component.modelType,
        component.modelPath,
        9,
      );
      expect(component.meta()!.media).toEqual([]);
    });
  });
```

`baseMeta` here is whatever complete `ModelMeta` literal the spec file already uses; reuse the existing one rather than inventing a new shape. Add `MediaItem` and `GalleryMedia` to the file's type imports, and `throwError` to the `rxjs` import if absent.

- [ ] **Step 2: Run tests to verify they fail**

Run (from `frontend/`): `npx ng test --watch=false -- model-detail`
Expected: FAIL — `component.canUpload is not a function`

- [ ] **Step 3: Write the implementation**

In `model-detail.ts`, add the import:

```typescript
import { GalleryMedia } from '../../components/media-gallery/media-gallery';
```

Add next to the other signals:

```typescript
  readonly uploadBusy = signal(false);
  readonly uploadError = signal('');

  /**
   * Uploading is offered while nothing but the user's own images is on show — an empty
   * gallery included. A fetched preview means the model already has artwork.
   */
  readonly canUpload = computed(() => (this.meta()?.media ?? []).every((m) => m.uploaded));
```

Add the two handlers:

```typescript
  uploadImages(files: File[]) {
    if (!files.length) return;
    this.uploadBusy.set(true);
    this.uploadError.set('');
    this.modelService
      .uploadModelMedia(this.modelType, this.modelPath, files)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (media) => {
          const current = this.meta();
          if (current) this.meta.set({ ...current, media });
          this.uploadBusy.set(false);
        },
        error: () => {
          this.uploadError.set(this.translate.instant('media_gallery.upload_failed'));
          this.uploadBusy.set(false);
        },
      });
  }

  removeImage(item: GalleryMedia) {
    this.modelService
      .deleteModelMedia(this.modelType, this.modelPath, item.mediaId)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (media) => {
          const current = this.meta();
          if (current) this.meta.set({ ...current, media });
        },
        error: () => {
          this.uploadError.set(this.translate.instant('media_gallery.upload_failed'));
        },
      });
  }
```

Make sure `computed` and `signal` are in the `@angular/core` import list.

> **Correction (found during Task 7).** An earlier draft of this plan claimed
> `provideTranslateServiceForTests` returns keys verbatim. It does not: it loads the real
> `frontend/public/i18n/en.json` through a `StaticTranslateLoader`, so `translate.instant()`
> resolves properly. The specs therefore assert the **translated** string — for
> `media_gallery.upload_failed` that is `'Upload failed.'`. Storing the resolved string in the
> signal via `translate.instant(...)` is the house pattern (see `model-detail.ts` where
> `model_detail.notify.saved` is handled the same way). The same correction applies to Task 8.

In `model-detail.html`, replace line 119:

```html
        <app-media-gallery
          [media]="meta()!.media"
          [uploadable]="canUpload()"
          [uploadBusy]="uploadBusy()"
          [uploadError]="uploadError()"
          (filesSelected)="uploadImages($event)"
          (removeRequested)="removeImage($event)"
        />
```

- [ ] **Step 4: Run tests to verify they pass**

Run (from `frontend/`): `npx ng test --watch=false -- model-detail`
Expected: PASS

- [ ] **Step 5: Format and commit**

```bash
npx prettier --write src/app/pages/model-detail/model-detail.ts src/app/pages/model-detail/model-detail.html src/app/pages/model-detail/model-detail.spec.ts
git add frontend/src/app/pages/model-detail
git commit -m "feat(model-detail): upload and remove card images (#159)"
```

---

### Task 8: Wire Catalog Detail

**Files:**
- Modify: `frontend/src/app/pages/catalog-detail/catalog-detail.ts` (`displayMedia` at line 123)
- Modify: `frontend/src/app/pages/catalog-detail/catalog-detail.html` (lines 77-87)
- Test: `frontend/src/app/pages/catalog-detail/catalog-detail.spec.ts`

**Interfaces:**
- Consumes: `ModelService.{uploadCatalogMedia, deleteCatalogMedia}` (Task 4); `MediaGallery` inputs/outputs (Task 6).
- Produces: `CatalogDetail` gains `uploadBusy`, `uploadError`, `canUpload`, `uploadImages(files: File[])`, `removeImage(item: GalleryMedia)`.

- [ ] **Step 1: Write the failing tests**

Append to `frontend/src/app/pages/catalog-detail/catalog-detail.spec.ts`, adding `uploadCatalogMedia: vi.fn()` and `deleteCatalogMedia: vi.fn()` to the file's existing mock service first:

```typescript
  describe('image upload', () => {
    const media = (over: Partial<MediaItem> = {}): MediaItem => ({
      id: 0,
      media_type: 'image',
      local_path: '/m/h/0.jpg',
      uploaded: false,
      ...over,
    });

    it('canUpload is true when the entry has no media', () => {
      component.entry.set({ ...baseEntry, media: [] });
      expect(component.canUpload()).toBe(true);
    });

    it('canUpload is false once a fetched image exists', () => {
      component.entry.set({ ...baseEntry, media: [media()] });
      expect(component.canUpload()).toBe(false);
    });

    it('uploadImages replaces the media from the response', () => {
      const stored = media({ local_path: '/m/h/upload-0123456789ab.png', uploaded: true });
      mockModelService.uploadCatalogMedia.mockReturnValue(of([stored]));
      component.entry.set({ ...baseEntry, media: [] });

      component.uploadImages([new File(['a'], 'a.png', { type: 'image/png' })]);

      expect(component.entry()!.media).toEqual([stored]);
      expect(component.uploadBusy()).toBe(false);
    });

    it('uploadImages surfaces a failure', () => {
      mockModelService.uploadCatalogMedia.mockReturnValue(throwError(() => new Error('boom')));
      component.entry.set({ ...baseEntry, media: [] });

      component.uploadImages([new File(['a'], 'a.png', { type: 'image/png' })]);

      expect(component.uploadError()).toBe('media_gallery.upload_failed');
      expect(component.uploadBusy()).toBe(false);
    });

    it('removeImage deletes by basename, not by the positional id', () => {
      mockModelService.deleteCatalogMedia.mockReturnValue(of([]));
      component.entry.set({
        ...baseEntry,
        media: [media({ local_path: '/m/h/upload-0123456789ab.png', uploaded: true })],
      });

      component.removeImage({
        src: '',
        isVideo: false,
        poster: null,
        uploaded: true,
        mediaId: 0,
        localPath: '/m/h/upload-0123456789ab.png',
      });

      expect(mockModelService.deleteCatalogMedia).toHaveBeenCalledWith(
        component.platform,
        component.pageId,
        'upload-0123456789ab.png',
      );
      expect(component.entry()!.media).toEqual([]);
    });
  });
```

`baseEntry` is the complete `CatalogEntryDetail` literal the spec file already uses; reuse it. Match the property names the component actually exposes for platform and page id — read the component before writing the assertion and adjust if they differ.

- [ ] **Step 2: Run tests to verify they fail**

Run (from `frontend/`): `npx ng test --watch=false -- catalog-detail`
Expected: FAIL — `component.canUpload is not a function`

- [ ] **Step 3: Write the implementation**

In `catalog-detail.ts`, add the import and the members (mirroring Task 7, but deleting by basename):

```typescript
import { GalleryMedia } from '../../components/media-gallery/media-gallery';
```

```typescript
  readonly uploadBusy = signal(false);
  readonly uploadError = signal('');

  readonly canUpload = computed(() => this.displayMedia().every((m) => m.uploaded));

  uploadImages(files: File[]) {
    if (!files.length) return;
    this.uploadBusy.set(true);
    this.uploadError.set('');
    this.modelService
      .uploadCatalogMedia(this.platform, this.pageId, files)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (media) => {
          const current = this.entry();
          if (current) this.entry.set({ ...current, media });
          this.uploadBusy.set(false);
        },
        error: () => {
          this.uploadError.set(this.translate.instant('media_gallery.upload_failed'));
          this.uploadBusy.set(false);
        },
      });
  }

  removeImage(item: GalleryMedia) {
    // Catalog media is a directory listing, so its `id` is the enumeration index and
    // renumbers on every read. The basename is the only stable handle.
    const name = item.localPath.split('/').pop() ?? '';
    this.modelService
      .deleteCatalogMedia(this.platform, this.pageId, name)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (media) => {
          const current = this.entry();
          if (current) this.entry.set({ ...current, media });
        },
        error: () => {
          this.uploadError.set(this.translate.instant('media_gallery.upload_failed'));
        },
      });
  }
```

If the component has no `destroyRef` or `translate` member yet, add `private readonly destroyRef = inject(DestroyRef);` and inject `TranslateService` the way `model-detail.ts` does.

In `catalog-detail.html`, extend the two gallery usages (leave the middle `thumbnail_url` branch alone — an image is visibly present there, so by the rule it gets no zone):

```html
        @if (displayMedia().length > 0) {
          <app-media-gallery
            [media]="displayMedia()"
            [uploadable]="canUpload()"
            [uploadBusy]="uploadBusy()"
            [uploadError]="uploadError()"
            (filesSelected)="uploadImages($event)"
            (removeRequested)="removeImage($event)"
          />
        } @else if (entry()!.thumbnail_url) {
          <div class="catalog-thumb-wrap">
            <img [src]="mediaUrl(entry()!.thumbnail_url)" alt="thumbnail" class="catalog-thumb" />
          </div>
        } @else {
          <app-media-gallery
            [media]="[]"
            [uploadable]="true"
            [uploadBusy]="uploadBusy()"
            [uploadError]="uploadError()"
            (filesSelected)="uploadImages($event)"
            (removeRequested)="removeImage($event)"
          />
        }
```

- [ ] **Step 4: Run tests to verify they pass**

Run (from `frontend/`): `npx ng test --watch=false -- catalog-detail`
Expected: PASS

- [ ] **Step 5: Format and commit**

```bash
npx prettier --write src/app/pages/catalog-detail/catalog-detail.ts src/app/pages/catalog-detail/catalog-detail.html src/app/pages/catalog-detail/catalog-detail.spec.ts
git add frontend/src/app/pages/catalog-detail
git commit -m "feat(catalog-detail): upload and remove card images (#159)"
```

---

### Task 9: Full verification, bundle rebuild, memory update

**Files:**
- Modify: `README.md` (features checklist entry, if one exists for this item)
- Modify: `web/**` (rebuilt bundle — tracked in git on purpose)
- Modify: the relevant Serena memory (`core`, and `conventions` if a new convention was established)

**Interfaces:**
- Consumes: everything from Tasks 1-8.
- Produces: a clean, committed, buildable branch ready for the user to review.

- [ ] **Step 1: Run every backend check**

```bash
PYTHONSAFEPATH=1 ../../../comfy-env/bin/python -m pytest
PYTHONSAFEPATH=1 ../../../comfy-env/bin/python -m ruff check py tests conftest.py
PYTHONSAFEPATH=1 ../../../comfy-env/bin/python -m ruff format --check py tests conftest.py
```
Expected: 0 failures, 0 ruff errors. Fix anything that fails before continuing — do not proceed on a red suite.

- [ ] **Step 2: Run every frontend check**

```bash
cd frontend
npx ng test --watch=false
npx ng lint
npm run format:check
```
Expected: all pass, 0 ESLint errors.

- [ ] **Step 3: Build the bundle from the main checkout**

```bash
cd frontend
npx ng build
```
Expected: build succeeds. ComfyUI serves the **main checkout's** `web/`, so this must run in `comfyui-tiny-model-manager/frontend/`, never inside a worktree.

- [ ] **Step 4: Update the README feature checklist**

Read `README.md` and find the features checklist. If it lists this feature, mark it `[x]`. If it does not, add a line for it in the same style as its neighbours. If the README has no such checklist, skip this step.

- [ ] **Step 5: Update the Serena memory**

Add a section to `mem:core` describing the feature, using `mcp__serena__write_memory`. It must record, at minimum:

- Uploads are marked by the filename `upload-<12 hex>.<ext>`, not a DB column, because catalog media is a directory listing with no rows. `py/services/media_upload.py` owns `UPLOAD_NAME_RE`, and the same regex sanitizes the delete routes.
- `media_upload` keeps its top-level imports to the standard library and pulls in `media_cleanup` / `model_paths` inside functions, because `media_cleanup` imports `model_repo` and the route layer imports `media_upload` — a top-level import would close the cycle.
- The `uploaded` flag is computed in the route layer (`_meta_response_data`, `_list_catalog_media`), never in `model_repo`: the repo's other media serialisations feed the Models-page card grid, which has no upload control, and annotating there would invert the `db → services` layering.
- Catalog media deletes by **basename**, not by the item `id`: `_list_catalog_media` numbers items by enumeration order, which renumbers whenever a file is added or removed.
- Catalog upload fills `catalog_entries.thumbnail_url` when empty, because `_fill_thumbnail` only joins through `model_media` and would otherwise leave the card blank for an entry with no installed model.
- Both `_compute_media_hash` and `catalog_media_hash` are deterministic, which is what lets the routes assign a `media_hash` on first upload for records that have none.

- [ ] **Step 6: Commit the bundle, README and memory together**

```bash
git add web README.md .serena
git status   # confirm nothing under frontend/ or py/ is left unstaged
git commit -m "chore: rebuild bundle and record the card-image upload feature (#159)"
```

- [ ] **Step 7: Present the commits to the user**

```bash
git log --oneline main..HEAD
git diff --stat main..HEAD
```

Report the result and **stop**. Do not push, do not open a PR, do not touch the project board — the user gives explicit approval for each of those.

---

## Self-Review

**Spec coverage:**

| Spec requirement | Task |
| --- | --- |
| `media_upload.py` with sniffing, naming, caps, guarded write/delete | 1 |
| `POST`/`DELETE` model media routes, `media_hash` assignment | 2 |
| `uploaded` flag in `_meta_response_data` | 2 |
| `POST`/`DELETE` catalog media routes, `media_hash` + `thumbnail_url` handling | 3 |
| `uploaded` flag in `_list_catalog_media` | 3 |
| `MediaItem.uploaded` + four `ModelService` methods | 4 |
| `MediaUploadZone` + i18n keys | 5 |
| `MediaGallery` `uploadable`, outputs, `GalleryMedia` fields, ✕ button | 6 |
| Model Detail `canUpload` and handlers | 7 |
| Catalog Detail `canUpload` and handlers, accepted `thumbnail_url` gap | 8 |
| Backend + frontend test coverage listed in the spec | 1-8 |
| `ng build` and the tracked `web/` bundle | 9 |

**Type consistency:** `GalleryMedia.mediaId` / `.localPath` / `.uploaded` are defined in Task 6 and used unchanged in Tasks 7 and 8. `MediaItem.uploaded` is defined in Task 4 and consumed in 6, 7, 8. `MAX_FILES` exists on both sides (`media_upload.MAX_FILES`, `media-upload-zone.MAX_FILES`) with the same value, 10. `set_catalog_media_fields` is defined and used within Task 3 only.
