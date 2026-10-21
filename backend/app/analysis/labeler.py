"""Label every beat of a transcript against virality-blueprint.json.

Deterministic regex/timing labels come first (unit-tested). Judgement labels from the LLM (Sonnet)
are merged in when available and keep `method: "llm"`. A label is a judgement about the WORDS of a
transcript, never proof that the technique caused a video's performance.
"""
from __future__ import annotations

import re
from typing import Any

from . import blueprint as bp
from .transcript import Sentence, Word, sentences, text_between

STOP = {"the", "a", "an", "and", "or", "but", "if", "of", "to", "in", "on", "for", "with", "that", "this",
        "it", "is", "are", "was", "were", "be", "been", "you", "your", "i", "my", "me", "we", "our", "they",
        "them", "so", "just", "not", "no", "do", "did", "does", "have", "has", "had", "will", "can", "at",
        "as", "by", "from", "out", "up", "off", "one", "all", "what", "why", "how", "its", "it's", "that's"}
INTERRUPT_OPENERS = re.compile(r"(?i)^(now|wait|look|imagine|picture|okay so|here'?s|so here'?s|stop)\b")
YOU = re.compile(r"(?i)\b(you|your|you're|yourself)\b")


def _label(rtype: str, fmt: str, t: float, duration: float, quote: str, method: str,
           ok: bool = True, confidence: float = 0.7, note: str = "") -> dict[str, Any]:
    r = bp.primary_rule(rtype, fmt)
    return {"rule_id": r["id"] if r else rtype, "type": rtype, "t": round(t, 2),
            "pct": round(100 * t / duration, 1) if duration else 0.0, "quote": quote[:160],
            "method": method, "ok": ok, "confidence": confidence, "note": note}


def _any(pats, text: str) -> bool:
    return any(p.search(text) for p in pats)


def _content_words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9$%']+", text.lower()) if w not in STOP and len(w) > 2}


def label_transcript(words: list[Word], duration: float | None = None, fmt: str = "shorts",
                     llm: dict[str, list[dict]] | None = None) -> list[dict]:
    """Return labels sorted by time. `llm` maps blueprint type -> [{t, quote}] judgement answers."""
    if not words:
        return []
    duration = duration or words[-1].e
    sents: list[Sentence] = sentences(words)
    labels: list[dict] = []

    # Hook: the words before 3 s, failing on greeting/preamble patterns.
    hook_rule = bp.rule("hook-first-line-3s")
    first = text_between(words, 0, 3.0) or sents[0].text
    bad = _any(bp.patterns(hook_rule["id"]), first)
    labels.append(_label("hook-placement", fmt, 0.0, duration, first, "regex", ok=not bad, confidence=0.9,
                         note="greeting or preamble in the first 3 s" if bad else ""))

    # No intro sequence in the first 5 s.
    intro_txt = text_between(words, 0, 5.0)
    if _any(bp.patterns("no-intro-sequence"), intro_txt):
        labels.append(_label("no-intro", fmt, 0.0, duration, intro_txt, "regex", ok=False, confidence=0.9,
                             note="intro/greeting phrase in the first 5 s"))

    stake_pats = bp.patterns("stakes-line-early")
    rehook_pats = bp.patterns("rehook-stage-boundaries")
    payoff_pats = bp.patterns("payoff-before-final-quarter")
    cta_pats = bp.patterns("cta-one-at-payoff")
    callout_pats = bp.patterns("callout-on-stressed-word")

    stake_found = False
    payoff_found = False
    prev_end = 0.0
    for i, s in enumerate(sents):
        pct = s.s / duration if duration else 0
        # Stakes: cost vocabulary or a figure, aimed at the viewer, first occurrence only.
        if not stake_found and _any(stake_pats, s.text) and (YOU.search(s.text) or "$" in s.text):
            labels.append(_label("stakes-line", fmt, s.s, duration, s.text, "regex"))
            stake_found = True
        # Re-hooks: pivot phrases after the opening.
        if pct >= 0.12 and _any(rehook_pats, s.text):
            labels.append(_label("rehook-cadence", fmt, s.s, duration, s.text, "regex", confidence=0.6))
        # Payoff: first answer marker after 40% of runtime.
        if not payoff_found and pct >= 0.4 and _any(payoff_pats, s.text):
            labels.append(_label("payoff-timing", fmt, s.s, duration, s.text, "regex", confidence=0.6))
            payoff_found = True
        # CTA asks.
        if _any(cta_pats, s.text):
            labels.append(_label("cta-placement", fmt, s.s, duration, s.text, "regex", ok=pct >= 0.15,
                                 confidence=0.8, note="" if pct >= 0.15 else "ask before 15% of runtime"))
        # Callouts: sentences carrying a figure; the label sits on the number word.
        if i > 0 and _any(callout_pats[:1], s.text):
            num_word = next((w for w in words if s.s <= w.s <= s.e and re.search(r"\d", w.w)), None)
            if num_word:
                labels.append(_label("callout-placement", fmt, num_word.s, duration, s.text, "regex", confidence=0.5))
        # Pattern-interrupt proxy: a pause >= 0.7 s or an interrupt opener (transcripts cannot see cuts).
        if i > 0 and s.s > 3.0 and (s.s - prev_end >= 0.7 or INTERRUPT_OPENERS.search(s.text)):
            labels.append(_label("pattern-interrupt-cadence", fmt, s.s, duration, s.text, "proxy", confidence=0.3,
                                 note="transcript proxy: pause or interrupt opener; cuts are not visible in words"))
        prev_end = s.e

    # One ask rule.
    asks = [l for l in labels if l["type"] == "cta-placement"]
    if len(asks) > 1:
        for a in asks[1:]:
            a["ok"] = False
            a["note"] = (a["note"] + "; " if a["note"] else "") + f"{len(asks)} asks in one video"

    # Loop: last sentence shares a content word with the first.
    if len(sents) >= 2:
        shared = _content_words(sents[0].text) & _content_words(sents[-1].text)
        labels.append(_label("loop-ending", fmt, sents[-1].s, duration, sents[-1].text, "regex", ok=bool(shared),
                             confidence=0.8, note=("echoes: " + ", ".join(sorted(shared)[:3])) if shared
                             else "last line shares no word with the hook"))

    # Merge LLM judgements (deliberate mistakes, payoff, re-hooks the regex missed).
    for rtype, answers in (llm or {}).items():
        if rtype not in bp.LABELED_TYPES:
            continue
        for a in answers or []:
            t = float(a.get("t", 0))
            dup = any(l["type"] == rtype and abs(l["t"] - t) < 1.5 for l in labels)
            if dup:
                continue
            labels.append(_label(rtype, fmt, t, duration, str(a.get("quote", "")), "llm",
                                 confidence=float(a.get("confidence", 0.6))))

    labels.sort(key=lambda l: (l["t"], l["type"]))
    return labels


def summarize(labels: list[dict]) -> dict[str, Any]:
    by_type: dict[str, list[float]] = {}
    for l in labels:
        by_type.setdefault(l["type"], []).append(l["pct"])
    return {t: {"count": len(v), "pct": v} for t, v in by_type.items()}
