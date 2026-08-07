"""Resolve a model that a workflow needs but that is not on disk (F-144).

ComfyUI's "Missing Models" panel knows a filename, a target directory and — only when the
workflow author embedded it — a download URL. This module turns that into something the
downloader can act on, preferring a provider match (which yields a full model card) over a
bare file.

Resolution order, exactly as specified in issue #144: CivitAI, then HuggingFace, then the
raw URL the panel supplied.

A provider hit is accepted **only on an exact filename match**. Taking the top-ranked search
result instead would silently install a different model under the requested name; when nothing
matches exactly the caller is told so and offers the user a dashboard search instead.

Security: the panel-supplied URL is never fetched here. It is parsed for provider IDs
(`link_resolver.parse_model_link`, itself gated on `url_guard.is_allowed_url`) and, when it is
used as the last-resort download source, re-checked with `is_allowed_url` before it reaches the
downloader — which streams it through `url_guard.guarded_stream`.
"""

import logging
import os
import re
from dataclasses import dataclass

import httpx

from . import link_resolver
from .providers import civitai, huggingface
from .url_guard import is_allowed_url

logger = logging.getLogger(__name__)

# Bounds the HuggingFace fallback: search returns a ranked list and each candidate repo costs
# one further request to list its files. Five keeps the worst case affordable while still
# covering the mirrors and re-uploads that make up most HuggingFace name collisions.
_HF_MAX_CANDIDATE_REPOS = 5
_CIVITAI_SEARCH_LIMIT = 10

# Only the `/blob/` that directly follows `host/owner/repo` is the viewer segment; a repo or a
# path component merely named "blob" further along must not be rewritten.
_HF_BLOB_PATH = re.compile(r"^(https?://[^/]+/[^/]+/[^/]+)/blob/")


@dataclass(frozen=True)
class Resolution:
    """Everything the downloader needs for one missing model."""

    download_url: str
    filename: str
    model_type: str
    platform: str = ""
    source_id: str = ""
    base_model: str = ""


# --- Patchable provider seams -------------------------------------------------------------
# Project convention: every outbound call is wrapped in a module-level coroutine so tests
# monkeypatch this module's attribute rather than httpx.


async def _civitai_search(query: str, model_type: str) -> dict:
    return await civitai.search(query, model_type, limit=_CIVITAI_SEARCH_LIMIT)


async def _civitai_model_versions(model_id: str) -> dict:
    return await civitai.get_model_versions(int(model_id))


async def _civitai_version_download_info(version_id: str) -> dict | None:
    return await civitai.version_download_info(version_id)


async def _hf_search(query: str, model_type: str) -> dict:
    return await huggingface.search(query, model_type, limit=_HF_MAX_CANDIDATE_REPOS)


async def _hf_model_files(repo_id: str) -> list[dict]:
    return await huggingface.get_model_files(repo_id)


# --- Matching helpers ---------------------------------------------------------------------


def _same_file(candidate: str, wanted: str) -> bool:
    """Exact filename match, ignoring any repo subfolder prefix and letter case."""
    return bool(candidate) and os.path.basename(candidate).lower() == wanted.lower()


def direct_download_url(url: str) -> str:
    """Rewrite a HuggingFace `/blob/` link to its `/resolve/` counterpart.

    `/blob/` serves the repository's HTML file-viewer page, not the file. Workflows and
    ComfyUI's own "copy URL" button both hand out that browsable form, so taking it verbatim
    would store a web page under a `.safetensors` name — a corrupt model that only fails at
    load time. Provider-resolved downloads never go through here; this guards the raw fallback.
    """
    return _HF_BLOB_PATH.sub(r"\1/resolve/", url, count=1)


def search_term(filename: str) -> str:
    """The query used for provider search and for the dashboard "Search in TMM" deep link."""
    return os.path.splitext(os.path.basename(filename))[0]


def _civitai_file_match(files: list[dict], filename: str) -> dict | None:
    return next((f for f in files if _same_file(f.get("name", ""), filename)), None)


def _from_civitai_version(version: dict, file: dict, filename: str, model_type: str) -> Resolution:
    return Resolution(
        download_url=file.get("downloadUrl", ""),
        filename=filename,
        model_type=model_type,
        platform=link_resolver.CIVITAI,
        source_id=str(version.get("id") or ""),
        base_model=version.get("baseModel", "") or "",
    )


