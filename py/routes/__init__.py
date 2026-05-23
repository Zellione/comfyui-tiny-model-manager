import asyncio
from .static import add_static_routes
from .models import add_model_routes
from .download import add_download_routes
from .metadata import add_metadata_routes
from .settings import add_settings_routes
from .. import config as cfg
from ..db.database import init_db


def register_routes(routes, ext_dir: str):
    cfg.init(ext_dir)
    add_static_routes(routes, ext_dir)
    add_model_routes(routes)
    add_download_routes(routes)
    add_metadata_routes(routes)
    add_settings_routes(routes)
    asyncio.ensure_future(init_db())
