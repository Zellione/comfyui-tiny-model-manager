"""SSRF guard for server-side media downloads in metadata_fetcher."""

from unittest.mock import patch

import httpx

# Captured before any patching: the tests below replace the *module* attribute
# httpx.AsyncClient, so the factory must not look it up by name or it recurses.
_REAL_ASYNC_CLIENT = httpx.AsyncClient


def _recording_client(requested: list[str], redirects: dict[str, str] | None = None):
    """Build a factory yielding a real AsyncClient over a request-recording transport.

    A real client (rather than a MagicMock) keeps guarded_stream's redirect handling in
    the code path under test, so the allowlist is exercised on every hop.
    """
    hops = redirects or {}

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(str(request.url))
        location = hops.get(str(request.url))
        if location:
            return httpx.Response(302, headers={"location": location})
        return httpx.Response(200, content=b"img", headers={"content-type": "image/jpeg"})

    def factory(**_kwargs):
        return _REAL_ASYNC_CLIENT(transport=httpx.MockTransport(handler))

    return factory


class TestMediaUrlAllowlist:
    async def test_disallowed_media_urls_are_not_fetched(self, ext_dir):
        from py.services import metadata_fetcher as mf

        requested: list[str] = []
        urls = [
            "https://image.civitai.com/abc/img0.jpeg",  # allowed
            "http://169.254.169.254/latest/meta-data/",  # blocked
            "https://huggingface.co/u/r/resolve/main/img1.png",  # allowed
            "file:///etc/passwd",  # blocked
        ]

        with patch("py.services.metadata_fetcher.httpx.AsyncClient", _recording_client(requested)):
            results = await mf._iter_downloaded_urls("a" * 40, urls)

        assert requested == [
            "https://image.civitai.com/abc/img0.jpeg",
            "https://huggingface.co/u/r/resolve/main/img1.png",
        ]
        assert len(results) == 2

    async def test_media_redirect_off_the_allowlist_drops_that_item(self, ext_dir):
        """A trusted CDN must not be able to bounce a preview fetch onto an internal host."""
        from py.services import metadata_fetcher as mf

        requested: list[str] = []
        redirects = {"https://image.civitai.com/abc/img0.jpeg": "http://169.254.169.254/meta-data/"}

        with patch(
            "py.services.metadata_fetcher.httpx.AsyncClient",
            _recording_client(requested, redirects),
        ):
            results = await mf._iter_downloaded_urls(
                "b" * 40,
                [
                    "https://image.civitai.com/abc/img0.jpeg",
                    "https://image.civitai.com/abc/img1.jpeg",
                ],
            )

        # The redirect target was never requested; the second, clean URL still succeeded.
        assert "http://169.254.169.254/meta-data/" not in requested
        assert len(results) == 1

    async def test_media_redirect_inside_the_allowlist_is_followed(self, ext_dir):
        from py.services import metadata_fetcher as mf

        requested: list[str] = []
        redirects = {"https://image.civitai.com/abc/img0.jpeg": "https://cdn.civitai.com/img0.jpeg"}

        with patch(
            "py.services.metadata_fetcher.httpx.AsyncClient",
            _recording_client(requested, redirects),
        ):
            results = await mf._iter_downloaded_urls(
                "c" * 40, ["https://image.civitai.com/abc/img0.jpeg"]
            )

        assert requested[-1] == "https://cdn.civitai.com/img0.jpeg"
        assert len(results) == 1
