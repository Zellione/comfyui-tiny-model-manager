"""Tests for HuggingFace provider (py/services/providers/huggingface_provider.py)."""

import httpx
import pytest


@pytest.fixture(scope="module")
def provider():
    from py.services.providers.huggingface_provider import HuggingFaceProvider

    return HuggingFaceProvider()


def _mock(response_body: dict | list, status: int = 200) -> httpx.MockTransport:
    return httpx.MockTransport(lambda r: httpx.Response(status, json=response_body))


def _patch_client(monkeypatch, transport: httpx.MockTransport) -> None:
    """Replace httpx.AsyncClient with one that uses *transport*, preserving other kwargs."""
    _orig = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: _orig(transport=transport, **kw))


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


class TestConstants:
    def test_model_extensions_contains_safetensors(self):
        from py.services.providers.huggingface_provider import MODEL_EXTENSIONS

        assert ".safetensors" in MODEL_EXTENSIONS

    def test_model_extensions_contains_gguf(self):
        from py.services.providers.huggingface_provider import MODEL_EXTENSIONS

        assert ".gguf" in MODEL_EXTENSIONS

    def test_image_extensions_contains_jpg(self):
        from py.services.providers.huggingface_provider import IMAGE_EXTENSIONS

        assert ".jpg" in IMAGE_EXTENSIONS

    def test_hf_type_map_defaults_to_text_to_image(self):
        from py.services.providers.huggingface_provider import HF_TYPE_MAP

        assert HF_TYPE_MAP.get("checkpoints") == "text-to-image"


# ---------------------------------------------------------------------------
# get_model_files
# ---------------------------------------------------------------------------


class TestGetModelFiles:
    async def test_filters_to_model_extensions(self, provider, monkeypatch):
        repo_data = {
            "siblings": [
                {"rfilename": "model.safetensors", "size": 1000},
                {"rfilename": "README.md", "size": 100},
                {"rfilename": "model.gguf", "size": 2000},
                {"rfilename": "image.jpg", "size": 50},
            ]
        }
        _patch_client(monkeypatch, _mock(repo_data))
        files = await provider.get_model_files("user/repo")
        names = [f["filename"] for f in files]
        assert "model.safetensors" in names
        assert "model.gguf" in names
        assert "README.md" not in names
        assert "image.jpg" not in names

    async def test_file_has_url(self, provider, monkeypatch):
        repo_data = {"siblings": [{"rfilename": "m.safetensors", "size": 500}]}
        _patch_client(monkeypatch, _mock(repo_data))
        files = await provider.get_model_files("user/repo")
        assert files[0]["url"] == "https://huggingface.co/user/repo/resolve/main/m.safetensors"


# ---------------------------------------------------------------------------
# get_readme — YAML front-matter stripping
# ---------------------------------------------------------------------------


class TestGetReadme:
    async def test_strips_yaml_front_matter(self, provider, monkeypatch):
        readme = "---\nlicense: mit\ntags:\n  - lora\n---\n\n# My Model\n\nGreat model."

        def handler(r: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text=readme)

        _patch_client(monkeypatch, httpx.MockTransport(handler))
        text = await provider.get_readme("user/repo")
        assert text.startswith("# My Model")
        assert "license: mit" not in text

    async def test_no_front_matter_returned_as_is(self, provider, monkeypatch):
        readme = "# Plain README\n\nNo YAML here."

        def handler(r: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text=readme)

        _patch_client(monkeypatch, httpx.MockTransport(handler))
        text = await provider.get_readme("user/repo")
        assert "# Plain README" in text

    async def test_returns_empty_on_404(self, provider, monkeypatch):
        _patch_client(monkeypatch, _mock({}, 404))
        assert await provider.get_readme("user/repo") == ""


# ---------------------------------------------------------------------------
# fetch_metadata
# ---------------------------------------------------------------------------


class TestFetchMetadata:
    async def test_tags_and_images_returned(self, provider, monkeypatch):
        repo_data = {
            "tags": ["lora", "anime"],
            "cardData": {"description": "nice model", "trigger": ["1girl"]},
            "siblings": [{"rfilename": "preview.jpg"}],
        }
        _patch_client(monkeypatch, _mock(repo_data))
        meta = await provider.fetch_metadata("user/repo")
        assert "lora" in meta.tags
        assert meta.description == "nice model"
        assert meta.trigger_words == ["1girl"]
        assert len(meta.image_urls) == 1

    async def test_at_most_5_images(self, provider, monkeypatch):
        siblings = [{"rfilename": f"img{i}.jpg"} for i in range(10)]
        repo_data = {"tags": [], "cardData": {}, "siblings": siblings}
        _patch_client(monkeypatch, _mock(repo_data))
        meta = await provider.fetch_metadata("user/repo")
        assert len(meta.image_urls) <= 5


# ---------------------------------------------------------------------------
# search — gguf filter param
# ---------------------------------------------------------------------------


class TestSearch:
    async def test_gguf_format_uses_filter_param(self, provider, monkeypatch):
        captured_params: dict = {}

        def handler(r: httpx.Request) -> httpx.Response:
            captured_params.update(dict(r.url.params))
            return httpx.Response(200, json=[])

        _patch_client(monkeypatch, httpx.MockTransport(handler))
        await provider.search("test", format=".gguf")
        assert captured_params.get("filter") == "gguf"
        assert "pipeline_tag" not in captured_params

    async def test_non_gguf_uses_pipeline_tag(self, provider, monkeypatch):
        captured_params: dict = {}

        def handler(r: httpx.Request) -> httpx.Response:
            captured_params.update(dict(r.url.params))
            return httpx.Response(200, json=[])

        _patch_client(monkeypatch, httpx.MockTransport(handler))
        await provider.search("test", format="")
        assert "pipeline_tag" in captured_params
        assert "filter" not in captured_params

    async def test_has_more_true_when_full_page(self, provider, monkeypatch):
        items = [{"modelId": str(i), "id": str(i), "siblings": [], "tags": []} for i in range(20)]
        _patch_client(monkeypatch, _mock(items))
        result = await provider.search("test")
        assert result["hasMore"] is True
        assert result["nextPage"] == 1

    async def test_has_more_false_when_partial_page(self, provider, monkeypatch):
        items = [{"modelId": "1", "id": "1", "siblings": [], "tags": []}]
        _patch_client(monkeypatch, _mock(items))
        result = await provider.search("test")
        assert result["hasMore"] is False
