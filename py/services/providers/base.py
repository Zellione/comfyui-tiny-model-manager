from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class ProviderMetadata:
    description: str = ""
    trigger_words: list[str] = field(default_factory=list)
    image_urls: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    base_model: str = ""
    civitai_model_id: str = ""


class ModelProvider(ABC):
    name: str

    @abstractmethod
    def auth_headers(self) -> dict: ...

    @abstractmethod
    async def search(self, query: str, model_type: str = "", **kwargs) -> dict: ...

    @abstractmethod
    async def fetch_metadata(self, source_id: str) -> ProviderMetadata: ...
