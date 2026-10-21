"""Stitch clips -> one video, burn captions + hook card + callouts (ASS), then a two-pass EBU R128
loudness normalisation (loudnorm) to the configured target (default -16 LUFS, -1 dBTP)."""
from __future__ import annotations

import json
import re
from pathlib import Path

from .media import dims, filter_path, probe, run_ffmpeg

# whole-video passes: a 5-minute 1080p stitch on a laptop CPU can outlast ffmpeg's default 10-minute timeout
LONG = 3600


def wrong_orientation(info: dict, ratio: str) -> bool:
    """True when a clip is landscape in a 9:16 video or portrait in a 16:9 one."""
    w, h = info.get("width") or 0, info.get("height") or 0
    if not w or not h:
        return False
    return (w > h) if ratio == "9:16" else (h > w)


def concat(clips: list[Path], out: Path, ratio: str, resolution: str, fps: int = 24) -> Path:
    w, h = dims(ratio, resolution)
    args: list[str] = []
    for c in clips:
        args += ["-i", str(c)]
    parts, n = [], len(clips)
    silent_inputs = []
    infos = [probe(c) for c in clips]
    for i, info in enumerate(infos):
        # each clip's audio is cut or padded to its own video length, so a clip whose audio runs long
        # (common with generated clips) cannot push every later clip and its captions out of sync
        dur = info["video_duration"] or info["duration"]
        if wrong_orientation(info, ratio):
            # a landscape clip in a vertical video (or the reverse): fill the frame from the centre instead of
            # shrinking it into a small letterboxed strip
            fit = f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h}"
        else:
            fit = f"scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=black"
        parts.append(f"[{i}:v]{fit},fps={fps},setsar=1,format=yuv420p,"
                     f"trim=duration={dur:.3f},setpts=PTS-STARTPTS[v{i}]")
        if info["has_audio"]:
            parts.append(f"[{i}:a]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,"
                         f"apad,atrim=duration={dur:.3f},asetpts=PTS-STARTPTS[a{i}]")
        else:
            silent_inputs.append((i, dur))
    extra = []
    for k, (i, dur) in enumerate(silent_inputs):
        extra += ["-f", "lavfi", "-t", f"{dur:.3f}", "-i", "anullsrc=r=48000:cl=stereo"]
        parts.append(f"[{n + k}:a]aformat=sample_fmts=fltp:channel_layouts=stereo[a{i}]")
    joined = "".join(f"[v{i}][a{i}]" for i in range(n))
    fc = ";".join(parts) + f";{joined}concat=n={n}:v=1:a=1[v][a]"
    run_ffmpeg([*args, *extra, "-filter_complex", fc, "-map", "[v]", "-map", "[a]",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-c:a", "aac", "-b:a", "192k", str(out)], timeout=LONG)
    return out


def burn_ass(video: Path, ass_file: Path, out: Path) -> Path:
    run_ffmpeg(["-i", str(video), "-vf", f"ass='{filter_path(ass_file)}'", "-c:v", "libx264", "-preset", "veryfast",
                "-crf", "20", "-c:a", "copy", str(out)], timeout=LONG)
    return out


_JSON_RE = re.compile(r"\{[^{}]*\"input_i\"[^{}]*\}", re.S)


def measure_loudness(media: Path, target_i: float = -16.0, target_tp: float = -1.0) -> dict:
    err = run_ffmpeg(["-i", str(media), "-af", f"loudnorm=I={target_i}:TP={target_tp}:LRA=11:print_format=json",
                      "-f", "null", "-"], timeout=LONG)
    m = _JSON_RE.search(err)
    if not m:
        raise RuntimeError("loudnorm produced no measurement")
    return json.loads(m.group(0))


def loudnorm(video: Path, out: Path, target_i: float = -16.0, target_tp: float = -1.0) -> dict:
    """Two-pass loudnorm. Returns {before, after} integrated loudness measurements."""
    first = measure_loudness(video, target_i, target_tp)
    before = float(first["input_i"])
    if before < -70:  # silent (-inf) or near-silent: loudnorm rejects the measurement, nothing to normalise
        run_ffmpeg(["-i", str(video), "-c", "copy", str(out)], timeout=LONG)
        return {"target_i": target_i, "target_tp": target_tp, "before_i": None, "after_i": None, "after_tp": None,
                "skipped": "the audio is silent; nothing to normalise"}
    af = (f"loudnorm=I={target_i}:TP={target_tp}:LRA=11:measured_I={first['input_i']}:"
          f"measured_TP={first['input_tp']}:measured_LRA={first['input_lra']}:"
          f"measured_thresh={first['input_thresh']}:offset={first['target_offset']}:linear=true,aresample=48000")
    run_ffmpeg(["-i", str(video), "-af", af, "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", str(out)], timeout=LONG)
    after = measure_loudness(out, target_i, target_tp)
    return {"target_i": target_i, "target_tp": target_tp, "before_i": float(first["input_i"]),
            "after_i": float(after["input_i"]), "after_tp": float(after["input_tp"])}
