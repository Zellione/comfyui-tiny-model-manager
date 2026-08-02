"""Integration tests for the CivitAI images routes (F-130)."""

import json

import httpx
import pytest
from aiohttp import web

from py.db import model_repo, workflow_repo

_API = "/tiny-model-manager/api/images"

GRAPH = {"last_node_id": 1, "nodes": [{"id": 1, "type": "KSampler"}], "links": []}

COMFY_IMAGE = {
    "id": 111,
    "url": "https://image.civitai.com/a.jpeg",
    "type": "image",
    "baseModel": "SDXL 1.0",
    "username": "someone",
    "meta": {"comfy": json.dumps({"prompt": {}, "workflow": GRAPH})},
}

PARAMS_IMAGE = {
    "id": 222,
    "url": "https://image.civitai.com/b.jpeg",
    "type": "image",
    "baseModel": "Flux.1 D",
    "username": "someone",
    "meta": {
        "prompt": "a cat <lora:Sparkle:0.7>",
        "negativePrompt": "blurry",
        "steps": 20,
        "cfgScale": 7,
        "sampler": "Euler a",
        "seed": 42,
        "width": 512,
        "height": 512,
        "Model": "base.safetensors",
        "hashes": {"model": "aaaaaaaaaa", "lora:Sparkle": "bbbbbbbbbb"},
    },
}

BARE_IMAGE = {"id": 333, "url": "https://image.civitai.com/c.jpeg", "type": "image", "meta": {}}

_IMAGES = {"111": COMFY_IMAGE, "222": PARAMS_IMAGE, "333": BARE_IMAGE}


@pytest.fixture
async def client(aiohttp_client, ext_dir):
    from py.routes.images import add_images_routes

    app = web.Application()
    routes = web.RouteTableDef()
    add_images_routes(routes)
    app.router.add_routes(routes)
    return await aiohttp_client(app)


@pytest.fixture
def stub_civitai(monkeypatch):
    """Stub every outbound CivitAI call; the block_network fixture would raise otherwise."""
    calls = {"version": [], "hash": []}

    async def fake_search(**params):
        image_id = str(params.get("image_id") or "")
        if image_id:
            item = _IMAGES.get(image_id)
            return {"items": [item] if item else [], "metadata": {}}
        return {"items": [COMFY_IMAGE, PARAMS_IMAGE, BARE_IMAGE], "metadata": {"nextCursor": "n1"}}

    async def fake_version(version_id):
        calls["version"].append(version_id)
        return {
            "filename": "sparkle.safetensors",
            "download_url": "https://civitai.com/api/download/models/9",
            "size_kb": 100,
            "model_type": "loras",
            "model_name": "Sparkle",
            "version_name": "v1",
            "base_model": "SDXL 1.0",
            "model_version_id": "9",
            "model_id": "8",
        }

    async def fake_hash(file_hash):
        calls["hash"].append(file_hash)
        if file_hash.startswith("bbbb"):
            return {
                "filename": "sparkle.safetensors",
                "download_url": "https://civitai.com/api/download/models/9",
                "size_kb": 100,
                "model_type": "loras",
                "model_name": "Sparkle",
                "version_name": "v1",
                "base_model": "SDXL 1.0",
                "model_version_id": "9",
                "model_id": "8",
            }
        return None

    monkeypatch.setattr("py.routes.images._civitai_image_search", fake_search)
    monkeypatch.setattr("py.routes.images._civitai_version_info", fake_version)
    monkeypatch.setattr("py.routes.images._civitai_hash_info", fake_hash)
    return calls


