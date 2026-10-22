"""Dialogue shorts: cast, the genre checker, clip grouping, the shot plan, voice timing, the renderer scene,
line captions, the sound bed, the whole dry-run pipeline, and a real three.js dialogue render."""
import json
import shutil
import subprocess
import wave

import pytest

from backend.app import dialogue as d
from backend.app import stages  # noqa: F401  (registers the stages)
from backend.app.agent import fixtures
from backend.app.render import captions as cap
from backend.app.render import stitch as st
from backend.app.render import threejs as tj
from backend.app.render import tts
from backend.app.settings import ffmpeg_bin

READY = tj.status()["ok"]
CAST = d.cast_for({})
HOOK = "Claude. The client said it's great."


def L(*pairs):
    return [{"speaker": s, "text": t} for s, t in pairs]


GOOD = {"title": "she said no sixty-one times. that's the job. what's the pettiest thing you've made your ai redo?",
        "turn": 12, "button": 16, "lines": L(
            ("a", HOOK), ("b", "That's great!"), ("a", "I didn't build it. You did."), ("b", "I wrote four thousand lines."),
            ("a", "...They were bad."), ("a", "I just said no a lot."), ("b", "Sixty-one times."), ("a", "You counted?"),
            ("b", "You said it very clearly."), ("a", "Anyone can say no."), ("b", "I can't. I say yes."), ("b", "Knowing that is the job."),
            ("a", "...Okay. It's good."), ("b", "It's great!"), ("a", "The footer's two pixels off."), ("b", "It's 1 AM."),
            ("a", "Two pixels, Claude."))}


def test_cast_defaults_merge_and_repair():
    c = d.cast_for({"cast": {"a": {"name": "Zoe", "appearance": {"hair": "#ff0000"}}, "b": {"kind": "dragon", "voice": "robot"}}})
    assert c["a"]["name"] == "Zoe" and c["a"]["appearance"]["hair"] == "#ff0000" and c["a"]["appearance"]["glasses"] == "round"
    assert c["b"]["kind"] == "mascot" and c["b"]["voice"] == "mascot" and c["b"]["name"] == "Claude"
    assert d.DEFAULT_CAST["a"]["name"] == "Mia"                         # defaults are never mutated


def test_good_script_passes_and_each_rule_is_checked():
    assert d.dialogue_flags(GOOD, CAST, HOOK, 60, 150) == []
    bad = {**GOOD, "title": "She Said No.", "turn": 2, "lines": [
        {"speaker": "b", "text": "Hello there."}, *GOOD["lines"][1:5],
        {"speaker": "a", "text": "Studies show 80% of developers redo things at least twice every week."},
        {"speaker": "a", "text": "Fine."}, {"speaker": "a", "text": "Fine again."}, {"speaker": "a", "text": "And {{your number}}."}]}
    flags = " | ".join(d.dialogue_flags(bad, CAST, HOOK, 60, 150))
    for part in ("lines for 60s", "the first line is Mia's", "approved hook", "words (max 9", "real-world statistic",
                 "4 lines in a row", "{{gap}}", "mark the turn", "ends with a question", "all lowercase"):
        assert part in flags, part


def test_callback_and_loop_are_detected():
    assert d.find_callback(GOOD["lines"]) is not None
    flat = {**GOOD, "lines": L(("a", HOOK), ("b", "Okay."), ("a", "Sure."), ("b", "Right."), ("a", "Fine."), ("b", "Done."))}
    flags = " | ".join(d.dialogue_flags(flat, CAST, HOOK, 20, 150))
    assert "no callback" in flags and "loop back" in flags and "in-story details" in flags


def test_lines_group_into_clips_in_order_without_splitting():
    g = d.group_lines(GOOD["lines"], 6, 150)
    assert g and len(g) == 6 and [i for grp in g for i in grp] == list(range(len(GOOD["lines"])))
    assert all(grp for grp in g)
    assert d.group_lines(GOOD["lines"][:3], 6, 150) is None             # fewer lines than clips
    long = L(*[("a" if k % 2 else "b", "this line has quite a lot of words in it now") for k in range(40)])
    assert d.group_lines(long, 6, 150) is None                          # cannot fit 60 s
    clips = d.clips_from_lines(GOOD["lines"], g)
    assert clips[0]["lines"][0] == {"i": 0, "speaker": "a", "text": HOOK} and clips[0]["vo"].startswith(HOOK)


