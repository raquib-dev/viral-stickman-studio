"""FastAPI app: REST + SSE for the pipeline, and the built React UI as static files.

Run: python -m uvicorn backend.app.main:app --port 8000   (see README for Windows steps)
"""
from __future__ import annotations

import asyncio
import json
import shutil
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import db, gates, paths, pipeline
from . import stages  # noqa: F401  (registers stages)
from .analysis import blueprint as bp
from .jobs import REGISTRY, bus, manager
from .settings import CONFIG, load_settings, public_settings, reload_env, save_settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    await manager.start()
    yield
    await manager.stop()


app = FastAPI(title="Viral Stickman Studio", version="0.1.0", lifespan=lifespan)


# ---- models ---------------------------------------------------------------------------------

class ProjectIn(BaseModel):
    name: str
    niche: str
    subtopics: list[str] = []
    platforms: list[str] = ["shorts", "reels"]
    style: str = "1"
    theme: str = "dark"
    ratio: str = "9:16"
    duration: int = 60
    competitors: dict[str, list[str]] = Field(default_factory=lambda: {"youtube": [], "instagram": []})
    voice_pref: str = "male"
    voice_transcripts: dict[str, list[str]] = Field(default_factory=lambda: {"youtube": [], "instagram": []})


class GateDecision(BaseModel):
    action: str
    choice: Any = None
    note: str = ""


class RunIn(BaseModel):
    params: dict = {}


class PipelineIn(BaseModel):
    from_stage: str | None = None
    to_stage: str | None = None


# ---- helpers --------------------------------------------------------------------------------

def _project_or_404(slug: str) -> dict:
    try:
        paths.project_dir(slug)
    except ValueError as e:
        raise HTTPException(400, str(e))
    p = db.get_project(slug)
    if not p:
        raise HTTPException(404, f"unknown project {slug}")
    return p


def _write_project_json(slug: str, data: dict) -> None:
    root = paths.ensure_project_dirs(slug)
    (root / "project.json").write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _snapshot(slug: str) -> dict:
    p = _project_or_404(slug)
    return {"project": p, "stages": pipeline.stage_status(slug), "pipeline": db.get_pipeline(slug),
            "gates": db.list_gates(slug), "spend_usd": round(db.project_spend(slug), 4),
            "render_spend_usd": round(sum(j["cost_usd"] for j in db.list_jobs(slug, 1000) if j["stage"] == "render"), 4)}


# ---- settings / meta ------------------------------------------------------------------------

@app.get("/api/health")
def health() -> dict:
    s = load_settings()
    return {"ok": True, "dry_run": s.get("dry_run", True), "time": time.time(),
            "agent_provider": s["agent"]["provider"], "render_backend": s["render"]["backend"]}


def _gpu() -> dict:
    """NVIDIA GPU name and memory via nvidia-smi (no CUDA libraries needed)."""
    import shutil
    import subprocess
    exe = shutil.which("nvidia-smi")
    if not exe:
        return {"ok": False, "error": "nvidia-smi not found (no NVIDIA driver on PATH)"}
    try:
        out = subprocess.run([exe, "--query-gpu=name,memory.total,memory.used,driver_version", "--format=csv,noheader,nounits"],
                             capture_output=True, text=True, timeout=8).stdout.strip().splitlines()
        name, total, used, driver = [x.strip() for x in out[0].split(",")]
        return {"ok": True, "name": name, "vram_total_gb": round(int(total) / 1024, 1), "vram_used_gb": round(int(used) / 1024, 1),
                "driver": driver}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {str(e)[:160]}"}


@app.get("/api/local/status")
async def local_status() -> dict:
    """Which local AI pieces are reachable/installed, for Settings → Local services."""
    from .agent.local import status as llm_status
    from .render import tts
    from .render.captions import whisper_device
    from .render.local import comfy_status
    s = load_settings()
    llm, comfy = await asyncio.gather(llm_status(s["agent"]["local"]["base_url"]), comfy_status(s["render"]["comfyui"]["url"]))
    if llm.get("ok"):
        llm["model_present"] = any(s["agent"]["local"]["model"] in (m or "") for m in llm.get("models", []))
    try:
        import faster_whisper  # noqa: F401
        whisper = {"installed": True, "device": whisper_device(s["captions"].get("whisper_device", "auto"))[0]}
    except Exception:
        whisper = {"installed": False}
    try:
        import PIL  # noqa: F401
        stickman = {"ok": True}
    except Exception:
        stickman = {"ok": False, "error": "pip install pillow"}
    return {"llm": {**llm, "url": s["agent"]["local"]["base_url"], "model": s["agent"]["local"]["model"]},
            "comfyui": {**comfy, "url": s["render"]["comfyui"]["url"]}, "tts": await asyncio.to_thread(tts.available),
            "whisper": whisper, "stickman": stickman, "gpu": await asyncio.to_thread(_gpu)}


