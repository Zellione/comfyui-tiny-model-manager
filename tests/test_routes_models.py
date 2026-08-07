"""Integration tests for py/routes/models.py (list / delete / move / types)."""

import os

import pytest
from aiohttp import web


@pytest.fixture
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


@pytest.fixture
def checkpoints_dir(ext_dir):
    d = os.path.join(ext_dir, "models", "checkpoints")
    os.makedirs(d, exist_ok=True)
    return d


@pytest.fixture
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

    async def test_delete_removes_the_models_media(self, client, checkpoints_dir, ext_dir):
        from py import config as cfg
        from py.db import model_repo

        model_file = os.path.join(checkpoints_dir, "with_media.safetensors")
        open(model_file, "wb").close()
        media_dir = os.path.join(cfg.media_dir(), "mediahash")
        os.makedirs(media_dir, exist_ok=True)
        preview = os.path.join(media_dir, "0.jpg")
        open(preview, "wb").close()
        model_id = await model_repo.upsert_model_with_meta(
            "with_media.safetensors",
            "checkpoints",
            "civitai",
            "123",
            "",
            [],
            [],
            media_hash="mediahash",
        )
        await model_repo.add_media(model_id, "image", preview)

        resp = await client.delete(
            "/tiny-model-manager/api/models/checkpoints/with_media.safetensors"
        )

        assert resp.status == 200
        assert not os.path.exists(preview)
        assert not os.path.isdir(media_dir)

    async def test_delete_keeps_media_owned_by_the_catalog_entry(
        self, client, checkpoints_dir, ext_dir
    ):
        from py import config as cfg
        from py.db import model_repo

        model_file = os.path.join(checkpoints_dir, "shared_media.safetensors")
        open(model_file, "wb").close()
        media_dir = os.path.join(cfg.media_dir(), "sharedhash")
        os.makedirs(media_dir, exist_ok=True)
        preview = os.path.join(media_dir, "0.jpg")
        open(preview, "wb").close()
        model_id = await model_repo.upsert_model_with_meta(
            "shared_media.safetensors",
            "checkpoints",
            "civitai",
            "123",
            "",
            [],
            [],
            media_hash="sharedhash",
        )
        await model_repo.add_media(model_id, "image", preview)
        await model_repo.upsert_catalog_entry(
            "civitai", "123", "", "Entry", "", "", media_hash="sharedhash"
        )

        resp = await client.delete(
            "/tiny-model-manager/api/models/checkpoints/shared_media.safetensors"
        )

        assert resp.status == 200
        assert not os.path.exists(model_file)
        # The catalog gallery must survive uninstalling the file.
        assert os.path.isfile(preview)


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


class TestUnregisteredFiles:
    async def test_returns_empty_when_all_registered(self, client, checkpoints_dir):
        from py.db import model_repo

        model_file = os.path.join(checkpoints_dir, "test.safetensors")
        open(model_file, "wb").close()
        await model_repo.register_model("test.safetensors", "checkpoints")

        resp = await client.get("/tiny-model-manager/api/models/unregistered")
        assert resp.status == 200
        data = (await resp.json())["data"]
        assert data == {}

    async def test_returns_file_when_not_in_db(self, client, checkpoints_dir):
        model_file = os.path.join(checkpoints_dir, "unregistered.safetensors")
        open(model_file, "wb").close()

        resp = await client.get("/tiny-model-manager/api/models/unregistered")
        assert resp.status == 200
        data = (await resp.json())["data"]
        assert "checkpoints" in data
        filenames = [f["filename"] for f in data["checkpoints"]]
        assert "unregistered.safetensors" in filenames

    async def test_ignores_non_model_extension(self, client, checkpoints_dir):
        txt_file = os.path.join(checkpoints_dir, "readme.txt")
        open(txt_file, "w").close()

        resp = await client.get("/tiny-model-manager/api/models/unregistered")
        assert resp.status == 200
        data = (await resp.json())["data"]
        ck_files = [f["filename"] for f in data.get("checkpoints", [])]
        assert "readme.txt" not in ck_files


