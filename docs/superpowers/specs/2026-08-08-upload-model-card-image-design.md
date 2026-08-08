# Upload a model card image (issue #159)

Status: approved 2026-08-08
Issue: https://github.com/Zellione/comfyui-tiny-model-manager/issues/159
Milestone: 0.2.0

## Problem

Models without a CivitAI or HuggingFace preview show a blank card on the Models page and an empty
gallery on the detail page. There is no way to give such a model an image. This feature lets the
user upload one.

## Scope

The upload control appears on **Model Detail** and **Catalog Detail**, and only while the gallery
holds no images the user did not upload themselves. Concretely: the control is shown when the
gallery is empty, and it stays shown while every image in it is a user upload. As soon as a fetched
image is present, the control disappears — a model that already has provider artwork does not need
a manual one.

Uploaded images can be removed again. Fetched images cannot: the ✕ appears on uploads only.

Out of scope: reordering the gallery, choosing which image is the card thumbnail, uploading video,
and uploading from the Models page card grid.

## How an upload is marked

Uploaded files are written as `upload-<12 hex>.<ext>` into the model's existing media directory,
`data/media/<media_hash>/`. **The filename is the marker.**

This is deliberate rather than a `model_media.source` column. Catalog media has no database rows at
all — `_list_catalog_media()` in `py/routes/catalog.py` enumerates the directory — so a column could
only ever have covered the model half of the feature. A single naming convention covers both, and
the same regex that recognises an upload doubles as the path sanitizer on the delete routes.

`UPLOAD_NAME_RE = ^upload-[0-9a-f]{12}\.(jpg|png|webp|gif)$`

Two existing invariants make this safe, and both already have tests:

- `model_repo.get_live_media_hashes()` unions `models.media_hash` and `catalog_entries.media_hash`,
  so `cleanup_stale_media()` on startup will not sweep a directory that holds only uploads.
- Fetched media is written as `0.jpg`, `1.jpg`, … by `metadata_fetcher._iter_downloaded_urls`, so a
  later re-fetch can never collide with an `upload-*` name.

## Backend

### New module `py/services/media_upload.py`

Pure and dependency-light, so it is cheap to unit test.

| Symbol | Purpose |
| --- | --- |
| `MAX_UPLOAD_BYTES = 10 * 1024 * 1024` | Per-file cap |
| `MAX_FILES = 10` | Per-request cap |
| `sniff_image_ext(head: bytes) -> str \| None` | Magic-byte detection for JPEG / PNG / WebP / GIF |
| `upload_name(ext: str) -> str` | `upload-<uuid4.hex[:12]>.<ext>` |
| `is_uploaded(path: str) -> bool` | Basename matches `UPLOAD_NAME_RE` |
| `store_upload(media_hash, part) -> str` | Streams one multipart part to disk, returns the absolute path |
| `delete_upload(media_hash, name) -> bool` | Removes one uploaded file |

`sniff_image_ext` reads the leading bytes only. The client-supplied filename and `Content-Type` are
never trusted: the stored extension is derived from the sniff, and a part whose bytes match none of
the four signatures is rejected.

`store_upload` reads the part in chunks into a bounded buffer, aborting the moment the running byte
count passes `MAX_UPLOAD_BYTES` — so an oversized upload never allocates more than the cap and
nothing is written to disk. It only touches the filesystem once the bytes are complete and the type
has been sniffed, so there is no partial file to clean up. The target directory is resolved through
the existing `media_cleanup.media_subdir()` traversal guard — nothing is ever written to a path
built from request data.

`media_cleanup` and `model_paths` are imported **inside** the two functions that need them, not at
module top. `media_cleanup` imports `model_repo`, and `_meta_response_data`'s annotation makes the
route layer import `media_upload`; keeping the module's top-level imports to the standard library
keeps it a leaf and rules out an import cycle.

`delete_upload` rejects any `name` that does not match `UPLOAD_NAME_RE` before touching the
filesystem, then resolves through `model_paths.contained_path`. This mirrors the "nothing is deleted
by absolute path" rule the media-cleanup service already follows.

### Routes

`base` below is the existing `"/tiny-model-manager/api/models/{model_type}/{path:.*}"` in
`py/routes/metadata.py`.

| Method | Path | Behaviour |
| --- | --- | --- |
| `POST` | `{base}/media` | Multipart upload for an installed model |
| `DELETE` | `{base}/media/{media_id}` | Remove one uploaded image |
| `POST` | `/tiny-model-manager/api/catalog/{platform}/{page_id}/media` | Multipart upload for a catalog entry |
| `DELETE` | `/tiny-model-manager/api/catalog/{platform}/{page_id}/media/{name}` | Remove one uploaded image |

All four respond with the refreshed gallery: `ok({"media": [...]})`, in the same item shape the
detail endpoints already return. The page re-renders from that one response instead of refetching.

**`POST {base}/media`** — resolves the model row, ensures it has a `media_hash` (compute with
`metadata_fetcher._compute_media_hash(platform, source_id, filename)`, which is deterministic, and
persist it when the column is empty — disk-registered models start with `''`), then stores each part
and inserts one `model_media` row per stored file with `media_type = "image"`.

