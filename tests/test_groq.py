"""Groq writing model: auth, OpenAI-compatible request, no Ollama probe, 429 waits, json_schema fallback,
clear key errors, hybrid routing, and the key check endpoint. Groq is faked with httpx.MockTransport."""
import json

import httpx
import pytest

from backend.app import settings as S
from backend.app.agent import local as la
from backend.app.agent.runner import AgentError, AgentTask, HybridAgent, SdkAgent, get_agent

KEY = "gsk_test_0123456789abcdef"
SCHEMA = {"type": "object", "properties": {"title": {"type": "string"}}, "required": ["title"]}


class Ctx:
    def __init__(self):
        self.lines = []

    def log(self, text, level="info"):
        self.lines.append((level, text))

    def check_cancelled(self):
        pass


@pytest.fixture
def key(monkeypatch):
    monkeypatch.setattr(S, "_env_cache", {"GROQ_API_KEY": KEY})


async def _no_sleep(s):
    pass


def _settings(provider="groq"):
    s = S.load_settings()
    s["agent"] = {**s["agent"], "provider": provider}
    return s


def _reply(content):
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}],
                                     "usage": {"prompt_tokens": 100, "completion_tokens": 20}})


async def test_groq_request_retries_rate_limit_and_falls_back_to_json_mode(key, monkeypatch):
    monkeypatch.setattr(la.asyncio, "sleep", _no_sleep)
    seen = []

    def handler(req: httpx.Request):
        seen.append(req)
        body = json.loads(req.content)
        if len(seen) == 1:
            return httpx.Response(400, json={"error": {"message": "json_schema not supported for this model"}})
        if len(seen) == 2:
            assert body["response_format"] == {"type": "json_object"}
            return httpx.Response(429, headers={"retry-after": "3"}, json={"error": {"message": "rate limit"}})
        return _reply('{"title": "ok"}')
    ctx = Ctx()
    out = await la.GroqAgent(_settings(), transport=httpx.MockTransport(handler)).run(AgentTask("x", "p", SCHEMA), ctx)
    assert out == {"title": "ok"} and len(seen) == 3
    assert all(r.url.host == "api.groq.com" and r.url.path == "/openai/v1/chat/completions" for r in seen)  # no Ollama probe
    assert seen[0].headers["authorization"] == f"Bearer {KEY}"
    assert json.loads(seen[0].content)["model"] == "openai/gpt-oss-120b"
    text = " ".join(t for _, t in ctx.lines)
    assert "rate limit; waiting 3s" in text and "billed by Groq" in text and KEY not in text


async def test_groq_request_too_large_shrinks_then_explains(key):
    seen = []
    big = 'Request too large for model on tokens per minute (TPM): Limit 8000, Requested 14200, please reduce your message size'

    def handler(req: httpx.Request):
        body = json.loads(req.content)
        seen.append(body)
        if len(seen) <= 2:                  # too large twice, then it fits
            return httpx.Response(413, json={"error": {"message": big, "type": "tokens"}})
        return _reply('{"title": "ok"}')
    ctx = Ctx()
    task = AgentTask("x", "p", SCHEMA, ["ig-reel"])
    out = await la.GroqAgent(_settings(), transport=httpx.MockTransport(handler)).run(task, ctx)
    assert out == {"title": "ok"} and len(seen) == 3
    # 6200 over: a reply allowance of 8192 - 6456 is too small for a script, so the skill text goes instead and the
    # reply allowance is what the limit leaves after the smaller prompt
    assert seen[0]["max_tokens"] == 8192 and la.MIN_REPLY_TOKENS <= seen[1]["max_tokens"] < 8000 - 256
    assert "SKILL `ig-reel`" in seen[0]["messages"][0]["content"] and "SKILL `ig-reel`" not in seen[1]["messages"][0]["content"]
    assert sum(1 for lv, _ in ctx.lines if lv == "warn") == 2
    always = httpx.MockTransport(lambda req: httpx.Response(413, json={"error": {"message": big}}))
    with pytest.raises(AgentError, match="limit is 8000 tokens per minute, this request needs 14200"):
        await la.GroqAgent(_settings(), transport=always).run(task, Ctx())


async def test_groq_bad_key_and_missing_key_are_clear(key, monkeypatch):
    t = httpx.MockTransport(lambda req: httpx.Response(401, json={"error": {"message": "Invalid API Key"}}))
    with pytest.raises(AgentError, match="API key was refused"):
        await la.GroqAgent(_settings(), transport=t).run(AgentTask("x", "p", SCHEMA), Ctx())
    monkeypatch.setattr(S, "_env_cache", {})
    with pytest.raises(AgentError, match="GROQ_API_KEY is not set"):
        await la.GroqAgent(_settings(), transport=t).run(AgentTask("x", "p", SCHEMA), Ctx())


def test_providers_route_to_groq(key):
    assert isinstance(get_agent({**_settings("groq"), "dry_run": False}), la.GroqAgent)
    h = get_agent({**_settings("hybrid-groq"), "dry_run": False})
    assert isinstance(h, HybridAgent) and isinstance(h.local, la.GroqAgent) and isinstance(h.claude, SdkAgent)
    assert "Groq" in h.kind
    plain = get_agent({**_settings("hybrid"), "dry_run": False})
    assert type(plain.local) is la.LocalAgent
    S.validate_settings(_settings("hybrid-groq"))
    pub = S.public_settings()
    assert pub["keys"]["groq_api_key"] is True and KEY not in json.dumps(pub)


