"""Tests for py/config.py — path helpers and settings load/save."""

import json
import os

import pytest


@pytest.fixture
def cfg(tmp_path):
    """Return the config module initialised against a fresh temp dir."""
    from py import config as _cfg

    _cfg.init(str(tmp_path))
    return _cfg


class TestPaths:
    def test_data_dir_is_inside_ext_dir(self, cfg, tmp_path):
        assert cfg.data_dir() == str(tmp_path / "data")

    def test_db_path(self, cfg, tmp_path):
        assert cfg.db_path() == str(tmp_path / "data" / "models.db")

    def test_settings_path(self, cfg, tmp_path):
        assert cfg.settings_path() == str(tmp_path / "data" / "settings.json")

    def test_media_dir_default(self, cfg, tmp_path):
        assert cfg.media_dir() == str(tmp_path / "data" / "media")

    def test_media_dir_custom_absolute(self, cfg, tmp_path):
        custom = str(tmp_path / "custom_media")
        os.makedirs(custom, exist_ok=True)
        cfg.save_settings({"media_dir": custom})
        assert cfg.media_dir() == custom

    def test_media_dir_relative_string_ignored(self, cfg):
        """A non-absolute custom path falls back to the default."""
        cfg.save_settings({"media_dir": "relative/path"})
        assert os.path.isabs(cfg.media_dir())
        assert "media" in cfg.media_dir()

    def test_init_creates_data_dir(self, tmp_path):
        from py import config as _cfg

        target = str(tmp_path / "new_ext")
        _cfg.init(target)
        assert os.path.isdir(os.path.join(target, "data"))


class TestSettingsRoundtrip:
    def test_load_returns_empty_when_no_file(self, cfg):
        assert cfg.load_settings() == {}

    def test_save_and_load_round_trip(self, cfg):
        data = {"civitai_api_key": "abc", "hf_token": "xyz"}
        cfg.save_settings(data)
        assert cfg.load_settings() == data

    def test_save_creates_parent_dir(self, tmp_path):
        from py import config as _cfg

        nested = str(tmp_path / "a" / "b")
        _cfg.init(nested)
        _cfg.save_settings({"k": "v"})
        assert json.loads(open(_cfg.settings_path()).read())["k"] == "v"

    def test_load_settings_is_dict(self, cfg):
        cfg.save_settings({"x": 1})
        result = cfg.load_settings()
        assert isinstance(result, dict)
