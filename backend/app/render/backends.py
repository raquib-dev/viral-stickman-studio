"""Backend factory."""
from __future__ import annotations

from .base import RenderBackend


def get_backend(name: str) -> RenderBackend:
    if name == "mock":
        from .mock import MockBackend
        return MockBackend()
    if name == "omni-gemini":
        from .omni_gemini import OmniGeminiBackend
        return OmniGeminiBackend()
    if name == "omni-fal":
        from .omni_fal import OmniFalBackend
        return OmniFalBackend()
    raise ValueError(f"unknown render backend {name!r}")
