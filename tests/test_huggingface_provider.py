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
# validate_repo_id
# ---------------------------------------------------------------------------


class TestValidateRepoId:
    def test_accepts_valid_repo_id(self):
        from py.services.providers.huggingface_provider import validate_repo_id

        assert validate_repo_id("user/repo") == "user/repo"

    def test_valid_single_segment(self):
        from py.services.providers.huggingface_provider import validate_repo_id

        assert validate_repo_id("bert-base-uncased") == "bert-base-uncased"

    def test_valid_with_dots_and_hyphens(self):
        from py.services.providers.huggingface_provider import validate_repo_id

        assert validate_repo_id("meta-llama/Llama-3.1-8B") == "meta-llama/Llama-3.1-8B"

    def test_rejects_path_traversal(self):
        from py.services.providers.huggingface_provider import validate_repo_id

        with pytest.raises(ValueError):
            validate_repo_id("../../etc/passwd")

    def test_rejects_double_slash(self):
        from py.services.providers.huggingface_provider import validate_repo_id

        with pytest.raises(ValueError):
            validate_repo_id("user/repo/subdir")

    def test_rejects_empty_string(self):
        from py.services.providers.huggingface_provider import validate_repo_id

        with pytest.raises(ValueError):
            validate_repo_id("")

    def test_rejects_absolute_path(self):
        from py.services.providers.huggingface_provider import validate_repo_id

        with pytest.raises(ValueError):
            validate_repo_id("/etc/passwd")

    def test_rejects_leading_dot(self):
        from py.services.providers.huggingface_provider import validate_repo_id

        with pytest.raises(ValueError):
            validate_repo_id(".hidden/repo")

    async def test_fetch_metadata_rejects_invalid_source_id(self, provider):
        with pytest.raises(ValueError):
            await provider.fetch_metadata("../../etc/passwd")

    async def test_get_model_files_rejects_invalid_repo_id(self, provider):
        with pytest.raises(ValueError):
            await provider.get_model_files("../../etc/passwd")

    async def test_get_readme_rejects_invalid_repo_id(self, provider):
        with pytest.raises(ValueError):
            await provider.get_readme("../../etc/passwd")

    async def test_resolve_direct_link_rejects_invalid_repo_id(self, provider):
        with pytest.raises(ValueError):
            await provider.resolve_direct_link("../../etc/passwd")


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

    async def test_exposes_lfs_oid_as_sha256(self, provider, monkeypatch):
        """F-92: the LFS oid is the SHA-256 auto-migration matches on."""
        repo_data = {
            "siblings": [{"rfilename": "m.safetensors", "size": 500, "lfs": {"oid": "abc123"}}]
        }
        _patch_client(monkeypatch, _mock(repo_data))
        files = await provider.get_model_files("user/repo")
        assert files[0]["sha256"] == "abc123"

    async def test_sha256_empty_without_lfs_block(self, provider, monkeypatch):
        """Plain git blobs carry a SHA-1 blob_id, which must not be mistaken for a hash."""
        repo_data = {"siblings": [{"rfilename": "m.safetensors", "size": 500, "blob_id": "sha1"}]}
        _patch_client(monkeypatch, _mock(repo_data))
        files = await provider.get_model_files("user/repo")
        assert files[0]["sha256"] == ""


# ---------------------------------------------------------------------------
# get_readme — YAML front-matter stripping
# ---------------------------------------------------------------------------


class TestGetReadme:
    async def test_strips_yaml_front_matter_and_returns_html(self, provider, monkeypatch):
        readme = "---\nlicense: mit\ntags:\n  - lora\n---\n\n# My Model\n\nGreat model."

        def handler(r: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text=readme)

        _patch_client(monkeypatch, httpx.MockTransport(handler))
        html = await provider.get_readme("user/repo")
        assert "<h1>" in html
        assert "My Model" in html
        assert "license: mit" not in html

    async def test_no_front_matter_converted_to_html(self, provider, monkeypatch):
        readme = "# Plain README\n\nNo YAML here."

        def handler(r: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text=readme)

        _patch_client(monkeypatch, httpx.MockTransport(handler))
        html = await provider.get_readme("user/repo")
        assert "<h1>" in html
        assert "Plain README" in html

    async def test_strips_yaml_front_matter_with_crlf_line_endings(self, provider, monkeypatch):
        readme = "---\r\nlicense: mit\r\n---\r\n\r\n# My Model\r\n\r\nGreat model."

        def handler(r: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text=readme)

        _patch_client(monkeypatch, httpx.MockTransport(handler))
        html = await provider.get_readme("user/repo")
        assert "<h1>" in html
        assert "My Model" in html
        assert "license: mit" not in html

    async def test_returns_empty_on_404(self, provider, monkeypatch):
        _patch_client(monkeypatch, _mock({}, 404))
        assert await provider.get_readme("user/repo") == ""


