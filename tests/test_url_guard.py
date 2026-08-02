"""Unit tests for py/services/url_guard.py — SSRF host allowlist and redirect guard."""

import httpx
import pytest

from py.services.url_guard import RedirectNotAllowed, guarded_stream, is_allowed_url


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


def _chain_transport(hops: dict[str, str], seen: list[httpx.Request] | None = None):
    """MockTransport that 302s along ``hops`` (url -> location) and 200s otherwise."""

    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(request)
        location = hops.get(str(request.url))
        if location:
            return httpx.Response(302, headers={"location": location})
        return httpx.Response(200, content=b"payload")

    return httpx.MockTransport(handler)


async def _read(client, url, headers=None):
    async with guarded_stream(client, "GET", url, headers=headers) as resp:
        return await resp.aread()


class TestGuardedStream:
    async def test_returns_the_response_when_there_is_no_redirect(self):
        async with httpx.AsyncClient(transport=_chain_transport({})) as client:
            assert await _read(client, "https://civitai.com/api/download/models/1") == b"payload"

    async def test_follows_a_redirect_that_stays_inside_the_allowlist(self):
        # The real CivitAI chain: civitai.com -> b2.civitai.com.
        hops = {"https://civitai.com/api/download/models/1": "https://b2.civitai.com/file/x.zip"}
        seen: list[httpx.Request] = []
        async with httpx.AsyncClient(transport=_chain_transport(hops, seen)) as client:
            assert await _read(client, "https://civitai.com/api/download/models/1") == b"payload"
        assert [str(r.url) for r in seen] == [
            "https://civitai.com/api/download/models/1",
            "https://b2.civitai.com/file/x.zip",
        ]

    async def test_follows_the_real_huggingface_cdn_hop(self):
        hops = {"https://huggingface.co/a/b/resolve/main/m.st": "https://us.aws.cdn.hf.co/xet/abc"}
        async with httpx.AsyncClient(transport=_chain_transport(hops)) as client:
            assert await _read(client, "https://huggingface.co/a/b/resolve/main/m.st") == b"payload"

    @pytest.mark.parametrize(
        "target",
        [
            "http://169.254.169.254/latest/meta-data/",
            "http://127.0.0.1:8188/internal",
            "https://evil.com/payload",
            "https://civitai.com.evil.com/x",
        ],
    )
    async def test_rejects_a_redirect_that_leaves_the_allowlist(self, target):
        """A trusted host must not be able to bounce the fetch onto an internal address."""
        hops = {"https://civitai.com/api/download/models/1": target}
        seen: list[httpx.Request] = []
        async with httpx.AsyncClient(transport=_chain_transport(hops, seen)) as client:
            with pytest.raises(RedirectNotAllowed):
                await _read(client, "https://civitai.com/api/download/models/1")
        # The blocked hop was never requested.
        assert [str(r.url) for r in seen] == ["https://civitai.com/api/download/models/1"]

    async def test_rejects_a_relative_redirect_that_escapes_via_the_next_hop(self):
        hops = {
            "https://civitai.com/a": "/b",
            "https://civitai.com/b": "https://evil.com/c",
        }
        async with httpx.AsyncClient(transport=_chain_transport(hops)) as client:
            with pytest.raises(RedirectNotAllowed):
                await _read(client, "https://civitai.com/a")

    async def test_resolves_relative_redirects_against_the_current_hop(self):
        hops = {"https://civitai.com/a/b": "../c/file.zip"}
        seen: list[httpx.Request] = []
        async with httpx.AsyncClient(transport=_chain_transport(hops, seen)) as client:
            assert await _read(client, "https://civitai.com/a/b") == b"payload"
        assert str(seen[-1].url) == "https://civitai.com/c/file.zip"

    async def test_rejects_a_chain_longer_than_the_hop_cap(self):
        hops = {f"https://civitai.com/{i}": f"https://civitai.com/{i + 1}" for i in range(20)}
        async with httpx.AsyncClient(transport=_chain_transport(hops)) as client:
            with pytest.raises(RedirectNotAllowed, match="Too many redirects"):
                await _read(client, "https://civitai.com/0")

    async def test_drops_authorization_on_a_cross_origin_hop(self):
        """Following redirects by hand disables httpx's own stripping — reproduce it.

        Both providers hand out pre-signed CDN URLs, so the key is only ever needed on
        the first hop; replaying it to the CDN host would leak the CivitAI API key.
        """
        hops = {"https://civitai.com/api/download/models/1": "https://b2.civitai.com/file/x.zip"}
        seen: list[httpx.Request] = []
        async with httpx.AsyncClient(transport=_chain_transport(hops, seen)) as client:
            await _read(
                client, "https://civitai.com/api/download/models/1", {"Authorization": "Bearer k"}
            )
        assert seen[0].headers.get("authorization") == "Bearer k"
        assert "authorization" not in seen[1].headers

    async def test_keeps_authorization_on_a_same_origin_hop(self):
        hops = {"https://civitai.com/a": "https://civitai.com/b"}
        seen: list[httpx.Request] = []
        async with httpx.AsyncClient(transport=_chain_transport(hops, seen)) as client:
            await _read(client, "https://civitai.com/a", {"Authorization": "Bearer k"})
        assert seen[1].headers.get("authorization") == "Bearer k"

    async def test_keeps_authorization_on_a_plain_https_upgrade(self):
        hops = {"http://civitai.com/a": "https://civitai.com/a"}
        seen: list[httpx.Request] = []
        async with httpx.AsyncClient(transport=_chain_transport(hops, seen)) as client:
            await _read(client, "http://civitai.com/a", {"Authorization": "Bearer k"})
        assert seen[1].headers.get("authorization") == "Bearer k"

    async def test_other_headers_survive_a_cross_origin_hop(self):
        hops = {"https://civitai.com/a": "https://b2.civitai.com/b"}
        seen: list[httpx.Request] = []
        async with httpx.AsyncClient(transport=_chain_transport(hops, seen)) as client:
            await _read(
                client, "https://civitai.com/a", {"User-Agent": "tmm", "Authorization": "k"}
            )
        assert seen[1].headers.get("user-agent") == "tmm"
        assert "authorization" not in seen[1].headers
