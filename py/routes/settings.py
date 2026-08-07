import os

from .. import config as cfg
from ..background import spawn
from ..db import keyword_repo
from ._helpers import err, json_route, ok


def _masked_settings(data: dict) -> dict:
    """Return the settings payload with secret keys masked for the client."""
    return {
        "civitai_api_key": "***" if data.get("civitai_api_key") else "",
        "hf_token": "***" if data.get("hf_token") else "",
        "media_dir": data.get("media_dir", ""),
        "organize_into_subfolders": data.get("organize_into_subfolders", False),
        "cleanup_stale_media_on_start": data.get("cleanup_stale_media_on_start", False),
        # F-144: on by default — the integration only adds buttons next to ComfyUI's own,
        # so opting in silently is not surprising, while opting out must be possible.
        "missing_models_integration": data.get("missing_models_integration", True),
        "media_dir_default": os.path.join(cfg.data_dir(), "media"),
    }


def _apply_masked_updates(existing: dict, body: dict) -> None:
    """Merge body into existing, ignoring mask placeholders for secret keys."""
    if body.get("civitai_api_key", "") not in ("", "***"):
        existing["civitai_api_key"] = body["civitai_api_key"]
    if body.get("hf_token", "") not in ("", "***"):
        existing["hf_token"] = body["hf_token"]
    if "media_dir" in body:
        existing["media_dir"] = body["media_dir"]
    if "cleanup_stale_media_on_start" in body:
        existing["cleanup_stale_media_on_start"] = bool(body["cleanup_stale_media_on_start"])
    if "missing_models_integration" in body:
        existing["missing_models_integration"] = bool(body["missing_models_integration"])


async def _organize_conflict(enabling: bool) -> str | None:
    """Return an error message if organizing can't be enabled while jobs are pending."""
    if not enabling:
        return None
    from ..db import model_repo as _repo

    pending = await _repo.get_pending_jobs()
    if pending:
        return (
            f"Cannot enable organizing while {len(pending)} model(s) "
            "are still being reorganized. "
            "Please wait for the current operation to complete."
        )
    return None


async def _enqueue_reorganize(direction: str) -> None:
    """Enqueue every eligible model for the given direction and start processing."""
    from ..db import model_repo
    from ..services import reorganizer

    models = await model_repo.get_all_models_slim()
    await model_repo.clear_pending_jobs(direction)
    for m in models:
        fname = m["filename"]
        has_subfolder = "/" in fname or "\\" in fname
        eligible = has_subfolder if direction == "deorganize" else not has_subfolder
        if eligible:
            await model_repo.enqueue_reorganize(fname, m.get("model_type") or "", direction)
    spawn(reorganizer.process_pending_jobs())


def _add_keyword_routes(routes):
    """Register keyword API routes."""

    @routes.get("/tiny-model-manager/api/filename-keywords")
    @json_route
    async def get_keywords(request):
        return ok(await keyword_repo.list_keywords())

    @routes.post("/tiny-model-manager/api/filename-keywords")
    @json_route
    async def create_keyword(request):
        body = await request.json()
        kw = body.get("keyword", "").strip()
        if not kw:
            return err("keyword is required", status=400)
        new_id = await keyword_repo.create_keyword(
            kw, body.get("base_model"), body.get("model_type")
        )
        return ok({"id": new_id})

    @routes.put("/tiny-model-manager/api/filename-keywords/{id}")
    @json_route
    async def update_keyword(request):
        keyword_id = int(request.match_info["id"])
        body = await request.json()
        kw = body.get("keyword", "").strip()
        if not kw:
            return err("keyword is required", status=400)
        updated = await keyword_repo.update_keyword(
            keyword_id, kw, body.get("base_model"), body.get("model_type")
        )
        if not updated:
            return err("Not found", status=404)
        return ok()

    @routes.delete("/tiny-model-manager/api/filename-keywords/{id}")
    @json_route
    async def delete_keyword(request):
        keyword_id = int(request.match_info["id"])
        deleted = await keyword_repo.delete_keyword(keyword_id)
        if not deleted:
            return err("Not found", status=404)
        return ok()


def add_settings_routes(routes):

    @routes.get("/tiny-model-manager/api/settings")
    @json_route
    async def get_settings(request):
        return ok(_masked_settings(cfg.load_settings()))

    @routes.put("/tiny-model-manager/api/settings")
    @json_route
    async def update_settings(request):
        body = await request.json()
        existing = cfg.load_settings()
        old_organize = existing.get("organize_into_subfolders", False)
        _apply_masked_updates(existing, body)
        if "organize_into_subfolders" in body:
            new_val = bool(body["organize_into_subfolders"])
            conflict = await _organize_conflict(new_val and not old_organize)
            if conflict:
                return err(conflict, status=409)
            existing["organize_into_subfolders"] = new_val
        new_organize = existing.get("organize_into_subfolders", False)
        cfg.save_settings(existing)
        if not old_organize and new_organize:
            await _enqueue_reorganize("organize")
        elif old_organize and not new_organize:
            await _enqueue_reorganize("deorganize")
        return ok()

    _add_keyword_routes(routes)
