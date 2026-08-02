"""Unit tests for the workflow store service (F-129).

The extraction path carries the security weight of the feature — the payload is an
attacker-influenceable archive — so it gets the bulk of the coverage here.
"""

import json
import os
import zipfile

import folder_paths
import pytest

from py.services import workflow_store as ws

GRAPH = {
    "last_node_id": 2,
    "nodes": [{"id": 1, "type": "KSampler"}, {"id": 2, "type": "VAEDecode"}],
    "links": [],
}
OTHER_GRAPH = {"last_node_id": 1, "nodes": [{"id": 1, "type": "LoadImage"}], "links": []}


def _write_zip(path, members: dict[str, bytes]) -> str:
    with zipfile.ZipFile(path, "w") as archive:
        for name, payload in members.items():
            archive.writestr(name, payload)
    return str(path)


def _graph_bytes(graph=GRAPH) -> bytes:
    return json.dumps(graph).encode()


class TestExtractGraphs:
    def test_single_graph_zip(self, tmp_path):
        path = _write_zip(tmp_path / "a.zip", {"My Workflow.json": _graph_bytes()})
        graphs = ws.extract_graphs(path)
        assert graphs == [("My Workflow.json", GRAPH)]

    def test_multiple_graphs_in_one_zip(self, tmp_path):
        """The real CivitAI case: one archive, several ComfyUI graphs."""
        path = _write_zip(
            tmp_path / "a.zip",
            {"auto.json": _graph_bytes(), "manual.json": _graph_bytes(OTHER_GRAPH)},
        )
        graphs = ws.extract_graphs(path)
        assert [name for name, _ in graphs] == ["auto.json", "manual.json"]
        assert graphs[1][1] == OTHER_GRAPH

    def test_non_json_members_are_ignored(self, tmp_path):
        path = _write_zip(
            tmp_path / "a.zip",
            {
                "readme.txt": b"hello",
                "preview.png": b"\x89PNG",
                "wf.json": _graph_bytes(),
            },
        )
        assert ws.extract_graphs(path) == [("wf.json", GRAPH)]

    def test_json_that_is_not_a_graph_is_ignored(self, tmp_path):
        path = _write_zip(
            tmp_path / "a.zip",
            {"package.json": b'{"name": "x"}', "wf.json": _graph_bytes()},
        )
        assert ws.extract_graphs(path) == [("wf.json", GRAPH)]

    def test_malformed_json_member_is_ignored(self, tmp_path):
        path = _write_zip(
            tmp_path / "a.zip", {"broken.json": b"{not json", "wf.json": _graph_bytes()}
        )
        assert ws.extract_graphs(path) == [("wf.json", GRAPH)]

    def test_zip_slip_member_is_dropped(self, tmp_path):
        path = _write_zip(
            tmp_path / "a.zip",
            {"../../evil.json": _graph_bytes(), "ok.json": _graph_bytes(OTHER_GRAPH)},
        )
        assert ws.extract_graphs(path) == [("ok.json", OTHER_GRAPH)]

    def test_absolute_member_name_is_dropped(self, tmp_path):
        path = _write_zip(
            tmp_path / "a.zip",
            {"/etc/evil.json": _graph_bytes(), "ok.json": _graph_bytes(OTHER_GRAPH)},
        )
        assert ws.extract_graphs(path) == [("ok.json", OTHER_GRAPH)]

    def test_macos_resource_fork_is_ignored(self, tmp_path):
        path = _write_zip(
            tmp_path / "a.zip",
            {"__MACOSX/._wf.json": _graph_bytes(), "wf.json": _graph_bytes()},
        )
        assert ws.extract_graphs(path) == [("wf.json", GRAPH)]

    def test_oversize_member_is_skipped(self, tmp_path, monkeypatch):
        monkeypatch.setattr(ws, "_MAX_GRAPH_BYTES", 10)
        path = _write_zip(tmp_path / "a.zip", {"wf.json": _graph_bytes()})
        with pytest.raises(ws.WorkflowPayloadError):
            ws.extract_graphs(path)

    def test_graph_cap_is_enforced(self, tmp_path, monkeypatch):
        monkeypatch.setattr(ws, "_MAX_GRAPHS", 2)
        members = {f"wf{i}.json": _graph_bytes() for i in range(5)}
        path = _write_zip(tmp_path / "a.zip", members)
        assert len(ws.extract_graphs(path)) == 2

    def test_bare_json_payload(self, tmp_path):
        """A non-archive response is still accepted when it is a graph itself."""
        path = tmp_path / "workflow.json"
        path.write_bytes(_graph_bytes())
        assert ws.extract_graphs(str(path)) == [("workflow.json", GRAPH)]

    def test_garbage_payload_raises(self, tmp_path):
        path = tmp_path / "payload.bin"
        path.write_bytes(b"\x00\x01not a zip and not json")
        with pytest.raises(ws.WorkflowPayloadError) as exc:
            ws.extract_graphs(str(path))
        assert "no_workflow_json" in str(exc.value)

    def test_empty_zip_raises(self, tmp_path):
        path = _write_zip(tmp_path / "a.zip", {"readme.txt": b"nothing here"})
        with pytest.raises(ws.WorkflowPayloadError):
            ws.extract_graphs(path)


