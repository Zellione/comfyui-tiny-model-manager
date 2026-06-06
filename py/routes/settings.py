import os

from .. import config as cfg
from ..background import spawn
from ._helpers import err, json_route, ok


def _masked_settings(data: dict) -> dict:
    """Return the settings payload with secret keys masked for the client."""
    return {
        "civitai_api_key": "***" if data.get("civitai_api_key") else "",
        "hf_token": "***" if data.get("hf_token") else "",
        "media_dir": data.get("media_dir", ""),
        "organize_into_subfolders": data.get("organize_into_subfolders", False),
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
