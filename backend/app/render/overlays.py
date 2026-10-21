"""Safe zones for post-production text (blueprint rule text-safe-zone-9x16) and a validator."""
from __future__ import annotations

import textwrap
from dataclasses import dataclass

# fractions of the frame: top, bottom, left, right (docs/research/video-direction.md section 4)
SAFE_9x16 = {"top": 0.14, "bottom": 0.35, "left": 0.06, "right": 0.21}
SAFE_16x9 = {"top": 0.06, "bottom": 0.10, "left": 0.05, "right": 0.05}


def safe_margins(ratio: str) -> dict[str, float]:
    return SAFE_9x16 if ratio == "9:16" else SAFE_16x9


@dataclass
class TextBox:
    name: str
    x: float  # left edge, fraction of width
    y: float  # top edge, fraction of height
    w: float
    h: float


def text_box(name: str, text: str, ratio: str, top_y: float, font_px: int, frame_w: int, frame_h: int) -> TextBox:
    """Approximate the block a centred, ASS-wrapped text occupies. ASS wraps inside the left/right
    margins we set to the safe columns, so width is bounded by them; the risk is vertical (a long
    text wrapping down into the caption band or the bottom UI), which is what the validator checks."""
    m = safe_margins(ratio)
    avail_px = (1 - m["left"] - m["right"]) * frame_w
    glyph = font_px * 0.55  # average glyph width in em for a bold sans
    per_line = max(1, int(avail_px // glyph))
    lines = textwrap.wrap(text, per_line) or [""]
    w = min(avail_px, max(len(l) for l in lines) * glyph) / frame_w
    h = len(lines) * font_px * 1.25 / frame_h
    return TextBox(name, safe_center_x(ratio) - w / 2, top_y, w, h)


def safe_zone_violations(boxes: list[TextBox], ratio: str) -> list[str]:
    m = safe_margins(ratio)
    out = []
    for b in boxes:
        if b.y < m["top"] - 1e-6:
            out.append(f"{b.name}: top edge {b.y:.2f} above safe line {m['top']:.2f}")
        if b.y + b.h > 1 - m["bottom"] + 1e-6:
            out.append(f"{b.name}: bottom edge {b.y + b.h:.2f} below safe line {1 - m['bottom']:.2f}")
        if b.x < m["left"] - 1e-6:
            out.append(f"{b.name}: left edge {b.x:.2f} outside {m['left']:.2f}")
        if b.x + b.w > 1 - m["right"] + 1e-6:
            out.append(f"{b.name}: right edge {b.x + b.w:.2f} outside {1 - m['right']:.2f}")
    return out


def safe_center_x(ratio: str) -> float:
    m = safe_margins(ratio)
    return (m["left"] + (1 - m["right"])) / 2