class TestSafeGraphFilename:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("plain.json", "plain.json"),
            ("sub/dir/nested.json", "nested.json"),
            ("..\\..\\evil.json", "evil.json"),
            ("weird:name*.json", "weird_name_.json"),
            ("...json", "workflow.json"),
            ("", "workflow.json"),
        ],
    )
    def test_normalisation(self, raw, expected):
        assert ws._safe_graph_filename(raw) == expected

    def test_length_is_capped(self):
        assert len(ws._safe_graph_filename("x" * 500)) == len("x" * 120) + len(".json")


class TestWorkflowSubdir:
    def test_valid_hash_resolves_inside_root(self, ext_dir):
        from py import config as cfg

        resolved = ws.workflow_subdir("abc123", "42")
        assert resolved.startswith(os.path.realpath(cfg.workflows_dir()))

    @pytest.mark.parametrize("bad", ["../escape", "a/b", "", "with.dot"])
    def test_traversing_hash_rejected(self, ext_dir, bad):
        with pytest.raises(ValueError):
            ws.workflow_subdir(bad)


class TestMediaHash:
    def test_differs_from_catalog_hash(self):
        from py.services.metadata_fetcher import catalog_media_hash

        assert ws.workflow_media_hash("civitai", "1") != catalog_media_hash("civitai", "1")


class TestExportWorkflow:
    @pytest.fixture()
    def user_dir(self, tmp_path, monkeypatch):
        target = tmp_path / "comfy_user"
        monkeypatch.setattr(folder_paths, "user_directory", str(target))
        return target / "default" / "workflows"

    async def _store_one(self, name="My Graph"):
        from py.db import workflow_repo

        media_hash = ws.workflow_media_hash("civitai", "1")
        entry_id = await workflow_repo.upsert_workflow_entry(
            source_platform="civitai", source_page_id="1", media_hash=media_hash
        )
        dest_dir = ws.workflow_subdir(media_hash, "7")
        os.makedirs(dest_dir, exist_ok=True)
        with open(os.path.join(dest_dir, f"{name}.json"), "w", encoding="utf-8") as f:
            json.dump(GRAPH, f)
        return await workflow_repo.upsert_workflow(
            entry_id=entry_id,
            name=name,
            local_path=os.path.join(media_hash, "7", f"{name}.json"),
            version_id="7",
        )

    async def test_export_writes_into_comfyui_user_workflows(self, ext_dir, user_dir):
        workflow_id = await self._store_one()
        path = await ws.export_workflow(workflow_id)
        assert path == str(user_dir / "My Graph.json")
        with open(path, encoding="utf-8") as f:
            assert json.load(f) == GRAPH

    async def test_second_export_gets_a_suffix(self, ext_dir, user_dir):
        workflow_id = await self._store_one()
        first = await ws.export_workflow(workflow_id)
        second = await ws.export_workflow(workflow_id)
        assert first != second
        assert second.endswith("My Graph_1.json")

    async def test_unknown_workflow_raises(self, ext_dir, user_dir):
        with pytest.raises(FileNotFoundError):
            await ws.export_workflow(999)

    async def test_missing_graph_file_raises(self, ext_dir, user_dir):
        workflow_id = await self._store_one()
        from py.db import workflow_repo

        workflow = await workflow_repo.get_workflow(workflow_id)
        os.remove(ws.graph_path(workflow))
        with pytest.raises(FileNotFoundError):
            await ws.export_workflow(workflow_id)


class TestDeleteEntry:
    async def test_removes_rows_files_and_media(self, ext_dir):
        from py import config as cfg
        from py.db import workflow_repo
        from py.services import media_cleanup

        media_hash = ws.workflow_media_hash("civitai", "5")
        entry_id = await workflow_repo.upsert_workflow_entry(
            source_platform="civitai", source_page_id="5", media_hash=media_hash
        )
        graph_dir = ws.workflow_subdir(media_hash, "9")
        os.makedirs(graph_dir, exist_ok=True)
        with open(os.path.join(graph_dir, "wf.json"), "w", encoding="utf-8") as f:
            json.dump(GRAPH, f)
        await workflow_repo.upsert_workflow(
            entry_id=entry_id,
            name="wf",
            local_path=os.path.join(media_hash, "9", "wf.json"),
            version_id="9",
        )
        media_dir = media_cleanup.media_subdir(media_hash)
        os.makedirs(media_dir, exist_ok=True)
        with open(os.path.join(media_dir, "0.jpg"), "wb") as f:
            f.write(b"jpg")

        assert await ws.delete_entry(entry_id) is True

        assert await workflow_repo.get_workflow_entry(entry_id) is None
        assert not os.path.exists(os.path.join(cfg.workflows_dir(), media_hash))
        assert not os.path.exists(media_dir)

    async def test_unknown_entry_returns_false(self, ext_dir):
        assert await ws.delete_entry(4242) is False


