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


def L(*items):
    return [{"speaker": x[0], "text": x[1], "timing": x[2] if len(x) > 2 else "normal"} for x in items]


GOOD = {"title": "she said no sixty-one times. that's the job. what's the pettiest thing you've made your ai redo?",
        "turn": 12, "button": 17, "lines": L(
            ("a", HOOK), ("b", "[excited] That's GREAT!", "quick"), ("a", "[flatly] I didn't build it. You did."),
            ("b", "[proudly] I wrote four thousand lines.", "quick"), ("a", "[deadpan] They were bad.", "beat"),
            ("a", "I just said no a lot."), ("b", "[cheerfully] Sixty-one times.", "quick"), ("a", "[sighs] You counted?"),
            ("b", "You said it very clearly."), ("a", "Anyone can say no."), ("b", "[nervously] I can't. I say yes.", "quick"),
            ("b", "Knowing that is the job."), ("a", "...Okay. It's good.", "beat"), ("b", "[excited] It's great!!", "quick"),
            ("a", "[annoyed] The footer's two pixels off."), ("b", "1 AM."), ("a", "[exasperated] Two pixels, Claaauude."))}


def test_cast_defaults_merge_and_repair():
    c = d.cast_for({"cast": {"a": {"name": "Zoe", "appearance": {"hair": "#ff0000"}}, "b": {"kind": "dragon", "voice": "robot"}}})
    assert c["a"]["name"] == "Zoe" and c["a"]["appearance"]["hair"] == "#ff0000" and c["a"]["appearance"]["glasses"] == "round"
    assert c["b"]["kind"] == "mascot" and c["b"]["voice"] == "mascot" and c["b"]["name"] == "Claude"
    assert d.DEFAULT_CAST["a"]["name"] == "Mia"                         # defaults are never mutated


def test_delivery_text_helpers():
    t = "[exasperated] Claaauude!! The client said it's GREAT."
    assert d.clean(t) == "Claaauude!! The client said it's GREAT." and d.tags(t) == ["exasperated"]
    assert d.squash(t) == d.squash("Claude. The client said it's great.")       # stretched/tagged hook still matches
    assert d.words(t) == 6
    assert d.timing_of({"text": "...Fine."}) == "beat" and d.timing_of({"text": "Fine.", "timing": "quick"}) == "quick"
    assert tts.strip_tags("[sighs] Fine. [laughs]") == "Fine." and tts.expressive("eleven_v4") and not tts.expressive("eleven_multilingual_v2")


def test_good_script_passes_and_each_rule_is_checked():
    assert d.dialogue_flags(GOOD, CAST, HOOK, 40, 150) == []
    short = " | ".join(d.dialogue_flags(GOOD, CAST, HOOK, 60, 150))     # 17 lines run about 38 s: too short for 60 s
    assert "the lines run about 38s but the video is set to 60s: add about" in short
    lo, hi = d.target_lines(60)
    assert lo <= 30 <= hi and 40 <= d.estimate_seconds(GOOD["lines"] * 2, 150)
    tagged_hook = {**GOOD, "lines": [{"speaker": "a", "text": "[exasperated] Claaauude. The client said it's GREAT.", "timing": "normal"},
                                     *GOOD["lines"][1:]]}
    assert d.dialogue_flags(tagged_hook, CAST, HOOK, 40, 150) == []
    bad = {**GOOD, "title": "She Said No [sighs].", "turn": 2, "lines": [
        {"speaker": "b", "text": "Hello there."}, *GOOD["lines"][1:5],
        {"speaker": "a", "text": "Studies show 80% of developers redo things at least twice every week."},
        {"speaker": "a", "text": "[a] [b] [c] Fine."}, {"speaker": "a", "text": "Fine again.", "timing": "slow"},
        {"speaker": "a", "text": "And {{your number}}."}]}
    flags = " | ".join(d.dialogue_flags(bad, CAST, HOOK, 60, 150))
    for part in ("lines for 60s", "the first line is Mia's", "approved hook", "words (max 9", "real-world statistic",
                 "4 lines in a row", "{{gap}}", "mark the turn", "ends with a question", "all lowercase", "delivery tags (max 2)",
                 "timing must be quick, normal or beat", "no delivery tags in the title"):
        assert part in flags, part