class TestRegisterModel:
    async def test_registers_minimal_data(self, client, checkpoints_dir):
        from py.db import model_repo

        model_file = os.path.join(checkpoints_dir, "test.safetensors")
        open(model_file, "wb").close()

        resp = await client.post(
            "/tiny-model-manager/api/models/register",
            json={"filename": "test.safetensors", "model_type": "checkpoints"},
        )
        assert resp.status == 200
        data = (await resp.json())["data"]
        assert "model_id" in data
        assert isinstance(data["model_id"], int)

        # Verify the record was created
        record = await model_repo.get_model_by_filename("test.safetensors")
        assert record is not None
        assert record["model_type"] == "checkpoints"

    async def test_registers_full_data(self, client, checkpoints_dir):
        from py.db import model_repo

        model_file = os.path.join(checkpoints_dir, "test.safetensors")
        open(model_file, "wb").close()

        resp = await client.post(
            "/tiny-model-manager/api/models/register",
            json={
                "filename": "test.safetensors",
                "model_type": "checkpoints",
                "base_model": "SD 1.5",
                "tags": ["tag1", "tag2"],
                "description": "Test model",
            },
        )
        assert resp.status == 200
        data = (await resp.json())["data"]
        assert "model_id" in data

        # Verify the record has all fields
        record = await model_repo.get_model_by_filename("test.safetensors")
        assert record is not None
        assert record["base_model"] == "SD 1.5"
        assert record["description"] == "Test model"
        assert "tag1" in record["tags"]
        assert "tag2" in record["tags"]

    async def test_file_not_found_returns_404(self, client):
        resp = await client.post(
            "/tiny-model-manager/api/models/register",
            json={"filename": "nonexistent.safetensors", "model_type": "checkpoints"},
        )
        assert resp.status == 404
        data = await resp.json()
        assert data["success"] is False
        assert "file_not_found" in data["error"]

    async def test_missing_fields_returns_400(self, client):
        resp = await client.post("/tiny-model-manager/api/models/register", json={})
        assert resp.status == 400
        data = await resp.json()
        assert data["success"] is False
        assert "required" in data["error"]

    async def test_path_traversal_rejected(self, client):
        """Path traversal filenames like '../../../etc/passwd' should be rejected with 404."""
        resp = await client.post(
            "/tiny-model-manager/api/models/register",
            json={"filename": "../../../etc/passwd", "model_type": "checkpoints"},
        )
        assert resp.status == 404
        data = await resp.json()
        assert data["success"] is False

    async def test_whitespace_only_input_rejected(self, client):
        """Whitespace-only inputs should be rejected with 400 after stripping."""
        resp = await client.post(
            "/tiny-model-manager/api/models/register",
            json={"filename": "   ", "model_type": "  "},
        )
        assert resp.status == 400
        data = await resp.json()
        assert data["success"] is False
        assert "required" in data["error"]

    async def test_register_stores_file_hash_and_civitai_ids(self, client, checkpoints_dir):
        from py.db import model_repo

        model_file = os.path.join(checkpoints_dir, "linked.safetensors")
        open(model_file, "wb").close()

        resp = await client.post(
            "/tiny-model-manager/api/models/register",
            json={
                "filename": "linked.safetensors",
                "model_type": "checkpoints",
                "file_hash": "abc123",
                "source_platform": "civitai",
                "source_id": "9999",
                "civitai_model_id": "8888",
            },
        )
        assert resp.status == 200
        row = await model_repo.get_model_by_filename("linked.safetensors")
        assert row["file_hash"] == "abc123"
        assert row["source_platform"] == "civitai"
        assert row["source_id"] == "9999"


class TestHashLookup:
    async def test_match_returns_hash_and_metadata(self, client, checkpoints_dir, monkeypatch):
        model_file = os.path.join(checkpoints_dir, "model.safetensors")
        open(model_file, "wb").close()

        monkeypatch.setattr(
            "py.routes.models._hash_file",
            lambda path: _async_return("deadbeefdeadbeef"),
        )
        monkeypatch.setattr(
            "py.routes.models._civitai_lookup",
            lambda sha256: _async_return(
                {
                    "name": "Cool Model",
                    "base_model": "SD 1.5",
                    "description": "Desc",
                    "tags": ["tag1"],
                    "trigger_words": ["word"],
                    "version_name": "v1",
                    "civitai_version_id": "111",
                    "civitai_model_id": "222",
                }
            ),
        )

        resp = await client.post(
            "/tiny-model-manager/api/models/hash-lookup",
            json={"filename": "model.safetensors", "model_type": "checkpoints"},
        )
        assert resp.status == 200
        data = (await resp.json())["data"]
        assert data["match"] is True
        assert data["hash"] == "deadbeefdeadbeef"
        assert data["metadata"]["name"] == "Cool Model"
        assert data["metadata"]["base_model"] == "SD 1.5"

    async def test_no_match_returns_match_false(self, client, checkpoints_dir, monkeypatch):
        model_file = os.path.join(checkpoints_dir, "nohit.safetensors")
        open(model_file, "wb").close()

        monkeypatch.setattr(
            "py.routes.models._hash_file",
            lambda path: _async_return("aaaa"),
        )
        monkeypatch.setattr(
            "py.routes.models._civitai_lookup",
            lambda sha256: _async_return(None),
        )

        resp = await client.post(
            "/tiny-model-manager/api/models/hash-lookup",
            json={"filename": "nohit.safetensors", "model_type": "checkpoints"},
        )
        assert resp.status == 200
        data = (await resp.json())["data"]
        assert data["match"] is False
        assert data["hash"] == "aaaa"
        assert data.get("metadata") is None

    async def test_file_not_found_returns_404(self, client):
        resp = await client.post(
            "/tiny-model-manager/api/models/hash-lookup",
            json={"filename": "missing.safetensors", "model_type": "checkpoints"},
        )
        assert resp.status == 404

    async def test_missing_fields_returns_400(self, client):
        resp = await client.post(
            "/tiny-model-manager/api/models/hash-lookup",
            json={"filename": "model.safetensors"},
        )
        assert resp.status == 400

    async def test_civitai_unavailable_returns_503(self, client, checkpoints_dir, monkeypatch):
        import httpx as _httpx

        model_file = os.path.join(checkpoints_dir, "err.safetensors")
        open(model_file, "wb").close()

        monkeypatch.setattr(
            "py.routes.models._hash_file",
            lambda path: _async_return("bbbb"),
        )

        async def _raise(_):
            raise _httpx.HTTPError("network error")

        monkeypatch.setattr("py.routes.models._civitai_lookup", _raise)

        resp = await client.post(
            "/tiny-model-manager/api/models/hash-lookup",
            json={"filename": "err.safetensors", "model_type": "checkpoints"},
        )
        assert resp.status == 503


