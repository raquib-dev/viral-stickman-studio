"""Local render backends ($0, run on this machine):

- local-stickman: the procedural animator in stickman.py. Needs only ffmpeg + Pillow. Fast on any laptop.
- local-comfyui: a ComfyUI server on your GPU (Wan 2.1/2.2, LTX-Video ...) driven by a workflow exported
  in API format with {{PLACEHOLDERS}}. The clip is normalised to the project's ratio, size and length.

Neither model speaks, so both add the clip's voiceover with local TTS (tts.py) when an engine is installed.
"""
from __future__ import annotations

import asyncio
import json
import random
import re
import time
import uuid
from pathlib import Path

import httpx

from ..paths import REPO_ROOT
from ..settings import load_settings
from . import tts
from .base import ClipResult, ClipSpec, Log, RenderError
from .media import arun_ffmpeg, dims, last_frame, probe
from .stickman import plan_scene, write_clip

VIDEO_EXT = (".mp4", ".webm", ".mov", ".mkv", ".gif")


async def _voice(clip: ClipSpec, silent: Path, settings: dict, log: Log) -> dict:
    """Speak the clip's VO and mux it under `silent` into clip.out_path."""
    out = clip.out_path
    assert out is not None
    wav = out.with_suffix(".vo.wav")
    log(f"clip {clip.index + 1}: voiceover ({settings['voice'].get('tts', 'auto')})")
    t0 = time.time()
    speech = await asyncio.to_thread(tts.synth, clip.vo, wav, settings, clip.voice_pref, log)
    fit = await tts.fit_to_clip(silent, speech, out, clip.duration, float(settings["voice"].get("max_speedup", 1.3)))
    if speech:
        log(f"clip {clip.index + 1}: voice {fit['speech_seconds']}s in {time.time() - t0:.1f}s"
            + (f", sped up x{fit['tempo']}" if fit["tempo"] > 1 else "") + (" (still too long: cut)" if fit.get("cut") else ""),
            "warn" if fit.get("cut") else "info")
    wav.unlink(missing_ok=True)
    return {"voice": bool(speech), **fit}


class LocalStickmanBackend:
    name = "local-stickman"

    def __init__(self) -> None:
        self.settings = load_settings()

    async def render_clip(self, clip: ClipSpec, prev: ClipResult | None, log: Log) -> ClipResult:
        w, h = dims(clip.ratio, clip.resolution)
        fps = int(self.settings["render"].get("stickman", {}).get("fps", 24))
        out = clip.out_path
        assert out is not None
        out.parent.mkdir(parents=True, exist_ok=True)
        scene = plan_scene(clip.index, clip.label, clip.vo, clip.prompt)
        log(f"local-stickman clip {clip.index + 1}: {w}x{h} {fps} fps, actions {'+'.join(scene.actions)}"
            + (f", prop {scene.prop}" if scene.prop else "") + (", two figures" if scene.duo else ""))
        t0 = time.time()
        silent = out.with_suffix(".silent.mp4")
        try:
            await asyncio.to_thread(write_clip, scene, silent, w, h, fps, clip.duration, clip.theme)
        except Exception as e:
            raise RenderError(f"stickman animator failed: {e}", retryable=False) from e
        log(f"clip {clip.index + 1}: animated in {time.time() - t0:.1f}s")
        voice = await _voice(clip, silent, self.settings, log)
        silent.unlink(missing_ok=True)
        lf = await asyncio.to_thread(last_frame, out, out.with_suffix(".last.png"))
        return ClipResult(clip.index, out, clip.duration, 0.0, self.name, last_frame=lf,
                          meta={"scene": {"actions": scene.actions, "prop": scene.prop, "duo": scene.duo}, **voice})


def clean_prompt(text: str, limit: int = 1200) -> str:
    """Phase B prompts are written for Omni (with audio and dialogue lines). Video-only models get the
    visual sentences only."""
    keep = [s for s in re.split(r"(?<=[.!?])\s+", text)
            if not re.search(r"\baudio|voice|dialogue|narrat|music|piano|synth|sound|spoken|speech", s, re.I)]
    return " ".join(keep)[:limit].strip() or text[:limit]


def fill(node, values: dict):
    """Replace {{NAME}} placeholders. A string that is exactly one placeholder takes the value's type."""
    if isinstance(node, dict):
        return {k: fill(v, values) for k, v in node.items() if not str(k).startswith("_")}
    if isinstance(node, list):
        return [fill(v, values) for v in node]
    if isinstance(node, str):
        m = re.fullmatch(r"\{\{(\w+)\}\}", node.strip())
        if m and m.group(1) in values:
            return values[m.group(1)]
        return re.sub(r"\{\{(\w+)\}\}", lambda x: str(values.get(x.group(1), x.group(0))), node)
    return node


