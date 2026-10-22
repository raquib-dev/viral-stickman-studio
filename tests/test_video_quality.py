"""Video quality repairs: caption timing (no overlaps, phrase pages, real speech windows), black-dip detection,
seam transitions, plan repairs (exposure/bloom/zoom/props/placeholders), script gaps, TTS silence trimming,
and the renderer's per-frame QA report."""
import json
import shutil
import subprocess
import wave

import pytest

from backend.app.analysis.transcript import Word
from backend.app.render import captions as cap
from backend.app.render import stitch as st
from backend.app.render import threejs as tj
from backend.app.render import tts
from backend.app.settings import ffmpeg_bin
from backend.app.stages.studio import fill_placeholders, placeholders

READY = tj.status()["ok"]


def _w(*items):
    return [Word(w, s, e) for w, s, e in items]


def test_caption_events_never_overlap_and_pages_end_at_sentences():
    # whisper-like timing: "problem." ends after "You" starts (this stacked two caption lines in the old build)
    words = _w(("You", 0.8, 1.0), ("don't", 1.0, 1.2), ("have", 1.2, 1.5), ("a", 1.5, 1.6), ("money", 1.6, 1.9),
               ("problem.", 1.9, 2.6), ("You", 2.5, 2.7), ("have", 2.7, 2.9), ("have", 2.75, 2.95), ("a", 4.0, 4.1))
    words = cap.dedupe_words(words)
    assert [w.w for w in words].count("have") == 2                  # the echoed "have" is dropped, the real one kept
    pages = cap.phrase_pages(words, 3)
    assert [[w.w for w in p] for p in pages] == [["You", "don't", "have"], ["a", "money", "problem."], ["You", "have"], ["a"]]
    ev = cap.page_events(pages)
    assert all(b[0] >= a[1] - 1e-9 for a, b in zip(ev, ev[1:]))
    assert all(e > s for s, e, _, _ in ev)
    ass, _ = cap.build_ass(words, "9:16", 720, 1280)
    assert "{{" not in ass and ass.count("Dialogue: 0,") == len(ev)


def test_placeholder_braces_never_reach_captions():
    assert cap.clean_text("Every replay costs you {{your number}}.") == "Every replay costs you your number."
    assert cap.clean_text("((x))") == "x"


def test_estimated_captions_follow_the_real_speech_window():
    words = cap.estimate_words(["one two three four", "five six"], durations=[10.0, 10.0], windows=[[0.25, 4.25], None])
    first = [w for w in words if w.w in ("one", "two", "three", "four")]
    assert first[0].s == pytest.approx(0.25) and first[-1].e <= 4.25 + 1e-6      # not spread to 9.4 s
    six = next(w for w in words if w.w == "six")
    assert 10.0 < six.s < 19.4                                                       # clip 2 falls back to the old window


def test_black_dips_flag_seams_but_not_dark_scenes_or_fades():
    fps = 24
    bright = [60.0] * 240
    seam = bright[:-6] + [30, 18, 17, 17, 17, 18] + [18, 18, 25, 40, 55, 60] + bright[6:]
    dips = st.black_runs(seam, fps, [(0, 0.6), (19.4, 21)])
    assert len(dips) == 1 and dips[0]["start"] == pytest.approx(9.79, abs=0.05)
    dark_scene = [12.0] * 480                                     # legitimately dark all along
    assert st.black_runs(dark_scene, fps, [(0, 0.6)]) == []
    fade_in = [5.0] * 10 + [60.0] * 470                           # the planned opening fade
    assert st.black_runs(fade_in, fps, [(0, 0.6), (19.4, 21)]) == []


def test_seams_cut_between_clips_and_fade_only_at_the_ends():
    assert tj.seam_transition(0, 6, {"in": "fade", "out": "fade"}) == {"in": "fade", "out": "none"}
    assert tj.seam_transition(3, 6, {"in": "fade", "out": "iris"}) == {"in": "none", "out": "none"}
    assert tj.seam_transition(5, 6, {"in": "fade", "out": "fade"}) == {"in": "none", "out": "fade"}
    assert tj.seam_transition(0, 1, None) == {"in": "fade", "out": "fade"}


