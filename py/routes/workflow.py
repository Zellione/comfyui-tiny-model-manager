import uuid

from aiohttp import web

_pending: list[dict] = []


async def workflow_insert(request: web.Request) -> web.Response:
    body = await request.json()
    item = {
        "id": str(uuid.uuid4()),
        "model_type": body.get("model_type", ""),
        "filename": body.get("filename", ""),
    }
    _pending.append(item)
    return web.json_response({"success": True, "id": item["id"]})


async def workflow_pending(request: web.Request) -> web.Response:
    return web.json_response({"success": True, "data": list(_pending)})


async def workflow_ack(request: web.Request) -> web.Response:
    global _pending
    body = await request.json()
    item_id = body.get("id")
    _pending = [p for p in _pending if p["id"] != item_id]
    return web.json_response({"success": True})


def register_workflow_routes(routes) -> None:
    routes.post("/tiny-model-manager/api/workflow/insert")(workflow_insert)
    routes.get("/tiny-model-manager/api/workflow/pending")(workflow_pending)
    routes.post("/tiny-model-manager/api/workflow/ack")(workflow_ack)
