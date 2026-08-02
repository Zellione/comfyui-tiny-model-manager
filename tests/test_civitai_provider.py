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

    async def test_description_prefers_model_page_over_version_notes(self, provider, monkeypatch):
        """The version 'description' is a changelog; the model page holds the real description."""
        version_data = {
            "trainedWords": [],
            "description": "Changelog",
            "baseModel": "",
            "images": [],
            "modelId": 112,
        }
        model_data = {"description": "Model page description", "tags": []}

        def handler(request: httpx.Request) -> httpx.Response:
            url = str(request.url)
            if "model-versions" in url:
                return httpx.Response(200, json=version_data)
            if "/models/112" in url:
                return httpx.Response(200, json=model_data)
            return httpx.Response(404)

        _patch_civitai_client(monkeypatch, httpx.MockTransport(handler))
        meta = await provider.fetch_metadata("9999")
        assert meta.description == ("Model page description<hr><h3>Version notes</h3>Changelog")

    async def test_version_name_populated(self, provider, monkeypatch):
        """F-96: civitai_version_name is populated from the 'name' field of the version response."""
        version_data = {
            "name": "V5.1 (VAE)",
            "trainedWords": [],
            "description": "",
            "baseModel": "SDXL 1.0",
            "images": [],
            "modelId": None,
        }

        transport = httpx.MockTransport(
            lambda req: (
                httpx.Response(200, json=version_data)
                if "model-versions" in str(req.url)
                else httpx.Response(404)
            )
        )
        _orig = httpx.AsyncClient
        monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: _orig(transport=transport, **kw))
        meta = await provider.fetch_metadata("9999")
        assert meta.civitai_version_name == "V5.1 (VAE)"

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


# ---------------------------------------------------------------------------
# get_version_files
# ---------------------------------------------------------------------------


class TestGetVersionFiles:
    _VERSION_DATA = {
        "modelId": 42,
        "files": [
            {
                "name": "model.safetensors",
                "type": "Model",
                "sizeKB": 1024,
                "downloadUrl": "https://civitai.com/dl/model",
            },
            {
                "name": "training_data.zip",
                "type": "Training Data",
                "sizeKB": 512,
                "downloadUrl": "https://civitai.com/dl/training",
            },
            {
                "name": "dataset_captions.zip",
                "type": "Training Data",
                "sizeKB": 256,
                "downloadUrl": "https://civitai.com/dl/captions",
            },
        ],
    }

    async def test_returns_only_model_type_files(self, provider, monkeypatch):
        transport = httpx.MockTransport(lambda r: httpx.Response(200, json=self._VERSION_DATA))
        _orig = httpx.AsyncClient
        monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: _orig(transport=transport, **kw))
        files = await provider.get_version_files(1)
        assert len(files) == 1
        assert files[0]["filename"] == "model.safetensors"

    async def test_excludes_zip_training_data(self, provider, monkeypatch):
        transport = httpx.MockTransport(lambda r: httpx.Response(200, json=self._VERSION_DATA))
        _orig = httpx.AsyncClient
        monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: _orig(transport=transport, **kw))
        files = await provider.get_version_files(1)
        filenames = [f["filename"] for f in files]
        assert "training_data.zip" not in filenames
        assert "dataset_captions.zip" not in filenames


# ---------------------------------------------------------------------------
# lookup_by_hash
# ---------------------------------------------------------------------------


