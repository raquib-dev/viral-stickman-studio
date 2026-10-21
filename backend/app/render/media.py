"""ffmpeg/ffprobe helpers shared by the mock backend, continuity frames and the stitch stage."""
from __future__ import annotations

import asyncio
import json
import os
import subprocess
from pathlib import Path

from ..settings import ffmpeg_bin, ffprobe_bin

DIMS = {
    ("16:9", "360p"): (640, 360), ("16:9", "720p"): (1280, 720), ("16:9", "1080p"): (1920, 1080), ("16:9", "4k"): (3840, 2160),
    ("9:16", "360p"): (360, 640), ("9:16", "720p"): (720, 1280), ("9:16", "1080p"): (1080, 1920), ("9:16", "4k"): (2160, 3840),
}


class MediaError(RuntimeError):
    pass


def dims(ratio: str, resolution: str) -> tuple[int, int]:
    return DIMS[(ratio, resolution)]


def run_ffmpeg(args: list[str], timeout: float = 600) -> str:
    cmd = [ffmpeg_bin(), "-hide_banner", "-nostdin", "-y", *args]
    p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
    if p.returncode != 0:
        raise MediaError(f"ffmpeg failed ({p.returncode}): {p.stderr.strip()[-800:]}")
    return p.stderr


async def arun_ffmpeg(args: list[str], timeout: float = 600) -> str:
    return await asyncio.to_thread(run_ffmpeg, args, timeout)


def probe(path: Path) -> dict:
    cmd = [ffprobe_bin(), "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)]
    p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if p.returncode != 0:
        raise MediaError(f"ffprobe failed: {p.stderr.strip()[:400]}")
    d = json.loads(p.stdout)
    v = next((s for s in d["streams"] if s["codec_type"] == "video"), None)
    a = next((s for s in d["streams"] if s["codec_type"] == "audio"), None)
    return {"duration": float(d["format"].get("duration", 0)), "video_duration": float((v or {}).get("duration") or 0),
            "width": v and int(v["width"]),
            "height": v and int(v["height"]), "has_audio": a is not None}


def last_frame(video: Path, out_png: Path) -> Path:
    run_ffmpeg(["-sseof", "-0.1", "-i", str(video), "-frames:v", "1", "-update", "1", str(out_png)])
    return out_png


def fontfile_arg() -> str:
    """drawtext needs an explicit font on Windows builds without fontconfig."""
    if os.name == "nt":
        for f in ("C:/Windows/Fonts/arialbd.ttf", "C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/segoeui.ttf"):
            if Path(f).exists():
                return "fontfile='" + f.replace(":", "\\:") + "':"
    return ""


def filter_path(p: Path) -> str:
    """Escape a path for use inside an ffmpeg filter argument (Windows drive colons, backslashes)."""
    s = str(p.resolve()).replace("\\", "/")
    return s.replace(":", "\\:").replace("'", "\\'")
