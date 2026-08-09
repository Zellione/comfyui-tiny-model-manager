"""Routes for importing models from another ComfyUI installation (F-154).

The module is named ``imports`` rather than ``import`` because the latter is a Python
keyword. It owns two job kinds, both defined in ``services/foreign_import``.
"""

import os

from ..services import foreign_import
from ._helpers import err, json_route, ok


def _selection_size(source_root: str, files: list[dict]) -> int:
    """Total bytes of the selected source files, skipping any that vanished."""
    total = 0
    for item in files:
        try:
            path = foreign_import.source_path(
                source_root, item.get("model_type", ""), item.get("filename", "")
            )
        except ValueError:
            continue
        total += os.path.getsize(path)
    return total


def _grouped_by_type(files: list[dict]) -> dict[str, list[dict]]:
    """Bucket a selection by ``model_type``, preserving the client's ordering."""
    by_type: dict[str, list[dict]] = {}
    for item in files:
        by_type.setdefault(item.get("model_type", ""), []).append(item)
    return by_type


def _space_error(root: str, files: list[dict]):
    """Check free space per destination; return an error response, or None when all fit.

    Each model type is checked against its own destination: a selection can span types
    that live on different filesystems, so one combined check against a single base would
    pass and then fail mid-copy.
    """
    for model_type, type_files in _grouped_by_type(files).items():
        try:
            base = foreign_import.dest_base(model_type)
            foreign_import.ensure_space(base, _selection_size(root, type_files))
        except ValueError as exc:
            return err(str(exc), status=400)
        except foreign_import.InsufficientSpaceError as exc:
            return err("insufficient_space", status=409, needed=exc.needed, available=exc.available)
    return None


def _job_response(job_id: str, kind: str):
    """Serialise a job of the expected kind, or 404 when it is absent or the wrong kind."""
    job = foreign_import.get_job(job_id)
    if job is None or job.kind != kind:
        return err("job_not_found", status=404)
    return ok(foreign_import.job_to_dict(job))


def add_imports_routes(routes):

    @routes.post("/tiny-model-manager/api/import/scan")
    @json_route
    async def start_scan(request):
        body = await request.json()
        try:
            root = foreign_import.validate_root(body.get("path", ""))
        except foreign_import.ForeignRootError as exc:
            return err(str(exc), status=400)
        job = foreign_import.start_scan(root)
        return ok({"job_id": job.id, "source_root": root})

    @routes.get("/tiny-model-manager/api/import/scan/{job_id}")
    @json_route
    async def get_scan(request):
        return _job_response(request.match_info["job_id"], "scan")

    @routes.post("/tiny-model-manager/api/import/start")
    @json_route
    async def start_import(request):
        body = await request.json()
        files = body.get("files") or []
        if not files:
            return err("no_files_selected", status=400)

        # Re-validate rather than trusting the client's root: this value came back from a
        # previous response, but it still arrives as request data and it becomes a path.
        try:
            root = foreign_import.validate_root(body.get("source_root", ""))
        except foreign_import.ForeignRootError as exc:
            return err(str(exc), status=400)

        space_error = _space_error(root, files)
        if space_error is not None:
            return space_error

        job = foreign_import.start_import(root, files)
        return ok({"job_id": job.id})

    @routes.get("/tiny-model-manager/api/import/jobs/{job_id}")
    @json_route
    async def get_import_job(request):
        return _job_response(request.match_info["job_id"], "import")

    @routes.post("/tiny-model-manager/api/import/jobs/{job_id}/cancel")
    @json_route
    async def cancel_import_job(request):
        # This route deliberately accepts BOTH job kinds (scan and import), unlike the GET
        # routes which are kind-specific. A scan hashes an entire library and can run for
        # minutes, so the UI must be able to abort it.
        job = foreign_import.get_job(request.match_info["job_id"])
        if job is None:
            return err("job_not_found", status=404)
        return ok({"cancelled": foreign_import.cancel_job(job.id)})