def test_performance_and_rhythm_are_required():
    flat = {**GOOD, "lines": [{**ln, "text": d.clean(ln["text"]).replace("!!", "!").replace("aaau", "au"), "timing": "normal"}
                              for ln in GOOD["lines"]]}
    flags = " | ".join(d.dialogue_flags(flat, CAST, HOOK, 60, 150))
    assert "write the performance into the lines" in flags and "at least 2 lines answer straight back" in flags and "beats" in flags


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
    assert clips[0]["lines"][0] == {"i": 0, "speaker": "a", "text": HOOK, "timing": "normal"} and clips[0]["vo"].startswith(HOOK)
    assert "[" not in " ".join(c["vo"] for c in clips)                   # the pipeline's text has no tags


def test_direction_rules():
    plan = d.plan_shots(GOOD["lines"])
    shots = [p["shot"] for p in plan]
    assert shots[0] == "a_cu"                                           # the hook lands in her face
    assert shots[1] == "m_b_r" and shots[3] == "m_b_l"                  # the AI at desk height, her behind it, alternating
    assert plan[5]["cut"] is False and shots[5] == shots[4]             # she goes on: the same shot holds, no cut
    assert shots[-1] == "wide"                                          # the last line plays wide (the pull-back follows)
    cuts = [p["shot"] for p in plan if p["cut"]]
    assert all(x != y or x == "wide" for x, y in zip(cuts, cuts[1:]))   # never the same framing on two cuts in a row
    assert "a_third" in shots                                           # off-centre framings are used
    since = 0
    for sh in shots:                                                    # a wide at least every 10 lines
        since = 0 if sh == "wide" else since + 1
        assert since <= 10
    assert plan[7]["face"] == "skeptical"                               # [sighs] You counted?
    assert plan[1]["face"] == "happy" and plan[1]["gesture"] == "cheer" # [excited] That's GREAT!
    assert plan[10]["face"] == "caught"                                 # [nervously]: the AI's small square eyes
    assert all(p["pose"] == "rest" for p in plan)                       # no poses written: hands on the desk
    assert all(d.shot_label(sh, {"a": "Mia", "b": "Claude"}) for sh in shots)


def test_poses_hold_until_changed_and_morning_starts_with_a_mug():
    lines = [{**ln} for ln in GOOD["lines"]]
    lines[2]["pose"], lines[9]["pose"] = "crossed", "temple"
    plan = d.plan_shots(lines, {"set": "office", "look": "night"})
    poses = [p["pose"] for p in plan]
    assert poses[:2] == ["rest", "rest"] and set(poses[2:9]) == {"crossed"} and set(poses[9:]) == {"temple"}
    assert d.plan_shots(GOOD["lines"], {"set": "office", "look": "morning"})[0]["pose"] == "mug"
    timing = {"starts": [0.37 + 1.4 * k for k in range(len(lines))], "ends": [1.37 + 1.4 * k for k in range(len(lines))]}
    scene = d.build_scene(plan, timing, CAST, {}, 30, 720, 1280, 26.0, seed=3, quality="high")
    g = scene["actors"][0]["gestures"]
    assert all(x["snap"] for x in g) and g[0]["t"] == -1.0             # poses switch on cuts, never on screen
    cuts = {k["t"] for k in scene["camera"] if k.get("cut")}
    assert all(x["t"] in cuts for x in g[1:])


