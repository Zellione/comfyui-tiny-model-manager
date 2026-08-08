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
