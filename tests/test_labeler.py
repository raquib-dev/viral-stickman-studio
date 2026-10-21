from backend.app.analysis.labeler import label_transcript
from backend.app.analysis.transcript import cues_to_words, parse_cues, sentences

CUES = [
    (0.0, 2.6, "Your brain thinks future you is a stranger."),
    (2.8, 5.4, "And it costs you money every month you wait."),
    (5.6, 8.0, "Most people think it's about discipline."),
    (21.0, 23.5, "But here's the catch."),
    (24.0, 26.0, "The reward feels far away."),
    (42.0, 44.5, "And get this."),
    (45.0, 47.5, "Here's how to fix it: automate the choice."),
    (54.0, 56.0, "Comment which one you'd pick."),
    (57.0, 59.8, "Remember the stranger."),
]


def labels(cues=CUES, duration=60.0, llm=None):
    return label_transcript(cues_to_words(cues), duration, "shorts", llm)


def by_type(ls, t):
    return [l for l in ls if l["type"] == t]


def test_hook_ok_and_greeting_fails():
    assert by_type(labels(), "hook-placement")[0]["ok"] is True
    bad = [(0.0, 2.5, "Hey guys, welcome back to the channel.")] + CUES[1:]
    ls = labels(bad)
    assert by_type(ls, "hook-placement")[0]["ok"] is False
    assert by_type(ls, "no-intro"), "intro phrase in the first 5 s must be labelled"


def test_stakes_line_position():
    st = by_type(labels(), "stakes-line")
    assert len(st) == 1 and 2.5 <= st[0]["t"] <= 3.2 and st[0]["pct"] < 10


def test_rehooks_and_percentages():
    rh = by_type(labels(), "rehook-cadence")
    assert [round(r["pct"]) for r in rh] == [35, 70]


def test_payoff_after_40_percent():
    po = by_type(labels(), "payoff-timing")
    assert len(po) == 1 and po[0]["pct"] == 75.0


def test_single_cta_ok_and_double_cta_flagged():
    cta = by_type(labels(), "cta-placement")
    assert len(cta) == 1 and cta[0]["ok"]
    two = CUES[:-1] + [(58.0, 59.0, "And subscribe for more."), CUES[-1]]
    ctas = by_type(labels(two), "cta-placement")
    assert len(ctas) == 2 and not ctas[1]["ok"]


def test_early_cta_flagged():
    early = [CUES[0], (3.0, 5.0, "Subscribe before we start, and follow me."), *CUES[2:]]
    first = by_type(labels(early), "cta-placement")[0]
    assert first["ok"] is False and "15%" in first["note"]


def test_loop_detected():
    lp = by_type(labels(), "loop-ending")[0]
    assert lp["ok"] and "stranger" in lp["note"]


def test_llm_labels_merge_without_duplicates():
    ls = labels(llm={"deliberate-mistake-placement": [{"t": 30.0, "quote": "one, two, four"}],
                     "payoff-timing": [{"t": 45.2, "quote": "dup of regex payoff"}]})
    assert by_type(ls, "deliberate-mistake-placement")[0]["method"] == "llm"
    assert len(by_type(ls, "payoff-timing")) == 1


def test_auto_caption_without_punctuation_splits_sentences():
    raw = "WEBVTT\n\n00:00:00.000 --> 00:00:02.000\nyour brain thinks future you\n\n00:00:02.900 --> 00:00:05.000\nis a stranger and that costs you\n"
    ss = sentences(cues_to_words(parse_cues(raw)))
    assert len(ss) == 2
