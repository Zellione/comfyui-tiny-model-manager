"""Unit tests for py/services/foreign_import.py (F-154)."""

import os

import pytest


class TestValidateRoot:
    def test_relative_path_rejected(self, ext_dir):
        from py.services import foreign_import

        with pytest.raises(foreign_import.ForeignRootError) as excinfo:
            foreign_import.validate_root("some/relative/dir")
        assert str(excinfo.value) == "path_not_absolute"

    def test_blank_path_rejected(self, ext_dir):
        from py.services import foreign_import

        with pytest.raises(foreign_import.ForeignRootError):
            foreign_import.validate_root("   ")

    def test_missing_path_rejected(self, tmp_path, ext_dir):
        from py.services import foreign_import

        missing = str(tmp_path / "nope")
        with pytest.raises(foreign_import.ForeignRootError) as excinfo:
            foreign_import.validate_root(missing)
        assert str(excinfo.value) == "path_not_found"

    def test_file_is_not_a_directory(self, tmp_path, ext_dir):
        from py.services import foreign_import

        target = tmp_path / "a.txt"
        target.write_text("x")
        with pytest.raises(foreign_import.ForeignRootError) as excinfo:
            foreign_import.validate_root(str(target))
        assert str(excinfo.value) == "path_not_found"

    def test_models_subdir_is_appended(self, tmp_path, ext_dir):
        from py.services import foreign_import

        (tmp_path / "models" / "loras").mkdir(parents=True)
        resolved = foreign_import.validate_root(str(tmp_path))
        assert resolved == os.path.realpath(str(tmp_path / "models"))

    def test_models_root_used_as_is(self, tmp_path, ext_dir):
        from py.services import foreign_import

        root = tmp_path / "models"
        (root / "loras").mkdir(parents=True)
        resolved = foreign_import.validate_root(str(root))
        assert resolved == os.path.realpath(str(root))

    def test_local_models_root_rejected(self, tmp_path, monkeypatch, ext_dir):
        import folder_paths

        from py.services import foreign_import

        local = tmp_path / "local_models"
        (local / "loras").mkdir(parents=True)
        monkeypatch.setattr(folder_paths, "models_dir", str(local))
        with pytest.raises(foreign_import.ForeignRootError) as excinfo:
            foreign_import.validate_root(str(local))
        assert str(excinfo.value) == "path_is_local_root"

    def test_parent_of_local_root_rejected(self, tmp_path, monkeypatch, ext_dir):
        import folder_paths

        from py.services import foreign_import

        local = tmp_path / "comfy" / "models"
        (local / "loras").mkdir(parents=True)
        monkeypatch.setattr(folder_paths, "models_dir", str(local))
        with pytest.raises(foreign_import.ForeignRootError) as excinfo:
            foreign_import.validate_root(str(tmp_path / "comfy"))
        assert str(excinfo.value) == "path_is_local_root"

    def test_registered_folder_dir_rejected(self, tmp_path, monkeypatch, ext_dir):
        import folder_paths

        from py.services import foreign_import

        custom = tmp_path / "extra" / "loras"
        custom.mkdir(parents=True)
        monkeypatch.setattr(
            folder_paths, "folder_names_and_paths", {"loras": ([str(custom)], {".safetensors"})}
        )
        with pytest.raises(foreign_import.ForeignRootError) as excinfo:
            foreign_import.validate_root(str(custom))
        assert str(excinfo.value) == "path_is_local_root"


def _make_source_tree(tmp_path):
    """Build a small foreign models root and return its path."""
    root = tmp_path / "foreign" / "models"
    (root / "checkpoints").mkdir(parents=True)
    (root / "loras" / "style").mkdir(parents=True)
    (root / "configs").mkdir(parents=True)
    (root / "checkpoints" / "sd15.safetensors").write_bytes(b"a" * 16)
    (root / "loras" / "style" / "neon.safetensors").write_bytes(b"b" * 32)
    (root / "loras" / "notes.txt").write_text("ignored")
    (root / "configs" / "cfg.safetensors").write_bytes(b"c" * 8)
    (root / "loose.safetensors").write_bytes(b"d" * 4)
    return root


