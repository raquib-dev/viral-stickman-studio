"""Topic scorer: a pure function over evidence features, so every score on the board is explainable.

score = w_outlier * outlier_evidence + w_gap * gap + w_fit * stickman_fit + w_niche * niche_fit + w_news * news
(news: how strongly the topic's real items were reacted to and how fresh they are, against the best item found)
Each component is in [0, 1]. Weights come from config/settings.json (topic_weights).
"""
from __future__ import annotations

import math
import re
from typing import Any

DEFAULT_WEIGHTS = {"outlier_evidence": 0.35, "gap": 0.25, "stickman_fit": 0.20, "niche_fit": 0.20, "news": 0.30}
STOP = {"the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "with", "your", "you", "why", "how",
        "what", "is", "are", "this", "that", "it", "my", "i", "do", "does", "vs", "about", "from", "most"}


def keywords(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9']{3,}", text.lower()) if w not in STOP}


def related(topic_kw: set[str], item_text: str, min_overlap: int = 1) -> bool:
    return len(topic_kw & keywords(item_text)) >= min_overlap


def outlier_evidence(multiples: list[float]) -> float:
    """Mean log2 multiple of related outliers, capped at 16x, with a sample-size penalty below 3 items."""
    if not multiples:
        return 0.0
    vals = [min(4.0, math.log2(max(1.0, m))) / 4.0 for m in multiples]
    mean = sum(vals) / len(vals)
    return round(mean * min(1.0, len(vals) / 3.0), 3)


def gap_score(related_views: list[int], strong_supply: int, niche_median_views: float) -> float:
    """Demand (views on related videos vs the niche median) against supply (how many strong videos
    already cover it). Three or more strong existing videos make it crowded."""
    if not related_views:
        return 0.3  # unknown demand: neutral-low, never zero (the board says 'no evidence')
    demand = min(1.0, (sum(related_views) / len(related_views)) / max(1.0, niche_median_views * 3))
    crowd = min(1.0, strong_supply / 3.0)
    return round(max(0.0, demand * (1.0 - 0.7 * crowd)), 3)


def niche_fit(topic_kw: set[str], niche_kw: set[str], agent_rating: float | None = None) -> float:
    overlap = len(topic_kw & niche_kw) / max(1, len(topic_kw | niche_kw))
    jacc = min(1.0, overlap * 3)  # small vocabularies rarely overlap much
    if agent_rating is None:
        return round(jacc, 3)
    return round(0.5 * jacc + 0.5 * max(0.0, min(1.0, (agent_rating - 1) / 4)), 3)


def stickman_fit(rating_1_to_5: float) -> float:
    return round(max(0.0, min(1.0, (float(rating_1_to_5) - 1) / 4)), 3)


def score(components: dict[str, float], weights: dict[str, float] | None = None) -> float:
    w = {**DEFAULT_WEIGHTS, **(weights or {})}
    keys = [k for k in DEFAULT_WEIGHTS if k in components]     # no live news: the news weight does not count
    total = sum(w[k] for k in keys) or 1.0
    return round(sum(w[k] * float(components[k]) for k in keys) / total, 4)


def news_strength(news_ids: list[str], news: list[dict]) -> float:
    """The best of the topic's real items, against the best item found (0 when it rests on none)."""
    by_id = {n["id"]: n for n in news}
    top = max((float(n.get("score") or 0) for n in news), default=0.0)
    mine = [float(by_id[i].get("score") or 0) for i in news_ids or [] if i in by_id]
    return round(max(mine) / top, 3) if mine and top else 0.0


def score_candidates(candidates: list[dict], swipe: list[dict], niche_text: str,
                     weights: dict[str, float] | None = None, min_multiple: float = 1.5,
                     news: list[dict] | None = None) -> list[dict]:
    """candidates: [{id, title, angle, keywords?, stickman_fit (1-5), stickman_reason, niche_rating?}]
    swipe: [{title|hook, multiple, views, ...}] from discovery."""
    niche_kw = keywords(niche_text)
    views = sorted(int(s.get("views") or 0) for s in swipe if s.get("views"))
    niche_median = views[len(views) // 2] if views else 0
    out = []
    for c in candidates:
        kw = set(c.get("keywords") or []) | keywords(c["title"] + " " + c.get("angle", ""))
        rel = [s for s in swipe if related(kw, (s.get("title") or "") + " " + (s.get("hook") or ""), 2)]
        mults = [float(s["multiple"]) for s in rel if s.get("multiple")]
        strong = sum(1 for m in mults if m >= min_multiple)
        comp = {
            "outlier_evidence": outlier_evidence([m for m in mults if m >= min_multiple]),
            "gap": gap_score([int(s.get("views") or 0) for s in rel], strong, niche_median),
            "stickman_fit": stickman_fit(c.get("stickman_fit", 3)),
            "niche_fit": niche_fit(kw, niche_kw, c.get("niche_rating")),
        }
        if news:
            comp["news"] = news_strength(c.get("news_ids") or [], news)
        by_id = {n["id"]: n for n in news or []}
        srcs = [by_id[i] for i in c.get("news_ids") or [] if i in by_id]
        if srcs:                                      # the real posts the topic grows from, for the script and the board
            c = {**c, "sources": [{k: n.get(k) for k in ("id", "title", "url", "discussion_url", "where", "kind", "date",
                                                          "engagement", "comments", "synthetic")} for n in srcs]}
        out.append({**c, "components": comp, "score": score(comp, weights),
                    "evidence": [{"title": s.get("title") or s.get("hook"), "multiple": s.get("multiple"),
                                  "views": s.get("views"), "url": s.get("url"), "platform": s.get("platform"),
                                  "synthetic": bool(s.get("synthetic"))} for s in sorted(rel, key=lambda x: -(x.get("multiple") or 0))[:6]]})
    out.sort(key=lambda r: -r["score"])
    for i, r in enumerate(out, 1):
        r["rank"] = i
    return out
