import httpx
from .. import config as cfg

_BASE = "https://civitai.com/api/v1"

CIVITAI_TYPE_MAP = {
    "checkpoints": "Checkpoint",
    "loras": "LORA",
    "embeddings": "TextualInversion",
    "vae": "VAE",
    "controlnet": "Controlnet",
}


def _headers() -> dict:
    settings = cfg.load_settings()
    key = settings.get("civitai_api_key", "")
    if key:
        return {"Authorization": f"Bearer {key}"}
    return {}


async def search_models(query: str, model_type: str = "", page: int = 1, limit: int = 20, cursor: str = "") -> dict:
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
        resp = await client.get(f"{_BASE}/models", params=params, headers=_headers())
        if not resp.is_success:
            raise httpx.HTTPStatusError(
                f"{resp.status_code} {resp.reason_phrase}: {resp.text}",
                request=resp.request,
                response=resp,
            )
        return resp.json()


async def get_model_versions(model_id: int) -> list:
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(f"{_BASE}/models/{model_id}", headers=_headers())
        if not resp.is_success:
            raise httpx.HTTPStatusError(
                f"{resp.status_code} {resp.reason_phrase}: {resp.text}",
                request=resp.request,
                response=resp,
            )
        data = resp.json()
        return data.get("modelVersions", [])


async def get_model_metadata(model_id: int) -> dict:
    """Returns description and trigger words for a model."""
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(f"{_BASE}/models/{model_id}", headers=_headers())
        resp.raise_for_status()
        data = resp.json()
    versions = data.get("modelVersions", [])
    trigger_words = []
    if versions:
        trigger_words = versions[0].get("trainedWords", [])
    return {
        "description": data.get("description", ""),
        "trigger_words": trigger_words,
        "tags": data.get("tags", []),
    }


async def get_version_metadata(version_id: int) -> dict:
    """Returns description, trigger words, and image URLs for a specific model version."""
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(f"{_BASE}/model-versions/{version_id}", headers=_headers())
        resp.raise_for_status()
        data = resp.json()
    image_urls = [img["url"] for img in data.get("images", [])[:5] if img.get("url")]
    # Version-level description is usually null; fetch model-level description instead
    description = data.get("description") or ""
    model_id = data.get("modelId")
    if model_id and not description:
        async with httpx.AsyncClient(timeout=15) as client:
            model_resp = await client.get(f"{_BASE}/models/{model_id}", headers=_headers())
            if model_resp.is_success:
                description = model_resp.json().get("description") or ""
    return {
        "description": description,
        "trigger_words": data.get("trainedWords", []),
        "image_urls": image_urls,
    }


async def get_version_images(version_id: int, limit: int = 5) -> list[str]:
    """Returns up to `limit` image URLs for a model version."""
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            f"{_BASE}/images",
            params={"modelVersionId": version_id, "limit": limit},
            headers=_headers(),
        )
        resp.raise_for_status()
        data = resp.json()
    return [img["url"] for img in data.get("items", []) if img.get("url")]