class TestScanSource:
    def test_groups_by_type_subfolder(self, tmp_path, ext_dir):
        from py.services import foreign_import

        files = foreign_import.scan_source(str(_make_source_tree(tmp_path)))
        assert {f.model_type for f in files} == {"checkpoints", "loras"}

    def test_preserves_relative_subfolder(self, tmp_path, ext_dir):
        from py.services import foreign_import

        files = foreign_import.scan_source(str(_make_source_tree(tmp_path)))
        lora = next(f for f in files if f.model_type == "loras")
        assert lora.filename == "style/neon.safetensors"

    def test_records_absolute_path_and_size(self, tmp_path, ext_dir):
        from py.services import foreign_import

        root = _make_source_tree(tmp_path)
        files = foreign_import.scan_source(str(root))
        ckpt = next(f for f in files if f.model_type == "checkpoints")
        assert ckpt.abs_path == os.path.join(str(root), "checkpoints", "sd15.safetensors")
        assert ckpt.size_bytes == 16

    def test_non_model_extensions_ignored(self, tmp_path, ext_dir):
        from py.services import foreign_import

        files = foreign_import.scan_source(str(_make_source_tree(tmp_path)))
        assert all(not f.filename.endswith(".txt") for f in files)

    def test_skip_types_ignored(self, tmp_path, ext_dir):
        from py.services import foreign_import

        files = foreign_import.scan_source(str(_make_source_tree(tmp_path)))
        assert all(f.model_type != "configs" for f in files)

    def test_loose_files_at_root_ignored(self, tmp_path, ext_dir):
        """A file directly in the models root has no type subfolder, so it has no type."""
        from py.services import foreign_import

        files = foreign_import.scan_source(str(_make_source_tree(tmp_path)))
        assert all(f.filename != "loose.safetensors" for f in files)

    def test_files_start_pending_and_unhashed(self, tmp_path, ext_dir):
        from py.services import foreign_import

        files = foreign_import.scan_source(str(_make_source_tree(tmp_path)))
        assert {f.status for f in files} == {"pending"}
        assert all(f.file_hash == "" for f in files)


class TestScanJob:
    async def test_marks_unknown_files_new(self, tmp_path, ext_dir):
        from py.services import foreign_import

        root = _make_source_tree(tmp_path)
        job = foreign_import.start_scan(str(root))
        await job.task
        assert job.state == "done"
        assert {f.status for f in job.files} == {"new"}
        assert job.progress == 100.0

    async def test_marks_locally_present_hash_installed(self, tmp_path, monkeypatch, ext_dir):
        from py.db import model_repo
        from py.services import foreign_import, model_paths

        root = _make_source_tree(tmp_path)
        known = model_paths.compute_file_hash(str(root / "checkpoints" / "sd15.safetensors"))
        await model_repo.register_model("sd15.safetensors", "checkpoints")
        await model_repo.set_file_hash("sd15.safetensors", known)
        monkeypatch.setattr(foreign_import, "_hash_unknown_local_files", _noop_local_hashes)

        job = foreign_import.start_scan(str(root))
        await job.task
        statuses = {f.filename: f.status for f in job.files}
        assert statuses["sd15.safetensors"] == "installed"
        assert statuses["style/neon.safetensors"] == "new"

    async def test_unreadable_file_does_not_fail_the_job(self, tmp_path, monkeypatch, ext_dir):
        from py.services import foreign_import

        root = _make_source_tree(tmp_path)
        monkeypatch.setattr(foreign_import, "_hash_unknown_local_files", _noop_local_hashes)

        def boom(path):
            if path.endswith("sd15.safetensors"):
                raise OSError("permission denied")
            return "deadbeef"

        monkeypatch.setattr(foreign_import.model_paths, "compute_file_hash", boom)
        job = foreign_import.start_scan(str(root))
        await job.task
        assert job.state == "done"
        statuses = {f.filename: f.status for f in job.files}
        assert statuses["sd15.safetensors"] == "unreadable"

    async def test_local_hashes_are_cached_back_to_the_db(self, tmp_path, monkeypatch, ext_dir):
        import folder_paths

        from py.db import model_repo
        from py.services import foreign_import, model_paths

        local = tmp_path / "local" / "models"
        (local / "loras").mkdir(parents=True)
        (local / "loras" / "known.safetensors").write_bytes(b"z" * 12)
        monkeypatch.setattr(folder_paths, "models_dir", str(local))
        await model_repo.register_model("known.safetensors", "loras")

        root = _make_source_tree(tmp_path)
        job = foreign_import.start_scan(str(root))
        await job.task

        expected = model_paths.compute_file_hash(str(local / "loras" / "known.safetensors"))
        assert await model_repo.get_file_hash_map() == {expected: "known.safetensors"}

    async def test_cancel_stops_the_scan(self, tmp_path, monkeypatch, ext_dir):
        from py.services import foreign_import

        root = _make_source_tree(tmp_path)
        monkeypatch.setattr(foreign_import, "_hash_unknown_local_files", _noop_local_hashes)
        job = foreign_import.start_scan(str(root))
        foreign_import.cancel_job(job.id)
        await job.task
        assert job.state == "cancelled"

    async def test_get_job_and_serialisation(self, tmp_path, ext_dir):
        from py.services import foreign_import

        root = _make_source_tree(tmp_path)
        job = foreign_import.start_scan(str(root))
        await job.task
        assert foreign_import.get_job(job.id) is job
        assert foreign_import.get_job("nope") is None
        payload = foreign_import.job_to_dict(job)
        assert payload["state"] == "done"
        assert payload["source_root"] == str(root)
        assert {f["status"] for f in payload["files"]} == {"new"}
        assert "abs_path" not in payload["files"][0]


