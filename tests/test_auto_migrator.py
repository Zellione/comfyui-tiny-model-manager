"""Unit tests for py/services/auto_migrator.py (F-92 auto-migration hook)."""

import hashlib
import os

import pytest


@pytest.fixture(autouse=True)
def _clean_module_state():
    """Hash cache and notification queue are module-level; isolate every test."""
    from py.services import auto_migrator, backend_notifier

    auto_migrator._hash_cache.clear()
    backend_notifier.flush()
    yield
    auto_migrator._hash_cache.clear()
    backend_notifier.flush()


@pytest.fixture()
def models_root(ext_dir):
    """Configure the folder_paths stub with real dirs backed by ext_dir."""
    import folder_paths

    models_dir = os.path.join(ext_dir, "models")
    for folder_type in ("checkpoints", "loras"):
        folder = os.path.join(models_dir, folder_type)
        os.makedirs(folder, exist_ok=True)
        folder_paths.folder_names_and_paths[folder_type] = ([folder], {".safetensors", ".ckpt"})
    folder_paths.models_dir = models_dir
    return models_dir


def _write_model(models_root: str, folder_type: str, name: str, content: bytes = b"weights"):
    """Write a real file so SHA-256 is genuinely computed. Returns (path, digest, size)."""
    path = os.path.join(models_root, folder_type, name)
    with open(path, "wb") as fh:
        fh.write(content)
    return path, hashlib.sha256(content).hexdigest(), len(content)


def _remote(name, digest, size=0, **kw):
    from py.services.auto_migrator import RemoteFile

    return RemoteFile(
        filename=name,
        sha256=digest,
        size_bytes=size,
        source_platform=kw.pop("source_platform", "civitai"),
        **kw,
    )


class TestFromCivitaiVersions:
    def test_extracts_all_fields(self):
        from py.services.auto_migrator import from_civitai_versions

        files = from_civitai_versions(
            {
                "versions": [
                    {
                        "id": 55,
                        "modelId": 12,
                        "baseModel": "SDXL 1.0",
                        "files": [
                            {
                                "type": "Model",
                                "name": "cool.safetensors",
                                "sizeKB": 2048.0,
                                "hashes": {"SHA256": "ABC123"},
                            }
                        ],
                    }
                ]
            }
        )

        assert len(files) == 1
        f = files[0]
        assert f.filename == "cool.safetensors"
        assert f.sha256 == "ABC123"
        assert f.size_bytes == 2048 * 1024
        assert f.base_model == "SDXL 1.0"
        assert f.source_platform == "civitai"
        assert f.source_id == "55"
        assert f.civitai_model_id == "12"

    def test_skips_non_model_and_hashless_files(self):
        from py.services.auto_migrator import from_civitai_versions

        files = from_civitai_versions(
            {
                "versions": [
                    {
                        "id": 1,
                        "files": [
                            # Not a weights file
                            {
                                "type": "Training Data",
                                "name": "data.zip",
                                "hashes": {"SHA256": "aaa"},
                            },
                            # Weights, but CivitAI published no SHA-256
                            {"type": "Model", "name": "nohash.safetensors", "hashes": {}},
                            # No filename to match against
                            {"type": "Model", "name": "", "hashes": {"SHA256": "bbb"}},
                        ],
                    }
                ]
            }
        )

        assert files == []

    def test_accepts_bare_version_list(self):
        from py.services.auto_migrator import from_civitai_versions

        files = from_civitai_versions(
            [
                {
                    "id": 7,
                    "files": [
                        {"type": "Model", "name": "x.safetensors", "hashes": {"SHA256": "z"}}
                    ],
                }
            ]
        )

        assert len(files) == 1
        assert files[0].source_id == "7"

    def test_unexpected_shape_returns_empty(self):
        from py.services.auto_migrator import from_civitai_versions

        assert from_civitai_versions(None) == []
        assert from_civitai_versions("nope") == []
        assert from_civitai_versions({"versions": ["not-a-dict"]}) == []


class TestFromHfFiles:
    def test_extracts_sha256(self):
        from py.services.auto_migrator import from_hf_files

        files = from_hf_files(
            "owner/repo",
            [{"filename": "model.safetensors", "size": 4096, "sha256": "deadbeef"}],
        )

        assert len(files) == 1
        f = files[0]
        assert f.filename == "model.safetensors"
        assert f.sha256 == "deadbeef"
        assert f.size_bytes == 4096
        assert f.source_platform == "huggingface"
        assert f.source_id == "owner/repo"

    def test_skips_entries_without_hash(self):
        from py.services.auto_migrator import from_hf_files

        files = from_hf_files(
            "owner/repo",
            [
                {"filename": "config.safetensors", "size": 1, "sha256": ""},
                {"filename": "no-key.safetensors", "size": 1},
            ],
        )

        assert files == []


