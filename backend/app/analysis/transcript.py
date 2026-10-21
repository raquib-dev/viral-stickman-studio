"""Transcript parsing: SRT, WebVTT, YouTube json3 and plain {text,start,end} segments -> timed words."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, asdict


@dataclass
class Word:
    w: str
    s: float
    e: float


@dataclass
class Sentence:
    text: str
    s: float
    e: float


_TS = re.compile(r"(\d+:)?\d{1,2}:\d{2}[.,]\d{1,3}")


def _ts(v: str) -> float:
    v = v.strip().replace(",", ".")
    parts = v.split(":")
    if len(parts) == 3:
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
    return int(parts[0]) * 60 + float(parts[1])


def parse_cues(raw: str) -> list[tuple[float, float, str]]:
    raw = raw.lstrip("﻿")
    stripped = raw.strip()
    if stripped.startswith("{") or stripped.startswith("["):
        return _parse_json(json.loads(stripped))
    cues: list[tuple[float, float, list[str]]] = []
    cur = None
    for line in raw.splitlines():
        m = re.match(r"\s*([\d:.,]+)\s*-->\s*([\d:.,]+)", line)
        if m and _TS.fullmatch(m.group(1).strip()) and _TS.fullmatch(m.group(2).strip()):
            cur = [_ts(m.group(1)), _ts(m.group(2)), []]
            cues.append(cur)
        elif cur is not None and line.strip() and not line.strip().isdigit() and line.strip() != "WEBVTT":
            cur[2].append(re.sub(r"<[^>]+>", "", line.strip()))
    out = [(a, b, " ".join(t).strip()) for a, b, t in cues if t]
    # YouTube auto-caption VTTs repeat the previous line; drop exact rolling duplicates.
    dedup: list[tuple[float, float, str]] = []
    for c in out:
        if dedup and c[2] == dedup[-1][2]:
            continue
        dedup.append(c)
    return dedup


def _parse_json(d) -> list[tuple[float, float, str]]:
    if isinstance(d, dict) and "events" in d:  # YouTube json3
        out = []
        for ev in d["events"]:
            segs = ev.get("segs")
            if not segs:
                continue
            start = ev.get("tStartMs", 0) / 1000
            dur = ev.get("dDurationMs", 0) / 1000
            text = "".join(s.get("utf8", "") for s in segs).replace("\n", " ").strip()
            if text:
                out.append((start, start + dur, text))
        return out
    segs = d.get("segments", d) if isinstance(d, dict) else d
    return [(float(s["start"]), float(s["end"]), str(s.get("text", "")).strip()) for s in segs]


def cues_to_words(cues: list[tuple[float, float, str]]) -> list[Word]:
    """Spread each cue's words across its window, weighted by length (as kino's cue estimator does)."""
    words: list[Word] = []
    for s, e, text in cues:
        toks = text.split()
        if not toks:
            continue
        weights = [len(t) + 2 for t in toks]
        total = sum(weights)
        t = s
        for tok, w in zip(toks, weights):
            d = (e - s) * w / total
            words.append(Word(tok, round(t, 3), round(t + d, 3)))
            t += d
    return words


def sentences(words: list[Word]) -> list[Sentence]:
    """Split on terminal punctuation. Auto-captions usually have none, so when punctuation is sparse
    we split on pauses >= 0.5 s or every 14 words instead."""
    punctuated = sum(1 for w in words if re.search(r"[.!?]['\")]*$", w.w)) >= max(1, len(words) // 40)
    out, buf = [], []
    for i, w in enumerate(words):
        buf.append(w)
        nxt = words[i + 1] if i + 1 < len(words) else None
        if punctuated:
            end = bool(re.search(r"[.!?]['\")]*$", w.w))
        else:
            end = len(buf) >= 14 or (nxt is not None and nxt.s - w.e >= 0.5)
        if end:
            out.append(Sentence(" ".join(x.w for x in buf), buf[0].s, buf[-1].e))
            buf = []
    if buf:
        out.append(Sentence(" ".join(x.w for x in buf), buf[0].s, buf[-1].e))
    return out


def text_between(words: list[Word], start: float, end: float) -> str:
    return " ".join(w.w for w in words if w.s >= start and w.s < end)


def to_srt(words: list[Word], words_per_cue: int = 8) -> str:
    def fmt(t: float) -> str:
        ms = int(round(t * 1000))
        h, ms = divmod(ms, 3600_000)
        m, ms = divmod(ms, 60_000)
        s, ms = divmod(ms, 1000)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"
    out, n = [], 1
    for i in range(0, len(words), words_per_cue):
        chunk = words[i:i + words_per_cue]
        out.append(f"{n}\n{fmt(chunk[0].s)} --> {fmt(chunk[-1].e)}\n{' '.join(w.w for w in chunk)}\n")
        n += 1
    return "\n".join(out)


def words_json(words: list[Word]) -> list[dict]:
    return [asdict(w) for w in words]


def words_from_json(rows: list[dict]) -> list[Word]:
    return [Word(r["w"], float(r["s"]), float(r["e"])) for r in rows]