async def _noop_local_hashes() -> set[str]:
    """Stand-in for the local-library hash sweep, which needs no files in most tests."""
    from py.db import model_repo

    return set(await model_repo.get_file_hash_map())


class TestDestinationAndCopy:
    def test_dest_base_uses_first_candidate_dir(self, tmp_path, monkeypatch, ext_dir):
        import folder_paths

        from py.services import foreign_import

        monkeypatch.setattr(folder_paths, "models_dir", str(tmp_path / "local"))
        assert foreign_import.dest_base("loras") == os.path.join(str(tmp_path / "local"), "loras")

    def test_unsafe_model_type_rejected(self, ext_dir):
        from py.services import foreign_import

        with pytest.raises(ValueError, match="invalid_model_type"):
            foreign_import.dest_base("..")

    def test_traversing_filename_rejected(self, tmp_path, monkeypatch, ext_dir):
        import folder_paths

        from py.services import foreign_import

        monkeypatch.setattr(folder_paths, "models_dir", str(tmp_path / "local"))
        with pytest.raises(ValueError, match="unsafe_filename"):
            foreign_import.resolve_destination("loras", "../../escape.safetensors")

    def test_resolve_destination_keeps_subfolder(self, tmp_path, monkeypatch, ext_dir):
        import folder_paths

        from py.services import foreign_import

        monkeypatch.setattr(folder_paths, "models_dir", str(tmp_path / "local"))
        dest = foreign_import.resolve_destination("loras", "style/neon.safetensors")
        assert dest.endswith(os.path.join("loras", "style", "neon.safetensors"))

    def test_copy_creates_the_file(self, tmp_path, ext_dir):
        from py.services import foreign_import

        src = tmp_path / "src.safetensors"
        src.write_bytes(b"payload")
        dest = tmp_path / "out" / "dest.safetensors"
        final = foreign_import.copy_file(str(src), str(dest))
        assert final == str(dest)
        assert (tmp_path / "out" / "dest.safetensors").read_bytes() == b"payload"

    def test_copy_suffixes_on_collision(self, tmp_path, ext_dir):
        from py.services import foreign_import

        src = tmp_path / "src.safetensors"
        src.write_bytes(b"payload")
        dest = tmp_path / "dest.safetensors"
        dest.write_bytes(b"existing")
        final = foreign_import.copy_file(str(src), str(dest))
        assert final == str(tmp_path / "dest_1.safetensors")
        assert dest.read_bytes() == b"existing"

    def test_failed_copy_leaves_no_partial_file(self, tmp_path, monkeypatch, ext_dir):
        import shutil

        from py.services import foreign_import

        src = tmp_path / "src.safetensors"
        src.write_bytes(b"payload")
        dest = tmp_path / "out" / "dest.safetensors"

        def boom(source, target):
            with open(target, "wb") as handle:
                handle.write(b"half")
            raise OSError("disk fell over")

        monkeypatch.setattr(shutil, "copyfile", boom)
        with pytest.raises(OSError):
            foreign_import.copy_file(str(src), str(dest))
        assert list((tmp_path / "out").iterdir()) == []

    def test_ensure_space_raises_when_short(self, tmp_path, monkeypatch, ext_dir):
        import shutil

        from py.services import foreign_import

        monkeypatch.setattr(
            shutil, "disk_usage", lambda path: shutil._ntuple_diskusage(100, 90, 10)
        )
        with pytest.raises(foreign_import.InsufficientSpaceError) as excinfo:
            foreign_import.ensure_space(str(tmp_path), 50)
        assert excinfo.value.needed == 50
        assert excinfo.value.available == 10

    def test_ensure_space_passes_when_ample(self, tmp_path, ext_dir):
        from py.services import foreign_import

        foreign_import.ensure_space(str(tmp_path), 1)

    def test_source_path_rejects_traversal(self, tmp_path, ext_dir):
        from py.services import foreign_import

        root = _make_source_tree(tmp_path)
        with pytest.raises(ValueError, match="source_not_found"):
            foreign_import.source_path(str(root), "loras", "../../etc/passwd")

    def test_source_path_resolves_existing_file(self, tmp_path, ext_dir):
        from py.services import foreign_import

        root = _make_source_tree(tmp_path)
        resolved = foreign_import.source_path(str(root), "loras", "style/neon.safetensors")
        assert os.path.isfile(resolved)


