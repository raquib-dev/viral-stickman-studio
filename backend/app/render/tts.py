"""Local text-to-speech for the local render backends (generated video from ComfyUI or the stickman
animator has no voice). Engines, best first for "auto":

- Kokoro-82M (`pip install kokoro soundfile`, Apache-2.0 weights): small, natural English, GPU or CPU.
- Piper (`pip install piper-tts` + a .onnx voice, MIT): CPU-only, very fast.
- ElevenLabs (cloud, ELEVENLABS_API_KEY in .env, billed per character by ElevenLabs) and Groq (cloud,
  GROQ_API_KEY, its OpenAI-compatible /audio/speech): chosen explicitly, never by "auto"; if one fails (no key,
  no credits, rate limit, outage) the clip falls back to Kokoro/Piper instead of going silent.

All write a WAV. `fit_to_clip` then muxes it under a clip, speeding speech up a little if it overruns.
"""
from __future__ import annotations

import functools
import re
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


AUDIO_TAG = re.compile(r"\[[^\[\]]{1,40}\]")


def expressive(model: str) -> bool:
    """ElevenLabs models that perform audio tags ([whispers], [sighs]...) written in the text."""
    return str(model or "").startswith(("eleven_v3", "eleven_v4"))


def strip_tags(text: str) -> str:
    return re.sub(r"\s{2,}", " ", AUDIO_TAG.sub("", text or "")).strip()


def voice_for(v: dict, engine: str, pref: str) -> str:
    """The engine's voice for "male", "female" or "mascot" (dialogue shorts); an unset mascot voice uses the male one."""
    return v.get(f"{engine}_voice_{pref}") or v.get(f"{engine}_voice_male") or ""


ELEVEN_URL = "https://api.elevenlabs.io/v1"


def available() -> dict:
    from ..settings import has_secret
    out = {"kokoro": False, "piper": False, "elevenlabs": has_secret("ELEVENLABS_API_KEY"), "groq": has_secret("GROQ_API_KEY")}
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
    voice = voice_for(v, "elevenlabs", voice_pref) or "pNInz6obpgDQGcFmaJgB"
    model = v.get("elevenlabs_model", "eleven_v4")
    settings = {"stability": float(v.get("elevenlabs_stability", 0.5)), "similarity_boost": float(v.get("elevenlabs_similarity", 0.75))}
    if not model.startswith("eleven_v4"):          # Eleven v4 takes only stability and similarity (no style, no boost)
        settings.update({"style": float(v.get("elevenlabs_style", 0.0)), "use_speaker_boost": True})
    if not expressive(model):
        text = strip_tags(text)                    # older models would read "[sighs]" out loud
    body = {"text": text, "model_id": model, "voice_settings": settings}
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


def _chunks(text: str, limit: int) -> list[str]:
    """Split at sentence ends (then commas, then spaces) into pieces of at most `limit` characters."""
    import re
    out, cur = [], ""
    for part in re.split(r"(?<=[.!?])\s+|(?<=,)\s+", text.strip()):
        while len(part) > limit:
            cut = part.rfind(" ", 0, limit)
            cut = cut if cut > 0 else limit
            out.append(part[:cut].strip()); part = part[cut:].strip()
        if cur and len(cur) + 1 + len(part) > limit:
            out.append(cur); cur = part
        else:
            cur = f"{cur} {part}".strip()
    if cur:
        out.append(cur)
    return [c for c in out if c]