def find_video(history: dict) -> dict | None:
    for node in (history.get("outputs") or {}).values():
        for key in ("videos", "gifs", "images", "video"):
            for f in node.get(key) or []:
                if isinstance(f, dict) and str(f.get("filename", "")).lower().endswith(VIDEO_EXT):
                    return f
    return None


class ComfyUIBackend:
    name = "local-comfyui"

    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.settings = load_settings()
        self.cfg = self.settings["render"]["comfyui"]
        self._transport = transport

    def _workflow(self, key: str) -> dict | None:
        rel = self.cfg.get(key) or ""
        if not rel:
            return None
        f = Path(rel) if Path(rel).is_absolute() else REPO_ROOT / rel
        if not f.exists():
            raise RenderError(f"ComfyUI workflow not found: {rel} (Settings → Render → ComfyUI)", retryable=False)
        return json.loads(f.read_text(encoding="utf-8"))

    async def render_clip(self, clip: ClipSpec, prev: ClipResult | None, log: Log) -> ClipResult:
        out = clip.out_path
        assert out is not None
        out.parent.mkdir(parents=True, exist_ok=True)
        vertical = clip.ratio == "9:16"
        long_side, short_side = int(self.cfg.get("gen_long_side", 832)), int(self.cfg.get("gen_short_side", 480))
        gw, gh = (short_side, long_side) if vertical else (long_side, short_side)
        fps, frames = int(self.cfg.get("fps", 16)), int(self.cfg.get("frames", 81))
        use_i2v = bool(clip.continuity != "none" and prev and prev.last_frame and prev.last_frame.exists()
                       and self.cfg.get("i2v_workflow"))
        wf = self._workflow("i2v_workflow" if use_i2v else "t2v_workflow")
        if wf is None:
            raise RenderError("set a ComfyUI text-to-video workflow in Settings → Render", retryable=False)
        url = self.cfg.get("url", "http://127.0.0.1:8188").rstrip("/")
        async with httpx.AsyncClient(base_url=url, timeout=60, transport=self._transport) as http:
            values = {"PROMPT": clean_prompt(clip.prompt), "NEGATIVE": self.cfg.get("negative", ""), "WIDTH": gw, "HEIGHT": gh,
                      "FRAMES": frames, "FPS": fps, "SEED": random.Random(clip.index * 104729).randint(1, 2**31 - 1)}
            try:
                if use_i2v:
                    assert prev and prev.last_frame
                    up = await http.post("/upload/image", files={"image": (f"vss-{uuid.uuid4().hex[:8]}.png",
                                                                          prev.last_frame.read_bytes(), "image/png")},
                                         data={"overwrite": "true"})
                    up.raise_for_status()
                    values["IMAGE"] = up.json()["name"]
                log(f"local-comfyui clip {clip.index + 1}: {'image' if use_i2v else 'text'}-to-video {gw}x{gh}, "
                    f"{frames} frames @ {fps} fps")
                missing = await missing_models(http, wf)
                if missing:
                    raise RenderError("ComfyUI is missing model files: " + missing_message(missing) +
                                      " (README → ComfyUI on Windows lists the exact files and folders)", retryable=False)
                r = await http.post("/prompt", json={"prompt": fill(wf, values), "client_id": "vss"})
            except httpx.ConnectError as e:
                raise RenderError(f"ComfyUI is not running at {url}. Start it, then retry.", retryable=False) from e
            except httpx.HTTPError as e:
                raise RenderError(f"ComfyUI request failed: {type(e).__name__}: {e}") from e
            if r.status_code >= 400:
                raise RenderError(f"ComfyUI rejected the workflow: {r.text[:500]} (check model file names in the "
                                  "workflow JSON match your ComfyUI models folder)", retryable=False)
            pid = r.json()["prompt_id"]
            hist = await self._wait(http, pid, clip, log)
            f = find_video(hist)
            if not f:
                raise RenderError("ComfyUI finished but saved no video (the workflow needs a video save node, "
                                  "e.g. SaveWEBM or VHS Video Combine)", retryable=False)
            raw = out.with_suffix(".raw" + Path(f["filename"]).suffix)
            v = await http.get("/view", params={"filename": f["filename"], "subfolder": f.get("subfolder", ""),
                                                "type": f.get("type", "output")}, timeout=300)
            v.raise_for_status()
            raw.write_bytes(v.content)
        silent = out.with_suffix(".silent.mp4")
        info = await asyncio.to_thread(probe, raw)
        src = info["duration"] or frames / fps
        w, h = dims(clip.ratio, clip.resolution)
        stretch = max(1.0, clip.duration / src)
        log(f"clip {clip.index + 1}: generated {src:.1f}s {info['width']}x{info['height']}; scaling to {w}x{h}"
            + (f", slowed x{stretch:.2f} to fill {clip.duration:.0f}s" if stretch > 1.01 else ""))
        await arun_ffmpeg(["-i", str(raw), "-an", "-vf",
                           f"setpts={stretch:.4f}*PTS,scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},"
                           f"fps=24,format=yuv420p", "-t", f"{clip.duration:.3f}", "-c:v", "libx264", "-preset", "veryfast",
                           "-crf", "18", str(silent)])
        raw.unlink(missing_ok=True)
        voice = await _voice(clip, silent, self.settings, log)
        silent.unlink(missing_ok=True)
        lf = await asyncio.to_thread(last_frame, out, out.with_suffix(".last.png"))
        return ClipResult(clip.index, out, clip.duration, 0.0, self.name, last_frame=lf,
                          meta={"prompt_id": pid, "generated_seconds": round(src, 2), "stretch": round(stretch, 3),
                                "task": "image_to_video" if use_i2v else "text_to_video", **voice})

    async def _wait(self, http: httpx.AsyncClient, pid: str, clip: ClipSpec, log: Log) -> dict:
        limit = float(self.cfg.get("timeout_s", 1800))
        t0, last_note = time.time(), 0.0
        while time.time() - t0 < limit:
            await asyncio.sleep(float(self.cfg.get("poll_s", 3)))
            try:
                r = await http.get(f"/history/{pid}")
                hist = r.json().get(pid) if r.status_code == 200 else None
            except httpx.HTTPError as e:
                log(f"clip {clip.index + 1}: ComfyUI poll error (will retry): {type(e).__name__}", "warn")
                continue
            if hist:
                st = hist.get("status") or {}
                if st.get("status_str") == "error":
                    msgs = [m[1].get("exception_message", "") for m in st.get("messages", [])
                            if isinstance(m, list) and len(m) > 1 and m[0] == "execution_error"]
                    msg = "; ".join(msgs) or "execution error"
                    oom = "out of memory" in msg.lower() or "allocation" in msg.lower()
                    raise RenderError(f"ComfyUI error: {msg[:400]}" + (" (GPU out of memory: lower frames or size in "
                                                                       "Settings → Render → ComfyUI)" if oom else ""),
                                      retryable=not oom)
                if st.get("completed", True) and hist.get("outputs"):
                    log(f"clip {clip.index + 1}: ComfyUI finished in {time.time() - t0:.0f}s")
                    return hist
            if time.time() - last_note > 30:
                last_note = time.time()
                log(f"clip {clip.index + 1}: generating on GPU… {time.time() - t0:.0f}s")
        raise RenderError(f"ComfyUI did not finish in {limit / 60:.0f} min", retryable=False)


