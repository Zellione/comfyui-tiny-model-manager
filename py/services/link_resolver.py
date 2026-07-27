"""Resolve a pasted CivitAI / HuggingFace model URL into registration metadata.

Used by ``POST /api/models/resolve-link`` so users can describe an on-disk model file by
pasting its source page URL when the CivitAI hash lookup finds nothing.

Only the provider hosts allowed by `url_guard` are accepted, and only the IDs extracted
from the URL are ever sent to a provider API — the pasted URL itself is never fetched.
"""

import re
from dataclasses import dataclass
from urllib.parse import parse_qs, urlparse

from .providers.civitai_provider import CivitaiProvider
from .providers.huggingface_provider import HuggingFaceProvider, validate_repo_id
from .url_guard import is_allowed_url

CIVITAI = "civitai"
HUGGINGFACE = "huggingface"

_CIVITAI_HOSTS = ("civitai.com", "civitai.red")
_HUGGINGFACE_HOSTS = ("huggingface.co", "hf.co")

_CIVITAI_MODEL_PATH = re.compile(r"^/models/(\d+)")
_CIVITAI_DOWNLOAD_PATH = re.compile(r"^/api/download/models/(\d+)")
_CIVITAI_VERSION_PATH = re.compile(r"^/model-versions/(\d+)")


@dataclass(frozen=True)
class ParsedLink:
    """A provider model reference extracted from a user-supplied URL."""

    platform: str
    model_id: str = ""
    version_id: str = ""
    repo_id: str = ""


def _host_matches(host: str, suffixes: tuple[str, ...]) -> bool:
    return any(host == suffix or host.endswith("." + suffix) for suffix in suffixes)


def _parse_civitai(path: str, query: str) -> ParsedLink | None:
    version_id = ""
    values = parse_qs(query).get("modelVersionId") or []
    if values and values[0].isdigit():
        version_id = values[0]

    match = _CIVITAI_MODEL_PATH.match(path)
    if match:
        return ParsedLink(platform=CIVITAI, model_id=match.group(1), version_id=version_id)

    for pattern in (_CIVITAI_DOWNLOAD_PATH, _CIVITAI_VERSION_PATH):
        match = pattern.match(path)
        if match:
            return ParsedLink(platform=CIVITAI, version_id=match.group(1))
    return None


def _parse_huggingface(path: str) -> ParsedLink | None:
    segments = [seg for seg in path.split("/") if seg]
    # Strip the sub-page suffix (/tree/main/..., /blob/main/file.safetensors, ...).
    for marker in ("tree", "blob", "resolve", "raw", "commit", "discussions"):
        if marker in segments:
            segments = segments[: segments.index(marker)]
            break
    if not segments or len(segments) > 2:
        return None
    repo_id = "/".join(segments)
    try:
        validate_repo_id(repo_id)
    except ValueError:
        return None
    return ParsedLink(platform=HUGGINGFACE, repo_id=repo_id)


def parse_model_link(url: str) -> ParsedLink | None:
    """Extract a provider model reference from ``url``; None if it is not a supported link."""
    if not is_allowed_url(url):
        return None
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    path = parsed.path.rstrip("/") or "/"
    if _host_matches(host, _CIVITAI_HOSTS):
        return _parse_civitai(path, parsed.query)
    if _host_matches(host, _HUGGINGFACE_HOSTS):
        return _parse_huggingface(path)
    return None


async def resolve(parsed: ParsedLink) -> dict | None:
    """Fetch registration metadata for a parsed link; None when the provider has no match."""
    if parsed.platform == HUGGINGFACE:
        return await HuggingFaceProvider().lookup_by_repo_id(parsed.repo_id)
    provider = CivitaiProvider()
    if parsed.model_id:
        return await provider.lookup_by_model_id(parsed.model_id, parsed.version_id)
    return await provider.lookup_by_version_id(parsed.version_id)