class TestMigrate:
    async def test_registers_matching_file(self, models_root):
        from py.db import model_repo
        from py.services.auto_migrator import migrate

        _, digest, size = _write_model(models_root, "checkpoints", "match.safetensors")

        migrated = await migrate(
            [_remote("match.safetensors", digest, size, base_model="SDXL 1.0", source_id="55")]
        )

        assert migrated == ["match.safetensors"]
        record = await model_repo.get_model_by_filename("match.safetensors")
        assert record is not None
        assert record["file_hash"] == digest
        assert record["model_type"] == "checkpoints"
        assert record["base_model"] == "SDXL 1.0"

    async def test_matches_case_insensitively_on_hash(self, models_root):
        from py.services.auto_migrator import migrate

        _, digest, size = _write_model(models_root, "loras", "upper.safetensors")

        migrated = await migrate([_remote("upper.safetensors", digest.upper(), size)])

        assert migrated == ["upper.safetensors"]

    async def test_skips_already_registered_file(self, models_root):
        from py.db import model_repo
        from py.services.auto_migrator import migrate

        _, digest, size = _write_model(models_root, "checkpoints", "known.safetensors")
        await model_repo.register_model("known.safetensors", "checkpoints")

        migrated = await migrate([_remote("known.safetensors", digest, size)])

        assert migrated == []

    async def test_size_mismatch_skips_without_hashing(self, models_root, monkeypatch):
        """The size gate is what keeps this feature affordable — never hash a size mismatch."""
        from py.services import auto_migrator

        _, digest, size = _write_model(models_root, "checkpoints", "big.safetensors")

        def explode(path):
            raise AssertionError(f"compute_file_hash must not be called for {path}")

        monkeypatch.setattr("py.services.model_paths.compute_file_hash", explode)

        migrated = await auto_migrator.migrate(
            [_remote("big.safetensors", digest, size + 10 * 1024 * 1024)]
        )

        assert migrated == []

    async def test_size_within_tolerance_still_hashes(self, models_root):
        """CivitAI rounds sizeKB, so near-misses must survive the size gate."""
        from py.services.auto_migrator import migrate

        _, digest, size = _write_model(models_root, "checkpoints", "rounded.safetensors")

        migrated = await migrate([_remote("rounded.safetensors", digest, size + 1024)])

        assert migrated == ["rounded.safetensors"]

    async def test_hash_mismatch_does_not_register(self, models_root):
        from py.db import model_repo
        from py.services.auto_migrator import migrate

        _, _, size = _write_model(models_root, "checkpoints", "other.safetensors")

        migrated = await migrate([_remote("other.safetensors", "f" * 64, size)])

        assert migrated == []
        assert await model_repo.get_model_by_filename("other.safetensors") is None

    async def test_name_mismatch_does_not_register(self, models_root):
        from py.services.auto_migrator import migrate

        _, digest, size = _write_model(models_root, "checkpoints", "local-name.safetensors")

        migrated = await migrate([_remote("remote-name.safetensors", digest, size)])

        assert migrated == []

    async def test_empty_input_does_not_scan_disk(self, monkeypatch):
        from py.services import auto_migrator

        def explode():
            raise AssertionError("scan_all must not run for an empty remote file list")

        monkeypatch.setattr("py.services.disk_scanner.scan_all", explode)

        assert await auto_migrator.migrate([]) == []

    async def test_hash_cache_prevents_second_read(self, models_root, monkeypatch):
        from py.services import auto_migrator

        _, digest, size = _write_model(models_root, "checkpoints", "cached.safetensors")
        calls = []
        real = auto_migrator.model_paths.compute_file_hash

        def counting(path):
            calls.append(path)
            return real(path)

        monkeypatch.setattr("py.services.model_paths.compute_file_hash", counting)

        # A deliberate hash mismatch means the file stays unregistered, so the second
        # pass reaches the hashing step again and can only be served by the cache.
        remote = [_remote("cached.safetensors", "f" * 64, size)]
        await auto_migrator.migrate(remote)
        await auto_migrator.migrate(remote)

        assert len(calls) == 1
        assert digest  # sanity: the file really was hashable

    async def test_unreadable_file_is_skipped(self, models_root, monkeypatch):
        from py.services import auto_migrator

        _, digest, size = _write_model(models_root, "checkpoints", "gone.safetensors")

        def vanished(path):
            raise OSError("file vanished between scan and hash")

        monkeypatch.setattr("py.services.model_paths.compute_file_hash", vanished)

        assert await auto_migrator.migrate([_remote("gone.safetensors", digest, size)]) == []

    async def test_pushes_notification(self, models_root):
        from py.services import backend_notifier
        from py.services.auto_migrator import migrate

        _, digest, size = _write_model(models_root, "checkpoints", "noticed.safetensors")

        await migrate([_remote("noticed.safetensors", digest, size)])

        pending = backend_notifier.flush()
        assert len(pending) == 1
        assert pending[0]["type"] == "info"
        assert "noticed.safetensors" in pending[0]["message"]

    async def test_registration_failure_does_not_abort_batch(self, models_root, monkeypatch):
        from py.db import model_repo
        from py.services import auto_migrator

        _, digest_a, size_a = _write_model(models_root, "checkpoints", "a.safetensors", b"aaa")
        _, digest_b, size_b = _write_model(models_root, "checkpoints", "b.safetensors", b"bbb")

        real_register = model_repo.register_model

        async def flaky(filename, *args, **kwargs):
            if filename == "a.safetensors":
                raise RuntimeError("disk full")
            return await real_register(filename, *args, **kwargs)

        monkeypatch.setattr("py.db.model_repo.register_model", flaky)

        migrated = await auto_migrator.migrate(
            [
                _remote("a.safetensors", digest_a, size_a),
                _remote("b.safetensors", digest_b, size_b),
            ]
        )

        assert migrated == ["b.safetensors"]

    async def test_never_calls_fetch_and_store(self, models_root, monkeypatch):
        """Enrichment would re-enter _fetch_repo_files and schedule another pass."""
        from py.services.auto_migrator import migrate

        _, digest, size = _write_model(models_root, "checkpoints", "noloop.safetensors")

        async def explode(*args, **kwargs):
            raise AssertionError("migration must not re-enter the metadata pipeline")

        monkeypatch.setattr("py.services.metadata_fetcher.fetch_and_store", explode)

        assert await migrate([_remote("noloop.safetensors", digest, size, source_id="55")]) == [
            "noloop.safetensors"
        ]

    async def test_stores_metadata_from_version_payload(self, models_root):
        """The card is built from the payload already in hand, not a second fetch."""
        from py.db import model_repo
        from py.services.auto_migrator import from_civitai_versions, migrate

        _, digest, size = _write_model(models_root, "loras", "rich.safetensors")
        remote = from_civitai_versions(
            {
                "versions": [
                    {
                        "id": 55,
                        "modelId": 12,
                        "baseModel": "SDXL 1.0",
                        "trainedWords": ["magicword"],
                        "description": "from the version payload",
                        "files": [
                            {
                                "type": "Model",
                                "name": "rich.safetensors",
                                "sizeKB": size / 1024,
                                "hashes": {"SHA256": digest},
                            }
                        ],
                    }
                ]
            }
        )

        assert await migrate(remote) == ["rich.safetensors"]
        record = await model_repo.get_model_by_filename("rich.safetensors")
        assert record["description"] == "from the version payload"
        assert record["base_model"] == "SDXL 1.0"
        assert record["trigger_words"] == ["magicword"]
        assert record["file_hash"] == digest


class TestSchedule:
    def test_noop_on_empty_list(self, monkeypatch):
        from py.services import auto_migrator

        def explode(coro):
            raise AssertionError("schedule must not spawn a task for an empty list")

        monkeypatch.setattr("py.background.spawn", explode)
        assert auto_migrator.schedule([]) is None

    async def test_spawns_background_task(self, models_root):
        from py.db import model_repo
        from py.services import auto_migrator

        _, digest, size = _write_model(models_root, "checkpoints", "spawned.safetensors")

        # Await only our own task. The global background task set also holds the
        # downloader's `while True` worker, which never completes.
        task = auto_migrator.schedule([_remote("spawned.safetensors", digest, size)])
        assert task is not None
        await task

        assert await model_repo.get_model_by_filename("spawned.safetensors") is not None

    async def test_background_run_swallows_failures(self, monkeypatch):
        from py.services import auto_migrator

        async def boom(_files):
            raise RuntimeError("scan blew up")

        monkeypatch.setattr(auto_migrator, "migrate", boom)

        assert await auto_migrator._run([_remote("x.safetensors", "abc")]) == []
