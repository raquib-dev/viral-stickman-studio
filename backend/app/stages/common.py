"""Helpers shared by stages."""
from __future__ import annotations

import asyncio
import re
from typing import Any, Callable

from ..analysis import blueprint as bp

PLATFORM_NAMES = {"youtube_long": "YouTube long-form", "shorts": "YouTube Shorts", "reels": "Instagram Reels"}


async def th(fn: Callable, *args, **kwargs) -> Any:
    """Run a blocking call (tool subprocess, ffmpeg, HTTP) off the event loop."""
    return await asyncio.to_thread(fn, *args, **kwargs)


def fmt_for_project(p: dict) -> str:
    return bp.format_for(float(p["duration"]), p["ratio"], p.get("platforms", []))


def primary_hook_panel(fmt: str, platforms: list[str]) -> str:
    """docs/repo-analysis.md C4: short-form ranks by the ig panel, long-form by yt; mixed -> mean."""
    has_short = any(x in platforms for x in ("shorts", "reels"))
    has_long = "youtube_long" in platforms
    if has_short and has_long:
        return "mean"
    return "ig" if fmt in ("shorts", "reels") else "yt"


def split_sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s.strip()]


def word_count(text: str) -> int:
    return len(text.split())
