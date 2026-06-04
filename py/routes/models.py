import os
import shutil

import folder_paths

from .. import config as cfg
from ..db import model_repo
from ..services.reorganizer import _sanitize_subfolder_name
from ._helpers import err, json_route, ok
from .metadata import _derive_source_url

_BROAD_EXTENSIONS = {".safetensors", ".ckpt", ".pt", ".bin", ".gguf", ".pth"}
_SKIP_TYPES = {"configs", "custom_nodes"}


def _scan_dir(base_dir: str, extensions: set) -> list:
    """Walk base_dir and return model file entries for matching extensions."""
    entries = []
    if not os.path.isdir(base_dir):
        return entries
    for root, _, files in os.walk(base_dir):
        for fname in files:
            if os.path.splitext(fname)[1].lower() in extensions:
                full = os.path.join(root, fname)
                rel = os.path.relpath(full, base_dir).replace("\\", "/")
                stat = os.stat(full)
                entries.append(
                    {
                        "filename": rel,
                        "base_dir": base_dir,
                        "size_bytes": stat.st_size,
                        "modified_at": stat.st_mtime,
                    }
                )
    return entries


def add_model_routes(routes):

    @routes.get("/tiny-model-manager/api/models")
    @json_route
    async def list_models(request):
        result = {}
        # Track every physical directory already covered so we don't double-count.
        scanned: set[str] = set()

        # 1. Registered ComfyUI folder types
        for folder_type, (dirs, extensions) in folder_paths.folder_names_and_paths.items():
            if folder_type in _SKIP_TYPES:
                continue
            models = []
            for base_dir in dirs:
                norm = os.path.normpath(base_dir)
                scanned.add(norm)
                models.extend(_scan_dir(base_dir, set(extensions) | _BROAD_EXTENSIONS))
            if models:
                result[folder_type] = models

        # 2. Physical subfolders of models_dir not covered by any registered path.
        #    Handles types like "unet"/"clip" that lost their folder_paths registration
        #    across ComfyUI versions, and any future custom folder.
        if os.path.isdir(folder_paths.models_dir):
            for name in sorted(os.listdir(folder_paths.models_dir)):
                if name in _SKIP_TYPES:
                    continue
                physical = os.path.normpath(os.path.join(folder_paths.models_dir, name))
                if not os.path.isdir(physical) or physical in scanned:
                    continue
                scanned.add(physical)
                models = _scan_dir(physical, _BROAD_EXTENSIONS)
                if models:
                    result.setdefault(name, []).extend(models)

        # 3. Legacy fallback location (data_dir/models/<type>) used by older versions
        #    of this plugin.  Surfaces already-downloaded files that ended up there.
        legacy_root = os.path.join(cfg.data_dir(), "models")
        if os.path.isdir(legacy_root):
            for name in sorted(os.listdir(legacy_root)):
                physical = os.path.normpath(os.path.join(legacy_root, name))
                if not os.path.isdir(physical) or physical in scanned:
                    continue
                scanned.add(physical)
                models = _scan_dir(physical, _BROAD_EXTENSIONS)
                if models:
                    result.setdefault(name, []).extend(models)
        all_filenames = [f["filename"] for files in result.values() for f in files]
        meta_map = await model_repo.get_metadata_by_filenames(all_filenames)
        for files in result.values():
            for f in files:
                m = meta_map.get(f["filename"])
                if m:
                    source_url = _derive_source_url(
                        m.get("source_platform", ""),
                        m.get("source_id", ""),
                        m.get("civitai_model_id", ""),
                    )
                    f["metadata"] = {
                        "description": m.get("description", ""),
                        "trigger_words": m.get("trigger_words", []),
                        "tags": m.get("tags", []),
                        "media": m.get("media", []),
                        "base_model": m.get("base_model", ""),
                        "source_platform": m.get("source_platform", ""),
                        "source_url": source_url,
                        "created_at": m.get("created_at", ""),
                    }
        return ok(result)

    @routes.delete("/tiny-model-manager/api/models/{model_type}/{path:.*}")
    @json_route
    async def delete_model(request):
        model_type = request.match_info["model_type"]
        rel_path = request.match_info["path"]
        dirs, _ = folder_paths.folder_names_and_paths.get(model_type, ([], set()))
        for base_dir in dirs:
            candidate = os.path.normpath(os.path.join(base_dir, rel_path))
            # Guard against path traversal
            if not candidate.startswith(os.path.normpath(base_dir)):
                continue
            if os.path.isfile(candidate):
                os.remove(candidate)
                await model_repo.delete_model_record(rel_path)
                return ok()
        return err("File not found", status=404)

    @routes.get("/tiny-model-manager/api/model-types")
    @json_route
    async def list_model_types(request):
        models_dir = folder_paths.models_dir
        types = []
        if os.path.isdir(models_dir):
            for name in os.listdir(models_dir):
                if name == "configs":
                    continue
                if os.path.isdir(os.path.join(models_dir, name)):
                    types.append(name)
        return ok(sorted(types))

    @routes.post("/tiny-model-manager/api/models/{model_type}/{path:.*}/move")
    @json_route
    async def move_model(request):
        model_type = request.match_info["model_type"]
        rel_path = request.match_info["path"]
        body = await request.json()
        new_type = body.get("new_type", "")

        # Validate new_type as a safe physical folder name under models_dir
        models_dir = folder_paths.models_dir
        dest_dir = os.path.normpath(os.path.join(models_dir, new_type))
        if (
            not new_type
            or new_type in ("configs", "custom_nodes")
            or not dest_dir.startswith(os.path.normpath(models_dir) + os.sep)
        ):
            return err("Unknown model type", status=400)

        # Locate source file. The type dropdown and the move destination both use
        # physical folder names under models_dir, but some physical folders (e.g.
        # "clip") are not registered folder_paths keys. Search the physical folder
        # first, then any registered dirs for the type, so a model previously moved
        # into a physical-only folder can still be relocated.
        src = None
        src_dirs = [os.path.join(models_dir, model_type)]
        registered, _ = folder_paths.folder_names_and_paths.get(model_type, ([], set()))
        src_dirs.extend(registered)
        for base_dir in src_dirs:
            base_norm = os.path.normpath(base_dir)
            candidate = os.path.normpath(os.path.join(base_dir, rel_path))
            if not candidate.startswith(base_norm + os.sep):
                continue
            if os.path.isfile(candidate):
                src = candidate
                break
        if not src:
            return err("File not found", status=404)

        # Destination is the literal models/<new_type> folder
        dest = os.path.normpath(os.path.join(dest_dir, rel_path))
        if not dest.startswith(dest_dir + os.sep):
            return err("Invalid destination path", status=400)
        if os.path.normpath(src) == dest:
            return ok()  # already in target folder
        if os.path.exists(dest):
            return err("Target file already exists", status=409)

        os.makedirs(os.path.dirname(dest), exist_ok=True)
        shutil.move(src, dest)

        # filename column unchanged; only model_type is updated
        await model_repo.update_model_type(rel_path, new_type)
        return ok()

    @routes.post("/tiny-model-manager/api/models/organize")
    @json_route
    async def organize_models(request):
        models = await model_repo.get_all_models_slim()
        moved = skipped = errors = 0

        for model in models:
            filename: str = model["filename"]
            model_type: str = model.get("model_type") or ""
            base_model: str = model.get("base_model") or ""

            # Resolve source file on disk
            try:
                base_dirs = folder_paths.get_folder_paths(model_type)
            except Exception:
                base_dirs = [os.path.join(folder_paths.models_dir, model_type)]

            src = None
            src_base_dir = None
            for base_dir in base_dirs:
                norm_base = os.path.normpath(base_dir)
                candidate = os.path.normpath(os.path.join(base_dir, filename))
                if not candidate.startswith(norm_base):
                    continue
                if os.path.isfile(candidate):
                    src = candidate
                    src_base_dir = base_dir
                    break

            if not src or not src_base_dir:
                skipped += 1
                continue

            basename = os.path.basename(filename)
            subfolder = _sanitize_subfolder_name(base_model)
            target_rel = subfolder + "/" + basename

            if filename == target_rel:
                skipped += 1
                continue

            target_abs = os.path.join(src_base_dir, target_rel)
            if os.path.exists(target_abs):
                skipped += 1
                continue

            try:
                os.makedirs(os.path.dirname(target_abs), exist_ok=True)
                shutil.move(src, target_abs)
                await model_repo.update_model_filename(filename, target_rel)
                moved += 1
            except Exception:
                errors += 1

        return ok({"moved": moved, "skipped": skipped, "errors": errors})

    @routes.get("/tiny-model-manager/api/reorganize/pending")
    @json_route
    async def get_pending_reorganize(request):
        jobs = await model_repo.get_pending_jobs()
        return ok([j["filename"] for j in jobs])
