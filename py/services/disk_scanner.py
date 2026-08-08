"""Disk scanning for model files across every configured model directory.

Extracted from ``py/routes/models.py`` so that both the unregistered-files route and the
auto-migration service (F-92) walk the library the same way.
"""

import os

import folder_paths

from .. import config as cfg

BROAD_EXTENSIONS = {".safetensors", ".ckpt", ".pt", ".bin", ".gguf", ".pth"}
SKIP_TYPES = {"configs", "custom_nodes"}


def scan_dir(base_dir: str, extensions: set) -> list:
    """Walk base_dir and return model file entries for matching extensions."""
    entries = []
    if not os.path.isdir(base_dir):
        return entries
    for root, _, files in os.walk(base_dir):
        for fname in files:
            if os.path.splitext(fname)[1].lower() in extensions:
                full = os.path.join(root, fname)
                rel = os.path.relpath(full, base_dir).replace("\\", "/")
                stat = os.stat(full)
                entries.append(
                    {
                        "filename": rel,
                        "base_dir": base_dir,
                        "size_bytes": stat.st_size,
                        "modified_at": stat.st_mtime,
                    }
                )
    return entries


def _scan_registered_types(result: dict, scanned: set) -> None:
    """Phase 1: scan every registered ComfyUI folder type into result."""
    for folder_type, (dirs, extensions) in folder_paths.folder_names_and_paths.items():
        if folder_type in SKIP_TYPES:
            continue
        models = []
        for base_dir in dirs:
            scanned.add(os.path.normpath(base_dir))
            models.extend(scan_dir(base_dir, set(extensions) | BROAD_EXTENSIONS))
        if models:
            result[folder_type] = models


def _scan_root_subdirs(result: dict, scanned: set, root: str, skip_types: bool) -> None:
    """Scan each subfolder of ``root`` not already covered, grouping files by folder name."""
    if not os.path.isdir(root):
        return
    for name in sorted(os.listdir(root)):
        if skip_types and name in SKIP_TYPES:
            continue
        physical = os.path.normpath(os.path.join(root, name))
        if not os.path.isdir(physical) or physical in scanned:
            continue
        scanned.add(physical)
        models = scan_dir(physical, BROAD_EXTENSIONS)
        if models:
            result.setdefault(name, []).extend(models)


def scan_all() -> dict[str, list[dict]]:
    """Scan every model directory, returning ``{model_type: [file entry, ...]}``.

    Entries are raw disk contents; the caller decides which of them are unregistered.
    """
    result: dict = {}
    scanned: set[str] = set()
    _scan_registered_types(result, scanned)
    _scan_root_subdirs(result, scanned, folder_paths.models_dir, skip_types=True)
    _scan_root_subdirs(result, scanned, os.path.join(cfg.data_dir(), "models"), skip_types=False)
    return result