**`DELETE {base}/media/{media_id}`** — loads the row, refuses with 400 when its `local_path` is not
an upload, deletes the file and the row.

**`POST /api/catalog/{platform}/{page_id}/media`** — keyed on
`metadata_fetcher.catalog_media_hash(platform, page_id)`, also deterministic; persisted on the entry
when empty. No rows are written — `_list_catalog_media` picks the files up on the next read. When
the entry has no `thumbnail_url`, the first stored upload's path is written to it, so the Models
page card shows the image (`_fill_thumbnail`'s existing fallback only joins through `model_media`
and would otherwise leave the card blank).

**`DELETE /api/catalog/{platform}/{page_id}/media/{name}`** — deletes the file and clears
`thumbnail_url` when it pointed at that file.

Error responses: 400 for an unsupported image type, a bad delete name, or more than `MAX_FILES`
parts; 413 for a part over `MAX_UPLOAD_BYTES`; 404 when the model or catalog entry does not exist.

### Gallery serialisation

Every gallery item gains an `uploaded: bool` field, computed with `media_upload.is_uploaded`, in the
**route** layer:

- `py/routes/catalog.py::_list_catalog_media`
- `py/routes/metadata.py::_meta_response_data` — the single place `model_media` rows reach the
  Model Detail page (shared by the get, refetch and refetch-apply routes)

`py/db/model_repo.py` is deliberately left alone. It serialises media rows in two other places, but
those feed the Models-page card grid, which only picks the first image for a thumbnail and has no
upload control. Annotating there would also force a `db → services` import, inverting the layering.

## Frontend

### New component `components/media-upload-zone/`

Owns the drag-and-drop target, the hidden multi-file `<input type="file">`, and client-side
validation of type, per-file size and count. It emits `File[]`; the server re-validates everything,
so the client copy exists only for immediate feedback. Inputs: `busy` (disables the zone during an
in-flight upload) and `error` (message rendered underneath).

### `MediaGallery` changes

- new input `uploadable = input(false)`
- new outputs `filesSelected = output<File[]>()` and `removeRequested = output<GalleryMedia>()`
- `GalleryMedia` gains `uploaded: boolean`, `mediaId: number` and `localPath: string`, so the parent
  can identify what to delete without the gallery knowing which page it serves: Model Detail deletes
  by `mediaId` (the `model_media` row id), Catalog Detail by the basename of `localPath` (catalog
  items carry a positional `id` that is not stable across reads)
- the zone renders in the empty branch, and also below the thumbnail strip when every item is an
  upload; both gated on `uploadable()`
- a ✕ button on thumbnails whose item is an upload

The gallery stays presentational: it neither calls HTTP nor holds upload state.

### Pages

Both detail pages compute `canUpload = media.every((m) => m.uploaded)` — vacuously true for an empty
gallery, which is exactly the "no images, or only images I uploaded" rule — and pass it as
`uploadable`. Each page owns the in-flight signal, the error signal, and the service calls, and
replaces its media from the response.

`ModelService` gains `uploadModelMedia`, `deleteModelMedia`, `uploadCatalogMedia` and
`deleteCatalogMedia`. Uploads post a `FormData` with repeated `files` parts. The `MediaItem`
interface in `services/model.ts` gains `uploaded: boolean` to match the backend payload.

**Accepted gap:** `catalog-detail.html` has a legacy middle branch that renders a bare
`thumbnail_url` image when `displayMedia()` is empty but a thumbnail path survives. An image is
visibly present in that state, so by the rule above it gets no upload zone. The branch is left as
it is.

### i18n

New keys under `media_gallery.*`, added to every locale file: `upload_hint`, `upload_browse`,
`uploading`, `remove_image`, `upload_error_type`, `upload_error_size`, `upload_error_count`,
`upload_failed`.

## Testing

Backend:

- new `tests/test_media_upload.py` — magic-byte sniffing for each accepted type and for a rejected
  one, `upload_name` / `is_uploaded` round trip, the size cap aborting mid-stream and leaving no
  partial file, `delete_upload` refusing a traversal name
- `tests/test_routes_metadata.py` — upload via `aiohttp` `FormData`; a model with an empty
  `media_hash` gets one assigned; delete removes file and row; delete refuses a fetched image
- `tests/test_routes_catalog.py` — upload writes into the catalog hash directory and appears in the
  next detail read; `thumbnail_url` is filled when empty and cleared on delete; a name outside
  `UPLOAD_NAME_RE` is rejected

Frontend:

- new `media-upload-zone.spec.ts` — emits selected files, rejects oversized and wrong-typed files,
  disables while busy
- `media-gallery.spec.ts` — zone shown when empty, shown when all items are uploads, hidden when any
  fetched image is present; ✕ only on uploads
- `model-detail.spec.ts` / `catalog-detail.spec.ts` — `canUpload` truth table, service called on
  emit, media replaced from the response, error surfaced on failure
- `model.spec.ts` — the four new service methods hit the expected URLs
