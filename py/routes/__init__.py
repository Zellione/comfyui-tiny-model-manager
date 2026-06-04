import asyncio

from .. import config as cfg
from ..db.database import init_db
from .catalog import add_catalog_routes
from .download import add_download_routes
from .metadata import add_metadata_routes
from .models import add_model_routes
from .notifications import add_notification_routes
from .settings import add_settings_routes
from .static import add_static_routes
from .workflow import register_workflow_routes


def register_routes(routes, ext_dir: str):
    cfg.init(ext_dir)
    add_static_routes(routes, ext_dir)
    add_model_routes(routes)
    add_download_routes(routes)
    add_metadata_routes(routes)
    add_catalog_routes(routes)
    add_settings_routes(routes)
    add_notification_routes(routes)
    register_workflow_routes(routes)

    async def _startup():
        await init_db()
        from ..services.metadata_fetcher import migrate_existing_media
        from ..services.reconciler import prune_stale_models
        from ..services.reorganizer import process_pending_jobs

        await migrate_existing_media()
        await prune_stale_models()
        await process_pending_jobs()

    asyncio.ensure_future(_startup())
