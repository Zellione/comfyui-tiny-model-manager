"""Unit tests for model_repo.set_file_hash (F-154)."""


class TestSetFileHash:
    async def test_updates_registered_model(self, ext_dir):
        from py.db import model_repo

        await model_repo.register_model("a.safetensors", "loras")
        updated = await model_repo.set_file_hash("a.safetensors", "abc123")
        assert updated is True
        assert await model_repo.get_file_hash_map() == {"abc123": "a.safetensors"}

    async def test_unknown_filename_is_a_no_op(self, ext_dir):
        from py.db import model_repo

        updated = await model_repo.set_file_hash("ghost.safetensors", "abc123")
        assert updated is False
        assert await model_repo.get_file_hash_map() == {}

    async def test_hash_is_lowercased(self, ext_dir):
        from py.db import model_repo

        await model_repo.register_model("b.safetensors", "loras")
        await model_repo.set_file_hash("b.safetensors", "ABC123")
        assert await model_repo.get_file_hash_map() == {"abc123": "b.safetensors"}
