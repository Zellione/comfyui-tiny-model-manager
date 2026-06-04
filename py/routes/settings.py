import asyncio
import os

from .. import config as cfg
from ._helpers import err, json_route, ok


def add_settings_routes(routes):

    @routes.get("/tiny-model-manager/api/settings")
    @json_route
    async def get_settings(request):
        data = cfg.load_settings()
        # Never send raw keys back — mask them
        safe = {
            "civitai_api_key": "***" if data.get("civitai_api_key") else "",
            "hf_token": "***" if data.get("hf_token") else "",
            "media_dir": data.get("media_dir", ""),
            "organize_into_subfolders": data.get("organize_into_subfolders", False),
            "media_dir_default": os.path.join(cfg.data_dir(), "media"),
        }
        return ok(safe)

    @routes.put("/tiny-model-manager/api/settings")
    @json_route
    async def update_settings(request):
        body = await request.json()
        existing = cfg.load_settings()
        old_organize = existing.get("organize_into_subfolders", False)
        # Only update keys that aren't the mask placeholder
        if body.get("civitai_api_key", "") not in ("", "***"):
            existing["civitai_api_key"] = body["civitai_api_key"]
        if body.get("hf_token", "") not in ("", "***"):
            existing["hf_token"] = body["hf_token"]
        if "media_dir" in body:
            existing["media_dir"] = body["media_dir"]
        if "organize_into_subfolders" in body:
            new_val = bool(body["organize_into_subfolders"])
            if new_val and not old_organize:
                from ..db import model_repo as _repo

                pending = await _repo.get_pending_jobs()
                if pending:
                    return err(
                        f"Cannot enable organizing while {len(pending)} model(s) "
                        "are still being reorganized. "
                        "Please wait for the current operation to complete.",
                        status=409,
                    )
            existing["organize_into_subfolders"] = new_val
        new_organize = existing.get("organize_into_subfolders", False)
        cfg.save_settings(existing)
        if not old_organize and new_organize:
            from ..db import model_repo
            from ..services import reorganizer

            models = await model_repo.get_all_models_slim()
            await model_repo.clear_pending_jobs("organize")
            for m in models:
                fname = m["filename"]
                if "/" not in fname and "\\" not in fname:
                    await model_repo.enqueue_reorganize(
                        fname, m.get("model_type") or "", "organize"
                    )
            asyncio.ensure_future(reorganizer.process_pending_jobs())
        elif old_organize and not new_organize:
            from ..db import model_repo
            from ..services import reorganizer

            models = await model_repo.get_all_models_slim()
            await model_repo.clear_pending_jobs("deorganize")
            for m in models:
                fname = m["filename"]
                if "/" in fname or "\\" in fname:
                    await model_repo.enqueue_reorganize(
                        fname, m.get("model_type") or "", "deorganize"
                    )
            asyncio.ensure_future(reorganizer.process_pending_jobs())
        return ok()
