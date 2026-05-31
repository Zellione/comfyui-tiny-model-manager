"""Tests for CivitAI provider (py/services/providers/civitai_provider.py)."""

import httpx
import pytest


@pytest.fixture(scope="module")
def provider():
    from py.services.providers.civitai_provider import CivitaiProvider

    return CivitaiProvider()


# ---------------------------------------------------------------------------
# Type map helpers
# ---------------------------------------------------------------------------


class TestTypeMaps:
    def test_forward_map_keys(self):
        from py.services.providers.civitai_provider import CIVITAI_TYPE_MAP

        assert "checkpoints" in CIVITAI_TYPE_MAP
        assert "loras" in CIVITAI_TYPE_MAP
        assert "embeddings" in CIVITAI_TYPE_MAP
        assert "vae" in CIVITAI_TYPE_MAP
        assert "controlnet" in CIVITAI_TYPE_MAP

    def test_reverse_map_values(self):
        from py.services.providers.civitai_provider import (
            CIVITAI_REVERSE_TYPE_MAP,
            CIVITAI_TYPE_MAP,
        )

        for k, v in CIVITAI_TYPE_MAP.items():
            assert CIVITAI_REVERSE_TYPE_MAP[v] == k

    def test_unknown_type_fallback(self):
        from py.services.providers.civitai_provider import CIVITAI_REVERSE_TYPE_MAP

        assert CIVITAI_REVERSE_TYPE_MAP.get("DoesNotExist", "checkpoints") == "checkpoints"


# ---------------------------------------------------------------------------
# auth_headers — reads from settings
# ---------------------------------------------------------------------------


class TestAuthHeaders:
    def test_no_key_returns_empty(self, provider, ext_dir):
        headers = provider.auth_headers()
        assert headers == {}

    def test_with_key_returns_bearer(self, provider, ext_dir):
        from py import config as cfg

        cfg.save_settings({"civitai_api_key": "tok123"})
        headers = provider.auth_headers()
        assert headers == {"Authorization": "Bearer tok123"}
        cfg.save_settings({})  # reset


# ---------------------------------------------------------------------------
# resolve_direct_link — mocked HTTP
# ---------------------------------------------------------------------------


def _make_transport(responses: dict) -> httpx.MockTransport:
    """
    Build an httpx.MockTransport from a dict of ``{url_fragment: response}``.
    Each value is a tuple of (status_code, json_body_dict).
    """

    def handler(request: httpx.Request) -> httpx.Response:
        for fragment, (status, body) in responses.items():
            if fragment in str(request.url):
                return httpx.Response(status, json=body)
        return httpx.Response(404, json={"error": "not found"})

    return httpx.MockTransport(handler)


class TestResolveDirectLink:
    async def test_primary_file_selected(self, provider, monkeypatch):
        version_data = {
            "files": [
                {"name": "secondary.pt", "type": "VAE", "primary": False, "sizeKB": 10},
                {"name": "primary.safetensors", "type": "Model", "primary": True, "sizeKB": 100},
            ],
            "model": {"type": "LORA"},
            "images": [{"url": "https://example.com/img.jpg"}],
        }
        transport = _make_transport({"model-versions/42": (200, version_data)})
        _orig = httpx.AsyncClient
        monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: _orig(transport=transport, **kw))
        result = await provider.resolve_direct_link(42)
        assert result["filename"] == "primary.safetensors"
        assert result["model_type"] == "loras"
        assert result["size_kb"] == 100

    async def test_fallback_to_first_model_file(self, provider, monkeypatch):
        version_data = {
            "files": [
                {"name": "first.safetensors", "type": "Model", "primary": False, "sizeKB": 50},
            ],
            "model": {"type": "Checkpoint"},
            "images": [],
        }
        transport = _make_transport({"model-versions/7": (200, version_data)})
        _orig = httpx.AsyncClient
        monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: _orig(transport=transport, **kw))
        result = await provider.resolve_direct_link(7)
        assert result["filename"] == "first.safetensors"
        assert result["model_type"] == "checkpoints"

    async def test_raises_when_no_files(self, provider, monkeypatch):
        version_data = {"files": [], "model": {"type": "Checkpoint"}, "images": []}
        transport = _make_transport({"model-versions/99": (200, version_data)})
        _orig = httpx.AsyncClient
        monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: _orig(transport=transport, **kw))
        with pytest.raises(ValueError, match="No downloadable file"):
            await provider.resolve_direct_link(99)

    async def test_image_urls_returned(self, provider, monkeypatch):
        version_data = {
            "files": [{"name": "m.safetensors", "type": "Model", "primary": True, "sizeKB": 1}],
            "model": {"type": "LORA"},
            "images": [
                {"url": "https://example.com/a.jpg"},
                {"url": "https://example.com/b.jpg"},
            ],
        }
        transport = _make_transport({"model-versions/5": (200, version_data)})
        _orig = httpx.AsyncClient
        monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: _orig(transport=transport, **kw))
        result = await provider.resolve_direct_link(5)
        assert len(result["image_urls"]) == 2


# ---------------------------------------------------------------------------
# fetch_metadata
# ---------------------------------------------------------------------------


