from backend.app.agent import fixtures, skillref
from backend.app.render import captions
from backend.app.render.overlays import TextBox, safe_zone_violations
from backend.app.stages.studio import check_phase_b


def test_safe_zone_validator():
    assert safe_zone_violations([TextBox("ok", 0.2, 0.2, 0.4, 0.1)], "9:16") == []
    v = safe_zone_violations([TextBox("low", 0.2, 0.6, 0.4, 0.1), TextBox("top", 0.2, 0.05, 0.4, 0.05)], "9:16")
    assert len(v) == 2


def test_captions_and_hook_card_stay_in_safe_zone():
    words = captions.estimate_words(["Your brain thinks future-you is a stranger, and it costs you money every month."])
    ass, viol = captions.build_ass(words, "9:16", 720, 1280, hook_card="FUTURE YOU?", callouts=[{"t": 4, "text": "EVERY MONTH"}])
    assert viol == [] and "Style: Hook" in ass and "FUTURE YOU?" in ass
    assert words[0].s >= 0.4 and words[-1].e <= 9.4


def test_phase_b_checker_enforces_verbatim_anchor_and_voice():
    rows = [{"clip": k + 1, "scene": "s", "motion": "m", "vo": "v"} for k in range(3)]
    res = fixtures.phase_b("md", rows, "9:16", 30, "1", "dark", {})
    assert check_phase_b(res, 3, "1", "dark") == []
    assert res["character_anchor"] == skillref.style1_anchor("dark")
    broken = {**res, "prompts": [dict(p) for p in res["prompts"]]}
    broken["prompts"][1]["text"] = broken["prompts"][1]["text"].replace(res["voice_block"], "Same narrator as before.")
    broken["prompts"][2]["text"] += " Use #FF0000 for the coin."
    errs = check_phase_b(broken, 3, "1", "dark")
    assert any("voice block" in e for e in errs) and any("colour" in e for e in errs)
    assert check_phase_b({**res, "prompts": res["prompts"][:2]}, 3, "1", "dark")
