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


# ---- final-video quality report ---------------------------------------------------------------------

def _streams(video: Path) -> dict:
    import subprocess

    from ..settings import ffprobe_bin
    p = subprocess.run([ffprobe_bin(), "-v", "error", "-count_packets", "-print_format", "json", "-show_streams", str(video)],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    d = json.loads(p.stdout or "{}")
    out = {}
    for s in d.get("streams", []):
        out[s["codec_type"]] = {"duration": float(s.get("duration") or 0), "packets": int(s.get("nb_read_packets") or 0),
                                "rate": s.get("r_frame_rate"), "sample_rate": s.get("sample_rate")}
    return out


def frame_luma(video: Path) -> list[float]:
    """Mean luma (0-255) of every frame."""
    err = run_ffmpeg(["-i", str(video), "-an", "-vf", "signalstats,metadata=print:key=lavfi.signalstats.YAVG", "-f", "null", "-"],
                     timeout=LONG)
    return [float(x) for x in re.findall(r"lavfi\.signalstats\.YAVG=([\d.]+)", err)]


def black_runs(luma: list[float], fps: float, intentional: list[tuple[float, float]], dark: float = 22.0,
               drop: float = 0.45, min_frames: int = 2) -> list[dict]:
    """Unexpected dark dips: frames under `dark` AND under `drop` x the median of the 2 s around them, outside the
    intentional windows (the opening fade-in, the closing fade-out). A scene that is dark all along is not a
    dip, so legitimately dark scenes are not flagged."""
    out, run = [], []
    half = int(fps)
    for i, y in enumerate(luma):
        t = i / fps
        around = sorted(luma[max(0, i - half):i + half + 1])
        med = around[len(around) // 2]
        bad = y < dark and y < drop * med and not any(a <= t <= b for a, b in intentional)
        if bad:
            run.append(i)
            continue
        if len(run) >= min_frames:
            out.append({"start": round(run[0] / fps, 2), "end": round((run[-1] + 1) / fps, 2), "min_luma": round(min(luma[k] for k in run), 1)})
        run = []
    if len(run) >= min_frames:
        out.append({"start": round(run[0] / fps, 2), "end": round((run[-1] + 1) / fps, 2), "min_luma": round(min(luma[k] for k in run), 1)})
    return out


def final_qa(video: Path, fps: float, clip_starts: list[float], caption_events: list[tuple[float, float, int, int]],
             fade: float = 0.6) -> dict:
    """Checks on the exported file: frame count vs duration, audio vs video length, unexpected black dips,
    caption gaps/overlaps. Returns the report with a list of human-readable problems."""
    st = _streams(video)
    v, a = st.get("video", {}), st.get("audio", {})
    problems = []
    expected = round(v.get("duration", 0) * fps)
    if v.get("packets") and abs(v["packets"] - expected) > 1:
        problems.append(f"{v['packets']} video frames for {v['duration']:.2f}s at {fps:g} fps (expected {expected})")
    if a and abs(a.get("duration", 0) - v.get("duration", 0)) > 0.15:
        problems.append(f"audio is {a['duration']:.2f}s but video is {v['duration']:.2f}s")
    if not a:
        problems.append("no audio stream")
    luma = frame_luma(video)
    end = len(luma) / fps if luma else v.get("duration", 0)
    dips = black_runs(luma, fps, [(0, fade), (end - fade, end + 1)])
    for d in dips:
        near = min(clip_starts, key=lambda s: abs(s - d["start"])) if clip_starts else None
        where = f" (at the clip seam {near:.1f}s)" if near is not None and abs(near - d["start"]) < 1.0 and near > 0 else ""
        problems.append(f"near-black frames {d['start']:.2f}-{d['end']:.2f}s{where}")
    overlaps = [(a1, b1) for (a0, b0, _, _), (a1, b1, _, _) in zip(caption_events, caption_events[1:]) if a1 < b0 - 1e-3]
    if overlaps:
        problems.append(f"{len(overlaps)} caption overlap(s), first at {overlaps[0][0]:.2f}s")
    return {"frames": v.get("packets"), "fps": fps, "video_seconds": v.get("duration"), "audio_seconds": a.get("duration"),
            "mean_luma": round(sum(luma) / len(luma), 1) if luma else None, "black_dips": dips,
            "caption_events": len(caption_events), "caption_overlaps": len(overlaps), "problems": problems}


# ---- sound bed (dialogue shorts) ------------------------------------------------------------------

def add_bed(video: Path, out: Path, bed: str = "room", level_db: float = -30.0) -> Path:
    """Mix a quiet bed under the video's voices, ducked while anyone speaks. bed = "room" (generated room tone with
    a faint low pad, nothing to license) or a path to your own music/ambience file (looped)."""
    dur = probe(video)["duration"]
    if bed == "room":
        src = ["-f", "lavfi", "-i", f"anoisesrc=color=brown:amplitude=0.6:sample_rate=48000:duration={dur:.3f}",
               "-f", "lavfi", "-i", f"sine=frequency=110:sample_rate=48000:duration={dur:.3f}",
               "-f", "lavfi", "-i", f"sine=frequency=164.81:sample_rate=48000:duration={dur:.3f}"]
        make = ("[1:a]lowpass=f=300,highpass=f=45[n];[2:a]volume=0.18,tremolo=f=0.17:d=0.5[p1];"
                "[3:a]volume=0.12,tremolo=f=0.11:d=0.5[p2];[n][p1][p2]amix=inputs=3,volume=3,lowpass=f=900[bedsrc];")
    else:
        if not Path(bed).exists():
            raise FileNotFoundError(f"sound bed file not found: {bed}")
        src = ["-stream_loop", "-1", "-i", str(bed)]
        make = "[1:a]anull[bedsrc];"
    graph = (make + f"[bedsrc]aresample=48000,aformat=channel_layouts=stereo,volume={level_db}dB,"
             f"afade=t=in:d=0.6,afade=t=out:st={max(0.0, dur - 0.8):.3f}:d=0.8[bed];"
             "[0:a]aresample=48000,aformat=channel_layouts=stereo,asplit=2[v1][v2];"
             "[bed][v2]sidechaincompress=threshold=0.02:ratio=6:attack=20:release=450[duck];")
    # amix scales each input by 1/n; the volume after it restores the levels (works on every ffmpeg version)
    run_ffmpeg(["-i", str(video), *src, "-filter_complex", graph + "[v1][duck]amix=inputs=2:duration=first,volume=2[a]",
                "-map", "0:v", "-map", "[a]", "-t", f"{dur:.3f}", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", str(out)], timeout=LONG)
    return out