@app.get("/api/settings")
def get_settings() -> dict:
    reload_env()
    return public_settings()


@app.put("/api/settings")
def put_settings(body: dict) -> dict:
    body.pop("keys", None)
    try:
        save_settings(body)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return public_settings()


@app.get("/api/pricing")
def get_pricing() -> dict:
    return json.loads((CONFIG / "pricing.json").read_text(encoding="utf-8"))


@app.get("/api/blueprint")
def get_blueprint() -> dict:
    return bp.load()


@app.get("/api/stages")
def get_stages() -> dict:
    return {"pipeline": pipeline.PIPELINE, "all": pipeline.ALL_STAGES, "gates": gates.GATES,
            "stages": {k: {"title": v.title, "lane": v.lane, "description": v.description, "skills": v.skills,
                           "tools": v.tools} for k, v in REGISTRY.items()}}


# ---- projects -------------------------------------------------------------------------------

@app.get("/api/projects")
def list_projects() -> list[dict]:
    out = []
    for r in db.list_projects():
        pl = db.get_pipeline(r["slug"])
        out.append({**r, "pipeline": pl and pl["status"]})
    return out


@app.post("/api/projects")
def create_project(body: ProjectIn) -> dict:
    slug = paths.slugify(body.name)
    base, k = slug, 2
    while db.get_project(slug):
        slug = paths.slugify(f"{base[:36]}-{k}")
        k += 1
    data = body.model_dump()
    db.upsert_project(slug, body.name, data)
    _write_project_json(slug, data)
    return _snapshot(slug)


@app.get("/api/projects/{slug}")
def get_project(slug: str) -> dict:
    return _snapshot(slug)


@app.put("/api/projects/{slug}")
def update_project(slug: str, body: dict) -> dict:
    p = _project_or_404(slug)
    data = {**p["data"], **{k: v for k, v in body.items() if k != "slug"}}
    db.upsert_project(slug, data.get("name", p["name"]), data)
    _write_project_json(slug, data)
    return _snapshot(slug)


@app.delete("/api/projects/{slug}")
def delete_project(slug: str, delete_files: bool = False) -> dict:
    _project_or_404(slug)
    if pipeline.is_running(slug):
        raise HTTPException(409, "stop the pipeline first")
    db.delete_project(slug)
    if delete_files:
        shutil.rmtree(paths.project_dir(slug), ignore_errors=True)
    return {"deleted": slug, "files_deleted": delete_files}


# ---- pipeline / stages / jobs ---------------------------------------------------------------

@app.post("/api/projects/{slug}/pipeline/start")
async def start_pipeline(slug: str, body: PipelineIn) -> dict:
    _project_or_404(slug)
    try:
        pipeline.start(slug, body.from_stage, body.to_stage)
    except (RuntimeError, ValueError) as e:
        raise HTTPException(409, str(e))
    return _snapshot(slug)


@app.post("/api/projects/{slug}/pipeline/stop")
async def stop_pipeline(slug: str) -> dict:
    _project_or_404(slug)
    pipeline.stop(slug)
    return _snapshot(slug)


@app.post("/api/projects/{slug}/stages/{stage_name}/run")
async def run_stage(slug: str, stage_name: str, body: RunIn) -> dict:
    _project_or_404(slug)
    if stage_name not in REGISTRY:
        raise HTTPException(404, f"unknown stage {stage_name}")
    if pipeline.is_running(slug):
        raise HTTPException(409, "the pipeline is running; stop it or wait")
    job_id, _ = manager.submit(slug, stage_name, body.params)
    return {"job_id": job_id}


@app.post("/api/projects/{slug}/clips/{n}/regenerate")
async def regenerate_clip(slug: str, n: int) -> dict:
    _project_or_404(slug)
    if pipeline.is_running(slug):
        raise HTTPException(409, "the pipeline is running; stop it or wait")
    n_clips = int(_project_or_404(slug)["data"].get("duration", 60)) // 10
    if not 1 <= n <= n_clips:
        raise HTTPException(400, f"clip {n} does not exist (this video has {n_clips} clips)")
    job_id, _ = manager.submit(slug, "render", {"only": [n], "force": True})
    return {"job_id": job_id}


