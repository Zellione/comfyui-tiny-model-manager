import httpx
import mistune

from ... import config as cfg
from .base import ModelProvider, ProviderMetadata

_BASE = "https://huggingface.co"
_API = "https://huggingface.co/api"

HF_TYPE_MAP = {
    "checkpoints": "text-to-image",
    "loras": "text-to-image",
    "embeddings": "text-to-image",
}

MODEL_EXTENSIONS = {".safetensors", ".ckpt", ".pt", ".bin", ".gguf"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}


def _file_ext(name: str) -> str:
    return ("." + name.rsplit(".", 1)[-1].lower()) if "." in name else ""


def _build_search_params(
    query: str,
    model_type: str,
    limit: int,
    p: int,
    sort: str,
    direction: int,
    file_format: str,
    tags: list[str] | None,
) -> dict:
    """Assemble the HuggingFace /models query params, honouring gguf and tag filters."""
    params: dict = {
        "search": query,
        "limit": limit,
        "sort": sort,
        "direction": direction,
        "p": p,
        "full": "true",
    }
    extra_tags = list(tags) if tags else []
    if file_format == ".gguf":
        filter_values = ["gguf"] + extra_tags
        params["filter"] = filter_values if len(filter_values) > 1 else filter_values[0]
    else:
        params["pipeline_tag"] = HF_TYPE_MAP.get(model_type, "text-to-image")
        if extra_tags:
            params["filter"] = extra_tags
    return params


def _image_urls_from_siblings(repo_id: str, data: dict, limit: int = 5) -> list[str]:
    """Collect up to ``limit`` ``resolve/main`` image URLs from a repo's siblings list."""
    image_urls: list[str] = []
    for sibling in data.get("siblings", []):
        name = sibling.get("rfilename", "")
        if _file_ext(name) in IMAGE_EXTENSIONS:
            image_urls.append(f"{_BASE}/{repo_id}/resolve/main/{name}")
        if len(image_urls) >= limit:
            break
    return image_urls


def _enrich_hf_model(model: dict) -> None:
    """Add thumbnail, images, formats and description fields to a raw HF model dict in place."""
    repo_id = model.get("modelId") or model.get("id", "")
    thumbnail = ""
    images: list[str] = []
    exts: set[str] = set()
    for sibling in model.get("siblings", []):
        name = sibling.get("rfilename", "")
        ext = _file_ext(name)
        if ext in IMAGE_EXTENSIONS:
            url = f"{_BASE}/{repo_id}/resolve/main/{name}"
            if not thumbnail:
                thumbnail = url
            if len(images) < 8:
                images.append(url)
        if ext in MODEL_EXTENSIONS:
            exts.add(ext)
    card_data = model.get("cardData") or {}
    model["thumbnail"] = thumbnail
    model["images"] = images
    model["formats"] = list(exts)
    model["description"] = card_data.get("description", "") or ""


class HuggingFaceProvider(ModelProvider):
    name = "huggingface"

    def auth_headers(self) -> dict:
        token = cfg.load_settings().get("hf_token", "")
        if token:
            return {"Authorization": f"Bearer {token}"}
        return {}

    async def search(
        self,
        query: str,
        model_type: str = "",
        limit: int = 20,
        p: int = 0,
        sort: str = "downloads",
        direction: int = -1,
        format: str = "",
        tags: list[str] | None = None,
        **kwargs,
    ) -> dict:
        params = _build_search_params(query, model_type, limit, p, sort, direction, format, tags)
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(f"{_API}/models", params=params, headers=self.auth_headers())
            resp.raise_for_status()
            data = resp.json()
        for model in data:
            _enrich_hf_model(model)
        return {"items": data, "hasMore": len(data) == limit, "nextPage": p + 1}

    async def get_model_files(self, repo_id: str) -> list[dict]:
        """Returns model files (.safetensors etc.) from a HuggingFace repo."""
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                f"{_API}/models/{repo_id}", params={"blobs": "true"}, headers=self.auth_headers()
            )
            resp.raise_for_status()
            data = resp.json()
        source_page_url = f"{_BASE}/{repo_id}"
        result = []
        for f in data.get("siblings", []):
            name = f.get("rfilename", "")
            ext = "." + name.rsplit(".", 1)[-1] if "." in name else ""
            if ext in MODEL_EXTENSIONS:
                result.append(
                    {
                        "filename": name,
                        "size": f.get("size", 0),
                        "url": f"{_BASE}/{repo_id}/resolve/main/{name}",
                        "source_page_url": source_page_url,
                    }
                )
        return result

    def _model_files_for_storage(self, repo_id: str, files: list[dict]) -> list[dict]:
        """Converts get_model_files() output to the shape expected by upsert_repo_files()."""
        return [
            {
                "filename": f["filename"],
                "size_bytes": f.get("size", 0),
                "download_url": f["url"],
                "source_page_url": f.get("source_page_url", f"{_BASE}/{repo_id}"),
            }
            for f in files
        ]

    async def get_readme(self, repo_id: str) -> str:
        """Fetches README.md and returns its body as HTML with YAML front matter stripped."""
        url = f"{_BASE}/{repo_id}/resolve/main/README.md"
        async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
            resp = await client.get(url, headers=self.auth_headers())
            if resp.status_code != 200:
                return ""
            text = resp.text.replace("\r\n", "\n")
        if text.startswith("---"):
            end = text.find("\n---", 3)
            if end != -1:
                text = text[end + 4 :].lstrip("\n")
        return mistune.html(text)

    async def resolve_direct_link(self, repo_id: str) -> dict:
        """Returns preview image URLs for a HuggingFace repo for direct link preview."""
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(f"{_API}/models/{repo_id}", headers=self.auth_headers())
            resp.raise_for_status()
            data = resp.json()
        return {"image_urls": _image_urls_from_siblings(repo_id, data)}

    async def fetch_metadata(self, source_id: str) -> ProviderMetadata:
        """Returns description, readme HTML, tags, and preview image URLs from a HuggingFace model card."""
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(f"{_API}/models/{source_id}", headers=self.auth_headers())
            resp.raise_for_status()
            data = resp.json()
        image_urls = _image_urls_from_siblings(source_id, data)
        card_data = data.get("cardData") or {}
        description = card_data.get("description", "") or ""
        readme_html = await self.get_readme(source_id)
        display_name = source_id.split("/")[-1] if source_id else ""
        return ProviderMetadata(
            description=description,
            trigger_words=card_data.get("trigger") or [],
            image_urls=image_urls,
            tags=data.get("tags", []),
            display_name=display_name,
            readme_html=readme_html,
        )
