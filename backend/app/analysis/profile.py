"""Niche pattern profile: aggregate per-video beat labels into where top videos in this niche place
each beat, build a timeline heatmap, and plan beats for a new video (profile first, blueprint default
when evidence is thin)."""
from __future__ import annotations

import math
from typing import Any

from . import blueprint as bp

HEATMAP_BINS = 20
MIN_VIDEOS_FOR_OVERRIDE = 5
PROFILE_TYPES = ("stakes-line", "rehook-cadence", "pattern-interrupt-cadence", "callout-placement",
                 "deliberate-mistake-placement", "payoff-timing", "cta-placement", "loop-ending", "hook-placement")


def _weight(multiple: float | None) -> float:
    # Weight by how far a video beat its own channel; a 1x video still counts a little.
    return max(0.25, math.log2(max(1.0, float(multiple or 1.0))) + 0.25)


def weighted_quantile(values: list[float], weights: list[float], q: float) -> float | None:
    if not values:
        return None
    pairs = sorted(zip(values, weights))
    total = sum(w for _, w in pairs)
    acc = 0.0
    for v, w in pairs:
        acc += w
        if acc >= q * total:
            return v
    return pairs[-1][0]


def _clusters(points: list[tuple[float, float]], min_gap: float = 15.0) -> list[list[tuple[float, float]]]:
    """Split sorted (pct, weight) points into at most two clusters at the largest gap >= min_gap."""
    pts = sorted(points)
    if len(pts) < 4:
        return [pts] if pts else []
    gaps = [(pts[i + 1][0] - pts[i][0], i) for i in range(len(pts) - 1)]
    g, i = max(gaps)
    if g < min_gap:
        return [pts]
    return [pts[: i + 1], pts[i + 1:]]


