"""Integration tests for py/routes/tags.py (GET /api/tags)."""

import pytest
from aiohttp import web


@pytest.fixture
async def client(aiohttp_client, ext_dir):
    from py.routes.tags import add_tag_routes

    app = web.Application()
    routes = web.RouteTableDef()
    add_tag_routes(routes)
    app.router.add_routes(routes)
    return await aiohttp_client(app)


async def _seed_model_with_tags(filename: str, tags: list[str]) -> int:
    from py.db import model_repo

    return await model_repo.upsert_model_with_meta(
        filename=filename,
        model_type="loras",
        source_platform="civitai",
        source_id="1",
        description="",
        trigger_words=[],
        tags=tags,
    )


class TestGetTags:
    async def test_empty_query_returns_empty_list(self, client, ext_dir):
        resp = await client.get("/tiny-model-manager/api/tags")
        assert resp.status == 200
        data = await resp.json()
        assert data["success"] is True
        assert data["data"] == []

    async def test_blank_q_returns_empty_list(self, client, ext_dir):
        resp = await client.get("/tiny-model-manager/api/tags", params={"q": "   "})
        assert resp.status == 200
        assert (await resp.json())["data"] == []

    async def test_prefix_matches_tags(self, client, ext_dir):
        await _seed_model_with_tags("a.safetensors", ["anime", "action"])
        resp = await client.get("/tiny-model-manager/api/tags", params={"q": "an"})
        data = (await resp.json())["data"]
        assert "anime" in data

    async def test_prefix_is_case_sensitive_match(self, client, ext_dir):
        await _seed_model_with_tags("b.safetensors", ["Lora"])
        resp = await client.get("/tiny-model-manager/api/tags", params={"q": "Lo"})
        data = (await resp.json())["data"]
        assert "Lora" in data

    async def test_non_matching_prefix_returns_empty(self, client, ext_dir):
        await _seed_model_with_tags("c.safetensors", ["anime"])
        resp = await client.get("/tiny-model-manager/api/tags", params={"q": "xyz"})
        assert (await resp.json())["data"] == []

    async def test_results_capped_at_five(self, client, ext_dir):
        tags = [f"tag{i}" for i in range(10)]
        await _seed_model_with_tags("d.safetensors", tags)
        resp = await client.get("/tiny-model-manager/api/tags", params={"q": "tag"})
        assert len((await resp.json())["data"]) <= 5

    async def test_more_popular_tags_ranked_first(self, client, ext_dir):
        await _seed_model_with_tags("e.safetensors", ["popular", "rare"])
        await _seed_model_with_tags("f.safetensors", ["popular"])
        resp = await client.get("/tiny-model-manager/api/tags", params={"q": "p"})
        assert (await resp.json())["data"][0] == "popular"
