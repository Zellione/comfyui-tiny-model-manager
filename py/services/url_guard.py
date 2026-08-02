"""SSRF guard for server-side URL fetches.

The backend fetches model files and gallery media from client-supplied URLs.
On an exposed ComfyUI instance an unrestricted fetch is an SSRF primitive
(e.g. against ``169.254.169.254`` or other loopback/link-local services).

We allow only the providers we integrate with, and the allowlist is enforced on
**every hop**, not just the initial URL: ``guarded_stream`` follows redirects
manually and re-checks each ``Location`` before issuing the next request, so a
trusted host cannot bounce a fetch onto an internal address.

Both providers do redirect their downloads, and both land inside the allowlist
(``civitai.com`` → ``b2.civitai.com``; ``huggingface.co`` → ``us.aws.cdn.hf.co``).
If a provider ever moves its CDN to a host outside these suffixes, downloads will
fail with ``RedirectNotAllowed`` naming the blocked host — add the suffix here
rather than relaxing the per-hop check.
"""

from contextlib import asynccontextmanager
from urllib.parse import urlparse

import httpx

# Host suffixes we trust. A host matches when it equals the suffix or is a
# subdomain of it (``image.civitai.com`` matches ``civitai.com``).
_ALLOWED_HOST_SUFFIXES = (
    "huggingface.co",
    "hf.co",
    "civitai.com",
    "civitai.red",
)

_MAX_REDIRECTS = 5
_DEFAULT_PORTS = {"http": 80, "https": 443}


class RedirectNotAllowed(Exception):
    """A redirect pointed outside the provider allowlist, or the chain was too long."""


def is_allowed_url(url: str) -> bool:
    """True if ``url`` is an http(s) URL on a trusted provider host."""
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    if parsed.scheme not in ("http", "https"):
        return False
    host = (parsed.hostname or "").lower()
    if not host:
        return False
    return any(host == suffix or host.endswith("." + suffix) for suffix in _ALLOWED_HOST_SUFFIXES)


def _port(url: httpx.URL) -> int | None:
    return url.port if url.port is not None else _DEFAULT_PORTS.get(url.scheme)


def _same_origin(a: httpx.URL, b: httpx.URL) -> bool:
    return a.scheme == b.scheme and a.host == b.host and _port(a) == _port(b)


def _is_https_upgrade(source: httpx.URL, target: httpx.URL) -> bool:
    """True for a plain http → https redirect on the same host and default ports."""
    return (
        source.host == target.host
        and source.scheme == "http"
        and _port(source) == 80
        and target.scheme == "https"
        and _port(target) == 443
    )


def _redirect_headers(headers: dict, source: httpx.URL, target: httpx.URL) -> dict:
    """Headers for the next hop, dropping credentials when the origin changes.

    Following redirects by hand means httpx's own ``Authorization`` stripping no
    longer applies, so it is reproduced here — otherwise the CivitAI API key would
    be replayed to whatever host a redirect names. Both providers hand out
    pre-signed CDN URLs, so nothing needs the header after the first hop.
    """
    if _same_origin(source, target) or _is_https_upgrade(source, target):
        return dict(headers)
    return {k: v for k, v in headers.items() if k.lower() != "authorization"}


@asynccontextmanager
async def guarded_stream(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    *,
    headers: dict | None = None,
    max_redirects: int = _MAX_REDIRECTS,
):
    """Stream ``url``, validating every redirect hop against the allowlist.

    Yields the final (already streaming) response. The caller is responsible for
    ``raise_for_status``; the response is closed on exit.

    ``client`` must not be configured with ``follow_redirects=True`` — redirects
    are resolved here so each hop can be checked.
    """
    current = httpx.URL(url)
    hop_headers = dict(headers or {})
    for _ in range(max_redirects + 1):
        request = client.build_request(method, current, headers=hop_headers)
        response = await client.send(request, stream=True, follow_redirects=False)
        if not response.is_redirect:
            try:
                yield response
            finally:
                await response.aclose()
            return
        target = current.join(response.headers.get("location", ""))
        await response.aclose()
        if not is_allowed_url(str(target)):
            raise RedirectNotAllowed(f"Redirect target host is not allowed: {target.host!r}")
        hop_headers = _redirect_headers(hop_headers, current, target)
        current = target
    raise RedirectNotAllowed(f"Too many redirects (>{max_redirects})")