def test_repair_clamps_the_look_and_keeps_props_out_of_the_lens():
    raw = {"style": "cozy", "exposure": 1.6, "handheld": 0.2, "bloom": {"strength": 2, "threshold": 0.5},
           "actors": [{"id": "hero", "gestures": [{"t": 1, "gesture": "point", "target": "p1"}]}],
           "props": [{"id": "p1", "type": "drum"}, {"id": "p2", "type": "moneybag", "pos": [0.5, 0, 1.2]}],
           "badges": [{"text": "{{your number}}", "t_in": 1}],
           "camera": [{"t": 0, "shot": {"type": "closeup", "target": "hero", "zoom": 0.5}}]}
    s, fixes, errs = tj.check_and_repair(raw, "Save your money.", 10.0)
    assert errs == []                                             # a dropped prop no longer leaves a dangling target
    assert s["exposure"] == 1.15 and s["handheld"] == 0.025 and "bloom" not in s
    assert s["camera"][0]["shot"]["zoom"] == 0.9                 # close-ups never closer than 0.9
    assert [p["id"] for p in s["props"]] == ["p2"] and s["props"][0]["pos"][2] == 0.6
    assert s["badges"] == [] and any("placeholder" in f for f in fixes)
    assert "target" not in s["actors"][0]["gestures"][0]


def test_script_gaps_are_listed_and_filled():
    clips = [{"index": 0, "vo": "You lose {{your number}} a month."}, {"index": 1, "vo": "Keep {{your number}}. Or {{goal}}."}]
    assert placeholders(clips) == [{"name": "your number", "clips": [1, 2]}, {"name": "goal", "clips": [2]}]
    out = fill_placeholders({"clips": clips, "hook": {"say": "x", "write": "{{goal}}"}}, {"your number": "$40", "goal": " "})
    assert out["clips"][0]["vo"] == "You lose $40 a month." and out["placeholders"] == [{"name": "goal", "clips": [2]}]


def test_tts_silence_is_trimmed(tmp_path):
    wav = tmp_path / "v.wav"
    subprocess.run([ffmpeg_bin(), "-y", "-loglevel", "error", "-f", "lavfi", "-i", "sine=frequency=300:duration=1",
                    "-af", "adelay=600|600,apad=pad_dur=0.8", "-ar", "24000", "-ac", "1", "-c:a", "pcm_s16le", str(wav)], check=True)
    tts.trim_silence(wav)
    with wave.open(str(wav)) as w:
        assert 0.95 < w.getnframes() / w.getframerate() < 1.15


