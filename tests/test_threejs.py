"""local-threejs: the keyword scene planner, scene validation, lip-sync envelope, and (when Node and the
renderer build are present) a tiny real render through the headless browser."""
import json
import shutil
import wave
from pathlib import Path

import pytest

from backend.app.render import threejs as tj
from backend.app.render.base import ClipSpec
from backend.app.render.media import probe

READY = tj.status()["ok"]


def _clip(i=0, vo="Wait. Nineteen files changed for one blue button?", label="hook", **kw):
    return ClipSpec(i, "prompt", "9:16", "360p", 10.0, label=label, vo=vo, **kw)


def test_auto_scene_picks_gesture_face_and_keeps_numbers_verbatim():
    s = tj.auto_scene(_clip(vo="Wait, it made 19 files and $500 of changes? That's wrong."), {"fps": 24}, (0.4, 6.0))
    a = s["actors"][0]
    assert [k["clip"] for k in a["anim"]] == ["Idle", "No"]
    assert a["face"][0]["expr"] == "surprised"
    assert s["badges"][0]["text"] == "19 files"            # only words the voiceover says
    assert (s["width"], s["height"]) == (360, 640) and s["duration"] == 10.0
    assert tj.validate_scene(s) == []


def test_auto_scene_no_badge_without_a_number():
    s = tj.auto_scene(_clip(i=2, vo="Most people think saving is about willpower."), {}, (0.4, 5.0))
    assert "badges" not in s and s["actors"][0]["face"][0]["expr"] == "thinking"
    assert s["theme"] == "dark" and s["style"] == "minimal"


def test_validate_scene_rejects_unknown_names():
    bad = {"camera": [{"t": 0}], "actors": [{"anim": [{"t": 0, "clip": "Moonwalk"}], "face": [{"t": 0, "expr": "smug"}]}]}
    errs = tj.validate_scene(bad)
    assert "unknown clip 'Moonwalk'" in errs and "unknown expression 'smug'" in errs


def test_mouth_envelope_follows_speech(tmp_path):
    import numpy as np
    rate = 24000
    t = np.arange(int(rate * 2.0)) / rate
    sig = np.where(t < 1.0, 0.5 * np.sin(2 * np.pi * 220 * t), 0.0).astype("float32")
    f = tmp_path / "v.wav"
    with wave.open(str(f), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate)
        w.writeframes((sig * 32767).astype("<i2").tobytes())
    env = tj.mouth_envelope(f, fps=10, lead=0.5, tempo=1.0, duration=3.0)
    assert len(env) == 30
    assert max(env[:5]) == 0                        # before the voice starts
    assert min(env[6:14]) > 0.5                     # speaking
    assert max(env[16:]) == 0                       # after it ends


@pytest.mark.skipif(not READY, reason="node + renderer build not present (cd renderer; npm install; npm run build)")
def test_real_render_is_exact_and_deterministic(tmp_path):
    import subprocess
    scene = json.loads((tj.RENDERER / "scenes" / "demo.json").read_text())
    scene.update(width=90, height=160, fps=6, duration=1.0, quality="draft")
    sp = tmp_path / "s.json"
    sp.write_text(json.dumps(scene))
    outs = []
    for k in (1, 2):
        out = tmp_path / f"o{k}.mp4"
        r = subprocess.run([shutil.which("node"), str(tj.RENDERER / "render.mjs"), "--scene", str(sp), "--out", str(out)],
                           capture_output=True, text=True, timeout=300)
        assert r.returncode == 0, r.stdout + r.stderr
        outs.append(out)
    info = probe(outs[0])
    assert (info["width"], info["height"]) == (90, 160) and abs(info["duration"] - 1.0) < 0.05
    # rule 2: same scene, same frames
    frames = [subprocess.run(["ffmpeg", "-v", "error", "-i", str(o), "-f", "rawvideo", "-pix_fmt", "gray", "-"],
                             capture_output=True).stdout for o in outs]
    assert frames[0] == frames[1] and len(frames[0]) == 90 * 160 * 6


def test_style_follows_project_or_setting():
    c = _clip(style="4")
    assert tj.auto_scene(c, {}, (0.4, 5))["style"] == "cozy"
    assert tj.auto_scene(c, {"style": "historic"}, (0.4, 5))["style"] == "historic"
    assert tj.auto_scene(_clip(style="2B"), {}, (0.4, 5))["style"] == "cinematic"