def build_profile(videos: list[dict], learned: list[dict] | None = None) -> dict[str, Any]:
    """videos: [{id, title, multiple, duration, labels:[...]}]. Labels with ok=False still count as a
    position (the beat exists) but are tallied separately as violations."""
    n = len(videos)
    per_type: dict[str, Any] = {}
    for rtype in PROFILE_TYPES:
        pts: list[tuple[float, float]] = []
        secs: list[tuple[float, float]] = []
        present, counts, vids, violations = 0.0, [], [], 0
        wsum = 0.0
        for v in videos:
            w = _weight(v.get("multiple"))
            wsum += w
            # Proxy labels are excluded, except for pattern interrupts where they are the only signal.
            ls = [l for l in v["labels"] if l["type"] == rtype
                  and (l.get("method") != "proxy" or rtype == "pattern-interrupt-cadence")]
            if ls:
                present += w
                vids.append(v["id"])
                counts.append(len(ls))
                violations += sum(1 for l in ls if not l.get("ok", True))
            for l in ls:
                pts.append((l["pct"], w))
                secs.append((l["t"], w))
        entry: dict[str, Any] = {
            "n_videos_with": len(vids), "presence_rate": round(present / wsum, 2) if wsum else 0.0,
            "median_count": sorted(counts)[len(counts) // 2] if counts else 0, "violations": violations,
            "videos": vids,
        }
        if pts:
            vals, ws = [p for p, _ in pts], [w for _, w in pts]
            entry["median_pct"] = weighted_quantile(vals, ws, 0.5)
            entry["iqr_pct"] = [weighted_quantile(vals, ws, 0.25), weighted_quantile(vals, ws, 0.75)]
            sv, sw = [s for s, _ in secs], [w for _, w in secs]
            entry["median_s"] = weighted_quantile(sv, sw, 0.5)
            entry["clusters_pct"] = [round(weighted_quantile([p for p, _ in c], [w for _, w in c], 0.5), 1)
                                     for c in _clusters(pts)]
        per_type[rtype] = entry

    profile = {"n_videos": n, "weighting": "log2(outlier multiple) + 0.25", "per_type": per_type,
               "heatmap": heatmap(videos), "learned": learned or [], "video_ids": [v["id"] for v in videos]}
    _apply_learned(profile)
    profile["summary"] = summarize(profile)
    return profile


def heatmap(videos: list[dict]) -> dict[str, Any]:
    """Rows = beat types, columns = 5% runtime bins, value = weighted share of videos with that beat there."""
    rows = []
    total_w = sum(_weight(v.get("multiple")) for v in videos) or 1.0
    for rtype in PROFILE_TYPES:
        row = [0.0] * HEATMAP_BINS
        for v in videos:
            w = _weight(v.get("multiple"))
            bins = {min(HEATMAP_BINS - 1, int(l["pct"] / 100 * HEATMAP_BINS)) for l in v["labels"] if l["type"] == rtype}
            for b in bins:
                row[b] += w
        rows.append({"type": rtype, "values": [round(x / total_w, 3) for x in row]})
    return {"bins": HEATMAP_BINS, "bin_pct": 100 / HEATMAP_BINS, "rows": rows}


def _apply_learned(profile: dict) -> None:
    """Learn loop: a retention cliff just before a planned beat pulls that beat earlier next time."""
    for adj in profile.get("learned", []):
        rtype, shift = adj.get("type"), float(adj.get("shift_pct", 0))
        e = profile["per_type"].get(rtype)
        if not e or "median_pct" not in e:
            e = profile["per_type"].setdefault(rtype, {})
            e.setdefault("learned_only", True)
        if "median_pct" in e:
            e["median_pct"] = round(max(0.0, min(100.0, e["median_pct"] + shift)), 1)
            if e.get("clusters_pct"):
                e["clusters_pct"] = [round(max(0.0, min(100.0, c + shift)), 1) for c in e["clusters_pct"]]
        e.setdefault("learned_adjustments", []).append(adj)


def summarize(profile: dict) -> list[str]:
    pt, n = profile["per_type"], profile["n_videos"]
    out = []
    if n == 0:
        return ["No outlier transcripts yet: beat placement uses the blueprint defaults."]
    r = pt.get("rehook-cadence", {})
    if r.get("clusters_pct"):
        out.append(f"Top videos re-hook at ~{' and ~'.join(f'{c:.0f}%' for c in r['clusters_pct'])} "
                   f"({r['n_videos_with']}/{n} videos).")
    s = pt.get("stakes-line", {})
    if s.get("median_s") is not None:
        out.append(f"Stakes line by ~0:{int(round(s['median_s'])):02d} ({s['n_videos_with']}/{n} videos).")
    p = pt.get("payoff-timing", {})
    if p.get("median_pct") is not None:
        out.append(f"Payoff lands around {p['median_pct']:.0f}% of runtime ({p['n_videos_with']}/{n}).")
    m = pt.get("deliberate-mistake-placement", {})
    out.append(f"Comment-bait mistake in {m.get('n_videos_with', 0)}/{n} videos.")
    c = pt.get("cta-placement", {})
    if c.get("n_videos_with"):
        out.append(f"CTA around {c.get('median_pct', 0):.0f}%; median {c['median_count']} ask(s) per video"
                   + (f"; {c['violations']} multi-ask/early-ask violations." if c.get("violations") else "."))
    lp = pt.get("loop-ending", {})
    out.append(f"Loop ending (last line echoes the hook) in {lp.get('n_videos_with', 0)}/{n} labelled videos.")
    if n < MIN_VIDEOS_FOR_OVERRIDE:
        out.append(f"Only {n} videos: below {MIN_VIDEOS_FOR_OVERRIDE}, so planning still uses blueprint defaults.")
    return out


# ---- planning -------------------------------------------------------------------------------

def plan_beats(duration: float, fmt: str, profile: dict | None, include_mistake: bool | None = None) -> list[dict]:
    """Concrete beat positions for a new video. Profile medians replace blueprint defaults for
    profile_overridable rules once the profile has >= MIN_VIDEOS_FOR_OVERRIDE videos with that beat."""
    pt = (profile or {}).get("per_type", {})

    def use(rtype: str) -> dict | None:
        e = pt.get(rtype) or {}
        if e.get("n_videos_with", 0) >= MIN_VIDEOS_FOR_OVERRIDE or e.get("learned_adjustments"):
            return e
        return None

    plan: list[dict] = []

    def add(rtype: str, rule_id: str, t: float, source: str, note: str = "") -> None:
        t = max(0.0, min(duration, t))
        plan.append({"type": rtype, "rule_id": rule_id, "t": round(t, 2), "pct": round(100 * t / duration, 1),
                     "source": source, "note": note, "clip": int(min(duration - 0.01, t) // 10)})

    add("hook-placement", "hook-first-line-3s", 0.0, "blueprint", "opening line lands within 3 s")
    short = fmt in ("shorts", "reels")
    e = use("stakes-line")
    if e and e.get("median_s") is not None:
        add("stakes-line", "stakes-line-early" if short else "stakes-line-long", e["median_s"], "profile")
    else:
        add("stakes-line", "stakes-line-early" if short else "stakes-line-long", 4.0 if short else 12.0, "blueprint")
    e = use("rehook-cadence")
    anchors = e.get("clusters_pct") if e else [35.0, 70.0]
    for a in anchors[:3]:
        add("rehook-cadence", "rehook-stage-boundaries", a / 100 * duration, "profile" if e else "blueprint")
    if not short:
        for t in range(150, int(duration) - 30, 180):
            add("rehook-cadence", "rehook-long-every-3min", float(t), "blueprint", "lore default")
    e = use("deliberate-mistake-placement")
    wants_mistake = include_mistake if include_mistake is not None else bool(e and e.get("presence_rate", 0) >= 0.3)
    if wants_mistake:
        add("deliberate-mistake-placement", "deliberate-mistake-one",
            (e["median_pct"] if e and e.get("median_pct") is not None else 45.0) / 100 * duration,
            "profile" if e else "blueprint", "visual/trivial only; never in a fact")
    e = use("payoff-timing")
    add("payoff-timing", "payoff-before-final-quarter",
        (e["median_pct"] if e and e.get("median_pct") is not None else 75.0) / 100 * duration,
        "profile" if e else "blueprint")
    add("cta-placement", "cta-one-at-payoff", (0.9 if short else 0.85) * duration, "blueprint", "exactly one ask")
    if short:
        add("loop-ending", "loop-ending-echo", duration - 1.5, "blueprint", "last line echoes a hook word")
    else:
        add("end-screen-hold", "end-screen-hold-long", duration - 15.0, "blueprint", "keep final 5-20 s clean")
    step = 12.0
    t = step
    while t < duration - 3:
        add("pattern-interrupt-cadence", "pattern-interrupt-cadence", t, "blueprint", "stage-level interrupt")
        t += step
    plan.sort(key=lambda b: (b["t"], b["type"]))
    return plan
