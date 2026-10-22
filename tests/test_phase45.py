"""Phase 4 (AI-drawn props), Phase 5 (scene editor API) and the animation-pack retargeting."""
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app import db, jobs, paths, stages  # noqa: F401  (registers the stages)
from backend.app.agent import runner
from backend.app.jobs import manager
from backend.app.main import app
from backend.app.render import assets as A
from backend.app.render import threejs as tj

READY = tj.status()["ok"]
VOS = ["A dragon guards my savings account.", "Then the dragon fell asleep and I got 19 coins."]


def test_normalize_asset_repairs_and_stands_on_the_floor():
    raw = {"name": "dragon", "height": 0.9, "parts": [
        {"shape": "sphere", "size": [0.3], "pos": [0, 0.5, 0], "color": "#00ff00"},
        {"shape": "cone", "size": [0.1, 0.3], "pos": [0.3, 0.9, 0], "color": "red", "motion": {"type": "swing", "axis": "q", "amount": 400}},
        {"shape": "teapot", "size": [1], "pos": [0, 0, 0], "color": "gold"},
        {"shape": "box", "size": [9, 9, 9], "pos": [0, -3, 0], "color": "dark"}]}
    a, fixes, errs = A.normalize_asset(raw)
    assert errs == [] and len(a["parts"]) == 3
    assert a["parts"][0]["color"] == "accent"                       # palette roles only
    assert a["parts"][1]["motion"] == {"type": "swing", "axis": "z", "amount": 90.0, "speed": 0.8}
    lows = [p["pos"][1] - A._extent(p) for p in a["parts"]]
    highs = [p["pos"][1] + A._extent(p) for p in a["parts"]]
    assert abs(min(lows)) < 1e-3 and abs(max(highs) - 0.9) < 1e-3   # on the floor, 0.9 m tall
    assert any("teapot" in f for f in fixes)
    assert A.normalize_asset({"parts": [{"shape": "blob"}]})[2] == ["the drawing has no usable parts"]


def _project(slug):
    db.upsert_project(slug, slug, {"name": slug, "niche": "x", "ratio": "9:16", "duration": 20, "platforms": ["shorts"],
                                   "theme": "dark", "style": "4"})
    root = paths.ensure_project_dirs(slug)
    for rel, obj in {"direction/phase-b.json": {"checks": [], "prompts": [{"text": "p1"}, {"text": "p2"}]},
                     "direction/phase-a.json": {"rows": [{"clip": 1, "purpose": "hook"}, {"clip": 2, "purpose": "payoff"}]},
                     "script/script.json": {"clips": [{"vo": v} for v in VOS]}}.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(json.dumps(obj))
    return root


def _settings(monkeypatch):
    real = jobs.load_settings

    def s():
        x = real()
        x["dry_run"] = False
        x["render"] = {**x["render"], "backend": "local-threejs"}
        return x
    monkeypatch.setattr(jobs, "load_settings", s)


class Artist:
    """Scene plans that ask for a new dragon prop; drawings of it."""
    def __init__(self):
        self.drawn = 0

    async def run(self, task, ctx):
        if task.name == "draw_prop":
            self.drawn += 1
            return {"name": "dragon", "height": 0.8, "parts": [
                {"shape": "capsule", "size": [0.15, 0.4], "pos": [0, 0.3, 0], "rot": [0, 0, 90], "color": "green"},
                {"shape": "sphere", "size": [0.13], "pos": [0.32, 0.45, 0], "color": "green"},
                {"shape": "wedge", "size": [0.3, 0.25, 0.02], "pos": [0, 0.55, 0], "color": "accent", "name": "wing",
                 "motion": {"type": "flap", "axis": "x", "amount": 30, "speed": 1.2}}], "notes": "a squat green dragon"}
        return {"mood": [{"t": 0, "mood": "mystery"}], "actors": [{"id": "hero", "gestures": [{"t": 1, "gesture": "point", "target": "p1"}]}],
                "props": [{"id": "p1", "type": "new", "asset": "Dragon", "describe": "small green dragon", "pos": [0.55, 0, 0.15]}],
                "camera": [{"t": 0, "shot": "medium"}], "notes": "the dragon sits beside him"}


async def test_planner_draws_new_props_once_and_redraw_updates_scenes(monkeypatch):
    _settings(monkeypatch)
    artist = Artist()
    monkeypatch.setattr(runner, "get_agent", lambda settings: artist)
    await manager.start()
    root = _project("ph4")
    job_id, fut = manager.submit("ph4", "scene_plan", {})
    assert await fut == "succeeded", db.get_job(job_id)
    assert artist.drawn == 1                                        # clip 2 reuses clip 1's drawing
    for n in (1, 2):
        s = json.loads((root / f"scenes/clip-{n:02d}.json").read_text())
        assert s["props"][0]["type"] == "custom:dragon" and "dragon" in s["assets"] and tj.validate_scene(s) == []
    assert (root / "assets/dragon.json").exists()
    index = json.loads((root / "scenes/index.json").read_text())
    assert index["1"]["props"] == ["dragon ✦"]
    if READY:
        assert (root / "assets/dragon.png").stat().st_size > 1000      # preview image rendered
    # redraw: every scene that uses it gets the new drawing
    job_id, fut = manager.submit("ph4", "draw_prop", {"key": "dragon", "describe": "a fiercer dragon"})
    assert await fut == "succeeded" and artist.drawn == 2
    logs = " ".join(l["text"] for l in db.job_logs(job_id))
    assert "updated 2 scene(s)" in logs
    await manager.stop()


