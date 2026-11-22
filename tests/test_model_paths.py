"""Unit tests for py/services/model_paths.py resolution and path-traversal guard."""

import os


def _type_dir(model_type: str) -> str:
    """Create and return <data_dir>/models/<model_type> (always a candidate dir)."""
    from py import config as cfg

    path = os.path.join(cfg.data_dir(), "models", model_type)
    os.makedirs(path, exist_ok=True)
    return path


class TestFindFile:
    def test_finds_file_in_data_dir(self, ext_dir):
        from py.services import model_paths

        target = os.path.join(_type_dir("mptype"), "foo.safetensors")
        with open(target, "wb") as f:
            f.write(b"abc")

        assert model_paths.find_file("mptype", "foo.safetensors") == os.path.realpath(target)
        assert model_paths.file_exists("mptype", "foo.safetensors") is True
        assert model_paths.file_size("mptype", "foo.safetensors") == 3

    def test_missing_file_returns_none(self, ext_dir):
        from py.services import model_paths

        _type_dir("mptype")
        assert model_paths.find_file("mptype", "nope.safetensors") is None
        assert model_paths.file_exists("mptype", "nope.safetensors") is False


class TestTraversalGuard:
    def test_rejects_parts_escaping_base(self, ext_dir):
        from py import config as cfg
        from py.services import model_paths

        _type_dir("mptype")
        # A secret file outside the models tree must stay invisible.
        secret = os.path.join(cfg.data_dir(), "secret.txt")
        with open(secret, "wb") as f:
            f.write(b"top secret")

        assert model_paths.find_file("mptype", "../../secret.txt") is None
        assert model_paths.file_exists("mptype", "../../secret.txt") is False

    def test_traversing_model_type_yields_no_unsafe_dirs(self, ext_dir):
        from py.services import model_paths

        # A model_type that is not a clean path segment must not create escaping base dirs.
        assert model_paths.candidate_dirs("../../etc") == []
        assert model_paths.candidate_paths("../../etc", "passwd") == []


def test_compute_file_hash_returns_sha256(tmp_path):
    import hashlib

    from py.services.model_paths import compute_file_hash

    f = tmp_path / "model.safetensors"
    f.write_bytes(b"hello world")
    result = compute_file_hash(f)
    assert result == hashlib.sha256(b"hello world").hexdigest()


def test_compute_file_hash_is_64_char_lowercase_hex(tmp_path):
    from py.services.model_paths import compute_file_hash

    f = tmp_path / "model.safetensors"
    f.write_bytes(b"\x00" * 64)
    result = compute_file_hash(f)
    assert len(result) == 64
    assert result == result.lower()
    assert all(c in "0123456789abcdef" for c in result)


class TestMediaPathStorage:
    """issue #176: media paths are stored relative to the media dir so a moved
    ComfyUI folder keeps them valid."""

    def test_to_stored_media_path_relativises_paths_inside_the_media_dir(self, ext_dir):
        from py import config as cfg
        from py.services.model_paths import to_stored_media_path

        absolute = os.path.join(cfg.media_dir(), "abc123", "0.jpg")
        assert to_stored_media_path(absolute) == "abc123/0.jpg"
        assert to_stored_media_path(os.path.join(cfg.media_dir(), "abc123", "1", "x.jpg")) == (
            "abc123/1/x.jpg"
        )

    def test_to_stored_media_path_passes_through_foreign_and_relative_paths(self, ext_dir):
        from py.services.model_paths import to_stored_media_path

        # A stable external media dir (custom media_dir setting) must keep working.
        external = "/srv/media/abc123/0.jpg"
        assert to_stored_media_path(external) == external
        assert to_stored_media_path("abc123/0.jpg") == "abc123/0.jpg"

    def test_normalize_leaves_relative_values_alone(self, ext_dir):
        from py.services.model_paths import normalize_stored_media_path

        assert normalize_stored_media_path("abc123/0.jpg") is None
        assert normalize_stored_media_path("") is None

    def test_normalize_relativises_absolute_values_under_the_media_dir(self, ext_dir):
        from py import config as cfg
        from py.services.model_paths import normalize_stored_media_path

        absolute = os.path.join(cfg.media_dir(), "abc123", "0.jpg")
        assert normalize_stored_media_path(absolute) == "abc123/0.jpg"

    def test_normalize_repairs_stale_absolute_when_the_tail_is_verifiable(self, ext_dir):
        """The classic moved-folder case: the old absolute path is dead, but the
        <hash>/<name> file exists in the current media dir."""
        from py import config as cfg
        from py.services.model_paths import normalize_stored_media_path

        target = os.path.join(cfg.media_dir(), "abc123", "0.jpg")
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "wb") as f:
            f.write(b"x")

        stale = "/old/root/ComfyUI/custom_nodes/comfyui-tiny-model-manager/data/media/abc123/0.jpg"
        assert normalize_stored_media_path(stale) == "abc123/0.jpg"

    def test_normalize_leaves_unverifiable_stale_values_alone(self, ext_dir):
        from py.services.model_paths import normalize_stored_media_path

        stale = "/old/root/somewhere/abc123/gone.jpg"
        assert normalize_stored_media_path(stale) is None

    def test_normalize_does_not_follow_traversing_tails(self, ext_dir):
        from py import config as cfg
        from py.services.model_paths import normalize_stored_media_path

        secret = os.path.join(cfg.data_dir(), "secret.txt")
        with open(secret, "wb") as f:
            f.write(b"top secret")

        stale = "/old/root/media/../../../secret.txt"
        assert normalize_stored_media_path(stale) is None

    def test_resolve_media_path_resolves_relative_against_the_media_dir(self, ext_dir):
        from py import config as cfg
        from py.services.model_paths import resolve_media_path

        assert resolve_media_path("abc123/0.jpg") == os.path.realpath(
            os.path.join(cfg.media_dir(), "abc123/0.jpg")
        )

    def test_resolve_media_path_accepts_legacy_absolute_values_inside_the_media_dir(self, ext_dir):
        """Rows written before issue #176 stored absolute paths inside the then-current
        media dir; they must keep resolving."""
        from py import config as cfg
        from py.services.model_paths import resolve_media_path

        absolute = os.path.join(cfg.media_dir(), "abc123", "0.jpg")
        assert resolve_media_path(absolute) == os.path.realpath(absolute)

    def test_resolve_media_path_rejects_values_outside_the_media_dir(self, ext_dir):
        """A stored value must never drive file access outside the media dir (CWE-22):
        traversal relatives and foreign absolute values resolve to None."""
        from py.services.model_paths import resolve_media_path

        assert resolve_media_path("../../secret.txt") is None
        assert resolve_media_path("abc123/../../x.jpg") is None
        assert resolve_media_path("/srv/media/abc123/0.jpg") is None
