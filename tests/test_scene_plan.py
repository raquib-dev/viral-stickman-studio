"""Phase 3: the AI scene planner (scene_plan stage) and the checker that makes AI plans safe to render."""
import json

from backend.app import db, jobs, paths, stages  # noqa: F401  (registers the stages)
from backend.app.agent import runner
from backend.app.agent.runner import AgentError
from backend.app.jobs import manager
from backend.app.render import threejs as tj

VOS = ["Wait. My boss asked for one blue button?", "But the AI changed 19 files and broke the database."]


def test_check_and_repair_makes_any_plan_safe():
    messy = {
        "style": "baroque", "mood": "ecstatic",
        "actors": [{"anim": [{"t": -2, "clip": "Moonwalk"}], "face": [{"t": 3, "expr": "smug"}], "hat": "fez",
                    "gestures": [{"t": 1, "gesture": "dab"}, {"t": 2, "gesture": "point", "target": "ghost"}],
                    "look": [{"t": 1, "at": "nobody"}], "position": [9, 3, 9]}],
        "props": [{"type": "unicorn"}, {"type": "coins", "pos": [5, 9, -9]}, {"type": "clock"}, {"type": "mug"}, {"type": "phone"}],
        "badges": [{"text": "93% of people", "t_in": 99}, {"text": "19 files", "t_in": 1}],
        "panels": [{"kind": "note", "title": "Facts", "lines": ["Costs $4,000 a year"]},
                   {"title": "db/client.ts", "lines": ["const retries = 3;"]}],
        "camera": [{"t": 2, "shot": "dolly_zoom"}], "transition": {"in": "spin"},
    }
    s, fixes, errs = tj.check_and_repair(messy, VOS[1], 10.0)
    assert errs == []
    assert s["style"] == "minimal" and s["mood"] == [{"t": 0, "mood": "neutral"}]
    hero = s["actors"][0]
    assert hero["id"] == "hero" and hero["anim"][0] == {"t": 0.0, "clip": "Idle"} and "hat" not in hero
    assert [g["gesture"] for g in hero["gestures"]] == ["point"] and "target" not in hero["gestures"][0]
    assert hero["position"] == [1.2, 0, 1] and hero["look"][0]["at"] == "camera"
    assert [p["type"] for p in s["props"]] == ["coins", "clock"]          # trimmed to 3, unknown dropped
    assert s["props"][0]["pos"] == [1.2, 2.4, -2.5]
    assert [b["text"] for b in s["badges"]] == ["19 files"]               # "93%" is not in the voiceover
    assert [p["title"] for p in s["panels"]] == ["db/client.ts"]          # "$4,000" note removed, code kept
    assert s["camera"][0]["shot"]["type"] == "medium" and s["transition"]["in"] == "none"
    assert any("93" in f for f in fixes) and any("dolly_zoom" in f for f in fixes)


def _project(slug, backend="local-threejs"):
    db.upsert_project(slug, slug, {"name": slug, "niche": "x", "ratio": "9:16", "duration": 20, "platforms": ["shorts"],
                                   "theme": "dark", "style": "2A"})
    root = paths.ensure_project_dirs(slug)
    for rel, obj in {"direction/phase-b.json": {"checks": [], "prompts": [{"text": "p1"}, {"text": "p2"}]},
                     "direction/phase-a.json": {"rows": [{"clip": 1, "purpose": "hook", "scene": "a man frowns at a screen"},
                                                         {"clip": 2, "purpose": "problem", "scene": "files pile up"}]},
                     "script/script.json": {"clips": [{"vo": v} for v in VOS]}}.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(json.dumps(obj))
    return root


def _settings(monkeypatch, backend="local-threejs", dry=False):
    real = jobs.load_settings

    def s():
        x = real()
        x["dry_run"] = dry
        x["render"] = {**x["render"], "backend": backend}
        return x
    monkeypatch.setattr(jobs, "load_settings", s)


class FakeAgent:
    """Returns an AI-style plan with a few mistakes for the checker to repair, or fails."""
    def __init__(self, mode="ok"):
        self.mode, self.calls = mode, []

    async def run(self, task, ctx):
        self.calls.append(task)
        if self.mode == "fail":
            raise AgentError("model unreachable")
        assert "Use ONLY these names" in task.prompt and "DRAFT" in task.prompt
        return {"mood": [{"t": 0, "mood": "tech"}, {"t": 3.1, "mood": "danger"}],
                "actors": [{"id": "hero", "gestures": [{"t": 1.2, "gesture": "facepalm"}, {"t": 2, "gesture": "teleport"}],
                            "face": [{"t": 0, "expr": "surprised"}]}],
                "props": [{"id": "p1", "type": "monitor", "pos": [0.6, 0, 0.1]}],
                "badges": [{"text": "19 files", "t_in": 2.0}, {"text": "99 bugs", "t_in": 3}],
                "camera": [{"t": 0, "shot": {"type": "wide", "target": "hero"}}, {"t": 5, "shot": "closeup"}],
                "notes": "Reveal the pile of files, then punch in on his reaction."}