def test_shot_plan_rules():
    plan = d.plan_shots(GOOD["lines"])
    shots = [p["shot"] for p in plan]
    assert shots[0] == "a" and shots[1] == "b"                          # starts on the speaker's close-up
    assert shots[5] == "wide"                                           # the same person twice in a row: new angle
    assert shots[-1] == "wide" and shots[-2] == "wide"                  # the button plays wide
    run = 0
    for s in shots:                                                     # never more than 6 close-ups in a row
        run = 0 if s == "wide" else run + 1
        assert run <= 6
    assert plan[7]["face"] == "confused" and plan[7]["gesture"] == "think"      # "You counted?"
    assert plan[1]["gesture"] == "cheer" and plan[1]["face"] == "happy"         # the mascot hops on "That's great!"


def test_layout_keeps_lines_apart_and_inside_the_clip():
    t = d.layout([1.2, 0.8, 1.5, 0.9], [False, False, True, False])
    assert t["tempo"] == 1.0 and t["overflow"] == 0
    for k in range(3):
        assert t["starts"][k + 1] - t["ends"][k] >= 0.3
    # line 3 starts with a pause beat ("..."): the silence before it is the longest
    assert t["starts"][2] - t["ends"][1] > t["starts"][3] - t["ends"][2] and t["starts"][2] - t["ends"][1] > t["starts"][1] - t["ends"][0]
    long = d.layout([3.0, 2.6, 2.8, 2.4], [False] * 4)
    assert 1.0 < long["tempo"] <= 1.25 and long["ends"][-1] <= 10.0
    assert all(long["starts"][k + 1] >= long["ends"][k] for k in range(3))
    over = d.layout([4.0, 4.0, 4.0], [False] * 3, max_speedup=1.1)
    assert over["overflow"] > 0


def test_scene_is_valid_with_a_cut_per_line_and_mouths_per_speaker():
    plan = d.plan_shots(GOOD["lines"][:4])
    timing = d.layout([1.6, 0.9, 1.4, 1.5], [False] * 4)
    env = [0.5] * 240
    mouths = d.speaker_mouths(env, plan, timing, 24)
    scene = d.build_scene(plan, timing, CAST, mouths, 24, 720, 1280, 10.0, seed=3, quality="high")
    assert tj.validate_scene(scene) == []
    cams = scene["camera"]
    assert len(cams) == 4 and all(k["cut"] for k in cams) and cams[0]["t"] == 0
    assert all(b["t"] > a["t"] for a, b in zip(cams, cams[1:]))
    a, b = scene["actors"]
    assert a["kind"] == "chibi" and b["kind"] == "mascot" and scene["style"] == "night"
    f = int(timing["starts"][1] * 24) + 2                               # mascot's line: only its mouth moves
    assert b["mouth"]["values"][f] > 0 and a["mouth"]["values"][f] == 0
    assert scene["transition"] == {"in": "none", "out": "none"}


def test_line_captions_never_overlap_and_sit_at_the_top():
    clip_lines = [[{"i": 0, "speaker": "a", "text": HOOK}, {"i": 1, "speaker": "b", "text": "That's great!"}],
                  [{"i": 2, "speaker": "a", "text": "I didn't build it."}]]
    metas = [{"meta": {"lines": [{"start": 0.5, "end": 2.6}, {"start": 2.7, "end": 3.5}]}}, {}]
    lines = d.caption_lines(metas, clip_lines, [0.0, 10.0], [10.0, 10.0])
    assert lines[0]["start"] == 0.5 and lines[1]["start"] == 2.7 and 10.0 < lines[2]["start"] < 11.0
    assert all(x["end"] <= y["start"] for x, y in zip(lines, lines[1:]))
    ass, problems = cap.build_line_ass(lines, "9:16", 720, 1280)
    assert ass.count("Dialogue: 0,") == 3 and ",8," in ass.split("Style: Line,")[1].split("\n")[0]   # alignment 8 = top
    assert problems == []


