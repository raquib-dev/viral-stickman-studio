"""Local AI: the OpenAI-compatible agent, the ComfyUI and stickman render backends, local TTS fitting,
settings defaults, and the clip tracker's live state. External servers are faked with httpx.MockTransport."""
import asyncio
import json

import httpx
import pytest

from backend.app import db, jobs, paths, settings as settings_mod
from backend.app.agent import local as la
from backend.app.agent.runner import AgentError, AgentTask, FixtureAgent, HybridAgent, SdkAgent, get_agent
from backend.app.jobs import manager
from backend.app.render import local as rl
from backend.app.render import tts
from backend.app.render.base import ClipSpec
from backend.app.render.media import probe, run_ffmpeg
from backend.app.stages import production

SCHEMA = {"type": "object", "properties": {"title": {"type": "string"}, "n": {"type": "integer"}},
          "required": ["title", "n"], "additionalProperties": True}
_sleep = asyncio.sleep


class Ctx:
    def __init__(self):
        self.lines = []

    def log(self, text, level="info"):
        self.lines.append((level, text))

    def check_cancelled(self):
        pass


def _settings(**agent):
    s = settings_mod.load_settings()
    s["agent"] = {**s["agent"], **agent}
    return s


def _reply(content):
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}],
                                     "usage": {"prompt_tokens": 10, "completion_tokens": 5}})


def test_settings_defaults_fill_old_files():
    s = settings_mod.load_settings()
    assert s["agent"]["provider"] == "claude" and s["voice"]["tts"] == "auto"
    assert s["render"]["comfyui"]["frames"] == 81 and s["render"]["backend"] == "mock"
    bad = {**s, "agent": {**s["agent"], "provider": "gpt"}}
    with pytest.raises(ValueError):
        settings_mod.validate_settings(bad)


def test_get_agent_routes_by_provider():
    s = _settings(provider="local")
    assert isinstance(get_agent({**s, "dry_run": True}), FixtureAgent)
    assert isinstance(get_agent({**s, "dry_run": False}), la.LocalAgent)
    assert isinstance(get_agent({**_settings(provider="hybrid"), "dry_run": False}), HybridAgent)
    assert isinstance(get_agent({**_settings(provider="claude"), "dry_run": False}), SdkAgent)


def test_extract_json_handles_think_and_fences():
    assert la.extract_json('<think>hmm {"x": 1}</think>\n```json\n{"title": "a", "n": 2}\n```') == {"title": "a", "n": 2}
    assert la.extract_json('Sure! Here it is: {"title": "b", "n": 3} hope that helps') == {"title": "b", "n": 3}
    with pytest.raises(AgentError):
        la.extract_json("no json here")


async def test_local_agent_retries_invalid_then_succeeds():
    calls = []

    def handler(req: httpx.Request):
        body = json.loads(req.content)
        calls.append(body)
        if len(calls) == 1:
            return httpx.Response(400, text="response_format json_schema not supported")
        if len(calls) == 2:
            return _reply('{"title": "missing n"}')
        return _reply('<think>fix it</think>{"title": "ok", "n": 5}')

    task = AgentTask("script", "Write it. Voice: config/voice/youtube.md", SCHEMA, ["yt-script"])
    agent = la.LocalAgent(_settings(provider="local"), transport=httpx.MockTransport(handler))
    ctx = Ctx()
    assert await agent.run(task, ctx) == {"title": "ok", "n": 5}
    assert calls[1]["response_format"] == {"type": "json_object"}       # fell back from json_schema
    assert "invalid" in calls[2]["messages"][-1]["content"]                # validation error fed back
    system = calls[0]["messages"][0]["content"]
    assert "SKILL `yt-script`" in system and "FILE config/voice/youtube.md" in system
    assert any("attempt 1 invalid" in t for _, t in ctx.lines)


async def test_local_agent_reports_unreachable_server():
    def handler(req):
        raise httpx.ConnectError("refused")
    agent = la.LocalAgent(_settings(provider="local"), transport=httpx.MockTransport(handler))
    with pytest.raises(AgentError, match="cannot reach the local LLM"):
        await agent.run(AgentTask("x", "p", SCHEMA), Ctx())