def test_scene_editor_api(monkeypatch):
    _settings(monkeypatch)
    root = _project("ph5")
    c = TestClient(app)
    r = c.get("/api/projects/ph5/scenes/1").json()
    assert r["source"] == "draft" and r["scene"]["style"] == "cozy" and r["vo"] == VOS[0]
    scene = r["scene"]
    scene["actors"][0]["gestures"] = [{"t": 1, "gesture": "cheer", "dur": 2}, {"t": 3, "gesture": "moonwalk"}]
    scene["badges"] = [{"text": "500 dragons", "t_in": 1}]
    chk = c.post("/api/projects/ph5/scenes/1/check", json={"scene": scene}).json()
    assert chk["errors"] == [] and any("moonwalk" in f for f in chk["fixes"]) and any("500" in f for f in chk["fixes"])
    saved = c.put("/api/projects/ph5/scenes/1", json={"scene": scene}).json()
    assert saved["scene"]["_planned_by"] == "editor"
    on_disk = json.loads((root / "scenes/clip-01.json").read_text())
    assert [g["gesture"] for g in on_disk["actors"][0]["gestures"]] == ["cheer"] and "badges" in on_disk and not on_disk["badges"]
    assert json.loads((root / "scenes/index.json").read_text())["1"]["planned_by"] == "editor"
    assert c.get("/api/projects/ph5/scenes/1").json()["source"] == "file"
    # an undrawn "new" prop cannot be saved; a missing clip is a clear 400
    bad = {**scene, "props": [{"type": "new", "asset": "unicorn"}]}
    assert c.put("/api/projects/ph5/scenes/1", json={"scene": bad}).status_code == 400
    assert c.get("/api/projects/ph5/scenes/9").status_code == 400
    cat = c.get("/api/projects/ph5/threejs/catalog").json()
    assert "asset_shapes" in cat and "renderer" in cat
    if READY:
        pv = c.post("/api/projects/ph5/scenes/1/preview", json={"scene": scene, "t": 2.0}).json()
        assert (root / pv["image"]).stat().st_size > 2000


def test_props_library_round_trip(monkeypatch, tmp_path):
    monkeypatch.setattr(A, "LIBRARY", tmp_path / "library")
    _project("ph4lib")
    a, _, _ = A.normalize_asset({"name": "anvil", "parts": [{"shape": "box", "size": [0.4, 0.2, 0.2], "pos": [0, 0.1, 0], "color": "metal"}]})
    A.save_asset("ph4lib", "anvil", a, "ai", "a heavy anvil")
    c = TestClient(app)
    assert c.post("/api/projects/ph4lib/assets/anvil/library").status_code == 200
    _project("ph4other")
    found = {x["key"]: x for x in c.get("/api/projects/ph4other/assets").json()}
    assert found["anvil"]["where"] == "library"                     # another project can use it


@pytest.mark.skipif(not READY, reason="node + renderer build not present")
def test_drawn_prop_renders(tmp_path):
    a, _, _ = A.normalize_asset(Artist().__class__.__dict__ and {"name": "dragon", "height": 0.8, "parts": [
        {"shape": "capsule", "size": [0.15, 0.4], "pos": [0, 0.3, 0], "rot": [0, 0, 90], "color": "green"},
        {"shape": "wedge", "size": [0.3, 0.25, 0.02], "pos": [0, 0.55, 0], "color": "accent", "motion": {"type": "flap"}}]})
    import asyncio
    png = asyncio.run(tj.render_still(A.preview_scene(a, "dragon"), tmp_path / "d.png"))
    assert png and png.stat().st_size > 1500


@pytest.mark.skipif(not READY, reason="node + renderer build not present")
def test_animation_pack_retargets_exactly(tmp_path):
    """A pack with Unreal-style bone names, pack-style clip names and a 180-degree turned model must give the
    same frames as the base rig (the pack's Idle/Walk are the base rig's motions under other names)."""
    sys.path.insert(0, str(Path(__file__).parent))
    from make_test_pack import make
    pack = make(tj.RENDERER / "public/models/stickman-rig.glb", tmp_path / "pack.glb")
    scene = {"width": 120, "height": 214, "fps": 6, "duration": 3, "style": "minimal", "quality": "draft",
             "actors": [{"id": "hero", "path": [{"t": 0, "pos": [-1, 0, 0]}, {"t": 2, "pos": [0, 0, 0]}], "anim": [{"t": 0, "clip": "Idle"}]}],
             "camera": [{"t": 0, "shot": "full"}]}
    outs = []
    for extra, d in (([], "base"), (["--pack", str(pack)], "pack")):
        sp = tmp_path / f"{d}.json"                                 # the bundled pack is off for the base run
        sp.write_text(json.dumps({**scene, "pack": False} if d == "base" else scene))
        r = subprocess.run([shutil.which("node"), str(tj.RENDERER / "render.mjs"), "--scene", str(sp), "--stills", "1.0,2.5",
                            "--out-dir", str(tmp_path / d), *extra], capture_output=True, text=True, timeout=300)
        assert r.returncode == 0, r.stdout[-500:]
        info = next(json.loads(x) for x in r.stdout.splitlines() if '"info"' in x)
        if d == "pack":
            assert info["pack"]["aliases"]["Walking"] == "Walk_Loop" and info["pack"]["aliases"]["Idle"] == "Idle_Loop"
        outs.append(tmp_path / d)
    from PIL import Image, ImageChops
    for t in ("1.00", "2.50"):
        a = Image.open(outs[0] / f"still-{t}.png").convert("L")
        b = Image.open(outs[1] / f"still-{t}.png").convert("L")
        hist = ImageChops.difference(a, b).histogram()
        assert sum(hist[40:]) / sum(hist) < 0.002, t
