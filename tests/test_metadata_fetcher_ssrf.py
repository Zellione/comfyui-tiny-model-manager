"""SSRF guard for server-side media downloads in metadata_fetcher."""

from unittest.mock import MagicMock, patch


class _AsyncCM:
    def __init__(self, value):
        self._value = value

    async def __aenter__(self):
        return self._value

    async def __aexit__(self, *_):
        return False


class TestMediaUrlAllowlist:
    async def test_disallowed_media_urls_are_not_fetched(self, ext_dir):
        from py.services import metadata_fetcher as mf

        requested: list[str] = []

        async def fake_get(url, *args, **kwargs):
            requested.append(url)
            resp = MagicMock()
            resp.raise_for_status = MagicMock()
            resp.headers = {"content-type": "image/jpeg"}
            resp.content = b"img"
            return resp

        mock_client = MagicMock()
        mock_client.get = fake_get

        urls = [
            "https://image.civitai.com/abc/img0.jpeg",  # allowed
            "http://169.254.169.254/latest/meta-data/",  # blocked
            "https://huggingface.co/u/r/resolve/main/img1.png",  # allowed
            "file:///etc/passwd",  # blocked
        ]

        with patch(
            "py.services.metadata_fetcher.httpx.AsyncClient", return_value=_AsyncCM(mock_client)
        ):
            results = await mf._iter_downloaded_urls("a" * 40, urls)

        assert requested == [
            "https://image.civitai.com/abc/img0.jpeg",
            "https://huggingface.co/u/r/resolve/main/img1.png",
        ]
        assert len(results) == 2
