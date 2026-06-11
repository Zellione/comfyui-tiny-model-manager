"""Integration tests for py/routes/models.py (list / delete / move / types)."""

import os

import pytest
from aiohttp import web


@pytest.fixture()
async def client(aiohttp_client, ext_dir):
    import folder_paths

    # Configure folder_paths stub with real temp dirs backed by ext_dir
    models_dir = os.path.join(ext_dir, "models")
    for folder_type in ("checkpoints", "loras"):
        folder = os.path.join(models_dir, folder_type)
        os.makedirs(folder, exist_ok=True)
        folder_paths.folder_names_and_paths[folder_type] = ([folder], {".safetensors", ".ckpt"})
    folder_paths.models_dir = models_dir

    from py.routes.models import add_model_routes

    app = web.Application()
    routes = web.RouteTableDef()
    add_model_routes(routes)
    app.router.add_routes(routes)
    return await aiohttp_client(app)


@pytest.fixture()
def checkpoints_dir(ext_dir):
    d = os.path.join(ext_dir, "models", "checkpoints")
    os.makedirs(d, exist_ok=True)
    return d


@pytest.fixture()
def loras_dir(ext_dir):
    d = os.path.join(ext_dir, "models", "loras")
    os.makedirs(d, exist_ok=True)
    return d


class TestListModels:
    async def test_returns_success(self, client):
        resp = await client.get("/tiny-model-manager/api/models")
        assert resp.status == 200
        data = await resp.json()
        assert data["success"] is True
        assert isinstance(data["data"], dict)

    async def test_lists_files_in_folder(self, client, checkpoints_dir):
        model_file = os.path.join(checkpoints_dir, "test.safetensors")
        open(model_file, "wb").close()
        resp = await client.get("/tiny-model-manager/api/models")
        data = (await resp.json())["data"]
        assert "checkpoints" in data
        filenames = [f["filename"] for f in data["checkpoints"]]
        assert "test.safetensors" in filenames

    async def test_excludes_wrong_extension(self, client, checkpoints_dir):
        open(os.path.join(checkpoints_dir, "readme.txt"), "w").close()
        resp = await client.get("/tiny-model-manager/api/models")
        data = (await resp.json())["data"]
        ck_files = [f["filename"] for f in data.get("checkpoints", [])]
        assert "readme.txt" not in ck_files


class TestDeleteModel:
    async def test_delete_existing_file(self, client, checkpoints_dir):
        model_file = os.path.join(checkpoints_dir, "to_delete.safetensors")
        open(model_file, "wb").close()
        resp = await client.delete(
            "/tiny-model-manager/api/models/checkpoints/to_delete.safetensors"
        )
        assert resp.status == 200
        assert not os.path.exists(model_file)

    async def test_delete_nonexistent_returns_404(self, client):
        resp = await client.delete("/tiny-model-manager/api/models/checkpoints/nope.safetensors")
        assert resp.status == 404

    async def test_delete_path_traversal_rejected(self, client):
        resp = await client.delete("/tiny-model-manager/api/models/checkpoints/../../etc/passwd")
        assert resp.status == 404

    async def test_delete_sibling_directory_escape_blocked(self, client, ext_dir):
        import types

        import folder_paths

        from py.routes.models import _delete_model

        # Sibling of the registered loras dir that shares its name prefix must be
        # unreachable (a plain str.startswith guard would wrongly allow "loras_evil").
        base = folder_paths.folder_names_and_paths["loras"][0][0]
        sibling = base + "_evil"
        os.makedirs(sibling, exist_ok=True)
        victim = os.path.join(sibling, "keep.safetensors")
        open(victim, "wb").close()

        rel = os.path.join("..", os.path.basename(sibling), "keep.safetensors")
        req = types.SimpleNamespace(match_info={"model_type": "loras", "path": rel})
        resp = await _delete_model(req)
        assert resp.status == 404
        assert os.path.exists(victim)


class TestListModelTypes:
    async def test_returns_types(self, client):
        resp = await client.get("/tiny-model-manager/api/model-types")
        assert resp.status == 200
        data = (await resp.json())["data"]
        assert isinstance(data, list)
        # checkpoints and loras folders were created in the fixture
        assert "checkpoints" in data
        assert "loras" in data

    async def test_excludes_configs(self, client, ext_dir):
        import folder_paths

        configs_dir = os.path.join(folder_paths.models_dir, "configs")
        os.makedirs(configs_dir, exist_ok=True)
        resp = await client.get("/tiny-model-manager/api/model-types")
        data = (await resp.json())["data"]
        assert "configs" not in data