def _wav(path, secs, freq=300, delay=0.0):
    subprocess.run([ffmpeg_bin(), "-y", "-loglevel", "error", "-f", "lavfi", "-i", f"sine=frequency={freq}:duration={secs}",
                    "-af", f"adelay={int(delay * 1000)}|{int(delay * 1000)}", "-ar", "22050", "-ac", "1", "-c:a", "pcm_s16le", str(path)], check=True)
    return path


def test_voices_are_placed_at_their_starts_and_pitch_keeps_length(tmp_path):
    a, b = _wav(tmp_path / "a.wav", 1.0), _wav(tmp_path / "b.wav", 0.5, 500)
    tts.pitch(b, 1.15)
    with wave.open(str(b)) as w:
        assert abs(w.getnframes() / w.getframerate() - 0.5) < 0.05
    out = tts.assemble([a, b], [0.5, 3.0], 1.0, tmp_path / "mix.wav", 10.0)
    import array
    with wave.open(str(out)) as w:
        assert w.getnframes() == 240000
        x = array.array("h", w.readframes(w.getnframes()))
    seg = lambda t0, t1: max(abs(v) for v in x[int(t0 * 24000):int(t1 * 24000)])  # noqa: E731
    assert seg(0, 0.45) == 0 and seg(0.6, 1.4) > 1000 and seg(1.6, 2.9) == 0 and seg(3.05, 3.45) > 1000


def test_sound_bed_ducks_under_the_voice(tmp_path):
    voice = tmp_path / "v.wav"
    _wav(voice, 2.0, 400, delay=3.0)
    video = tmp_path / "in.mp4"
    subprocess.run([ffmpeg_bin(), "-y", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=black:s=90x160:d=6:r=24", "-i", str(voice),
                    "-af", "apad", "-t", "6", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(video)], check=True)
    out = st.add_bed(video, tmp_path / "out.mp4", "room", -24)
    from backend.app.render.media import probe
    assert abs(probe(out)["duration"] - 6.0) < 0.1
    raw = subprocess.run([ffmpeg_bin(), "-loglevel", "error", "-i", str(out), "-ac", "1", "-ar", "8000", "-f", "s16le", "-"],
                         capture_output=True, check=True).stdout
    import array
    x = array.array("h", raw)
    rms = lambda t0, t1: (sum(v * v for v in x[int(t0 * 8000):int(t1 * 8000)]) / max(1, int((t1 - t0) * 8000))) ** 0.5  # noqa: E731
    assert rms(1.0, 2.5) > 20                                           # the bed plays in the gaps
    with pytest.raises(FileNotFoundError):
        st.add_bed(video, tmp_path / "x.mp4", str(tmp_path / "missing.mp3"), -24)


def test_fill_keeps_lines_in_sync():
    from backend.app.stages.studio import fill_placeholders
    script = {"mode": "dialogue", "lines": L(("a", "It costs {{your number}}.")),
              "clips": [{"index": 0, "vo": "It costs {{your number}}.", "lines": [{"i": 0, "speaker": "a", "text": "It costs {{your number}}."}]}],
              "hook": {"say": "x"}}
    out = fill_placeholders(script, {"your number": "$5"})
    assert out["lines"][0]["text"] == out["clips"][0]["lines"][0]["text"] == out["clips"][0]["vo"] == "It costs $5."


