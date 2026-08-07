"""Unit tests for py/services/missing_model_resolver.py (F-144).

Every provider call goes through a module-level seam, so these tests monkeypatch this module's
attributes and never touch httpx (the autouse ``block_network`` fixture would raise anyway).
"""

import httpx
import pytest

from py.services import missing_model_resolver as res

CIVITAI_LINK = "https://civitai.com/api/download/models/555"
CIVITAI_MODEL_LINK = "https://civitai.com/models/42"
HF_LINK = "https://huggingface.co/owner/repo"
WANTED = "wanted.safetensors"


def _seam(monkeypatch, name, value):
    """Replace a provider seam with a coroutine returning ``value`` (or raising it)."""
    calls = []

    async def fake(*args):
        calls.append(args)
        if isinstance(value, Exception):
            raise value
        return value

    monkeypatch.setattr(res, name, fake)
    return calls


def _no_matches(monkeypatch):
    """Make both search stages come up empty so a test can isolate an earlier stage."""
    _seam(monkeypatch, "_civitai_search", {"items": []})
    _seam(monkeypatch, "_hf_search", {"items": []})


def _civitai_version(files, version_id=7, base_model="SDXL 1.0"):
    return {"id": version_id, "baseModel": base_model, "files": files}


class TestSearchTerm:
    def test_strips_extension_and_directory(self):
        assert res.search_term("sub/dir/My_Model.v2.safetensors") == "My_Model.v2"


class TestCivitaiVersionLink:
    async def test_version_link_is_authoritative_even_on_a_name_mismatch(self, monkeypatch):
        _no_matches(monkeypatch)
        _seam(
            monkeypatch,
            "_civitai_version_download_info",
            {
                "download_url": "https://civitai.com/api/download/models/555",
                "model_version_id": "555",
                "base_model": "SD 1.5",
            },
        )
        result = await res.resolve(WANTED, "loras", CIVITAI_LINK)
        assert result is not None
        assert result.platform == "civitai"
        assert result.source_id == "555"
        assert result.base_model == "SD 1.5"
        # The caller asked for this name; the file is stored under it.
        assert result.filename == WANTED
        assert result.model_type == "loras"

    async def test_deleted_version_falls_through(self, monkeypatch):
        _no_matches(monkeypatch)
        _seam(monkeypatch, "_civitai_version_download_info", None)
        # The link host is allowed, so the raw-URL fallback still applies.
        result = await res.resolve(WANTED, "loras", CIVITAI_LINK)
        assert result is not None
        assert result.platform == ""
        assert result.download_url == CIVITAI_LINK


class TestCivitaiModelLink:
    async def test_picks_the_version_holding_the_exact_filename(self, monkeypatch):
        _no_matches(monkeypatch)
        _seam(
            monkeypatch,
            "_civitai_model_versions",
            {
                "versions": [
                    _civitai_version([{"name": "other.safetensors", "downloadUrl": "u1"}], 1),
                    _civitai_version([{"name": WANTED, "downloadUrl": "u2"}], 2),
                ]
            },
        )
        result = await res.resolve(WANTED, "checkpoints", CIVITAI_MODEL_LINK)
        assert result is not None
        assert result.download_url == "u2"
        assert result.source_id == "2"


class TestHuggingFaceLink:
    async def test_exact_match_in_repo_files(self, monkeypatch):
        _no_matches(monkeypatch)
        _seam(
            monkeypatch,
            "_hf_model_files",
            [
                {"filename": "other.safetensors", "url": "u1"},
                {"filename": f"split_files/{WANTED}", "url": "u2"},
            ],
        )
        result = await res.resolve(WANTED, "text_encoders", HF_LINK)
        assert result is not None
        assert result.platform == "huggingface"
        assert result.source_id == "owner/repo"
        assert result.download_url == "u2"


class TestCivitaiSearch:
    async def test_exact_filename_hit(self, monkeypatch):
        _seam(
            monkeypatch,
            "_civitai_search",
            {
                "items": [
                    {"modelVersions": [_civitai_version([{"name": "nope.safetensors"}])]},
                    {
                        "modelVersions": [
                            _civitai_version([{"name": WANTED, "downloadUrl": "hit"}], 9)
                        ]
                    },
                ]
            },
        )
        result = await res.resolve(WANTED, "loras")
        assert result is not None
        assert result.download_url == "hit"
        assert result.source_id == "9"
        assert result.base_model == "SDXL 1.0"

    async def test_near_miss_name_is_rejected(self, monkeypatch):
        """A same-stem-different-name file must never be installed under the wanted name."""
        _seam(
            monkeypatch,
            "_civitai_search",
            {"items": [{"modelVersions": [_civitai_version([{"name": "wanted_v2.safetensors"}])]}]},
        )
        _seam(monkeypatch, "_hf_search", {"items": []})
        assert await res.resolve(WANTED, "loras") is None

    async def test_search_uses_the_filename_stem(self, monkeypatch):
        calls = _seam(monkeypatch, "_civitai_search", {"items": []})
        _seam(monkeypatch, "_hf_search", {"items": []})
        await res.resolve("My_Lora.safetensors", "loras")
        assert calls == [("My_Lora", "loras")]

    async def test_provider_outage_falls_through_instead_of_raising(self, monkeypatch):
        _seam(monkeypatch, "_civitai_search", httpx.HTTPError("boom"))
        _seam(monkeypatch, "_hf_search", {"items": [{"id": "owner/repo"}]})
        _seam(monkeypatch, "_hf_model_files", [{"filename": WANTED, "url": "hf"}])
        result = await res.resolve(WANTED, "loras")
        assert result is not None
        assert result.download_url == "hf"


