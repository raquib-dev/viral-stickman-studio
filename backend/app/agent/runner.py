"""Agent runner: executes a task through the Claude Agent SDK so the REAL vendored skills run.

- setting_sources=["user", "project"]: loads .claude/skills (vendored) and CLAUDE.md, plus your own
  ~/.claude/skills if present.
- skills=[...]: only the skills the stage needs.
- permission_mode="dontAsk" with a read-only allow-list: the agent may read files and run the packs'
  Python tools; it cannot write files, post, or fetch. Results come back as structured JSON
  (output_format) and are validated before any stage uses them.
- FixtureAgent: same interface for dry runs; deterministic, clearly labelled fixture outputs.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from jsonschema import Draft202012Validator

from ..paths import REPO_ROOT
from ..settings import has_secret, redact, secret

READ_ONLY_TOOLS = ["Read", "Glob", "Grep", "Bash(python:*)", "Bash(python3:*)", "Bash(py:*)"]
DENIED_TOOLS = ["Write", "Edit", "NotebookEdit", "WebFetch", "WebSearch"]

SYSTEM_APPEND = """You are running inside Viral Stickman Studio, a local app. Hard rules:
- Never publish, post, comment, like, follow, upload or DM anything. Output is files and copy blocks for the user.
- Never invent a statistic, result, quotation or source. If a number is needed and not provided, write {{your number}}.
- Voice profiles: use config/voice/youtube.md instead of ~/.claude/youtube/voice.md and
  config/voice/instagram.md instead of ~/.claude/instagram/voice.md. Never write to ~/.claude.
- Run skill Python tools with the same interpreter that runs you (python or python3), from the repo root.
- Return ONLY the structured result requested; the app writes the files."""


class AgentError(RuntimeError):
    pass


@dataclass
class AgentTask:
    name: str                       # fixture key and log label
    prompt: str
    schema: dict                    # JSON Schema of the structured result
    skills: list[str] = field(default_factory=list)
    model_key: str = "direction"    # settings.models[...]
    context: dict = field(default_factory=dict)  # inputs, also given to the fixture agent


def _validate(task: AgentTask, data: Any) -> None:
    errs = sorted(Draft202012Validator(task.schema).iter_errors(data), key=lambda e: list(e.path))
    if errs:
        raise AgentError(f"{task.name}: result does not match schema: " +
                         "; ".join(f"{list(e.path)}: {e.message}" for e in errs[:5]))


def build_options(task: AgentTask, settings: dict):
    """ClaudeAgentOptions for one skill call: project + user skills, read-only tools, structured output."""
    from claude_agent_sdk import ClaudeAgentOptions

    env = {}
    if has_secret("ANTHROPIC_API_KEY"):
        env["ANTHROPIC_API_KEY"] = secret("ANTHROPIC_API_KEY")  # in-memory only, never logged
    return ClaudeAgentOptions(
        cwd=str(REPO_ROOT), setting_sources=["user", "project"], skills=task.skills or None,
        allowed_tools=READ_ONLY_TOOLS + [f"Skill({s})" for s in task.skills],
        disallowed_tools=DENIED_TOOLS, permission_mode="dontAsk",
        model=settings["models"].get(task.model_key, settings["models"]["direction"]),
        max_budget_usd=float(settings.get("agent_budget_per_stage_usd", 2.0)),
        system_prompt={"type": "preset", "preset": "claude_code", "append": SYSTEM_APPEND},
        output_format={"type": "json_schema", "schema": task.schema}, env=env,
    )


class SdkAgent:
    kind = "claude-agent-sdk"

    def __init__(self, settings: dict):
        self.settings = settings

    async def run(self, task: AgentTask, ctx) -> dict:
        from claude_agent_sdk import AssistantMessage, ResultMessage, TextBlock, ToolUseBlock, query

        model = self.settings["models"].get(task.model_key, self.settings["models"]["direction"])
        last_err = None
        prompt = task.prompt
        for attempt in (1, 2):
            opts = build_options(task, self.settings)
            ctx.log(f"agent[{task.name}] model={model} skills={','.join(task.skills) or '-'} attempt {attempt}")
            result = None
            try:
                async for msg in query(prompt=prompt, options=opts):
                    if isinstance(msg, AssistantMessage):
                        for b in msg.content:
                            if isinstance(b, ToolUseBlock):
                                ctx.log(f"  tool {b.name}: {redact(json.dumps(b.input)[:160])}", "agent")
                            elif isinstance(b, TextBlock) and b.text.strip():
                                ctx.log("  " + redact(b.text.strip()[:240]), "agent")
                    elif isinstance(msg, ResultMessage):
                        result = msg
            except Exception as e:
                raise AgentError(f"Claude Agent SDK failed: {type(e).__name__}: {redact(str(e))[:300]}. "
                                 "Set ANTHROPIC_API_KEY in .env or log in with `claude login`.") from e
            if result is None:
                raise AgentError(f"{task.name}: no result message")
            if result.total_cost_usd:
                ctx.add_cost(float(result.total_cost_usd), f"agent {task.name}")
            if result.is_error:
                raise AgentError(f"{task.name}: agent error ({result.subtype}): {redact(str(result.result))[:300]}")
            data = result.structured_output
            if data is None and result.result:
                try:
                    data = json.loads(result.result)
                except json.JSONDecodeError:
                    data = None
            try:
                if data is None:
                    raise AgentError(f"{task.name}: no structured output")
                _validate(task, data)
                return data
            except AgentError as e:
                last_err = e
                ctx.log(f"agent[{task.name}] invalid result, retrying once: {e}", "warn")
                prompt = task.prompt + f"\n\nYour previous result was invalid: {e}. Return a result that matches the schema exactly."
        raise last_err or AgentError(task.name)


class FixtureAgent:
    """Dry-run agent. Produces deterministic, clearly labelled outputs so every downstream tool, gate
    and screen can be exercised for free. The pack Python tools still run for real on this text."""
    kind = "fixture (dry run)"

    def __init__(self, settings: dict):
        self.settings = settings

    async def run(self, task: AgentTask, ctx) -> dict:
        from . import fixtures
        fn = getattr(fixtures, task.name, None)
        if fn is None:
            raise AgentError(f"no dry-run fixture for task {task.name}")
        data = fn(**task.context)
        _validate(task, data)
        ctx.log(f"agent[{task.name}] dry-run fixture used (no Claude call, $0)", "agent")
        return data


class HybridAgent:
    """Claude for direction (the hardest, highest-leverage writing), the local model (or Groq) for the rest."""

    def __init__(self, settings: dict, writer: str = "local"):
        from .local import GroqAgent, LocalAgent
        self.claude, self.local = SdkAgent(settings), (GroqAgent if writer == "groq" else LocalAgent)(settings)
        self.kind = f"hybrid (Claude direction + {self.local.kind})"

    async def run(self, task: AgentTask, ctx) -> dict:
        return await (self.claude if task.model_key == "direction" else self.local).run(task, ctx)


def get_agent(settings: dict):
    if settings.get("dry_run", True):
        return FixtureAgent(settings)
    provider = settings.get("agent", {}).get("provider", "claude")
    if provider == "local":
        from .local import LocalAgent
        return LocalAgent(settings)
    if provider == "groq":
        from .local import GroqAgent
        return GroqAgent(settings)
    if provider == "hybrid":
        return HybridAgent(settings)
    if provider == "hybrid-groq":
        return HybridAgent(settings, "groq")
    return SdkAgent(settings)
