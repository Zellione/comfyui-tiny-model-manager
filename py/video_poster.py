"""Extract a poster (first frame) from a video file using ffmpeg."""

import os
import shutil
import subprocess


def extract_video_poster(video_path: str) -> str | None:
    """Extract the first frame of a video as a JPEG poster image.

    Returns the poster path on success, None if ffmpeg is unavailable or fails.
    The poster is saved as <video_stem>_poster.jpg beside the video.
    """
    if not shutil.which("ffmpeg"):
        return None
    poster_path = os.path.splitext(video_path)[0] + "_poster.jpg"
    if os.path.exists(poster_path):
        return poster_path
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
