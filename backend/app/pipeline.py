"""Run the whole pipeline automatically, one stage after another, pausing at gates set to "pause"
and resuming when the user decides. Every stage is still a separate, re-runnable job."""
from __future__ import annotations

import asyncio
import json
import time

from . import db
from .jobs import bus, manager

PIPELINE = ["niche", "news", "discover", "patterns", "topics", "hooks", "script", "direction_a", "direction_b", "scene_plan",
            "render", "stitch", "package"]
# Learn runs on its own after you publish (it needs your retention export / insights).
ALL_STAGES = PIPELINE + ["learn"]

_tasks: dict[str, asyncio.Task] = {}
_stop: dict[str, bool] = {}


def stage_status(project: str) -> list[dict]:
    """Latest job per stage, plus staleness: a stage is stale when an earlier stage succeeded after it."""
    out, upstream_done = [], 0.0
    runs: dict[str, int] = {}
    for jj in db.list_jobs(project, 2000):
        runs[jj["stage"]] = runs.get(jj["stage"], 0) + 1
    for s in ALL_STAGES:
        j = db.latest_job(project, s)
        st = j["status"] if j else "not_run"
        finished = (j or {}).get("finished_at") or 0.0
        stale = bool(j and st == "succeeded" and s != "learn" and upstream_done > finished + 1e-6)
        out.append({"stage": s, "status": "stale" if stale else st, "job_id": j and j["id"],
                    "progress": j and j["progress"], "message": j and j["message"], "cost_usd": j and j["cost_usd"],
                    "finished_at": finished or None, "error": j and j["error"], "started_at": j and j["started_at"],
                    "runs": runs.get(s, 0)})
        if s != "learn" and j and st == "succeeded":
            upstream_done = max(upstream_done, finished)
    return out


def next_needed(project: str) -> str:
    for row in stage_status(project):
        if row["stage"] in PIPELINE and row["status"] != "succeeded":
            return row["stage"]
    return PIPELINE[-1]


def is_running(project: str) -> bool:
    t = _tasks.get(project)
    return bool(t and not t.done())


def start(project: str, from_stage: str | None = None, to_stage: str | None = None) -> dict:
    if is_running(project):
        raise RuntimeError("pipeline already running for this project")
    first = from_stage or next_needed(project)
    if first not in PIPELINE:
        raise ValueError(f"unknown stage {first}")
    last = to_stage or PIPELINE[-1]
    _stop[project] = False
    db.put_pipeline(project, status="running", current_stage=first, from_stage=first, to_stage=last,
                    waiting_gate=None, message="")
    _tasks[project] = asyncio.create_task(_run(project, first, last))
    return db.get_pipeline(project)


def stop(project: str) -> None:
    _stop[project] = True
    p = db.get_pipeline(project)
    if p and p["current_stage"]:
        j = db.latest_job(project, p["current_stage"])
        if j and j["status"] in ("queued", "running"):
            manager.cancel(j["id"])


def resume_after_gate(project: str, gate: str | None = None) -> dict | None:
    """Called when a gate is approved. A job started on its own (Run stage, Regenerate this clip) that
    stopped at the gate is re-queued with its original params; otherwise, if the pipeline paused there,
    it continues from that stage."""
    from .gates import GATE_STAGE
    stage_name = GATE_STAGE.get(gate or "")
    j = db.latest_job(project, stage_name) if stage_name else None
    if j and j["status"] == "waiting_gate" and json.loads(j["params"] or "{}").get("via") != "pipeline":
        db.update_job(j["id"], status="resumed", finished_at=time.time())
        job_id, _ = manager.submit(project, stage_name, json.loads(j["params"] or "{}"))
        return {"resubmitted_job": job_id}
    p = db.get_pipeline(project)
    if p and p["status"] == "waiting_gate" and not is_running(project):
        return start(project, p["current_stage"], p["to_stage"])
    return None


async def _run(project: str, first: str, last: str) -> None:
    stages = PIPELINE[PIPELINE.index(first): PIPELINE.index(last) + 1]
    for s in stages:
        if _stop.get(project):
            _set(project, status="stopped", current_stage=s, message="stopped by you")
            return
        _set(project, status="running", current_stage=s, waiting_gate=None, message=f"running {s}")
        _job_id, fut = manager.submit(project, s, {"via": "pipeline"})
        result = await fut
        if result == "waiting_gate":
            gate = _pending_gate(project)
            _set(project, status="waiting_gate", current_stage=s, waiting_gate=gate,
                 message=f"waiting for your decision: {gate}")
            return
        if result != "succeeded":
            _set(project, status="failed" if result == "failed" else result, current_stage=s,
                 message=f"{s} {result}")
            return
    _set(project, status="completed", current_stage=last, message="pipeline finished")


def _pending_gate(project: str) -> str | None:
    rows = [g for g in db.list_gates(project) if g["status"] == "pending"]
    rows.sort(key=lambda g: g.get("opened_at") or 0, reverse=True)
    return rows[0]["name"] if rows else None


def _set(project: str, **f) -> None:
    db.put_pipeline(project, **f)
    bus.publish(project, {"type": "pipeline", **(db.get_pipeline(project) or {})})
