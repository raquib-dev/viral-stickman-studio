"""Local LLM agent: any OpenAI-compatible chat server on this machine (Ollama, LM Studio, llama.cpp server).

A local model cannot run the Agent SDK's tools, so the skill text the task names is put into the system
prompt instead, along with the repo files the prompt tells it to read (voice profiles). The pack's Python
tools still run in the stages themselves, exactly as with Claude. The result must match the task's JSON
schema; an invalid result is retried with the validation errors fed back.
"""
from __future__ import annotations

import json
import re
import time
from typing import Any

import httpx

from ..paths import REPO_ROOT, SKILLS
from .runner import SYSTEM_APPEND, AgentError, AgentTask, _validate

_THINK = re.compile(r"<think>.*?</think>", re.S)
_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.S)
_FILE_REF = re.compile(r"\b(config/voice/[\w.-]+\.md)\b")


def skill_text(name: str, limit: int) -> str:
    f = SKILLS / name / "SKILL.md"
    if not f.exists():
        return ""
    t = f.read_text(encoding="utf-8")
    return t if len(t) <= limit else t[:limit] + "\n[... skill text truncated to fit the local model ...]"


def extract_json(text: str) -> Any:
    """Parse a model reply that may carry <think> blocks, code fences or prose around the JSON."""
    text = _THINK.sub("", text or "").strip()
    for candidate in [text, *(m.group(1).strip() for m in _FENCE.finditer(text))]:
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass
    start = min([i for i in (text.find("{"), text.find("[")) if i >= 0], default=-1)
    if start >= 0:
        end = max(text.rfind("}"), text.rfind("]"))
        if end > start:
            try:
                return json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                pass
    raise AgentError("the reply is not valid JSON")


def build_messages(task: AgentTask, cfg: dict) -> list[dict]:
    parts = [SYSTEM_APPEND, "You cannot run tools or read files: everything you need is below. "
             "Reply with ONE JSON value that matches the schema, and nothing else."]
    for s in task.skills:
        body = skill_text(s, int(cfg.get("skill_chars", 14000)))
        if body:
            parts.append(f"=== SKILL `{s}` (follow it) ===\n{body}")
    for rel in sorted(set(_FILE_REF.findall(task.prompt))):
        f = REPO_ROOT / rel
        if f.exists():
            parts.append(f"=== FILE {rel} ===\n{f.read_text(encoding='utf-8')[:6000]}")
    user = f"{task.prompt}\n\nJSON SCHEMA OF THE RESULT:\n{json.dumps(task.schema)}"
    return [{"role": "system", "content": "\n\n".join(parts)}, {"role": "user", "content": user}]


class LocalAgent:
    kind = "local LLM"

    def __init__(self, settings: dict, transport: httpx.AsyncBaseTransport | None = None):
        self.settings = settings
        self.cfg = settings["agent"]["local"]
        self._transport = transport  # tests inject a fake server

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(base_url=self.cfg["base_url"].rstrip("/"), timeout=float(self.cfg.get("timeout_s", 900)),
                                 transport=self._transport)

    async def run(self, task: AgentTask, ctx) -> dict:
        attempts = int(self.settings["agent"].get("max_attempts", 3))
        messages = build_messages(task, self.cfg)
        fmt: dict | None = {"type": "json_schema", "json_schema": {"name": task.name, "schema": task.schema}}
        last: Exception | None = None
        async with self._client() as http:
            for attempt in range(1, attempts + 1):
                ctx.check_cancelled()
                ctx.log(f"agent[{task.name}] local model={self.cfg['model']} attempt {attempt}/{attempts}")
                body = {"model": self.cfg["model"], "messages": messages, "temperature": float(self.cfg.get("temperature", 0.4)),
                        "max_tokens": int(self.cfg.get("max_tokens", 8192)), "stream": False}
                if fmt:
                    body["response_format"] = fmt
                t0 = time.time()
                try:
                    r = await http.post("/chat/completions", json=body)
                except httpx.HTTPError as e:
                    raise AgentError(f"cannot reach the local LLM at {self.cfg['base_url']} ({type(e).__name__}). "
                                     "Start Ollama / LM Studio, or check the URL in Settings → Writing model.") from e
                if r.status_code == 400 and fmt and fmt["type"] == "json_schema":
                    # older servers reject json_schema; fall back to plain JSON mode and keep the attempt
                    ctx.log("local server rejected json_schema output; falling back to JSON mode", "warn")
                    fmt = {"type": "json_object"}
                    r = await http.post("/chat/completions", json={**body, "response_format": fmt})
                if r.status_code == 404:
                    raise AgentError(f"model {self.cfg['model']!r} not found on the local server "
                                     f"(Ollama: `ollama pull {self.cfg['model']}`)")
                if r.status_code >= 400:
                    last = AgentError(f"local LLM HTTP {r.status_code}: {r.text[:300]}")
                    ctx.log(f"agent[{task.name}] {last}", "warn")
                    continue
                d = r.json()
                text = (d.get("choices") or [{}])[0].get("message", {}).get("content") or ""
                usage = d.get("usage") or {}
                ctx.log(f"agent[{task.name}] reply in {time.time() - t0:.1f}s, "
                        f"{usage.get('prompt_tokens', '?')} in / {usage.get('completion_tokens', '?')} out tokens, $0", "agent")
                try:
                    data = extract_json(text)
                    _validate(task, data)
                    return data
                except AgentError as e:
                    last = e
                    ctx.log(f"agent[{task.name}] attempt {attempt} invalid: {str(e)[:300]}", "warn")
                    messages = [*messages, {"role": "assistant", "content": text[:4000]},
                                {"role": "user", "content": f"That result was invalid: {e}. Reply again with ONLY the "
                                                            "corrected JSON that matches the schema exactly."}]
        raise AgentError(f"{task.name}: local model gave no valid result after {attempts} attempt(s): {last}")


async def status(base_url: str, timeout: float = 4.0) -> dict:
    """Is the local server up, and which models does it have?"""
    try:
        async with httpx.AsyncClient(base_url=base_url.rstrip("/"), timeout=timeout) as http:
            r = await http.get("/models")
            r.raise_for_status()
            return {"ok": True, "models": [m.get("id") for m in r.json().get("data", [])]}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}"}
