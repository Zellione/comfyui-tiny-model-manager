"""Unit tests for py/services/foreign_import.py (F-154)."""

import os

import pytest


class TestValidateRoot:
    def test_relative_path_rejected(self, ext_dir):
        from py.services import foreign_import

        with pytest.raises(foreign_import.ForeignRootError) as excinfo:
            foreign_import.validate_root("some/relative/dir")
        assert str(excinfo.value) == "path_not_absolute"

    def test_blank_path_rejected(self, ext_dir):
        from py.services import foreign_import

        with pytest.raises(foreign_import.ForeignRootError):
            foreign_import.validate_root("   ")

    def test_missing_path_rejected(self, tmp_path, ext_dir):
        from py.services import foreign_import

        missing = str(tmp_path / "nope")
        with pytest.raises(foreign_import.ForeignRootError) as excinfo:
            foreign_import.validate_root(missing)
        assert str(excinfo.value) == "path_not_found"

    def test_file_is_not_a_directory(self, tmp_path, ext_dir):
        from py.services import foreign_import

        target = tmp_path / "a.txt"
        target.write_text("x")
        with pytest.raises(foreign_import.ForeignRootError) as excinfo:
            foreign_import.validate_root(str(target))
        assert str(excinfo.value) == "path_not_found"

    def test_models_subdir_is_appended(self, tmp_path, ext_dir):
        from py.services import foreign_import

        (tmp_path / "models" / "loras").mkdir(parents=True)
        resolved = foreign_import.validate_root(str(tmp_path))
        assert resolved == os.path.realpath(str(tmp_path / "models"))

    def test_models_root_used_as_is(self, tmp_path, ext_dir):
        from py.services import foreign_import

        root = tmp_path / "models"
        (root / "loras").mkdir(parents=True)
        resolved = foreign_import.validate_root(str(root))
        assert resolved == os.path.realpath(str(root))

    def test_local_models_root_rejected(self, tmp_path, monkeypatch, ext_dir):
        import folder_paths

        from py.services import foreign_import

        local = tmp_path / "local_models"
        (local / "loras").mkdir(parents=True)
        monkeypatch.setattr(folder_paths, "models_dir", str(local))
        with pytest.raises(foreign_import.ForeignRootError) as excinfo:
            foreign_import.validate_root(str(local))
        assert str(excinfo.value) == "path_is_local_root"

    def test_parent_of_local_root_rejected(self, tmp_path, monkeypatch, ext_dir):
        import folder_paths

        from py.services import foreign_import

        local = tmp_path / "comfy" / "models"
        (local / "loras").mkdir(parents=True)
        monkeypatch.setattr(folder_paths, "models_dir", str(local))
        with pytest.raises(foreign_import.ForeignRootError) as excinfo:
            foreign_import.validate_root(str(tmp_path / "comfy"))
        assert str(excinfo.value) == "path_is_local_root"

    def test_registered_folder_dir_rejected(self, tmp_path, monkeypatch, ext_dir):
        import folder_paths

        from py.services import foreign_import

        custom = tmp_path / "extra" / "loras"
        custom.mkdir(parents=True)
        monkeypatch.setattr(
            folder_paths, "folder_names_and_paths", {"loras": ([str(custom)], {".safetensors"})}
        )
        with pytest.raises(foreign_import.ForeignRootError) as excinfo:
            foreign_import.validate_root(str(custom))
        assert str(excinfo.value) == "path_is_local_root"


def _make_source_tree(tmp_path):
    """Build a small foreign models root and return its path."""
    root = tmp_path / "foreign" / "models"
    (root / "checkpoints").mkdir(parents=True)
    (root / "loras" / "style").mkdir(parents=True)
    (root / "configs").mkdir(parents=True)
    (root / "checkpoints" / "sd15.safetensors").write_bytes(b"a" * 16)
    (root / "loras" / "style" / "neon.safetensors").write_bytes(b"b" * 32)
    (root / "loras" / "notes.txt").write_text("ignored")
    (root / "configs" / "cfg.safetensors").write_bytes(b"c" * 8)
    (root / "loose.safetensors").write_bytes(b"d" * 4)
    return root


class TestScanSource:
    def test_groups_by_type_subfolder(self, tmp_path, ext_dir):
        from py.services import foreign_import

        files = foreign_import.scan_source(str(_make_source_tree(tmp_path)))
        assert {f.model_type for f in files} == {"checkpoints", "loras"}

    def test_preserves_relative_subfolder(self, tmp_path, ext_dir):
        from py.services import foreign_import

        files = foreign_import.scan_source(str(_make_source_tree(tmp_path)))
        lora = next(f for f in files if f.model_type == "loras")
        assert lora.filename == "style/neon.safetensors"

    def test_records_absolute_path_and_size(self, tmp_path, ext_dir):
        from py.services import foreign_import

        root = _make_source_tree(tmp_path)
        files = foreign_import.scan_source(str(root))
        ckpt = next(f for f in files if f.model_type == "checkpoints")
        assert ckpt.abs_path == os.path.join(str(root), "checkpoints", "sd15.safetensors")
        assert ckpt.size_bytes == 16

    def test_non_model_extensions_ignored(self, tmp_path, ext_dir):
        from py.services import foreign_import

        files = foreign_import.scan_source(str(_make_source_tree(tmp_path)))
        assert all(not f.filename.endswith(".txt") for f in files)

    def test_skip_types_ignored(self, tmp_path, ext_dir):
        from py.services import foreign_import

        files = foreign_import.scan_source(str(_make_source_tree(tmp_path)))
        assert all(f.model_type != "configs" for f in files)

    def test_loose_files_at_root_ignored(self, tmp_path, ext_dir):
        """A file directly in the models root has no type subfolder, so it has no type."""
        from py.services import foreign_import

        files = foreign_import.scan_source(str(_make_source_tree(tmp_path)))
        assert all(f.filename != "loose.safetensors" for f in files)

    def test_files_start_pending_and_unhashed(self, tmp_path, ext_dir):
        from py.services import foreign_import

        files = foreign_import.scan_source(str(_make_source_tree(tmp_path)))
        assert {f.status for f in files} == {"pending"}
        assert all(f.file_hash == "" for f in files)
