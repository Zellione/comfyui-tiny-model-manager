"""Integration tests for py/routes/imports.py (F-154)."""

import os

import pytest
from aiohttp import web


@pytest.fixture
async def client(aiohttp_client, ext_dir):
    from py.routes.imports import add_imports_routes

    app = web.Application()
    routes = web.RouteTableDef()
    add_imports_routes(routes)
    app.router.add_routes(routes)
    return await aiohttp_client(app)


@pytest.fixture
def source_root(tmp_path):
    root = tmp_path / "foreign" / "models"
    (root / "loras").mkdir(parents=True)
    (root / "loras" / "neon.safetensors").write_bytes(b"n" * 24)
    return root


@pytest.fixture(autouse=True)
def local_models_dir(tmp_path, monkeypatch):
    import folder_paths

    local = tmp_path / "local" / "models"
    local.mkdir(parents=True)
    monkeypatch.setattr(folder_paths, "models_dir", str(local))
    return local


@pytest.fixture(autouse=True)
def no_civitai(monkeypatch):
    async def miss(sha256):
        return None

    from py.services import foreign_import

    monkeypatch.setattr(foreign_import, "_civitai_lookup", miss)


API = "/tiny-model-manager/api/import"


class TestScanRoute:
    async def test_relative_path_is_400(self, client):
        resp = await client.post(f"{API}/scan", json={"path": "relative/dir"})
        assert resp.status == 400
        assert (await resp.json())["error"] == "path_not_absolute"

    async def test_missing_path_is_400(self, client, tmp_path):
        resp = await client.post(f"{API}/scan", json={"path": str(tmp_path / "nope")})
        assert resp.status == 400
        assert (await resp.json())["error"] == "path_not_found"

    async def test_scan_returns_job_id_and_resolved_root(self, client, source_root):
        resp = await client.post(f"{API}/scan", json={"path": str(source_root.parent)})
        assert resp.status == 200
        body = await resp.json()
        assert body["success"] is True
        assert body["data"]["job_id"]
        assert body["data"]["source_root"] == os.path.realpath(str(source_root))

    async def test_scan_progress_reports_the_file(self, client, source_root):
        from py.services import foreign_import

        start = await client.post(f"{API}/scan", json={"path": str(source_root)})
        job_id = (await start.json())["data"]["job_id"]
        await foreign_import.get_job(job_id).task

        resp = await client.get(f"{API}/scan/{job_id}")
        assert resp.status == 200
        data = (await resp.json())["data"]
        assert data["state"] == "done"
        assert data["files"] == [
            {
                "model_type": "loras",
                "filename": "neon.safetensors",
                "size_bytes": 24,
                "status": "new",
                "file_hash": data["files"][0]["file_hash"],
            }
        ]

    async def test_unknown_scan_job_is_404(self, client):
        resp = await client.get(f"{API}/scan/does-not-exist")
        assert resp.status == 404

    async def test_cancel_scan_job_succeeds(self, client, source_root):
        start = await client.post(f"{API}/scan", json={"path": str(source_root)})
        job_id = (await start.json())["data"]["job_id"]

        resp = await client.post(f"{API}/jobs/{job_id}/cancel")
        assert resp.status == 200
        body = await resp.json()
        assert body["success"] is True
        assert body["data"]["cancelled"] is True