class TestMoveModel:
    async def test_move_to_different_type(self, client, checkpoints_dir, loras_dir, ext_dir):
        from py.db import model_repo

        src = os.path.join(checkpoints_dir, "moveme.safetensors")
        open(src, "wb").close()

        # Pre-insert into DB
        await model_repo.upsert_model("moveme.safetensors", "checkpoints", "", "", "")

        resp = await client.post(
            "/tiny-model-manager/api/models/checkpoints/moveme.safetensors/move",
            json={"new_type": "loras"},
        )
        assert resp.status == 200
        assert (await resp.json())["success"] is True
        assert not os.path.exists(src)
        assert os.path.exists(os.path.join(loras_dir, "moveme.safetensors"))

    async def test_move_nonexistent_returns_404(self, client):
        resp = await client.post(
            "/tiny-model-manager/api/models/checkpoints/ghost.safetensors/move",
            json={"new_type": "loras"},
        )
        assert resp.status == 404

    async def test_move_invalid_type_returns_400(self, client, checkpoints_dir):
        src = os.path.join(checkpoints_dir, "safe.safetensors")
        open(src, "wb").close()
        resp = await client.post(
            "/tiny-model-manager/api/models/checkpoints/safe.safetensors/move",
            json={"new_type": "configs"},
        )
        assert resp.status == 400


class TestOrganizeModels:
    async def test_organize_moves_to_base_model_subfolder(self, client, loras_dir):
        from py.db import model_repo

        src = os.path.join(loras_dir, "my-lora.safetensors")
        open(src, "wb").close()
        await model_repo.upsert_model(
            "my-lora.safetensors", "loras", "civitai", "123", "", base_model="SDXL 1.0"
        )

        resp = await client.post("/tiny-model-manager/api/models/organize")
        assert resp.status == 200
        data = (await resp.json())["data"]
        assert data["moved"] >= 1
        assert os.path.exists(os.path.join(loras_dir, "SDXL 1.0", "my-lora.safetensors"))
        assert not os.path.exists(src)

    async def test_organize_moves_to_unknown_when_no_base_model(self, client, loras_dir):
        from py.db import model_repo

        src = os.path.join(loras_dir, "no-meta.safetensors")
        open(src, "wb").close()
        await model_repo.upsert_model("no-meta.safetensors", "loras", "", "", "")

        resp = await client.post("/tiny-model-manager/api/models/organize")
        assert resp.status == 200
        assert os.path.exists(os.path.join(loras_dir, "Unknown", "no-meta.safetensors"))

    async def test_organize_is_idempotent(self, client, loras_dir):
        from py.db import model_repo

        subfolder = os.path.join(loras_dir, "SDXL 1.0")
        os.makedirs(subfolder, exist_ok=True)
        src = os.path.join(subfolder, "already-organized.safetensors")
        open(src, "wb").close()
        await model_repo.upsert_model(
            "SDXL 1.0/already-organized.safetensors", "loras", "", "", "", base_model="SDXL 1.0"
        )

        resp = await client.post("/tiny-model-manager/api/models/organize")
        data = (await resp.json())["data"]
        assert data["skipped"] >= 1
        assert os.path.exists(src)

    async def test_organize_returns_stats(self, client):
        resp = await client.post("/tiny-model-manager/api/models/organize")
        assert resp.status == 200
        body = await resp.json()
        assert body["success"] is True
        assert "moved" in body["data"]
        assert "skipped" in body["data"]
        assert "errors" in body["data"]


class TestPendingReorganize:
    async def test_returns_empty_when_no_jobs(self, client):
        resp = await client.get("/tiny-model-manager/api/reorganize/pending")
        assert resp.status == 200
        body = await resp.json()
        assert body["success"] is True
        assert body["data"] == []

    async def test_returns_pending_filenames(self, client):
        from py.db import model_repo

        await model_repo.enqueue_reorganize("SDXL 1.0/a.safetensors", "loras", "deorganize")
        await model_repo.enqueue_reorganize("flat.safetensors", "loras", "organize")

        resp = await client.get("/tiny-model-manager/api/reorganize/pending")
        assert resp.status == 200
        data = (await resp.json())["data"]
        assert "SDXL 1.0/a.safetensors" in data
        assert "flat.safetensors" in data