class TestSearch:
    async def test_returns_items_with_a_recreatable_tag(self, client, stub_civitai):
        resp = await client.get(f"{_API}/search", params={"sort": "Newest"})
        assert resp.status == 200
        data = (await resp.json())["data"]
        assert [i["recreatable"] for i in data["items"]] == ["graph", "params", ""]
        assert data["metadata"]["nextCursor"] == "n1"

    async def test_filters_are_forwarded(self, client, monkeypatch):
        seen = {}

        async def fake_search(**params):
            seen.update(params)
            return {"items": [], "metadata": {}}

        monkeypatch.setattr("py.routes.images._civitai_image_search", fake_search)
        await client.get(
            f"{_API}/search",
            params={
                "sort": "Most Reactions",
                "period": "Week",
                "nsfw": "None",
                "base_model": "SDXL 1.0",
                "type": "image",
                "username": "bob",
                "cursor": "c1",
            },
        )
        assert seen["sort"] == "Most Reactions"
        assert seen["period"] == "Week"
        assert seen["nsfw"] == "None"
        assert seen["base_model"] == "SDXL 1.0"
        assert seen["media_type"] == "image"
        assert seen["username"] == "bob"
        assert seen["cursor"] == "c1"

    @pytest.mark.parametrize("raw,expected", [("500", 200), ("0", 1), ("abc", 50), ("20", 20)])
    async def test_limit_is_clamped(self, client, monkeypatch, raw, expected):
        seen = {}

        async def fake_search(**params):
            seen.update(params)
            return {"items": [], "metadata": {}}

        monkeypatch.setattr("py.routes.images._civitai_image_search", fake_search)
        await client.get(f"{_API}/search", params={"limit": raw})
        assert seen["limit"] == expected

    async def test_provider_error_is_503(self, client, monkeypatch):
        async def boom(**params):
            raise httpx.ConnectError("down")

        monkeypatch.setattr("py.routes.images._civitai_image_search", boom)
        resp = await client.get(f"{_API}/search")
        assert resp.status == 503
        assert (await resp.json())["error"] == "provider_unavailable"


class TestDetail:
    async def test_returns_the_single_image(self, client, stub_civitai):
        resp = await client.get(f"{_API}/111")
        assert resp.status == 200
        data = (await resp.json())["data"]
        assert data["id"] == 111
        assert data["recreatable"] == "graph"

    async def test_unknown_image_is_404(self, client, stub_civitai):
        resp = await client.get(f"{_API}/999")
        assert resp.status == 404
        assert (await resp.json())["error"] == "image_not_found"

    async def test_non_numeric_id_is_404(self, client, stub_civitai):
        resp = await client.get(f"{_API}/abc")
        assert resp.status == 404

    async def test_out_of_range_id_is_404_not_503(self, client, stub_civitai):
        # CivitAI answers 500 "out of range for type integer" past 2^31-1; forwarding it
        # would surface a bad id as a provider outage.
        resp = await client.get(f"{_API}/999999999999")
        assert resp.status == 404
        assert (await resp.json())["error"] == "image_not_found"

    async def test_double_nested_meta_is_unwrapped(self, client, monkeypatch):
        """Querying by imageId wraps meta one level deeper than the plain feed does."""

        async def fake_search(**params):
            nested = dict(COMFY_IMAGE)
            nested["meta"] = {"id": 111, "meta": COMFY_IMAGE["meta"]}
            return {"items": [nested], "metadata": {}}

        monkeypatch.setattr("py.routes.images._civitai_image_search", fake_search)
        resp = await client.get(f"{_API}/111")
        assert resp.status == 200
        assert (await resp.json())["data"]["recreatable"] == "graph"

    async def test_provider_error_is_503(self, client, monkeypatch):
        async def boom(**params):
            raise httpx.ConnectError("down")

        monkeypatch.setattr("py.routes.images._civitai_image_search", boom)
        resp = await client.get(f"{_API}/111")
        assert resp.status == 503