def test_group_cast_opens_wide_and_gives_each_ai_its_shot():
    cast = d.cast_for({"cast": {"c": {"enabled": True}, "d": {"enabled": True}}})
    assert d.speakers(cast) == ("a", "b", "c", "d") and d.speakers(CAST) == ("a", "b")
    lines = L(("a", "Okay, everyone. Launch is tomorrow."), ("b", "Tomorrow?!", "quick"), ("c", "[flatly] Fine."),
              ("a", "So I got help."), ("d", "[excited] Hi! I already started.", "quick"), ("a", "I haven't said what."),
              ("d", "I guessed."), ("c", "Done."), ("b", "...I was asking a question.", "beat"), ("a", "Nobody touch anything."))
    plan = d.plan_shots(lines)
    assert plan[0]["shot"] == "wide" and plan[2]["shot"].startswith("m_c_") and plan[4]["shot"].startswith("m_d_")
    timing = {"starts": [0.37 + 1.4 * k for k in range(len(lines))], "ends": [1.37 + 1.4 * k for k in range(len(lines))]}
    scene = d.build_scene(plan, timing, cast, {}, 30, 720, 1280, 16.0, seed=3, quality="high")
    assert tj.validate_scene(scene) == []
    ids = {x["id"]: x for x in scene["actors"]}
    assert set(ids) == {"a", "b", "c", "d"} and ids["c"]["appearance"]["shape"] == "cloud" and ids["d"]["appearance"]["shape"] == "cube"
    assert all(ids[s]["appearance"]["mouth"] is False and "mouth" not in ids[s] for s in "bcd")   # the AIs act with their eyes
    yaws = ids["c"]["facing"]                                           # cheated to face its camera, from the cut on
    assert isinstance(yaws, list) and any(abs(k["yaw"]) > 0 for k in yaws)
    flags = " | ".join(d.dialogue_flags({**GOOD, "lines": lines}, cast, lines[0]["text"], 20, 150))
    assert "speaker must be" not in flags


def test_scene_picks_set_and_look_settings_win():
    s = {"scene": {"set": "classroom", "look": "dusk"}, "lines": L(("a", "Explain it."), ("b", "Okay."))}
    assert d.scene_for(s) == {"set": "classroom", "look": "dusk"}
    assert d.scene_for(s, {"dialogue": {"look": "rain"}}) == {"set": "classroom", "look": "rain"}
    assert d.scene_for({"scene": {"set": "classroom"}, "lines": L(("a", "Hi."), ("c", "Done."))}) == {"set": "office", "look": "night"}
    assert d.scene_for({}) == {"set": "office", "look": "night"} and d.scene_for({"scene": {"set": "classroom"}})["look"] == "morning"


def test_classroom_board_fills_in_as_the_words_are_said():
    lines = [{"speaker": "a", "text": "Claude. Explain an API like I'm five.", "timing": "normal",
              "board": [{"op": "title", "text": "What is an API?"}]},
             {"speaker": "b", "text": "It's an interface between systems.", "timing": "quick",
              "board": [{"op": "word", "text": "interface", "at": "interface"}, {"op": "word", "text": "systems", "at": "systems"}]},
             {"speaker": "a", "text": "No. Simpler.", "timing": "quick", "board": [{"op": "strike"}]},
             {"speaker": "b", "text": "Okay. A restaurant.", "timing": "beat"}]
    scene_d = {"set": "classroom", "look": "morning"}
    plan = d.plan_shots(lines, scene_d)
    assert [p["shot"] for p in plan] == ["board", "board", "board", "b_books"]
    timing = {"starts": [0.37, 2.3, 4.2, 5.8], "ends": [2.0, 4.0, 5.0, 7.0]}
    scene = d.build_scene(plan, timing, CAST, {}, 30, 720, 1280, 7.3, seed=3, quality="high", scene=scene_d,
                          board_before=[{"op": "title", "text": "Earlier"}])
    assert tj.validate_scene(scene) == [] and scene["set"] == "classroom"
    ev = scene["board"]["events"]
    assert ev[0] == {"t": -1.0, "op": "title", "text": "Earlier"}       # earlier clips' writing is already up
    word = next(e for e in ev if e.get("text") == "systems")
    assert 2.3 + 0.5 * 1.7 <= word["t"] <= 4.0                           # appears as "systems" is said
    flags = " | ".join(d.dialogue_flags({**GOOD, "scene": scene_d, "lines": GOOD["lines"]}, CAST, HOOK, 60, 150))
    assert "board with a title" in flags and "at least 4 items" in flags


