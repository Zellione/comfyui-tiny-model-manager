from .base import ModelProvider, ProviderMetadata
from .civitai_provider import CivitaiProvider
from .huggingface_provider import HuggingFaceProvider

civitai = CivitaiProvider()
huggingface = HuggingFaceProvider()

_PROVIDERS: dict[str, ModelProvider] = {p.name: p for p in (civitai, huggingface)}


def get_provider(name: str) -> ModelProvider | None:
    return _PROVIDERS.get(name)


__all__ = [
    "ModelProvider",
    "ProviderMetadata",
    "CivitaiProvider",
    "HuggingFaceProvider",
    "civitai",
    "huggingface",
    "get_provider",
]