class TestFetchMetadata:
    async def test_returns_provider_metadata(self, provider, monkeypatch):
        version_data = {
            "trainedWords": ["word1", "word2"],
            "description": "version desc",
            "baseModel": "SDXL 1.0",
            "images": [{"url": "https://example.com/img.jpg"}],
            "modelId": 111,
        }
        model_data = {"description": "model desc", "tags": ["fantasy", "portrait"]}

        def handler(request: httpx.Request) -> httpx.Response:
            url = str(request.url)
            if "model-versions" in url:
                return httpx.Response(200, json=version_data)
            if "/models/111" in url:
                return httpx.Response(200, json=model_data)
            return httpx.Response(404)

        transport = httpx.MockTransport(handler)
        _orig = httpx.AsyncClient
        monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: _orig(transport=transport, **kw))
        meta = await provider.fetch_metadata("9999")
        assert meta.trigger_words == ["word1", "word2"]
        assert meta.base_model == "SDXL 1.0"
        assert "fantasy" in meta.tags
        assert meta.civitai_model_id == "111"

    async def test_base_model_not_in_tags(self, provider, monkeypatch):
        """F-32: base_model comes from baseModel field, never appears in tags."""
        version_data = {
            "trainedWords": [],
            "description": "",
            "baseModel": "Pony",
            "images": [],
            "modelId": 200,
        }
        model_data = {"description": "", "tags": ["anime", "portrait"]}

        def handler(request: httpx.Request) -> httpx.Response:
            url = str(request.url)
            if "model-versions" in url:
                return httpx.Response(200, json=version_data)
            if "/models/200" in url:
                return httpx.Response(200, json=model_data)
            return httpx.Response(404)

        transport = httpx.MockTransport(handler)
        _orig = httpx.AsyncClient
        monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: _orig(transport=transport, **kw))
        meta = await provider.fetch_metadata("9999")
        assert meta.base_model == "Pony"
        assert "Pony" not in meta.tags

    async def test_trigger_words_not_in_tags(self, provider, monkeypatch):
        """F-32: trigger_words come from trainedWords field, never appear in tags."""
        version_data = {
            "trainedWords": ["masterpiece", "best quality"],
            "description": "",
            "baseModel": "",
            "images": [],
            "modelId": 201,
        }
        model_data = {"description": "", "tags": ["anime"]}

        def handler(request: httpx.Request) -> httpx.Response:
            url = str(request.url)
            if "model-versions" in url:
                return httpx.Response(200, json=version_data)
            if "/models/201" in url:
                return httpx.Response(200, json=model_data)
            return httpx.Response(404)

        transport = httpx.MockTransport(handler)
        _orig = httpx.AsyncClient
        monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: _orig(transport=transport, **kw))
        meta = await provider.fetch_metadata("9999")
        assert "masterpiece" in meta.trigger_words
        assert "masterpiece" not in meta.tags
        assert "best quality" not in meta.tags

    async def test_http_error_propagates(self, provider, monkeypatch):
        transport = httpx.MockTransport(lambda r: httpx.Response(404))
        _orig = httpx.AsyncClient
        monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: _orig(transport=transport, **kw))
        with pytest.raises(httpx.HTTPStatusError):
            await provider.fetch_metadata("0")


# ---------------------------------------------------------------------------
# search — tag param
# ---------------------------------------------------------------------------


class TestSearch:
    async def test_first_tag_sent_as_tag_param(self, provider, monkeypatch):
        captured: dict = {}

        def handler(r: httpx.Request) -> httpx.Response:
            captured.update(dict(r.url.params))
            return httpx.Response(200, json={"items": [], "metadata": {}})

        transport = httpx.MockTransport(handler)
        _orig = httpx.AsyncClient
        monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: _orig(transport=transport, **kw))
        await provider.search("test", tags=["lora", "anime"])
        assert captured.get("tag") == "lora"

    async def test_no_tag_param_when_tags_empty(self, provider, monkeypatch):
        captured: dict = {}

        def handler(r: httpx.Request) -> httpx.Response:
            captured.update(dict(r.url.params))
            return httpx.Response(200, json={"items": [], "metadata": {}})

        transport = httpx.MockTransport(handler)
        _orig = httpx.AsyncClient
        monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: _orig(transport=transport, **kw))
        await provider.search("test")
        assert "tag" not in captured

    async def test_cursor_used_without_query(self, provider, monkeypatch):
        captured: dict = {}

        def handler(r: httpx.Request) -> httpx.Response:
            captured.update(dict(r.url.params))
            return httpx.Response(200, json={"items": [], "metadata": {}})

        transport = httpx.MockTransport(handler)
        _orig = httpx.AsyncClient
        monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: _orig(transport=transport, **kw))
        await provider.search("", cursor="abc123")
        assert captured.get("cursor") == "abc123"
        assert "page" not in captured

    async def test_page_used_when_no_query_and_no_cursor(self, provider, monkeypatch):
        captured: dict = {}

        def handler(r: httpx.Request) -> httpx.Response:
            captured.update(dict(r.url.params))
            return httpx.Response(200, json={"items": [], "metadata": {}})

        transport = httpx.MockTransport(handler)
        _orig = httpx.AsyncClient
        monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: _orig(transport=transport, **kw))
        await provider.search("", page=2)
        assert captured.get("page") == "2"
        assert "cursor" not in captured