async def _run(slug, params=None):
    job_id, fut = manager.submit(slug, "scene_plan", params or {})
    status = await fut
    return status, db.get_job(job_id)


async def test_stage_writes_checked_ai_plans(monkeypatch):
    _settings(monkeypatch)
    agent = FakeAgent()
    monkeypatch.setattr(runner, "get_agent", lambda settings: agent)
    await manager.start()
    root = _project("plan-ai")
    status, job = await _run("plan-ai")
    assert status == "succeeded", job
    s2 = json.loads((root / "scenes/clip-02.json").read_text())
    assert s2["_planned_by"] == "ai" and s2["style"] == "modern"
    assert [m["mood"] for m in s2["mood"]] == ["tech", "danger"]
    assert [g["gesture"] for g in s2["actors"][0]["gestures"]] == ["facepalm"]
    assert [b["text"] for b in s2["badges"]] == ["19 files"]
    assert any("teleport" in f for f in s2["_fixes"]) and any("99" in f for f in s2["_fixes"])
    assert tj.validate_scene(s2) == []
    index = json.loads((root / "scenes/index.json").read_text())
    assert index["2"]["notes"].startswith("Reveal") and index["2"]["shots"] == ["wide", "closeup"]
    # unchanged inputs: nothing is re-planned
    n = len(agent.calls)
    assert (await _run("plan-ai"))[0] == "succeeded" and len(agent.calls) == n
    # re-plan one clip on request
    await _run("plan-ai", {"only": [1], "force": True})
    assert len(agent.calls) == n + 1
    await manager.stop()


async def test_hand_edited_plans_are_kept_and_failures_fall_back(monkeypatch):
    _settings(monkeypatch)
    monkeypatch.setattr(runner, "get_agent", lambda settings: FakeAgent("fail"))
    await manager.start()
    root = _project("plan-fallback")
    (root / "scenes").mkdir(exist_ok=True)
    mine = {"style": "cozy", "camera": [{"t": 0, "shot": "medium"}], "actors": [{"id": "hero"}]}
    (root / "scenes/clip-01.json").write_text(json.dumps(mine))
    status, job = await _run("plan-fallback")
    assert status == "succeeded"
    assert json.loads((root / "scenes/clip-01.json").read_text()) == mine          # never overwritten
    s2 = json.loads((root / "scenes/clip-02.json").read_text())
    assert s2["_planned_by"] == "keywords" and tj.validate_scene(s2) == []
    logs = " ".join(l["text"] for l in db.job_logs(job["id"]))
    assert "keeping your edited" in logs and "using the keyword plan" in logs
    await manager.stop()


async def test_skips_for_other_backends_and_dry_run_uses_fixture(monkeypatch):
    _settings(monkeypatch, backend="omni-fal")
    await manager.start()
    root = _project("plan-skip")
    assert (await _run("plan-skip"))[0] == "succeeded" and not (root / "scenes/index.json").exists()
    _settings(monkeypatch, backend="local-threejs", dry=True)
    assert (await _run("plan-skip"))[0] == "succeeded"
    s1 = json.loads((root / "scenes/clip-01.json").read_text())
    assert s1["_planned_by"] == "fixture (dry run)" and tj.validate_scene(s1) == []
    await manager.stop()


def test_repair_survives_stringly_typed_model_output():
    """Claude's structured output once sent numbers as strings and `hold` as a bare actor id; that crashed the stage."""
    from backend.app.render import threejs as tj
    raw = {"version": "2", "width": "720", "height": "1280", "fps": "30", "duration": "10.0", "style": "cozy", "theme": "dark",
           "mood": [{"t": "0", "mood": "money"}],
           "actors": [{"id": "hero", "gestures": [{"t": "1.5", "gesture": "point", "dur": "2", "target": "p1"}],
                       "path": '[{"t": 0, "pos": ["-1", 0, "0"]}]', "anim": ["Idle"]}],
           "props": [{"id": "p1", "type": "mug", "hold": "hero", "t_in": "0.5"}, {"id": "p2", "type": "mug", "hold": "R"}, "coin"],
           "badges": [{"text": "19", "t_in": "2"}], "camera": [{"t": "0", "shot": "medium"}]}
    s, fixes, errs = tj.check_and_repair(raw, "I saved 19 coins.", 10.0, True)
    assert errs == []
    assert s["props"][0]["hold"] == {"actor": "hero"} and s["props"][1]["hold"] == {"hand": "R", "actor": "hero"}
    assert len(s["props"]) == 2 and s["props"][0]["t_in"] == 0.5
    g = s["actors"][0]["gestures"][0]
    assert g["t"] == 1.5 and g["dur"] == 2.0 and g["target"] == "p1"
    assert s["actors"][0]["path"][0]["pos"] == [-1.0, 0.0, 0.0] and s["actors"][0]["anim"] == []
    assert s["badges"][0]["text"] == "19"                            # on-screen text stays text
    assert any("malformed" in f for f in fixes)
