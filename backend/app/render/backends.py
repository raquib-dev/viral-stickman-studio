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
    if name == "local-threejs":
        from .threejs import ThreeJSBackend
        return ThreeJSBackend()
    if name == "local-stickman":
        from .local import LocalStickmanBackend
        return LocalStickmanBackend()
    if name == "local-comfyui":
        from .local import ComfyUIBackend
        return ComfyUIBackend()
    raise ValueError(f"unknown render backend {name!r}")
