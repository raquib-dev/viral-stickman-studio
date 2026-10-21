"""Verbatim text pulled from the vendored directing-stickman-videos skill, so anchors and the voice
block are never retyped (and drift) in our code. Used by the Phase B checker and the dry-run fixture."""
from __future__ import annotations

import functools
import re

from ..paths import SKILLS

REF = SKILLS / "directing-stickman-videos" / "references"
STYLES = {
    "1": "Style 1 (Classic Minimalist)",
    "2A": "Style 2A (Modern Studio Tech)",
    "2B": "Style 2B (Cinematic Story)",
    "3": "Style 3 (Prehistoric Hand-Drawn / Dark Comedy)",
    "4": "Style 4 (Cozy Storytelling)",
    "5": "Style 5 (Historical Cartoon)",
}


@functools.lru_cache(maxsize=None)
def _text(name: str) -> str:
    return (REF / name).read_text(encoding="utf-8")


def _block_after(text: str, marker: str) -> str:
    i = text.index(marker)
    m = re.search(r"```text\n(.*?)\n```", text[i:], re.S)
    if not m:
        raise ValueError(f"no text block after {marker!r}")
    return m.group(1).strip()


def style1_anchor(theme: str = "dark", expressions: bool = True) -> str:
    """The tested Style 1 base. By default the skill swaps the faceless clause for simple expressions
    unless the user asks for a faceless figure (style-catalog.md, Character DNA)."""
    marker = "**Classic Dark — tested faceless base:**" if theme == "dark" else "**Classic Light — tested faceless base:**"
    base = _block_after(_text("style-catalog.md"), marker)
    if expressions:
        base = base.replace("no face, no eyes, no mouth,", "occasional simple line expressions, no detailed facial features,")
    return base


def style2_anchor(first_clip: bool) -> str:
    t = _text("style-catalog.md")
    return _block_after(t, "**Clip 1 Character Anchor:**" if first_clip else "**Subsequent Clips Character Anchor")


def style4_anchor() -> str:
    return _block_after(_text("cozy-storytelling.md"), "Default anchor")


def style5_anchor() -> str:
    return _block_after(_text("historical-cartoon.md"), "Repeat this anchor verbatim")


def anchor_for(style: str, theme: str = "dark", clip_index: int = 0) -> str:
    if style == "1":
        return style1_anchor(theme)
    if style in ("2A", "2B"):
        return style2_anchor(clip_index == 0)
    if style == "4":
        return style4_anchor()
    if style == "5":
        return style5_anchor()
    raise ValueError(f"style {style} needs story-specific cast cards (Style 3); no fixed anchor")


def male_voice_block() -> str:
    return _block_after(_text("voice-continuity.md"), "The following complete male block")


def female_voice_block() -> str:
    """The illustrative female profile, read verbatim from examples.md (not provider-tested, per the skill)."""
    for line in _text("examples.md").splitlines():
        if line.startswith("One off-screen adult female narrator throughout."):
            return line.strip()
    raise ValueError("female voice block not found in examples.md")


COLOR_NOTATION = re.compile(r"#[0-9a-fA-F]{3,8}\b|\brgba?\s*\(|\bhsla?\s*\(|\bpantone\b", re.I)
