import pytest

from py.services.link_resolver import CIVITAI, HUGGINGFACE, parse_model_link, resolve
from py.services.providers.civitai_provider import CivitaiProvider
from py.services.providers.huggingface_provider import HuggingFaceProvider


class TestParseCivitaiLinks:
    @pytest.mark.parametrize(
        "url",
        [
            "https://civitai.com/models/1234",
            "https://civitai.com/models/1234/some-model-slug",
            "https://civitai.com/models/1234/",
            "https://civitai.red/models/1234",
        ],
    )
    def test_model_page_url(self, url):
        parsed = parse_model_link(url)
        assert parsed is not None
        assert parsed.platform == CIVITAI
        assert parsed.model_id == "1234"
        assert parsed.version_id == ""

    def test_model_page_url_with_version_query(self):
        parsed = parse_model_link("https://civitai.com/models/1234?modelVersionId=567")
        assert parsed is not None
        assert parsed.platform == CIVITAI
        assert parsed.model_id == "1234"
        assert parsed.version_id == "567"

    def test_non_numeric_version_query_is_ignored(self):
        parsed = parse_model_link("https://civitai.com/models/1234?modelVersionId=abc")
        assert parsed is not None
        assert parsed.model_id == "1234"
        assert parsed.version_id == ""

    def test_download_url_yields_version_only(self):
        parsed = parse_model_link("https://civitai.com/api/download/models/567")
        assert parsed is not None
        assert parsed.platform == CIVITAI
        assert parsed.model_id == ""
        assert parsed.version_id == "567"

    def test_model_versions_url_yields_version_only(self):
        parsed = parse_model_link("https://civitai.com/model-versions/999")
        assert parsed is not None
        assert parsed.platform == CIVITAI
        assert parsed.version_id == "999"

    @pytest.mark.parametrize(
        "url",
        [
            "https://civitai.com/user/someone",
            "https://civitai.com/models/notanumber",
            "https://civitai.com/",
        ],
    )
    def test_unsupported_civitai_paths_return_none(self, url):
        assert parse_model_link(url) is None


class TestParseHuggingFaceLinks:
    @pytest.mark.parametrize(
        "url",
        [
            "https://huggingface.co/owner/repo",
            "https://huggingface.co/owner/repo/",
            "https://huggingface.co/owner/repo/tree/main",
            "https://huggingface.co/owner/repo/blob/main/model.safetensors",
            "https://huggingface.co/owner/repo/resolve/main/model.safetensors",
            "https://hf.co/owner/repo",
        ],
    )
    def test_repo_urls(self, url):
        parsed = parse_model_link(url)
        assert parsed is not None
        assert parsed.platform == HUGGINGFACE
        assert parsed.repo_id == "owner/repo"

    def test_single_segment_repo(self):
        parsed = parse_model_link("https://huggingface.co/bert-base-uncased")
        assert parsed is not None
        assert parsed.platform == HUGGINGFACE
        assert parsed.repo_id == "bert-base-uncased"

    @pytest.mark.parametrize(
        "url",
        [
            "https://huggingface.co/",
            "https://huggingface.co/owner/repo/extra/segment",
            "https://huggingface.co/.hidden/repo",
        ],
    )
    def test_unsupported_hf_paths_return_none(self, url):
        assert parse_model_link(url) is None


class TestRejectedLinks:
    @pytest.mark.parametrize(
        "url",
        [
            "",
            "not-a-url",
            "https://example.com/models/1234",
            "file:///etc/passwd",
            "http://169.254.169.254/latest/meta-data",
            "https://civitai.com.evil.example/models/1234",
        ],
    )
    def test_rejected(self, url):
        assert parse_model_link(url) is None


class TestResolveDispatch:
    async def test_huggingface_uses_repo_lookup(self, monkeypatch):
        captured = {}

        async def _lookup(self, repo_id):
            captured["repo_id"] = repo_id
            return {"name": "cool-lora"}

        monkeypatch.setattr(HuggingFaceProvider, "lookup_by_repo_id", _lookup)
        parsed = parse_model_link("https://huggingface.co/owner/cool-lora")
        assert await resolve(parsed) == {"name": "cool-lora"}
        assert captured["repo_id"] == "owner/cool-lora"

    async def test_civitai_model_url_uses_model_lookup(self, monkeypatch):
        captured = {}

        async def _lookup(self, model_id, version_id=""):
            captured["args"] = (model_id, version_id)
            return {"name": "Great LoRA"}

        monkeypatch.setattr(CivitaiProvider, "lookup_by_model_id", _lookup)
        parsed = parse_model_link("https://civitai.com/models/77?modelVersionId=900")
        assert await resolve(parsed) == {"name": "Great LoRA"}
        assert captured["args"] == ("77", "900")

    async def test_civitai_download_url_uses_version_lookup(self, monkeypatch):
        captured = {}

        async def _lookup(self, version_id):
            captured["version_id"] = version_id
            return {"name": "By version"}

        monkeypatch.setattr(CivitaiProvider, "lookup_by_version_id", _lookup)
        parsed = parse_model_link("https://civitai.com/api/download/models/900")
        assert await resolve(parsed) == {"name": "By version"}
        assert captured["version_id"] == "900"