# --- Resolution stages --------------------------------------------------------------------


async def _from_civitai_version_link(version_id: str, filename: str, model_type: str):
    """A version link is authoritative: its primary file is taken even if the name differs.

    The workflow author pointed at that exact version, so second-guessing the name here would
    reject legitimate renames (CivitAI hands out ``model_v2.safetensors`` for a file a workflow
    calls ``model.safetensors`` often enough to matter).
    """
    info = await _civitai_version_download_info(version_id)
    if not info or not info.get("download_url"):
        return None
    return Resolution(
        download_url=info["download_url"],
        filename=filename,
        model_type=model_type,
        platform=link_resolver.CIVITAI,
        source_id=str(info.get("model_version_id") or version_id),
        base_model=info.get("base_model", ""),
    )


async def _from_civitai_model_link(model_id: str, filename: str, model_type: str):
    payload = await _civitai_model_versions(model_id)
    for version in payload.get("versions") or []:
        file = _civitai_file_match(version.get("files") or [], filename)
        if file:
            return _from_civitai_version(version, file, filename, model_type)
    return None


async def _from_hf_repo(repo_id: str, filename: str, model_type: str):
    for file in await _hf_model_files(repo_id):
        if _same_file(file.get("filename", ""), filename):
            return Resolution(
                download_url=file.get("url", ""),
                filename=filename,
                model_type=model_type,
                platform=link_resolver.HUGGINGFACE,
                source_id=repo_id,
            )
    return None


async def _from_link(url: str, filename: str, model_type: str):
    """Stage 1 — use the IDs embedded in the URL the panel supplied."""
    parsed = link_resolver.parse_model_link(url)
    if parsed is None:
        return None
    if parsed.platform == link_resolver.HUGGINGFACE:
        return await _from_hf_repo(parsed.repo_id, filename, model_type)
    if parsed.model_id:
        return await _from_civitai_model_link(parsed.model_id, filename, model_type)
    return await _from_civitai_version_link(parsed.version_id, filename, model_type)


async def _from_civitai_search(filename: str, model_type: str):
    """Stage 2 — one CivitAI search; the payload already carries every version's file list."""
    payload = await _civitai_search(search_term(filename), model_type)
    for item in payload.get("items") or []:
        for version in item.get("modelVersions") or []:
            file = _civitai_file_match(version.get("files") or [], filename)
            if file:
                return _from_civitai_version(version, file, filename, model_type)
    return None


async def _from_hf_search(filename: str, model_type: str):
    """Stage 3 — search, then list files for at most `_HF_MAX_CANDIDATE_REPOS` repos."""
    payload = await _hf_search(search_term(filename), model_type)
    items = payload.get("items") or []
    if len(items) > _HF_MAX_CANDIDATE_REPOS:
        logger.info(
            "HuggingFace returned %d candidates for %s; only the first %d are inspected",
            len(items),
            filename,
            _HF_MAX_CANDIDATE_REPOS,
        )
    for item in items[:_HF_MAX_CANDIDATE_REPOS]:
        repo_id = item.get("id") or ""
        if not repo_id:
            continue
        match = await _from_hf_repo(repo_id, filename, model_type)
        if match:
            return match
    return None


async def _try(stage, *args) -> Resolution | None:
    """Run one stage, treating a provider outage as "no match" rather than a failed request."""
    try:
        return await stage(*args)
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("Missing-model resolution stage %s failed: %s", stage.__name__, exc)
        return None


async def resolve(filename: str, model_type: str, url: str = "") -> Resolution | None:
    """Resolve one missing model, or None when no source could be established."""
    if url:
        resolution = await _try(_from_link, url, filename, model_type)
        if resolution:
            return resolution

    for stage in (_from_civitai_search, _from_hf_search):
        resolution = await _try(stage, filename, model_type)
        if resolution:
            return resolution

    # Last resort: the raw URL from the workflow. No provider metadata, so the download
    # produces a plain file — the behaviour issue #144 specifies for this branch.
    if url and is_allowed_url(url):
        return Resolution(
            download_url=direct_download_url(url), filename=filename, model_type=model_type
        )
    return None