class TestRecreate:
    async def test_embedded_graph_is_stored_verbatim(self, client, stub_civitai):
        resp = await client.post(f"{_API}/111/recreate")
        assert resp.status == 200
        data = (await resp.json())["data"]
        assert data["source"] == "graph"
        assert data["template_warning"] is False
        assert data["workflow"]["node_count"] == 1

        stored = await workflow_repo.get_workflow(data["workflow"]["id"])
        assert stored is not None
        from py.services import workflow_store

        assert workflow_store.read_graph(stored) == GRAPH

    async def test_entry_is_recorded_against_the_image(self, client, stub_civitai):
        await client.post(f"{_API}/111/recreate")
        entries = await workflow_repo.list_workflow_entries()
        assert len(entries) == 1
        assert entries[0]["source_platform"] == "civitai-image"
        assert entries[0]["source_page_id"] == "111"
        assert entries[0]["source_page_url"] == "https://civitai.com/images/111"

    async def test_recreating_twice_upserts(self, client, stub_civitai):
        first = (await (await client.post(f"{_API}/111/recreate")).json())["data"]
        second = (await (await client.post(f"{_API}/111/recreate")).json())["data"]
        assert first["entry_id"] == second["entry_id"]
        assert first["workflow"]["id"] == second["workflow"]["id"]
        assert len(await workflow_repo.list_workflow_entries()) == 1

    async def test_params_image_builds_the_template(self, client, stub_civitai):
        resp = await client.post(f"{_API}/222/recreate")
        assert resp.status == 200
        data = (await resp.json())["data"]
        assert data["source"] == "params"
        # Flux.1 D is outside the SD family the template is shaped for.
        assert data["template_warning"] is True
        stored = await workflow_repo.get_workflow(data["workflow"]["id"])
        from py.services import workflow_store

        types = [n["type"] for n in workflow_store.read_graph(stored)["nodes"]]
        assert "CheckpointLoaderSimple" in types
        assert "KSampler" in types

    async def test_template_points_at_an_installed_file(self, client, stub_civitai):
        # A locally registered model whose SHA-256 starts with the image's AutoV2 hash.
        await model_repo.register_model(
            filename="mine/base_real.safetensors",
            model_type="checkpoints",
            file_hash="AAAAAAAAAA" + "f" * 54,
        )
        data = (await (await client.post(f"{_API}/222/recreate")).json())["data"]
        installed = [r for r in data["resources"] if r["status"] == "installed"]
        assert [r["filename"] for r in installed] == ["mine/base_real.safetensors"]

        from py.services import workflow_store

        stored = await workflow_repo.get_workflow(data["workflow"]["id"])
        graph = workflow_store.read_graph(stored)
        ckpt = next(n for n in graph["nodes"] if n["type"] == "CheckpointLoaderSimple")
        assert ckpt["widgets_values"] == ["mine/base_real.safetensors"]

    async def test_image_without_metadata_is_422(self, client, stub_civitai):
        resp = await client.post(f"{_API}/333/recreate")
        assert resp.status == 422
        assert (await resp.json())["error"] == "no_metadata"

    async def test_unknown_image_is_404(self, client, stub_civitai):
        resp = await client.post(f"{_API}/999/recreate")
        assert resp.status == 404

    async def test_double_nested_meta_still_recreates(self, client, monkeypatch):
        """Regression: the imageId lookup nests meta twice, which looked like no metadata."""

        async def fake_search(**params):
            nested = dict(COMFY_IMAGE)
            nested["meta"] = {"id": 111, "meta": COMFY_IMAGE["meta"]}
            return {"items": [nested], "metadata": {}}

        monkeypatch.setattr("py.routes.images._civitai_image_search", fake_search)
        resp = await client.post(f"{_API}/111/recreate")
        assert resp.status == 200
        assert (await resp.json())["data"]["source"] == "graph"

    async def test_thumbnail_hash_survives_media_cleanup(self, client, stub_civitai):
        """The entry's media hash must be in the live set, or startup cleanup sweeps it."""
        await client.post(f"{_API}/111/recreate")
        entries = await workflow_repo.list_workflow_entries()
        live = await model_repo.get_live_media_hashes()
        assert entries[0]["media_hash"] in live


