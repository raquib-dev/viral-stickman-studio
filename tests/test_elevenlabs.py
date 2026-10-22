"""ElevenLabs voiceover: request shape, MP3 -> WAV, retries, clear errors, local fallback, key never logged."""
import json
import subprocess
import wave

import httpx
import pytest

from backend.app import settings as S
from backend.app.render import tts

KEY = "sk_test_eleven_0123456789"


@pytest.fixture
def key(monkeypatch):
    monkeypatch.setattr(S, "_env_cache", {"ELEVENLABS_API_KEY": KEY})


@pytest.fixture(scope="module")
def mp3(tmp_path_factory):
    out = tmp_path_factory.mktemp("el") / "tone.mp3"
    subprocess.run([S.ffmpeg_bin(), "-y", "-loglevel", "error", "-f", "lavfi", "-i", "sine=frequency=220:duration=1.5",
                    "-c:a", "libmp3lame", str(out)], check=True)
    return out.read_bytes()


def _voice(**kw):
    return {"voice": {**S.DEFAULTS["voice"], "tts": "elevenlabs", **kw}}


def test_elevenlabs_writes_a_wav_and_never_logs_the_key(key, mp3, tmp_path, monkeypatch):
    seen = []

    def handler(req: httpx.Request):
        seen.append(req)
        return httpx.Response(429) if len(seen) == 1 else httpx.Response(200, content=mp3)
    monkeypatch.setattr("time.sleep", lambda s: None)
    logs = []
    out = tts.elevenlabs_say("Hello there.", tmp_path / "vo.wav", _voice()["voice"], "female",
                             lambda m, lvl="info": logs.append(m), transport=httpx.MockTransport(handler))
    with wave.open(str(out)) as w:
        assert w.getsampwidth() == 2 and w.getnchannels() == 1 and w.getnframes() / w.getframerate() > 1.2
    r = seen[-1]
    assert len(seen) == 2 and r.url.path == "/v1/text-to-speech/21m00Tcm4TlvDq8ikWAM"   # female default (Rachel)
    assert r.headers["xi-api-key"] == KEY and r.url.params["output_format"] == "mp3_44100_128"
    body = json.loads(r.content)
    assert body["text"] == "Hello there." and body["model_id"] == "eleven_multilingual_v2"
    assert "12 characters" in " ".join(logs) and KEY not in " ".join(logs)
    assert not list(tmp_path.glob("*.mp3"))


def test_elevenlabs_errors_are_clear(key, tmp_path):
    t = httpx.MockTransport(lambda req: httpx.Response(401, json={"detail": {"status": "invalid_api_key"}}))
    with pytest.raises(tts.TTSUnavailable, match="401: the API key is wrong"):
        tts.elevenlabs_say("Hi.", tmp_path / "a.wav", _voice()["voice"], transport=t)


def test_synth_falls_back_to_local_when_elevenlabs_fails(key, tmp_path, monkeypatch):
    def boom(*a, **k):
        raise tts.TTSUnavailable("ElevenLabs HTTP 402: out of credits")
    monkeypatch.setattr(tts, "elevenlabs_say", boom)
    monkeypatch.setattr(tts, "available", lambda: {"elevenlabs": True, "kokoro": True, "piper": False})
    monkeypatch.setattr(tts, "kokoro_say", lambda text, out, voice: out)
    logs = []
    got = tts.synth("Hi.", tmp_path / "b.wav", _voice(), "male", lambda m, lvl="info": logs.append((lvl, m)))
    assert got == tmp_path / "b.wav"
    assert any(lvl == "warn" and "trying the local voice" in m for lvl, m in logs)


def test_auto_never_uses_elevenlabs(key, tmp_path, monkeypatch):
    monkeypatch.setattr(tts, "elevenlabs_say", lambda *a, **k: pytest.fail("auto must stay local/free"))
    monkeypatch.setattr(tts, "available", lambda: {"elevenlabs": True, "kokoro": False, "piper": False})
    assert tts.synth("Hi.", tmp_path / "c.wav", _voice(tts="auto"), "male") is None


def test_settings_accept_elevenlabs_and_hide_the_key(key):
    S.validate_settings(S._deep_merge(S.load_settings(), _voice()))
    pub = S.public_settings()
    assert pub["keys"]["elevenlabs_api_key"] is True and KEY not in json.dumps(pub)
    assert KEY not in S.redact(f"oops {KEY}")
