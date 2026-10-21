"""Render backend interface. Every backend renders one clip at a time from a Phase B prompt."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Protocol


@dataclass
class ClipSpec:
    index: int                    # 0-based
    prompt: str                   # Phase B prompt, verbatim
    ratio: str                    # "16:9" | "9:16"
    resolution: str               # "360p" | "720p" | "1080p" | "4k"
    duration: float = 10.0
    continuity: str = "none"      # "none" | "first_frame" | "extend"
    out_path: Path | None = None
    label: str = ""
    vo: str = ""


@dataclass
class ClipResult:
    index: int
    path: Path
    duration: float
    cost_usd: float
    backend: str
    interaction_id: str | None = None
    last_frame: Path | None = None
    meta: dict = field(default_factory=dict)


class RenderError(RuntimeError):
    def __init__(self, msg: str, retryable: bool = True):
        super().__init__(msg)
        self.retryable = retryable


Log = Callable[[str], None]


class RenderBackend(Protocol):
    name: str

    async def render_clip(self, clip: ClipSpec, prev: ClipResult | None, log: Log) -> ClipResult: ...
