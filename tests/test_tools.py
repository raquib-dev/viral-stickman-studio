"""The vendored pack tools run unmodified through our wrappers, including their non-zero 'verdict' exits."""
from backend.app.tools import runner as r


def test_hookscore_panels_and_formulas():
    hooks = ["Stop budgeting. 70% of budgets fail by week three.", "Hey guys, today I wanted to talk about money"]
    yt = r.yt_hookscore(hooks)
    ig = r.ig_hookscore(hooks)
    assert {h["hook"] for h in yt} == set(hooks) and all("verdict" in h for h in yt)
    weak = next(h for h in ig if h["hook"].startswith("Hey"))
    assert weak["verdict"] == "WEAK" and weak["flags"], "greeting is an ig dealbreaker"
    assert r.ig_formula(hooks[:1])[hooks[0]]["name"] == "The Statistic"


def test_beats_exit_code_policy_and_flags():
    rep = r.beats("This hook line is far too long to land inside three seconds of speech.\nShort.\n", 150, 10)
    assert rep["beats"][0]["flags"]


def test_caption_title_humanize_detect_chapters():
    assert r.caption_lint("Hello\n#a #b #c #d #e #f")["verdict"] == "FIX"   # exit 1, still parsed
    assert r.title_lint(["An ULTIMATE AMAZING INSANE title"], "AMAZING")[0]["issues"]
    assert "—" not in r.humanize("It is crucial — really.")["text"]
    assert r.detect("A short line. Another one here.")["verdict"] in ("PASS", "REVIEW", "FLAGGED")
    srt = "".join(f"{i}\n00:00:{i * 9:02d},000 --> 00:00:{i * 9 + 8:02d},000\nline {i} about topic{i % 3} words here\n\n" for i in range(1, 7))
    assert "chapters" in r.chapters(srt, 3)
