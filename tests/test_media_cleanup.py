"""Unit tests for py/services/media_cleanup.py (F-95)."""

import os

import pytest


@pytest.fixture()
def media_root(ext_dir):
    from py import config as cfg

    root = cfg.media_dir()
    os.makedirs(root, exist_ok=True)
    return root


def _make_media_dir(media_root: str, media_hash: str, *names: str) -> list[str]:
    """Create <media_root>/<hash>/ with the given files; return their paths."""
    folder = os.path.join(media_root, media_hash)
    os.makedirs(folder, exist_ok=True)
    paths = []
    for name in names or ("0.jpg",):
        path = os.path.join(folder, name)
        open(path, "wb").close()
        paths.append(path)
    return paths


async def _register_model(filename: str, media_hash: str, paths: list[str]) -> int:
    from py.db import model_repo

    model_id = await model_repo.upsert_model_with_meta(
        filename, "checkpoints", "civitai", "123", "", [], [], media_hash=media_hash
    )
    for path in paths:
        await model_repo.add_media(model_id, "image", path)
    return model_id


class TestMediaSubdir:
    def test_resolves_inside_media_dir(self, media_root):
        from py.services.media_cleanup import media_subdir

        assert media_subdir("abc123") == os.path.join(os.path.realpath(media_root), "abc123")

    @pytest.mark.parametrize("bad", ["../evil", "", "abc/def", "a" * 129])
    def test_rejects_unsafe_hash(self, media_root, bad):
        from py.services.media_cleanup import media_subdir

        with pytest.raises(ValueError, match="Invalid media hash"):
            media_subdir(bad)

    def test_metadata_fetcher_shares_the_same_helper(self):
        from py.services import media_cleanup, metadata_fetcher

        assert metadata_fetcher._media_subdir is media_cleanup.media_subdir


class TestCleanupModelMedia:
    async def test_deletes_media_dir_when_hash_is_unreferenced(self, media_root):
        from py.services.media_cleanup import cleanup_model_media

        _make_media_dir(media_root, "orphan", "0.jpg", "1.mp4")

        removed = await cleanup_model_media("orphan")

        assert removed == 2
        assert not os.path.isdir(os.path.join(media_root, "orphan"))

    async def test_keeps_media_owned_by_the_catalog_entry(self, media_root):
        from py.db import model_repo
        from py.services.media_cleanup import cleanup_model_media

        paths = _make_media_dir(media_root, "shared")
        await model_repo.upsert_catalog_entry(
            "civitai", "123", "", "Entry", "", "", media_hash="shared"
        )

        removed = await cleanup_model_media("shared")

        assert removed == 0
        assert os.path.isfile(paths[0])

    async def test_keeps_media_still_claimed_by_another_model(self, media_root):
        from py.services.media_cleanup import cleanup_model_media

        paths = _make_media_dir(media_root, "shared")
        await _register_model("other.safetensors", "shared", paths)

        removed = await cleanup_model_media("shared")

        assert removed == 0
        assert os.path.isfile(paths[0])

    async def test_hashless_model_deletes_nothing(self, media_root):
        from py.services.media_cleanup import cleanup_model_media

        legacy = os.path.join(media_root, "legacy.jpg")
        open(legacy, "wb").close()

        assert await cleanup_model_media("") == 0
        assert os.path.isfile(legacy)

    async def test_invalid_hash_deletes_nothing(self, media_root):
        from py.services.media_cleanup import cleanup_model_media

        victim = _make_media_dir(media_root, "keepme")[0]

        removed = await cleanup_model_media("../keepme")

        assert removed == 0
        assert os.path.isfile(victim)


class TestCleanupStaleMedia:
    async def test_disabled_by_default(self, media_root):
        from py.services.media_cleanup import cleanup_stale_media

        paths = _make_media_dir(media_root, "orphan")

        assert await cleanup_stale_media() == {"dirs": 0, "files": 0}
        assert os.path.isfile(paths[0])

    async def test_removes_orphan_dirs_and_keeps_live_ones(self, media_root):
        from py import config as cfg
        from py.db import model_repo
        from py.services.media_cleanup import cleanup_stale_media

        cfg.save_settings({"cleanup_stale_media_on_start": True})
        orphan = _make_media_dir(media_root, "orphan", "0.jpg", "1.jpg")
        model_media = _make_media_dir(media_root, "live-model")
        catalog_media = _make_media_dir(media_root, "live-catalog")
        await _register_model("a.safetensors", "live-model", model_media)
        await model_repo.upsert_catalog_entry(
            "civitai", "123", "", "Entry", "", "", media_hash="live-catalog"
        )

        result = await cleanup_stale_media()

        assert result == {"dirs": 1, "files": 2}
        assert not os.path.exists(os.path.dirname(orphan[0]))
        assert os.path.isfile(model_media[0])
        assert os.path.isfile(catalog_media[0])

    async def test_removes_unreferenced_loose_files_only(self, media_root):
        from py import config as cfg
        from py.services.media_cleanup import cleanup_stale_media

        cfg.save_settings({"cleanup_stale_media_on_start": True})
        stale = os.path.join(media_root, "stale.jpg")
        kept = os.path.join(media_root, "kept.jpg")
        open(stale, "wb").close()
        open(kept, "wb").close()
        await _register_model("a.safetensors", "", [kept])

        result = await cleanup_stale_media()

        assert result == {"dirs": 0, "files": 1}
        assert not os.path.exists(stale)
        assert os.path.isfile(kept)

    async def test_deletes_cached_video_posters_in_orphan_dirs(self, media_root):
        from py import config as cfg
        from py.services.media_cleanup import cleanup_stale_media

        cfg.save_settings({"cleanup_stale_media_on_start": True})
        # A poster is written beside its video and has no model_media row of its own.
        _make_media_dir(media_root, "orphan", "0.mp4", "0_poster.jpg")

        assert await cleanup_stale_media() == {"dirs": 1, "files": 2}

    async def test_notifies_when_files_were_removed(self, media_root):
        from py import config as cfg
        from py.services import backend_notifier
        from py.services.media_cleanup import cleanup_stale_media

        cfg.save_settings({"cleanup_stale_media_on_start": True})
        _make_media_dir(media_root, "orphan")
        backend_notifier.flush()

        await cleanup_stale_media()

        messages = [n["message"] for n in backend_notifier.flush()]
        assert any("stale media" in m for m in messages)

    async def test_stays_quiet_when_nothing_was_removed(self, media_root):
        from py import config as cfg
        from py.services import backend_notifier
        from py.services.media_cleanup import cleanup_stale_media

        cfg.save_settings({"cleanup_stale_media_on_start": True})
        backend_notifier.flush()

        assert await cleanup_stale_media() == {"dirs": 0, "files": 0}
        assert backend_notifier.flush() == []

    async def test_missing_media_dir_is_not_an_error(self, ext_dir):
        from py import config as cfg
        from py.services.media_cleanup import cleanup_stale_media

        cfg.save_settings(
            {
                "cleanup_stale_media_on_start": True,
                "media_dir": os.path.join(ext_dir, "gone"),
            }
        )

        assert await cleanup_stale_media() == {"dirs": 0, "files": 0}

    async def test_relative_media_dir_is_refused(self, ext_dir):
        from py import config as cfg
        from py.services.media_cleanup import cleanup_stale_media

        # A relative path would resolve against ComfyUI's CWD, not the intended folder.
        cfg.save_settings({"cleanup_stale_media_on_start": True, "media_dir": "relative/media"})

        assert await cleanup_stale_media() == {"dirs": 0, "files": 0}
