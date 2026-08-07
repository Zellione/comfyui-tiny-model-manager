import os

from aiohttp import web

from ..db import model_repo
from ..services import auto_migrator, missing_model_resolver, model_paths
from ..services import downloader as dl
from ..services.providers import civitai, huggingface
from ..services.url_guard import is_allowed_url
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
        # F-92: the listing carries LFS hashes, so any matching unregistered file on
        # disk can be turned into a model card in the background.
        auto_migrator.schedule(auto_migrator.from_hf_files(repo_id, files))
        return ok(files)

    @routes.get("/tiny-model-manager/api/civitai/versions/{model_id}")
    @json_route
    async def civitai_versions(request):
        model_id = int(request.match_info["model_id"])
        versions = await civitai.get_model_versions(model_id)
        auto_migrator.schedule(auto_migrator.from_civitai_versions(versions))
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


async def _queue_download(
    url: str,
    model_type: str,
    filename: str,
    platform: str,
    source_id: str,
    hint_base_model: str = "",
) -> str:
    """Confine the destination, record the history row and enqueue; returns the task id.

    ``dl.validate_target`` runs before any DB write so a rejected request leaves no dangling
    history row. It raises ``ValueError`` on a traversal attempt — callers answer 400.
    """
    dl.validate_target(model_type, filename, platform)
    model_name = os.path.basename(filename)
    history_id = await model_repo.insert_download_history(
        model_name=model_name,
        source=platform,
        model_id=source_id if platform == "huggingface" else "",
        version_id=source_id if platform == "civitai" else "",
        file_url=url,
        dest_path=filename,
        model_type=model_type,
    )
    task = dl.enqueue(
        url,
        model_type,
        filename,
        platform,
        source_id,
        history_id=history_id,
        hint_base_model=hint_base_model,
    )
    return task.id


async def _start_download(request):
    body = await request.json()
    url = body.get("url", "")
    model_type = body.get("model_type", "checkpoints")
    filename = body.get("filename", "")
    platform = body.get("platform", "")
    source_id = body.get("source_id", "")
    hint_base_model = body.get("base_model", "")
    if not url or not filename:
        return err("url and filename required", status=400)
    if not is_allowed_url(url):
        return err("Download URL host is not allowed", status=400)
    try:
        task_id = await _queue_download(
            url, model_type, filename, platform, source_id, hint_base_model
        )
    except ValueError as exc:
        return err(str(exc), status=400)
    return ok({"task_id": task_id})


async def _start_missing_download(request):
    """Resolve one entry of ComfyUI's Missing Models panel and queue it (F-144).

    ``directory`` is the panel's folder name and is authoritative — a provider's own idea of
    the model type never overrides it, because the panel never offers a TMM button for a row
    whose directory it could not determine.
    """
    body = await request.json()
    filename = (body.get("filename") or "").strip()
    model_type = (body.get("directory") or "").strip()
    url = (body.get("url") or "").strip()

    if not filename:
        return err("filename required", status=400)
    # Any folder ComfyUI itself groups by is acceptable — `_get_dest_dir` resolves it through
    # `folder_paths`, which knows the full set (26 folders in ComfyUI 0.24, plus whatever
    # custom nodes register). A curated allowlist here would silently reject legitimate
    # folders such as `latent_upscale_models` or `audio_encoders`. The only rejects are the
    # "unknown category" row, whose directory is empty, and anything that is not a single
    # path component.
    if not model_paths.is_safe_segment(model_type):
        return err("unsupported_directory", status=400)
    # Cheap short-circuit for a file TMM installed after the panel last refreshed. Only the
    # model type's own directories are checked, not subfolders created by
    # ``organize_into_subfolders`` — a miss here just means the resolution chain runs.
    if model_paths.find_file(model_type, os.path.basename(filename)):
        return ok({"already_installed": True})

    resolution = await missing_model_resolver.resolve(filename, model_type, url)
    if resolution is None:
        return ok(
            {
                "unresolved": True,
                "search_term": missing_model_resolver.search_term(filename),
                "model_type": model_type,
            }
        )

    try:
        task_id = await _queue_download(
            resolution.download_url,
            resolution.model_type,
            resolution.filename,
            resolution.platform,
            resolution.source_id,
            resolution.base_model,
        )
    except ValueError as exc:
        return err(str(exc), status=400)
    return ok(
        {
            "task_id": task_id,
            "platform": resolution.platform,
            "source_id": resolution.source_id,
            "model_type": resolution.model_type,
            "filename": resolution.filename,
        }
    )


async def _redownload(request):
    entry_id = int(request.match_info["id"])
    entry = await model_repo.get_download_history_entry(entry_id)
    if not entry:
        return err("History entry not found", status=404)
    url = entry["file_url"]
    if not url:
        return err("No download URL stored for this entry", status=400)
    if not is_allowed_url(url):
        return err("Download URL host is not allowed", status=400)
    platform = entry["source"]
    source_id = entry["version_id"] or entry["model_id"]
    model_type = entry["model_type"]
    dest_path = entry["dest_path"]
    model_name = entry["model_name"]
    try:
        dl.validate_target(model_type, dest_path, platform)
    except ValueError as exc:
        return err(str(exc), status=400)
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


def _register_download_mgmt_routes(routes):
    @routes.post("/tiny-model-manager/api/download")
    @json_route
    async def start_download(request):
        return await _start_download(request)

    @routes.post("/tiny-model-manager/api/download/missing")
    @json_route
    async def start_missing_download(request):
        return await _start_missing_download(request)

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
        return await _redownload(request)


def add_download_routes(routes):
    _register_search_routes(routes)
    _register_download_mgmt_routes(routes)