class TestLookupByHash:
    async def test_found_returns_metadata(self, provider, monkeypatch):
        version_data = {
            "id": 12345,
            "name": "v2.0",
            "modelId": 789,
            "baseModel": "SD 1.5",
            "description": "A great model",
            "trainedWords": ["portrait"],
            "images": [{"url": "https://example.com/img.jpg"}],
            "model": {"name": "Great LoRA", "tags": ["portrait", "realistic"]},
        }
        transport = _make_transport({"model-versions/by-hash": (200, version_data)})
        _orig = httpx.AsyncClient
        monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: _orig(transport=transport, **kw))
        result = await provider.lookup_by_hash("deadbeef")
        assert result is not None
        assert result["name"] == "Great LoRA"
        assert result["base_model"] == "SD 1.5"
        assert result["description"] == "A great model"
        assert result["trigger_words"] == ["portrait"]
        assert result["tags"] == ["portrait", "realistic"]
        assert result["version_name"] == "v2.0"
        assert result["civitai_version_id"] == "12345"
        assert result["civitai_model_id"] == "789"

    async def test_not_found_returns_none(self, provider, monkeypatch):
        transport = _make_transport({"model-versions/by-hash": (404, {"error": "not found"})})
        _orig = httpx.AsyncClient
        monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: _orig(transport=transport, **kw))
        result = await provider.lookup_by_hash("notexist")
        assert result is None

    async def test_server_error_propagates(self, provider, monkeypatch):
        transport = _make_transport({"model-versions/by-hash": (500, {"error": "oops"})})
        _orig = httpx.AsyncClient
        monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: _orig(transport=transport, **kw))
        with pytest.raises(httpx.HTTPStatusError):
            await provider.lookup_by_hash("abc123")

    async def test_description_comes_from_model_page(self, provider, monkeypatch):
        """The version response carries no model description — it must be fetched separately."""
        version_data = {"id": 1, "modelId": 500, "description": None, "model": {"name": "Lo"}}
        _patch_civitai_client(
            monkeypatch,
            _make_transport(
                {
                    "model-versions/by-hash": (200, version_data),
                    "models/500": (200, {"description": "The real model description"}),
                }
            ),
        )
        result = await provider.lookup_by_hash("abc")
        assert result["description"] == "The real model description"

    async def test_version_notes_appended_to_model_description(self, provider, monkeypatch):
        version_data = {"id": 1, "modelId": 501, "description": "<p>Changelog</p>", "model": {}}
        _patch_civitai_client(
            monkeypatch,
            _make_transport(
                {
                    "model-versions/by-hash": (200, version_data),
                    "models/501": (200, {"description": "<p>Model page</p>"}),
                }
            ),
        )
        result = await provider.lookup_by_hash("abc")
        assert result["description"] == (
            "<p>Model page</p><hr><h3>Version notes</h3><p>Changelog</p>"
        )

    async def test_tags_come_from_model_page(self, provider, monkeypatch):
        version_data = {"id": 1, "modelId": 502, "model": {"name": "Lo"}}
        _patch_civitai_client(
            monkeypatch,
            _make_transport(
                {
                    "model-versions/by-hash": (200, version_data),
                    "models/502": (200, {"tags": ["anime", "style"]}),
                }
            ),
        )
        result = await provider.lookup_by_hash("abc")
        assert result["tags"] == ["anime", "style"]

    async def test_model_page_failure_falls_back_to_version_description(
        self, provider, monkeypatch
    ):
        version_data = {"id": 1, "modelId": 503, "description": "Version only", "model": {}}
        _patch_civitai_client(
            monkeypatch,
            _make_transport(
                {
                    "model-versions/by-hash": (200, version_data),
                    "models/503": (500, {"error": "oops"}),
                }
            ),
        )
        result = await provider.lookup_by_hash("abc")
        assert result["description"] == "Version only"

    async def test_empty_optional_fields_default(self, provider, monkeypatch):
        version_data = {
            "id": 1,
            "modelId": 2,
            "model": {},
        }
        transport = _make_transport({"model-versions/by-hash": (200, version_data)})
        _orig = httpx.AsyncClient
        monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: _orig(transport=transport, **kw))
        result = await provider.lookup_by_hash("abc")
        assert result["name"] == ""
        assert result["base_model"] == ""
        assert result["description"] == ""
        assert result["tags"] == []
        assert result["trigger_words"] == []


# ---------------------------------------------------------------------------
# lookup_by_version_id / lookup_by_model_id
# ---------------------------------------------------------------------------


def _patch_civitai_client(monkeypatch, transport: httpx.MockTransport) -> None:
    _orig = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: _orig(transport=transport, **kw))


