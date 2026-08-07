"""Tests for py/nodes/_utils.py — sync trigger-word lookup used by the ComfyUI nodes."""

from py.db import model_repo
from py.nodes._utils import get_trigger_words_sync


class TestGetTriggerWordsSync:
    def test_returns_joined_words(self, ext_dir):
        async def _seed():
            await model_repo.upsert_model("lora.safetensors", "loras", "", "", "")
            await model_repo.update_model_meta("lora.safetensors", "", ["word_a", "word_b"], [])

        import asyncio

        asyncio.get_event_loop().run_until_complete(_seed())

        assert get_trigger_words_sync("lora.safetensors") == "word_a, word_b"

    def test_returns_empty_for_unknown_model(self, ext_dir):
        assert get_trigger_words_sync("missing.safetensors") == ""

    async def test_returns_empty_when_loop_is_running(self, ext_dir):
        # Called from async context (a running loop) the sync helper must bail out
        # instead of deadlocking on run_until_complete.
        assert get_trigger_words_sync("lora.safetensors") == ""

    def test_returns_empty_on_repo_error(self, ext_dir, monkeypatch):
        async def _boom(filename):
            raise RuntimeError("db exploded")

        monkeypatch.setattr("py.db.model_repo.get_model_by_filename", _boom)
        assert get_trigger_words_sync("lora.safetensors") == ""
