"""
Shared test fixtures and ComfyUI stubs.

IMPORTANT: ComfyUI stubs are installed at module-import time (top level below),
not inside a fixture.  pytest imports conftest.py during the *collection* phase,
before it calls Package.setup() which would otherwise try to import the real
server.py from the ComfyUI directory tree.
"""

import os
import sys
import tempfile
import types

import pytest

# ---------------------------------------------------------------------------
# Build ComfyUI stub modules
# ---------------------------------------------------------------------------

_MODELS_DIR = tempfile.mkdtemp(prefix="comfyui_models_")

_COMFY_SD = "comfy.sd"
_COMFY_UTILS = "comfy.utils"


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
        folder = os.path.join(models_dir, folder_type)
        return os.path.join(folder, filename)

    mod.get_folder_paths = get_folder_paths  # type: ignore[attr-defined]
    mod.get_filename_list = get_filename_list  # type: ignore[attr-defined]
    mod.get_full_path = get_full_path  # type: ignore[attr-defined]
    return mod


def _install_stubs(models_dir: str) -> None:
    """Put all ComfyUI stubs into sys.modules if not already present."""
    sys.modules.setdefault("folder_paths", _make_folder_paths_stub(models_dir))

    server_mod = types.ModuleType("server")
    routes_stub = types.SimpleNamespace()
    server_mod.PromptServer = types.SimpleNamespace(  # type: ignore[attr-defined]
        instance=types.SimpleNamespace(routes=routes_stub)
    )
    sys.modules.setdefault("server", server_mod)

    for name in (
        "comfy",
        _COMFY_SD,
        _COMFY_UTILS,
        "comfy.controlnet",
        "comfy_extras",
        "comfy_extras.chainner_models",
    ):
        sys.modules.setdefault(name, types.ModuleType(name))

    comfy_sd = sys.modules[_COMFY_SD]
    if not hasattr(comfy_sd, "load_lora_for_models"):
        comfy_sd.load_lora_for_models = lambda m, c, lora, sm, sc: (m, c)  # type: ignore[attr-defined]

    comfy_utils = sys.modules[_COMFY_UTILS]
    if not hasattr(comfy_utils, "load_torch_file"):
        comfy_utils.load_torch_file = lambda path, safe_load=True: {}  # type: ignore[attr-defined]

    # Wire sub-module attributes so ``comfy.sd`` etc. resolve after import
    sys.modules["comfy"].sd = sys.modules[_COMFY_SD]  # type: ignore[attr-defined]
    sys.modules["comfy"].utils = sys.modules[_COMFY_UTILS]  # type: ignore[attr-defined]
    sys.modules["comfy"].controlnet = sys.modules["comfy.controlnet"]  # type: ignore[attr-defined]
    sys.modules["comfy_extras"].chainner_models = sys.modules["comfy_extras.chainner_models"]  # type: ignore[attr-defined]


# Install stubs NOW — at conftest import time — before any Package.setup() runs.
_install_stubs(_MODELS_DIR)

# ---------------------------------------------------------------------------
# Per-test extension-dir fixture (isolated data dir + fresh DB)
# ---------------------------------------------------------------------------


@pytest.fixture()
async def ext_dir(tmp_path):
    """Fresh extension directory with an initialised DB for each test."""
    from py import config as cfg
    from py.db.database import init_db

    cfg.init(str(tmp_path))
    await init_db()
    yield str(tmp_path)


# ---------------------------------------------------------------------------
# Per-test downloader reset (event-loop isolation)
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def reset_downloader_state():
    """Give every test a download queue bound to its own event loop.

    ``downloader._queue`` is built at import time and ``asyncio.Queue`` binds itself to the
    first loop that uses it, refusing any other one afterwards.  ``_worker`` is an uncancelled
    ``while True`` task that parks on ``await _queue.get()``, and pytest-asyncio hands each test
    a fresh loop — so without this reset the worker from an earlier test keeps a getter on a
    closed loop and the queue silently stops draining, which hung CI indefinitely.

    Deliberately synchronous: an async autouse fixture would force a loop onto every test, and
    ``asyncio.Queue()`` binds lazily, so building it here correctly attaches it to the loop of
    the test that is about to run.
    """
    import asyncio

    from py import background
    from py.services import downloader as dl

    for task in list(background._background_tasks):
        if not task.done():
            # The task's loop is usually already closed, which makes cancel() raise.
            try:
                task.cancel()
            except RuntimeError:
                pass
    background._background_tasks.clear()

    dl._tasks.clear()
    dl._worker_started = False
    dl._queue = asyncio.Queue()
    yield
