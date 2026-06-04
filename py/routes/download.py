from ..services import downloader as dl
from ..services.providers import civitai, huggingface
from ._helpers import err, json_route, ok


def add_download_routes(routes):

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
        format = request.rel_url.query.get("format", "")
        tags_raw = request.rel_url.query.get("tags", "")
        tags = [t.strip() for t in tags_raw.split(",") if t.strip()]
        data = await huggingface.search(
            q, model_type, p=p, sort=sort, direction=direction, format=format, tags=tags
        )
        return ok(data)

    @routes.get("/tiny-model-manager/api/search/huggingface/files")
    @json_route
    async def hf_files(request):
        repo_id = request.rel_url.query.get("repo", "")
        if not repo_id:
            return err("Missing repo", status=400)
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
            return err("Missing repo", status=400)
        text = await huggingface.get_readme(repo_id)
        return ok({"description": text})

    @routes.get("/tiny-model-manager/api/huggingface/resolve")
    @json_route
    async def hf_resolve(request):
        repo_id = request.rel_url.query.get("repo", "")
        if not repo_id:
            return err("Missing repo", status=400)
        result = await huggingface.resolve_direct_link(repo_id)
        return ok(result)

    @routes.get("/tiny-model-manager/api/civitai/resolve/{version_id}")
    @json_route
    async def civitai_resolve_version(request):
        version_id = int(request.match_info["version_id"])
        result = await civitai.resolve_direct_link(version_id)
        return ok(result)

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
        task = dl.enqueue(url, model_type, filename, platform, source_id)
        return ok({"task_id": task.id})

    @routes.get("/tiny-model-manager/api/download/status")
    @json_route
    async def download_status(request):
        return ok(dl.get_all_tasks())