def groq_say(text: str, out: Path, v: dict, voice_pref: str = "male", log=None, transport=None, base_url: str | None = None) -> Path:
    """Groq text-to-speech (OpenAI-compatible POST /audio/speech) -> WAV at `out`. Long lines are spoken in
    sentence-sized pieces and joined; 429/5xx are retried after the wait Groq asks for."""
    import time

    import httpx

    from ..settings import load_settings, secret
    from .media import run_ffmpeg
    key = secret("GROQ_API_KEY")
    if not key:
        raise TTSUnavailable("GROQ_API_KEY is not set in .env")
    base = (base_url or load_settings()["agent"]["groq"]["base_url"]).rstrip("/")
    model = v.get("groq_tts_model") or "canopylabs/orpheus-v1-english"
    voice = voice_for(v, "groq", voice_pref) or "troy"
    parts = []
    with httpx.Client(timeout=120, transport=transport) as http:
        for k, piece in enumerate(_chunks(text, int(v.get("groq_tts_chunk_chars", 190)))):
            for attempt in range(4):
                r = http.post(f"{base}/audio/speech", headers={"Authorization": f"Bearer {key}"},
                              json={"model": model, "voice": voice, "input": piece, "response_format": "wav"})
                if r.status_code == 200:
                    break
                if r.status_code in (429, 500, 502, 503, 504) and attempt < 3:
                    wait = min(30.0, float(r.headers.get("retry-after") or 2 * (attempt + 1)))
                    if log:
                        log(f"Groq voice busy (HTTP {r.status_code}); retrying in {wait:.0f}s", "warn")
                    time.sleep(wait)
                    continue
                hint = {401: "the API key was refused", 403: "this key cannot use the model (accept its terms in the Groq console?)",
                        404: f"no model {model!r} or voice {voice!r}", 400: "the request was rejected (model, voice or text)"}.get(r.status_code, "")
                raise TTSUnavailable(f"Groq speech HTTP {r.status_code}{': ' + hint if hint else ''} {r.text[:200]}")
            f = out.with_suffix(f".groq{k}.wav")
            f.write_bytes(r.content)
            parts.append(f)
    if not parts:
        raise TTSUnavailable("Groq returned no audio")
    if len(parts) == 1:
        run_ffmpeg(["-i", str(parts[0]), "-ac", "1", "-c:a", "pcm_s16le", str(out)])
    else:
        listing = out.with_suffix(".groq.txt")
        listing.write_text("".join(f"file '{p.resolve().as_posix()}'\n" for p in parts), encoding="utf-8")
        run_ffmpeg(["-f", "concat", "-safe", "0", "-i", str(listing), "-ac", "1", "-c:a", "pcm_s16le", str(out)])
        listing.unlink(missing_ok=True)
    for p in parts:
        p.unlink(missing_ok=True)
    if log:
        log(f"Groq voice {voice} ({model}): {len(text)} characters in {len(parts)} piece(s) (billed by Groq)")
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
    cloud = engine in ("elevenlabs", "groq")
    order = ["kokoro", "piper"] if engine == "auto" else [engine, "kokoro", "piper"] if cloud else [engine]
    errors = []
    for name in order:
        if not have.get(name):
            errors.append(f"{name} not installed")
            continue
        try:
            if name == "elevenlabs":
                return elevenlabs_say(text, out, v, voice_pref, log)
            # these engines cannot perform audio tags: they get the words only
            if name == "groq":
                return groq_say(strip_tags(text), out, v, voice_pref, log)
            if name == "kokoro":
                voice = voice_for(v, "kokoro", voice_pref) or "am_michael"
                return kokoro_say(strip_tags(text), out, voice)
            return piper_say(strip_tags(text), out, v.get("piper_model", ""))
        except Exception as e:
            errors.append(f"{name}: {type(e).__name__}: {str(e)[:200]}")
            if name in ("elevenlabs", "groq") and log:
                log(f"{'ElevenLabs' if name == 'elevenlabs' else 'Groq voice'} failed ({str(e)[:200]}); trying the local voice instead", "warn")
    if log:
        log("no voiceover: " + "; ".join(errors) + " (pip install kokoro soundfile — see README → Local mode)", "warn")
    return None


def pitch(wav: Path, factor: float) -> Path:
    """Raise (or lower) a voice's pitch by `factor` without changing its speed (sets a mascot voice apart)."""
    if abs(factor - 1.0) < 0.01:
        return wav
    from .media import run_ffmpeg
    with wave.open(str(wav)) as w:
        rate = w.getframerate()
    tmp = wav.with_suffix(".pitch.wav")
    run_ffmpeg(["-i", str(wav), "-af", f"asetrate={rate * factor:.0f},aresample={rate},atempo={1 / factor:.4f}",
                "-c:a", "pcm_s16le", str(tmp)])
    tmp.replace(wav)
    return wav


def assemble(parts: list[Path | None], starts: list[float], tempo: float, out: Path, duration: float, rate: int = 24000) -> Path:
    """One mono voice track `duration` long with each line's audio placed at its start (sped up by `tempo`)."""
    from .media import run_ffmpeg
    buf = bytearray(int(duration * rate) * 2)
    for k, (part, start) in enumerate(zip(parts, starts)):
        if part is None:
            continue
        norm = out.with_suffix(f".n{k:02d}.wav")
        af = [f"atempo={tempo:.4f}"] if tempo > 1.001 else []
        run_ffmpeg(["-i", str(part), *(["-af", ",".join(af)] if af else []), "-ac", "1", "-ar", str(rate), "-c:a", "pcm_s16le", str(norm)])
        with wave.open(str(norm)) as w:
            data = w.readframes(w.getnframes())
        norm.unlink(missing_ok=True)
        at = int(start * rate) * 2
        if at < len(buf):
            chunk = data[: len(buf) - at]
            buf[at:at + len(chunk)] = chunk
    with wave.open(str(out), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(bytes(buf))
    return out


async def mux_exact(video: Path, speech: Path | None, out: Path, duration: float) -> dict:
    """Mux an already-timed voice track under `video` as is (no lead, no speed-up): dialogue clips."""
    if speech is None:
        return await fit_to_clip(video, None, out, duration)
    await arun_ffmpeg(["-i", str(video), "-i", str(speech), "-filter_complex",
                       "[1:a]aresample=48000,aformat=channel_layouts=stereo,apad[a]", "-map", "0:v", "-map", "[a]",
                       "-t", f"{duration:.3f}", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", str(out)])
    return {"speech_seconds": round(probe(speech)["duration"], 2), "tempo": 1.0}


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