class TestImportJob:
    async def test_copies_and_registers(self, tmp_path, monkeypatch, ext_dir):
        import folder_paths

        from py.db import model_repo
        from py.services import foreign_import

        monkeypatch.setattr(folder_paths, "models_dir", str(tmp_path / "local"))
        monkeypatch.setattr(foreign_import, "_civitai_lookup", _no_civitai_match)
        root = _make_source_tree(tmp_path)

        job = foreign_import.start_import(
            str(root),
            [{"model_type": "loras", "filename": "style/neon.safetensors", "file_hash": ""}],
        )
        await job.task

        assert job.state == "done"
        assert job.imported == ["style/neon.safetensors"]
        assert job.failed == []
        copied = tmp_path / "local" / "loras" / "style" / "neon.safetensors"
        assert copied.read_bytes() == b"b" * 32
        rows = await model_repo.get_file_hash_map()
        assert list(rows.values()) == ["style/neon.safetensors"]

    async def test_enriches_from_civitai(self, tmp_path, monkeypatch, ext_dir):
        import folder_paths

        from py.db import model_repo
        from py.services import foreign_import

        monkeypatch.setattr(folder_paths, "models_dir", str(tmp_path / "local"))

        async def fake_lookup(sha256):
            return {
                "base_model": "SDXL 1.0",
                "description": "A neon style",
                "tags": ["style", "neon"],
                "civitai_version_id": 4242,
                "civitai_model_id": 99,
            }

        monkeypatch.setattr(foreign_import, "_civitai_lookup", fake_lookup)
        root = _make_source_tree(tmp_path)

        job = foreign_import.start_import(
            str(root),
            [{"model_type": "loras", "filename": "style/neon.safetensors", "file_hash": ""}],
        )
        await job.task

        row = await model_repo.get_model_by_filename("style/neon.safetensors")
        assert row["base_model"] == "SDXL 1.0"
        assert row["description"] == "A neon style"
        assert row["source_platform"] == "civitai"
        assert row["source_id"] == "4242"
        assert row["civitai_model_id"] == "99"

    async def test_civitai_failure_still_imports(self, tmp_path, monkeypatch, ext_dir):
        import folder_paths
        import httpx

        from py.db import model_repo
        from py.services import foreign_import

        monkeypatch.setattr(folder_paths, "models_dir", str(tmp_path / "local"))

        async def exploding_lookup(sha256):
            raise httpx.ConnectError("offline")

        monkeypatch.setattr(foreign_import, "_civitai_lookup", exploding_lookup)
        root = _make_source_tree(tmp_path)

        job = foreign_import.start_import(
            str(root),
            [{"model_type": "loras", "filename": "style/neon.safetensors", "file_hash": ""}],
        )
        await job.task

        assert job.state == "done"
        assert job.imported == ["style/neon.safetensors"]
        assert await model_repo.get_model_by_filename("style/neon.safetensors") is not None

    async def test_missing_source_is_recorded_and_job_continues(
        self, tmp_path, monkeypatch, ext_dir
    ):
        import folder_paths

        from py.services import foreign_import

        monkeypatch.setattr(folder_paths, "models_dir", str(tmp_path / "local"))
        monkeypatch.setattr(foreign_import, "_civitai_lookup", _no_civitai_match)
        root = _make_source_tree(tmp_path)

        job = foreign_import.start_import(
            str(root),
            [
                {"model_type": "loras", "filename": "ghost.safetensors", "file_hash": ""},
                {"model_type": "checkpoints", "filename": "sd15.safetensors", "file_hash": ""},
            ],
        )
        await job.task

        assert job.state == "done"
        assert job.imported == ["sd15.safetensors"]
        assert job.failed == [{"filename": "ghost.safetensors", "reason": "source_not_found"}]
        assert job.progress == 100.0

    async def test_reuses_the_hash_from_the_scan(self, tmp_path, monkeypatch, ext_dir):
        import folder_paths

        from py.db import model_repo
        from py.services import foreign_import

        monkeypatch.setattr(folder_paths, "models_dir", str(tmp_path / "local"))
        monkeypatch.setattr(foreign_import, "_civitai_lookup", _no_civitai_match)

        def forbidden(path):
            raise AssertionError("compute_file_hash must not run when a hash is supplied")

        monkeypatch.setattr(foreign_import.model_paths, "compute_file_hash", forbidden)
        root = _make_source_tree(tmp_path)

        job = foreign_import.start_import(
            str(root),
            [
                {
                    "model_type": "loras",
                    "filename": "style/neon.safetensors",
                    "file_hash": "cafebabe",
                }
            ],
        )
        await job.task

        assert job.state == "done"
        assert await model_repo.get_file_hash_map() == {"cafebabe": "style/neon.safetensors"}

    async def test_cancel_stops_before_the_next_file(self, tmp_path, monkeypatch, ext_dir):
        import folder_paths

        from py.services import foreign_import

        monkeypatch.setattr(folder_paths, "models_dir", str(tmp_path / "local"))
        monkeypatch.setattr(foreign_import, "_civitai_lookup", _no_civitai_match)
        root = _make_source_tree(tmp_path)

        job = foreign_import.start_import(
            str(root),
            [{"model_type": "loras", "filename": "style/neon.safetensors", "file_hash": ""}],
        )
        foreign_import.cancel_job(job.id)
        await job.task
        assert job.state == "cancelled"
        assert job.imported == []

    async def test_registration_failure_does_not_kill_the_job(self, tmp_path, monkeypatch, ext_dir):
        import folder_paths

        from py.services import foreign_import

        monkeypatch.setattr(folder_paths, "models_dir", str(tmp_path / "local"))

        async def exploding_register(final_path, model_type, file_hash):
            raise RuntimeError("database error")

        monkeypatch.setattr(foreign_import, "_register_imported", exploding_register)
        root = _make_source_tree(tmp_path)

        job = foreign_import.start_import(
            str(root),
            [
                {"model_type": "loras", "filename": "style/neon.safetensors", "file_hash": ""},
                {"model_type": "checkpoints", "filename": "sd15.safetensors", "file_hash": ""},
            ],
        )
        await job.task

        assert job.state == "done"
        assert job.progress == 100.0
        assert job.imported == []
        assert len(job.failed) == 2
        assert job.failed[0] == {"filename": "style/neon.safetensors", "reason": "register_failed"}
        assert job.failed[1] == {"filename": "sd15.safetensors", "reason": "register_failed"}
        # Files are still on disk despite registration failure
        assert (tmp_path / "local" / "loras" / "style" / "neon.safetensors").exists()
        assert (tmp_path / "local" / "checkpoints" / "sd15.safetensors").exists()


