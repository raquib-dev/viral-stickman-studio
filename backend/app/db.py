"""SQLite job store. Content lives in project folders; this holds jobs, logs, costs, gates, the swipe
library and pipeline state. Keys are never written here (log text is redacted before insert)."""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

from . import paths
from .settings import redact

SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
  slug TEXT PRIMARY KEY, name TEXT NOT NULL, created_at REAL NOT NULL, data TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS jobs (
  id INTEGER PRIMARY KEY AUTOINCREMENT, project TEXT NOT NULL, stage TEXT NOT NULL,
  status TEXT NOT NULL, created_at REAL NOT NULL, started_at REAL, finished_at REAL,
  cost_usd REAL NOT NULL DEFAULT 0, progress REAL NOT NULL DEFAULT 0, message TEXT,
  error TEXT, params TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS jobs_project ON jobs(project, stage);
CREATE TABLE IF NOT EXISTS job_logs (
  id INTEGER PRIMARY KEY AUTOINCREMENT, job_id INTEGER NOT NULL, ts REAL NOT NULL,
  level TEXT NOT NULL, text TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS job_logs_job ON job_logs(job_id);
CREATE TABLE IF NOT EXISTS gates (
  project TEXT NOT NULL, name TEXT NOT NULL, status TEXT NOT NULL, payload_hash TEXT NOT NULL,
  payload TEXT NOT NULL, choice TEXT, note TEXT, decided_by TEXT, opened_at REAL, decided_at REAL,
  PRIMARY KEY (project, name)
);
CREATE TABLE IF NOT EXISTS swipe_items (
  id INTEGER PRIMARY KEY AUTOINCREMENT, project TEXT NOT NULL, platform TEXT NOT NULL,
  source TEXT NOT NULL, account TEXT, title TEXT, hook TEXT, url TEXT, views INTEGER,
  baseline INTEGER, multiple REAL, formula TEXT, duration REAL, synthetic INTEGER NOT NULL DEFAULT 0,
  data TEXT NOT NULL DEFAULT '{}', added_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS swipe_project ON swipe_items(project, platform);
CREATE TABLE IF NOT EXISTS pipelines (
  project TEXT PRIMARY KEY, status TEXT NOT NULL, current_stage TEXT, from_stage TEXT,
  to_stage TEXT, waiting_gate TEXT, updated_at REAL NOT NULL, message TEXT
);
"""

_lock = threading.RLock()
_conn: sqlite3.Connection | None = None


def db_path() -> Path:
    return paths.DATA / "studio.sqlite3"


def conn() -> sqlite3.Connection:
    global _conn
    with _lock:
        if _conn is None:
            paths.DATA.mkdir(parents=True, exist_ok=True)
            _conn = sqlite3.connect(db_path(), check_same_thread=False, isolation_level=None)
            _conn.row_factory = sqlite3.Row
            _conn.execute("PRAGMA journal_mode=WAL")
            _conn.execute("PRAGMA foreign_keys=ON")
            _conn.executescript(SCHEMA)
        return _conn


def reset_connection() -> None:
    """For tests: drop the cached connection so a new DATA dir takes effect."""
    global _conn
    with _lock:
        if _conn is not None:
            _conn.close()
        _conn = None


def execute(sql: str, args: tuple = ()) -> sqlite3.Cursor:
    with _lock:
        return conn().execute(sql, args)


def query(sql: str, args: tuple = ()) -> list[dict[str, Any]]:
    with _lock:
        return [dict(r) for r in conn().execute(sql, args).fetchall()]


def one(sql: str, args: tuple = ()) -> dict[str, Any] | None:
    rows = query(sql, args)
    return rows[0] if rows else None


# ---- projects -------------------------------------------------------------------------------

def upsert_project(slug: str, name: str, data: dict) -> None:
    execute("INSERT INTO projects(slug,name,created_at,data) VALUES(?,?,?,?) "
            "ON CONFLICT(slug) DO UPDATE SET name=excluded.name, data=excluded.data",
            (slug, name, time.time(), json.dumps(data)))


def get_project(slug: str) -> dict | None:
    row = one("SELECT * FROM projects WHERE slug=?", (slug,))
    if row:
        row["data"] = json.loads(row["data"])
    return row


def list_projects() -> list[dict]:
    rows = query("SELECT slug,name,created_at FROM projects ORDER BY created_at DESC")
    return rows


def delete_project(slug: str) -> None:
    for t in ("jobs", "gates", "swipe_items", "pipelines"):
        execute(f"DELETE FROM {t} WHERE project=?", (slug,))
    execute("DELETE FROM projects WHERE slug=?", (slug,))


# ---- jobs -----------------------------------------------------------------------------------

def create_job(project: str, stage: str, params: dict | None = None) -> int:
    cur = execute("INSERT INTO jobs(project,stage,status,created_at,params) VALUES(?,?,?,?,?)",
                  (project, stage, "queued", time.time(), json.dumps(params or {})))
    return int(cur.lastrowid)


def update_job(job_id: int, **fields: Any) -> None:
    if not fields:
        return
    if "message" in fields and fields["message"]:
        fields["message"] = redact(str(fields["message"]))
    if "error" in fields and fields["error"]:
        fields["error"] = redact(str(fields["error"]))
    cols = ", ".join(f"{k}=?" for k in fields)
    execute(f"UPDATE jobs SET {cols} WHERE id=?", (*fields.values(), job_id))


def add_job_cost(job_id: int, usd: float) -> None:
    execute("UPDATE jobs SET cost_usd = cost_usd + ? WHERE id=?", (float(usd), job_id))


def get_job(job_id: int) -> dict | None:
    row = one("SELECT * FROM jobs WHERE id=?", (job_id,))
    if row:
        row["params"] = json.loads(row["params"])
    return row


def list_jobs(project: str, limit: int = 200) -> list[dict]:
    rows = query("SELECT * FROM jobs WHERE project=? ORDER BY id DESC LIMIT ?", (project, limit))
    for r in rows:
        r["params"] = json.loads(r["params"])
    return rows


def latest_job(project: str, stage: str) -> dict | None:
    return one("SELECT * FROM jobs WHERE project=? AND stage=? ORDER BY id DESC LIMIT 1", (project, stage))


def add_log(job_id: int, level: str, text: str) -> dict:
    ts = time.time()
    text = redact(text)
    cur = execute("INSERT INTO job_logs(job_id,ts,level,text) VALUES(?,?,?,?)", (job_id, ts, level, text))
    return {"id": cur.lastrowid, "job_id": job_id, "ts": ts, "level": level, "text": text}


def job_logs(job_id: int, after_id: int = 0) -> list[dict]:
    return query("SELECT * FROM job_logs WHERE job_id=? AND id>? ORDER BY id", (job_id, after_id))


def mark_interrupted() -> int:
    """On startup, jobs left running by a crash become 'interrupted' (re-runnable)."""
    cur = execute("UPDATE jobs SET status='interrupted', finished_at=? WHERE status IN ('running','queued')",
                  (time.time(),))
    execute("UPDATE pipelines SET status='interrupted' WHERE status='running'")
    return cur.rowcount


def project_spend(project: str, stage_prefix: str = "") -> float:
    row = one("SELECT COALESCE(SUM(cost_usd),0) AS c FROM jobs WHERE project=? AND stage LIKE ?",
              (project, stage_prefix + "%"))
    return float(row["c"]) if row else 0.0


# ---- gates ----------------------------------------------------------------------------------

def get_gate(project: str, name: str) -> dict | None:
    row = one("SELECT * FROM gates WHERE project=? AND name=?", (project, name))
    if row:
        row["payload"] = json.loads(row["payload"])
        row["choice"] = json.loads(row["choice"]) if row["choice"] else None
    return row


def list_gates(project: str) -> list[dict]:
    rows = query("SELECT * FROM gates WHERE project=?", (project,))
    for r in rows:
        r["payload"] = json.loads(r["payload"])
        r["choice"] = json.loads(r["choice"]) if r["choice"] else None
    return rows


def put_gate(project: str, name: str, **f: Any) -> None:
    existing = one("SELECT name FROM gates WHERE project=? AND name=?", (project, name))
    if "payload" in f:
        f["payload"] = json.dumps(f["payload"])
    if "choice" in f:
        f["choice"] = json.dumps(f["choice"]) if f["choice"] is not None else None
    if existing:
        cols = ", ".join(f"{k}=?" for k in f)
        execute(f"UPDATE gates SET {cols} WHERE project=? AND name=?", (*f.values(), project, name))
    else:
        f.setdefault("payload", "{}")
        f.setdefault("payload_hash", "")
        f.setdefault("status", "pending")
        cols = ", ".join(["project", "name", *f.keys()])
        qs = ", ".join("?" * (len(f) + 2))
        execute(f"INSERT INTO gates({cols}) VALUES({qs})", (project, name, *f.values()))


# ---- swipe library --------------------------------------------------------------------------

def replace_swipe(project: str, platform: str, source: str, items: list[dict]) -> None:
    execute("DELETE FROM swipe_items WHERE project=? AND platform=? AND source=?", (project, platform, source))
    now = time.time()
    for it in items:
        execute("INSERT INTO swipe_items(project,platform,source,account,title,hook,url,views,baseline,"
                "multiple,formula,duration,synthetic,data,added_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (project, platform, source, it.get("account"), it.get("title"), it.get("hook"), it.get("url"),
                 it.get("views"), it.get("baseline"), it.get("multiple"), it.get("formula"),
                 it.get("duration"), 1 if it.get("synthetic") else 0, json.dumps(it), now))


def swipe_items(project: str) -> list[dict]:
    rows = query("SELECT * FROM swipe_items WHERE project=? ORDER BY multiple DESC", (project,))
    for r in rows:
        r["data"] = json.loads(r["data"])
        r["synthetic"] = bool(r["synthetic"])
    return rows


# ---- pipeline -------------------------------------------------------------------------------

def put_pipeline(project: str, **f: Any) -> None:
    f["updated_at"] = time.time()
    if one("SELECT project FROM pipelines WHERE project=?", (project,)):
        cols = ", ".join(f"{k}=?" for k in f)
        execute(f"UPDATE pipelines SET {cols} WHERE project=?", (*f.values(), project))
    else:
        f.setdefault("status", "idle")
        cols = ", ".join(["project", *f.keys()])
        execute(f"INSERT INTO pipelines({cols}) VALUES({', '.join('?' * (len(f) + 1))})", (project, *f.values()))


def get_pipeline(project: str) -> dict | None:
    return one("SELECT * FROM pipelines WHERE project=?", (project,))