@app.get("/api/projects/{slug}/jobs")
def project_jobs(slug: str) -> list[dict]:
    _project_or_404(slug)
    return db.list_jobs(slug)


@app.get("/api/jobs/{job_id}")
def job_detail(job_id: int, after: int = 0) -> dict:
    j = db.get_job(job_id)
    if not j:
        raise HTTPException(404, "unknown job")
    return {**j, "logs": db.job_logs(job_id, after)}


@app.post("/api/jobs/{job_id}/retry")
async def retry_job(job_id: int) -> dict:
    """Run a finished job's stage again with the same params (e.g. 'clip 6 only')."""
    j = db.get_job(job_id)
    if not j:
        raise HTTPException(404, "unknown job")
    if pipeline.is_running(j["project"]):
        raise HTTPException(409, "the pipeline is running; stop it or wait")
    if j["status"] in ("queued", "running"):
        raise HTTPException(409, "that job is still running")
    params = {k: v for k, v in (j["params"] or {}).items() if k != "via"}
    new_id, _ = manager.submit(j["project"], j["stage"], params)
    return {"job_id": new_id}


@app.post("/api/jobs/{job_id}/cancel")
def cancel_job(job_id: int) -> dict:
    return {"cancelled": manager.cancel(job_id)}


# ---- gates ----------------------------------------------------------------------------------

@app.get("/api/projects/{slug}/gates")
def list_gates(slug: str) -> list[dict]:
    _project_or_404(slug)
    return db.list_gates(slug)


@app.post("/api/projects/{slug}/gates/{name}")
async def decide_gate(slug: str, name: str, body: GateDecision) -> dict:
    _project_or_404(slug)
    try:
        g = gates.decide(slug, name, body.action, body.choice, body.note)
    except (KeyError, ValueError) as e:
        raise HTTPException(400, str(e))
    if body.action == "approve":
        pipeline.resume_after_gate(slug, name)
    else:
        pl = db.get_pipeline(slug)
        if pl and pl["status"] == "waiting_gate":
            db.put_pipeline(slug, status="rejected", message=f"you rejected {name}: {body.note}")
            bus.publish(slug, {"type": "pipeline", **(db.get_pipeline(slug) or {})})
    return {"gate": g, **_snapshot(slug)}


@app.put("/api/projects/{slug}/phase-a")
def edit_phase_a(slug: str, body: dict) -> dict:
    """Edit Phase A text before approving. The gate's payload hash changes with the text."""
    p = _project_or_404(slug)
    md = body.get("markdown", "")
    if not md.strip():
        raise HTTPException(400, "empty Phase A")
    f = paths.safe_project_path(slug, "direction/phase-a.md")
    f.write_text(md, encoding="utf-8", newline="\n")
    from .stages.studio import phase_a_gate_payload
    gates.reopen_with_payload(slug, "phase_a", phase_a_gate_payload(paths.project_dir(slug), p["data"]))
    return _snapshot(slug)


# ---- inputs the user pastes / uploads -------------------------------------------------------

@app.post("/api/projects/{slug}/ig-rows")
def add_ig_rows(slug: str, body: dict) -> dict:
    p = _project_or_404(slug)
    rows = [r for r in body.get("rows", []) if r.get("views") and r.get("hook")]
    data = {**p["data"], "ig_rows": (p["data"].get("ig_rows") or []) + rows}
    db.upsert_project(slug, p["name"], data)
    _write_project_json(slug, data)
    return {"ig_rows": len(data["ig_rows"])}


@app.post("/api/projects/{slug}/yt-rows")
def add_yt_rows(slug: str, body: dict) -> dict:
    p = _project_or_404(slug)
    rows = [r for r in body.get("rows", []) if r.get("channel") and r.get("views") and r.get("title")]
    data = {**p["data"], "yt_rows_pasted": (p["data"].get("yt_rows_pasted") or []) + rows}
    db.upsert_project(slug, p["name"], data)
    _write_project_json(slug, data)
    return {"yt_rows": len(data["yt_rows_pasted"])}


@app.post("/api/projects/{slug}/transcripts")
def add_transcript(slug: str, body: dict) -> dict:
    p = _project_or_404(slug)
    if not body.get("url") or not body.get("text"):
        raise HTTPException(400, "url and text are required")
    trs = [t for t in (p["data"].get("pasted_transcripts") or []) if t.get("url") != body["url"]]
    trs.append({"url": body["url"], "title": body.get("title", ""), "text": body["text"]})
    data = {**p["data"], "pasted_transcripts": trs}
    db.upsert_project(slug, p["name"], data)
    _write_project_json(slug, data)
    return {"transcripts": len(trs)}


