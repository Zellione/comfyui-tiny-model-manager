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
}

CIVITAI_REVERSE_TYPE_MAP = {v: k for k, v in CIVITAI_TYPE_MAP.items()}


class CivitaiProvider(ModelProvider):
    name = "civitai"

    def auth_headers(self) -> dict:
        key = cfg.load_settings().get("civitai_api_key", "")
        if key:
            return {"Authorization": f"Bearer {key}"}
        return {}

    async def search(self, query: str, model_type: str = "", page: int = 1, limit: int = 20,
                     cursor: str = "", base_model: str = "", sort: str = "", period: str = "", **kwargs) -> dict:
        params: dict = {"limit": limit}
        if query:
            params["query"] = query
            # CivitAI does not allow page with query; use cursor-based pagination instead
            if cursor:
                params["cursor"] = cursor
        else:
            params["page"] = page
        if model_type and model_type in CIVITAI_TYPE_MAP:
            params["types"] = CIVITAI_TYPE_MAP[model_type]
        if base_model:
            params["baseModels"] = base_model
        if sort:
            params["sort"] = sort
            if period:
                params["period"] = period
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(f"{_BASE}/models", params=params, headers=self.auth_headers())
            if not resp.is_success:
                raise httpx.HTTPStatusError(
                    f"{resp.status_code} {resp.reason_phrase}: {resp.text}",
                    request=resp.request,
                    response=resp,
                )
            return resp.json()

    async def get_model_versions(self, model_id: int) -> dict:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(f"{_BASE}/models/{model_id}", headers=self.auth_headers())
            if not resp.is_success:
                raise httpx.HTTPStatusError(
                    f"{resp.status_code} {resp.reason_phrase}: {resp.text}",
                    request=resp.request,
                    response=resp,
                )
            data = resp.json()
        civitai_type = data.get("type", "")
        return {
            "versions": data.get("modelVersions", []),
            "model_type": CIVITAI_REVERSE_TYPE_MAP.get(civitai_type, "checkpoints"),
        }

    async def resolve_direct_link(self, version_id: int) -> dict:
        """Resolves a CivitAI version ID to primary file info for direct download."""
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(f"{_BASE}/model-versions/{version_id}", headers=self.auth_headers())
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

    async def fetch_metadata(self, source_id: str) -> ProviderMetadata:
        """Returns description, trigger words, image URLs, tags, base model, and model ID for a version."""
        version_id = int(source_id)
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(f"{_BASE}/model-versions/{version_id}", headers=self.auth_headers())
            resp.raise_for_status()
            data = resp.json()
        image_urls = [img["url"] for img in data.get("images", [])[:5] if img.get("url")]
        description = data.get("description") or ""
        base_model = data.get("baseModel", "")
        tags: list[str] = []
        model_id = data.get("modelId")
        civitai_model_id = str(model_id) if model_id else ""
        if model_id:
            async with httpx.AsyncClient(timeout=15) as client:
                model_resp = await client.get(f"{_BASE}/models/{model_id}", headers=self.auth_headers())
                if model_resp.is_success:
                    model_data = model_resp.json()
                    description = description or model_data.get("description") or ""
                    tags = model_data.get("tags", [])
        return ProviderMetadata(
            description=description,
            trigger_words=data.get("trainedWords", []),
            image_urls=image_urls,
            tags=tags,
            base_model=base_model,
            civitai_model_id=civitai_model_id,
        )
