"""Stitch on clips shaped like real renders: silent audio, audio longer than the video, odd lengths,
and a faster-whisper that fails. None of these may fail the stitch."""
import sys
import types

from backend.app.render import captions as cap
from backend.app.render import stitch as st
from backend.app.render.media import probe, run_ffmpeg


def _clip(path, seconds, audio):
    a = {"silent": ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-t", str(seconds)],
         "long": ["-f", "lavfi", "-i", f"sine=frequency=300:sample_rate=24000:duration={seconds + 0.4}", "-ac", "1"],
         "none": []}[audio]
    run_ffmpeg(["-f", "lavfi", "-i", f"testsrc2=s=360x640:r=30:d={seconds}", *a, "-c:v", "libx264",
                "-pix_fmt", "yuv420p", *(["-c:a", "aac"] if a else []), str(path)])
    return path


def test_concat_keeps_each_clip_at_its_video_length(tmp_path):
    clips = [_clip(tmp_path / "a.mp4", 3.0, "long"), _clip(tmp_path / "b.mp4", 2.0, "none"),
             _clip(tmp_path / "c.mp4", 2.5, "long")]
    out = st.concat(clips, tmp_path / "out.mp4", "9:16", "360p")
    assert abs(probe(out)["duration"] - 7.5) < 0.15


def test_loudnorm_skips_silent_audio(tmp_path):
    clip = _clip(tmp_path / "s.mp4", 2.0, "silent")
    rep = st.loudnorm(clip, tmp_path / "n.mp4")
    assert rep["after_i"] is None and rep["skipped"] and (tmp_path / "n.mp4").exists()


def test_whisper_failure_falls_back(monkeypatch, tmp_path):
    class Boom:
        def __init__(self, *a, **k):
            raise OSError("model download failed")
    monkeypatch.setitem(sys.modules, "faster_whisper", types.SimpleNamespace(WhisperModel=Boom))
    logged = []
    assert cap.whisper_words(tmp_path / "x.mp4", lambda m, lvl="info": logged.append(m)) is None
    assert any("model download failed" in m for m in logged)


def test_estimate_uses_real_clip_lengths():
    words = cap.estimate_words(["one two", "three four"], durations=[8.0, 10.0])
    assert words[2].s >= 8.0 and words[-1].e <= 18.0


def test_landscape_clip_fills_vertical_frame(tmp_path):
    land = tmp_path / "land.mp4"
    run_ffmpeg(["-f", "lavfi", "-i", "color=c=white:s=640x360:r=24:d=1", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(land)])
    assert st.wrong_orientation(probe(land), "9:16") and not st.wrong_orientation(probe(land), "16:9")
    out = st.concat([land], tmp_path / "out.mp4", "9:16", "360p")
    frame = tmp_path / "f.png"
    run_ffmpeg(["-ss", "0.5", "-i", str(out), "-frames:v", "1", "-vf", "crop=360:40:0:0,scale=1:1", "-f", "rawvideo",
                "-pix_fmt", "gray", str(frame)])
    assert frame.read_bytes()[0] > 200  # top edge is picture, not a black letterbox bar