class TestImportRoute:
    async def _scanned_root(self, client, source_root):
        from py.services import foreign_import

        start = await client.post(f"{API}/scan", json={"path": str(source_root)})
        job_id = (await start.json())["data"]["job_id"]
        await foreign_import.get_job(job_id).task
        return (await start.json())["data"]["source_root"]

    async def test_full_round_trip_registers_the_model(self, client, source_root, local_models_dir):
        from py.db import model_repo
        from py.services import foreign_import

        root = await self._scanned_root(client, source_root)
        resp = await client.post(
            f"{API}/start",
            json={
                "source_root": root,
                "files": [{"model_type": "loras", "filename": "neon.safetensors"}],
            },
        )
        assert resp.status == 200
        job_id = (await resp.json())["data"]["job_id"]
        await foreign_import.get_job(job_id).task

        progress = await client.get(f"{API}/jobs/{job_id}")
        data = (await progress.json())["data"]
        assert data["state"] == "done"
        assert data["imported"] == ["neon.safetensors"]
        assert (local_models_dir / "loras" / "neon.safetensors").exists()
        assert await model_repo.get_registered_filenames() == {"neon.safetensors"}

    async def test_empty_selection_is_400(self, client, source_root):
        root = await self._scanned_root(client, source_root)
        resp = await client.post(f"{API}/start", json={"source_root": root, "files": []})
        assert resp.status == 400
        assert (await resp.json())["error"] == "no_files_selected"

    async def test_unvalidated_root_is_400(self, client, tmp_path):
        resp = await client.post(
            f"{API}/start",
            json={
                "source_root": str(tmp_path / "never-scanned"),
                "files": [{"model_type": "loras", "filename": "x.safetensors"}],
            },
        )
        assert resp.status == 400

    async def test_insufficient_space_is_409(self, client, source_root, monkeypatch):
        import shutil

        root = await self._scanned_root(client, source_root)
        monkeypatch.setattr(shutil, "disk_usage", lambda path: shutil._ntuple_diskusage(100, 99, 1))
        resp = await client.post(
            f"{API}/start",
            json={
                "source_root": root,
                "files": [{"model_type": "loras", "filename": "neon.safetensors"}],
            },
        )
        assert resp.status == 409
        body = await resp.json()
        assert body["error"] == "insufficient_space"
        assert body["needed"] == 24
        assert body["available"] == 1

    async def test_unknown_job_is_404(self, client):
        resp = await client.get(f"{API}/jobs/nope")
        assert resp.status == 404

    async def test_cancel_unknown_job_is_404(self, client):
        resp = await client.post(f"{API}/jobs/nope/cancel")
        assert resp.status == 404

    async def test_insufficient_space_on_second_type_is_409(
        self, client, tmp_path, local_models_dir, monkeypatch
    ):
        import shutil

        # Create a source with two model types
        source = tmp_path / "source_multi"
        (source / "loras").mkdir(parents=True)
        (source / "loras" / "a.safetensors").write_bytes(b"a" * 30)
        (source / "checkpoints").mkdir(parents=True)
        (source / "checkpoints" / "b.safetensors").write_bytes(b"b" * 50)

        # Scan to get the resolved root
        start = await client.post(f"{API}/scan", json={"path": str(source)})
        root = (await start.json())["data"]["source_root"]

        # Monkeypatch disk_usage to report plenty of space for loras, almost none for checkpoints
        original_disk_usage = shutil.disk_usage

        def mock_disk_usage(path):
            if "checkpoints" in path:
                return shutil._ntuple_diskusage(100, 99, 1)
            return original_disk_usage(path)

        monkeypatch.setattr(shutil, "disk_usage", mock_disk_usage)

        # Try to import both: should fail with 409 for checkpoints
        resp = await client.post(
            f"{API}/start",
            json={
                "source_root": root,
                "files": [
                    {"model_type": "loras", "filename": "a.safetensors"},
                    {"model_type": "checkpoints", "filename": "b.safetensors"},
                ],
            },
        )
        assert resp.status == 409
        body = await resp.json()
        assert body["error"] == "insufficient_space"
        assert body["needed"] == 50
        assert body["available"] == 1

    async def test_all_invalid_selections_complete_with_empty_imported(
        self, client, source_root, local_models_dir
    ):
        from py.services import foreign_import

        root = await self._scanned_root(client, source_root)
        resp = await client.post(
            f"{API}/start",
            json={
                "source_root": root,
                "files": [
                    {"model_type": "loras", "filename": "bogus1.safetensors"},
                    {"model_type": "loras", "filename": "bogus2.safetensors"},
                ],
            },
        )
        assert resp.status == 200
        job_id = (await resp.json())["data"]["job_id"]
        await foreign_import.get_job(job_id).task

        progress = await client.get(f"{API}/jobs/{job_id}")
        data = (await progress.json())["data"]
        assert data["state"] == "done"
        assert data["imported"] == []
        failed_filenames = {
            item.get("filename") if isinstance(item, dict) else item for item in data["failed"]
        }
        assert failed_filenames == {"bogus1.safetensors", "bogus2.safetensors"}
