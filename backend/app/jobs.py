"""Jobs: persisted in SQLite, executed by an in-process asyncio worker pool with two lanes, streamed to
the UI over SSE. Every log line passes through settings.redact before it is stored or broadcast."""
from __future__ import annotations

import asyncio
import json
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable

from . import db, paths
from .settings import load_settings, redact


class GatePending(Exception):
    def __init__(self, gate: str):
        super().__init__(f"waiting for gate: {gate}")
        self.gate = gate


class JobCancelled(Exception):
    pass


class StageError(Exception):
    """A stage failed for a reason worth showing the user verbatim."""


# ---- event bus ------------------------------------------------------------------------------

class EventBus:
    def __init__(self) -> None:
        self._subs: dict[str, set[asyncio.Queue]] = {}
        self._loop: asyncio.AbstractEventLoop | None = None

    def bind(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def subscribe(self, project: str) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=2000)
        self._subs.setdefault(project, set()).add(q)
        return q

    def unsubscribe(self, project: str, q: asyncio.Queue) -> None:
        self._subs.get(project, set()).discard(q)

    def publish(self, project: str, event: dict) -> None:
        event = {**event, "ts": time.time()}
        for q in list(self._subs.get(project, ())):
            def put(q=q):
                try:
                    q.put_nowait(event)
                except asyncio.QueueFull:
                    pass
            if self._loop and self._loop.is_running():
                self._loop.call_soon_threadsafe(put)
            else:
                put()


bus = EventBus()


# ---- stage registry -------------------------------------------------------------------------

StageFn = Callable[["JobContext"], Awaitable[dict | None]]


@dataclass
class StageDef:
    name: str
    title: str
    fn: StageFn
    lane: str = "general"
    description: str = ""
    skills: list[str] = field(default_factory=list)
    tools: list[str] = field(default_factory=list)


REGISTRY: dict[str, StageDef] = {}


def stage(name: str, title: str, lane: str = "general", description: str = "",
          skills: list[str] | None = None, tools: list[str] | None = None):
    def deco(fn: StageFn) -> StageFn:
        REGISTRY[name] = StageDef(name, title, fn, lane, description, skills or [], tools or [])
        return fn
    return deco


# ---- job context ----------------------------------------------------------------------------

class JobContext:
    def __init__(self, job_id: int, project: str, stage: str, params: dict):
        self.job_id = job_id
        self.project = project
        self.stage = stage
        self.params = params
        self.settings = load_settings()
        self.root = paths.ensure_project_dirs(project)
        self._cancel = False
        self._agent = None

    # -- logging / progress
    def log(self, text: str, level: str = "info") -> None:
        row = db.add_log(self.job_id, level, str(text))
        bus.publish(self.project, {"type": "log", "job_id": self.job_id, "stage": self.stage, **row})

    def progress(self, frac: float, message: str = "") -> None:
        frac = max(0.0, min(1.0, frac))
        db.update_job(self.job_id, progress=frac, message=message)
        bus.publish(self.project, {"type": "progress", "job_id": self.job_id, "stage": self.stage,
                                   "progress": frac, "message": redact(message)})

    def add_cost(self, usd: float, what: str = "") -> None:
        if usd:
            db.add_job_cost(self.job_id, usd)
            self.log(f"cost +${usd:.4f}" + (f" ({what})" if what else ""))
            bus.publish(self.project, {"type": "cost", "job_id": self.job_id, "stage": self.stage, "usd": usd})

    def check_cancelled(self) -> None:
        if self._cancel:
            raise JobCancelled()

    # -- files
    @property
    def dry_run(self) -> bool:
        return bool(self.settings.get("dry_run", True))

    def path(self, rel: str) -> Path:
        return paths.safe_project_path(self.project, rel)

    def read_json(self, rel: str, default: Any = None) -> Any:
        p = self.path(rel)
        if not p.exists():
            if default is not None:
                return default
            raise StageError(f"missing input {rel}: run the earlier stage first")
        return json.loads(p.read_text(encoding="utf-8"))

    def write_json(self, rel: str, data: Any) -> Path:
        p = self.path(rel)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return p

    def read_text(self, rel: str) -> str:
        p = self.path(rel)
        if not p.exists():
            raise StageError(f"missing input {rel}: run the earlier stage first")
        return p.read_text(encoding="utf-8")

    def write_text(self, rel: str, text: str) -> Path:
        p = self.path(rel)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8", newline="\n")
        return p

    def project_data(self) -> dict:
        proj = db.get_project(self.project)
        if not proj:
            raise StageError(f"unknown project {self.project}")
        return proj["data"]

    # -- agent and gates
    @property
    def agent(self):
        if self._agent is None:
            from .agent.runner import get_agent
            self._agent = get_agent(self.settings)
        return self._agent

    def require_gate(self, name: str, payload: Any, options: list | None = None,
                     default_choice: Any = None, auto_allowed: bool = True, auto_reason: str = "") -> Any:
        from .gates import require
        return require(self, name, payload, options, default_choice, auto_allowed, auto_reason)


