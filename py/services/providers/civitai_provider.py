import httpx

from ... import config as cfg
from .base import ModelProvider, ProviderMetadata

_BASE = "https://civitai.com/api/v1"

CIVITAI_TYPE_MAP = {
    "checkpoints": "Checkpoint",
    "loras": "LORA",
    "embeddings": "TextualInversion",
    "vae": "VAE",
    "controlnet": "Controlnet",
    "upscale_models": "Upscaler",
    "hypernetworks": "Hypernetwork",
}

CIVITAI_REVERSE_TYPE_MAP = {
    **{v: k for k, v in CIVITAI_TYPE_MAP.items()},
    # Extra CivitAI model types that map to an internal type but are not valid
    # search-filter values (not in CIVITAI_TYPE_MAP to keep that map 1-to-1).
    "LoCon": "loras",
    "DoRA": "loras",
    "MotionModule": "loras",
    "AestheticGradient": "embeddings",
}


_VERSION_NOTES_SEPARATOR = "<hr><h3>Version notes</h3>"


def _compose_description(model_description: str, version_description: str) -> str:
    """Join the model-page description with the version changelog below it.

    CivitAI's ``description`` on a model version is the version changelog, not the model
    description — they are different texts and both are worth keeping. Either side may be
    missing, in which case the other is used on its own.
    """
    model_description = (model_description or "").strip()
    version_description = (version_description or "").strip()
    if not model_description:
        return version_description
    if not version_description:
        return model_description
    return f"{model_description}{_VERSION_NOTES_SEPARATOR}{version_description}"


def _version_to_metadata(data: dict) -> dict:
    """Flatten a CivitAI model-version response into the registration metadata shape.

    Shared by every lookup entry point (hash, version ID, model page) so the API and the
    frontend only ever see one dict shape.
    """
    model = data.get("model") or {}
    images = data.get("images") or []
    thumbnail = next((img.get("url", "") for img in images if img.get("url")), "")
    return {
        "name": model.get("name", ""),
        "base_model": data.get("baseModel", ""),
        "description": _compose_description(
            model.get("description") or "", data.get("description") or ""
        ),
        "tags": model.get("tags") or [],
        "trigger_words": data.get("trainedWords") or [],
        "version_name": data.get("name", ""),
        "civitai_version_id": str(data.get("id") or ""),
        "civitai_model_id": str(data.get("modelId") or ""),
        "model_type": CIVITAI_REVERSE_TYPE_MAP.get(model.get("type", ""), "checkpoints"),
        "thumbnail": thumbnail,
    }