def test_layout_follows_each_lines_timing():
    t = d.layout([1.2, 0.8, 1.5, 0.9], ["normal", "quick", "beat", "normal"])
    assert t["tempo"] == 1.0 and t["overflow"] == 0
    g = [t["starts"][k + 1] - t["ends"][k] for k in range(3)]
    assert 0.15 <= g[0] <= 0.25 and 0.8 <= g[1] <= 1.0 and 0.4 <= g[2] <= 0.5   # quick comeback, a beat, a normal turn
    long = d.layout([3.0, 2.6, 2.8, 2.4], ["normal"] * 4)
    assert 1.0 < long["tempo"] <= 1.25 and long["ends"][-1] <= 10.0
    assert all(long["starts"][k + 1] >= long["ends"][k] for k in range(3))
    over = d.layout([4.0, 4.0, 4.0], ["normal"] * 3, max_speedup=1.1)
    assert over["overflow"] > 0
    short = d.layout([0.8, 0.7], ["normal", "normal"])                  # spare time never becomes dead air mid-talk
    assert short["starts"][1] - short["ends"][0] <= 0.46
    # a clip ends when its talk does (plus a short tail), so the next clip's first line is not after dead air
    tight = d.layout([0.8, 0.7], ["normal", "normal"], pad=False)
    assert tight["starts"][0] == d.LEAD
    end = d.clip_end(tight, 10.0, 24)
    assert abs(end - (tight["ends"][-1] + d.TAIL)) <= 1 / 24 and abs(end * 24 - round(end * 24)) < 1e-6
    assert d.clip_end(long) <= 10.0 and d.clip_end({"starts": [], "ends": []}) == 10.0
    assert d.clip_end(d.layout([0.3], ["normal"], pad=False)) == 2.0      # never a flash clip
    later = d.layout([0.8], ["normal"], pad=False, lead=d.clip_lead(False, "normal"))
    assert abs(d.TAIL + later["starts"][0] - d.GAPS["normal"]) < 1e-6     # across a clip cut the turn keeps its gap
    final = d.clip_end(tight, 10.0, 30, 1.7)
    assert abs(final - (tight["ends"][-1] + 1.7)) <= 1 / 30               # the last clip holds for the pull-back


def test_scene_is_valid_with_a_cut_per_line_and_mouths_per_speaker():
    plan = d.plan_shots(GOOD["lines"][:5])
    timing = d.layout([1.6, 0.9, 1.4, 1.5, 0.8], [p["timing"] for p in plan])
    env = [0.5] * 240
    mouths = d.speaker_mouths(env, plan, timing, 24)
    scene = d.build_scene(plan, timing, CAST, mouths, 24, 720, 1280, 10.0, seed=3, quality="high")
    assert tj.validate_scene(scene) == []
    cams = scene["camera"]
    assert len(cams) == 5 and all(k["cut"] for k in cams) and cams[0]["t"] == 0
    assert all(b["t"] > a["t"] for a, b in zip(cams, cams[1:]))
    for k in (1, 2, 3):                                                 # the cut lands 0.15 s before the speaker's first word
        assert abs(cams[k]["t"] - (timing["starts"][k] - d.CUT_LEAD)) < 1e-3
    assert cams[4]["t"] <= timing["ends"][3] + 0.34                      # a beat cuts to the responder's look early
    a, b = scene["actors"]
    assert {"t": round(timing["ends"][3], 3), "expr": "skeptical"} in a["face"]
    assert a["kind"] == "chibi" and b["kind"] == "mascot" and scene["style"] == "night" and scene["handheld"] == 0
    assert "mouth" not in b and b["appearance"]["mouth"] is False        # the AI acts with its eyes (reference style)
    talking = d.build_scene(plan, timing, CAST, mouths, 24, 720, 1280, 10.0, seed=3, quality="high", mascot_mouth=True)
    a, b = talking["actors"]
    f = int(timing["starts"][1] * 24) + 2                               # mascot's line: only its mouth moves
    assert b["mouth"]["values"][f] > 0 and a["mouth"]["values"][f] == 0
    final = d.build_scene(plan, timing, CAST, mouths, 24, 720, 1280, timing["ends"][-1] + 1.7, seed=3, quality="high", final=True)
    hold, back = final["camera"][-2:]                                   # the last shot holds, then pulls back
    assert hold["t"] == timing["ends"][-1] and back["pos"][2] > hold["pos"][2] and not back.get("cut")
    assert scene["transition"] == {"in": "none", "out": "none"}


