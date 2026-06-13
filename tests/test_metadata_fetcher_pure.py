"""Tests for pure functions in py/services/metadata_fetcher.py."""

import hashlib
import os


def test_compute_media_hash_deterministic():
    from py.services.metadata_fetcher import _compute_media_hash

    h1 = _compute_media_hash("civitai", "123456", "my_model.safetensors")
    h2 = _compute_media_hash("civitai", "123456", "my_model.safetensors")
    assert h1 == h2


def test_compute_media_hash_uses_platform_source_id():
    from py.services.metadata_fetcher import _compute_media_hash

    expected = hashlib.sha1(b"civitai:123456").hexdigest()
    assert _compute_media_hash("civitai", "123456", "ignored.safetensors") == expected


def test_compute_media_hash_falls_back_to_filename_when_no_platform():
    from py.services.metadata_fetcher import _compute_media_hash

    expected = hashlib.sha1(b"my_model.safetensors").hexdigest()
    assert _compute_media_hash("", "", "my_model.safetensors") == expected


def test_compute_media_hash_falls_back_to_filename_when_no_source_id():
    from py.services.metadata_fetcher import _compute_media_hash

    expected = hashlib.sha1(b"my_model.safetensors").hexdigest()
    assert _compute_media_hash("civitai", "", "my_model.safetensors") == expected


def test_compute_media_hash_unique_per_source():
    from py.services.metadata_fetcher import _compute_media_hash

    h1 = _compute_media_hash("civitai", "111", "f.safetensors")
    h2 = _compute_media_hash("civitai", "222", "f.safetensors")
    assert h1 != h2


def test_compute_media_hash_unique_per_platform():
    from py.services.metadata_fetcher import _compute_media_hash

    h1 = _compute_media_hash("civitai", "123", "f.safetensors")
    h2 = _compute_media_hash("huggingface", "123", "f.safetensors")
    assert h1 != h2


def test_compute_media_hash_is_40_char_hex():
    from py.services.metadata_fetcher import _compute_media_hash

    h = _compute_media_hash("civitai", "123", "f.ckpt")
    assert len(h) == 40
    assert all(c in "0123456789abcdef" for c in h)


# ---------------------------------------------------------------------------
# _media_subdir
# ---------------------------------------------------------------------------


def test_media_subdir_returns_path_inside_media_dir(tmp_path, monkeypatch):
    import py.config as cfg
    from py.services.metadata_fetcher import _media_subdir

    monkeypatch.setattr(cfg, "media_dir", lambda: str(tmp_path))
    result = _media_subdir("a" * 40)
    assert result.startswith(str(tmp_path))


def test_media_subdir_returns_realpath(tmp_path, monkeypatch):
    import py.config as cfg
    from py.services.metadata_fetcher import _media_subdir

    monkeypatch.setattr(cfg, "media_dir", lambda: str(tmp_path))
    result = _media_subdir("abc123")
    assert result == os.path.realpath(result)


def test_media_subdir_rejects_traversal():
    import pytest

    from py.services.metadata_fetcher import _media_subdir

    with pytest.raises(ValueError):
        _media_subdir("../escape")


def test_media_subdir_rejects_empty():
    import pytest

    from py.services.metadata_fetcher import _media_subdir

    with pytest.raises(ValueError):
        _media_subdir("")
