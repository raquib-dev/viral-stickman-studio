"""Local LLM agent: any OpenAI-compatible chat server on this machine (Ollama, LM Studio, llama.cpp server).

A local model cannot run the Agent SDK's tools, so the skill text the task names is put into the system
prompt instead, along with the repo files the prompt tells it to read (voice profiles). The pack's Python
tools still run in the stages themselves, exactly as with Claude. The result must match the task's JSON
schema; an invalid result is retried with the validation errors fed back.
"""
from __future__ import annotations

import asyncio
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
    for s in task.skills if int(cfg.get("skill_chars", 14000)) > 0 else []:      # 0: no skill text at all
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
    cfg_key = "local"       # settings["agent"][cfg_key]
    label = "local LLM"
    cost_note = "$0"
    native_ollama = True    # probe for Ollama's native API

    def __init__(self, settings: dict, transport: httpx.AsyncBaseTransport | None = None):
        self.settings = settings
        self.cfg = settings["agent"][self.cfg_key]
        self._transport = transport  # tests inject a fake server

    def _headers(self) -> dict:
        return {}

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(base_url=self.cfg["base_url"].rstrip("/"), timeout=float(self.cfg.get("timeout_s", 900)),
                                 transport=self._transport, headers=self._headers())

    def _not_found(self) -> str:
        return f"model {self.cfg['model']!r} not found on the local server (Ollama: `ollama pull {self.cfg['model']}`)"

    def _unreachable(self, e: Exception) -> str:
        return (f"cannot reach the local LLM at {self.cfg['base_url']} ({type(e).__name__}). "
                "Start Ollama / LM Studio, or check the URL in Settings → Writing model.")

    async def _is_ollama(self, http: httpx.AsyncClient) -> str | None:
        """Ollama's version when the server is Ollama. Its native API takes the context size per call; the
        OpenAI-compatible one silently cuts long prompts at the server default."""
        try:
            r = await http.get(ollama_root(self.cfg["base_url"]) + "/api/version", timeout=5)
            return r.json().get("version") if r.status_code == 200 else None
        except Exception:
            return None

    async def _ollama_chat(self, http: httpx.AsyncClient, task: AgentTask, messages: list[dict], ctx) -> tuple[str, dict]:
        num_ctx = int(self.cfg.get("num_ctx", 8192))
        body = {"model": self.cfg["model"], "messages": messages, "stream": False, "format": task.schema,
                "think": bool(self.cfg.get("think", False)), "keep_alive": self.cfg.get("keep_alive", "5m"),
                "options": {"temperature": float(self.cfg.get("temperature", 0.4)), "num_ctx": num_ctx,
                            "num_predict": int(self.cfg.get("max_tokens", 8192))}}
        try:
            r = await http.post(ollama_root(self.cfg["base_url"]) + "/api/chat", json=body)
        except httpx.HTTPError as e:
            raise AgentError(f"cannot reach Ollama at {self.cfg['base_url']} ({type(e).__name__}). Is it running?") from e
        if r.status_code == 404:
            raise AgentError(f"model {self.cfg['model']!r} is not pulled in Ollama: run `ollama pull {self.cfg['model']}`")
        if r.status_code >= 400:
            raise _Retry(f"Ollama HTTP {r.status_code}: {r.text[:300]}")
        d = r.json()
        used_in, used_out = d.get("prompt_eval_count") or 0, d.get("eval_count") or 0
        if used_in + used_out >= num_ctx - 16:
            ctx.log(f"agent[{task.name}] the prompt + reply filled the {num_ctx}-token context, so part of it was cut. "
                    "Raise Settings → Writing model → Context tokens (16384 fits an 8B model on 8 GB).", "warn")
        if d.get("done_reason") == "length":
            ctx.log(f"agent[{task.name}] the reply hit Max output tokens and was cut off", "warn")
        return (d.get("message") or {}).get("content") or "", {"prompt_tokens": used_in, "completion_tokens": used_out}

    async def run(self, task: AgentTask, ctx) -> dict:
        attempts = int(self.settings["agent"].get("max_attempts", 3))
        messages = build_messages(task, self.cfg)
        max_out = int(self.cfg.get("max_tokens", 8192))
        fmt: dict | None = {"type": "json_schema", "json_schema": {"name": task.name, "schema": task.schema}}
        last: Exception | None = None
        async with self._client() as http:
            native = await self._is_ollama(http) if self.native_ollama else None
            if native:
                ctx.log(f"agent[{task.name}] Ollama {native}: native API, context {int(self.cfg.get('num_ctx', 8192))} tokens")
            for attempt in range(1, attempts + 1):
                ctx.check_cancelled()
                ctx.log(f"agent[{task.name}] {self.label} model={self.cfg['model']} attempt {attempt}/{attempts}")
                if native:
                    t0 = time.time()
                    try:
                        text, usage = await self._ollama_chat(http, task, messages, ctx)
                    except _Retry as e:
                        last = AgentError(str(e))
                        ctx.log(f"agent[{task.name}] {e}", "warn")
                        continue
                    ctx.log(f"agent[{task.name}] reply in {time.time() - t0:.1f}s, {usage['prompt_tokens']} in / "
                            f"{usage['completion_tokens']} out tokens, $0", "agent")
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
                        continue
                body = {"model": self.cfg["model"], "messages": messages, "temperature": float(self.cfg.get("temperature", 0.4)),
                        "max_tokens": max_out, "stream": False}
                if fmt:
                    body["response_format"] = fmt
                t0 = time.time()
                try:
                    r = await http.post("/chat/completions", json=body)
                except httpx.HTTPError as e:
                    raise AgentError(self._unreachable(e)) from e
                if r.status_code == 400 and fmt and fmt["type"] == "json_schema":
                    # older servers (and models without structured outputs) reject json_schema: plain JSON mode
                    ctx.log(f"{self.label} rejected json_schema output; falling back to JSON mode", "warn")
                    fmt = {"type": "json_object"}
                    r = await http.post("/chat/completions", json={**body, "response_format": fmt})
                waits = 0
                while r.status_code == 429 and waits < 3:
                    # rate limited (hosted APIs): wait as told, without spending an attempt
                    wait = min(60.0, float(r.headers.get("retry-after") or 10 * (waits + 1)))
                    ctx.log(f"agent[{task.name}] {self.label} rate limit; waiting {wait:.0f}s", "warn")
                    await asyncio.sleep(wait)
                    ctx.check_cancelled()
                    waits += 1
                    r = await http.post("/chat/completions", json={**body, **({"response_format": fmt} if fmt else {})})
                if r.status_code in (401, 403):
                    raise AgentError(f"{self.label} HTTP {r.status_code}: the API key was refused ({r.text[:200]})")
                if r.status_code == 404:
                    raise AgentError(self._not_found())
                shrinks = 0
                while r.status_code == 413 and shrinks < 2:
                    # too large for the plan's per-minute token limit (Groq counts the prompt plus the reply it may
                    # write): first lower the reply allowance to fit, then leave out the skill text
                    shrinks += 1
                    lim = _token_limit(r.text)
                    over = lim[1] - lim[0] if lim else 0
                    if shrinks == 1 and lim and max_out - over - 256 >= MIN_REPLY_TOKENS:
                        max_out = max_out - over - 256
                        ctx.log(f"agent[{task.name}] {self.label}: request too large for the plan's limit ({lim[1]} > {lim[0]} "
                                f"tokens); retrying with a reply allowance of {max_out} tokens", "warn")
                    else:
                        messages = build_messages(task, {**self.cfg, "skill_chars": 0})
                        if lim:                    # the smaller prompt, estimated generously (3.5 characters a token)
                            prompt_est = int(sum(len(m["content"]) for m in messages) / 3.5)
                            max_out = max(MIN_REPLY_TOKENS, min(max_out, lim[0] - prompt_est - 256))
                        ctx.log(f"agent[{task.name}] {self.label}: still too large; retrying without the skill text "
                                f"(the task's own rules stay), reply allowance {max_out} tokens", "warn")
                    body = {**body, "messages": messages, "max_tokens": max_out}
                    r = await http.post("/chat/completions", json={**body, **({"response_format": fmt} if fmt else {})})
                if r.status_code == 413:
                    lim = _token_limit(r.text)
                    sizes = f" (the limit is {lim[0]} tokens per minute, this request needs {lim[1]})" if lim else ""
                    raise AgentError(f"{self.label} HTTP 413: the request is larger than this model/plan allows{sizes}. "
                                     "Lower Max output tokens or Skill text per prompt in Settings → Writing model, or pick a "
                                     "model with a higher tokens-per-minute limit (console.groq.com/settings/limits).")
                if r.status_code >= 400:
                    last = AgentError(f"{self.label} HTTP {r.status_code}: {r.text[:300]}")
                    ctx.log(f"agent[{task.name}] {last}", "warn")
                    continue
                d = r.json()
                text = (d.get("choices") or [{}])[0].get("message", {}).get("content") or ""
                usage = d.get("usage") or {}
                ctx.log(f"agent[{task.name}] reply in {time.time() - t0:.1f}s, "
                        f"{usage.get('prompt_tokens', '?')} in / {usage.get('completion_tokens', '?')} out tokens, {self.cost_note}", "agent")
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
        raise AgentError(f"{task.name}: {self.label} gave no valid result after {attempts} attempt(s): {last}")


