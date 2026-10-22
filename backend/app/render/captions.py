"""Word timing for burned-in captions and an ASS subtitle builder (captions + hook card + callouts).

Timing source, best first: faster-whisper on the rendered audio (if installed and the audio is real
speech), else each clip's known VO text spread across its known window (exact clip boundaries,
approximate words). The method used is recorded in final/words.json.
"""
from __future__ import annotations

import re
from pathlib import Path

from ..analysis.transcript import Word
from .overlays import TextBox, safe_margins, safe_zone_violations, text_box

VO_LEAD = 0.4   # seconds before the narrator starts inside a clip (kino's voStart)
VO_TAIL = 0.6


def estimate_words(clip_vos: list[str], clip_seconds: float = 10.0, durations: list[float] | None = None,
                   windows: list[list[float] | None] | None = None) -> list[Word]:
    """durations: each clip's real length (generated clips are not always exactly clip_seconds).
    windows: where the voice really is inside each clip ([start, end] seconds, from the local TTS), so the
    estimate follows the audio instead of spreading words over the whole clip."""
    words: list[Word] = []
    offset = 0.0
    for i, vo in enumerate(clip_vos):
        length = durations[i] if durations and i < len(durations) and durations[i] > 0 else clip_seconds
        clip_start, offset = offset, offset + length
        toks = clean_text(vo).split()
        if not toks:
            continue
        win = windows[i] if windows and i < len(windows) else None
        if win and win[1] - win[0] > 0.3:
            start, end = clip_start + win[0], clip_start + min(length, win[1])
        else:
            start, end = clip_start + VO_LEAD, clip_start + length - VO_TAIL
        weights = [len(t) + 2 + (3 if t[-1:] in ",.;:!?" else 0) for t in toks]
        total = sum(weights)
        t = start
        for tok, w in zip(toks, weights):
            d = (end - start) * w / total
            words.append(Word(tok, round(t, 3), round(t + d * 0.92, 3)))
            t += d
    return words


def whisper_device(device: str = "auto") -> tuple[str, str]:
    """(device, compute_type). auto = the GPU when CTranslate2 sees CUDA, else the CPU."""
    if device == "auto":
        try:
            import ctranslate2
            device = "cuda" if ctranslate2.get_cuda_device_count() > 0 else "cpu"
        except Exception:
            device = "cpu"
    return device, ("float16" if device == "cuda" else "int8")


def whisper_words(audio_or_video: Path, log=None, model_name: str = "base.en", device: str = "auto") -> list[Word] | None:
    """None when faster-whisper is missing or fails (model download, broken install): captions fall back to
    the estimate instead of failing the stitch."""
    try:
        from faster_whisper import WhisperModel  # optional dependency
    except Exception:
        return None
    try:
        dev, compute = whisper_device(device)
        if log:
            log(f"faster-whisper {model_name} on {dev} ({compute})")
        model = WhisperModel(model_name, device=dev, compute_type=compute)
        segs, _ = model.transcribe(str(audio_or_video), word_timestamps=True)
        out = [Word(w.word.strip(), float(w.start), float(w.end)) for s in segs for w in (s.words or []) if w.word.strip()]
    except Exception as e:
        if log:
            log(f"faster-whisper failed ({type(e).__name__}: {str(e)[:200]}); using estimated caption timing", "warn")
        return None
    return out or None


def dedupe_words(words: list[Word]) -> list[Word]:
    """Drop a word repeated back-to-back with overlapping times (a transcription echo), keep real repeats."""
    out: list[Word] = []
    for w in words:
        if out and w.w.lower().strip(".,!?") == out[-1].w.lower().strip(".,!?") and w.s < out[-1].e:
            continue
        out.append(w)
    return out


def groq_words(audio_or_video: Path, log=None, model: str = "whisper-large-v3-turbo", transport=None,
               base_url: str | None = None) -> list[Word] | None:
    """Word timings from Groq's hosted Whisper (OpenAI-compatible /audio/transcriptions, verbose_json with word
    timestamps). The audio is sent as a small 16 kHz mono MP3. None on any failure (captions then fall back)."""
    import httpx

    from ..settings import load_settings, secret
    from .media import run_ffmpeg
    key = secret("GROQ_API_KEY")
    if not key:
        if log:
            log("Groq captions: GROQ_API_KEY is not set in .env; using the fallback timing", "warn")
        return None
    base = (base_url or load_settings()["agent"]["groq"]["base_url"]).rstrip("/")
    mp3 = Path(audio_or_video).with_suffix(".groq-asr.mp3")
    try:
        run_ffmpeg(["-i", str(audio_or_video), "-vn", "-ac", "1", "-ar", "16000", "-b:a", "48k", str(mp3)])
        with httpx.Client(timeout=300, transport=transport) as http:
            r = http.post(f"{base}/audio/transcriptions", headers={"Authorization": f"Bearer {key}"},
                          data={"model": model, "response_format": "verbose_json", "timestamp_granularities[]": "word",
                                "language": "en", "temperature": "0"},
                          files={"file": (mp3.name, mp3.read_bytes(), "audio/mpeg")})
        if r.status_code != 200:
            raise RuntimeError(f"HTTP {r.status_code}: {r.text[:200]}")
        d = r.json()
        raw = d.get("words") or [w for s in d.get("segments", []) for w in s.get("words", [])]
        out = [Word(str(w["word"]).strip(), float(w["start"]), float(w["end"])) for w in raw if str(w.get("word", "")).strip()]
        if log:
            log(f"Groq Whisper ({model}): {len(out)} words timed")
        return out or None
    except Exception as e:
        if log:
            log(f"Groq captions failed ({type(e).__name__}: {str(e)[:200]}); using the fallback timing", "warn")
        return None
    finally:
        mp3.unlink(missing_ok=True)