# ---- worker pool ----------------------------------------------------------------------------

class JobManager:
    LANES = {"general": 2, "render": 1}

    def __init__(self) -> None:
        self._queues: dict[str, asyncio.Queue] = {}
        self._futures: dict[int, asyncio.Future] = {}
        self._contexts: dict[int, JobContext] = {}
        self._workers: list[asyncio.Task] = []
        self.started = False

    async def start(self) -> None:
        if self.started:
            return
        bus.bind(asyncio.get_running_loop())
        n = db.mark_interrupted()
        if n:
            print(f"[jobs] marked {n} unfinished job(s) as interrupted")
        for lane, conc in self.LANES.items():
            self._queues[lane] = asyncio.Queue()
            for _ in range(conc):
                self._workers.append(asyncio.create_task(self._worker(lane)))
        self.started = True

    async def stop(self) -> None:
        for w in self._workers:
            w.cancel()
        self._workers.clear()
        self.started = False

    def submit(self, project: str, stage_name: str, params: dict | None = None) -> tuple[int, asyncio.Future]:
        if stage_name not in REGISTRY:
            raise KeyError(f"unknown stage {stage_name}")
        job_id = db.create_job(project, stage_name, params)
        fut: asyncio.Future = asyncio.get_running_loop().create_future()
        self._futures[job_id] = fut
        self._queues[REGISTRY[stage_name].lane].put_nowait(job_id)
        bus.publish(project, {"type": "job", "job_id": job_id, "stage": stage_name, "status": "queued"})
        return job_id, fut

    def cancel(self, job_id: int) -> bool:
        ctx = self._contexts.get(job_id)
        if ctx:
            ctx._cancel = True
            return True
        job = db.get_job(job_id)
        if job and job["status"] == "queued":
            db.update_job(job_id, status="cancelled", finished_at=time.time())
            return True
        return False

    async def _worker(self, lane: str) -> None:
        q = self._queues[lane]
        while True:
            job_id = await q.get()
            try:
                await self._run(job_id)
            finally:
                q.task_done()

    async def _run(self, job_id: int) -> None:
        job = db.get_job(job_id)
        fut = self._futures.pop(job_id, None)
        if not job or job["status"] == "cancelled":
            if fut and not fut.done():
                fut.set_result("cancelled")
            return
        sd = REGISTRY[job["stage"]]
        ctx = JobContext(job_id, job["project"], job["stage"], job["params"])
        self._contexts[job_id] = ctx
        db.update_job(job_id, status="running", started_at=time.time(), progress=0.0)
        bus.publish(job["project"], {"type": "job", "job_id": job_id, "stage": sd.name, "status": "running"})
        status, error = "succeeded", None
        try:
            ctx.log(f"start {sd.title}" + (" (dry run)" if ctx.dry_run else ""))
            result = await sd.fn(ctx)
            if result:
                ctx.log("outputs: " + ", ".join(result.get("outputs", [])) if result.get("outputs") else "done")
            ctx.progress(1.0, "done")
        except GatePending as g:
            status = "waiting_gate"
            ctx.log(f"waiting for your decision at gate '{g.gate}'", "gate")
        except JobCancelled:
            status = "cancelled"
            ctx.log("cancelled", "warn")
        except StageError as e:
            status, error = "failed", str(e)
            ctx.log(f"failed: {e}", "error")
        except Exception as e:  # keep the worker alive; full trace goes to the job log
            status, error = "failed", f"{type(e).__name__}: {e}"
            ctx.log("failed: " + redact(traceback.format_exc()[-2000:]), "error")
        finally:
            self._contexts.pop(job_id, None)
        db.update_job(job_id, status=status, finished_at=time.time(), error=error)
        bus.publish(job["project"], {"type": "job", "job_id": job_id, "stage": sd.name, "status": status,
                                     "error": redact(error or "")})
        if fut and not fut.done():
            fut.set_result(status)


manager = JobManager()
