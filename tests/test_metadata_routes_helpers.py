"""Tests for _derive_source_url in py/routes/metadata.py."""

import pytest


@pytest.fixture(scope="module")
def derive():
    from py.routes.metadata import _derive_source_url

    return _derive_source_url


class TestDeriveSourceUrl:
    def test_civitai_with_model_id(self, derive):
        url = derive("civitai", "12345", "67890")
        assert url == "https://civitai.com/models/67890"

    def test_civitai_without_civitai_model_id_returns_empty(self, derive):
        assert derive("civitai", "12345", "") == ""

    def test_huggingface_with_source_id(self, derive):
        url = derive("huggingface", "user/repo", "")
        assert url == "https://huggingface.co/user/repo"

    def test_huggingface_without_source_id_returns_empty(self, derive):
        assert derive("huggingface", "", "") == ""

    def test_unknown_platform_returns_empty(self, derive):
        assert derive("unknown", "123", "456") == ""

    def test_empty_platform_returns_empty(self, derive):
        assert derive("", "", "") == ""

    def test_civitai_url_contains_model_id_not_version_id(self, derive):
        url = derive("civitai", "version-999", "model-42")
        assert "model-42" in url
        assert "version-999" not in url