def _project(slug, duration=20):
    from backend.app import db, paths
    db.upsert_project(slug, slug, {"name": slug, "niche": "AI coding tools", "ratio": "9:16", "duration": duration,
                                   "platforms": ["shorts"], "theme": "dark", "style": "2A", "format": "dialogue", "voice_pref": "female",
                                   "cast": {"a": {"name": "Zoe"}}})
    root = paths.ensure_project_dirs(slug)
    (root / "research").mkdir(parents=True, exist_ok=True)
    (root / "research/niche-profile.json").write_text(json.dumps({"summary": []}))
    (root / "script").mkdir(parents=True, exist_ok=True)
    (root / "script/hooks.json").write_text(json.dumps({"topic": {"id": "t1", "title": "saying no to the AI"},
                                                         "hooks": [{"id": "h1", "say": HOOK, "write": "61 NOS", "rank": 1}]}))
    return root


async def test_dry_run_pipeline_end_to_end(monkeypatch):
    from backend.app import db, jobs
    from backend.app.jobs import manager
    real = jobs.load_settings

    def s():
        x = real()
        x["dry_run"] = True
        x["gates"] = {k: "auto" for k in x["gates"]}
        return x
    monkeypatch.setattr(jobs, "load_settings", s)
    root = _project("dlg-dry", 30)
    await manager.start()
    for stage in ("script", "direction_a", "direction_b", "scene_plan", "render", "stitch", "package"):
        jid, fut = manager.submit("dlg-dry", stage, {})
        assert await fut == "succeeded", (stage, db.get_job(jid))
    await manager.stop()
    sc = json.loads((root / "script/script.json").read_text())
    assert sc["mode"] == "dialogue" and sc["cast"] == {"a": "Zoe", "b": "Claude"} and len(sc["clips"]) == 3
    assert sc["lines"][0]["text"] == HOOK and sc["flags"] == []
    plan = json.loads((root / "scenes/dialogue.json").read_text())
    assert len(plan["plan"]) == len(sc["lines"])
    ass = (root / "final/captions.ass").read_text()
    assert "Style: Line" in ass and ass.count("Dialogue: 0,") == len(sc["lines"])
    qa = json.loads((root / "final/qa.json").read_text())
    assert qa["caption_overlaps"] == 0
    words = json.loads((root / "final/words.json").read_text())
    assert words["method"].startswith("dialogue lines") and len(words["lines"]) == len(sc["lines"])


async def test_real_render_needs_the_threejs_backend(monkeypatch):
    from backend.app import db, jobs
    from backend.app.jobs import manager
    real = jobs.load_settings

    def s():
        x = real()
        x["dry_run"] = True
        x["gates"] = {k: "auto" for k in x["gates"]}
        return x
    monkeypatch.setattr(jobs, "load_settings", s)
    _project("dlg-guard", 20)
    await manager.start()
    for stage in ("script", "direction_a", "direction_b"):
        assert await manager.submit("dlg-guard", stage, {})[1] == "succeeded"

    def live():
        x = s()
        x["dry_run"] = False
        x["render"] = {**x["render"], "backend": "omni-fal"}
        return x
    monkeypatch.setattr(jobs, "load_settings", live)
    jid, fut = manager.submit("dlg-guard", "render", {})
    assert await fut == "failed" and "local-threejs" in db.get_job(jid)["error"]
    await manager.stop()


@pytest.mark.skipif(not READY, reason="node + renderer build not present")
def test_dialogue_scene_renders_with_cuts(tmp_path):
    plan = d.plan_shots(GOOD["lines"][:3])
    timing = d.layout([1.0, 0.7, 1.0], [False] * 3, clip_len=4.0)
    scene = d.build_scene(plan, timing, CAST, {}, 6, 120, 214, 4.0, seed=3, quality="draft")
    sp = tmp_path / "s.json"
    sp.write_text(json.dumps(scene))
    r = subprocess.run([shutil.which("node"), str(tj.RENDERER / "render.mjs"), "--scene", str(sp), "--out", str(tmp_path / "c.mp4")],
                       capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, r.stdout[-600:]
    qa = next(json.loads(x) for x in r.stdout.splitlines() if '"qa"' in x)
    assert qa["frames"] == qa["expected"] == 24 and qa["black"] == [] and qa["blown"] == []
    assert not any('"page-error"' in x for x in r.stdout.splitlines())