def test_elevenlabs_v4_request_and_tags(tmp_path, monkeypatch):
    import httpx

    from backend.app import settings as S
    monkeypatch.setattr(S, "_env_cache", {"ELEVENLABS_API_KEY": "sk_test_0123456789"})
    sent = []
    mp3 = subprocess.run([ffmpeg_bin(), "-loglevel", "error", "-f", "lavfi", "-i", "sine=duration=0.5", "-f", "mp3", "-"],
                         capture_output=True, check=True).stdout

    def handler(req):
        sent.append(json.loads(req.content))
        return httpx.Response(200, content=mp3)
    v = {**S.DEFAULTS["voice"], "elevenlabs_model": "eleven_v4", "elevenlabs_stability": 0.3}
    tts.elevenlabs_say("[exasperated] Claaauude!!", tmp_path / "a.wav", v, "female", transport=httpx.MockTransport(handler))
    assert sent[0]["model_id"] == "eleven_v4" and sent[0]["text"] == "[exasperated] Claaauude!!"
    assert sent[0]["voice_settings"] == {"stability": 0.3, "similarity_boost": 0.75}       # v4 takes only these two
    tts.elevenlabs_say("[sighs] Fine.", tmp_path / "b.wav", {**v, "elevenlabs_model": "eleven_multilingual_v2"}, "female",
                       transport=httpx.MockTransport(handler))
    assert sent[1]["text"] == "Fine." and "style" in sent[1]["voice_settings"]               # older model: no tags


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
    for bed in ("rain", "city"):                                        # the window looks' ambiences render too
        o = st.add_bed(video, tmp_path / f"{bed}.mp4", bed, -24)
        assert abs(probe(o)["duration"] - 6.0) < 0.1
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
    assert sc["punch_up"]["applied"]                                   # the punch-up pass ran (Settings: on by default)
    if sc["punch_up"]["before"]:
        assert any(ln["text"] == "[flatly] Very clearly." for ln in sc["lines"])
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
    timing = d.layout([1.0, 0.7, 1.0], ["normal"] * 3, clip_len=4.0)
    scene = d.build_scene(plan, timing, CAST, {}, 6, 120, 214, 4.0, seed=3, quality="draft")
    sp = tmp_path / "s.json"
    sp.write_text(json.dumps(scene))
    r = subprocess.run([shutil.which("node"), str(tj.RENDERER / "render.mjs"), "--scene", str(sp), "--out", str(tmp_path / "c.mp4")],
                       capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, r.stdout[-600:]
    qa = next(json.loads(x) for x in r.stdout.splitlines() if '"qa"' in x)
    assert qa["frames"] == qa["expected"] == 24 and qa["black"] == [] and qa["blown"] == []
    assert not any('"page-error"' in x for x in r.stdout.splitlines())


def test_still_motion_is_the_default_and_lively_restores_gestures():
    lines = L(("a", HOOK), ("b", "That's great!"), ("a", "You counted?"), ("b", "Sixty-one times!"))
    plan = d.plan_shots(lines)
    timing = d.layout([1.6, 0.9, 1.0, 1.2], [p["timing"] for p in plan])
    still = d.build_scene(plan, timing, CAST, {}, 24, 720, 1280, 10.0, seed=3, quality="draft")
    a, b = still["actors"]
    assert a["still"] and b["still"]
    assert a["anim"] == [{"t": 0, "clip": "Idle", "speed": 0}]                  # the idle pose, frozen
    assert [g["gesture"] for g in a["gestures"]] == ["rest"] and a["gestures"][0]["t"] < 0   # hands already on the desk
    assert b["gestures"] == [] and len(a["look"]) == 1 and len(b["look"]) == 1  # no hops, gaze never switches
    assert len({f["expr"] for f in a["face"]}) > 1                            # faces still change with the words
    lively = d.build_scene(plan, timing, CAST, {}, 24, 720, 1280, 10.0, seed=3, quality="draft", motion="lively")
    la, lb = lively["actors"]
    assert not la["still"] and "think" in [g["gesture"] for g in la["gestures"]] and "cheer" in [g["gesture"] for g in lb["gestures"]]
    assert len(lb["look"]) > 1
    assert tj.validate_scene(still) == [] and tj.validate_scene(lively) == []


def test_package_description_has_no_links_or_impossible_timestamps():
    from backend.app.stages.production import clean_description, description_checks
    text = ("Watch a 10-minute showdown where I race an AI robot.\n\nhttps://example.com/resource\n\n"
            "Timestamps:\n0:00 Intro\n0:10 Timer starts\n0:45 Results\n0:50 Wrap-up")
    short = clean_description(text, 37, chapters_ok=False)
    assert "example.com" not in short and "Timestamps" not in short and "0:10" not in short
    long = clean_description(text, 48 * 60, chapters_ok=True)
    assert "0:10 Timer starts" in long and "Timestamps:" in long and "http" not in long
    assert description_checks(short, "Claude. Good morning.") and not description_checks("Morning again.", "")


def test_package_writer_gets_the_real_length_ratio_and_script():
    from backend.app.agent import tasks
    t = tasks.package("t", "Mia: Claude. Hi.\nClaude: Hello!", {}, {"say": "Claude. Hi."}, 60, ["shorts"], [{"label": "0:00"}], 37.0, "9:16", "a desk")
    assert "VIDEO LENGTH: 37 s (a short)" in t.prompt and "1080x1920" in t.prompt and "no timestamps" in t.prompt
    assert "DRAFT CHAPTERS (chapters.py): []" in t.prompt and "Plain international English" in t.prompt
    assert {"pinned_comment", "cover_prompt"} <= set(t.schema["required"])
    wide = tasks.package("t", "x", {}, {"say": "x"}, 600, ["youtube"], [], 600.0, "16:9")
    assert "1280x720" in wide.prompt
    part = tasks.package_part("description", "old text", "funnier", "t", "x", 37.0, "9:16")
    assert "old text" in part.prompt and "funnier" in part.prompt and part.schema["required"] == ["text"]


class _PunchCtx:
    def __init__(self, reply):
        self.reply, self.logs, self.calls = reply, [], 0
        outer = self

        class Agent:
            async def run(self, task, ctx):
                outer.calls += 1
                assert task.name == "punch_up" and task.skills == ["joke-engineering"]
                if isinstance(outer.reply, Exception):
                    raise outer.reply
                return outer.reply(task) if callable(outer.reply) else outer.reply
        self.agent = Agent()

    def log(self, text, level="info"):
        self.logs.append((level, text))


async def test_punch_up_keeps_good_changes_and_guards_the_format():
    from backend.app.stages.studio import _punch_up
    res = {**GOOD, "lines": [dict(ln) for ln in GOOD["lines"]]}
    texts = [ln["text"] for ln in res["lines"]]
    better = list(texts)
    better[8] = "[flatly] Very clearly."                                # a sharper line: kept
    better[0] = "Claude. Nice work."                                    # the hook is never rewritten: reverted
    better[9] = "Anyone can say no at any time of the day or night, honestly."   # over the word cap: reverted
    ctx = _PunchCtx({"lines": better, "notes": [{"line": 9, "state": "H6", "change": "cut the setup"},
                                                {"line": 1, "state": "H1", "change": "x"}]})
    out, report = await _punch_up(ctx, res, CAST, {}, {"say": HOOK}, 40, 150)
    got = [ln["text"] for ln in out["lines"]]
    assert got[8] == "[flatly] Very clearly." and got[0] == texts[0] and got[9] == texts[9]
    assert all(a["speaker"] == b["speaker"] and a["timing"] == b["timing"] for a, b in zip(out["lines"], res["lines"]))
    assert report["applied"] and report["before"] == {8: texts[8]} and [n["line"] for n in report["notes"]] == [9]
    # the wrong number of lines, a rule broken, or a failed call: the script stays as written
    for reply in ({"lines": texts[:-1]}, {"lines": [d.clean(t).replace("!!", "!").replace("aaau", "au") for t in texts]},   # the acting gone
                  RuntimeError("Groq HTTP 413")):
        same, rep = await _punch_up(_PunchCtx(reply), res, CAST, {}, {"say": HOOK}, 40, 150)
        assert same is res and not rep["applied"]


def test_punch_up_toggle_and_skill():
    from backend.app.settings import DEFAULTS
    from pathlib import Path
    assert DEFAULTS["dialogue"]["punch_up"] is True
    skill = (Path(__file__).resolve().parents[1] / ".claude/skills/joke-engineering/SKILL.md").read_text(encoding="utf-8")
    assert "name: joke-engineering" in skill and "H4 Over-explained" in skill and "Output persistence" not in skill
