"""local-threejs: the three.js animation renderer (renderer/) as a render backend.

Per clip: a scene plan (JSON) -> renderer/render.mjs in a headless browser -> frames -> mp4, then the
local voiceover. The scene plan comes from, in order:
  1. projects/<slug>/scenes/clip-NN.json   (hand-written or AI-planned; edit it and regenerate the clip)
  2. auto_scene(): a keyword planner over the beat purpose and voiceover (no AI call)
The voice is synthesised first, so the mouth moves with the real speech loudness (lip sync).
"""
from __future__ import annotations

import asyncio
import json
import re
import shutil
import time
import wave
from pathlib import Path

from ..paths import REPO_ROOT
from ..settings import ffmpeg_bin, load_settings
from . import tts
from .base import ClipResult, ClipSpec, Log, RenderError
from .media import arun_ffmpeg, dims, last_frame, probe

RENDERER = REPO_ROOT / "renderer"
CLIPS = ["Idle", "Walking", "Running", "Dance", "Death", "Sitting", "Standing", "Jump", "Yes", "No", "Wave", "Punch",
         "ThumbsUp", "WalkJump"]
EXPRESSIONS = ["neutral", "happy", "surprised", "sad", "angry", "confused", "thinking", "skeptical"]

GESTURES = [  # (clip, keywords) first match wins: the one gesture the beat is built around
    ("ThumbsUp", r"win|won|success|works|finally|best|great|free|rich|growth"),
    ("No", r"\bno\b|not\b|never|wrong|mistake|stop|don't|isn't|avoid|trap|fail"),
    ("Yes", r"\byes\b|exactly|right\b|true|agree|that's it|simple"),
    ("Wave", r"\bhey\b|hello|hi\b|welcome|meet"),
    ("Walking", r"walk|journey|step|path|go\b|going|daily|habit|routine|progress"),
    ("Jump", r"jump|excited|amazing|boom|suddenly"),
    ("Punch", r"fight|hit|beat|attack|crush"),
]
FACES = [
    ("surprised", r"\?|what\b|wait|really|suddenly|shock|nineteen|surpris"),
    ("happy", r"win|happy|love|great|best|finally|free|easy|works"),
    ("sad", r"sad|lost|lose|broke|regret|tired|alone|pain|debt"),
    ("angry", r"angry|hate|unfair|stupid|annoy"),
    ("thinking", r"think|why|how|idea|imagine|consider|brain|mind"),
    ("skeptical", r"actually|but\b|however|really\?|supposedly"),
    ("confused", r"confus|weird|strange|no idea"),
]
NUMBER = re.compile(r"(?:[$€£₹]\s?\d[\d,.]*\s?(?:k|m|bn|million|billion)?|\d[\d,.]*\s?(?:%|percent|x\b|times|files|days|years|hours|minutes))", re.I)
CAMERAS = {
    "closeup": [{"t": 0, "pos": [0.05, 1.62, 1.5], "look": [0, 1.58, 0], "fov": 32},
                {"t": 10, "pos": [0, 1.6, 1.2], "look": [0, 1.58, 0], "fov": 32, "ease": "inOutSine"}],
    "medium": [{"t": 0, "pos": [0.5, 1.45, 3.3], "look": [0.1, 1.2, 0], "fov": 36},
               {"t": 10, "pos": [0.2, 1.4, 2.7], "look": [0.05, 1.25, 0], "fov": 36, "ease": "inOutSine"}],
    "wide": [{"t": 0, "pos": [-1.3, 1.9, 5.2], "look": [0, 1.0, 0], "fov": 40},
             {"t": 10, "pos": [-0.6, 1.7, 4.2], "look": [0, 1.05, 0], "fov": 40, "ease": "inOutSine"}],
    "low": [{"t": 0, "pos": [0.6, 0.55, 2.6], "look": [0, 1.25, 0], "fov": 38},
            {"t": 10, "pos": [0.3, 0.6, 2.2], "look": [0, 1.3, 0], "fov": 38, "ease": "inOutSine"}],
}
CAMERA_ORDER = ["closeup", "medium", "wide", "closeup", "low", "medium"]


def status() -> dict:
    """Is everything the renderer needs present? (Settings → Local services)"""
    node = shutil.which("node")
    out = {"node": bool(node), "built": (RENDERER / "dist" / "index.html").exists(),
           "deps": (RENDERER / "node_modules" / "playwright-core").exists()}
    out["ok"] = all(out.values())
    if not out["ok"]:
        out["fix"] = ("install Node.js 20+" if not node else "") + \
                     ("" if out["deps"] and out["built"] else " · cd renderer; npm install; npm run build")
    return out