class TestResolveResources:
    async def test_reports_installed_missing_and_unresolvable(self, client, stub_civitai):
        await model_repo.register_model(
            filename="checkpoints/base_real.safetensors",
            model_type="checkpoints",
            file_hash="aaaaaaaaaa" + "0" * 54,
        )
        resp = await client.post(f"{_API}/resolve-resources", json={"image_id": "222"})
        assert resp.status == 200
        resources = (await resp.json())["data"]["resources"]
        by_status = {r["status"] for r in resources}
        assert by_status == {"installed", "missing"}

        installed = next(r for r in resources if r["status"] == "installed")
        assert installed["filename"] == "checkpoints/base_real.safetensors"
        missing = next(r for r in resources if r["status"] == "missing")
        assert missing["download_url"] == "https://civitai.com/api/download/models/9"
        assert missing["model_type"] == "loras"
        assert missing["weight"] == 0.7

    async def test_unresolvable_resource_does_not_fail_the_batch(self, client, stub_civitai):
        resp = await client.post(f"{_API}/resolve-resources", json={"image_id": "222"})
        assert resp.status == 200
        resources = (await resp.json())["data"]["resources"]
        # The checkpoint hash resolves to nothing on CivitAI, the LoRA does.
        statuses = sorted(r["status"] for r in resources)
        assert statuses == ["missing", "unresolvable"]

    async def test_a_failing_lookup_is_reported_not_raised(self, client, stub_civitai, monkeypatch):
        async def boom(file_hash):
            raise httpx.ConnectError("down")

        monkeypatch.setattr("py.routes.images._civitai_hash_info", boom)
        resp = await client.post(f"{_API}/resolve-resources", json={"image_id": "222"})
        assert resp.status == 200
        assert all(r["status"] == "unresolvable" for r in (await resp.json())["data"]["resources"])

    async def test_version_id_is_preferred_over_hash(self, client, stub_civitai, monkeypatch):
        async def fake_search(**params):
            return {
                "items": [
                    {
                        "id": 444,
                        "url": "",
                        "baseModel": "SDXL 1.0",
                        "meta": {
                            "civitaiResources": [
                                {"type": "lora", "modelVersionId": 77, "weight": 0.5}
                            ]
                        },
                    }
                ],
                "metadata": {},
            }

        monkeypatch.setattr("py.routes.images._civitai_image_search", fake_search)
        resp = await client.post(f"{_API}/resolve-resources", json={"image_id": "444"})
        assert resp.status == 200
        assert stub_civitai["version"] == ["77"]
        assert stub_civitai["hash"] == []

    async def test_image_without_metadata_yields_no_resources(self, client, stub_civitai):
        resp = await client.post(f"{_API}/resolve-resources", json={"image_id": "333"})
        assert resp.status == 200
        assert (await resp.json())["data"]["resources"] == []

    @pytest.mark.parametrize("body", [{}, {"image_id": "abc"}, {"image_id": ""}])
    async def test_bad_image_id_is_404(self, client, stub_civitai, body):
        resp = await client.post(f"{_API}/resolve-resources", json=body)
        assert resp.status == 404

    async def test_provider_error_is_503(self, client, monkeypatch):
        async def boom(**params):
            raise httpx.ConnectError("down")

        monkeypatch.setattr("py.routes.images._civitai_image_search", boom)
        resp = await client.post(f"{_API}/resolve-resources", json={"image_id": "222"})
        assert resp.status == 503


class TestFileHashMap:
    async def test_maps_lowercased_hash_to_filename(self, ext_dir):
        await model_repo.register_model(
            filename="a.safetensors", model_type="checkpoints", file_hash="ABCDEF1234" + "0" * 54
        )
        await model_repo.register_model(filename="b.safetensors", model_type="checkpoints")
        mapping = await model_repo.get_file_hash_map()
        assert mapping == {"abcdef1234" + "0" * 54: "a.safetensors"}