def test_comfy_fill_and_find():
    wf = {"_comment": "x", "1": {"inputs": {"w": "{{WIDTH}}", "text": "a {{PROMPT}} b", "keep": "{{UNKNOWN}}"}}}
    out = rl.fill(wf, {"WIDTH": 480, "PROMPT": "stickman"})
    assert out == {"1": {"inputs": {"w": 480, "text": "a stickman b", "keep": "{{UNKNOWN}}"}}}
    hist = {"outputs": {"9": {"images": [{"filename": "a.png"}]}, "10": {"gifs": [{"filename": "clip.webm", "subfolder": "vss"}]}}}
    assert rl.find_video(hist)["filename"] == "clip.webm"
    assert "piano" not in rl.clean_prompt("A stickman walks. Audio: quiet piano. He points at a coin.")


async def test_comfyui_backend_end_to_end(tmp_path, monkeypatch):
    src = tmp_path / "gen.webm"
    run_ffmpeg(["-f", "lavfi", "-i", "testsrc2=s=480x832:r=16:d=2", "-c:v", "libvpx-vp9", "-b:v", "200k", str(src)])
    seen = {}

    def handler(req: httpx.Request):
        if req.url.path == "/prompt":
            seen["prompt"] = json.loads(req.content)["prompt"]
            return httpx.Response(200, json={"prompt_id": "p1"})
        if req.url.path == "/history/p1":
            return httpx.Response(200, json={"p1": {"status": {"status_str": "success", "completed": True},
                                                    "outputs": {"10": {"images": [{"filename": "c.webm", "subfolder": "vss", "type": "output"}]}}}})
        if req.url.path == "/view":
            return httpx.Response(200, content=src.read_bytes())
        return httpx.Response(404)

    real = settings_mod.load_settings

    def fake_settings():
        s = real()
        s["voice"]["tts"] = "none"
        s["render"]["comfyui"]["poll_s"] = 0
        return s
    monkeypatch.setattr(rl, "load_settings", fake_settings)
    be = rl.ComfyUIBackend(transport=httpx.MockTransport(handler))
    clip = ClipSpec(0, "A stickman points. Audio: piano.", "9:16", "360p", 4.0, out_path=tmp_path / "clip-01.mp4")
    res = await be.render_clip(clip, None, lambda *a, **k: None)
    info = probe(res.path)
    assert (info["width"], info["height"]) == (360, 640) and abs(info["duration"] - 4.0) < 0.2 and info["has_audio"]
    assert res.meta["stretch"] == pytest.approx(2.0, abs=0.02) and res.cost_usd == 0
    node = seen["prompt"]["7"]["inputs"]
    assert (node["width"], node["height"], node["length"]) == (480, 832, 81)
    assert "piano" not in seen["prompt"]["5"]["inputs"]["text"]


async def test_comfyui_oom_is_not_retried(tmp_path, monkeypatch):
    def handler(req):
        if req.url.path == "/prompt":
            return httpx.Response(200, json={"prompt_id": "p"})
        return httpx.Response(200, json={"p": {"status": {"status_str": "error", "messages": [
            ["execution_error", {"exception_message": "CUDA out of memory. Tried to allocate 2 GiB"}]]}}})
    real = settings_mod.load_settings
    monkeypatch.setattr(rl, "load_settings", lambda: {**real(), "render": {**real()["render"], "comfyui": {**real()["render"]["comfyui"], "poll_s": 0}}})
    be = rl.ComfyUIBackend(transport=httpx.MockTransport(handler))
    with pytest.raises(rl.RenderError) as e:
        await be.render_clip(ClipSpec(0, "x", "9:16", "360p", out_path=tmp_path / "c.mp4"), None, lambda *a, **k: None)
    assert not e.value.retryable and "out of memory" in str(e.value)


