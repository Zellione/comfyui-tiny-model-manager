"""Routes for browsing, downloading and exporting CivitAI workflows (F-129).

Kept separate from ``routes/workflow.py`` (singular), which is the ComfyUI node-insertion
queue and is unrelated apart from being reused here to push a graph onto the canvas.
"""

import json

import httpx
from aiohttp import web

from ..db import workflow_repo
from ..services import workflow_store
from ..services.providers import civitai
from ._helpers import err, json_route, ok
from .workflow import enqueue_graph

_NOT_FOUND = "Workflow not found"
_ENTRY_NOT_FOUND = "Workflow entry not found"
_PROVIDER_UNAVAILABLE = "provider_unavailable"


def _entry_payload(entry: dict) -> dict:
    """A stored entry plus its gallery, ready for the frontend."""
    entry["media"] = workflow_store.list_entry_media(entry.get("media_hash", ""))
    return entry


async def _search(request: web.Request) -> web.Response:
    q = request.rel_url.query.get("q", "")
    cursor = request.rel_url.query.get("cursor", "")
    page = int(request.rel_url.query.get("page", 1))
    base_model = request.rel_url.query.get("base_model", "")
    sort = request.rel_url.query.get("sort", "")
    period = request.rel_url.query.get("period", "")
    tags_raw = request.rel_url.query.get("tags", "")
    tags = [t.strip() for t in tags_raw.split(",") if t.strip()]
    try:
        data = await civitai.search(
            q,
            page=page,
            cursor=cursor,
            base_model=base_model,
            sort=sort,
            period=period,
            tags=tags,
            types=workflow_store.CIVITAI_WORKFLOW_TYPE,
        )
    except httpx.HTTPError:
        return err(_PROVIDER_UNAVAILABLE, status=503)
    data["installed_version_ids"] = sorted(await workflow_repo.get_installed_version_ids())
    return ok(data)


async def _download(request: web.Request) -> web.Response:
    body = await request.json()
    model_id = str(body.get("model_id", "")).strip()
    version_id = str(body.get("version_id", "")).strip()
    if not model_id.isdigit():
        return err("model_id required", status=400)
    try:
        result = await workflow_store.download_workflow(model_id, version_id)
    except workflow_store.WorkflowTooLargeError:
        return err("archive_too_large", status=413)
    except workflow_store.WorkflowPayloadError as exc:
        return err(str(exc), status=422)
    except ValueError as exc:
        return err(str(exc), status=400)
    except httpx.HTTPError:
        return err(_PROVIDER_UNAVAILABLE, status=503)
    return ok(result)


async def _list(request: web.Request) -> web.Response:
    entries = await workflow_repo.list_workflow_entries()
    return ok([_entry_payload(e) for e in entries])


async def _delete(request: web.Request) -> web.Response:
    entry_id = int(request.match_info["id"])
    if not await workflow_store.delete_entry(entry_id):
        return err(_ENTRY_NOT_FOUND, status=404)
    return web.Response(status=204)


async def _export(request: web.Request) -> web.Response:
    workflow_id = int(request.match_info["id"])
    try:
        path = await workflow_store.export_workflow(workflow_id)
    except FileNotFoundError:
        return err(_NOT_FOUND, status=404)
    return ok({"path": path})


async def _file(request: web.Request) -> web.Response:
    workflow_id = int(request.match_info["id"])
    workflow = await workflow_repo.get_workflow(workflow_id)
    if workflow is None:
        return err(_NOT_FOUND, status=404)
    try:
        graph = workflow_store.read_graph(workflow)
    except (FileNotFoundError, ValueError):
        return err(_NOT_FOUND, status=404)
    # Served raw (not wrapped in the ok() envelope): both the JS extension and the
    # browser's "download JSON" action want the graph itself.
    return web.json_response(
        graph,
        dumps=json.dumps,
        headers={"Content-Disposition": f'attachment; filename="{workflow["name"]}.json"'},
    )


async def _open(request: web.Request) -> web.Response:
    workflow_id = int(request.match_info["id"])
    workflow = await workflow_repo.get_workflow(workflow_id)
    if workflow is None:
        return err(_NOT_FOUND, status=404)
    return ok({"id": enqueue_graph(workflow_id)})


def add_workflows_routes(routes) -> None:
    routes.get("/tiny-model-manager/api/workflows/search")(json_route(_search))
    routes.post("/tiny-model-manager/api/workflows/download")(json_route(_download))
    routes.get("/tiny-model-manager/api/workflows")(json_route(_list))
    routes.delete("/tiny-model-manager/api/workflows/{id}")(json_route(_delete))
    routes.post("/tiny-model-manager/api/workflows/{id}/export")(json_route(_export))
    routes.get("/tiny-model-manager/api/workflows/{id}/file")(json_route(_file))
    routes.post("/tiny-model-manager/api/workflows/{id}/open")(json_route(_open))
