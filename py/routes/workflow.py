import uuid

from aiohttp import web

from ._helpers import json_route, ok

_pending: list[dict] = []


def enqueue_graph(workflow_id: int) -> str:
    """Queue a stored workflow graph for the JS extension to load onto the canvas.

    Exposed as a function rather than by exporting ``_pending``: ``workflow_ack`` rebinds
    that list, so a module that imported the name would append to a stale one.
    """
    item = {"id": str(uuid.uuid4()), "kind": "graph", "workflow_id": workflow_id}
    _pending.append(item)
    return item["id"]


@json_route
async def workflow_insert(request: web.Request) -> web.Response:
    body = await request.json()
    item = {
        "id": str(uuid.uuid4()),
        "kind": "node",
        "model_type": body.get("model_type", ""),
        "filename": body.get("filename", ""),
    }
    _pending.append(item)
    return ok(id=item["id"])


@json_route
async def workflow_pending(request: web.Request) -> web.Response:
    return ok(list(_pending))


@json_route
async def workflow_ack(request: web.Request) -> web.Response:
    global _pending
    body = await request.json()
    item_id = body.get("id")
    _pending = [p for p in _pending if p["id"] != item_id]
    return ok()


def register_workflow_routes(routes) -> None:
    routes.post("/tiny-model-manager/api/workflow/insert")(workflow_insert)
    routes.get("/tiny-model-manager/api/workflow/pending")(workflow_pending)
    routes.post("/tiny-model-manager/api/workflow/ack")(workflow_ack)
