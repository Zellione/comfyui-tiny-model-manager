"""
Root-level conftest — loaded by pytest before any Package.setup() call.

Two jobs:
1. Install ComfyUI stubs into sys.modules early enough that the project's
   own __init__.py (which does ``from server import PromptServer``) never
   triggers a real import of server.py.
2. Patch Package.setup() so that importing the project root's __init__.py
   (which uses relative imports and runs register_routes at module level) is
   skipped gracefully; stubs installed here are sufficient for all tests.
"""

import os
import sys
import types

# ---------------------------------------------------------------------------
# ComfyUI stub installation — must happen at module import time
# ---------------------------------------------------------------------------

_MODELS_DIR = os.path.join(os.path.dirname(__file__), "_test_models")
os.makedirs(_MODELS_DIR, exist_ok=True)


def _make_folder_paths_stub(models_dir: str) -> types.ModuleType:
    mod = types.ModuleType("folder_paths")
    mod.models_dir = models_dir  # type: ignore[attr-defined]
    mod.folder_names_and_paths = {}  # type: ignore[attr-defined]

    def get_folder_paths(folder_type: str) -> list[str]:
        info = mod.folder_names_and_paths.get(folder_type)
        if info:
            return info[0]
        return [os.path.join(models_dir, folder_type)]

    def get_filename_list(folder_type: str) -> list[str]:
        folder = os.path.join(models_dir, folder_type)
        if os.path.isdir(folder):
            return sorted(os.listdir(folder))
        return []

    def get_full_path(folder_type: str, filename: str) -> str | None:
        return os.path.join(os.path.join(models_dir, folder_type), filename)

    mod.get_folder_paths = get_folder_paths  # type: ignore[attr-defined]
    mod.get_filename_list = get_filename_list  # type: ignore[attr-defined]
    mod.get_full_path = get_full_path  # type: ignore[attr-defined]
    return mod


def _install_stubs() -> None:
    sys.modules.setdefault("folder_paths", _make_folder_paths_stub(_MODELS_DIR))

    server_mod = types.ModuleType("server")
    server_mod.PromptServer = types.SimpleNamespace(  # type: ignore[attr-defined]
        instance=types.SimpleNamespace(routes=types.SimpleNamespace())
    )
    sys.modules.setdefault("server", server_mod)

    for name in (
        "comfy",
        "comfy.sd",
        "comfy.utils",
        "comfy.controlnet",
        "comfy_extras",
        "comfy_extras.chainner_models",
    ):
        sys.modules.setdefault(name, types.ModuleType(name))

    comfy_sd = sys.modules["comfy.sd"]
    if not hasattr(comfy_sd, "load_lora_for_models"):
        comfy_sd.load_lora_for_models = lambda m, c, lora, sm, sc: (m, c)  # type: ignore[attr-defined]
    comfy_utils = sys.modules["comfy.utils"]
    if not hasattr(comfy_utils, "load_torch_file"):
        comfy_utils.load_torch_file = lambda path, safe_load=True: {}  # type: ignore[attr-defined]
    sys.modules["comfy"].sd = sys.modules["comfy.sd"]  # type: ignore[attr-defined]
    sys.modules["comfy"].utils = sys.modules["comfy.utils"]  # type: ignore[attr-defined]
    sys.modules["comfy"].controlnet = sys.modules["comfy.controlnet"]  # type: ignore[attr-defined]
    sys.modules["comfy_extras"].chainner_models = sys.modules["comfy_extras.chainner_models"]  # type: ignore[attr-defined]


_install_stubs()

# ---------------------------------------------------------------------------
# Ensure the local py/ package takes precedence over the installed py.py
# module (a pytest support library).  We put the project root at sys.path[0]
# and evict any cached entry that points to the wrong module.
# ---------------------------------------------------------------------------

_PROJECT_ROOT_STR = os.path.dirname(os.path.abspath(__file__))
if _PROJECT_ROOT_STR not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT_STR)

_cached_py = sys.modules.get("py")
if _cached_py is not None:
    # If the cached 'py' is not our local package, remove it so the next import
    # resolves to our py/ directory instead of the installed py.py module.
    cached_file = getattr(_cached_py, "__file__", "") or ""
    if not cached_file.startswith(_PROJECT_ROOT_STR):
        sys.modules.pop("py", None)

# ---------------------------------------------------------------------------
# Patch Package.setup() to skip importing the project root __init__.py.
# The project's __init__.py cannot be imported as a standalone module because
# it uses relative imports and calls register_routes() at module level.
# Stubs installed above are sufficient; no package-level initialisation is
# needed for the test suite.
# ---------------------------------------------------------------------------

import _pytest.python as _pp  # noqa: E402

_PROJECT_ROOT = os.path.normpath(os.path.dirname(__file__))
_orig_pkg_setup = _pp.Package.setup


def _safe_pkg_setup(self: "_pp.Package") -> None:
    init_path = os.path.normpath(str(self.path / "__init__.py"))
    project_init = os.path.normpath(os.path.join(_PROJECT_ROOT, "__init__.py"))
    if init_path == project_init:
        return  # skip — stubs already installed
    _orig_pkg_setup(self)


_pp.Package.setup = _safe_pkg_setup  # type: ignore[method-assign]
