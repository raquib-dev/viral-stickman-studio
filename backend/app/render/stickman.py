"""Procedural stick-figure animator: a posed, jointed stickman drawn frame by frame (Pillow, 2x supersampled)
and piped into ffmpeg. Fully offline, deterministic and free. Actions and props are picked from each
clip's beat purpose and voiceover by keyword, so a 60 s video gets varied but consistent scenes.

Every clip starts and ends in the same neutral pose at the same spot, so first-frame continuity is exact.
"""
from __future__ import annotations

import math
import random
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw

from ..settings import ffmpeg_bin

THEMES = {"dark": {"bg": (14, 16, 20), "ink": (238, 238, 238), "accent": (255, 196, 0), "soft": (60, 64, 72)},
          "light": {"bg": (250, 249, 245), "ink": (24, 24, 24), "accent": (232, 96, 44), "soft": (205, 205, 200)}}

# joint angles in radians from straight down; +ve swings toward screen-right. Elbows/knees are relative.
NEUTRAL = dict(l_sh=-0.22, l_el=0.12, r_sh=0.22, r_el=-0.12, l_hip=-0.14, l_kn=0.02, r_hip=0.14, r_kn=-0.02,
               lean=0.0, head=0.0, dy=0.0)
POSES = {
    "explain": dict(NEUTRAL, r_sh=1.25, r_el=-0.9, l_sh=-0.5, l_el=0.6, head=0.05),
    "explain2": dict(NEUTRAL, r_sh=0.9, r_el=-1.2, l_sh=-1.1, l_el=0.8, head=-0.05),
    "point": dict(NEUTRAL, r_sh=2.25, r_el=0.0, l_sh=-0.3, l_el=0.4, head=0.12),
    "think": dict(NEUTRAL, r_sh=0.55, r_el=-2.55, l_sh=0.45, l_el=1.35, head=0.18, lean=-0.04),
    "celebrate": dict(NEUTRAL, l_sh=-2.7, l_el=-0.2, r_sh=2.7, r_el=0.2, l_hip=-0.35, r_hip=0.35, dy=-0.06),
    "sad": dict(NEUTRAL, l_sh=-0.05, l_el=0.0, r_sh=0.05, r_el=0.0, lean=0.22, head=0.4, dy=0.02),
    "shrug": dict(NEUTRAL, l_sh=-1.2, l_el=1.7, r_sh=1.2, r_el=-1.7, head=-0.12),
    "stop": dict(NEUTRAL, r_sh=1.6, r_el=-1.45, l_sh=-0.3, l_el=0.2, lean=-0.05),
    "walk_a": dict(NEUTRAL, l_hip=-0.45, l_kn=0.15, r_hip=0.4, r_kn=-0.55, l_sh=0.35, r_sh=-0.35, l_el=0.3, r_el=0.3),
    "walk_b": dict(NEUTRAL, l_hip=0.4, l_kn=-0.55, r_hip=-0.45, r_kn=0.15, l_sh=-0.35, r_sh=0.35, l_el=0.3, r_el=0.3),
}
ACTIONS = [  # (action, keywords) checked in order; first match wins
    ("celebrate", r"win|won|success|happy|celebrat|finally|rich|free|growth|best|yes\b|amazing"),
    ("sad", r"fail|lost|lose|broke|sad|regret|mistake|debt|tired|stuck|wrong|problem|pain"),
    ("think", r"think|why|wonder|question|\?|idea|realis|consider|imagine|brain|mind|psycholog"),
    ("walk", r"walk|journey|step|move|path|go\b|going|habit|daily|routine|progress|start"),
    ("stop", r"stop|don't|never|avoid|trap|warning|careful|instead|but\b"),
    ("shrug", r"maybe|most people|everyone|nobody|confus|random"),
    ("point", r"look|this|here|notice|see|show|first|rule|secret|key|truth"),
]
PROPS = [
    ("coin", r"money|\$|cash|save|saving|spend|invest|price|cost|budget|rich|income|salary|pay"),
    ("bulb", r"idea|realis|learn|insight|tip|trick|secret|smart|brain"),
    ("clock", r"time|minute|hour|day|year|wait|later|late|deadline|future|today"),
    ("chart", r"grow|growth|percent|%|compound|increase|more|rise|stock|market|result"),
    ("question", r"why|what|how|\?|wonder|question"),
    ("heart", r"love|feel|emotion|happy|friend|family|relationship"),
    ("warning", r"warning|danger|trap|mistake|never|avoid|stop"),
]
DUO = r"\bvs\b|versus|compare|friend|other people|they\b|someone|partner|two\b"