# ---------------------------------------------------------------------------
# resolve_direct_link
# ---------------------------------------------------------------------------


class TestResolveDirectLink:
    async def test_returns_image_urls_from_siblings(self, provider, monkeypatch):
        repo_data = {
            "siblings": [
                {"rfilename": "preview.png"},
                {"rfilename": "model.safetensors"},  # non-image ignored
                {"rfilename": "sample.webp"},
            ]
        }
        _patch_client(monkeypatch, _mock(repo_data))
        result = await provider.resolve_direct_link("user/repo")
        assert result["image_urls"] == [
            "https://huggingface.co/user/repo/resolve/main/preview.png",
            "https://huggingface.co/user/repo/resolve/main/sample.webp",
        ]

    async def test_caps_at_5_images(self, provider, monkeypatch):
        siblings = [{"rfilename": f"img{i}.jpg"} for i in range(10)]
        _patch_client(monkeypatch, _mock({"siblings": siblings}))
        result = await provider.resolve_direct_link("user/repo")
        assert len(result["image_urls"]) == 5


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

    async def test_trigger_words_not_in_tags(self, provider, monkeypatch):
        """F-32: trigger_words come from cardData.trigger, never appear in tags."""
        repo_data = {
            "tags": ["lora", "anime"],
            "cardData": {"trigger": ["1girl", "solo"]},
            "siblings": [],
        }
        _patch_client(monkeypatch, _mock(repo_data))
        meta = await provider.fetch_metadata("user/repo")
        assert "1girl" in meta.trigger_words
        assert "1girl" not in meta.tags
        assert "solo" not in meta.tags

    async def test_base_model_empty_for_hf(self, provider, monkeypatch):
        """F-32: HuggingFace has no dedicated base_model source; field is left empty."""
        repo_data = {
            "tags": ["text-to-image", "stable-diffusion-xl-base-1.0"],
            "cardData": {},
            "siblings": [],
        }
        _patch_client(monkeypatch, _mock(repo_data))
        meta = await provider.fetch_metadata("user/repo")
        assert meta.base_model == ""

    async def test_readme_html_populated_from_readme(self, provider, monkeypatch):
        """F-80: fetch_metadata always fetches README and converts it to HTML."""
        api_data = {"tags": [], "cardData": {"description": "desc"}, "siblings": []}
        readme_md = "# Model Title\n\nSome content."

        def handler(r: httpx.Request) -> httpx.Response:
            if "README.md" in str(r.url):
                return httpx.Response(200, text=readme_md)
            return httpx.Response(200, json=api_data)

        _patch_client(monkeypatch, httpx.MockTransport(handler))
        meta = await provider.fetch_metadata("user/repo")
        assert meta.readme_html != ""
        assert "<h1>" in meta.readme_html
        assert "Model Title" in meta.readme_html


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

    async def test_tags_added_as_repeated_filter_params(self, provider, monkeypatch):
        captured_filters: list[str] = []
        captured_has_pipeline_tag: list[bool] = []

        def handler(r: httpx.Request) -> httpx.Response:
            captured_filters.extend(r.url.params.get_list("filter"))
            captured_has_pipeline_tag.append("pipeline_tag" in dict(r.url.params))
            return httpx.Response(200, json=[])

        _patch_client(monkeypatch, httpx.MockTransport(handler))
        await provider.search("test", tags=["lora", "anime"])
        assert "lora" in captured_filters
        assert "anime" in captured_filters
        assert captured_has_pipeline_tag[0]

    async def test_tags_combined_with_gguf_filter(self, provider, monkeypatch):
        captured_filters: list[str] = []

        def handler(r: httpx.Request) -> httpx.Response:
            captured_filters.extend(r.url.params.get_list("filter"))
            return httpx.Response(200, json=[])

        _patch_client(monkeypatch, httpx.MockTransport(handler))
        await provider.search("test", format=".gguf", tags=["lora"])
        assert "gguf" in captured_filters
        assert "lora" in captured_filters

    async def test_no_filter_param_when_no_tags_and_no_gguf(self, provider, monkeypatch):
        captured_filters: list[str] = []

        def handler(r: httpx.Request) -> httpx.Response:
            captured_filters.extend(r.url.params.get_list("filter"))
            return httpx.Response(200, json=[])

        _patch_client(monkeypatch, httpx.MockTransport(handler))
        await provider.search("test")
        assert captured_filters == []