@app.post("/api/projects/{slug}/voice/apply")
def apply_voice(slug: str, body: dict) -> dict:
    _project_or_404(slug)
    platform = body.get("platform")
    if platform not in ("youtube", "instagram"):
        raise HTTPException(400, "platform must be youtube or instagram")
    draft = paths.safe_project_path(slug, f"research/voice-draft-{platform}.md")
    if not draft.exists():
        raise HTTPException(404, "no draft; run the niche stage with your transcripts first")
    target = CONFIG / "voice" / f"{platform}.md"
    if target.exists():
        shutil.copy2(target, target.with_suffix(f".bak-{int(time.time())}.md"))
    shutil.copy2(draft, target)
    return {"applied": str(target.relative_to(paths.REPO_ROOT))}


@app.get("/api/voice/{platform}")
def get_voice(platform: str) -> dict:
    if platform not in ("youtube", "instagram"):
        raise HTTPException(400, "platform must be youtube or instagram")
    return {"markdown": (CONFIG / "voice" / f"{platform}.md").read_text(encoding="utf-8")}


@app.put("/api/voice/{platform}")
def put_voice(platform: str, body: dict) -> dict:
    if platform not in ("youtube", "instagram"):
        raise HTTPException(400, "platform must be youtube or instagram")
    (CONFIG / "voice" / f"{platform}.md").write_text(body.get("markdown", ""), encoding="utf-8", newline="\n")
    return {"saved": True}


@app.post("/api/projects/{slug}/learn/retention")
async def upload_retention(slug: str, file: UploadFile = File(...)) -> dict:
    _project_or_404(slug)
    data = await file.read()
    if len(data) > 5_000_000:
        raise HTTPException(413, "file too large")
    f = paths.safe_project_path(slug, "research/learn/retention.csv")
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_bytes(data)
    return {"saved": "research/learn/retention.csv", "bytes": len(data)}


@app.post("/api/projects/{slug}/learn/ig")
def save_ig_insights(slug: str, body: dict) -> dict:
    _project_or_404(slug)
    f = paths.safe_project_path(slug, "research/learn/ig-insights.txt")
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(body.get("text", ""), encoding="utf-8")
    return {"saved": "research/learn/ig-insights.txt"}


@app.get("/api/projects/{slug}/swipe")
def swipe(slug: str) -> list[dict]:
    _project_or_404(slug)
    return db.swipe_items(slug)


@app.get("/api/projects/{slug}/files/{rel:path}")
def project_file(slug: str, rel: str, optional: bool = False):
    """Serve a project output. optional=1 answers 204 for "not produced yet" instead of 404, so the UI
    can poll for files that appear as stages finish without logging errors."""
    _project_or_404(slug)
    try:
        f = paths.safe_project_path(slug, rel)
    except ValueError as e:
        raise HTTPException(400, str(e))
    if not f.exists() or not f.is_file():
        if optional:
            return Response(status_code=204)
        raise HTTPException(404, f"{rel} does not exist yet")
    if f.suffix == ".json":
        return JSONResponse(json.loads(f.read_text(encoding="utf-8")))
    return FileResponse(f, headers={"Cache-Control": "no-store"})


@app.get("/api/projects/{slug}/ls/{rel:path}")
def project_ls(slug: str, rel: str) -> list[dict]:
    _project_or_404(slug)
    d = paths.safe_project_path(slug, rel)
    if not d.is_dir():
        return []
    return [{"name": x.name, "size": x.stat().st_size, "mtime": x.stat().st_mtime, "dir": x.is_dir()}
            for x in sorted(d.iterdir())]


# ---- SSE ------------------------------------------------------------------------------------

@app.get("/api/projects/{slug}/events")
async def events(slug: str, request: Request):
    _project_or_404(slug)
    q = bus.subscribe(slug)

    async def stream():
        try:
            yield f"event: snapshot\ndata: {json.dumps(_snapshot(slug), default=str)}\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    ev = await asyncio.wait_for(q.get(), timeout=15)
                    yield f"event: {ev.get('type', 'message')}\ndata: {json.dumps(ev, default=str)}\n\n"
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            bus.unsubscribe(slug, q)

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ---- frontend -------------------------------------------------------------------------------

if paths.FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=paths.FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{full_path:path}")
    def spa(full_path: str):
        if full_path.startswith("api/"):
            raise HTTPException(404)
        f = paths.FRONTEND_DIST / full_path
        if full_path and f.is_file():
            return FileResponse(f)
        return FileResponse(paths.FRONTEND_DIST / "index.html")