class CivitaiProvider(ModelProvider):
    name = "civitai"

    def auth_headers(self) -> dict:
        key = cfg.load_settings().get("civitai_api_key", "")
        if key:
            return {"Authorization": f"Bearer {key}"}
        return {}

    async def search(
        self,
        query: str,
        model_type: str = "",
        page: int = 1,
        limit: int = 20,
        cursor: str = "",
        base_model: str = "",
        sort: str = "",
        period: str = "",
        tags: list[str] | None = None,
        types: str = "",
        **kwargs,
    ) -> dict:
        params: dict = {"limit": limit}
        if query:
            params["query"] = query
        if cursor:
            params["cursor"] = cursor
        elif not query:
            params["page"] = page
        # ``types`` is the raw CivitAI filter value and wins over the internal
        # model_type mapping. It exists for CivitAI types that have no model folder of
        # ours — "Workflows" (F-129) — which therefore must stay out of CIVITAI_TYPE_MAP,
        # since that map also feeds CIVITAI_REVERSE_TYPE_MAP and the register form.
        if types:
            params["types"] = types
        elif model_type and model_type in CIVITAI_TYPE_MAP:
            params["types"] = CIVITAI_TYPE_MAP[model_type]
        if base_model:
            params["baseModels"] = base_model
        if sort:
            params["sort"] = sort
            if period:
                params["period"] = period
        if tags:
            params["tag"] = tags[0]
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(f"{_BASE}/models", params=params, headers=self.auth_headers())
            if not resp.is_success:
                raise httpx.HTTPStatusError(
                    f"{resp.status_code} {resp.reason_phrase}: {resp.text}",
                    request=resp.request,
                    response=resp,
                )
            return resp.json()

    async def get_model_page(self, model_id: int) -> dict:
        """Raw CivitAI model-page payload: model-level metadata plus every version.

        Callers that need the files of a non-Model type (workflow archives, F-129) use
        this: resolve_direct_link and get_version_files both filter on ``type == "Model"``
        and would return nothing for them.
        """
        safe_id = int(model_id)
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(f"{_BASE}/models/{safe_id}", headers=self.auth_headers())
            if not resp.is_success:
                raise httpx.HTTPStatusError(
                    f"{resp.status_code} {resp.reason_phrase}: {resp.text}",
                    request=resp.request,
                    response=resp,
                )
            return resp.json()

    async def get_model_versions(self, model_id: int) -> dict:
        data = await self.get_model_page(model_id)
        civitai_type = data.get("type", "")
        return {
            "versions": data.get("modelVersions", []),
            "model_type": CIVITAI_REVERSE_TYPE_MAP.get(civitai_type, "checkpoints"),
        }

    async def resolve_direct_link(self, version_id: int) -> dict:
        """Resolves a CivitAI version ID to primary file info for direct download."""
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                f"{_BASE}/model-versions/{version_id}", headers=self.auth_headers()
            )
            resp.raise_for_status()
            data = resp.json()
        files = data.get("files", [])
        primary = (
            next((f for f in files if f.get("primary") and f.get("type") == "Model"), None)
            or next((f for f in files if f.get("type") == "Model"), None)
            or (files[0] if files else None)
        )
        if not primary:
            raise ValueError("No downloadable file found for this version")
        civitai_type = data.get("model", {}).get("type", "")
        image_urls = [img["url"] for img in data.get("images", [])[:5] if img.get("url")]
        return {
            "filename": primary["name"],
            "model_type": CIVITAI_REVERSE_TYPE_MAP.get(civitai_type, "checkpoints"),
            "size_kb": primary.get("sizeKB", 0),
            "image_urls": image_urls,
        }

    async def get_version_files(self, version_id: int) -> list[dict]:
        """Returns all files in a CivitAI model version for repo-files storage."""
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                f"{_BASE}/model-versions/{version_id}", headers=self.auth_headers()
            )
            resp.raise_for_status()
            data = resp.json()
        model_id = data.get("modelId")
        source_page_url = f"https://civitai.com/models/{model_id}" if model_id else ""
        version_name = data.get("name", "")
        result = []
        for f in data.get("files", []):
            if f.get("type") != "Model":
                continue
            result.append(
                {
                    "filename": f.get("name", ""),
                    "size_bytes": int(f.get("sizeKB", 0) * 1024),
                    "download_url": f.get("downloadUrl", ""),
                    "source_page_url": source_page_url,
                    "civitai_version_name": version_name,
                }
            )
        return result

    async def _fetch_model_page(self, model_id) -> dict:
        """Fetch the parent model page; returns ``{}`` when it is missing or unreachable.

        The model-version endpoints embed only ``{name, type, nsfw, poi}`` for the parent
        model — description and tags live on the model page and need a second request.
        """
        if not model_id:
            return {}
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(f"{_BASE}/models/{model_id}", headers=self.auth_headers())
        return resp.json() if resp.is_success else {}

    async def _enrich_version(self, data: dict) -> dict:
        """Flatten a version response after splicing in its model page's description and tags."""
        model_page = await self._fetch_model_page(data.get("modelId"))
        if not model_page:
            return _version_to_metadata(data)
        model = data.get("model") or {}
        merged = {
            **data,
            "model": {
                **model,
                "description": model_page.get("description") or "",
                "tags": model_page.get("tags") or model.get("tags") or [],
            },
        }
        return _version_to_metadata(merged)

    async def fetch_metadata(self, source_id: str) -> ProviderMetadata:
        """Returns description, trigger words, image URLs, tags, base model, and model ID for a version."""
        version_id = int(source_id)
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                f"{_BASE}/model-versions/{version_id}", headers=self.auth_headers()
            )
            resp.raise_for_status()
            data = resp.json()
        image_urls = [img["url"] for img in data.get("images", [])[:5] if img.get("url")]
        model_id = data.get("modelId")
        model_data = await self._fetch_model_page(model_id)
        return ProviderMetadata(
            description=_compose_description(
                model_data.get("description") or "", data.get("description") or ""
            ),
            trigger_words=data.get("trainedWords", []),
            image_urls=image_urls,
            tags=model_data.get("tags", []),
            base_model=data.get("baseModel", ""),
            civitai_model_id=str(model_id) if model_id else "",
            civitai_version_name=data.get("name", ""),
            display_name=model_data.get("name", ""),
        )

    async def lookup_by_hash(self, sha256: str) -> dict | None:
        """Look up a model version by SHA-256 hash. Returns None if not found on CivitAI."""
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                f"{_BASE}/model-versions/by-hash/{sha256}",
                headers=self.auth_headers(),
            )
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            data = resp.json()
        return await self._enrich_version(data)

    async def lookup_by_version_id(self, version_id: str | int) -> dict | None:
        """Look up a model version by its CivitAI version ID. Returns None if not found."""
        safe_id = int(version_id)
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                f"{_BASE}/model-versions/{safe_id}", headers=self.auth_headers()
            )
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            data = resp.json()
        return await self._enrich_version(data)

    async def lookup_by_model_id(self, model_id: str | int, version_id: str = "") -> dict | None:
        """Look up a model page by its CivitAI model ID.

        ``version_id`` selects a specific version; without it the first (newest) version
        of the model is used. Returns None if the model is unknown or has no versions.
        """
        safe_id = int(model_id)
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(f"{_BASE}/models/{safe_id}", headers=self.auth_headers())
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            data = resp.json()
        versions = data.get("modelVersions") or []
        if not versions:
            return None
        version = versions[0]
        if version_id:
            version = next((v for v in versions if str(v.get("id")) == version_id), version)
        # The versions embedded in a model response carry no back-reference to their
        # parent, so splice in the model-level fields _version_to_metadata expects.
        merged = {
            **version,
            "modelId": data.get("id", safe_id),
            "model": {
                "name": data.get("name", ""),
                "tags": data.get("tags") or [],
                "type": data.get("type", ""),
                "description": data.get("description") or "",
            },
        }
        return _version_to_metadata(merged)
