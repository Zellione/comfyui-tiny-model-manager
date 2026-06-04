"""Unit tests for py/services/reconciler.py (startup stale-model pruning)."""

import os


def _models_dir(ext_dir: str, model_type: str) -> str:
    """Per-test model directory under the isolated data dir."""
    from py import config as cfg

    path = os.path.join(cfg.data_dir(), "models", model_type)
    os.makedirs(path, exist_ok=True)
    return path


def _touch(directory: str, rel_path: str) -> None:
    full = os.path.join(directory, rel_path)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "wb") as f:
        f.write(b"x")


class TestPruneStaleModels:
    async def test_prunes_model_when_dir_exists_but_file_absent(self, ext_dir):
        from py.db import model_repo
        from py.services.reconciler import prune_stale_models

        _models_dir(ext_dir, "recontype")  # directory exists, file does not
        await model_repo.upsert_model_with_meta(
            "absent.safetensors", "recontype", "civitai", "1", "d", trigger_words=[], tags=[]
        )

        pruned = await prune_stale_models()
        assert pruned == 1
        assert await model_repo.get_model_by_filename("absent.safetensors") is None

    async def test_keeps_model_when_file_present(self, ext_dir):
        from py.db import model_repo
        from py.services.reconciler import prune_stale_models

        d = _models_dir(ext_dir, "recontype")
        _touch(d, "present.safetensors")
        await model_repo.upsert_model_with_meta(
            "present.safetensors", "recontype", "civitai", "1", "d", trigger_words=[], tags=[]
        )

        pruned = await prune_stale_models()
        assert pruned == 0
        assert await model_repo.get_model_by_filename("present.safetensors") is not None

    async def test_keeps_model_in_subfolder_when_present(self, ext_dir):
        from py.db import model_repo
        from py.services.reconciler import prune_stale_models

        d = _models_dir(ext_dir, "recontype")
        _touch(d, os.path.join("Pony", "sub.safetensors"))
        await model_repo.upsert_model_with_meta(
            "Pony/sub.safetensors", "recontype", "civitai", "1", "d", trigger_words=[], tags=[]
        )

        pruned = await prune_stale_models()
        assert pruned == 0
        assert await model_repo.get_model_by_filename("Pony/sub.safetensors") is not None

    async def test_does_not_prune_when_directory_inaccessible(self, ext_dir):
        """If no candidate directory exists (e.g. unmounted storage), skip pruning."""
        from py.db import model_repo
        from py.services.reconciler import prune_stale_models

        # No directory is created for this type, so its storage looks unavailable.
        await model_repo.upsert_model_with_meta(
            "x.safetensors",
            "type-with-no-dir-xyz",
            "civitai",
            "1",
            "d",
            trigger_words=[],
            tags=[],
        )

        pruned = await prune_stale_models()
        assert pruned == 0
        assert await model_repo.get_model_by_filename("x.safetensors") is not None

    async def test_prunes_only_absent_records(self, ext_dir):
        from py.db import model_repo
        from py.services.reconciler import prune_stale_models

        d = _models_dir(ext_dir, "recontype")
        _touch(d, "keep.safetensors")
        for name in ("keep.safetensors", "gone-a.safetensors", "gone-b.safetensors"):
            await model_repo.upsert_model_with_meta(
                name, "recontype", "civitai", "1", "d", trigger_words=[], tags=[]
            )

        pruned = await prune_stale_models()
        assert pruned == 2
        assert await model_repo.get_model_by_filename("keep.safetensors") is not None
        assert await model_repo.get_model_by_filename("gone-a.safetensors") is None
        assert await model_repo.get_model_by_filename("gone-b.safetensors") is None
