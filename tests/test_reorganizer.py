"""Integration tests for py/services/reorganizer.py."""

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


class TestDeorganize:
    async def test_flattens_file_from_subfolder(self, setup):
        from py.db import model_repo
        from py.services.reorganizer import process_pending_jobs

        loras_dir = setup
        subfolder = os.path.join(loras_dir, "SDXL 1.0")
        os.makedirs(subfolder)
        src = os.path.join(subfolder, "my-lora.safetensors")
        open(src, "wb").close()

        await model_repo.upsert_model("SDXL 1.0/my-lora.safetensors", "loras", "", "", "")
        await model_repo.enqueue_reorganize("SDXL 1.0/my-lora.safetensors", "loras", "deorganize")

        await process_pending_jobs()

        assert os.path.exists(os.path.join(loras_dir, "my-lora.safetensors"))
        assert not os.path.exists(src)

    async def test_removes_empty_subfolder_after_flatten(self, setup):
        from py.db import model_repo
        from py.services.reorganizer import process_pending_jobs

        loras_dir = setup
        subfolder = os.path.join(loras_dir, "Pony")
        os.makedirs(subfolder)
        src = os.path.join(subfolder, "pony-lora.safetensors")
        open(src, "wb").close()

        await model_repo.upsert_model("Pony/pony-lora.safetensors", "loras", "", "", "")
        await model_repo.enqueue_reorganize("Pony/pony-lora.safetensors", "loras", "deorganize")

        await process_pending_jobs()

        assert not os.path.isdir(subfolder)

    async def test_skips_if_flat_destination_exists(self, setup):
        from py.db import model_repo
        from py.services.reorganizer import process_pending_jobs

        loras_dir = setup
        subfolder = os.path.join(loras_dir, "SDXL 1.0")
        os.makedirs(subfolder)
        src = os.path.join(subfolder, "clash.safetensors")
        flat = os.path.join(loras_dir, "clash.safetensors")
        open(src, "wb").close()
        open(flat, "wb").close()

        await model_repo.upsert_model("SDXL 1.0/clash.safetensors", "loras", "", "", "")
        await model_repo.enqueue_reorganize("SDXL 1.0/clash.safetensors", "loras", "deorganize")

        await process_pending_jobs()

        assert os.path.exists(src)
        assert os.path.exists(flat)

    async def test_updates_db_filename_after_flatten(self, setup):
        from py.db import model_repo
        from py.services.reorganizer import process_pending_jobs

        loras_dir = setup
        subfolder = os.path.join(loras_dir, "Unknown")
        os.makedirs(subfolder)
        src = os.path.join(subfolder, "unk.safetensors")
        open(src, "wb").close()

        await model_repo.upsert_model("Unknown/unk.safetensors", "loras", "", "", "")
        await model_repo.enqueue_reorganize("Unknown/unk.safetensors", "loras", "deorganize")

        await process_pending_jobs()

        row = await model_repo.get_model_by_filename("unk.safetensors")
        assert row is not None
        assert row["filename"] == "unk.safetensors"

    async def test_marks_job_done(self, setup):
        from py.db import model_repo
        from py.services.reorganizer import process_pending_jobs

        loras_dir = setup
        subfolder = os.path.join(loras_dir, "SDXL 1.0")
        os.makedirs(subfolder)
        open(os.path.join(subfolder, "done.safetensors"), "wb").close()

        await model_repo.upsert_model("SDXL 1.0/done.safetensors", "loras", "", "", "")
        await model_repo.enqueue_reorganize("SDXL 1.0/done.safetensors", "loras", "deorganize")

        await process_pending_jobs()

        remaining = await model_repo.get_pending_jobs("deorganize")
        assert len(remaining) == 0


