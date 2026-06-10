"""Unit tests for py/services/url_guard.py — SSRF host allowlist."""

import pytest

from py.services.url_guard import is_allowed_url


class TestAllowedHosts:
    @pytest.mark.parametrize(
        "url",
        [
            "https://huggingface.co/foo/bar/resolve/main/model.safetensors",
            "https://cdn-lfs.huggingface.co/repo/abc",
            "https://hf.co/foo/bar",
            "https://civitai.com/api/download/models/123",
            "https://image.civitai.com/xyz/width=450/img.jpeg",
            "https://civitai.red/api/download/models/123",
            "https://cdn.civitai.red/blob/abc",
        ],
    )
    def test_trusted_hosts_allowed(self, url):
        assert is_allowed_url(url) is True


class TestBlockedHosts:
    @pytest.mark.parametrize(
        "url",
        [
            "http://169.254.169.254/latest/meta-data/",
            "http://localhost:8188/internal",
            "http://127.0.0.1/secret",
            "https://evil.com/payload",
            "https://huggingface.co.evil.com/x",  # suffix-spoof must not match
            "https://notciviai.red/x",
            "file:///etc/passwd",
            "ftp://huggingface.co/x",
            "",
            "not a url",
        ],
    )
    def test_untrusted_or_malformed_blocked(self, url):
        assert is_allowed_url(url) is False
