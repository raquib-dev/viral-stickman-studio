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
CATALOG = json.loads((RENDERER / "catalog.json").read_text(encoding="utf-8"))
CLIPS, EXPRESSIONS = CATALOG["clips"], CATALOG["expressions"]

GESTURE_CLIPS = [  # (clip, keywords) first match wins: the body move the beat is built around
    ("ThumbsUp", r"win|won|success|works|finally|best|great|free|rich|growth"),
    ("No", r"\bno\b|not\b|never|wrong|mistake|stop|don't|isn't|avoid|trap|fail"),
    ("Yes", r"\byes\b|exactly|right\b|true|agree|that's it|simple"),
    ("Wave", r"\bhey\b|hello|hi\b|welcome|meet"),
    ("Jump", r"jump|excited|amazing|boom|suddenly"),
    ("Punch", r"fight|hit|beat|attack|crush"),
]
ARM_GESTURES = [  # (gesture, keywords): an arm gesture layered on top
    ("think", r"think|why|how come|wonder|idea|imagine|consider|brain|mind"),
    ("facepalm", r"mistake|stupid|oops|forgot|wrong|regret|dumb"),
    ("shrug", r"maybe|nobody knows|who knows|no idea|random|whatever"),
    ("cheer", r"win|won|finally|success|did it|celebrat"),
    ("crossed", r"no way|refuse|won't|skeptic|doubt|supposedly"),
    ("hips", r"listen|here's the thing|truth is|look,|confident"),
    ("present", r"first|second|third|step|rule|here's|meet|introduc|this is"),
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
MOODS_KW = [  # (mood, keywords): the colour of the beat
    ("danger", r"danger|warning|risk|scam|trap|crash|debt|lose|lost|fail|mistake|threat|fear|panic|broke"),
    ("money", r"money|\$|cash|sav(e|ing)|spend|invest|income|salary|price|budget|rich|wealth|profit|dollar|rupee"),
    ("success", r"win|won|success|achiev|goal|finally|result|growth|grow|level up|best"),
    ("tech", r"code|software|app|ai\b|computer|data|algorithm|robot|tech|program|server|internet"),
    ("calm", r"calm|relax|peace|sleep|breathe|slow|simple|quiet|rest|mindful|morning|coffee|tea\b|cozy|read"),
    ("mystery", r"secret|myster|hidden|nobody knows|strange|unknown|dark side|truth"),
    ("nostalgia", r"remember|years ago|childhood|used to|back then|history|ancient|old days|grandp"),
    ("sad", r"sad|alone|lonely|tired|regret|cry|miss\b|grief|empty"),
    ("love", r"love|heart|friend|family|relationship|kind|care|together"),
    ("nature", r"nature|tree|forest|plant|earth|green|garden|outdoor|ocean"),
]
TURN = re.compile(r"\b(but|however|until|instead|then|turns out|actually)\b", re.I)
PROP_KW = [  # (props, keywords): concrete objects first, then ideas; holdable ones get held
    (["phone"], r"phone|scroll|social|instagram|tiktok|notification|text|call"),
    (["mug"], r"coffee|tea|morning|break|cozy"),
    (["books"], r"book|read|study|school|learn|course"),
    (["house"], r"home|house|rent|mortgage|family"),
    (["laptop", "monitor"], r"code|software|app|computer|work|job|office|email|startup|website"),
    (["lock", "key"], r"secret|password|security|lock|safe|protect|private|key\b"),
    (["gift"], r"gift|bonus|free|reward|surprise"),
    (["rocket"], r"launch|startup|fast|rocket|takeoff|boost"),
    (["coins", "moneybag", "piggybank"], r"money|\$|cash|sav(e|ing)|invest|income|salary|price|budget|rich|wealth|coin|dollar|rupee"),
    (["heart"], r"love|heart|care|relationship|kind"),
    (["warning"], r"danger|warning|risk|scam|trap|careful|mistake"),
    (["chart", "arrow_up"], r"grow|growth|percent|%|compound|increase|rise|stock|market|result|scale"),
    (["arrow_down"], r"drop|fall|decline|lose|loss|crash|decrease"),
    (["target", "trophy"], r"goal|target|aim|focus|win|award|champion"),
    (["bulb"], r"idea|realis|insight|tip|trick|learn|smart|figure"),
    (["clock", "hourglass", "calendar"], r"time|minute|hour|day|week|year|deadline|late|wait|later|schedule"),
    (["question"], r"\?|why|how|what if|question"),]
STYLE_PROPS = {  # extra props that fit a style when no topic prop matched
    "historic": ["scroll", "flag", "shield"], "prehistoric": ["rock", "campfire", "spear"], "cozy": ["mug", "books", "plant"],
    "modern": ["laptop", "monitor"], "cinematic": ["question", "exclamation"], "minimal": ["question", "bulb"],
}
HOLDABLE = {"phone", "mug", "key", "sword", "torch", "spear", "moneybag", "briefcase", "coin"}
HATS_KW = [("crown", r"king|queen|emperor|royal|empire|throne|pharaoh"), ("helmet", r"soldier|war|army|knight|battle|roman"),
           ("tophat", r"gentleman|magic|victorian|banker|ceo|fancy"), ("headband", r"caveman|tribe|hunter|stone age"),
           ("beanie", r"winter|cold|snow|cozy")]
DUO = re.compile(r"\bvs\b|versus|compare|friend|other people|\bthey\b|someone|partner|boss|customer|everyone else", re.I)
NUMBER = re.compile(r"(?:[$€£₹]\s?\d[\d,.]*\s?(?:k|m|bn|million|billion)?|\d[\d,.]*\s?(?:%|percent|x\b|times|files|days|years|hours|minutes))", re.I)
SHOT_PAIRS = [("medium", "closeup"), ("full", "medium"), ("closeup", "medium"), ("wide", "medium"), ("low", "closeup"), ("medium", "high")]


def status() -> dict:
    """Is everything the renderer needs present? (Settings → Local services)"""
    node = shutil.which("node")
    out = {"node": bool(node), "built": (RENDERER / "dist" / "index.html").exists(),
           "deps": (RENDERER / "node_modules" / "playwright-core").exists()}
    out["ok"] = all(out.values())
    # optional humanoid animation pack (more human walking/running/idle); used when present
    out["pack"] = any((RENDERER / d / "models" / "anim-pack.glb").exists() for d in ("public", "dist"))
    if not out["ok"]:
        out["fix"] = ("install Node.js 20+" if not node else "") + \
                     ("" if out["deps"] and out["built"] else " · cd renderer; npm install; npm run build")
    return out


def _pick(rules, text: str, default: str | None) -> str | None:
    return next((name for name, rx in rules if re.search(rx, text, re.I)), default)


def style_for(clip: ClipSpec, settings: dict) -> str:
    forced = settings.get("style", "auto")
    if forced and forced != "auto":
        return CATALOG["skill_styles"].get(forced, forced)
    return CATALOG["skill_styles"].get(clip.style, "minimal")


def mood_track(clip: ClipSpec, settings: dict, talk: tuple[float, float]) -> list[dict]:
    """The beat's colour: one mood, or two when the line turns ("...but...") at the point it turns."""
    mode = settings.get("mood", "auto")
    if mode == "off":
        return [{"t": 0, "mood": "neutral"}]
    if mode in CATALOG["moods"]:
        return [{"t": 0, "mood": mode}]
    text = f"{clip.label} {clip.vo}"
    m = TURN.search(clip.vo or "")
    if m and m.start() > 8:
        before, after = clip.vo[:m.start()], clip.vo[m.start():]
        a, b = _pick(MOODS_KW, before, None), _pick(MOODS_KW, after, None)
        if a and b and a != b:
            frac = m.start() / max(1, len(clip.vo))
            return [{"t": 0, "mood": a}, {"t": round(talk[0] + (talk[1] - talk[0]) * frac, 2), "mood": b}]
    return [{"t": 0, "mood": _pick(MOODS_KW, text, "neutral")}]


def auto_scene(clip: ClipSpec, settings: dict, talk: tuple[float, float]) -> dict:
    """A scene plan without any AI call: style from the project, mood/props/gestures/hat from the words,
    two camera shots, and a stat badge only when the voiceover itself says a number (exact words)."""
    w, h = dims(clip.ratio, clip.resolution)
    text = f"{clip.label} {clip.vo}"
    style = style_for(clip, settings)
    a, b = talk
    mid = round((a + b) / 2, 2)
    vertical = h > w
    clip_move = _pick(GESTURE_CLIPS, text, "Wave" if clip.index == 0 else "Idle")
    face = _pick(FACES, text, "neutral")
    end_face = "happy" if face in ("happy", "surprised") else "thinking" if face == "thinking" else "neutral"
    hero = {"id": "hero", "anim": [{"t": 0, "clip": "Idle"}], "face": [{"t": 0, "expr": face}, {"t": round(mid + 1.5, 2), "expr": end_face}],
            "talk": [[round(a, 2), round(b, 2)]], "facing": "camera", "position": [0, 0, 0]}
    if clip_move != "Idle":
        hero["anim"].append({"t": round(a + 0.4, 2), "clip": clip_move})
    hat = _pick(HATS_KW, text, "headband" if style == "prehistoric" else None)
    if hat:
        hero["hat"] = hat
    # the opening clip walks the hero in; "journey" lines walk across
    if clip.index == 0 or re.search(r"walk|journey|step by step|path|road", text, re.I):
        start = -1.6 if clip.index % 2 == 0 else 1.6
        hero["path"] = [{"t": 0, "pos": [start, 0, 0.3]}, {"t": 1.7, "pos": [0, 0, 0]}]
    scene = {"version": 2, "width": w, "height": h, "fps": int(settings.get("fps", 24)), "duration": clip.duration,
             "style": style, "theme": "light" if clip.theme == "light" else "dark", "mood": mood_track(clip, settings, talk),
             "seed": 11 + clip.index * 31, "quality": settings.get("quality", "high"), "actors": [hero], "props": []}
    # props: the topic's, else one that fits the style; placed beside the hero, inside a 9:16 frame
    found = next((ps for ps, rx in PROP_KW if re.search(rx, text, re.I)), None)
    choices = found or STYLE_PROPS.get(style, [])
    gestures = []
    if choices:
        kind = choices[clip.index % len(choices)]
        side_x = 0.55 if vertical else 0.9
        if kind in HOLDABLE:
            scene["props"].append({"id": "p1", "type": kind, "hold": {"actor": "hero", "hand": "R", "t": round(a + 0.2, 2)},
                                   "t_in": round(a + 0.2, 2), "enter": "pop", "idle": "none"})
            gestures.append({"t": round(a + 0.2, 2), "gesture": "hold", "side": "R", "dur": round(b - a + 0.6, 2)})
        else:
            floor = kind in ("desk", "chair", "house", "chart", "coins", "piggybank", "campfire", "rock", "plant", "lamp", "trophy", "flag")
            pos = [side_x, 0, 0.15] if floor else [side_x, 1.25, 0.1]
            scene["props"].append({"id": "p1", "type": kind, "pos": pos, "rot": [0, -0.35, 0], "t_in": round(a + 0.6, 2),
                                   "enter": "drop" if floor else "pop", "idle": "none" if floor else "bob", "scale": 0.9})
            gestures.append({"t": round(a + 0.7, 2), "gesture": "point" if face in ("surprised", "skeptical") else "present",
                             "side": "L", "target": "p1", "dur": 2.2})
    arm = _pick(ARM_GESTURES, text, None)
    if arm and not any(g["gesture"] == "hold" for g in gestures):
        gestures.append({"t": mid, "gesture": arm, "dur": 2.4})
    elif not gestures:
        gestures.append({"t": round(a + 0.3, 2), "gesture": "explain", "side": "both", "dur": round(b - a, 2)})
    hero["gestures"] = gestures
    # a second character for "they / vs / friend" lines: the hero turns to them
    if DUO.search(clip.vo or ""):
        hero["position"] = [-0.42, 0, 0]
        hero.pop("path", None)
        hero["look"] = [{"t": 0, "at": "camera"}, {"t": round(a + 0.8, 2), "at": "other"}, {"t": round(mid + 1, 2), "at": "camera"}]
        scene["actors"].append({"id": "other", "position": [0.45, 0, -0.1], "facing": -0.7, "anim": [{"t": 0, "clip": "Idle"}],
                                "face": [{"t": 0, "expr": "neutral"}, {"t": round(mid, 2), "expr": "skeptical"}],
                                "gestures": [{"t": round(mid, 2), "gesture": "crossed", "dur": 3}],
                                "color": "#c9d4e6" if clip.theme != "light" else "#4a5568"})
        scene["camera"] = [{"t": 0, "shot": {"type": "two_shot", "target": ["hero", "other"]}},
                           {"t": clip.duration, "shot": {"type": "two_shot", "target": ["hero", "other"], "zoom": 0.85}, "ease": "inOutSine"}]
        for p in scene["props"]:
            if "pos" in p:
                p["pos"] = [0.05, 1.9, -0.5]
    else:
        s1, s2 = SHOT_PAIRS[clip.index % len(SHOT_PAIRS)]
        side = 0.18 if clip.index % 2 else -0.18
        scene["camera"] = [{"t": 0, "shot": {"type": s1, "target": "hero", "side": side}},
                           {"t": round(max(1.0, mid - 0.4), 2), "shot": {"type": s1, "target": "hero", "side": side * 0.6}, "ease": "inOutSine"},
                           {"t": round(min(clip.duration - 0.5, mid + 0.6), 2), "shot": {"type": s2, "target": "hero", "side": side * 0.3}, "ease": "inOutCubic"},
                           {"t": clip.duration, "shot": {"type": s2, "target": "hero", "side": 0, "zoom": 0.94}, "ease": "inOutSine"}]
    scene["transition"] = {"in": "fade" if clip.index == 0 else "none", "out": "fade" if clip.index == clip.count - 1 else "none"}
    m = NUMBER.search(clip.vo or "")
    if m:
        scene["badges"] = [{"text": m.group(0).strip(), "t_in": round(a + 1.2, 2), "pos": [0.0, 2.15, -0.4], "size": 1.0}]
    return scene


def validate_scene(s: dict, extra_ids: set | None = None) -> list[str]:
    """Names must exist in the renderer's catalog (catalog.json), so a plan never renders something wrong."""
    C, errs = CATALOG, []
    style = s.get("style")
    if style and style not in C["styles"] and style not in C["skill_styles"]:
        errs.append(f"unknown style {style!r}")
    moods = s.get("mood", [])
    for m in ([{"mood": moods}] if isinstance(moods, str) else moods):
        if m.get("mood") not in C["moods"]:
            errs.append(f"unknown mood {m.get('mood')!r}")
    ids = {a.get("id") for a in s.get("actors", [])} | {p.get("id") for p in s.get("props", [])} | {"camera", "other"} | (extra_ids or set())
    for a in s.get("actors", []):
        # "pack:<name>" clips come from the optional animation pack (checked by the renderer, Idle if absent)
        errs += [f"unknown clip {k.get('clip')!r}" for k in a.get("anim", [])
                 if k.get("clip") not in C["clips"] and not str(k.get("clip", "")).startswith("pack:")]
        errs += [f"unknown expression {k.get('expr')!r}" for k in a.get("face", []) if k.get("expr") not in C["expressions"]]
        errs += [f"unknown gesture {g.get('gesture')!r}" for g in a.get("gestures", []) if g.get("gesture") not in C["gestures"]]
        if a.get("hat", "none") not in C["hats"]:
            errs.append(f"unknown hat {a.get('hat')!r}")
        if a.get("kind", "stickman") not in C["kinds"]:
            errs.append(f"unknown character kind {a.get('kind')!r}")
        ap = a.get("appearance") or {}
        for key, allowed in (("hair_style", "hair_styles"), ("glasses", "glasses"), ("shape", "mascot_shapes")):
            if key in ap and ap[key] not in C[allowed]:
                errs.append(f"unknown {key.replace('_', ' ')} {ap[key]!r}")
        for g in a.get("gestures", []) + a.get("look", []):
            tgt = g.get("target", g.get("at"))
            if isinstance(tgt, str) and tgt not in ids and tgt not in ("left", "right", "up", "down", "none"):
                errs.append(f"unknown target {tgt!r}")
    assets = s.get("assets") or {}
    errs += [f"unknown prop {p.get('type')!r}" for p in s.get("props", [])
             if p.get("type") not in C["props"] and not (str(p.get("type", "")).startswith("custom:") and p["type"][7:] in assets)]
    for k in s.get("camera", []):
        shot = k.get("shot")
        kind = shot if isinstance(shot, str) else (shot or {}).get("type")
        if shot and kind not in C["shots"]:
            errs.append(f"unknown shot {kind!r}")
        if not shot and not (k.get("pos") and k.get("look")):
            errs.append("camera key needs a shot or pos+look")
    if not s.get("camera"):
        errs.append("no camera keys")
    for k in ("in", "out"):
        if s.get("transition", {}).get(k, "none") not in C["transitions"]:
            errs.append(f"unknown transition {s['transition'][k]!r}")
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
        if clip.lines:
            return await self._render_dialogue(clip, log)
        out = clip.out_path
        assert out is not None
        out.parent.mkdir(parents=True, exist_ok=True)
        fps = int(self.cfg.get("fps", 24))
        # 1. voice first, so the mouth can follow the real speech
        wav = out.with_suffix(".vo.wav")
        speech = await asyncio.to_thread(tts.synth, clip.vo, wav, self.settings, clip.voice_pref, log)
        lead, tail = tts.VO_LEAD, 0.3
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
            log(f"clip {clip.index + 1}: scene plan from scenes/{override.name} ({scene.get('_planned_by', 'your file')})")
        else:
            scene = auto_scene(clip, self.cfg, talk)
        w, h = dims(clip.ratio, clip.resolution)
        scene.update({"width": w, "height": h, "fps": fps, "duration": clip.duration})
        # seams between clips are the app's: fade in only at the start of the video and out only at its end, so the
        # story never dips to black mid-video. A plan you edited in the scene editor keeps its own transitions.
        if scene.get("_planned_by") != "editor":
            for key in ("badges", "panels"):
                keep = [el for el in scene.get(key) or [] if not PLACEHOLDER.search(json.dumps(el))]
                if len(keep) != len(scene.get(key) or []):
                    log(f"clip {clip.index + 1}: removed a {key[:-1]} showing a template placeholder", "warn")
                    scene[key] = keep
            want = seam_transition(clip.index, clip.count, scene.get("transition"))
            if want != scene.get("transition"):
                log(f"clip {clip.index + 1}: transition {scene.get('transition')} -> {want} (no fade to black between clips)")
                scene["transition"] = want
        if self.cfg.get("animation_pack", "auto") == "off":
            scene["pack"] = False
        errs = validate_scene(scene)
        if errs:
            raise RenderError(f"scene plan is invalid: {'; '.join(errs[:4])}", retryable=False)
        if speech and scene.get("actors"):
            scene["actors"][0]["mouth"] = {"fps": fps, "values": mouth_envelope(speech, fps, lead, tempo, clip.duration)}
        scene_path = out.with_suffix(".scene.json")
        scene_path.write_text(json.dumps(scene, indent=1), encoding="utf-8")
        a = scene["actors"][0] if scene.get("actors") else {}
        moods = scene.get("mood", [])
        moods = moods if isinstance(moods, list) else [{"mood": moods}]
        log(f"local-threejs clip {clip.index + 1}: {w}x{h} {fps} fps · style {scene.get('style', '?')} · "
            f"mood {' → '.join(m['mood'] for m in moods) or 'neutral'} · "
            f"{' → '.join(k['clip'] for k in a.get('anim', [])) or 'no actor'} · "
            f"{' → '.join(k['expr'] for k in a.get('face', []))}"
            + (f" · gestures {', '.join(g['gesture'] for g in a.get('gestures', []))}" if a.get("gestures") else "")
            + (f" · props {', '.join(p['type'] for p in scene.get('props', []))}" if scene.get("props") else "")
            + (" · two characters" if len(scene.get("actors", [])) > 1 else "")
            + (f" · badge “{scene['badges'][0]['text']}”" if scene.get("badges") else "")
            + (" · lip sync from the voice" if a.get("mouth") else ""))
        # 3. render frames in the headless browser
        silent = out.with_suffix(".silent.mp4")
        qa = await self._render(scene_path, silent, clip, log)
        # 4. mux the voice under it
        fit = await tts.fit_to_clip(silent, speech, out, clip.duration, float(self.settings["voice"].get("max_speedup", 1.3)), lead)
        for f in (silent, wav):
            f.unlink(missing_ok=True)
        lf = await asyncio.to_thread(last_frame, out, out.with_suffix(".last.png"))
        return ClipResult(clip.index, out, clip.duration, 0.0, self.name, last_frame=lf,
                          meta={"scene": scene_path.name, "voice": bool(speech),
                                "planned_by": scene.get("_planned_by", "your file") if override.exists() else "keywords",
                                "qa": qa, **fit})

    async def _render_dialogue(self, clip: ClipSpec, log: Log) -> ClipResult:
        """Dialogue shorts: each line in its speaker's voice, laid out in the clip, one track; per-speaker lip sync;
        a hard cut per line (dialogue.build_scene); each line's real timing saved for the captions."""
        from .. import dialogue as dlg
        out = clip.out_path
        assert out is not None and clip.cast and clip.plan is not None
        out.parent.mkdir(parents=True, exist_ok=True)
        fps = int(self.cfg.get("fps", 24))
        dcfg = self.settings.get("dialogue", {})
        wpm = float(self.settings.get("speaking_wpm", 150))
        # performed lines go to ElevenLabs' most expressive model with a drama preset (low stability), whatever the
        # narrated videos use; other engines get the words without the audio tags (tts.synth removes them)
        vs = {**self.settings, "voice": {**self.settings["voice"],
                                         "elevenlabs_model": dcfg.get("elevenlabs_model", "eleven_v4"),
                                         "elevenlabs_stability": float(dcfg.get("elevenlabs_stability", 0.3)),
                                         "elevenlabs_similarity": float(dcfg.get("elevenlabs_similarity", 0.8))}}
        parts, durs = [], []
        for k, ln in enumerate(clip.lines):
            voice = clip.cast[ln["speaker"]]["voice"]
            f = out.with_suffix(f".line{k:02d}.wav")
            got = await asyncio.to_thread(tts.synth, ln["text"], f, vs, voice, log)
            if got and voice == "mascot":
                await asyncio.to_thread(tts.pitch, got, float(dcfg.get("mascot_pitch", 1.0)))
            parts.append(got)
            durs.append(probe(got)["duration"] if got else dlg.line_seconds(ln["text"], wpm))
        timing = dlg.layout(durs, [dlg.timing_of(ln) for ln in clip.lines], clip.duration,
                            float(self.settings["voice"].get("max_speedup", 1.3)), pad=False)
        dur = dlg.clip_end(timing, clip.duration, fps)      # the clip ends when its talk does: no dead air before the next
        if timing["tempo"] > 1.001:
            log(f"clip {clip.index + 1}: lines sped up x{timing['tempo']} to fit 10 s", "warn")
        if timing["overflow"] > 0.05:
            log(f"clip {clip.index + 1}: the lines run {timing['overflow']:.1f}s past the clip even sped up; the last one is cut "
                "(re-run Script for shorter lines)", "warn")
        mix = out.with_suffix(".vo.wav")
        voiced = any(parts)
        if voiced:
            await asyncio.to_thread(tts.assemble, parts, timing["starts"], timing["tempo"], mix, dur)
            envelope = mouth_envelope(mix, fps, 0.0, 1.0, dur)
        else:
            envelope = [0.0] * int(round(dur * fps))
        w, h = dims(clip.ratio, clip.resolution)
        scene = dlg.build_scene(clip.plan, timing, clip.cast, dlg.speaker_mouths(envelope, clip.plan, timing, fps), fps, w, h,
                                dur, seed=7 + clip.index * 31, quality=self.cfg.get("quality", "high"),
                                theme=clip.theme if clip.theme == "light" else "dark", dof=float(dcfg.get("dof", 0.035)),
                                motion=str(dcfg.get("motion", "still")))
        if self.cfg.get("animation_pack", "auto") == "off":
            scene["pack"] = False
        errs = validate_scene(scene)
        if errs:
            raise RenderError(f"dialogue scene is invalid: {'; '.join(errs[:4])}", retryable=False)
        scene_path = out.with_suffix(".scene.json")
        scene_path.write_text(json.dumps(scene, indent=1), encoding="utf-8")
        names = {k: clip.cast[k]["name"] for k in dlg.SPEAKERS}
        log(f"local-threejs clip {clip.index + 1}: dialogue, {len(clip.lines)} lines · "
            + ", ".join(dlg.shot_label(p["shot"], names) for p in clip.plan)
            + (" · lip sync from the voices" if voiced else " · no voice engine: silent"))
        silent = out.with_suffix(".silent.mp4")
        qa = await self._render(scene_path, silent, clip, log)
        fit = await tts.mux_exact(silent, mix if voiced else None, out, dur)
        for f in [silent, mix, *[x for x in parts if x]]:
            f.unlink(missing_ok=True)
        lf = await asyncio.to_thread(last_frame, out, out.with_suffix(".last.png"))
        timed = [{"i": ln["i"], "speaker": ln["speaker"], "text": dlg.clean(ln["text"]), "start": t0, "end": t1}
                 for ln, t0, t1 in zip(clip.lines, timing["starts"], timing["ends"])]
        return ClipResult(clip.index, out, dur, 0.0, self.name, last_frame=lf,
                          meta={"scene": scene_path.name, "voice": voiced, "planned_by": "dialogue", "qa": qa, "lines": timed,
                                "speech_window": [timed[0]["start"], timed[-1]["end"]] if timed else None,
                                "tempo": timing["tempo"], **fit})

    async def _render(self, scene_path: Path, out: Path, clip: ClipSpec, log: Log) -> dict:
        env = {**__import__("os").environ, "FFMPEG_PATH": ffmpeg_bin()}
        if self.cfg.get("browser_path"):
            env["VSS_BROWSER_PATH"] = self.cfg["browser_path"]
        if self.cfg.get("browser_channel"):
            env["VSS_BROWSER_CHANNEL"] = self.cfg["browser_channel"]
        proc = await asyncio.create_subprocess_exec(
            shutil.which("node") or "node", str(RENDERER / "render.mjs"), "--scene", str(scene_path), "--out", str(out),
            cwd=str(RENDERER), env=env, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        t0, last_note, error, qa = time.time(), 0.0, None, {}
        assert proc.stdout is not None
        async for raw in proc.stdout:
            try:
                ev = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if ev.get("event") == "info":
                if ev.get("pack"):
                    log(f"clip {clip.index + 1}: animation pack in use ({len(ev['pack']['clips'])} clips; "
                        f"{', '.join(f'{k}→{v}' for k, v in list(ev['pack']['aliases'].items())[:5])})")
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
            elif ev.get("event") == "qa":
                qa = {k: v for k, v in ev.items() if k != "event"}
            elif ev.get("event") in ("error", "page-error"):
                error = ev.get("message")
        err = (await proc.stderr.read()).decode(errors="replace") if proc.stderr else ""
        await proc.wait()
        if proc.returncode != 0 or not out.exists():
            raise RenderError(f"three.js renderer failed: {(error or err.strip()[-400:] or f'exit {proc.returncode}')[:500]}",
                              retryable=False)
        log(f"clip {clip.index + 1}: rendered in {time.time() - t0:.0f}s")
        for line, level in qa_lines(qa, clip.index + 1):
            log(line, level)
        return qa


def seam_transition(index: int, count: int, current: dict | None = None) -> dict:
    """Fade in at the very start, out at the very end, hard cuts between clips (the voice carries straight on)."""
    cur = current or {}
    return {**cur, "in": cur.get("in", "fade") if index == 0 else "none",
            "out": cur.get("out", "fade") if index == count - 1 else "none"}


def qa_lines(qa: dict, n: int) -> list[tuple[str, str]]:
    """The renderer's frame report as log lines: problems as warnings, the summary as info."""
    if not qa:
        return []
    out = []
    if qa.get("frames") != qa.get("expected"):
        out.append((f"clip {n}: QA rendered {qa.get('frames')} of {qa.get('expected')} frames", "warn"))
    for a, b in qa.get("black", []):
        out.append((f"clip {n}: QA near-black frames {a:.2f}-{b:.2f}s with no fade planned there (an empty view?)", "warn"))
    for a, b in qa.get("blown", []):
        out.append((f"clip {n}: QA over a quarter of the frame is pure white {a:.2f}-{b:.2f}s", "warn"))
    g = qa.get("guarded_frames", 0)
    out.append((f"clip {n}: QA {qa.get('frames')} frames, mean brightness {qa.get('mean_luma')}/255"
                + (f", highlight guard lowered exposure on {g} frame(s) (to x{qa.get('min_exposure_scale')})" if g else ""), "info"))
    return out


# ---- checking and repairing a scene plan written by an AI -----------------------------------------

LIMITS = {"actors": 2, "props": 3, "panels": 2, "badges": 2}
DIGITS = re.compile(r"\d[\d,.]*")
PLACEHOLDER = re.compile(r"\{\{[^{}]*\}\}|\(\([^()]*\)\)|\[\[[^\[\]]*\]\]")


def _nums(text: str) -> set[str]:
    return {m.group(0).replace(",", "").rstrip(".") for m in DIGITS.finditer(text or "")}


_NUM_KEYS = {"t", "dur", "t_in", "t_out", "until", "amount", "speed", "intensity", "scale", "height", "seed", "zoom"}
_VEC_KEYS = {"pos", "rot", "size", "position", "at", "target"}
_NUM_RE = re.compile(r"^-?\d+(\.\d+)?$")
_LISTS = ("mood", "actors", "props", "badges", "panels", "camera", "anim", "face", "gestures", "look", "path")


def _coerce(v, key=""):
    """Undo the type slips models make in structured output: JSON objects/arrays sent as strings, and numbers
    sent as strings ("720", "1.5"). Only numeric fields become numbers, so on-screen text stays text."""
    if isinstance(v, str):
        t = v.strip()
        if t[:1] in "{[" and t[-1:] in "}]":
            try:
                return _coerce(json.loads(t), key)
            except json.JSONDecodeError:
                return v
        if (key in _NUM_KEYS or key == "#") and _NUM_RE.match(t):
            return float(t)
        return v
    if isinstance(v, dict):
        return {k: _coerce(x, k) for k, x in v.items()}
    if isinstance(v, list):
        return [_coerce(x, "#" if key in _VEC_KEYS else key) for x in v]
    return v


def check_and_repair(scene: dict, vo: str, duration: float, vertical: bool = True,
                     known_assets: set | None = None) -> tuple[dict, list[str], list[str]]:
    """Make an AI-written plan safe to render. Unknown names fall back to safe defaults, times and positions
    are clamped into the clip and the frame, clutter is trimmed, and on-screen numbers the voiceover does not
    say are removed (never invent a statistic). Returns (scene, fixes made, errors that remain)."""
    C, fixes = CATALOG, []
    s = _coerce(json.loads(json.dumps(scene)))
    for key in _LISTS[:6]:                                          # entries must be objects: drop stray strings
        if isinstance(s.get(key), list) and any(not isinstance(x, dict) for x in s[key]):
            if key == "mood":                                       # ["calm", ...] is still readable
                s[key] = [x if isinstance(x, dict) else {"t": 0, "mood": x} for x in s[key]]
                continue
            fixes.append(f"dropped {sum(not isinstance(x, dict) for x in s[key])} malformed {key} entr(ies)")
            s[key] = [x for x in s[key] if isinstance(x, dict)]
    for a in s.get("actors") or []:
        for key in _LISTS[6:]:
            if key in a and (not isinstance(a[key], list) or any(not isinstance(x, dict) for x in a[key])):
                fixes.append(f"dropped malformed {key} on {a.get('id', 'actor')}")
                a[key] = [x for x in a[key] if isinstance(x, dict)] if isinstance(a[key], list) else []
    T = lambda v: round(min(max(float(v or 0), 0.0), duration), 2)  # noqa: E731
    xr = 1.2 if vertical else 2.2
    clampv = lambda v, lo, hi: [round(min(max(float(v[0]), lo[0]), hi[0]), 2), round(min(max(float(v[1]), lo[1]), hi[1]), 2),  # noqa: E731
                                round(min(max(float(v[2]), lo[2]), hi[2]), 2)] if isinstance(v, list) and len(v) == 3 else None
    if s.get("style") not in C["styles"] and s.get("style") not in C["skill_styles"]:
        fixes.append(f"style {s.get('style')!r} -> minimal"); s["style"] = "minimal"
    moods = s.get("mood") or [{"t": 0, "mood": "neutral"}]
    moods = [{"t": 0, "mood": moods}] if isinstance(moods, str) else moods
    for m in moods:
        if m.get("mood") not in C["moods"]:
            fixes.append(f"mood {m.get('mood')!r} -> neutral"); m["mood"] = "neutral"
        m["t"] = T(m.get("t"))
    s["mood"] = sorted(moods, key=lambda m: m["t"])
    for key, n in LIMITS.items():
        if len(s.get(key) or []) > n:
            fixes.append(f"kept {n} of {len(s[key])} {key}"); s[key] = s[key][:n]
    actors = s.get("actors") or []
    if not actors:
        fixes.append("added the hero"); actors = [{"id": "hero"}]
    actors[0].setdefault("id", "hero")
    prop_ids = []
    assets0 = s.get("assets") or {}
    for i, p in enumerate(s.get("props") or []):
        p.setdefault("id", f"p{i + 1}")
        t = str(p.get("type", ""))
        # only props that survive the checks below can be pointed at or looked at
        if t in C["props"] or (t == "new" and p.get("asset")) or (t.startswith("custom:") and (
                t[7:] in assets0 or t[7:] in (known_assets or ()))):
            prop_ids.append(p["id"])
    ids = {a.get("id") for a in actors} | set(prop_ids) | {"camera"}
    for a in actors:
        for k in a.get("anim", []):
            if k.get("clip") not in C["clips"] and not str(k.get("clip", "")).startswith("pack:"):
                fixes.append(f"clip {k.get('clip')!r} -> Idle"); k["clip"] = "Idle"
            k["t"] = T(k.get("t"))
        for k in a.get("face", []):
            if k.get("expr") not in C["expressions"]:
                fixes.append(f"expression {k.get('expr')!r} -> neutral"); k["expr"] = "neutral"
            k["t"] = T(k.get("t"))
        kept = []
        for g in a.get("gestures", []):
            if g.get("gesture") not in C["gestures"]:
                fixes.append(f"dropped gesture {g.get('gesture')!r}"); continue
            if isinstance(g.get("target"), str) and g["target"] not in ids:
                fixes.append(f"gesture target {g['target']!r} removed"); g.pop("target")
            g["t"] = T(g.get("t")); g["dur"] = round(min(max(float(g.get("dur", 1.8)), 0.6), duration - g["t"] + 0.5), 2)
            kept.append(g)
        a["gestures"] = kept
        look = []
        for k in a.get("look", []):
            at = k.get("at")
            if isinstance(at, str) and at not in ids and at not in ("left", "right", "up", "down", "none"):
                fixes.append(f"look target {at!r} -> camera"); k["at"] = "camera"
            k["t"] = T(k.get("t")); look.append(k)
        if look:
            a["look"] = look
        if a.get("hat", "none") not in C["hats"]:
            fixes.append(f"hat {a.get('hat')!r} removed"); a.pop("hat")
        if a.get("position") is not None:
            a["position"] = clampv(a["position"], [-xr, 0, -2], [xr, 0, 1]) or [0, 0, 0]
        for k in a.get("path", []):
            pos = k.get("pos", [0, 0, 0])
            k["pos"] = clampv(pos if len(pos) == 3 else [pos[0], 0, pos[1]], [-2.5, 0, -2], [2.5, 0, 1]); k["t"] = T(k.get("t"))
        for key in ("anim", "face", "gestures", "path"):
            if a.get(key):
                a[key] = sorted(a[key], key=lambda k: k["t"])
    s["actors"] = actors
    props = []
    assets = s.get("assets") or {}
    for p in s.get("props") or []:
        t = str(p.get("type", ""))
        pending = t == "new" and p.get("asset")                     # to be drawn by the scene_plan stage
        custom = t.startswith("custom:") and (t[7:] in assets or t[7:] in (known_assets or ()))
        if t not in C["props"] and not pending and not custom:
            fixes.append(f"dropped prop {p.get('type')!r}"); continue
        if p.get("pos") is not None:
            # not closer to the camera than the actor's front (a prop at z 1.2 sat inside close-up shots)
            p["pos"] = clampv(p["pos"], [-xr, 0, -2.5], [xr, 2.4, 0.6])
        if p.get("hold") and not isinstance(p["hold"], dict):      # "hero", "R" or true -> held by that actor
            h = p["hold"]
            p["hold"] = {"hand": h} if h in ("L", "R") else {"actor": h} if isinstance(h, str) else {}
        if p.get("hold") and p["hold"].get("actor") not in ids:
            p["hold"]["actor"] = actors[0]["id"]
        p["t_in"] = T(p.get("t_in"))
        props.append(p)
    s["props"] = props
    said = _nums(vo)
    for key in ("badges", "panels"):
        kept = []
        for el in s.get(key) or []:
            el["t_in"] = T(el.get("t_in"))
            if el.get("pos") is not None:
                el["pos"] = clampv(el["pos"], [-xr, 0.3, -3], [xr, 2.8, 0.5])
            code = key == "panels" and (el.get("kind") == "code" or re.search(r"\.\w+$", el.get("title", "")))
            texts = [el.get("text", ""), el.get("title", "")] + ([] if code else el.get("lines", []))
            if any(PLACEHOLDER.search(str(x)) for x in texts):
                fixes.append(f"removed a {key[:-1]} showing a template placeholder (fill it in the script first)"); continue
            bad = sorted(set().union(*(_nums(x) for x in texts)) - said)
            if bad:
                fixes.append(f"removed a {key[:-1]} showing {', '.join(bad)} (not said in the voiceover)"); continue
            kept.append(el)
        s[key] = kept
    cams = []
    for k in s.get("camera") or []:
        shot = k.get("shot")
        kind = shot if isinstance(shot, str) else (shot or {}).get("type")
        if shot and kind not in C["shots"]:
            fixes.append(f"shot {kind!r} -> medium")
            k["shot"] = {**(shot if isinstance(shot, dict) else {}), "type": "medium"}
        if not shot and not (k.get("pos") and k.get("look")):
            k["shot"] = "medium"
        z = k["shot"].get("zoom") if isinstance(k.get("shot"), dict) else None
        lo = 0.9 if kind == "closeup" else 0.75                # a closer close-up is just a face filling the frame
        if isinstance(z, (int, float)) and not lo <= z <= 1.6:
            fixes.append(f"camera zoom {z} -> {min(1.6, max(lo, z))}")
            k["shot"]["zoom"] = min(1.6, max(lo, z))
        k["t"] = T(k.get("t")); cams.append(k)
    if not cams:
        fixes.append("added a medium shot"); cams = [{"t": 0, "shot": {"type": "medium", "target": actors[0]["id"]}}]
    s["camera"] = sorted(cams, key=lambda k: k["t"])
    tr = s.get("transition") or {}
    for side in ("in", "out"):
        if tr.get(side, "none") not in C["transitions"]:
            fixes.append(f"transition {tr[side]!r} -> none"); tr[side] = "none"
    s["transition"] = tr
    # the look is the style's: exposure/bloom/shake from a plan are kept inside safe ranges (they blew frames out)
    for key, lo, hi in (("exposure", 0.8, 1.15), ("handheld", 0.0, 0.025)):
        if key in s and not (isinstance(s[key], (int, float)) and lo <= s[key] <= hi):
            fixes.append(f"{key} {s[key]!r} -> {'default' if not isinstance(s[key], (int, float)) else min(hi, max(lo, s[key]))}")
            if isinstance(s[key], (int, float)):
                s[key] = min(hi, max(lo, s[key]))
            else:
                s.pop(key)
    if "bloom" in s:
        fixes.append("bloom settings removed (the style decides the glow)"); s.pop("bloom")
    # pending AI-drawn props and library props are resolved by the caller; validate the rest
    probe = {**s, "props": [p for p in s["props"] if p.get("type") != "new" and not (
        str(p.get("type", "")).startswith("custom:") and p["type"][7:] not in (s.get("assets") or {}))]}
    return s, fixes, validate_scene(probe, {p.get("id") for p in s["props"]})


async def render_still(scene: dict, out_png: Path, t: float = 1.0, timeout: float = 180) -> Path | None:
    """One PNG frame of a scene (prop previews, editor previews). None when the renderer is not ready."""
    if not status()["ok"]:
        return None
    import tempfile
    work = Path(tempfile.mkdtemp(prefix="vss-still-"))
    sp = work / "scene.json"
    sp.write_text(json.dumps(scene), encoding="utf-8")
    env = {**__import__("os").environ, "FFMPEG_PATH": ffmpeg_bin()}
    cfg = load_settings()["render"].get("threejs", {})
    if cfg.get("browser_path"):
        env["VSS_BROWSER_PATH"] = cfg["browser_path"]
    if cfg.get("browser_channel"):
        env["VSS_BROWSER_CHANNEL"] = cfg["browser_channel"]
    proc = await asyncio.create_subprocess_exec(shutil.which("node") or "node", str(RENDERER / "render.mjs"), "--scene", str(sp),
                                                "--stills", f"{t:.2f}", "--out-dir", str(work), cwd=str(RENDERER), env=env,
                                                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout)
    except asyncio.TimeoutError:
        proc.kill()
        raise RenderError("preview render timed out", retryable=False)
    png = work / f"still-{t:.2f}.png"
    if proc.returncode != 0 or not png.exists():
        msg = next((json.loads(x).get("message") for x in out.decode(errors="replace").splitlines()
                    if x.startswith("{") and '"error"' in x), None)
        raise RenderError(f"preview failed: {msg or err.decode(errors='replace')[-300:]}", retryable=False)
    out_png.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(png), out_png)
    shutil.rmtree(work, ignore_errors=True)
    return out_png
