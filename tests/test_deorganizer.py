"""Integration tests for py/services/deorganizer.py."""

import os

import pytest


@pytest.fixture()
async def setup(ext_dir):
    import folder_paths

    models_dir = os.path.join(ext_dir, "models")
    loras_dir = os.path.join(models_dir, "loras")
    os.makedirs(loras_dir, exist_ok=True)
    folder_paths.models_dir = models_dir
    folder_paths.folder_names_and_paths["loras"] = ([loras_dir], {".safetensors"})
    return loras_dir


class TestProcessPendingJobs:
    async def test_flattens_file_from_subfolder(self, setup):
        from py.db import model_repo
        from py.services.deorganizer import process_pending_jobs

        loras_dir = setup
        subfolder = os.path.join(loras_dir, "SDXL 1.0")
        os.makedirs(subfolder)
        src = os.path.join(subfolder, "my-lora.safetensors")
        open(src, "wb").close()

        await model_repo.upsert_model("SDXL 1.0/my-lora.safetensors", "loras", "", "", "")
        await model_repo.enqueue_deorganize("SDXL 1.0/my-lora.safetensors", "loras")

        await process_pending_jobs()

        assert os.path.exists(os.path.join(loras_dir, "my-lora.safetensors"))
        assert not os.path.exists(src)

    async def test_removes_empty_subfolder_after_flatten(self, setup):
        from py.db import model_repo
        from py.services.deorganizer import process_pending_jobs

        loras_dir = setup
        subfolder = os.path.join(loras_dir, "Pony")
        os.makedirs(subfolder)
        src = os.path.join(subfolder, "pony-lora.safetensors")
        open(src, "wb").close()

        await model_repo.upsert_model("Pony/pony-lora.safetensors", "loras", "", "", "")
        await model_repo.enqueue_deorganize("Pony/pony-lora.safetensors", "loras")

        await process_pending_jobs()

        assert not os.path.isdir(subfolder)

    async def test_skips_if_flat_destination_exists(self, setup):
        from py.db import model_repo
        from py.services.deorganizer import process_pending_jobs

        loras_dir = setup
        subfolder = os.path.join(loras_dir, "SDXL 1.0")
        os.makedirs(subfolder)
        src = os.path.join(subfolder, "clash.safetensors")
        flat = os.path.join(loras_dir, "clash.safetensors")
        open(src, "wb").close()
        open(flat, "wb").close()

        await model_repo.upsert_model("SDXL 1.0/clash.safetensors", "loras", "", "", "")
        await model_repo.enqueue_deorganize("SDXL 1.0/clash.safetensors", "loras")

        await process_pending_jobs()

        # src not moved because flat target already exists
        assert os.path.exists(src)
        assert os.path.exists(flat)

    async def test_updates_db_filename_after_flatten(self, setup):
        from py.db import model_repo
        from py.services.deorganizer import process_pending_jobs

        loras_dir = setup
        subfolder = os.path.join(loras_dir, "Unknown")
        os.makedirs(subfolder)
        src = os.path.join(subfolder, "unk.safetensors")
        open(src, "wb").close()

        await model_repo.upsert_model("Unknown/unk.safetensors", "loras", "", "", "")
        await model_repo.enqueue_deorganize("Unknown/unk.safetensors", "loras")

        await process_pending_jobs()

        row = await model_repo.get_model_by_filename("unk.safetensors")
        assert row is not None
        assert row["filename"] == "unk.safetensors"

    async def test_marks_job_done(self, setup):
        from py.db import model_repo
        from py.services.deorganizer import process_pending_jobs

        loras_dir = setup
        subfolder = os.path.join(loras_dir, "SDXL 1.0")
        os.makedirs(subfolder)
        open(os.path.join(subfolder, "done.safetensors"), "wb").close()

        await model_repo.upsert_model("SDXL 1.0/done.safetensors", "loras", "", "", "")
        await model_repo.enqueue_deorganize("SDXL 1.0/done.safetensors", "loras")

        await process_pending_jobs()

        remaining = await model_repo.get_pending_deorganize_jobs()
        assert len(remaining) == 0
