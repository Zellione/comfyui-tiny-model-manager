"""Unit tests for py/services/downloader.py — _stream_file, _run_download, resume_interrupted_downloads."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from py.services.downloader import DownloadTask, _Cancelled, _run_download, _stream_file


def _task(dest_path: str, **kwargs) -> DownloadTask:
    defaults = {
        "id": str(uuid.uuid4()),
        "url": "https://example.com/model.safetensors",
        "model_type": "checkpoints",
        "filename": "model.safetensors",
        "platform": "civitai",
        "source_id": "123",
        "dest_path": dest_path,
    }
    defaults.update(kwargs)
    return DownloadTask(**defaults)


class _AsyncCM:
    """Minimal async context manager that yields a fixed value."""

    def __init__(self, value):
        self._value = value

    async def __aenter__(self):
        return self._value

    async def __aexit__(self, *_):
        return False


class TestStreamFile:
    async def test_downloads_content_and_updates_progress(self, tmp_path):
        data = b"X" * 200
        task = _task(dest_path=str(tmp_path / "model.safetensors"))

        async def fake_aiter_bytes(_chunk_size):
            yield data

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.headers = {"content-length": "200"}
        mock_resp.aiter_bytes = fake_aiter_bytes

        mock_file = AsyncMock()
        mock_client = MagicMock()

        with patch("py.services.downloader.httpx.AsyncClient", return_value=_AsyncCM(mock_client)):
            with (
                patch("py.services.downloader.guarded_stream", return_value=_AsyncCM(mock_resp)),
                patch("py.services.downloader.aiofiles.open", return_value=_AsyncCM(mock_file)),
            ):
                await _stream_file(task, {})

        assert task.total_bytes == 200
        assert task.downloaded_bytes == 200
        assert task.progress == 100.0

    async def test_raises_cancelled_when_task_is_cancelled(self, tmp_path):
        task = _task(dest_path=str(tmp_path / "model.safetensors"))
        task.cancelled = True

        async def fake_aiter_bytes(_chunk_size):
            yield b"data"

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.headers = {}
        mock_resp.aiter_bytes = fake_aiter_bytes

        mock_file = AsyncMock()
        mock_client = MagicMock()

        with patch("py.services.downloader.httpx.AsyncClient", return_value=_AsyncCM(mock_client)):
            with (
                patch("py.services.downloader.guarded_stream", return_value=_AsyncCM(mock_resp)),
                patch("py.services.downloader.aiofiles.open", return_value=_AsyncCM(mock_file)),
            ):
                with pytest.raises(_Cancelled):
                    await _stream_file(task, {})

    async def test_uses_bounded_timeout(self, tmp_path):
        import httpx

        task = _task(dest_path=str(tmp_path / "model.safetensors"))
        captured: dict = {}

        async def fake_aiter_bytes(_chunk_size):
            yield b"data"

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.headers = {}
        mock_resp.aiter_bytes = fake_aiter_bytes

        mock_file = AsyncMock()
        mock_client = MagicMock()

        def fake_client(**kwargs):
            captured.update(kwargs)
            return _AsyncCM(mock_client)

        with patch("py.services.downloader.httpx.AsyncClient", fake_client):
            with (
                patch("py.services.downloader.guarded_stream", return_value=_AsyncCM(mock_resp)),
                patch("py.services.downloader.aiofiles.open", return_value=_AsyncCM(mock_file)),
            ):
                await _stream_file(task, {})

        # Redirects are resolved by guarded_stream, so the client itself must not follow
        # them — otherwise a hop could skip the per-hop allowlist check.
        assert captured.get("follow_redirects") in (None, False)
        # A stalled connection must eventually abort rather than hang the worker forever.
        timeout = captured.get("timeout")
        assert timeout is not None
        assert isinstance(timeout, httpx.Timeout)
        assert timeout.read is not None

    async def test_progress_zero_when_no_content_length(self, tmp_path):
        data = b"X" * 50
        task = _task(dest_path=str(tmp_path / "model.safetensors"))

        async def fake_aiter_bytes(_chunk_size):
            yield data

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.headers = {}  # no content-length
        mock_resp.aiter_bytes = fake_aiter_bytes

        mock_file = AsyncMock()
        mock_client = MagicMock()

        with patch("py.services.downloader.httpx.AsyncClient", return_value=_AsyncCM(mock_client)):
            with (
                patch("py.services.downloader.guarded_stream", return_value=_AsyncCM(mock_resp)),
                patch("py.services.downloader.aiofiles.open", return_value=_AsyncCM(mock_file)),
            ):
                await _stream_file(task, {})

        assert task.progress == 0.0


class TestRunDownload:
    async def test_success_sets_status_done(self, tmp_path, monkeypatch):
        import py.services.downloader as dl

        task = _task(dest_path=str(tmp_path / "model.safetensors"))

        async def fake_stream(t, headers):
            pass

        monkeypatch.setattr(dl, "_stream_file", fake_stream)
        monkeypatch.setattr(dl, "spawn", lambda coro: coro.close())

        await _run_download(task)

        assert task.status == "done"
        assert task.progress == 100.0
        assert task.completed_at is not None

    async def test_cancelled_sets_status_cancelled_and_removes_file(self, tmp_path, monkeypatch):
        import py.services.downloader as dl

        dest = tmp_path / "model.safetensors"
        dest.write_bytes(b"partial")
        task = _task(dest_path=str(dest))

        async def fake_stream(t, headers):
            raise _Cancelled()

        monkeypatch.setattr(dl, "_stream_file", fake_stream)
        monkeypatch.setattr(dl, "spawn", lambda coro: coro.close())

        await _run_download(task)

        assert task.status == "cancelled"
        assert task.completed_at is not None
        assert not dest.exists()

    async def test_error_sets_status_error_and_removes_file(self, tmp_path, monkeypatch):
        import py.services.downloader as dl

        dest = tmp_path / "model.safetensors"
        dest.write_bytes(b"partial")
        task = _task(dest_path=str(dest))

        async def fake_stream(t, headers):
            raise RuntimeError("connection refused")

        monkeypatch.setattr(dl, "_stream_file", fake_stream)
        monkeypatch.setattr(dl, "spawn", lambda coro: coro.close())

        await _run_download(task)

        assert task.status == "error"
        assert task.error is not None
        assert "connection refused" in task.error
        assert task.completed_at is not None
        assert not dest.exists()

    async def test_success_updates_history_status(self, ext_dir, tmp_path, monkeypatch):
        import py.services.downloader as dl
        from py.db import model_repo

        history_id = await model_repo.insert_download_history(
            model_name="m.safetensors",
            source="civitai",
            model_id="",
            version_id="1",
            file_url="https://example.com/m.safetensors",
            dest_path="m.safetensors",
            model_type="checkpoints",
        )
        task = _task(dest_path=str(tmp_path / "m.safetensors"), history_id=history_id)

        async def fake_stream(t, headers):
            pass

        monkeypatch.setattr(dl, "_stream_file", fake_stream)
        monkeypatch.setattr(dl, "spawn", lambda coro: coro.close())

        await _run_download(task)

        entries, _ = await model_repo.get_download_history()
        assert entries[0]["status"] == "done"

    async def test_cancelled_updates_history_status(self, ext_dir, tmp_path, monkeypatch):
        import py.services.downloader as dl
        from py.db import model_repo

        history_id = await model_repo.insert_download_history(
            model_name="m.safetensors",
            source="civitai",
            model_id="",
            version_id="1",
            file_url="https://example.com/m.safetensors",
            dest_path="m.safetensors",
            model_type="checkpoints",
        )
        task = _task(dest_path=str(tmp_path / "m.safetensors"), history_id=history_id)

        async def fake_stream(t, headers):
            raise _Cancelled()

        monkeypatch.setattr(dl, "_stream_file", fake_stream)
        monkeypatch.setattr(dl, "spawn", lambda coro: coro.close())

        await _run_download(task)

        entries, _ = await model_repo.get_download_history()
        assert entries[0]["status"] == "cancelled"

    async def test_error_updates_history_status(self, ext_dir, tmp_path, monkeypatch):
        import py.services.downloader as dl
        from py.db import model_repo

        history_id = await model_repo.insert_download_history(
            model_name="m.safetensors",
            source="civitai",
            model_id="",
            version_id="1",
            file_url="https://example.com/m.safetensors",
            dest_path="m.safetensors",
            model_type="checkpoints",
        )
        task = _task(dest_path=str(tmp_path / "m.safetensors"), history_id=history_id)

        async def fake_stream(t, headers):
            raise RuntimeError("network failure")

        monkeypatch.setattr(dl, "_stream_file", fake_stream)
        monkeypatch.setattr(dl, "spawn", lambda coro: coro.close())

        await _run_download(task)

        entries, _ = await model_repo.get_download_history()
        assert entries[0]["status"] == "error"

    async def test_on_complete_called_on_success(self, tmp_path, monkeypatch):
        import py.services.downloader as dl

        called_with = []

        async def on_complete(t):
            called_with.append(t)

        task = _task(dest_path=str(tmp_path / "m.safetensors"), on_complete=on_complete)

        async def fake_stream(t, headers):
            pass

        monkeypatch.setattr(dl, "_stream_file", fake_stream)
        monkeypatch.setattr(dl, "spawn", lambda coro: coro.close())

        await _run_download(task)

        assert called_with == [task]


class TestValidateTarget:
    def test_rejects_traversing_filename(self):
        import py.services.downloader as dl

        with pytest.raises(ValueError):
            dl.validate_target("checkpoints", "../../../../etc/passwd", "civitai")

    def test_rejects_traversing_model_type(self):
        import py.services.downloader as dl

        with pytest.raises(ValueError):
            dl.validate_target("../../evil", "model.safetensors", "civitai")

    def test_huggingface_strips_subfolder_and_contains(self):
        import os

        import folder_paths

        import py.services.downloader as dl

        dest = dl.validate_target("checkpoints", "split_files/model.safetensors", "huggingface")
        expected_dir = folder_paths.get_folder_paths("checkpoints")[0]
        assert os.path.basename(dest) == "model.safetensors"
        assert os.path.realpath(dest).startswith(os.path.realpath(expected_dir) + os.sep)

    def test_normal_civitai_filename_resolves_under_dest_dir(self):
        import os

        import folder_paths

        import py.services.downloader as dl

        dest = dl.validate_target("checkpoints", "model.safetensors", "civitai")
        expected_dir = folder_paths.get_folder_paths("checkpoints")[0]
        assert os.path.realpath(dest).startswith(os.path.realpath(expected_dir) + os.sep)


class TestEnqueueTraversalGuard:
    def test_enqueue_rejects_traversal_without_creating_task(self, monkeypatch):
        import py.services.downloader as dl

        monkeypatch.setattr(dl, "_ensure_worker", lambda: None)

        with pytest.raises(ValueError):
            dl.enqueue(
                url="https://civitai.com/api/download/models/1",
                model_type="checkpoints",
                filename="../../../../tmp/evil.txt",
                platform="civitai",
            )

        assert dl._tasks == {}


class TestResumeInterruptedDownloads:
    async def test_enqueues_interrupted_downloads(self, ext_dir, monkeypatch):
        import py.services.downloader as dl
        from py.db import model_repo

        history_id = await model_repo.insert_download_history(
            model_name="m.safetensors",
            source="civitai",
            model_id="",
            version_id="1",
            file_url="https://example.com/m.safetensors",
            dest_path="m.safetensors",
            model_type="checkpoints",
        )
        monkeypatch.setattr(dl, "spawn", lambda coro: coro.close())

        await dl.resume_interrupted_downloads()

        assert any(t.history_id == history_id for t in dl._tasks.values())

    async def test_removes_partial_file_before_requeue(self, ext_dir, monkeypatch):
        import folder_paths

        import py.services.downloader as dl
        from py.db import model_repo

        await model_repo.insert_download_history(
            model_name="partial.safetensors",
            source="civitai",
            model_id="",
            version_id="2",
            file_url="https://example.com/partial.safetensors",
            dest_path="partial.safetensors",
            model_type="checkpoints",
        )

        dest_dir = folder_paths.get_folder_paths("checkpoints")[0]
        import os

        os.makedirs(dest_dir, exist_ok=True)
        partial = os.path.join(dest_dir, "partial.safetensors")
        with open(partial, "wb") as f:
            f.write(b"incomplete")

        monkeypatch.setattr(dl, "spawn", lambda coro: coro.close())

        await dl.resume_interrupted_downloads()

        assert not os.path.exists(partial)

    async def test_skips_completed_downloads(self, ext_dir, monkeypatch):
        import py.services.downloader as dl
        from py.db import model_repo
        from py.db.database import get_db

        await model_repo.insert_download_history(
            model_name="done.safetensors",
            source="civitai",
            model_id="",
            version_id="3",
            file_url="https://example.com/done.safetensors",
            dest_path="done.safetensors",
            model_type="checkpoints",
        )
        async with get_db() as db:
            await db.execute("UPDATE download_history SET status='done'")
            await db.commit()

        before_count = len(dl._tasks)
        monkeypatch.setattr(dl, "spawn", lambda coro: coro.close())

        await dl.resume_interrupted_downloads()

        assert len(dl._tasks) == before_count


class TestQueueLoopBinding:
    """Regression: the module-level queue must be usable from each test's own event loop.

    ``asyncio.Queue`` binds to the first loop that uses it and refuses any other one after
    that, while pytest-asyncio hands every test a fresh loop. Without a per-test rebind the
    second of these two tests fails with "bound to a different event loop", and in the real
    suite the download queue silently stops draining — which used to hang CI indefinitely.
    """

    @staticmethod
    async def _roundtrip() -> None:
        import asyncio

        from py.services import downloader as dl

        sentinel = object()
        # The queue must be EMPTY when get() is awaited: Queue.get() only touches
        # _get_loop() (and thus binds) on the empty path — a pre-filled queue short-circuits
        # through get_nowait() and would never exercise the binding. This mirrors _worker,
        # which parks on an empty queue.
        asyncio.get_running_loop().call_later(0.01, dl._queue.put_nowait, sentinel)
        # wait_for keeps a regression failing fast instead of hanging the suite.
        assert await asyncio.wait_for(dl._queue.get(), timeout=1) is sentinel

    async def test_queue_usable_in_first_test(self):
        await self._roundtrip()

    async def test_queue_usable_in_second_test(self):
        await self._roundtrip()