def _ass_time(t: float) -> str:
    cs = int(round(max(0.0, t) * 100))
    h, cs = divmod(cs, 360000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


PLACEHOLDER = re.compile(r"\{\{\s*([^{}]*?)\s*\}\}|\(\(\s*([^()]*?)\s*\)\)")


def clean_text(text: str) -> str:
    """A template placeholder that reached the narration ("{{your number}}") is shown as its words, never braces."""
    return PLACEHOLDER.sub(lambda m: m.group(1) or m.group(2) or "", text or "")


def phrase_pages(words: list[Word], max_words: int = 3, gap: float = 0.55) -> list[list[Word]]:
    """Group words into caption pages: at most max_words, and a page ends at sentence punctuation or a pause, so
    a page never straddles two sentences or a breath."""
    pages, cur = [], []
    for w in words:
        if cur and (len(cur) >= max_words or w.s - cur[-1].e > gap or cur[-1].w[-1:] in ".!?"):
            pages.append(cur); cur = []
        cur.append(w)
    if cur:
        pages.append(cur)
    return pages


def page_events(pages: list[list[Word]], hold: float = 0.15) -> list[tuple[float, float, int, int]]:
    """(start, end, page, word) for every highlighted word. No two events overlap: a page's last word holds at most
    `hold` seconds and never past the next page's first word (overlaps made ASS stack two lines)."""
    out = []
    for p, page in enumerate(pages):
        nxt = pages[p + 1][0].s if p + 1 < len(pages) else float("inf")
        for j, w in enumerate(page):
            start = max(w.s, out[-1][1] if out else 0.0)
            end = page[j + 1].s if j + 1 < len(page) else min(w.e + hold, nxt)
            end = max(end, start + 0.04)
            if out and start < out[-1][1]:
                start = out[-1][1]
            out.append((round(start, 3), round(end, 3), p, j))
    return out


def _esc(text: str) -> str:
    text = clean_text(text)
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
Style: Cap,Arial,{cap_size},&H00FFFFFF,&H0000D7FF,&H00000000,&H90000000,1,0,0,0,100,100,0,0,1,{max(3, cap_size // 11)},{max(1, cap_size // 24)},2,{ml},{mr},{cap_bottom_margin},1
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
        words = dedupe_words(words)
        pages = phrase_pages(words, words_per_page)
        for start, end, p, j in page_events(pages):
            page = pages[p]
            parts = [("{\\c&H0000D7FF&}" + _esc(x.w) + "{\\c&H00FFFFFF&}") if k == j else _esc(x.w) for k, x in enumerate(page)]
            events.append(f"Dialogue: 0,{_ass_time(start)},{_ass_time(end)},Cap,,0,0,0,,{' '.join(parts)}")
        longest = max((" ".join(x.w for x in p) for p in pages), key=len)
        # captions are bottom-aligned (ASS alignment 2): the block grows upward from the margin
        box = text_box("captions", longest, ratio, 0.0, cap_size, frame_w, frame_h)
        box.y = 1 - (cap_bottom_margin / frame_h) - box.h
        boxes.append(box)
    return header + "\n".join(events) + "\n", safe_zone_violations(boxes, ratio)


def build_line_ass(lines: list[dict], ratio: str, frame_w: int, frame_h: int, captions: bool = True) -> tuple[str, list[str]]:
    """Dialogue captions: each line whole, centred near the top (clear of faces), small white text on a
    translucent dark box, a quick fade. `lines` carry start/end in seconds. Returns (ass_text, safe-zone problems)."""
    m = safe_margins(ratio)
    size = int(frame_h * (0.03 if ratio == "9:16" else 0.045))
    # the reference reels put the box's top edge at 10-12 % of the height, over the window and above the heads,
    # a little higher than the platforms' 14 % guide; only the width is checked against the safe zone
    top = int(frame_h * (0.115 if ratio == "9:16" else m["top"] + 0.01))
    ml, mr = int(frame_w * max(m["left"], 0.12)), int(frame_w * max(m["right"], 0.12))
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {frame_w}
PlayResY: {frame_h}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Line,Arial,{size},&H00FFFFFF,&H00FFFFFF,&H3336302B,&H00000000,1,0,0,0,100,100,0,0,3,{max(3, size // 5)},0,8,{ml},{mr},{top},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events, boxes = [], []
    if captions:
        for ln in lines:
            if ln["end"] <= ln["start"]:
                continue
            events.append(f"Dialogue: 0,{_ass_time(ln['start'])},{_ass_time(ln['end'])},Line,,0,0,0,,{{\\fad(160,0)}}{_esc(ln['text'])}")
        if lines:
            longest = max((ln["text"] for ln in lines), key=len)
            boxes.append(text_box("line captions", longest, ratio, max(top / frame_h, m["top"]), size, frame_w, frame_h))
    return header + "\n".join(events) + "\n", safe_zone_violations(boxes, ratio)
