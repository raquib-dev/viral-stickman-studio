"""Word timing for burned-in captions and an ASS subtitle builder (captions + hook card + callouts).

Timing source, best first: faster-whisper on the rendered audio (if installed and the audio is real
speech), else each clip's known VO text spread across its known window (exact clip boundaries,
approximate words). The method used is recorded in final/words.json.
"""
from __future__ import annotations

from pathlib import Path

from ..analysis.transcript import Word
from .overlays import TextBox, safe_margins, safe_zone_violations, text_box

VO_LEAD = 0.4   # seconds before the narrator starts inside a clip (kino's voStart)
VO_TAIL = 0.6


def estimate_words(clip_vos: list[str], clip_seconds: float = 10.0, durations: list[float] | None = None) -> list[Word]:
    """durations: each clip's real length (generated clips are not always exactly clip_seconds)."""
    words: list[Word] = []
    offset = 0.0
    for i, vo in enumerate(clip_vos):
        length = durations[i] if durations and i < len(durations) and durations[i] > 0 else clip_seconds
        clip_start, offset = offset, offset + length
        toks = vo.split()
        if not toks:
            continue
        start, end = clip_start + VO_LEAD, clip_start + length - VO_TAIL
        weights = [len(t) + 2 + (3 if t[-1:] in ",.;:!?" else 0) for t in toks]
        total = sum(weights)
        t = start
        for tok, w in zip(toks, weights):
            d = (end - start) * w / total
            words.append(Word(tok, round(t, 3), round(t + d * 0.92, 3)))
            t += d
    return words


def whisper_words(audio_or_video: Path, log=None) -> list[Word] | None:
    """None when faster-whisper is missing or fails (model download, broken install): captions fall back to
    the estimate instead of failing the stitch."""
    try:
        from faster_whisper import WhisperModel  # optional dependency
    except Exception:
        return None
    try:
        model = WhisperModel("base.en", device="cpu", compute_type="int8")
        segs, _ = model.transcribe(str(audio_or_video), word_timestamps=True)
        out = [Word(w.word.strip(), float(w.start), float(w.end)) for s in segs for w in (s.words or []) if w.word.strip()]
    except Exception as e:
        if log:
            log(f"faster-whisper failed ({type(e).__name__}: {str(e)[:200]}); using estimated caption timing", "warn")
        return None
    return out or None


def _ass_time(t: float) -> str:
    cs = int(round(max(0.0, t) * 100))
    h, cs = divmod(cs, 360000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _esc(text: str) -> str:
    return text.replace("\\", "\\\\").replace("{", "(").replace("}", ")").replace("\n", "\\N")


def build_ass(words: list[Word], ratio: str, frame_w: int, frame_h: int, hook_card: str | None = None,
              hook_until: float = 2.4, callouts: list[dict] | None = None, words_per_page: int = 3,
              captions: bool = True) -> tuple[str, list[str]]:
    """Return (ass_text, safe_zone_violations). Captions pop a page of 1-3 words, highlighting the
    spoken word. Hook card sits just under the top safe line from frame 0."""
    m = safe_margins(ratio)
    cap_size = int(frame_h * (0.045 if ratio == "9:16" else 0.06))
    hook_size = int(frame_h * (0.05 if ratio == "9:16" else 0.075))
    call_size = int(frame_h * (0.035 if ratio == "9:16" else 0.05))
    cap_bottom_margin = int(frame_h * (m["bottom"] + 0.02))
    hook_top = int(frame_h * (m["top"] + 0.01))
    # ASS margins: horizontal margins keep text inside the safe columns
    ml, mr = int(frame_w * m["left"]), int(frame_w * m["right"])
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {frame_w}
PlayResY: {frame_h}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,Arial,{cap_size},&H00FFFFFF,&H0000D7FF,&H00000000,&H80000000,1,0,0,0,100,100,0,0,1,{max(2, cap_size // 14)},0,2,{ml},{mr},{cap_bottom_margin},1
Style: Hook,Arial,{hook_size},&H00FFFFFF,&H00FFFFFF,&H00000000,&HB4000000,1,0,0,0,100,100,0,0,3,{max(4, hook_size // 6)},0,8,{ml},{mr},{hook_top},1
Style: Callout,Arial,{call_size},&H0000D7FF,&H00FFFFFF,&H00000000,&H96000000,1,0,0,0,100,100,0,0,3,{max(3, call_size // 6)},0,8,{ml},{mr},{int(frame_h * 0.30)},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events: list[str] = []
    boxes: list[TextBox] = []
    if hook_card:
        events.append(f"Dialogue: 2,{_ass_time(0)},{_ass_time(hook_until)},Hook,,0,0,0,,{_esc(hook_card.upper())}")
        boxes.append(text_box("hook card", hook_card.upper(), ratio, hook_top / frame_h, hook_size, frame_w, frame_h))
    for c in callouts or []:
        t0, t1 = float(c["t"]), float(c["t"]) + float(c.get("hold", 2.0))
        events.append(f"Dialogue: 1,{_ass_time(t0)},{_ass_time(t1)},Callout,,0,0,0,,{_esc(c['text'])}")
        boxes.append(text_box(f"callout @{t0:.1f}s", c["text"], ratio, 0.30, call_size, frame_w, frame_h))
    if captions and words:
        pages = [words[i:i + words_per_page] for i in range(0, len(words), words_per_page)]
        for page in pages:
            for j, w in enumerate(page):
                start = w.s
                end = page[j + 1].s if j + 1 < len(page) else w.e + 0.15
                parts = [("{\\c&H0000D7FF&}" + _esc(x.w) + "{\\c&H00FFFFFF&}") if x is w else _esc(x.w) for x in page]
                events.append(f"Dialogue: 0,{_ass_time(start)},{_ass_time(end)},Cap,,0,0,0,,{' '.join(parts)}")
        longest = max((" ".join(x.w for x in p) for p in pages), key=len)
        # captions are bottom-aligned (ASS alignment 2): the block grows upward from the margin
        box = text_box("captions", longest, ratio, 0.0, cap_size, frame_w, frame_h)
        box.y = 1 - (cap_bottom_margin / frame_h) - box.h
        boxes.append(box)
    return header + "\n".join(events) + "\n", safe_zone_violations(boxes, ratio)
