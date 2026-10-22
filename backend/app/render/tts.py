"""Local text-to-speech for the local render backends (generated video from ComfyUI or the stickman
animator has no voice). Engines, best first for "auto":

- Kokoro-82M (`pip install kokoro soundfile`, Apache-2.0 weights): small, natural English, GPU or CPU.
- Piper (`pip install piper-tts` + a .onnx voice, MIT): CPU-only, very fast.
- ElevenLabs (cloud, ELEVENLABS_API_KEY in .env, billed per character by ElevenLabs): chosen explicitly, never
  by "auto"; if it fails (no key, no credits, outage) the clip falls back to Kokoro/Piper instead of going silent.

All write a WAV. `fit_to_clip` then muxes it under a clip, speeding speech up a little if it overruns.
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
VO_LEAD = 0.25   # seconds of quiet before the narrator starts inside a clip (after trimming the engine's own silence)


class TTSUnavailable(RuntimeError):
    pass


ELEVEN_URL = "https://api.elevenlabs.io/v1"


def available() -> dict:
    from ..settings import has_secret
    out = {"kokoro": False, "piper": False, "elevenlabs": has_secret("ELEVENLABS_API_KEY")}
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


def elevenlabs_say(text: str, out: Path, v: dict, voice_pref: str = "male", log=None, transport=None) -> Path:
    """ElevenLabs text-to-speech -> MP3 -> WAV at `out`. Retries busy/5xx twice; clear errors otherwise."""
    import time

    import httpx

    from ..settings import secret
    from .media import run_ffmpeg
    key = secret("ELEVENLABS_API_KEY")
    if not key:
        raise TTSUnavailable("ELEVENLABS_API_KEY is not set in .env")
    voice = v.get("elevenlabs_voice_female" if voice_pref == "female" else "elevenlabs_voice_male") or "pNInz6obpgDQGcFmaJgB"
    body = {"text": text, "model_id": v.get("elevenlabs_model", "eleven_multilingual_v2"),
            "voice_settings": {"stability": float(v.get("elevenlabs_stability", 0.5)),
                               "similarity_boost": float(v.get("elevenlabs_similarity", 0.75)),
                               "style": float(v.get("elevenlabs_style", 0.0)), "use_speaker_boost": True}}
    mp3 = out.with_suffix(".eleven.mp3")
    with httpx.Client(timeout=120, transport=transport) as http:
        for attempt in range(3):
            r = http.post(f"{ELEVEN_URL}/text-to-speech/{voice}", params={"output_format": "mp3_44100_128"},
                          headers={"xi-api-key": key, "accept": "audio/mpeg"}, json=body)
            if r.status_code == 200:
                break
            if r.status_code in (429, 500, 502, 503, 504) and attempt < 2:
                if log:
                    log(f"ElevenLabs busy (HTTP {r.status_code}); retrying", "warn")
                time.sleep(2 * (attempt + 1))
                continue
            detail = r.text[:200]
            hint = {401: "the API key is wrong", 402: "out of credits or the plan does not include this", 404: f"voice {voice!r} not found in your account",
                    422: "the request was rejected (model or settings)"}.get(r.status_code, "")
            raise TTSUnavailable(f"ElevenLabs HTTP {r.status_code}{': ' + hint if hint else ''} {detail}")
    mp3.write_bytes(r.content)
    run_ffmpeg(["-i", str(mp3), "-ac", "1", "-ar", "44100", str(out)])
    mp3.unlink(missing_ok=True)
    if log:
        log(f"ElevenLabs voice {voice}: {len(text)} characters (billed to your ElevenLabs account)")
    return out


def elevenlabs_voices(transport=None) -> list[dict]:
    """The voices in the user's ElevenLabs account, for the Settings picker."""
    import httpx

    from ..settings import secret
    key = secret("ELEVENLABS_API_KEY")
    if not key:
        return []
    with httpx.Client(timeout=20, transport=transport) as http:
        r = http.get(f"{ELEVEN_URL}/voices", headers={"xi-api-key": key})
        r.raise_for_status()
        return [{"id": x.get("voice_id"), "name": x.get("name"), "labels": x.get("labels") or {}, "category": x.get("category")}
                for x in r.json().get("voices", [])]


def trim_silence(wav: Path, threshold_db: float = -45.0) -> Path:
    """Cut the quiet the engines put before and after the speech (Kokoro adds ~0.2-0.4 s each side), so the
    clip's own lead decides when the voice starts and seams do not collect seconds of dead air."""
    from .media import run_ffmpeg
    tmp = wav.with_suffix(".trim.wav")
    try:
        sr = f"silenceremove=start_periods=1:start_threshold={threshold_db}dB:start_silence=0.05"
        run_ffmpeg(["-i", str(wav), "-af", f"{sr},areverse,{sr},areverse", "-c:a", "pcm_s16le", str(tmp)])
        if probe(tmp)["duration"] > 0.3:
            tmp.replace(wav)
    except Exception:
        pass
    tmp.unlink(missing_ok=True)
    return wav


def synth(text: str, out: Path, settings: dict, voice_pref: str = "male", log=None) -> Path | None:
    """Speak `text` into `out` (WAV, leading/trailing silence trimmed). None when TTS is off or no engine works."""
    wav = _synth(text, out, settings, voice_pref, log)
    return trim_silence(wav) if wav else None


def _synth(text: str, out: Path, settings: dict, voice_pref: str = "male", log=None) -> Path | None:
    v = settings.get("voice", {})
    engine = v.get("tts", "auto")
    if engine == "none" or not text.strip():
        return None
    have = available()
    # ElevenLabs falls back to the local engines so a missing key or empty credits never means a silent clip
    order = ["kokoro", "piper"] if engine == "auto" else ["elevenlabs", "kokoro", "piper"] if engine == "elevenlabs" else [engine]
    errors = []
    for name in order:
        if not have.get(name):
            errors.append(f"{name} not installed")
            continue
        try:
            if name == "elevenlabs":
                return elevenlabs_say(text, out, v, voice_pref, log)
            if name == "kokoro":
                voice = v.get("kokoro_voice_female" if voice_pref == "female" else "kokoro_voice_male", "am_michael")
                return kokoro_say(text, out, voice)
            return piper_say(text, out, v.get("piper_model", ""))
        except Exception as e:
            errors.append(f"{name}: {type(e).__name__}: {str(e)[:200]}")
            if name == "elevenlabs" and log:
                log(f"ElevenLabs failed ({str(e)[:200]}); trying the local voice instead", "warn")
    if log:
        log("no voiceover: " + "; ".join(errors) + " (pip install kokoro soundfile — see README → Local mode)", "warn")
    return None


async def fit_to_clip(video: Path, speech: Path | None, out: Path, duration: float, max_speedup: float = 1.3,
                      lead: float = VO_LEAD) -> dict:
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
    # where the voice really is inside the clip: captions are timed from this when faster-whisper is not installed
    window = [round(lead, 3), round(min(duration, lead + said / tempo), 3)]
    return {"speech_seconds": round(said, 2), "tempo": round(tempo, 3), "cut": said / tempo > room + 0.05, "speech_window": window}
