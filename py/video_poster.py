"""Extract a poster (first frame) from a video file."""

import os
import shutil
import subprocess


def extract_video_poster(video_path: str) -> str | None:
    """Extract the first frame of a video as a JPEG poster image.

    Tries PyAV first (bundled libav, no system dependency), then falls back
    to a system ffmpeg subprocess. Returns None if both are unavailable.
    The poster is saved as <video_stem>_poster.jpg beside the video.
    """
    poster_path = os.path.splitext(video_path)[0] + "_poster.jpg"
    if os.path.exists(poster_path):
        return poster_path
    return _extract_with_av(video_path, poster_path) or _extract_with_ffmpeg(
        video_path, poster_path
    )


def _extract_with_av(video_path: str, poster_path: str) -> str | None:
    try:
        import av  # type: ignore[import-untyped]

        with av.open(video_path) as container:
            stream = next(
                (s for s in container.streams if s.type == "video"),
                None,
            )
            if stream is None:
                return None
            for frame in container.decode(stream):
                if not hasattr(frame, "to_image"):
                    continue
                img = frame.to_image()  # type: ignore[union-attr]
                img.save(poster_path, "JPEG", quality=85)
                return poster_path
    except Exception:
        pass
    return None


def _extract_with_ffmpeg(video_path: str, poster_path: str) -> str | None:
    if not shutil.which("ffmpeg"):
        return None
    try:
        result = subprocess.run(
            ["ffmpeg", "-i", video_path, "-vframes", "1", "-q:v", "2", poster_path, "-y"],
            capture_output=True,
            timeout=30,
        )
        if result.returncode == 0 and os.path.exists(poster_path):
            return poster_path
    except Exception:
        pass
    return None
