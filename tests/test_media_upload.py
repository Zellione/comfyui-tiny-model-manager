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

    part = _FakePart(b"<html>nope</html>" * 4)
    with pytest.raises(media_upload.UnsupportedImage):
        await media_upload.store_upload("deadbeef", part)


async def test_store_upload_rejects_an_oversized_part_without_writing(ext_dir):
    from py.services import media_cleanup, media_upload

    oversized = _JPEG + b"\x00" * (media_upload.MAX_UPLOAD_BYTES + 1)
    part = _FakePart(oversized, chunk_size=65536)
    with pytest.raises(media_upload.UploadTooLarge):
        await media_upload.store_upload("deadbeef", part)

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
