"""Integration tests for py/routes/workflow.py (insert / pending / ack)."""

import pytest
from aiohttp import web


@pytest.fixture()
async def client(aiohttp_client, ext_dir):
    from py.routes.workflow import _pending, register_workflow_routes

    _pending.clear()

    app = web.Application()
    routes = web.RouteTableDef()
    register_workflow_routes(routes)
    app.router.add_routes(routes)
    return await aiohttp_client(app)


class TestWorkflowInsert:
    async def test_insert_returns_success_and_id(self, client):
        resp = await client.post(
            "/tiny-model-manager/api/workflow/insert",
            json={"model_type": "loras", "filename": "my_lora.safetensors"},
        )
        assert resp.status == 200
        data = await resp.json()
        assert data["success"] is True
        assert "id" in data

    async def test_pending_contains_inserted_item(self, client):
        await client.post(
            "/tiny-model-manager/api/workflow/insert",
            json={"model_type": "checkpoints", "filename": "ck.safetensors"},
        )
        resp = await client.get("/tiny-model-manager/api/workflow/pending")
        data = await resp.json()
        items = data["data"]
        assert any(i["filename"] == "ck.safetensors" for i in items)

    async def test_multiple_inserts_queued(self, client):
        from py.routes.workflow import _pending

        _pending.clear()
        await client.post(
            "/tiny-model-manager/api/workflow/insert",
            json={"model_type": "loras", "filename": "a.safetensors"},
        )
        await client.post(
            "/tiny-model-manager/api/workflow/insert",
            json={"model_type": "loras", "filename": "b.safetensors"},
        )
        resp = await client.get("/tiny-model-manager/api/workflow/pending")
        items = (await resp.json())["data"]
        assert len(items) == 2


class TestWorkflowAck:
    async def test_ack_removes_item(self, client):
        from py.routes.workflow import _pending

        _pending.clear()
        resp = await client.post(
            "/tiny-model-manager/api/workflow/insert",
            json={"model_type": "loras", "filename": "z.safetensors"},
        )
        item_id = (await resp.json())["id"]
        await client.post("/tiny-model-manager/api/workflow/ack", json={"id": item_id})
        pending_resp = await client.get("/tiny-model-manager/api/workflow/pending")
        items = (await pending_resp.json())["data"]
        assert not any(i["id"] == item_id for i in items)

    async def test_ack_unknown_id_is_noop(self, client):
        resp = await client.post(
            "/tiny-model-manager/api/workflow/ack", json={"id": "nonexistent-uuid"}
        )
        assert resp.status == 200
        assert (await resp.json())["success"] is True
