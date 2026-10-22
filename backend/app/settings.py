"""Settings and secrets.

Secrets come only from the environment / .env and never leave this module except as in-memory
arguments to SDK clients. `public_settings()` is what the API returns: key presence as booleans.
"""
from __future__ import annotations

import copy
import json
import os
import re
import shutil
from pathlib import Path
from typing import Any

from dotenv import dotenv_values

from .paths import CONFIG, REPO_ROOT

SECRET_NAMES = ("ANTHROPIC_API_KEY", "GEMINI_API_KEY", "FAL_KEY", "YOUTUBE_API_KEY")
SETTINGS_FILE = Path(os.environ.get("VSS_SETTINGS_FILE") or CONFIG / "settings.json")
PRICING_FILE = CONFIG / "pricing.json"

_env_cache: dict[str, str] | None = None


def _env() -> dict[str, str]:
    global _env_cache
    if _env_cache is None:
        values = {k: v for k, v in dotenv_values(REPO_ROOT / ".env").items() if v}
        # real environment wins over .env
        values.update({k: v for k, v in os.environ.items() if k in SECRET_NAMES + ("FFMPEG_PATH", "FFPROBE_PATH") and v})
        _env_cache = values
    return _env_cache


def reload_env() -> None:
    global _env_cache
    _env_cache = None


def secret(name: str) -> str | None:
    if name not in SECRET_NAMES:
        raise KeyError(name)
    return _env().get(name) or None


def has_secret(name: str) -> bool:
    return bool(secret(name))


def secret_values() -> list[str]:
    return [v for k in SECRET_NAMES if (v := _env().get(k)) and len(v) >= 8]


