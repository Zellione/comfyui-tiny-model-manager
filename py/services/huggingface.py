import httpx
from .. import config as cfg

_BASE = "https://huggingface.co"
_API = "https://huggingface.co/api"

HF_TYPE_MAP = {
    "checkpoints": "text-to-image",
    "loras": "text-to-image",
    "embeddings": "text-to-image",
}

MODEL_EXTENSIONS = {".safetensors", ".ckpt", ".pt", ".bin", ".gguf"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}


def _headers() -> dict:
    settings = cfg.load_settings()
    token = settings.get("hf_token", "")
    if token:
        return {"Authorization": f"Bearer {token}"}
    return {}


async def search_models(query: str, model_type: str = "", limit: int = 20, p: int = 0) -> dict:
    params = {"search": query, "limit": limit, "sort": "downloads", "direction": -1, "p": p, "full": "true"}
    pipeline = HF_TYPE_MAP.get(model_type, "text-to-image")
    params["pipeline_tag"] = pipeline
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(f"{_API}/models", params=params, headers=_headers())
        resp.raise_for_status()
        data = resp.json()
    for model in data:
        repo_id = model.get("modelId") or model.get("id", "")
        thumbnail = ""
        for sibling in model.get("siblings", []):
            name = sibling.get("rfilename", "")
            ext = ("." + name.rsplit(".", 1)[-1].lower()) if "." in name else ""
            if ext in IMAGE_EXTENSIONS and "/" not in name:
                thumbnail = f"{_BASE}/{repo_id}/resolve/main/{name}"
                break
        model["thumbnail"] = thumbnail
    return {"items": data, "hasMore": len(data) == limit, "nextPage": p + 1}


async def get_model_files(repo_id: str) -> list[dict]:
    """Returns model files (.safetensors etc.) from a HuggingFace repo."""
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(f"{_API}/models/{repo_id}", params={"blobs": "true"}, headers=_headers())
        resp.raise_for_status()
        data = resp.json()
    siblings = data.get("siblings", [])
    result = []
    for f in siblings:
        name = f.get("rfilename", "")
        ext = "." + name.rsplit(".", 1)[-1] if "." in name else ""
        if ext in MODEL_EXTENSIONS:
            result.append({
                "filename": name,
                "size": f.get("size", 0),
                "url": f"{_BASE}/{repo_id}/resolve/main/{name}",
            })
    return result


async def get_model_card(repo_id: str) -> dict:
    """Returns description, tags, and preview image URLs from a HuggingFace model card."""
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(f"{_API}/models/{repo_id}", headers=_headers())
        resp.raise_for_status()
        data = resp.json()
    image_urls = []
    for sibling in data.get("siblings", []):
        name = sibling.get("rfilename", "")
        ext = ("." + name.rsplit(".", 1)[-1].lower()) if "." in name else ""
        if ext in IMAGE_EXTENSIONS and "/" not in name:
            image_urls.append(f"{_BASE}/{repo_id}/resolve/main/{name}")
        if len(image_urls) >= 5:
            break
    return {
        "description": data.get("cardData", {}).get("description", ""),
        "trigger_words": data.get("cardData", {}).get("trigger", []),
        "tags": data.get("tags", []),
        "image_urls": image_urls,
    }
