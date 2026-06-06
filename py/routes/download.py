import os

from aiohttp import web

from ..db import model_repo
from ..services import downloader as dl
from ..services.providers import civitai, huggingface
from ._helpers import err, json_route, ok

_MISSING_REPO = "Missing repo"


def _register_search_routes(routes):
    @routes.get("/tiny-model-manager/api/search/civitai")
    @json_route
    async def search_civitai(request):
        q = request.rel_url.query.get("q", "")
        model_type = request.rel_url.query.get("type", "")
        page = int(request.rel_url.query.get("page", 1))
        cursor = request.rel_url.query.get("cursor", "")
        base_model = request.rel_url.query.get("base_model", "")
        sort = request.rel_url.query.get("sort", "")
        period = request.rel_url.query.get("period", "")
        tags_raw = request.rel_url.query.get("tags", "")
        tags = [t.strip() for t in tags_raw.split(",") if t.strip()]
        data = await civitai.search(
            q,
            model_type,
            page=page,
            cursor=cursor,
            base_model=base_model,
            sort=sort,
            period=period,
            tags=tags,
        )
        return ok(data)

    @routes.get("/tiny-model-manager/api/search/huggingface")
    @json_route
    async def search_hf(request):
        q = request.rel_url.query.get("q", "")
        model_type = request.rel_url.query.get("type", "")
        p = int(request.rel_url.query.get("p", 0))
        sort = request.rel_url.query.get("sort", "downloads")
        direction = int(request.rel_url.query.get("direction", -1))
        file_format = request.rel_url.query.get("format", "")
        tags_raw = request.rel_url.query.get("tags", "")
        tags = [t.strip() for t in tags_raw.split(",") if t.strip()]
        data = await huggingface.search(
            q, model_type, p=p, sort=sort, direction=direction, format=file_format, tags=tags
        )
        return ok(data)

    @routes.get("/tiny-model-manager/api/search/huggingface/files")
    @json_route
    async def hf_files(request):
        repo_id = request.rel_url.query.get("repo", "")
        if not repo_id:
            return err(_MISSING_REPO, status=400)
        files = await huggingface.get_model_files(repo_id)
        return ok(files)

    @routes.get("/tiny-model-manager/api/civitai/versions/{model_id}")
    @json_route
    async def civitai_versions(request):
        model_id = int(request.match_info["model_id"])
        versions = await civitai.get_model_versions(model_id)
        return ok(versions)

    @routes.get("/tiny-model-manager/api/huggingface/readme")
    @json_route
    async def hf_readme(request):
        repo_id = request.rel_url.query.get("repo", "")
        if not repo_id:
            return err(_MISSING_REPO, status=400)
        text = await huggingface.get_readme(repo_id)
        return ok({"description": text})

    @routes.get("/tiny-model-manager/api/huggingface/resolve")
    @json_route
    async def hf_resolve(request):
        repo_id = request.rel_url.query.get("repo", "")
        if not repo_id:
            return err(_MISSING_REPO, status=400)
        result = await huggingface.resolve_direct_link(repo_id)
        return ok(result)

    @routes.get("/tiny-model-manager/api/civitai/resolve/{version_id}")
    @json_route
    async def civitai_resolve_version(request):
        version_id = int(request.match_info["version_id"])
        result = await civitai.resolve_direct_link(version_id)
        return ok(result)


def _register_download_mgmt_routes(routes):
    @routes.post("/tiny-model-manager/api/download")
    @json_route
    async def start_download(request):
        body = await request.json()
        url = body.get("url", "")
        model_type = body.get("model_type", "checkpoints")
        filename = body.get("filename", "")
        platform = body.get("platform", "")
        source_id = body.get("source_id", "")
        if not url or not filename:
            return err("url and filename required", status=400)
        model_name = os.path.basename(filename)
        version_id = source_id if platform == "civitai" else ""
        model_id = source_id if platform == "huggingface" else ""
        history_id = await model_repo.insert_download_history(
            model_name=model_name,
            source=platform,
            model_id=model_id,
            version_id=version_id,
            file_url=url,
            dest_path=filename,
            model_type=model_type,
        )
        task = dl.enqueue(url, model_type, filename, platform, source_id, history_id=history_id)
        return ok({"task_id": task.id})

    @routes.get("/tiny-model-manager/api/download/status")
    @json_route
    async def download_status(request):
        return ok(dl.get_all_tasks())

    @routes.delete("/tiny-model-manager/api/downloads/{id}")
    @json_route
    async def cancel_download(request):
        task_id = request.match_info["id"]
        if not dl.cancel_task(task_id):
            return err("Task not found", status=404)
        return web.Response(status=204)

    @routes.get("/tiny-model-manager/api/download/history")
    @json_route
    async def get_history(request):
        status = request.rel_url.query.get("status", "")
        q = request.rel_url.query.get("q", "")
        page = int(request.rel_url.query.get("page", 1))
        page_size = int(request.rel_url.query.get("page_size", 20))
        entries, total = await model_repo.get_download_history(
            status=status, q=q, page=page, page_size=page_size
        )
        return ok({"entries": entries, "total": total})

    @routes.post("/tiny-model-manager/api/download/history/{id}/redownload")
    @json_route
    async def redownload(request):
        entry_id = int(request.match_info["id"])
        entry = await model_repo.get_download_history_entry(entry_id)
        if not entry:
            return err("History entry not found", status=404)
        url = entry["file_url"]
        if not url:
            return err("No download URL stored for this entry", status=400)
        platform = entry["source"]
        source_id = entry["version_id"] or entry["model_id"]
        model_type = entry["model_type"]
        dest_path = entry["dest_path"]
        model_name = entry["model_name"]
        new_history_id = await model_repo.insert_download_history(
            model_name=model_name,
            source=platform,
            model_id=entry["model_id"],
            version_id=entry["version_id"],
            file_url=url,
            dest_path=dest_path,
            model_type=model_type,
        )
        task = dl.enqueue(
            url=url,
            model_type=model_type,
            filename=dest_path,
            platform=platform,
            source_id=source_id,
            history_id=new_history_id,
        )
        return ok({"task_id": task.id})


def add_download_routes(routes):
    _register_search_routes(routes)
    _register_download_mgmt_routes(routes)