async def _async_return(value):
    return value


class TestResolveLink:
    async def test_civitai_url_returns_metadata(self, client, monkeypatch):
        captured = {}

        async def _resolve(parsed):
            captured["parsed"] = parsed
            return {
                "name": "Great LoRA",
                "base_model": "SD 1.5",
                "description": "Desc",
                "tags": ["tag1"],
                "trigger_words": ["word"],
                "version_name": "v1",
                "civitai_version_id": "900",
                "civitai_model_id": "77",
                "model_type": "loras",
                "thumbnail": "https://example.com/a.jpg",
            }

        monkeypatch.setattr("py.routes.models._resolve_model_link", _resolve)

        resp = await client.post(
            "/tiny-model-manager/api/models/resolve-link",
            json={"url": "https://civitai.com/models/77"},
        )
        assert resp.status == 200
        data = (await resp.json())["data"]
        assert data["platform"] == "civitai"
        assert data["source_id"] == "900"
        assert data["metadata"]["name"] == "Great LoRA"
        assert captured["parsed"].model_id == "77"

    async def test_huggingface_url_returns_repo_id_as_source(self, client, monkeypatch):
        async def _resolve(parsed):
            return {
                "name": "cool-lora",
                "base_model": "SDXL",
                "description": "",
                "tags": [],
                "trigger_words": [],
                "version_name": "",
                "civitai_version_id": "",
                "civitai_model_id": "",
                "model_type": "loras",
                "thumbnail": "",
            }

        monkeypatch.setattr("py.routes.models._resolve_model_link", _resolve)

        resp = await client.post(
            "/tiny-model-manager/api/models/resolve-link",
            json={"url": "https://huggingface.co/owner/cool-lora"},
        )
        assert resp.status == 200
        data = (await resp.json())["data"]
        assert data["platform"] == "huggingface"
        assert data["source_id"] == "owner/cool-lora"

    async def test_missing_url_returns_400(self, client):
        resp = await client.post("/tiny-model-manager/api/models/resolve-link", json={})
        assert resp.status == 400

    async def test_invalid_url_returns_400(self, client):
        resp = await client.post(
            "/tiny-model-manager/api/models/resolve-link",
            json={"url": "https://example.com/models/1"},
        )
        assert resp.status == 400
        assert (await resp.json())["error"] == "invalid_url"

    async def test_no_match_returns_404(self, client, monkeypatch):
        monkeypatch.setattr(
            "py.routes.models._resolve_model_link", lambda parsed: _async_return(None)
        )
        resp = await client.post(
            "/tiny-model-manager/api/models/resolve-link",
            json={"url": "https://civitai.com/models/12345"},
        )
        assert resp.status == 404
        assert (await resp.json())["error"] == "not_found"

    async def test_provider_error_returns_503(self, client, monkeypatch):
        import httpx as _httpx

        async def _raise(parsed):
            raise _httpx.HTTPError("network error")

        monkeypatch.setattr("py.routes.models._resolve_model_link", _raise)

        resp = await client.post(
            "/tiny-model-manager/api/models/resolve-link",
            json={"url": "https://civitai.com/models/12345"},
        )
        assert resp.status == 503
        assert (await resp.json())["error"] == "provider_unavailable"