def _pick(rules, text: str, default: str) -> str:
    return next((name for name, rx in rules if re.search(rx, text, re.I)), default)


def auto_scene(clip: ClipSpec, settings: dict, talk: tuple[float, float]) -> dict:
    """A scene plan without any AI call: one gesture, one expression arc, a camera preset, and a stat
    badge only when the voiceover itself says a number (the badge shows those exact words)."""
    w, h = dims(clip.ratio, clip.resolution)
    text = f"{clip.label} {clip.vo}"
    gesture = _pick(GESTURES, text, "Wave" if clip.index == 0 else "Idle")
    face = _pick(FACES, text, "neutral")
    end_face = "happy" if face in ("happy", "surprised") else "neutral" if face != "thinking" else "thinking"
    a, b = talk
    anim = [{"t": 0, "clip": "Idle"}]
    if gesture != "Idle":
        anim += [{"t": round(a + 0.4, 2), "clip": gesture}]
        if gesture in ("Walking",):
            anim += [{"t": round(min(b, a + 5), 2), "clip": "Idle"}]
    scene = {
        "version": 1, "width": w, "height": h, "fps": int(settings.get("fps", 24)), "duration": clip.duration,
        "theme": "light" if clip.theme == "light" else "warm-dark", "seed": 11 + clip.index * 31,
        "quality": settings.get("quality", "high"),
        "actors": [{"id": "hero", "anim": anim,
                    "face": [{"t": 0, "expr": face}, {"t": round((a + b) / 2 + 1.5, 2), "expr": end_face}],
                    "talk": [[round(a, 2), round(b, 2)]]}],
        "camera": CAMERAS[CAMERA_ORDER[clip.index % len(CAMERA_ORDER)]],
    }
    m = NUMBER.search(clip.vo or "")
    if m:
        scene["badges"] = [{"text": m.group(0).strip(), "t_in": round(a + 1.2, 2), "pos": [0.35, 2.45, -0.5], "size": 1.3}]
    return scene


def validate_scene(s: dict) -> list[str]:
    errs = []
    for a in s.get("actors", []):
        errs += [f"unknown clip {k.get('clip')!r}" for k in a.get("anim", []) if k.get("clip") not in CLIPS]
        errs += [f"unknown expression {k.get('expr')!r}" for k in a.get("face", []) if k.get("expr") not in EXPRESSIONS]
    if not s.get("camera"):
        errs.append("no camera keys")
    return errs


def mouth_envelope(wav_path: Path, fps: int, lead: float, tempo: float, duration: float) -> list[float]:
    """Per-frame speech loudness (0..1) of the voiceover as it will play in the clip."""
    import numpy as np
    with wave.open(str(wav_path), "rb") as w:
        rate, n = w.getframerate(), w.getnframes()
        x = np.frombuffer(w.readframes(n), dtype="<i2").astype("float32") / 32768.0
        if w.getnchannels() > 1:
            x = x.reshape(-1, w.getnchannels()).mean(axis=1)
    frames = int(round(duration * fps))
    out = []
    for i in range(frames):
        t = i / fps - lead
        if t < 0:
            out.append(0.0)
            continue
        s0, s1 = int(t * tempo * rate), int((t + 1 / fps) * tempo * rate)
        seg = x[s0:s1]
        out.append(float(np.sqrt(np.mean(seg * seg))) if len(seg) else 0.0)
    peak = max(out) or 1.0
    return [round(min(1.0, v / (peak * 0.7)), 3) for v in out]


