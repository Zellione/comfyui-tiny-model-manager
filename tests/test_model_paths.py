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