@pytest.mark.skipif(not READY, reason="node + renderer build not present")
def test_renderer_reports_frame_qa(tmp_path):
    scene = {"width": 120, "height": 214, "fps": 8, "duration": 2, "style": "cozy", "quality": "draft",
             "transition": {"in": "fade", "out": "none"}, "actors": [{"id": "hero"}], "camera": [{"t": 0, "shot": "closeup"}]}
    sp = tmp_path / "s.json"
    sp.write_text(json.dumps(scene))
    r = subprocess.run([shutil.which("node"), str(tj.RENDERER / "render.mjs"), "--scene", str(sp), "--out", str(tmp_path / "c.mp4")],
                       capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, r.stdout[-500:]
    qa = next(json.loads(x) for x in r.stdout.splitlines() if '"qa"' in x)
    assert qa["frames"] == qa["expected"] == 16 and qa["black"] == [] and qa["blown"] == []
    assert 15 < qa["mean_luma"] < 200
    lines = tj.qa_lines(qa, 1)
    assert lines and all(level == "info" for _, level in lines)


# ---- script gaps: rewrite without a figure ----

class _Ctx:
    def __init__(self, agent):
        self.agent, self.lines = agent, []

    def log(self, text, level="info"):
        self.lines.append((level, text))


class _Writer:
    def __init__(self, *answers):
        self.answers, self.calls = list(answers), []

    async def run(self, task, ctx):
        self.calls.append(task)
        return {"lines": self.answers.pop(0)}


HOOK = "You don't have a money problem."
GAP_SCRIPT = {"hook": {"say": HOOK}, "clips": [
    {"index": 0, "vo": HOOK + " Every replay costs you {{your number}}. Same pit, every Friday night again."},
    {"index": 1, "vo": "Keep the trigger, keep the reward, and just swap the button you press next time."},
    {"index": 2, "vo": "Stress hits, and you move {{your number}} into savings instead of takeout again."}]}


async def test_gap_rewrite_is_checked_then_applied():
    import copy

    from backend.app.stages.studio import rewrite_gaps
    bad = [{"clip": 1, "vo": HOOK + " Every replay costs you $40. Same pit, every Friday night again."},   # invents a figure
           {"clip": 3, "vo": "Stress hits, and you move {{your number}} into savings instead."}]           # gap kept
    good = [{"clip": 1, "vo": HOOK + " Every replay costs you more than you think. Same pit, every Friday night."},
            {"clip": 3, "vo": "Stress hits, and you move a slice of that money into savings instead of takeout."}]
    w = _Writer(bad, good)
    ctx = _Ctx(w)
    out = await rewrite_gaps(ctx, copy.deepcopy(GAP_SCRIPT))
    assert len(w.calls) == 2 and "invent" in w.calls[1].prompt.lower() and "$40" not in out["clips"][0]["vo"]
    assert "added numbers" in w.calls[1].context["feedback"] and "still has a gap" in w.calls[1].context["feedback"]
    assert out["placeholders"] == [] and out["clips"][1]["vo"] == GAP_SCRIPT["clips"][1]["vo"]   # untouched line kept
    assert out["clips"][0]["vo"].startswith(HOOK)


async def test_gap_rewrite_gives_up_clearly():
    import copy

    from backend.app.jobs import StageError
    from backend.app.stages.studio import rewrite_gaps
    lost_hook = [{"clip": 1, "vo": "Every replay costs you more than you think. Same pit, every Friday night, again and again."},
                 {"clip": 3, "vo": "Stress hits, and you move a slice of that money into savings instead of takeout."}]
    with pytest.raises(StageError, match="Fill them in yourself"):
        await rewrite_gaps(_Ctx(_Writer(lost_hook, lost_hook)), copy.deepcopy(GAP_SCRIPT))


def test_dry_run_fixture_for_gaps_is_valid():
    from backend.app.agent import fixtures, tasks
    from backend.app.agent.runner import _validate
    t = tasks.fill_gaps([{"clip": 3, "vo": GAP_SCRIPT["clips"][2]["vo"]}], HOOK)
    data = fixtures.fill_gaps(**t.context)
    _validate(t, data)
    assert "{{" not in data["lines"][0]["vo"]


async def test_render_stops_or_rewrites_by_setting(monkeypatch):
    import json as _json

    from backend.app import db, jobs, paths
    from backend.app.agent import runner
    from backend.app.jobs import manager
    slug = "gaps-render"
    db.upsert_project(slug, slug, {"name": slug, "niche": "x", "ratio": "9:16", "duration": 30, "platforms": ["shorts"],
                                   "theme": "dark", "style": "4"})
    root = paths.ensure_project_dirs(slug)
    for rel, obj in {"direction/phase-b.json": {"checks": [], "prompts": [{"text": "p"}] * 3},
                     "direction/phase-a.json": {"rows": [{"clip": k, "purpose": "beat"} for k in (1, 2, 3)]},
                     "script/script.json": GAP_SCRIPT}.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(_json.dumps(obj))
    real = jobs.load_settings
    mode = {"v": "ask"}

    def s():
        x = real()
        x["dry_run"] = False
        x["script_gaps"] = mode["v"]
        x["render"] = {**x["render"], "backend": "local-stickman"}
        return x
    monkeypatch.setattr(jobs, "load_settings", s)
    good = [{"clip": 1, "vo": HOOK + " Every replay costs you more than you think. Same pit, every Friday night."},
            {"clip": 3, "vo": "Stress hits, and you move a slice of that money into savings instead of takeout."}]
    monkeypatch.setattr(runner, "get_agent", lambda settings: _Writer(good))
    await manager.start()
    jid, fut = manager.submit(slug, "render", {"only": [99]})
    assert await fut == "failed"
    assert "Rewrite without the number" in (db.get_job(jid)["error"] or "")
    mode["v"] = "rewrite"
    jid, fut = manager.submit(slug, "render", {"only": [99]})          # clip 99 does not exist: only the gap step runs
    await fut
    await manager.stop()
    after = _json.loads((root / "script/script.json").read_text())
    assert "{{" not in _json.dumps(after["clips"]) and after["placeholders"] == []