MODEL_EXT = (".safetensors", ".pth", ".pt", ".ckpt", ".gguf", ".bin", ".sft")


def workflow_models(wf: dict) -> list[tuple[str, str, str]]:
    """(loader class, input name, file name) for every model file a workflow names."""
    out = []
    for node in wf.values():
        if not isinstance(node, dict):
            continue
        for field, v in (node.get("inputs") or {}).items():
            if isinstance(v, str) and v.lower().endswith(MODEL_EXT):
                out.append((node.get("class_type", "?"), field, v))
    return out


async def missing_models(http: httpx.AsyncClient, wf: dict) -> list[dict]:
    """Model files the workflow needs that this ComfyUI does not have, with what it has instead."""
    missing, cache = [], {}
    for cls, field, name in workflow_models(wf):
        if cls not in cache:
            r = await http.get(f"/object_info/{cls}")
            cache[cls] = r.json().get(cls, {}).get("input", {}) if r.status_code == 200 else {}
        spec = {**cache[cls].get("required", {}), **cache[cls].get("optional", {})}.get(field)
        have = spec[0] if spec and isinstance(spec[0], list) else None
        if have is not None and name not in have:
            missing.append({"loader": cls, "file": name, "available": have[:20]})
    return missing


def missing_message(missing: list[dict]) -> str:
    return "; ".join(f"{m['loader']} needs {m['file']} (found: {', '.join(m['available']) or 'nothing'})" for m in missing)


async def comfy_status(url: str, timeout: float = 4.0, workflow: str = "") -> dict:
    try:
        async with httpx.AsyncClient(base_url=url.rstrip("/"), timeout=timeout) as http:
            r = await http.get("/system_stats")
            r.raise_for_status()
            d = r.json()
            dev = (d.get("devices") or [{}])[0]
            out = {"ok": True, "device": dev.get("name"), "vram_total_gb": round((dev.get("vram_total") or 0) / 2**30, 1),
                   "vram_free_gb": round((dev.get("vram_free") or 0) / 2**30, 1),
                   "version": (d.get("system") or {}).get("comfyui_version"), "missing_models": []}
            f = Path(workflow) if workflow and Path(workflow).is_absolute() else REPO_ROOT / workflow
            if workflow and f.is_file():
                out["missing_models"] = await missing_models(http, json.loads(f.read_text(encoding="utf-8")))
            return out
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}"}

