"""Load the virality blueprint and turn its rules into concrete beat windows for a given video."""
from __future__ import annotations

import functools
import json
import re
from typing import Any

from ..paths import BLUEPRINT

FORMATS = ("shorts", "reels", "long")
LABELED_TYPES = ("hook-placement", "no-intro", "stakes-line", "rehook-cadence", "pattern-interrupt-cadence",
                 "callout-placement", "deliberate-mistake-placement", "payoff-timing", "cta-placement",
                 "loop-ending")


@functools.lru_cache(maxsize=1)
def load() -> dict[str, Any]:
    return json.loads(BLUEPRINT.read_text(encoding="utf-8"))


def rules(fmt: str | None = None) -> list[dict]:
    rs = load()["rules"]
    return [r for r in rs if fmt is None or fmt in r["timing"]["formats"]]


def rule(rule_id: str) -> dict:
    for r in load()["rules"]:
        if r["id"] == rule_id:
            return r
    raise KeyError(rule_id)


def primary_rule(rtype: str, fmt: str) -> dict | None:
    for r in rules(fmt):
        if r["type"] == rtype:
            return r
    return None


@functools.lru_cache(maxsize=None)
def patterns(rule_id: str) -> tuple[re.Pattern, ...]:
    return tuple(re.compile(p) for p in rule(rule_id)["how_to_detect"].get("patterns", []))


def format_for(duration: float, ratio: str, platforms: list[str] | None = None) -> str:
    """Pick the blueprint format: vertical up to 3 min is short-form (Shorts/Reels), else long."""
    if ratio == "9:16" and duration <= 180:
        plats = platforms or []
        if "reels" in plats and "shorts" not in plats:
            return "reels"
        return "shorts"
    return "long"


def window_seconds(r: dict, duration: float) -> tuple[float, float] | None:
    t = r["timing"]
    if "from" not in t:
        return None
    lo = t["from"]
    hi = t.get("to", t["from"])
    if t["mode"] == "percent":
        lo, hi = lo / 100 * duration, hi / 100 * duration
    if t.get("from_end"):
        lo, hi = max(0.0, duration - hi), max(0.0, duration - lo)
    return (round(min(lo, duration), 2), round(min(hi, duration), 2))
