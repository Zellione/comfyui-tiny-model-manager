"""SSRF guard for server-side URL fetches.

The backend fetches model files and gallery media from client-supplied URLs.
On an exposed ComfyUI instance an unrestricted fetch is an SSRF primitive
(e.g. against ``169.254.169.254`` or other loopback/link-local services).

We allow only the providers we integrate with. Matching the *initial* URL's
host against this suffix allowlist blocks attacker-controlled internal targets;
redirects from these trusted domains (HF/CivitAI CDNs) are accepted as the
intended download path.
"""

from urllib.parse import urlparse

# Host suffixes we trust. A host matches when it equals the suffix or is a
# subdomain of it (``image.civitai.com`` matches ``civitai.com``).
_ALLOWED_HOST_SUFFIXES = (
    "huggingface.co",
    "hf.co",
    "civitai.com",
    "civitai.red",
)


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
