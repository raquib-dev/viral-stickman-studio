"""Regenerating a clip: the paid cost gate must restart the stopped job once approved, and a failure
outside RenderError (download, ffprobe) must be retried and recorded instead of leaving the clip stuck."""
import asyncio
import json

from backend.app import db, gates, jobs, paths, pipeline
from backend.app.jobs import manager
from backend.app.render.mock import MockBackend
from backend.app.stages import production

N_CLIPS = 3
_sleep = asyncio.sleep  # the retry test patches asyncio.sleep (one module object) to skip backoff


def _project(slug: str) -> None:
    data = {"name": slug, "niche": "test", "ratio": "9:16", "duration": N_CLIPS * 10, "platforms": ["shorts"]}
    db.upsert_project(slug, slug, data)
    root = paths.ensure_project_dirs(slug)
    for rel, obj in {
        "direction/phase-b.json": {"checks": [], "prompts": [{"text": f"stickman clip {k}"} for k in range(N_CLIPS)]},
        "direction/phase-a.json": {"rows": [{"purpose": f"beat {k}"} for k in range(N_CLIPS)]},
        "script/script.json": {"clips": [{"vo": f"line {k}"} for k in range(N_CLIPS)]},
    }.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(json.dumps(obj))


async def _wait(job_id: int, timeout: float = 60) -> dict:
    for _ in range(int(timeout * 10)):
        j = db.get_job(job_id)
        if j["status"] not in ("queued", "running"):
            return j
        await _sleep(0.1)
    raise AssertionError(f"job {job_id} did not finish")


def _paid_settings(monkeypatch):
    real = jobs.load_settings

    def settings():
        s = real()
        s["gates"] = {**s["gates"], "render_cost": "pause"}
        s["render"] = {**s["render"], "max_retries": 1}
        return s
    monkeypatch.setattr(jobs, "load_settings", settings)
    monkeypatch.setattr(production, "load_pricing", lambda: {"mock": {"720p": 0.01}, "retry_allowance": 0.25})


async def test_regenerate_resumes_after_cost_gate(monkeypatch):
    _paid_settings(monkeypatch)
    await manager.start()
    slug = "regen-gate"
    _project(slug)
    job_id, _ = manager.submit(slug, "render", {"only": [N_CLIPS], "force": True})
    assert (await _wait(job_id))["status"] == "waiting_gate"
    assert db.get_gate(slug, "render_cost")["status"] == "pending"

    gates.decide(slug, "render_cost", "approve")
    resumed = pipeline.resume_after_gate(slug, "render_cost")
    assert resumed and resumed["resubmitted_job"] != job_id
    assert db.get_job(job_id)["status"] == "resumed"
    assert (await _wait(resumed["resubmitted_job"]))["status"] == "succeeded"
    meta = json.loads((paths.project_dir(slug) / f"clips/clip-{N_CLIPS:02d}.json").read_text())
    assert meta["status"] == "done"
    await manager.stop()


async def test_unexpected_backend_error_is_retried_then_recorded(monkeypatch):
    monkeypatch.setattr(production.asyncio, "sleep", lambda *_: _sleep(0))
    calls = {"n": 0}

    class Flaky(MockBackend):
        async def render_clip(self, clip, prev, log):
            calls["n"] += 1
            if calls["n"] == 1:
                raise OSError("connection reset during download")
            return await super().render_clip(clip, prev, log)

    class Broken(MockBackend):
        async def render_clip(self, clip, prev, log):
            raise OSError("connection reset during download")

    await manager.start()
    slug = "regen-flaky"
    _project(slug)
    monkeypatch.setattr(production, "get_backend", lambda name: Flaky())
    j = await _wait(manager.submit(slug, "render", {"only": [1], "force": True})[0])
    assert j["status"] == "succeeded" and calls["n"] == 2

    monkeypatch.setattr(production, "get_backend", lambda name: Broken())
    j = await _wait(manager.submit(slug, "render", {"only": [2], "force": True})[0])
    assert j["status"] == "failed" and "connection reset" in j["error"]
    meta = json.loads((paths.project_dir(slug) / "clips/clip-02.json").read_text())
    assert meta["status"] == "failed" and "connection reset" in meta["error"]
    await manager.stop()
