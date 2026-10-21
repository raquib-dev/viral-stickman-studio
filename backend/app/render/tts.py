"""Local text-to-speech for the local render backends (generated video from ComfyUI or the stickman
animator has no voice). Engines, best first for "auto":

- Kokoro-82M (`pip install kokoro soundfile`, Apache-2.0 weights): small, natural English, GPU or CPU.
- Piper (`pip install piper-tts` + a .onnx voice, MIT): CPU-only, very fast.

Both write a WAV. `fit_to_clip` then muxes it under a clip, speeding speech up a little if it overruns.
"""
from __future__ import annotations

import functools
import shutil
import subprocess
import sys
import wave
from pathlib import Path

from .media import arun_ffmpeg, probe

KOKORO_RATE = 24000


class TTSUnavailable(RuntimeError):
    pass


def available() -> dict:
    out = {"kokoro": False, "piper": False}
    try:
        import kokoro  # noqa: F401
        out["kokoro"] = True
    except Exception:
        pass
    out["piper"] = bool(shutil.which("piper")) or _module("piper")
    return out


def _module(name: str) -> bool:
    import importlib.util
    return importlib.util.find_spec(name) is not None


@functools.lru_cache(maxsize=2)
def _kokoro_pipeline(lang: str):
    from kokoro import KPipeline
    return KPipeline(lang_code=lang)


def _write_wav(path: Path, samples, rate: int) -> None:
    import numpy as np
    pcm = (np.clip(np.asarray(samples, dtype="float32"), -1.0, 1.0) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm.tobytes())


def kokoro_say(text: str, out: Path, voice: str) -> Path:
    import numpy as np
    pipe = _kokoro_pipeline(voice[0] if voice[:1] in "abefhijpz" else "a")
    chunks = [np.asarray(audio) for _, _, audio in pipe(text, voice=voice)]
    if not chunks:
        raise TTSUnavailable("kokoro produced no audio")
    _write_wav(out, np.concatenate(chunks), KOKORO_RATE)
    return out


def piper_say(text: str, out: Path, model: str) -> Path:
    if not model or not Path(model).exists():
        raise TTSUnavailable("set Settings → Voice → Piper voice model to a downloaded .onnx file")
    exe = shutil.which("piper")
    cmd = [exe] if exe else [sys.executable, "-m", "piper"]
    p = subprocess.run([*cmd, "--model", model, "--output_file", str(out)], input=text, capture_output=True,
                       text=True, encoding="utf-8", timeout=300)
    if p.returncode != 0 or not out.exists():
        raise TTSUnavailable(f"piper failed: {p.stderr.strip()[-300:]}")
    return out


def synth(text: str, out: Path, settings: dict, voice_pref: str = "male", log=None) -> Path | None:
    """Speak `text` into `out` (WAV). Returns None when TTS is off or no engine is installed."""
    v = settings.get("voice", {})
    engine = v.get("tts", "auto")
    if engine == "none" or not text.strip():
        return None
    have = available()
    order = ["kokoro", "piper"] if engine == "auto" else [engine]
    errors = []
    for name in order:
        if not have.get(name):
            errors.append(f"{name} not installed")
            continue
        try:
            if name == "kokoro":
                voice = v.get("kokoro_voice_female" if voice_pref == "female" else "kokoro_voice_male", "am_michael")
                return kokoro_say(text, out, voice)
            return piper_say(text, out, v.get("piper_model", ""))
        except Exception as e:
            errors.append(f"{name}: {type(e).__name__}: {str(e)[:160]}")
    if log:
        log("no voiceover: " + "; ".join(errors) + " (pip install kokoro soundfile — see README → Local mode)", "warn")
    return None


async def fit_to_clip(video: Path, speech: Path | None, out: Path, duration: float, max_speedup: float = 1.3,
                      lead: float = 0.4) -> dict:
    """Mux speech under `video`, exactly `duration` long. Speech that overruns is sped up (up to
    max_speedup) and then cut; the clip always gets a 48 kHz stereo track so stitch sees real audio."""
    if speech is None:
        await arun_ffmpeg(["-i", str(video), "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-t", f"{duration:.3f}",
                           "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-shortest", str(out)])
        return {"speech_seconds": 0.0, "tempo": 1.0}
    said = probe(speech)["duration"]
    room = max(1.0, duration - lead - 0.3)
    tempo = min(max_speedup, max(1.0, said / room))
    af = (f"atempo={tempo:.3f}," if tempo > 1.0 else "") + \
         f"adelay={int(lead * 1000)}|{int(lead * 1000)},aresample=48000,aformat=channel_layouts=stereo,apad"
    await arun_ffmpeg(["-i", str(video), "-i", str(speech), "-filter_complex", f"[1:a]{af}[a]", "-map", "0:v", "-map", "[a]",
                       "-t", f"{duration:.3f}", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", str(out)])
    return {"speech_seconds": round(said, 2), "tempo": round(tempo, 3), "cut": said / tempo > room + 0.05}