def test_mood_follows_content_and_turns_mid_line():
    c = _clip(i=1, vo="Everyone said saving money was boring. But compound growth wins in the end.")
    moods = tj.auto_scene(c, {}, (0.4, 8.4))["mood"]
    assert [m["mood"] for m in moods] == ["money", "success"]
    assert 0.4 < moods[1]["t"] < 8.4                       # changes where the line turns
    assert tj.auto_scene(c, {"mood": "off"}, (0.4, 8))["mood"] == [{"t": 0, "mood": "neutral"}]
    assert tj.auto_scene(c, {"mood": "calm"}, (0.4, 8))["mood"] == [{"t": 0, "mood": "calm"}]


def test_props_gestures_hat_and_second_character():
    s = tj.auto_scene(_clip(i=1, vo="The king checked his phone. They laughed at him.", style="5"), {}, (0.4, 6))
    hero = s["actors"][0]
    assert hero["hat"] == "crown"
    assert s["props"][0]["type"] == "phone" and s["props"][0]["hold"]["actor"] == "hero"
    assert any(g["gesture"] == "hold" for g in hero["gestures"])
    assert len(s["actors"]) == 2 and any(k["at"] == "other" for k in hero["look"])
    assert s["camera"][0]["shot"]["type"] == "two_shot"
    assert tj.validate_scene(s) == []


def test_first_and_last_clip_transitions():
    assert tj.auto_scene(_clip(i=0, count=3), {}, (0.4, 5))["transition"] == {"in": "fade", "out": "none"}
    assert tj.auto_scene(_clip(i=2, count=3), {}, (0.4, 5))["transition"] == {"in": "none", "out": "fade"}


def test_validate_scene_checks_every_name():
    bad = {"style": "baroque", "mood": [{"t": 0, "mood": "ecstatic"}], "camera": [{"t": 0, "shot": "dolly_zoom"}],
           "actors": [{"id": "hero", "gestures": [{"t": 0, "gesture": "moonwalk"}, {"t": 1, "gesture": "point", "target": "ghost"}], "hat": "fez"}],
           "props": [{"type": "unicorn"}], "transition": {"in": "spin"}}
    errs = " ".join(tj.validate_scene(bad))
    for word in ("baroque", "ecstatic", "dolly_zoom", "moonwalk", "ghost", "fez", "unicorn", "spin"):
        assert word in errs, word


@pytest.mark.skipif(not READY, reason="node + renderer build not present")
def test_catalog_matches_the_built_renderer():
    import subprocess
    r = subprocess.run([shutil.which("node"), str(tj.RENDERER / "render.mjs"), "--catalog"], capture_output=True, text=True, timeout=120)
    ev = json.loads(r.stdout.strip().splitlines()[-1])
    for k, v in ev["live"].items():
        assert sorted(v) == sorted(tj.CATALOG[k]), k


@pytest.mark.skipif(not READY, reason="node + renderer build not present")
def test_every_style_renders(tmp_path):
    import subprocess
    lines = {"1": "Saving money is boring. But compound growth wins.", "2A": "My boss wanted one button. They got 19 files.",
             "2B": "Nobody knows the secret behind this.", "3": "The caveman found fire by mistake.",
             "4": "Every morning I make coffee and read.", "5": "The king lost the war in 1648."}
    for k, (style, vo) in enumerate(lines.items()):
        scene = tj.auto_scene(_clip(i=k, vo=vo, style=style, count=6), {"quality": "draft"}, (0.4, 2.5))
        scene.update(width=90, height=160, fps=4, duration=3.0)
        assert tj.validate_scene(scene) == [], style
        sp = tmp_path / f"{style}.json"
        sp.write_text(json.dumps(scene))
        r = subprocess.run([shutil.which("node"), str(tj.RENDERER / "render.mjs"), "--scene", str(sp), "--stills", "2.0",
                            "--out-dir", str(tmp_path / style)], capture_output=True, text=True, timeout=300)
        events = [json.loads(x) for x in r.stdout.splitlines() if x.startswith("{")]
        assert r.returncode == 0 and not [e for e in events if "error" in e["event"]], (style, r.stdout[-800:])
        png = (tmp_path / style / "still-2.00.png").read_bytes()
        assert len(png) > 2000, style                       # not a blank frame
