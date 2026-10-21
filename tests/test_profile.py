from backend.app.analysis.profile import build_profile, plan_beats


def video(i, rehooks=(36, 71), stakes_s=4.0, mult=4.0, duration=60.0):
    ls = [{"type": "stakes-line", "t": stakes_s, "pct": 100 * stakes_s / duration, "method": "regex", "ok": True},
          {"type": "payoff-timing", "t": 45.0, "pct": 75.0, "method": "regex", "ok": True},
          {"type": "cta-placement", "t": 54.0, "pct": 90.0, "method": "regex", "ok": True}]
    ls += [{"type": "rehook-cadence", "t": p / 100 * duration, "pct": float(p), "method": "regex", "ok": True} for p in rehooks]
    return {"id": f"v{i}", "multiple": mult, "duration": duration, "labels": ls}


def test_profile_finds_two_rehook_clusters_and_stakes():
    vids = [video(i, rehooks=(34 + i, 69 + i)) for i in range(6)]
    prof = build_profile(vids)
    rh = prof["per_type"]["rehook-cadence"]
    assert len(rh["clusters_pct"]) == 2
    assert 34 <= rh["clusters_pct"][0] <= 40 and 69 <= rh["clusters_pct"][1] <= 75
    assert prof["per_type"]["stakes-line"]["median_s"] == 4.0
    assert any("re-hook at ~" in s for s in prof["summary"])
    assert len(prof["heatmap"]["rows"]) >= 9 and len(prof["heatmap"]["rows"][0]["values"]) == 20


def test_plan_uses_profile_only_with_enough_videos():
    thin = build_profile([video(i, rehooks=(20, 50)) for i in range(3)])
    plan = plan_beats(60, "shorts", thin)
    rh = [b for b in plan if b["type"] == "rehook-cadence"]
    assert [b["pct"] for b in rh] == [35.0, 70.0] and all(b["source"] == "blueprint" for b in rh)
    rich = build_profile([video(i, rehooks=(20, 50)) for i in range(6)])
    rh2 = [b for b in plan_beats(60, "shorts", rich) if b["type"] == "rehook-cadence"]
    assert [round(b["pct"]) for b in rh2] == [20, 50] and all(b["source"] == "profile" for b in rh2)


def test_weighting_prefers_bigger_outliers():
    vids = [video(0, stakes_s=2.0, mult=32.0)] + [video(i, stakes_s=6.0, mult=1.0) for i in range(1, 4)]
    assert build_profile(vids)["per_type"]["stakes-line"]["median_s"] == 2.0


def test_learned_adjustment_moves_beat_earlier():
    vids = [video(i) for i in range(6)]
    base = build_profile(vids)["per_type"]["rehook-cadence"]["clusters_pct"]
    moved = build_profile(vids, [{"type": "rehook-cadence", "shift_pct": -5.0, "reason": "cliff"}])
    assert moved["per_type"]["rehook-cadence"]["clusters_pct"] == [round(c - 5, 1) for c in base]


def test_plan_has_every_short_form_beat_and_maps_to_clips():
    plan = plan_beats(60, "shorts", None)
    types = {b["type"] for b in plan}
    assert {"hook-placement", "stakes-line", "rehook-cadence", "payoff-timing", "cta-placement", "loop-ending"} <= types
    assert all(0 <= b["clip"] <= 5 for b in plan)
