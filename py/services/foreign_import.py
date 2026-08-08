"""Import models from another ComfyUI installation's models folder (F-154).

Two background jobs drive the feature. The *scan* job walks a foreign models root and
SHA-256s every file to decide which are already in the local library; the *import* job
copies the selected files in, registers them and enriches them from CivitAI.

Import is **copy only** by design: a move would break the source installation
irreversibly, and links need admin rights on Windows or a shared filesystem.
"""

import os

import folder_paths


class ForeignRootError(ValueError):
    """The supplied source path is not a usable foreign models root.

    The message is a stable error key (``path_not_absolute``, ``path_not_found``,
    ``path_is_local_root``) that the route layer hands to the UI for translation.
    """


def _local_model_roots() -> list[str]:
    """Every directory the local library already reads models from."""
    roots: list[str] = []
    models_dir = getattr(folder_paths, "models_dir", "")
    if models_dir:
        roots.append(models_dir)
    for dirs, _ in folder_paths.folder_names_and_paths.values():
        roots.extend(d for d in dirs if d)
    return roots


def _overlaps_local_library(real_root: str) -> bool:
    """True if ``real_root`` is, contains, or sits inside a local model directory.

    A containing directory counts: scanning it would list the local library's own files
    and the import would then copy them onto themselves.
    """
    for local in _local_model_roots():
        local_real = os.path.realpath(local)
        if (
            real_root == local_real
            or real_root.startswith(local_real + os.sep)
            or local_real.startswith(real_root + os.sep)
        ):
            return True
    return False


def validate_root(path: str) -> str:
    """Resolve a user-supplied foreign models root, or raise ``ForeignRootError``.

    A path holding a ``models`` subdirectory resolves to that subdirectory, so pasting a
    ComfyUI installation root works as well as pasting its models folder.
    """
    candidate = os.path.normpath(os.path.expanduser(path.strip())) if path.strip() else ""
    if not candidate or not os.path.isabs(candidate):
        raise ForeignRootError("path_not_absolute")
    if not os.path.isdir(candidate):
        raise ForeignRootError("path_not_found")

    nested = os.path.join(candidate, "models")
    if os.path.isdir(nested):
        candidate = nested

    real_root = os.path.realpath(candidate)
    if _overlaps_local_library(real_root):
        raise ForeignRootError("path_is_local_root")
    return real_root
