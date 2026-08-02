from .. import config as cfg
from ..background import spawn
from ..db.database import init_db
from .catalog import add_catalog_routes
from .download import add_download_routes
from .images import add_images_routes
from .metadata import add_metadata_routes
from .models import add_model_routes
from .notifications import add_notification_routes
from .settings import add_settings_routes
from .static import add_static_routes
from .tags import add_tag_routes
from .workflow import register_workflow_routes
from .workflows import add_workflows_routes


def register_routes(routes, ext_dir: str):
    cfg.init(ext_dir)
    add_static_routes(routes, ext_dir)
    add_model_routes(routes)
    add_download_routes(routes)
    add_metadata_routes(routes)
    add_catalog_routes(routes)
    add_settings_routes(routes)
    add_notification_routes(routes)
    add_tag_routes(routes)
    # Singular: the ComfyUI node-insertion queue. Plural: the workflow store (F-129).
    register_workflow_routes(routes)
    add_workflows_routes(routes)
    add_images_routes(routes)

    async def _startup():
        await init_db()
        from ..services.downloader import resume_interrupted_downloads
        from ..services.media_cleanup import cleanup_stale_media
        from ..services.metadata_fetcher import migrate_existing_media
        from ..services.reconciler import prune_stale_models
        from ..services.reorganizer import process_pending_jobs

        await migrate_existing_media()
        await prune_stale_models()
        # After pruning, so media freed by records that vanished is swept in the same pass.
        await cleanup_stale_media()
        await process_pending_jobs()
        await resume_interrupted_downloads()

    spawn(_startup())