async def _no_civitai_match(sha256):
    """Stand-in for the CivitAI by-hash lookup: always a miss."""
    return None


class TestJobPruning:
    async def test_finished_jobs_older_than_retention_are_dropped(
        self, tmp_path, monkeypatch, ext_dir
    ):
        from py.services import foreign_import

        root = _make_source_tree(tmp_path)
        monkeypatch.setattr(foreign_import, "_hash_unknown_local_files", _noop_local_hashes)

        # Create and finish a scan job
        job1 = foreign_import.start_scan(str(root))
        await job1.task
        assert foreign_import.get_job(job1.id) is not None

        # Manually expire the job by pretending it finished long ago
        job1.completed_at = 0.0

        # Start a new job, which triggers pruning
        job2 = foreign_import.start_scan(str(root))

        # The old job should be pruned
        assert foreign_import.get_job(job1.id) is None
        assert foreign_import.get_job(job2.id) is not None

    async def test_running_jobs_are_never_pruned(self, tmp_path, monkeypatch, ext_dir):
        from py.services import foreign_import

        root = _make_source_tree(tmp_path)
        monkeypatch.setattr(foreign_import, "_hash_unknown_local_files", _noop_local_hashes)

        job = foreign_import.start_scan(str(root))
        # Job is still running
        assert job.state == "running"

        # Manually trigger pruning by calling it directly
        foreign_import._prune_jobs()

        # Running job should still be there
        assert foreign_import.get_job(job.id) is not None

        # Let the job finish
        await job.task
        assert job.state == "done"