_KEY_PATTERNS = [re.compile(p) for p in (r"AIza[0-9A-Za-z_\-]{20,}", r"sk-ant-[0-9A-Za-z_\-]{10,}",
                                          r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}:[0-9a-f]{20,}")]


def redact(text: str) -> str:
    """Remove configured secret values and common key shapes from any text bound for logs/UI."""
    if not text:
        return text
    for v in secret_values():
        text = text.replace(v, "[REDACTED]")
    for p in _KEY_PATTERNS:
        text = p.sub("[REDACTED]", text)
    return text


def ffmpeg_bin() -> str:
    return _env().get("FFMPEG_PATH") or shutil.which("ffmpeg") or "ffmpeg"


def ffprobe_bin() -> str:
    return _env().get("FFPROBE_PATH") or shutil.which("ffprobe") or "ffprobe"


# ---- non-secret settings -------------------------------------------------------------------

# Defaults for keys added after a settings.json was written, so older files keep working unchanged.
DEFAULTS: dict[str, Any] = {
    "agent": {
        # claude: Claude Agent SDK for every task. local: an OpenAI-compatible server on this machine
        # (Ollama, LM Studio, llama.cpp). hybrid: Claude for direction, local for research and labeling.
        "provider": "claude",
        "max_attempts": 3,
        "local": {"base_url": "http://localhost:11434/v1", "model": "qwen3:8b", "temperature": 0.4,
                  "max_tokens": 8192, "timeout_s": 900, "skill_chars": 14000,
                  # Ollama only (native API): context window, reasoning on/off, how long the model stays loaded
                  "num_ctx": 8192, "think": False, "keep_alive": "5m"},
    },
    "render": {
        "comfyui": {"url": "http://127.0.0.1:8188", "t2v_workflow": "config/comfyui/wan21-t2v-1.3b.json",
                    "i2v_workflow": "", "timeout_s": 1800, "poll_s": 3,
                    "negative": ("photorealistic, 3D render, shading, gradients, texture, colorful background, blurry, "
                                 "low quality, jpeg artifacts, deformed body, extra limbs, extra fingers, missing limbs, "
                                 "fused limbs, multiple heads, text, letters, subtitles, watermark, logo, flicker, "
                                 "jittery motion, static frame"),
                    # sampler values filled into {{STEPS}} {{CFG}} {{SHIFT}}; Wan 1.3B is tuned for cfg 6, shift 8
                    "steps": 30, "cfg": 6.0, "shift": 8.0,
                    # how a 5 s generation fills a 10 s clip: smooth = motion-interpolated slow motion (+~30 s CPU
                    # per clip), slow = plain slow motion (choppy, ~8 new frames a second)
                    "fill": "smooth",
                    # Wan 2.1 1.3B native size; 81 frames at 16 fps = 5 s, slowed to the 10 s clip. Fits 8 GB VRAM.
                    "gen_long_side": 832, "gen_short_side": 480, "frames": 81, "fps": 16},
        "stickman": {"fps": 24},
        # three.js renderer (renderer/): quality high = bloom + depth of field; browser_channel "" = Edge on
        # Windows, Playwright's Chromium elsewhere; browser_path overrides both
        "threejs": {"fps": 24, "quality": "high", "browser_channel": "", "browser_path": "",
                    # style: "auto" = the project's style (1, 2A, 2B, 3, 4, 5), or a pack name to force one
                    # mood: "auto" = colours follow each beat's content, "off" = the style's own colours, or a mood name
                    "style": "auto", "mood": "auto"},
    },
    "voice": {"tts": "auto", "kokoro_voice_male": "am_michael", "kokoro_voice_female": "af_heart",
              "piper_model": "", "max_speedup": 1.3},
    "captions": {"whisper_model": "base.en", "whisper_device": "auto"},
}

AGENT_PROVIDERS = ("claude", "local", "hybrid")
RENDER_BACKENDS = ("mock", "omni-gemini", "omni-fal", "local-threejs", "local-stickman", "local-comfyui")
LOCAL_BACKENDS = ("local-threejs", "local-stickman", "local-comfyui")
TTS_ENGINES = ("auto", "kokoro", "piper", "none")


def load_settings() -> dict[str, Any]:
    return _deep_merge(DEFAULTS, json.loads(SETTINGS_FILE.read_text(encoding="utf-8")))


def save_settings(new: dict[str, Any]) -> dict[str, Any]:
    current = load_settings()
    merged = _deep_merge(current, new)
    validate_settings(merged)
    SETTINGS_FILE.write_text(json.dumps(merged, indent=2) + "\n", encoding="utf-8")
    return merged


def validate_settings(s: dict[str, Any]) -> None:
    for k in s:
        if k.upper() in SECRET_NAMES or "key" in k.lower():
            raise ValueError("secrets belong in .env, not settings")
    if s["render"]["backend"] not in RENDER_BACKENDS:
        raise ValueError("unknown render backend")
    if s["agent"]["provider"] not in AGENT_PROVIDERS:
        raise ValueError("agent provider must be claude, local or hybrid")
    if not str(s["agent"]["local"]["base_url"]).startswith(("http://", "https://")):
        raise ValueError("local LLM URL must start with http:// or https://")
    if s["voice"]["tts"] not in TTS_ENGINES:
        raise ValueError("unknown TTS engine")
    if not 1 <= int(s["agent"]["max_attempts"]) <= 6:
        raise ValueError("agent attempts must be 1-6")
    if s["render"]["resolution"] not in ("360p", "720p", "1080p", "4k"):
        raise ValueError("unknown resolution")
    if float(s["render"]["budget_cap_usd"]) < 0:
        raise ValueError("budget cap must be >= 0")
    for g, mode in s["gates"].items():
        if mode not in ("pause", "auto"):
            raise ValueError(f"gate {g}: mode must be pause or auto")


def load_pricing() -> dict[str, Any]:
    return json.loads(PRICING_FILE.read_text(encoding="utf-8"))


def public_settings() -> dict[str, Any]:
    s = load_settings()
    s["keys"] = {name.lower(): has_secret(name) for name in SECRET_NAMES}
    return s


def _deep_merge(a: dict, b: dict) -> dict:
    out = copy.deepcopy(a)
    for k, v in b.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out
