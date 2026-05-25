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


class CivitaiProvider(ModelProvider):
    name = "civitai"

    def auth_headers(self) -> dict:
        key = cfg.load_settings().get("civitai_api_key", "")
        if key:
            return {"Authorization": f"Bearer {key}"}
        return {}

    async def search(self, query: str, model_type: str = "", page: int = 1, limit: int = 20, cursor: str = "", **kwargs) -> dict:
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
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(f"{_BASE}/models", params=params, headers=self.auth_headers())
            if not resp.is_success:
                raise httpx.HTTPStatusError(
                    f"{resp.status_code} {resp.reason_phrase}: {resp.text}",
                    request=resp.request,
                    response=resp,
                )
            return resp.json()

    async def get_model_versions(self, model_id: int) -> list:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(f"{_BASE}/models/{model_id}", headers=self.auth_headers())
            if not resp.is_success:
                raise httpx.HTTPStatusError(
                    f"{resp.status_code} {resp.reason_phrase}: {resp.text}",
                    request=resp.request,
                    response=resp,
                )
            data = resp.json()
            return data.get("modelVersions", [])

    async def fetch_metadata(self, source_id: str) -> ProviderMetadata:
        """Returns description, trigger words, and image URLs for a model version."""
        version_id = int(source_id)
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(f"{_BASE}/model-versions/{version_id}", headers=self.auth_headers())
            resp.raise_for_status()
            data = resp.json()
        image_urls = [img["url"] for img in data.get("images", [])[:5] if img.get("url")]
        # Version-level description is usually null; fetch model-level description instead
        description = data.get("description") or ""
        model_id = data.get("modelId")
        if model_id and not description:
            async with httpx.AsyncClient(timeout=15) as client:
                model_resp = await client.get(f"{_BASE}/models/{model_id}", headers=self.auth_headers())
                if model_resp.is_success:
                    description = model_resp.json().get("description") or ""
        return ProviderMetadata(
            description=description,
            trigger_words=data.get("trainedWords", []),
            image_urls=image_urls,
        )
