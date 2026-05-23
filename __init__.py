import os
from server import PromptServer
from .py.routes import register_routes
from .py.nodes.lora_loader_with_triggers import (
    NODE_CLASS_MAPPINGS as _LORA_NODES,
    NODE_DISPLAY_NAME_MAPPINGS as _LORA_NAMES,
)

_ext_dir = os.path.dirname(__file__)

register_routes(PromptServer.instance.routes, _ext_dir)

WEB_DIRECTORY = "./web"
NODE_CLASS_MAPPINGS = {**_LORA_NODES}
NODE_DISPLAY_NAME_MAPPINGS = {**_LORA_NAMES}
__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]
