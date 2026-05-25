from aiohttp import web
from ..services import downloader as dl
from ..services.providers import civitai, huggingface


def add_download_routes(routes):

    @routes.get("/tiny-model-manager/api/search/civitai")
    async def search_civitai(request):
        q = request.rel_url.query.get("q", "")
        model_type = request.rel_url.query.get("type", "")
        page = int(request.rel_url.query.get("page", 1))
        cursor = request.rel_url.query.get("cursor", "")
        try:
            data = await civitai.search(q, model_type, page=page, cursor=cursor)
            return web.json_response({"success": True, "data": data})
        except Exception as exc:
            return web.json_response({"success": False, "error": str(exc)}, status=500)

    @routes.get("/tiny-model-manager/api/search/huggingface")
    async def search_hf(request):
        q = request.rel_url.query.get("q", "")
        model_type = request.rel_url.query.get("type", "")
        p = int(request.rel_url.query.get("p", 0))
        try:
            data = await huggingface.search(q, model_type, p=p)
            return web.json_response({"success": True, "data": data})
        except Exception as exc:
            return web.json_response({"success": False, "error": str(exc)}, status=500)

    @routes.get("/tiny-model-manager/api/search/huggingface/files")
    async def hf_files(request):
        repo_id = request.rel_url.query.get("repo", "")
        if not repo_id:
            return web.json_response({"success": False, "error": "Missing repo"}, status=400)
        try:
            files = await huggingface.get_model_files(repo_id)
            return web.json_response({"success": True, "data": files})
        except Exception as exc:
            return web.json_response({"success": False, "error": str(exc)}, status=500)

    @routes.get("/tiny-model-manager/api/civitai/versions/{model_id}")
    async def civitai_versions(request):
        model_id = int(request.match_info["model_id"])
        try:
            versions = await civitai.get_model_versions(model_id)
            return web.json_response({"success": True, "data": versions})
        except Exception as exc:
            return web.json_response({"success": False, "error": str(exc)}, status=500)

    @routes.get("/tiny-model-manager/api/huggingface/resolve")
    async def hf_resolve(request):
        repo_id = request.rel_url.query.get("repo", "")
        if not repo_id:
            return web.json_response({"success": False, "error": "Missing repo"}, status=400)
        try:
            result = await huggingface.resolve_direct_link(repo_id)
            return web.json_response({"success": True, "data": result})
        except Exception as exc:
            return web.json_response({"success": False, "error": str(exc)}, status=500)

    @routes.get("/tiny-model-manager/api/civitai/resolve/{version_id}")
    async def civitai_resolve_version(request):
        version_id = int(request.match_info["version_id"])
        try:
            result = await civitai.resolve_direct_link(version_id)
            return web.json_response({"success": True, "data": result})
        except Exception as exc:
            return web.json_response({"success": False, "error": str(exc)}, status=500)

    @routes.post("/tiny-model-manager/api/download")
    async def start_download(request):
        body = await request.json()
        url = body.get("url", "")
        model_type = body.get("model_type", "checkpoints")
        filename = body.get("filename", "")
        platform = body.get("platform", "")
        source_id = body.get("source_id", "")
        if not url or not filename:
            return web.json_response({"success": False, "error": "url and filename required"}, status=400)
        task = dl.enqueue(url, model_type, filename, platform, source_id)
        return web.json_response({"success": True, "data": {"task_id": task.id}})

    @routes.get("/tiny-model-manager/api/download/status")
    async def download_status(request):
        return web.json_response({"success": True, "data": dl.get_all_tasks()})
