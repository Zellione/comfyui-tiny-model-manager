"""Integration tests for py/routes/notifications.py (backend toast queue flush)."""

import pytest
from aiohttp import web

from py.services import backend_notifier


@pytest.fixture
async def client(aiohttp_client, ext_dir):
    from py.routes.notifications import add_notification_routes

    backend_notifier._pending.clear()

    app = web.Application()
    routes = web.RouteTableDef()
    add_notification_routes(routes)
    app.router.add_routes(routes)
    return await aiohttp_client(app)


class TestGetNotifications:
    async def test_returns_pushed_notifications(self, client):
        backend_notifier.push("success", "model downloaded")
        backend_notifier.push("error", "fetch failed")

        resp = await client.get("/tiny-model-manager/api/notifications")
        assert resp.status == 200
        body = await resp.json()
        assert body["success"] is True
        assert [(n["type"], n["message"]) for n in body["data"]] == [
            ("success", "model downloaded"),
            ("error", "fetch failed"),
        ]
        assert all(n["id"] for n in body["data"])

    async def test_flush_empties_the_queue(self, client):
        backend_notifier.push("success", "once")

        first = await (await client.get("/tiny-model-manager/api/notifications")).json()
        second = await (await client.get("/tiny-model-manager/api/notifications")).json()
        assert [n["message"] for n in first["data"]] == ["once"]
        assert second["data"] == []

    async def test_empty_queue_returns_empty_list(self, client):
        body = await (await client.get("/tiny-model-manager/api/notifications")).json()
        assert body == {"success": True, "data": []}
