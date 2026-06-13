"""Tests for pure functions in py/services/metadata_fetcher.py."""

import hashlib


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


class TestMediaSubdir:
    def test_returns_path_inside_media_dir(self, tmp_path):
        import py.config as cfg

        cfg.init(str(tmp_path))
        from py.services.metadata_fetcher import _media_subdir

        result = _media_subdir("a" * 40)
        assert result.startswith(cfg.media_dir())

    def test_rejects_path_traversal(self, tmp_path):
        import pytest

        import py.config as cfg

        cfg.init(str(tmp_path))
        from py.services.metadata_fetcher import _media_subdir

        with pytest.raises(ValueError):
            _media_subdir("../evil")

    def test_rejects_empty_hash(self, tmp_path):
        import pytest

        import py.config as cfg

        cfg.init(str(tmp_path))
        from py.services.metadata_fetcher import _media_subdir

        with pytest.raises(ValueError):
            _media_subdir("")

    def test_rejects_slash_in_hash(self, tmp_path):
        import pytest

        import py.config as cfg

        cfg.init(str(tmp_path))
        from py.services.metadata_fetcher import _media_subdir

        with pytest.raises(ValueError):
            _media_subdir("abc/def")