@dataclass
class Scene:
    actions: list[str]
    prop: str | None
    duo: bool
    seed: int
    prop_at: float = 0.6  # clip 1 waits for the hook card (first 2.4 s) to clear the top of the frame


def plan_scene(index: int, label: str, vo: str, prompt: str = "") -> Scene:
    # beat purpose + voiceover only: Phase B prompts repeat the style anchor ("exactly two arms", "no face"),
    # which would match the same keywords in every clip
    text = f"{label} {vo}".lower() if (label or vo) else prompt[:600].lower()
    found = [a for a, rx in ACTIONS if re.search(rx, text)]
    primary = found[0] if found else ("explain" if index % 2 == 0 else "point")
    secondary = "explain" if primary != "explain" else "point"
    prop = next((p for p, rx in PROPS if re.search(rx, text)), None)
    return Scene([primary, secondary], prop, bool(re.search(DUO, text)), seed=index * 7919 + len(vo),
                 prop_at=2.6 if index == 0 else 0.6)


def _smooth(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


def _mix(a: dict, b: dict, t: float) -> dict:
    return {k: a[k] + (b[k] - a[k]) * t for k in a}


def pose_at(scene: Scene, t: float, dur: float) -> dict:
    """Neutral in, two actions, neutral out; walk cycles; breathing and talk-nod on top."""
    ease = 0.45
    if t < ease or t > dur - ease:
        k = _smooth(t / ease) if t < ease else _smooth((dur - t) / ease)
        target = _action_pose(scene.actions[0], ease if t < ease else dur - ease)
        p = _mix(NEUTRAL, target, k)
    else:
        mid = ease + (dur - 2 * ease) * 0.62
        if t < mid - 0.3:
            p = _action_pose(scene.actions[0], t)
        elif t > mid + 0.3:
            p = _action_pose(scene.actions[1], t)
        else:
            k = _smooth((t - (mid - 0.3)) / 0.6)
            p = _mix(_action_pose(scene.actions[0], t), _action_pose(scene.actions[1], t), k)
    p = dict(p)
    p["dy"] += 0.006 * math.sin(t * 2 * math.pi * 0.5)          # breathing
    p["head"] += 0.04 * math.sin(t * 2 * math.pi * 1.7)          # talking nod
    return p


def _action_pose(action: str, t: float) -> dict:
    if action == "walk":
        k = (math.sin(t * 2 * math.pi * 1.1) + 1) / 2
        return _mix(POSES["walk_a"], POSES["walk_b"], k)
    if action == "explain":
        k = (math.sin(t * 2 * math.pi * 0.45) + 1) / 2
        return _mix(POSES["explain"], POSES["explain2"], _smooth(k))
    if action == "celebrate":
        p = dict(POSES["celebrate"])
        p["dy"] = -0.06 * abs(math.sin(t * 2 * math.pi * 1.2))
        return p
    return POSES.get(action, NEUTRAL)


def _limb(d: ImageDraw.ImageDraw, x, y, a, length, w, color):
    ex, ey = x + length * math.sin(a), y + length * math.cos(a)
    d.line([(x, y), (ex, ey)], fill=color, width=w)
    r = w / 2
    d.ellipse([ex - r, ey - r, ex + r, ey + r], fill=color)
    return ex, ey


def draw_figure(d: ImageDraw.ImageDraw, cx: float, ground: float, h: float, p: dict, color, flip: bool = False):
    s = -1 if flip else 1
    w = max(4, int(h * 0.028))
    hip = (cx, ground - h * 0.42 + p["dy"] * h)
    lean = p["lean"] * s
    torso = h * 0.3
    sh = (hip[0] + torso * math.sin(lean), hip[1] - torso * math.cos(lean))
    for side in ("l", "r"):
        ha = p[f"{side}_hip"] * s
        kx, ky = _limb(d, *hip, ha, h * 0.21, w, color)
        _limb(d, kx, ky, ha + p[f"{side}_kn"] * s, h * 0.21, w, color)
    d.line([hip, sh], fill=color, width=w)
    for side in ("l", "r"):
        a = p[f"{side}_sh"] * s
        ex, ey = _limb(d, *sh, a, h * 0.16, w, color)
        _limb(d, ex, ey, a + p[f"{side}_el"] * s, h * 0.15, w, color)
    r = h * 0.085
    na = lean + p["head"] * 0.5 * s
    hx, hy = sh[0] + (r + h * 0.03) * math.sin(na), sh[1] - (r + h * 0.03) * math.cos(na)
    d.ellipse([hx - r, hy - r, hx + r, hy + r], outline=color, width=w)
    eye = max(2, w // 2)
    for ox in (-0.32, 0.32):  # simple line expression, no detailed features (style 1)
        ex = hx + r * ox + r * 0.18 * math.sin(p["head"]) * s
        d.ellipse([ex - eye / 2, hy - r * 0.15 - eye / 2, ex + eye / 2, hy - r * 0.15 + eye / 2], fill=color)


def draw_prop(d: ImageDraw.ImageDraw, kind: str, cx: float, cy: float, size: float, t: float, theme: dict,
              start: float = 0.6):
    pop = _smooth((t - start) / 0.5)
    if pop <= 0:
        return
    s = size * (0.6 + 0.4 * pop) * (1 + 0.04 * math.sin(t * 3))
    cy = cy + 0.05 * size * math.sin(t * 2.2)
    a, ink = theme["accent"], theme["ink"]
    w = max(4, int(size * 0.07))
    if kind == "coin":
        d.ellipse([cx - s / 2, cy - s / 2, cx + s / 2, cy + s / 2], outline=a, width=w)
        d.line([(cx, cy - s * 0.3), (cx, cy + s * 0.3)], fill=a, width=w)
        d.arc([cx - s * 0.18, cy - s * 0.24, cx + s * 0.18, cy], 90, 360, fill=a, width=w)
        d.arc([cx - s * 0.18, cy, cx + s * 0.18, cy + s * 0.24], 270, 180, fill=a, width=w)
    elif kind == "bulb":
        d.ellipse([cx - s * 0.32, cy - s * 0.45, cx + s * 0.32, cy + s * 0.15], outline=a, width=w)
        d.rectangle([cx - s * 0.14, cy + s * 0.15, cx + s * 0.14, cy + s * 0.32], outline=a, width=w)
        for k in range(5):
            ang = math.pi * (0.15 + 0.175 * k) + math.pi
            d.line([(cx + s * 0.45 * math.cos(ang), cy - s * 0.15 + s * 0.45 * math.sin(ang)),
                    (cx + s * 0.6 * math.cos(ang), cy - s * 0.15 + s * 0.6 * math.sin(ang))], fill=a, width=w)
    elif kind == "clock":
        d.ellipse([cx - s / 2, cy - s / 2, cx + s / 2, cy + s / 2], outline=a, width=w)
        ang = t * 2.4
        d.line([(cx, cy), (cx + s * 0.32 * math.sin(ang), cy - s * 0.32 * math.cos(ang))], fill=a, width=w)
        d.line([(cx, cy), (cx + s * 0.22 * math.sin(ang / 12), cy - s * 0.22 * math.cos(ang / 12))], fill=ink, width=w)
    elif kind == "chart":
        bars = [0.3, 0.45, 0.62, 0.9]
        bw = s / 6
        for k, b in enumerate(bars):
            hgt = s * b * min(1.0, pop * 1.2)
            x0 = cx - s / 2 + k * bw * 1.5
            d.rectangle([x0, cy + s / 2 - hgt, x0 + bw, cy + s / 2], fill=a if k == 3 else theme["soft"])
        d.line([(cx - s / 2, cy + s * 0.2), (cx + s / 2, cy - s * 0.45)], fill=ink, width=w)
    elif kind == "question":
        d.arc([cx - s * 0.25, cy - s * 0.5, cx + s * 0.25, cy], 180, 400, fill=a, width=w)
        d.line([(cx + s * 0.05, cy - s * 0.05), (cx, cy + s * 0.18)], fill=a, width=w)
        d.ellipse([cx - w, cy + s * 0.3 - w, cx + w, cy + s * 0.3 + w], fill=a)
    elif kind == "heart":
        r = s * 0.25
        d.ellipse([cx - 2 * r, cy - r * 1.6, cx, cy + r * 0.4], fill=a)
        d.ellipse([cx, cy - r * 1.6, cx + 2 * r, cy + r * 0.4], fill=a)
        d.polygon([(cx - 1.95 * r, cy - r * 0.35), (cx + 1.95 * r, cy - r * 0.35), (cx, cy + r * 1.9)], fill=a)
    elif kind == "warning":
        d.polygon([(cx, cy - s / 2), (cx + s / 2, cy + s * 0.4), (cx - s / 2, cy + s * 0.4)], outline=a, width=w)
        d.line([(cx, cy - s * 0.15), (cx, cy + s * 0.12)], fill=a, width=w)
        d.ellipse([cx - w * 0.7, cy + s * 0.22, cx + w * 0.7, cy + s * 0.3], fill=a)


def render_frames(scene: Scene, w: int, h: int, fps: int, dur: float, theme_name: str = "dark"):
    """Yield RGB frames (bytes) for one clip."""
    theme = THEMES.get(theme_name, THEMES["dark"])
    ss = 2
    W, H = w * ss, h * ss
    vertical = h > w
    # stay inside the band the stitch leaves free: hook card on top, word captions above the bottom safe zone
    # (9:16 captions sit at ~55-63% of the height, 16:9 at ~78-88%; see overlays.py)
    fig_h = (H * 0.27) if vertical else (H * 0.5)
    ground = H * (0.525 if vertical else 0.74)
    cx = W * (0.5 if vertical else 0.4)
    prop_xy = (W * 0.5, H * 0.17) if vertical else (W * 0.72, H * 0.3)
    rnd = random.Random(scene.seed)
    dashes = [(rnd.random(), rnd.random() * 0.5 + 0.2) for _ in range(9)]
    n = int(round(dur * fps))
    for i in range(n):
        t = i / fps
        img = Image.new("RGB", (W, H), theme["bg"])
        d = ImageDraw.Draw(img)
        lw = max(2, int(fig_h * 0.012))
        d.line([(W * 0.08, ground + lw), (W * 0.92, ground + lw)], fill=theme["soft"], width=lw)
        if "walk" in scene.actions:  # ground marks scroll so walking in place reads as moving
            for x0, ln in dashes:
                x = ((x0 - t * 0.12) % 1.0) * W
                d.line([(x, ground + lw * 5), (x + W * 0.04 * ln, ground + lw * 5)], fill=theme["soft"], width=lw)
        p = pose_at(scene, t, dur)
        if scene.duo:
            draw_figure(d, cx - fig_h * 0.42, ground, fig_h * 0.92, p, theme["ink"])
            p2 = pose_at(Scene(["shrug", "explain"], None, False, scene.seed + 1), t, dur)
            draw_figure(d, cx + fig_h * 0.42, ground, fig_h * 0.92, p2, theme["ink"], flip=True)
        else:
            draw_figure(d, cx, ground, fig_h, p, theme["ink"])
        if scene.prop:
            draw_prop(d, scene.prop, prop_xy[0], prop_xy[1], fig_h * 0.42, t, theme, scene.prop_at)
        zoom = 1.0 + 0.06 * _smooth(t / dur)  # slow push-in
        cw, ch = W / zoom, H / zoom
        yield img.resize((w, h), Image.BILINEAR, box=((W - cw) / 2, (H - ch) / 2, (W + cw) / 2, (H + ch) / 2)).tobytes()


def write_clip(scene: Scene, out: Path, w: int, h: int, fps: int, dur: float, theme: str = "dark") -> Path:
    cmd = [ffmpeg_bin(), "-hide_banner", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
           "-s", f"{w}x{h}", "-r", str(fps), "-i", "-", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "veryfast",
           "-crf", "18", str(out)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    assert proc.stdin is not None
    try:
        for frame in render_frames(scene, w, h, fps, dur, theme):
            proc.stdin.write(frame)
    finally:
        proc.stdin.close()
        err = proc.stderr.read().decode(errors="replace") if proc.stderr else ""
        proc.wait()
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg (stickman) failed: {err[-400:]}")
    return out
