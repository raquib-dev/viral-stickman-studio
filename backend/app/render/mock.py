"""Dry-run backend: ffmpeg placeholder clips with the exact duration, ratio and resolution, and an
audio tone, so the whole pipeline (stitch, captions, loudness, packaging) runs for free."""
from __future__ import annotations

import asyncio
import tempfile
import textwrap
from pathlib import Path

from .base import ClipResult, ClipSpec, Log
from .media import arun_ffmpeg, dims, fontfile_arg, last_frame

PALETTE = ["0x14181f", "0x1b1420", "0x101c1a", "0x1f1a12", "0x121a24", "0x1e1216"]


class MockBackend:
    name = "mock"

    async def render_clip(self, clip: ClipSpec, prev: ClipResult | None, log: Log) -> ClipResult:
        w, h = dims(clip.ratio, clip.resolution)
        out = clip.out_path
        assert out is not None
        out.parent.mkdir(parents=True, exist_ok=True)
        # kept short and above the caption band so dry-run captions stay readable (real Omni clips carry no text)
        lines = [f"DRY RUN - clip {clip.index + 1}", clip.label[:40]] + textwrap.wrap(clip.vo, 30)[:3]
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as fh:
            fh.write("\n".join(lines))
            txt = Path(fh.name)
        font = fontfile_arg()
        size = max(16, w // 30)
        bg = PALETTE[clip.index % len(PALETTE)]
        tf = str(txt).replace("\\", "/").replace(":", "\\:")
        vf = (f"drawtext={font}textfile='{tf}':fontcolor=white:fontsize={size}:line_spacing={size // 3}:"
              f"x=(w-tw)/2:y=h*0.30,"
              # a moving dot stands in for motion so scene-change and frame checks have something to see
              f"drawbox=x='mod(t*{w // 4}\\,{w})':y={int(h * 0.75)}:w={size}:h={size}:color=white@0.9:t=fill")
        freq = 196 + 24 * (clip.index % 8)
        await arun_ffmpeg([
            "-f", "lavfi", "-i", f"color=c={bg}:s={w}x{h}:d={clip.duration}:r=24",
            "-f", "lavfi", "-i", f"sine=frequency={freq}:sample_rate=48000:duration={clip.duration}",
            "-vf", vf, "-af", "volume=0.25", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "veryfast",
            "-c:a", "aac", "-b:a", "128k", "-shortest", str(out)])
        txt.unlink(missing_ok=True)
        log(f"mock clip {clip.index + 1}: {w}x{h} {clip.duration:.0f}s written (no API call, $0)")
        lf = await asyncio.to_thread(last_frame, out, out.with_suffix(".last.png"))
        return ClipResult(clip.index, out, clip.duration, 0.0, self.name, last_frame=lf, meta={"placeholder": True})
