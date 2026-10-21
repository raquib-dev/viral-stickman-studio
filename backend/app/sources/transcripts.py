"""Public transcripts. The YouTube Data API cannot download other people's captions, so we use yt-dlp's
public auto-captions (no login, low volume: the method ig-viral documents). yt-dlp is optional; without
it the user pastes transcripts in the Discover screen."""
from __future__ import annotations

import importlib.util
import subprocess
import sys
import tempfile
from pathlib import Path


def ytdlp_available() -> bool:
    return importlib.util.find_spec("yt_dlp") is not None


def fetch_auto_captions(url: str, timeout: float = 120) -> str | None:
    """Return the raw json3 caption text, or None if unavailable."""
    if not ytdlp_available():
        return None
    with tempfile.TemporaryDirectory(prefix="vss-subs-") as d:
        cmd = [sys.executable, "-m", "yt_dlp", "--skip-download", "--write-auto-subs", "--write-subs",
               "--sub-langs", "en.*,en", "--sub-format", "json3", "--no-playlist", "--quiet", "--no-warnings",
               "-o", str(Path(d) / "sub"), url]
        try:
            subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            return None
        files = sorted(Path(d).glob("sub*.json3"))
        return files[0].read_text(encoding="utf-8") if files else None