class TestDownloadWorkflow:
    @pytest.fixture()
    def civitai_page(self):
        return {
            "id": 123,
            "name": "Cool Workflow Pack",
            "description": "<p>does things</p>",
            "tags": ["comfyui", "tool"],
            "modelVersions": [
                {
                    "id": 456,
                    "name": "v1.0",
                    "baseModel": "Flux.1 D",
                    "files": [
                        {
                            "name": "pack.zip",
                            "type": "Archive",
                            "primary": True,
                            "downloadUrl": "https://civitai.com/api/download/models/456",
                        },
                    ],
                    "images": [{"url": "https://image.civitai.com/a.jpg", "type": "image"}],
                }
            ],
        }

    @pytest.fixture()
    def stub_provider(self, monkeypatch, civitai_page, tmp_path):
        async def fake_page(model_id):
            return civitai_page

        async def fake_fetch(url, dest, headers):
            _write_zip(
                dest, {"auto.json": _graph_bytes(), "manual.json": _graph_bytes(OTHER_GRAPH)}
            )

        async def no_media(media_hash, urls):
            return None

        monkeypatch.setattr(ws.civitai, "get_model_page", fake_page)
        monkeypatch.setattr(ws, "_fetch_archive", fake_fetch)
        monkeypatch.setattr(ws, "_download_media", no_media)

    async def test_stores_entry_and_every_graph(self, ext_dir, stub_provider):
        from py.db import workflow_repo

        result = await ws.download_workflow("123", "456")

        assert len(result["workflows"]) == 2
        entry = await workflow_repo.get_workflow_entry(result["entry_id"])
        assert entry["display_name"] == "Cool Workflow Pack"
        assert entry["base_model"] == "Flux.1 D"
        assert entry["tags"] == ["comfyui", "tool"]
        assert [i["name"] for i in entry["items"]] == ["auto", "manual"]
        assert entry["items"][0]["node_count"] == 2

    async def test_graphs_are_written_to_disk(self, ext_dir, stub_provider):
        from py.db import workflow_repo

        result = await ws.download_workflow("123", "456")
        workflow = await workflow_repo.get_workflow(result["workflows"][0]["id"])
        assert ws.read_graph(workflow) == GRAPH

    async def test_repeat_download_upserts(self, ext_dir, stub_provider):
        from py.db import workflow_repo

        first = await ws.download_workflow("123", "456")
        second = await ws.download_workflow("123", "456")
        assert first["entry_id"] == second["entry_id"]
        entries = await workflow_repo.list_workflow_entries()
        assert len(entries) == 1
        assert len(entries[0]["items"]) == 2

    async def test_version_defaults_to_first(self, ext_dir, stub_provider):
        result = await ws.download_workflow("123")
        assert result["workflows"][0]["version_id"] == "456"

    async def test_unknown_version_falls_back_to_first(self, ext_dir, stub_provider):
        result = await ws.download_workflow("123", "999999")
        assert result["workflows"][0]["version_id"] == "456"

    async def test_disallowed_host_rejected(self, ext_dir, monkeypatch, civitai_page):
        civitai_page["modelVersions"][0]["files"][0]["downloadUrl"] = "http://169.254.169.254/x"

        async def fake_page(model_id):
            return civitai_page

        monkeypatch.setattr(ws.civitai, "get_model_page", fake_page)
        with pytest.raises(ValueError):
            await ws.download_workflow("123", "456")

    async def test_version_without_files_raises(self, ext_dir, monkeypatch, civitai_page):
        civitai_page["modelVersions"][0]["files"] = []

        async def fake_page(model_id):
            return civitai_page

        monkeypatch.setattr(ws.civitai, "get_model_page", fake_page)
        with pytest.raises(ws.WorkflowPayloadError):
            await ws.download_workflow("123", "456")

    async def test_page_without_versions_raises(self, ext_dir, monkeypatch):
        async def fake_page(model_id):
            return {"id": 1, "name": "x", "modelVersions": []}

        monkeypatch.setattr(ws.civitai, "get_model_page", fake_page)
        with pytest.raises(ws.WorkflowPayloadError):
            await ws.download_workflow("123")


class TestListEntryMedia:
    def test_lists_images_and_videos(self, ext_dir):
        from py.services import media_cleanup

        media_hash = ws.workflow_media_hash("civitai", "77")
        media_dir = media_cleanup.media_subdir(media_hash)
        os.makedirs(media_dir, exist_ok=True)
        for name in ("0.jpg", "1.mp4"):
            with open(os.path.join(media_dir, name), "wb") as f:
                f.write(b"x")
        items = ws.list_entry_media(media_hash)
        assert [i["media_type"] for i in items] == ["image", "video"]

    def test_missing_dir_is_empty(self, ext_dir):
        assert ws.list_entry_media(ws.workflow_media_hash("civitai", "nope")) == []

    def test_invalid_hash_is_empty(self, ext_dir):
        assert ws.list_entry_media("../escape") == []
