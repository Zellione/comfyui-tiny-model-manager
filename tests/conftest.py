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
    # Mirrors real ComfyUI: a module-level global read through a getter, so a test can
    # point the workflow export (F-129) at a tmp_path by patching the attribute.
    mod.base_path = os.path.dirname(models_dir)  # type: ignore[attr-defined]
    mod.user_directory = os.path.join(models_dir, "user")  # type: ignore[attr-defined]

    def get_user_directory() -> str:
        return mod.user_directory

    mod.get_user_directory = get_user_directory  # type: ignore[attr-defined]

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


@pytest.fixture
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


# ---------------------------------------------------------------------------
# Network isolation (issue #118)
# ---------------------------------------------------------------------------


class RealNetworkAccessError(RuntimeError):
    """Raised when a test tries to reach a host outside the loopback interface."""


def _loopback(host) -> bool:
    if isinstance(host, bytes):
        host = host.decode("utf-8", "replace")
    host = str(host)
    return host in ("localhost", "127.0.0.1", "::1", "0.0.0.0", "") or host.startswith("127.")


@pytest.fixture(autouse=True)
def block_network(monkeypatch):
    """Fail loudly on any real outbound connection instead of hanging CI.

    A real DNS lookup is resolved by ``loop.getaddrinfo``, which runs in asyncio's default
    ``ThreadPoolExecutor``.  pytest-asyncio tears down its per-test loop with
    ``asyncio.Runner.close()``, which calls ``loop.shutdown_default_executor()`` **without a
    timeout** — so it joins that worker thread forever.  When a CI runner's resolver stalls on
    a name, the whole suite wedges mid-test with no output and an orphan Python process, which
    is the intermittent backend hang tracked in issue #118.  ``httpx``'s ``connect`` timeout
    cannot interrupt it: the block is inside a C call on a thread, not on the event loop.

    Tests must therefore mock every outbound request.  Loopback stays open so aiohttp's test
    server keeps working.
    """
    import socket

    real_getaddrinfo = socket.getaddrinfo
    real_connect = socket.socket.connect
    real_connect_ex = socket.socket.connect_ex

    def guarded_getaddrinfo(host, port, *args, **kwargs):
        if not _loopback(host):
            raise RealNetworkAccessError(
                f"Test attempted a real DNS lookup for {host!r}:{port}. "
                "Mock the request — real network calls hang CI (issue #118)."
            )
        return real_getaddrinfo(host, port, *args, **kwargs)

    def guarded_connect(self, address):
        if isinstance(address, tuple) and not _loopback(address[0]):
            raise RealNetworkAccessError(
                f"Test attempted a real connection to {address!r}. "
                "Mock the request — real network calls hang CI (issue #118)."
            )
        return real_connect(self, address)

    def guarded_connect_ex(self, address):
        if isinstance(address, tuple) and not _loopback(address[0]):
            raise RealNetworkAccessError(
                f"Test attempted a real connection to {address!r}. "
                "Mock the request — real network calls hang CI (issue #118)."
            )
        return real_connect_ex(self, address)

    monkeypatch.setattr(socket, "getaddrinfo", guarded_getaddrinfo)
    monkeypatch.setattr(socket.socket, "connect", guarded_connect)
    monkeypatch.setattr(socket.socket, "connect_ex", guarded_connect_ex)
    yield