class TestOrganize:
    async def test_moves_flat_file_to_subfolder(self, setup):
        from py.db import model_repo
        from py.services.reorganizer import process_pending_jobs

        loras_dir = setup
        src = os.path.join(loras_dir, "my-lora.safetensors")
        open(src, "wb").close()

        await model_repo.upsert_model(
            "my-lora.safetensors", "loras", "", "", "", base_model="SDXL 1.0"
        )
        await model_repo.enqueue_reorganize("my-lora.safetensors", "loras", "organize")

        await process_pending_jobs()

        assert os.path.exists(os.path.join(loras_dir, "SDXL 1.0", "my-lora.safetensors"))
        assert not os.path.exists(src)

    async def test_uses_unknown_subfolder_when_no_base_model(self, setup):
        from py.db import model_repo
        from py.services.reorganizer import process_pending_jobs

        loras_dir = setup
        src = os.path.join(loras_dir, "no-meta.safetensors")
        open(src, "wb").close()

        await model_repo.upsert_model("no-meta.safetensors", "loras", "", "", "")
        await model_repo.enqueue_reorganize("no-meta.safetensors", "loras", "organize")

        await process_pending_jobs()

        assert os.path.exists(os.path.join(loras_dir, "Unknown", "no-meta.safetensors"))
        assert not os.path.exists(src)

    async def test_skips_already_organized_file(self, setup):
        from py.db import model_repo
        from py.services.reorganizer import process_pending_jobs

        loras_dir = setup
        subfolder = os.path.join(loras_dir, "SDXL 1.0")
        os.makedirs(subfolder)
        src = os.path.join(subfolder, "already.safetensors")
        open(src, "wb").close()

        await model_repo.upsert_model(
            "SDXL 1.0/already.safetensors", "loras", "", "", "", base_model="SDXL 1.0"
        )
        await model_repo.enqueue_reorganize("SDXL 1.0/already.safetensors", "loras", "organize")

        await process_pending_jobs()

        # File not moved; job still completes
        assert os.path.exists(src)
        remaining = await model_repo.get_pending_jobs("organize")
        assert len(remaining) == 0

    async def test_updates_db_filename_after_organize(self, setup):
        from py.db import model_repo
        from py.services.reorganizer import process_pending_jobs

        loras_dir = setup
        src = os.path.join(loras_dir, "tracked.safetensors")
        open(src, "wb").close()

        await model_repo.upsert_model("tracked.safetensors", "loras", "", "", "", base_model="Pony")
        await model_repo.enqueue_reorganize("tracked.safetensors", "loras", "organize")

        await process_pending_jobs()

        row = await model_repo.get_model_by_filename("Pony/tracked.safetensors")
        assert row is not None
        assert row["filename"] == "Pony/tracked.safetensors"

    async def test_marks_organize_job_done(self, setup):
        from py.db import model_repo
        from py.services.reorganizer import process_pending_jobs

        loras_dir = setup
        src = os.path.join(loras_dir, "done2.safetensors")
        open(src, "wb").close()

        await model_repo.upsert_model("done2.safetensors", "loras", "", "", "", base_model="SD 1.5")
        await model_repo.enqueue_reorganize("done2.safetensors", "loras", "organize")

        await process_pending_jobs()

        remaining = await model_repo.get_pending_jobs("organize")
        assert len(remaining) == 0


class TestOrdering:
    async def test_organize_runs_before_deorganize(self, setup):
        """When both directions are pending, organize jobs complete first."""
        from py.db import model_repo
        from py.services.reorganizer import process_pending_jobs

        loras_dir = setup

        # Flat file to organize
        flat_src = os.path.join(loras_dir, "flat.safetensors")
        open(flat_src, "wb").close()
        await model_repo.upsert_model("flat.safetensors", "loras", "", "", "", base_model="Pony")
        await model_repo.enqueue_reorganize("flat.safetensors", "loras", "organize")

        # Organized file to deorganize
        sub = os.path.join(loras_dir, "SDXL 1.0")
        os.makedirs(sub)
        org_src = os.path.join(sub, "org.safetensors")
        open(org_src, "wb").close()
        await model_repo.upsert_model("SDXL 1.0/org.safetensors", "loras", "", "", "")
        await model_repo.enqueue_reorganize("SDXL 1.0/org.safetensors", "loras", "deorganize")

        await process_pending_jobs()

        assert os.path.exists(os.path.join(loras_dir, "Pony", "flat.safetensors"))
        assert os.path.exists(os.path.join(loras_dir, "org.safetensors"))
        assert not await model_repo.get_pending_jobs()


class TestOrganizeCatalogFallback:
    async def test_uses_catalog_entry_base_model_when_model_base_model_is_empty(self, setup):
        """When models.base_model is empty but catalog_entries.base_model is set,
        the organizer should move the file into the correct subfolder."""
        from py.db import model_repo
        from py.services.reorganizer import process_pending_jobs

        loras_dir = setup
        src = os.path.join(loras_dir, "nobase.safetensors")
        open(src, "wb").close()

        entry_id = await model_repo.upsert_catalog_entry(
            source_platform="civitai",
            source_page_id="999",
            source_page_url="https://civitai.com/models/999",
            display_name="Test",
            thumbnail_url="",
            base_model="SDXL 1.0",
        )
        # Model row has empty base_model
        await model_repo.upsert_model("nobase.safetensors", "loras", "civitai", "999", "")
        await model_repo.set_model_catalog_entry("nobase.safetensors", entry_id)
        await model_repo.enqueue_reorganize("nobase.safetensors", "loras", "organize")

        await process_pending_jobs()

        # File should have moved to the catalog entry's base_model subfolder
        assert os.path.exists(os.path.join(loras_dir, "SDXL 1.0", "nobase.safetensors"))
        assert not os.path.exists(src)
        # DB should now have base_model set on the models row
        row = await model_repo.get_model_by_filename("SDXL 1.0/nobase.safetensors")
        assert row is not None
        assert row["base_model"] == "SDXL 1.0"