# ---------------------------------------------------------------------------
# lookup_by_repo_id
# ---------------------------------------------------------------------------


class TestLookupByRepoId:
    REPO_DATA = {
        "id": "owner/cool-lora",
        "tags": ["diffusers", "lora", "text-to-image"],
        "cardData": {
            "base_model": ["stabilityai/stable-diffusion-xl-base-1.0"],
            "description": "A cool LoRA",
            "instance_prompt": "cool style",
        },
        "siblings": [
            {"rfilename": "README.md"},
            {"rfilename": "preview.png"},
            {"rfilename": "second.png"},
        ],
    }

    async def test_maps_card_data(self, provider, monkeypatch):
        _patch_client(monkeypatch, _mock(self.REPO_DATA))
        result = await provider.lookup_by_repo_id("owner/cool-lora")
        assert result is not None
        assert result["name"] == "cool-lora"
        assert result["base_model"] == "stabilityai/stable-diffusion-xl-base-1.0"
        assert result["description"] == "A cool LoRA"
        assert result["tags"] == ["diffusers", "lora", "text-to-image"]
        assert result["trigger_words"] == ["cool style"]
        assert result["model_type"] == "loras"
        assert (
            result["thumbnail"] == "https://huggingface.co/owner/cool-lora/resolve/main/preview.png"
        )
        assert result["civitai_version_id"] == ""
        assert result["civitai_model_id"] == ""
        assert result["version_name"] == ""

    async def test_base_model_as_plain_string(self, provider, monkeypatch):
        _patch_client(monkeypatch, _mock({"cardData": {"base_model": "SD 1.5"}, "tags": []}))
        result = await provider.lookup_by_repo_id("owner/repo")
        assert result["base_model"] == "SD 1.5"

    async def test_non_lora_repo_defaults_to_checkpoints(self, provider, monkeypatch):
        _patch_client(monkeypatch, _mock({"tags": ["text-to-image"], "cardData": {}}))
        result = await provider.lookup_by_repo_id("owner/repo")
        assert result["model_type"] == "checkpoints"
        assert result["thumbnail"] == ""

    async def test_trigger_field_used_when_no_instance_prompt(self, provider, monkeypatch):
        _patch_client(monkeypatch, _mock({"tags": [], "cardData": {"trigger": ["a", "b"]}}))
        result = await provider.lookup_by_repo_id("owner/repo")
        assert result["trigger_words"] == ["a", "b"]

    async def test_missing_fields_default_to_empty(self, provider, monkeypatch):
        _patch_client(monkeypatch, _mock({}))
        result = await provider.lookup_by_repo_id("bert-base-uncased")
        assert result["name"] == "bert-base-uncased"
        assert result["base_model"] == ""
        assert result["description"] == ""
        assert result["tags"] == []
        assert result["trigger_words"] == []

    async def test_not_found_returns_none(self, provider, monkeypatch):
        _patch_client(monkeypatch, _mock({"error": "not found"}, status=404))
        assert await provider.lookup_by_repo_id("owner/missing") is None

    async def test_server_error_propagates(self, provider, monkeypatch):
        _patch_client(monkeypatch, _mock({"error": "oops"}, status=500))
        with pytest.raises(httpx.HTTPStatusError):
            await provider.lookup_by_repo_id("owner/repo")

    async def test_invalid_repo_id_raises(self, provider, monkeypatch):
        _patch_client(monkeypatch, _mock({}))
        with pytest.raises(ValueError):
            await provider.lookup_by_repo_id("../../etc/passwd")
