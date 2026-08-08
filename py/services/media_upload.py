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