async def test_fit_speeds_up_long_speech(tmp_path):
    video = tmp_path / "v.mp4"
    speech = tmp_path / "s.wav"
    run_ffmpeg(["-f", "lavfi", "-i", "color=c=black:s=320x240:r=24:d=4", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(video)])
    run_ffmpeg(["-f", "lavfi", "-i", "sine=frequency=200:sample_rate=24000:duration=6", str(speech)])
    fit = await tts.fit_to_clip(video, speech, tmp_path / "o.mp4", 4.0, max_speedup=1.3)
    assert fit["tempo"] == 1.3 and fit["cut"]
    info = probe(tmp_path / "o.mp4")
    assert info["has_audio"] and abs(info["duration"] - 4.0) < 0.15


async def test_local_stickman_render_stage_records_progress(monkeypatch):
    real = jobs.load_settings

    def live_local():
        s = real()
        s["dry_run"] = False
        s["render"] = {**s["render"], "backend": "local-stickman", "resolution": "360p"}
        s["voice"] = {**s["voice"], "tts": "none"}
        return s
    monkeypatch.setattr(jobs, "load_settings", live_local)
    monkeypatch.setattr(rl, "load_settings", live_local)
    await manager.start()
    slug = "local-stick"
    db.upsert_project(slug, slug, {"name": slug, "niche": "x", "ratio": "9:16", "duration": 20, "platforms": ["shorts"], "theme": "light"})
    root = paths.ensure_project_dirs(slug)
    for rel, obj in {"direction/phase-b.json": {"checks": [], "prompts": [{"text": "stickman saves money"}, {"text": "stickman wins"}]},
                     "direction/phase-a.json": {"rows": [{"purpose": "hook"}, {"purpose": "payoff"}]},
                     "script/script.json": {"clips": [{"vo": "Why do we spend?"}, {"vo": "You finally win."}]}}.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(json.dumps(obj))
    events = []
    q = jobs.bus.subscribe(slug)
    job_id, fut = manager.submit(slug, "render", {})
    assert await fut == "succeeded", db.get_job(job_id)
    while not q.empty():
        events.append(q.get_nowait())
    meta = json.loads((root / "clips/clip-02.json").read_text())
    assert meta["status"] == "done" and meta["backend"] == "local-stickman" and meta["attempts"] == 1
    assert meta["history"][0]["ok"] and meta["meta"]["scene"]["actions"][0] == "celebrate"
    assert (meta["width"], meta["height"]) == (360, 640) and meta["has_audio"]
    statuses = [e["status"] for e in events if e["type"] == "clip"]
    assert statuses[0] == "queued" and "rendering" in statuses and statuses[-1] == "done"
    assert db.get_job(job_id)["cost_usd"] == 0
    await manager.stop()