async def test_groq_models_check(key):
    def handler(req):
        assert req.url.path == "/openai/v1/models" and req.headers["authorization"] == f"Bearer {KEY}"
        return httpx.Response(200, json={"data": [{"id": "openai/gpt-oss-120b", "active": True}, {"id": "llama-3.3-70b-versatile"}]})
    r = await la.groq_models(S.load_settings()["agent"]["groq"], transport=httpx.MockTransport(handler))
    assert r["ok"] and r["model_present"] and len(r["models"]) == 2


# ---- Groq voice (text-to-speech) and Groq Whisper (caption timing) ----

def _wav_bytes(seconds=0.6):
    import subprocess
    r = subprocess.run([S.ffmpeg_bin(), "-loglevel", "error", "-f", "lavfi", "-i", f"sine=frequency=200:duration={seconds}",
                        "-ar", "24000", "-ac", "1", "-f", "wav", "-"], capture_output=True, check=True)
    return r.stdout


def test_groq_voice_speaks_in_pieces_and_joins_them(key, tmp_path, monkeypatch):
    import wave

    from backend.app.render import tts
    monkeypatch.setattr("time.sleep", lambda s: None)
    seen = []

    def handler(req):
        seen.append(json.loads(req.content))
        if len(seen) == 1:
            return httpx.Response(429, headers={"retry-after": "1"})
        return httpx.Response(200, content=_wav_bytes())
    v = {**S.DEFAULTS["voice"], "tts": "groq", "groq_tts_chunk_chars": 40}
    text = "You don't have a money problem. You have a game on repeat. Friday night, level one."
    logs = []
    out = tts.groq_say(text, tmp_path / "vo.wav", v, "female", lambda m, lvl="info": logs.append(m),
                       transport=httpx.MockTransport(handler), base_url="https://api.groq.com/openai/v1")
    bodies = seen[1:]
    assert len(bodies) >= 3 and all(len(b["input"]) <= 40 for b in bodies)
    assert " ".join(b["input"] for b in bodies) == text                        # nothing lost or reordered
    assert bodies[0]["voice"] == "hannah" and bodies[0]["model"] == "canopylabs/orpheus-v1-english"
    with wave.open(str(out)) as w:
        assert w.getnframes() / w.getframerate() > 0.6 * len(bodies) - 0.1      # pieces joined
    assert not list(tmp_path.glob("*.groq*")) and KEY not in " ".join(logs)


def test_synth_with_groq_falls_back_to_local(key, tmp_path, monkeypatch):
    from backend.app.render import tts

    def boom(*a, **k):
        raise tts.TTSUnavailable("Groq speech HTTP 403: terms not accepted")
    monkeypatch.setattr(tts, "groq_say", boom)
    monkeypatch.setattr(tts, "available", lambda: {"groq": True, "kokoro": True, "piper": False})
    monkeypatch.setattr(tts, "kokoro_say", lambda text, out, voice: out)
    logs = []
    s = {"voice": {**S.DEFAULTS["voice"], "tts": "groq"}}
    assert tts._synth("Hi.", tmp_path / "x.wav", s, "male", lambda m, lvl="info": logs.append((lvl, m))) == tmp_path / "x.wav"
    assert any("Groq voice failed" in m for _, m in logs)


def test_groq_whisper_word_timings(key, tmp_path):
    from backend.app.render import captions as cap
    audio = tmp_path / "a.wav"
    audio.write_bytes(_wav_bytes(1.0))
    seen = {}

    def handler(req):
        seen["path"], seen["auth"], seen["body"] = req.url.path, req.headers["authorization"], req.content
        return httpx.Response(200, json={"text": "you have", "words": [{"word": " You", "start": 0.1, "end": 0.3},
                                                                       {"word": "have", "start": 0.3, "end": 0.6}]})
    words = cap.groq_words(audio, None, transport=httpx.MockTransport(handler), base_url="https://api.groq.com/openai/v1")
    assert [(w.w, w.s, w.e) for w in words] == [("You", 0.1, 0.3), ("have", 0.3, 0.6)]
    assert seen["path"] == "/openai/v1/audio/transcriptions" and seen["auth"] == f"Bearer {KEY}"
    assert b"whisper-large-v3-turbo" in seen["body"] and b"timestamp_granularities[]" in seen["body"]
    bad = cap.groq_words(audio, None, transport=httpx.MockTransport(lambda r: httpx.Response(500)), base_url="https://x/v1")
    assert bad is None and not list(tmp_path.glob("*.mp3"))


def test_settings_accept_groq_everywhere(key):
    s = _settings("groq")
    s["voice"] = {**s["voice"], "tts": "groq"}
    s["captions"] = {**s["captions"], "engine": "groq"}
    S.validate_settings(s)
    s["captions"]["engine"] = "cloud"
    with pytest.raises(ValueError):
        S.validate_settings(s)
