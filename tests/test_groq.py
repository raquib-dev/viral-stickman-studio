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