def test_ui_build_stale_detects_old_dist(tmp_path, monkeypatch):
    import os
    from backend.app import main
    (tmp_path / "frontend" / "src").mkdir(parents=True)
    (tmp_path / "frontend" / "dist").mkdir()
    src, built = tmp_path / "frontend/src/a.tsx", tmp_path / "frontend/dist/index.html"
    built.write_text("<body></body>")
    src.write_text("x")
    monkeypatch.setattr(main.paths, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(main.paths, "FRONTEND_DIST", tmp_path / "frontend" / "dist")
    os.utime(built, (1000, 1000))
    os.utime(src, (5000, 5000))
    assert main.ui_build_stale() is True
    os.utime(built, (9000, 9000))
    assert main.ui_build_stale() is False


def test_phase_b_blocks_inserted_verbatim_for_local_models():
    from backend.app.agent import tasks
    from backend.app.agent.skillref import anchor_for, male_voice_block
    from backend.app.stages.studio import assemble_phase_b, check_phase_b
    task = tasks.phase_b("md", [], "9:16", 30, "1", "dark", {}, app_inserts_blocks=True)
    assert "{{ANCHOR}}" in task.prompt and "{{VOICE}}" in task.prompt
    # what qwen3:8b did: paraphrased both blocks; one clip uses the markers, one skips them
    res = {"character_anchor": "A white stick man with a round head.", "voice_block": "A calm male narrator.",
           "prompts": [{"clip": 1, "text": "Create a 10s clip.\nBlack canvas.\n{{ANCHOR}}\nHe walks.\nSays: hi\n{{VOICE}}"},
                       {"clip": 2, "text": "Create a 10s clip.\nA white stick man with a round head walks. A calm male narrator."},
                       {"clip": 3, "text": "Create a 10s clip.\nHe smiles."}]}
    assert len(check_phase_b(dict(res, prompts=[dict(p) for p in res["prompts"]]), 3, "1", "dark")) == 6
    assemble_phase_b(res, "1", "dark", "male", app_inserts=True)
    assert check_phase_b(res, 3, "1", "dark") == []
    anchor, voice = anchor_for("1", "dark"), male_voice_block()
    assert res["character_anchor"] == anchor and res["voice_block"] == voice
    assert all(p["text"].count(anchor) == 1 and p["text"].count(voice) == 1 for p in res["prompts"])
    assert res["prompts"][0]["text"].split("\n")[2] == anchor          # placed where the marker was


def test_phase_b_claude_output_left_alone_when_valid():
    from backend.app.agent import fixtures
    from backend.app.stages.studio import assemble_phase_b, check_phase_b
    rows = [{"clip": k, "scene": "s", "motion": "m", "vo": "v"} for k in (1, 2)]
    res = fixtures.phase_b("md", rows, "9:16", 20, "1", "dark", {})
    before = [p["text"] for p in res["prompts"]]
    assert assemble_phase_b(res, "1", "dark", "male", app_inserts=False) == []
    assert [p["text"] for p in res["prompts"]] == before and check_phase_b(res, 2, "1", "dark") == []


async def test_ollama_native_api_sets_context_and_warns_on_overflow():
    seen = {}

    def handler(req: httpx.Request):
        if req.url.path == "/api/version":
            return httpx.Response(200, json={"version": "0.12.0"})
        if req.url.path == "/api/chat":
            seen["body"] = json.loads(req.content)
            return httpx.Response(200, json={"message": {"content": '{"title": "t", "n": 1}'},
                                             "prompt_eval_count": 8100, "eval_count": 90, "done_reason": "stop"})
        return httpx.Response(404)

    s = _settings(provider="local")
    s["agent"]["local"] = {**s["agent"]["local"], "base_url": "http://localhost:11434/v1", "num_ctx": 8192}
    ctx = Ctx()
    out = await la.LocalAgent(s, transport=httpx.MockTransport(handler)).run(AgentTask("x", "p", SCHEMA), ctx)
    assert out == {"title": "t", "n": 1}
    b = seen["body"]
    assert b["options"]["num_ctx"] == 8192 and b["format"] == SCHEMA and b["think"] is False
    assert any("filled the 8192-token context" in t for _, t in ctx.lines)


async def test_ollama_missing_model_says_how_to_pull():
    def handler(req):
        if req.url.path == "/api/version":
            return httpx.Response(200, json={"version": "0.12.0"})
        return httpx.Response(404, json={"error": "model not found"})
    s = _settings(provider="local")
    s["agent"]["local"] = {**s["agent"]["local"], "model": "qwen3:14b"}
    with pytest.raises(AgentError, match="ollama pull qwen3:14b"):
        await la.LocalAgent(s, transport=httpx.MockTransport(handler)).run(AgentTask("x", "p", SCHEMA), Ctx())


async def test_comfyui_reports_missing_model_files():
    wf = json.loads((paths.REPO_ROOT / "config/comfyui/wan21-t2v-1.3b.json").read_text())
    have = {"UNETLoader": ("unet_name", ["wan2.1_t2v_1.3B_fp16.safetensors"]),
            "CLIPLoader": ("clip_name", ["models_t5_umt5-xxl-enc-bf16.pth"]),
            "VAELoader": ("vae_name", ["Wan2.1_VAE.pth"])}

    def handler(req: httpx.Request):
        cls = req.url.path.rsplit("/", 1)[-1]
        field, files = have[cls]
        return httpx.Response(200, json={cls: {"input": {"required": {field: [files], "type": [["wan"]]}}}})
    async with httpx.AsyncClient(base_url="http://c", transport=httpx.MockTransport(handler)) as http:
        missing = await rl.missing_models(http, wf)
    assert [m["file"] for m in missing] == ["umt5_xxl_fp8_e4m3fn_scaled.safetensors", "wan_2.1_vae.safetensors"]
    assert "found: Wan2.1_VAE.pth" in rl.missing_message(missing)
