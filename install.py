"""Post-install hook run by ComfyUI-Manager from the custom node root.

Published Registry packages always ship a prebuilt ``web/``, so this script is a no-op there.
It exists for source checkouts ("Install via Git URL", manual clone) where the Angular bundle
has never been built.

This script never fails the install. ComfyUI-Manager treats a non-zero exit as a failed
installation, and an unbuilt dashboard is not a reason to reject the node: the loader nodes
themselves work fine without it.
"""

import os
import shutil
import subprocess
import sys

_ROOT = os.path.dirname(os.path.abspath(__file__))
_WEB_INDEX = os.path.join(_ROOT, "web", "index.html")
_FRONTEND_DIR = os.path.join(_ROOT, "frontend")

_PREFIX = "[tiny-model-manager]"
_MANUAL_BUILD_HINT = f"""{_PREFIX} The web dashboard is not built and Node.js was not found.
  The loader nodes still work; only the dashboard at /tiny-model-manager is unavailable.
  To build it, install Node.js 22+ and run:
      cd frontend && npm install && npx ng build
  See https://github.com/Zellione/comfyui-tiny-model-manager#manual-installation"""


def build_frontend() -> bool:
    """Build the Angular bundle into ``web/``.

    Returns ``False`` when the Node.js toolchain is unavailable; raises on build failure.
    """
    npm = shutil.which("npm")
    npx = shutil.which("npx")
    if npm is None or npx is None:
        return False

    print(f"{_PREFIX} Building the web dashboard (this runs npm install once)...")
    subprocess.run([npm, "install"], cwd=_FRONTEND_DIR, check=True)
    subprocess.run([npx, "ng", "build"], cwd=_FRONTEND_DIR, check=True)
    return True


def main() -> int:
    if os.path.isfile(_WEB_INDEX):
        return 0

    if not os.path.isdir(_FRONTEND_DIR):
        # Registry packages strip frontend/ but always ship a prebuilt web/, so reaching this
        # branch means the package is incomplete rather than merely unbuilt.
        print(f"{_PREFIX} No prebuilt web/ bundle and no frontend/ sources to build from.")
        return 0

    try:
        if build_frontend():
            print(f"{_PREFIX} Web dashboard built successfully.")
            return 0
    except (subprocess.CalledProcessError, OSError) as exc:
        print(f"{_PREFIX} Frontend build failed: {exc}")

    print(_MANUAL_BUILD_HINT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