class GroqAgent(LocalAgent):
    """Groq's hosted OpenAI-compatible API (https://api.groq.com/openai/v1). Fast open models; GROQ_API_KEY in .env.
    Groq bills per token on paid plans and rate-limits the free tier; 429s wait and retry without using an attempt."""
    kind = "Groq"
    cfg_key = "groq"
    label = "Groq"
    cost_note = "billed by Groq per token"
    native_ollama = False

    def _headers(self) -> dict:
        from ..settings import secret
        key = secret("GROQ_API_KEY")
        if not key:
            raise AgentError("GROQ_API_KEY is not set in .env (https://console.groq.com/keys)")
        return {"Authorization": f"Bearer {key}"}

    def _not_found(self) -> str:
        return f"Groq has no model {self.cfg['model']!r} (or your key cannot use it): see https://console.groq.com/docs/models"

    def _unreachable(self, e: Exception) -> str:
        return f"cannot reach Groq at {self.cfg['base_url']} ({type(e).__name__}). Check your internet connection."


class _Retry(Exception):
    pass


MIN_REPLY_TOKENS = 2500     # the smallest reply allowance a full script (with a reasoning model's thinking) fits in


def _token_limit(text: str) -> tuple[int, int] | None:
    """(limit, requested) from a "request too large" reply ("... Limit 8000, Requested 14215 ..."), if it says."""
    m = re.search(r"Limit\s+(\d+)\s*,\s*Requested\s+(\d+)", text or "")
    return (int(m.group(1)), int(m.group(2))) if m else None


