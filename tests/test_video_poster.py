"""Unit tests for py/video_poster.py: PyAV and ffmpeg poster extraction."""

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture()
def video_file(tmp_path):
    p = tmp_path / "clip.mp4"
    p.write_bytes(b"\x00\x00\x00\x18ftyp")
    return str(p)


class TestExtractVideoPoster:
    def test_returns_none_when_both_extractors_fail(self, video_file):
        from py.video_poster import extract_video_poster

        with (
            patch("py.video_poster._extract_with_av", return_value=None),
            patch("py.video_poster._extract_with_ffmpeg", return_value=None),
        ):
            assert extract_video_poster(video_file) is None

    def test_returns_existing_poster_without_re_extracting(self, video_file):
        from py.video_poster import extract_video_poster

        poster_path = os.path.splitext(video_file)[0] + "_poster.jpg"
        Path(poster_path).write_bytes(b"\xff\xd8\xff")

        with (
            patch("py.video_poster._extract_with_av") as mock_av,
            patch("py.video_poster._extract_with_ffmpeg") as mock_ffmpeg,
        ):
            result = extract_video_poster(video_file)

        assert result == poster_path
        mock_av.assert_not_called()
        mock_ffmpeg.assert_not_called()

    def test_prefers_av_over_ffmpeg(self, video_file):
        from py.video_poster import extract_video_poster

        poster_path = os.path.splitext(video_file)[0] + "_poster.jpg"

        with (
            patch("py.video_poster._extract_with_av", return_value=poster_path) as mock_av,
            patch("py.video_poster._extract_with_ffmpeg") as mock_ffmpeg,
        ):
            result = extract_video_poster(video_file)

        assert result == poster_path
        mock_av.assert_called_once()
        mock_ffmpeg.assert_not_called()

    def test_falls_back_to_ffmpeg_when_av_fails(self, video_file):
        from py.video_poster import extract_video_poster

        poster_path = os.path.splitext(video_file)[0] + "_poster.jpg"

        with (
            patch("py.video_poster._extract_with_av", return_value=None),
            patch("py.video_poster._extract_with_ffmpeg", return_value=poster_path),
        ):
            result = extract_video_poster(video_file)

        assert result == poster_path


class TestExtractWithAv:
    def test_returns_none_when_av_not_importable(self, video_file):
        from py.video_poster import _extract_with_av

        poster_path = os.path.splitext(video_file)[0] + "_poster.jpg"
        with patch.dict("sys.modules", {"av": None}):
            result = _extract_with_av(video_file, poster_path)

        assert result is None

    def test_writes_jpeg_and_returns_path(self, video_file):
        from py.video_poster import _extract_with_av

        poster_path = os.path.splitext(video_file)[0] + "_poster.jpg"

        mock_frame = MagicMock()
        mock_img = MagicMock()
        mock_frame.to_image.return_value = mock_img

        mock_stream = MagicMock()
        mock_stream.type = "video"

        mock_container = MagicMock()
        mock_container.__enter__ = lambda s: s
        mock_container.__exit__ = MagicMock(return_value=False)
        mock_container.streams = [mock_stream]
        mock_container.decode.return_value = [mock_frame]

        mock_av = MagicMock()
        mock_av.open.return_value = mock_container

        with patch.dict("sys.modules", {"av": mock_av}):
            result = _extract_with_av(video_file, poster_path)

        mock_img.save.assert_called_once_with(poster_path, "JPEG", quality=85)
        assert result == poster_path

    def test_returns_none_when_no_video_stream(self, video_file):
        from py.video_poster import _extract_with_av

        poster_path = os.path.splitext(video_file)[0] + "_poster.jpg"

        mock_stream = MagicMock()
        mock_stream.type = "audio"

        mock_container = MagicMock()
        mock_container.__enter__ = lambda s: s
        mock_container.__exit__ = MagicMock(return_value=False)
        mock_container.streams = [mock_stream]

        mock_av = MagicMock()
        mock_av.open.return_value = mock_container

        with patch.dict("sys.modules", {"av": mock_av}):
            result = _extract_with_av(video_file, poster_path)

        assert result is None


class TestExtractWithFfmpeg:
    def test_returns_none_when_ffmpeg_not_found(self, video_file):
        from py.video_poster import _extract_with_ffmpeg

        poster_path = os.path.splitext(video_file)[0] + "_poster.jpg"
        with patch("py.video_poster.shutil.which", return_value=None):
            result = _extract_with_ffmpeg(video_file, poster_path)

        assert result is None

    def test_returns_poster_on_success(self, video_file):
        from py.video_poster import _extract_with_ffmpeg

        poster_path = os.path.splitext(video_file)[0] + "_poster.jpg"

        def fake_run(cmd, **_kw):
            Path(cmd[-2]).write_bytes(b"\xff\xd8\xff")
            return MagicMock(returncode=0)

        with (
            patch("py.video_poster.shutil.which", return_value="/usr/bin/ffmpeg"),
            patch("py.video_poster.subprocess.run", side_effect=fake_run),
        ):
            result = _extract_with_ffmpeg(video_file, poster_path)

        assert result == poster_path

    def test_returns_none_on_nonzero_returncode(self, video_file):
        from py.video_poster import _extract_with_ffmpeg

        poster_path = os.path.splitext(video_file)[0] + "_poster.jpg"
        with (
            patch("py.video_poster.shutil.which", return_value="/usr/bin/ffmpeg"),
            patch("py.video_poster.subprocess.run", return_value=MagicMock(returncode=1)),
        ):
            result = _extract_with_ffmpeg(video_file, poster_path)

        assert result is None
