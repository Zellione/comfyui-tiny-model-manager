import os
from server import PromptServer
from .py.routes import register_routes
from .py.nodes.lora_loader_with_triggers import (
    NODE_CLASS_MAPPINGS as _LORA_NODES,
    NODE_DISPLAY_NAME_MAPPINGS as _LORA_NAMES,
)
from .py.nodes.checkpoint_loader_with_triggers import (
    NODE_CLASS_MAPPINGS as _CKPT_NODES,
    NODE_DISPLAY_NAME_MAPPINGS as _CKPT_NAMES,
)
from .py.nodes.vae_loader import (
    NODE_CLASS_MAPPINGS as _VAE_NODES,
    NODE_DISPLAY_NAME_MAPPINGS as _VAE_NAMES,
)
from .py.nodes.controlnet_loader import (
    NODE_CLASS_MAPPINGS as _CN_NODES,
    NODE_DISPLAY_NAME_MAPPINGS as _CN_NAMES,
)
from .py.nodes.embedding_helper import (
    NODE_CLASS_MAPPINGS as _EMB_NODES,
    NODE_DISPLAY_NAME_MAPPINGS as _EMB_NAMES,
)
from .py.nodes.upscale_model_loader import (
    NODE_CLASS_MAPPINGS as _UP_NODES,
    NODE_DISPLAY_NAME_MAPPINGS as _UP_NAMES,
)

_ext_dir = os.path.dirname(__file__)

register_routes(PromptServer.instance.routes, _ext_dir)

WEB_DIRECTORY = "./web"
NODE_CLASS_MAPPINGS = {**_LORA_NODES, **_CKPT_NODES, **_VAE_NODES, **_CN_NODES, **_EMB_NODES, **_UP_NODES}
NODE_DISPLAY_NAME_MAPPINGS = {**_LORA_NAMES, **_CKPT_NAMES, **_VAE_NAMES, **_CN_NAMES, **_EMB_NAMES, **_UP_NAMES}
__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]