def ollama_root(base_url: str) -> str:
    u = base_url.rstrip("/")
    return u[:-3] if u.endswith("/v1") else u


async def unload(settings: dict, log) -> None:
    """Free the GPU before a local video render: Ollama keeps a model loaded for minutes after the last
    call, and an 8 GB card cannot hold it and Wan at the same time."""
    cfg = settings["agent"]["local"]
    try:
        async with httpx.AsyncClient(timeout=10) as http:
            r = await http.post(ollama_root(cfg["base_url"]) + "/api/generate", json={"model": cfg["model"], "keep_alive": 0})
            if r.status_code == 200:
                log(f"unloaded {cfg['model']} from Ollama to free GPU memory for the render")
    except Exception:
        pass  # not Ollama, or not running: nothing to free


async def groq_models(cfg: dict, transport=None) -> dict:
    """The models this Groq key can use (GET /models), for Settings → Writing model → Test Groq."""
    from ..settings import secret
    key = secret("GROQ_API_KEY")
    if not key:
        return {"ok": False, "error": "GROQ_API_KEY is not set in .env"}
    try:
        async with httpx.AsyncClient(timeout=15, transport=transport) as http:
            r = await http.get(cfg["base_url"].rstrip("/") + "/models", headers={"Authorization": f"Bearer {key}"})
    except httpx.HTTPError as e:
        return {"ok": False, "error": f"cannot reach Groq ({type(e).__name__})"}
    if r.status_code != 200:
        return {"ok": False, "error": f"Groq HTTP {r.status_code}" + (": the API key was refused" if r.status_code in (401, 403) else "")}
    ids = sorted(m.get("id") for m in r.json().get("data", []) if m.get("active", True))
    return {"ok": True, "models": ids, "model_present": cfg["model"] in ids}


async def status(base_url: str, timeout: float = 4.0) -> dict:
    """Is the local server up, and which models does it have?"""
    try:
        async with httpx.AsyncClient(base_url=base_url.rstrip("/"), timeout=timeout) as http:
            r = await http.get("/models")
            r.raise_for_status()
            return {"ok": True, "models": [m.get("id") for m in r.json().get("data", [])]}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}"}