class TestHuggingFaceSearch:
    async def test_scans_candidate_repos_until_a_match(self, monkeypatch):
        _seam(monkeypatch, "_civitai_search", {"items": []})
        _seam(monkeypatch, "_hf_search", {"items": [{"id": "a/one"}, {"id": "b/two"}]})

        async def files(repo_id):
            return [{"filename": WANTED, "url": "hit"}] if repo_id == "b/two" else []

        monkeypatch.setattr(res, "_hf_model_files", files)
        result = await res.resolve(WANTED, "loras")
        assert result is not None
        assert result.source_id == "b/two"

    async def test_candidate_repos_are_capped(self, monkeypatch):
        _seam(monkeypatch, "_civitai_search", {"items": []})
        overflow = [{"id": f"o/{i}"} for i in range(12)]
        _seam(monkeypatch, "_hf_search", {"items": overflow})
        inspected = _seam(monkeypatch, "_hf_model_files", [])
        assert await res.resolve(WANTED, "loras") is None
        assert len(inspected) == res._HF_MAX_CANDIDATE_REPOS


class TestRawFallback:
    async def test_allowed_url_is_used_without_metadata(self, monkeypatch):
        _no_matches(monkeypatch)
        _seam(monkeypatch, "_hf_model_files", [])
        url = "https://huggingface.co/owner/repo/resolve/main/wanted.safetensors"
        result = await res.resolve(WANTED, "vae", url)
        assert result is not None
        assert result.download_url == url
        assert result.platform == ""
        assert result.source_id == ""

    async def test_disallowed_host_is_not_used(self, monkeypatch):
        _no_matches(monkeypatch)
        assert await res.resolve(WANTED, "vae", "http://169.254.169.254/model.safetensors") is None

    async def test_no_url_and_no_provider_match_is_unresolved(self, monkeypatch):
        _no_matches(monkeypatch)
        assert await res.resolve(WANTED, "vae") is None


@pytest.mark.parametrize(
    ("candidate", "expected"),
    [
        (WANTED, True),
        (WANTED.upper(), True),
        ("nested/dir/" + WANTED, True),
        ("wanted.ckpt", False),
        ("", False),
    ],
)
def test_same_file(candidate, expected):
    assert res._same_file(candidate, WANTED) is expected


class TestBlobUrlNormalisation:
    """A HuggingFace `/blob/` URL is an HTML page, not the file (F-144 follow-up).

    Workflows and ComfyUI's own "copy URL" button both hand out the browsable `/blob/` form.
    Downloading it verbatim would silently store an HTML page under a `.safetensors` name.
    """

    BLOB = "https://huggingface.co/Lightricks/LTX-2.3-fp8/blob/main/ltx-2.3-22b-dev-fp8.safetensors"
    RESOLVE = (
        "https://huggingface.co/Lightricks/LTX-2.3-fp8/resolve/main/ltx-2.3-22b-dev-fp8.safetensors"
    )

    async def test_raw_fallback_rewrites_blob_to_resolve(self, monkeypatch):
        _no_matches(monkeypatch)
        _seam(monkeypatch, "_hf_model_files", [])
        result = await res.resolve(WANTED, "diffusion_models", self.BLOB)
        assert result is not None
        assert result.download_url == self.RESOLVE

    async def test_a_resolve_url_is_left_alone(self, monkeypatch):
        _no_matches(monkeypatch)
        _seam(monkeypatch, "_hf_model_files", [])
        result = await res.resolve(WANTED, "diffusion_models", self.RESOLVE)
        assert result is not None
        assert result.download_url == self.RESOLVE

    @pytest.mark.parametrize(
        "url",
        [
            "https://civitai.com/api/download/models/555",
            "https://huggingface.co/owner/repo/resolve/main/a.safetensors",
        ],
    )
    async def test_non_blob_urls_are_untouched(self, monkeypatch, url):
        _no_matches(monkeypatch)
        _seam(monkeypatch, "_hf_model_files", [])
        _seam(monkeypatch, "_civitai_version_download_info", None)
        result = await res.resolve(WANTED, "vae", url)
        assert result is not None
        assert result.download_url == url


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        (
            "https://huggingface.co/o/r/blob/main/a.safetensors",
            "https://huggingface.co/o/r/resolve/main/a.safetensors",
        ),
        # Only the viewer segment right after host/owner/repo is rewritten.
        (
            "https://huggingface.co/o/r/resolve/main/blob/a.safetensors",
            "https://huggingface.co/o/r/resolve/main/blob/a.safetensors",
        ),
        ("https://civitai.com/api/download/models/1", "https://civitai.com/api/download/models/1"),
        ("", ""),
    ],
)
def test_direct_download_url(url, expected):
    assert res.direct_download_url(url) == expected