class TestLookupByVersionId:
    async def test_found_returns_metadata(self, provider, monkeypatch):
        version_data = {
            "id": 555,
            "name": "v3",
            "modelId": 42,
            "baseModel": "SDXL 1.0",
            "description": "Version notes",
            "trainedWords": ["magic"],
            "images": [{"url": "https://example.com/preview.jpg"}],
            "model": {"name": "Magic LoRA", "tags": ["magic"], "type": "LORA"},
        }
        _patch_civitai_client(
            monkeypatch, _make_transport({"model-versions/555": (200, version_data)})
        )
        result = await provider.lookup_by_version_id("555")
        assert result is not None
        assert result["name"] == "Magic LoRA"
        assert result["base_model"] == "SDXL 1.0"
        assert result["civitai_version_id"] == "555"
        assert result["civitai_model_id"] == "42"
        assert result["model_type"] == "loras"
        assert result["thumbnail"] == "https://example.com/preview.jpg"

    async def test_description_comes_from_model_page(self, provider, monkeypatch):
        version_data = {"id": 556, "modelId": 43, "description": "", "model": {"name": "M"}}
        _patch_civitai_client(
            monkeypatch,
            _make_transport(
                {
                    "model-versions/556": (200, version_data),
                    "models/43": (200, {"description": "Model page description"}),
                }
            ),
        )
        result = await provider.lookup_by_version_id("556")
        assert result["description"] == "Model page description"

    async def test_not_found_returns_none(self, provider, monkeypatch):
        _patch_civitai_client(monkeypatch, _make_transport({"model-versions/1": (404, {})}))
        assert await provider.lookup_by_version_id("1") is None

    async def test_server_error_propagates(self, provider, monkeypatch):
        _patch_civitai_client(monkeypatch, _make_transport({"model-versions/2": (500, {})}))
        with pytest.raises(httpx.HTTPStatusError):
            await provider.lookup_by_version_id("2")


class TestLookupByModelId:
    MODEL_DATA = {
        "id": 77,
        "name": "Great Checkpoint",
        "type": "Checkpoint",
        "tags": ["photo"],
        "description": "Model page description",
        "modelVersions": [
            {
                "id": 900,
                "name": "v2",
                "baseModel": "SD 1.5",
                "trainedWords": ["newest"],
                "images": [{"url": "https://example.com/v2.jpg"}],
            },
            {
                "id": 800,
                "name": "v1",
                "baseModel": "SD 1.0",
                "trainedWords": ["older"],
                "images": [{"url": "https://example.com/v1.jpg"}],
            },
        ],
    }

    async def test_uses_first_version_by_default(self, provider, monkeypatch):
        _patch_civitai_client(monkeypatch, _make_transport({"models/77": (200, self.MODEL_DATA)}))
        result = await provider.lookup_by_model_id("77")
        assert result is not None
        assert result["name"] == "Great Checkpoint"
        assert result["version_name"] == "v2"
        assert result["base_model"] == "SD 1.5"
        assert result["civitai_version_id"] == "900"
        assert result["civitai_model_id"] == "77"
        assert result["model_type"] == "checkpoints"
        assert result["tags"] == ["photo"]
        assert result["trigger_words"] == ["newest"]
        assert result["thumbnail"] == "https://example.com/v2.jpg"

    async def test_selects_requested_version(self, provider, monkeypatch):
        _patch_civitai_client(monkeypatch, _make_transport({"models/77": (200, self.MODEL_DATA)}))
        result = await provider.lookup_by_model_id("77", "800")
        assert result["version_name"] == "v1"
        assert result["civitai_version_id"] == "800"

    async def test_unknown_version_falls_back_to_first(self, provider, monkeypatch):
        _patch_civitai_client(monkeypatch, _make_transport({"models/77": (200, self.MODEL_DATA)}))
        result = await provider.lookup_by_model_id("77", "12345")
        assert result["civitai_version_id"] == "900"

    async def test_description_falls_back_to_model_page(self, provider, monkeypatch):
        _patch_civitai_client(monkeypatch, _make_transport({"models/77": (200, self.MODEL_DATA)}))
        result = await provider.lookup_by_model_id("77")
        assert result["description"] == "Model page description"

    async def test_version_notes_appended_to_model_description(self, provider, monkeypatch):
        model_data = {
            **self.MODEL_DATA,
            "id": 81,
            "modelVersions": [{**self.MODEL_DATA["modelVersions"][0], "description": "Changelog"}],
        }
        _patch_civitai_client(monkeypatch, _make_transport({"models/81": (200, model_data)}))
        result = await provider.lookup_by_model_id("81")
        assert result["description"] == (
            "Model page description<hr><h3>Version notes</h3>Changelog"
        )

    async def test_no_versions_returns_none(self, provider, monkeypatch):
        _patch_civitai_client(
            monkeypatch, _make_transport({"models/78": (200, {"id": 78, "modelVersions": []})})
        )
        assert await provider.lookup_by_model_id("78") is None

    async def test_not_found_returns_none(self, provider, monkeypatch):
        _patch_civitai_client(monkeypatch, _make_transport({"models/79": (404, {})}))
        assert await provider.lookup_by_model_id("79") is None

    async def test_server_error_propagates(self, provider, monkeypatch):
        _patch_civitai_client(monkeypatch, _make_transport({"models/80": (500, {})}))
        with pytest.raises(httpx.HTTPStatusError):
            await provider.lookup_by_model_id("80")
