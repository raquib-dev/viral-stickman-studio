"""AI-drawn props for the three.js renderer (Phase 4).

A prop the catalog lacks ("a dragon", "a bank vault") is drawn by the writing model as DATA: low-poly shapes,
each with a colour role from the palette and an optional motion. normalize_asset() checks and repairs a drawing
(known shapes/colours/motions only, sizes clamped, at most 40 parts) and rescales it so it stands on the floor
at a sensible height. Drawings are cached per project (projects/<slug>/assets/<key>.json) and can be saved to
the shared library (config/assets/) so every project can reuse them.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

from ..paths import CONFIG, project_dir
from .threejs import CATALOG

LIBRARY = CONFIG / "assets"
MAX_PARTS = 40
SIZE_ARITY = {"box": 3, "sphere": 1, "ico": 1, "cylinder": 3, "cone": 2, "torus": 3, "capsule": 2, "pyramid": 2, "wedge": 3}


def asset_key(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")[:40] or "prop"


def _f(v, lo, hi, default):
    try:
        return round(min(max(float(v), lo), hi), 4)
    except (TypeError, ValueError):
        return default


def _extent(pt: dict) -> float:
    """Rough half-size of a part, for the bounding box."""
    sz = pt.get("size") or [0.1]
    sc = max(pt.get("scale") or [1, 1, 1])
    shape = pt["shape"]
    if shape in ("box", "wedge"):
        return max(sz) / 2 * sc
    if shape in ("cylinder",):
        return max(sz[0], sz[1] if len(sz) > 1 else sz[0], (sz[2] if len(sz) > 2 else 0.1) / 2) * sc
    if shape in ("cone", "pyramid", "capsule"):
        return max(sz[0], (sz[1] if len(sz) > 1 else sz[0]) / 2 + (sz[0] if shape == "capsule" else 0)) * sc
    if shape == "torus":
        return (sz[0] + (sz[1] if len(sz) > 1 else 0.02)) * sc
    return sz[0] * sc


def normalize_asset(d: dict, height: float | None = None) -> tuple[dict, list[str], list[str]]:
    """Check and repair a drawn prop. Returns (asset, fixes, errors)."""
    fixes, errs = [], []
    shapes, colors, motions = CATALOG["asset_shapes"], CATALOG["asset_colors"], CATALOG["asset_motions"]
    parts = []
    for i, pt in enumerate(d.get("parts") or []):
        if not isinstance(pt, dict) or pt.get("shape") not in shapes:
            fixes.append(f"dropped part {i + 1} (shape {pt.get('shape') if isinstance(pt, dict) else '?'!r})")
            continue
        n = SIZE_ARITY[pt["shape"]]
        size = [_f(v, 0.005, 2.0, 0.1) for v in (pt.get("size") or [0.1])[:n]]
        if pt["shape"] == "torus" and len(size) == 3:
            size[2] = _f(pt["size"][2], 0.3, 6.2832, 6.2832)
        size += [size[0]] * (n - len(size))
        q = {"shape": pt["shape"], "size": size,
             "pos": [_f(v, -2, 2, 0) for v in (pt.get("pos") or [0, 0, 0])[:3]] + [0] * max(0, 3 - len(pt.get("pos") or [])),
             "rot": [_f(v, -360, 360, 0) for v in (pt.get("rot") or [0, 0, 0])[:3]] + [0] * max(0, 3 - len(pt.get("rot") or [])),
             "color": pt.get("color") if pt.get("color") in colors else "accent"}
        if pt.get("color") not in colors:
            fixes.append(f"part {i + 1}: colour {pt.get('color')!r} -> accent (props use the palette's colours)")
        if pt.get("scale"):
            q["scale"] = [_f(v, 0.05, 5, 1) for v in pt["scale"][:3]] + [1] * max(0, 3 - len(pt["scale"]))
        mo = pt.get("motion")
        if isinstance(mo, dict):
            if mo.get("type") in motions:
                q["motion"] = {"type": mo["type"], "axis": mo.get("axis") if mo.get("axis") in ("x", "y", "z") else "z",
                               "amount": _f(mo.get("amount", 20), 0, 90, 20), "speed": _f(mo.get("speed", 0.8), 0.05, 4, 0.8)}
            else:
                fixes.append(f"part {i + 1}: motion {mo.get('type')!r} removed")
        if pt.get("name"):
            q["name"] = str(pt["name"])[:24]
        parts.append(q)
    if len(parts) > MAX_PARTS:
        fixes.append(f"kept {MAX_PARTS} of {len(parts)} parts"); parts = parts[:MAX_PARTS]
    if not parts:
        errs.append("the drawing has no usable parts")
        return {"name": d.get("name", "prop"), "parts": []}, fixes, errs
    # stand it on the floor, centred, at a sensible height
    lo = min(p["pos"][1] - _extent(p) for p in parts)
    hi = max(p["pos"][1] + _extent(p) for p in parts)
    cx = (min(p["pos"][0] - _extent(p) for p in parts) + max(p["pos"][0] + _extent(p) for p in parts)) / 2
    cz = (min(p["pos"][2] - _extent(p) for p in parts) + max(p["pos"][2] + _extent(p) for p in parts)) / 2
    want = _f(height if height is not None else d.get("height", 0.6), 0.15, 1.8, 0.6)
    k = want / max(1e-3, hi - lo)
    for p in parts:
        p["pos"] = [round((p["pos"][0] - cx) * k, 4), round((p["pos"][1] - lo) * k, 4), round((p["pos"][2] - cz) * k, 4)]
        p["size"] = [round(v * k, 4) if not (p["shape"] == "torus" and j == 2) else v for j, v in enumerate(p["size"])]
        if p.get("motion", {}).get("type") == "bob" and p["motion"]["amount"] <= 1:
            p["motion"]["amount"] = round(p["motion"]["amount"] * k, 4)
    if abs(k - 1) > 0.05:
        fixes.append(f"scaled to {want:.2f} m tall, standing on the floor")
    out = {"name": str(d.get("name", "prop"))[:40], "height": want, "parts": parts}
    if isinstance(d.get("grip"), list) and len(d["grip"]) == 3:
        out["grip"] = [round((_f(d["grip"][0], -2, 2, 0) - cx) * k, 4), round((_f(d["grip"][1], -2, 2, 0) - lo) * k, 4),
                       round((_f(d["grip"][2], -2, 2, 0) - cz) * k, 4)]
    if d.get("glow") or any(p["color"] == "glow" for p in parts):
        out["glow"] = True
    return out, fixes, errs


def find_asset(slug: str, key: str) -> dict | None:
    for f in (project_dir(slug) / "assets" / f"{key}.json", LIBRARY / f"{key}.json"):
        if f.exists():
            return json.loads(f.read_text(encoding="utf-8"))
    return None


def save_asset(slug: str, key: str, asset: dict, source: str, describe: str = "") -> Path:
    d = project_dir(slug) / "assets"
    d.mkdir(parents=True, exist_ok=True)
    f = d / f"{key}.json"
    f.write_text(json.dumps({**asset, "_source": source, "_describe": describe, "_at": time.time()}, indent=1), encoding="utf-8")
    return f


def to_library(slug: str, key: str) -> Path:
    a = find_asset(slug, key)
    if a is None:
        raise KeyError(key)
    LIBRARY.mkdir(parents=True, exist_ok=True)
    f = LIBRARY / f"{key}.json"
    f.write_text(json.dumps({**a, "_library": True}, indent=1), encoding="utf-8")
    return f


def list_assets(slug: str) -> list[dict]:
    out, seen = [], set()
    for src, d in (("project", project_dir(slug) / "assets"), ("library", LIBRARY)):
        for f in sorted(d.glob("*.json")) if d.exists() else []:
            if f.stem in seen:
                continue
            seen.add(f.stem)
            a = json.loads(f.read_text(encoding="utf-8"))
            png = f.with_suffix(".png")
            out.append({"key": f.stem, "name": a.get("name", f.stem), "where": src, "source": a.get("_source", "?"),
                        "describe": a.get("_describe", ""), "parts": len(a.get("parts", [])), "height": a.get("height"),
                        "preview": (f"assets/{png.name}" if src == "project" and png.exists() else None)})
    return out


def preview_scene(asset: dict, key: str, style: str = "minimal", theme: str = "dark") -> dict:
    """A small scene that shows just the prop, for its preview image."""
    h = asset.get("height", 0.6)
    return {"version": 2, "width": 320, "height": 320, "fps": 12, "duration": 2.0, "style": style, "theme": theme,
            "quality": "medium", "mood": "neutral", "assets": {key: asset}, "actors": [],
            "props": [{"type": f"custom:{key}", "pos": [0, 0, 0], "enter": "none", "idle": "none", "rot": [0, -0.5, 0]}],
            "camera": [{"t": 0, "pos": [0, h * 0.75 + 0.15, h * 2.4 + 0.6], "look": [0, h * 0.45, 0], "fov": 35}]}