class ThreeJSBackend:
    name = "local-threejs"

    def __init__(self) -> None:
        self.settings = load_settings()
        self.cfg = self.settings["render"].get("threejs", {})
        st = status()
        if not st["ok"]:
            raise RenderError(f"the three.js renderer is not ready: {st.get('fix', '').strip(' ·')}", retryable=False)

    async def render_clip(self, clip: ClipSpec, prev: ClipResult | None, log: Log) -> ClipResult:
        out = clip.out_path
        assert out is not None
        out.parent.mkdir(parents=True, exist_ok=True)
        fps = int(self.cfg.get("fps", 24))
        # 1. voice first, so the mouth can follow the real speech
        wav = out.with_suffix(".vo.wav")
        speech = await asyncio.to_thread(tts.synth, clip.vo, wav, self.settings, clip.voice_pref, log)
        lead, tail = 0.4, 0.3
        if speech:
            said = probe(speech)["duration"]
            tempo = min(float(self.settings["voice"].get("max_speedup", 1.3)), max(1.0, said / max(1.0, clip.duration - lead - tail)))
            talk = (lead, min(clip.duration - tail, lead + said / tempo))
        else:
            tempo, words = 1.0, len((clip.vo or "").split())
            talk = (lead, min(clip.duration - tail, lead + max(1.0, words / 2.5)))
        # 2. the scene plan: a project file wins over the keyword planner
        override = out.parent.parent / "scenes" / f"clip-{clip.index + 1:02d}.json"
        if override.exists():
            scene = json.loads(override.read_text(encoding="utf-8"))
            log(f"clip {clip.index + 1}: scene plan from scenes/{override.name}")
        else:
            scene = auto_scene(clip, self.cfg, talk)
        w, h = dims(clip.ratio, clip.resolution)
        scene.update({"width": w, "height": h, "fps": fps, "duration": clip.duration})
        errs = validate_scene(scene)
        if errs:
            raise RenderError(f"scene plan is invalid: {'; '.join(errs[:4])}", retryable=False)
        if speech and scene.get("actors"):
            scene["actors"][0]["mouth"] = {"fps": fps, "values": mouth_envelope(speech, fps, lead, tempo, clip.duration)}
        scene_path = out.with_suffix(".scene.json")
        scene_path.write_text(json.dumps(scene, indent=1), encoding="utf-8")
        a = scene["actors"][0] if scene.get("actors") else {}
        log(f"local-threejs clip {clip.index + 1}: {w}x{h} {fps} fps · "
            f"{' → '.join(k['clip'] for k in a.get('anim', [])) or 'no actor'} · "
            f"{' → '.join(k['expr'] for k in a.get('face', []))}"
            + (f" · badge “{scene['badges'][0]['text']}”" if scene.get("badges") else "")
            + (" · lip sync from the voice" if a.get("mouth") else ""))
        # 3. render frames in the headless browser
        silent = out.with_suffix(".silent.mp4")
        await self._render(scene_path, silent, clip, log)
        # 4. mux the voice under it
        fit = await tts.fit_to_clip(silent, speech, out, clip.duration, float(self.settings["voice"].get("max_speedup", 1.3)), lead)
        for f in (silent, wav):
            f.unlink(missing_ok=True)
        lf = await asyncio.to_thread(last_frame, out, out.with_suffix(".last.png"))
        return ClipResult(clip.index, out, clip.duration, 0.0, self.name, last_frame=lf,
                          meta={"scene": scene_path.name, "voice": bool(speech), "planned_by": "file" if override.exists() else "keywords",
                                **fit})

    async def _render(self, scene_path: Path, out: Path, clip: ClipSpec, log: Log) -> None:
        env = {**__import__("os").environ, "FFMPEG_PATH": ffmpeg_bin()}
        if self.cfg.get("browser_path"):
            env["VSS_BROWSER_PATH"] = self.cfg["browser_path"]
        if self.cfg.get("browser_channel"):
            env["VSS_BROWSER_CHANNEL"] = self.cfg["browser_channel"]
        proc = await asyncio.create_subprocess_exec(
            shutil.which("node") or "node", str(RENDERER / "render.mjs"), "--scene", str(scene_path), "--out", str(out),
            cwd=str(RENDERER), env=env, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        t0, last_note, error = time.time(), 0.0, None
        assert proc.stdout is not None
        async for raw in proc.stdout:
            try:
                ev = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if ev.get("event") == "info":
                gpu = ev.get("gpu", "")
                soft = "swiftshader" in gpu.lower() or "llvmpipe" in gpu.lower()
                log(f"clip {clip.index + 1}: rendering {ev['frames']} frames on {gpu}"
                    + (" (software rendering: slow; use Edge/Chrome with the GPU enabled)" if soft else ""),
                    "warn" if soft else "info")
            elif ev.get("event") == "progress" and time.time() - last_note > 4:
                last_note = time.time()
                f, n = ev["frame"], ev["frames"]
                eta = (time.time() - t0) / max(1, f) * (n - f)
                log(f"clip {clip.index + 1}: frame {f}/{n} ({f / n:.0%}), ~{eta:.0f}s left")
            elif ev.get("event") in ("error", "page-error"):
                error = ev.get("message")
        err = (await proc.stderr.read()).decode(errors="replace") if proc.stderr else ""
        await proc.wait()
        if proc.returncode != 0 or not out.exists():
            raise RenderError(f"three.js renderer failed: {(error or err.strip()[-400:] or f'exit {proc.returncode}')[:500]}",
                              retryable=False)
        log(f"clip {clip.index + 1}: rendered in {time.time() - t0:.0f}s")
