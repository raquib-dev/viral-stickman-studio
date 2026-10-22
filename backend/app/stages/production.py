"""Stages 7-9: render (GATE: cost, hard budget cap), stitch, package, learn."""
from __future__ import annotations

import asyncio
import hashlib
import json
import re
import time
from pathlib import Path

from .. import db
from .. import dialogue as dlg
from ..agent import tasks
from ..analysis import blueprint as bp
from ..analysis.profile import build_profile
from ..analysis.transcript import to_srt, words_from_json, words_json
from ..jobs import JobCancelled, StageError, bus, stage
from ..render import captions as cap
from ..render import stitch as st
from ..render.backends import get_backend
from ..render.base import ClipResult, ClipSpec, RenderError
from ..render.cost import PricingUnknown, clip_cost, estimate, within_budget
from ..render.media import dims, probe
from ..settings import LOCAL_BACKENDS, load_pricing
from ..tools import runner as tools
from .common import fmt_for_project, split_sentences, th


def _prompt_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:12]


def _clip_specs(ctx, p: dict) -> list[ClipSpec]:
    b = ctx.read_json("direction/phase-b.json")
    s = ctx.read_json("script/script.json")
    a = ctx.read_json("direction/phase-a.json")
    if b.get("checks"):
        raise StageError("Phase B has failing checks; re-run direction_b first")
    r = ctx.settings["render"]
    specs = []
    for k, pr in enumerate(b["prompts"]):
        specs.append(ClipSpec(index=k, prompt=pr["text"], ratio=p["ratio"], resolution=r["resolution"], duration=10.0,
                              continuity=r.get("continuity", "first_frame") if k else "none",
                              out_path=ctx.path(f"clips/clip-{k + 1:02d}.mp4"),
                              label=a["rows"][k]["purpose"] if k < len(a["rows"]) else "",
                              vo=s["clips"][k]["vo"] if k < len(s["clips"]) else "",
                              theme=p.get("theme", "dark"), voice_pref=p.get("voice_pref", "male"),
                              style=str(p.get("style", "1")), count=len(b["prompts"])))
    if dlg.is_dialogue(p):
        cast = dlg.cast_for(p)
        plan = dialogue_plan(ctx, s)
        for sp in specs:
            sp.lines = s["clips"][sp.index].get("lines") or [] if sp.index < len(s["clips"]) else []
            sp.cast = cast
            sp.plan = [plan[ln["i"]] for ln in sp.lines if ln["i"] < len(plan)]
            # a different look or voice is a different clip: the render step redoes clips whose prompt changed
            sp.prompt += "\nCAST " + json.dumps(cast, sort_keys=True)
    return specs


def dialogue_plan(ctx, script: dict) -> list[dict]:
    """The saved shot plan when it matches the script's lines, else a fresh one (it is deterministic and free)."""
    lines = script.get("lines") or [ln for c in script.get("clips", []) for ln in c.get("lines", [])]
    saved = ctx.read_json("scenes/dialogue.json", default={}) if ctx.path("scenes/dialogue.json").exists() else {}
    if saved.get("lines") == [{"speaker": ln["speaker"], "text": ln["text"]} for ln in lines] and saved.get("plan"):
        return saved["plan"]
    return dlg.plan_shots(lines)


def _fmt_eta(sec: float) -> str:
    return f"{sec / 60:.0f} min" if sec >= 90 else f"{sec:.0f} s"


class ClipTracker:
    """Live state of one clip in clips/clip-NN.json: status, attempt N of M, the step it is on, every
    attempt's error and timing. Each write is pushed to the UI as a 'clip' event."""

    def __init__(self, ctx, index: int, backend: str, max_attempts: int):
        self.ctx, self.index, self.rel = ctx, index, f"clips/clip-{index + 1:02d}.json"
        old = ctx.read_json(self.rel, default={}) if ctx.path(self.rel).exists() else {}
        # the last good render stays visible on the card while a regenerate runs (or if it fails)
        previous = old if old.get("status") == "done" else old.get("previous")
        self.m: dict = {"index": index, "backend": backend, "max_attempts": max_attempts, "attempt": 0, "history": [],
                        "job_id": ctx.job_id, "previous": previous}
        self._t0 = 0.0

    def _save(self, **f) -> None:
        self.m.update(f, updated_at=time.time())
        self.ctx.write_json(self.rel, self.m)
        bus.publish(self.ctx.project, {"type": "clip", "job_id": self.ctx.job_id, "clip": self.index + 1,
                                       "status": self.m.get("status"), "step": self.m.get("step")})

    def queued(self) -> None:
        self._save(status="queued", step="waiting for its turn", queued_at=time.time())

    def attempt_start(self, n: int) -> None:
        self._t0 = time.time()
        self._save(status="rendering" if n == 1 else "retrying", attempt=n, step="starting",
                   started_at=self.m.get("started_at") or self._t0, attempt_started_at=self._t0)

    def log(self, text: str, level: str = "info") -> None:
        self.ctx.log(text, level)
        self._save(step=str(text)[:200])

    def attempt_failed(self, error: str, retry_in: float | None, retryable: bool) -> None:
        self.m["history"].append({"attempt": self.m["attempt"], "ok": False, "error": error[:500], "retryable": retryable,
                                  "seconds": round(time.time() - self._t0, 1), "at": time.time()})
        self._save(step=f"attempt {self.m['attempt']} failed" + (f"; retrying in {retry_in:.0f} s" if retry_in else ""),
                   last_error=error[:500])

    def finish(self, status: str, error: str | None = None, **f) -> None:
        if status == "done":
            self.m["history"].append({"attempt": self.m["attempt"], "ok": True, "seconds": round(time.time() - self._t0, 1),
                                      "at": time.time()})
            self.m["previous"] = None
        self._save(status=status, step=status if not error else error[:200], error=error, attempts=self.m["attempt"],
                   finished_at=time.time(), render_seconds=round(time.time() - (self.m.get("started_at") or time.time()), 1), **f)


def render_spend(project: str) -> float:
    return sum(j["cost_usd"] for j in db.list_jobs(project, 1000) if j["stage"] == "render")


async def _draw_asset(ctx, name: str, describe: str, style: str, key: str) -> dict | None:
    """Have the writing model draw a prop, check it (one retry with the problems), cache it, render a preview."""
    from ..agent.runner import AgentError
    from ..render import assets as A
    from ..render import threejs as tj
    feedback = ""
    for attempt in (1, 2):
        try:
            res = await ctx.agent.run(tasks.draw_prop(name, describe, style, tj.CATALOG, feedback), ctx)
        except AgentError as e:
            ctx.log(f"prop “{name}”: drawing failed ({str(e)[:160]})", "warn")
            return None
        asset, fixes, errs = A.normalize_asset(res)
        if errs:
            feedback = "; ".join(errs)
            ctx.log(f"prop “{name}”: drawing rejected (attempt {attempt}): {feedback}", "warn")
            continue
        for f in fixes:
            ctx.log(f"prop “{name}”: repaired: {f}", "warn")
        A.save_asset(ctx.project, key, asset, "fixture (dry run)" if res.get("_fixture") else "ai", describe)
        try:
            await tj.render_still(A.preview_scene(asset, key, style), ctx.path(f"assets/{key}.png"))
        except Exception as e:  # a preview is nice to have, never required
            ctx.log(f"prop “{name}”: no preview image ({str(e)[:160]})", "warn")
        ctx.log(f"prop “{name}”: drawn by {'the dry-run fixture' if res.get('_fixture') else 'AI'}: "
                f"{len(asset['parts'])} parts, {asset['height']:.2f} m" + (f" · “{res.get('notes')}”" if res.get("notes") else ""))
        return asset
    return None


async def _resolve_assets(ctx, scene: dict, style: str) -> None:
    """Replace "new" props with drawn ones (cached per project or from the library) and embed their drawings."""
    from ..render import assets as A
    scene.setdefault("assets", {})
    kept = []
    for pr in scene.get("props", []):
        t = str(pr.get("type", ""))
        if t == "new" or (t.startswith("custom:") and t[7:] not in scene["assets"]):
            name = pr.get("asset") or t[7:]
            key = A.asset_key(name)
            a = A.find_asset(ctx.project, key)
            if a:
                ctx.log(f"prop “{name}”: reusing the drawing in {'the project' if ctx.path(f'assets/{key}.json').exists() else 'your library'}")
            else:
                a = await _draw_asset(ctx, name, pr.get("describe", ""), style, key)
            if not a:
                ctx.log(f"prop “{name}”: left out of the scene", "warn")
                continue
            scene["assets"][key] = {k: v for k, v in a.items() if not k.startswith("_")}
            pr = {**{k: v for k, v in pr.items() if k not in ("asset", "describe")}, "type": f"custom:{key}"}
        kept.append(pr)
    scene["props"] = kept
    if not scene["assets"]:
        scene.pop("assets")


@stage("draw_prop", "Draw a prop",
       description="Redraw one AI-drawn prop and update every clip that uses it (Render page → props).")
async def draw_prop(ctx) -> dict:
    from ..render import assets as A
    p = ctx.project_data()
    key = A.asset_key(ctx.params.get("key") or ctx.params.get("name", ""))
    old = A.find_asset(ctx.project, key) or {}
    name = ctx.params.get("name") or old.get("name") or key
    describe = ctx.params.get("describe") or old.get("_describe", "")
    style = CATALOG_STYLE(p, ctx.settings)
    a = await _draw_asset(ctx, name, describe, style, key)
    if not a:
        raise StageError(f"could not draw “{name}”")
    updated = []
    for f in sorted(ctx.path("scenes").glob("clip-*.json")) if ctx.path("scenes").exists() else []:
        sc = json.loads(f.read_text(encoding="utf-8"))
        if key in (sc.get("assets") or {}):
            sc["assets"][key] = {k: v for k, v in a.items() if not k.startswith("_")}
            f.write_text(json.dumps(sc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            updated.append(f.name)
    ctx.log(f"updated {len(updated)} scene(s): {', '.join(updated) or 'none'} (regenerate those clips to see it)")
    return {"outputs": [f"assets/{key}.json", f"assets/{key}.png"]}


def CATALOG_STYLE(p: dict, settings: dict) -> str:
    from ..render import threejs as tj
    forced = settings["render"].get("threejs", {}).get("style", "auto")
    return tj.CATALOG["skill_styles"].get(forced, forced) if forced and forced != "auto" else tj.CATALOG["skill_styles"].get(str(p.get("style", "1")), "minimal")


async def _dialogue_scene_plan(ctx) -> dict:
    """Dialogue shorts: one shot per line (the speaker's close-up, or a wide two-shot), faces and gestures from the
    words. Deterministic, so it needs no writing-model call; timing is fixed at render, from the real voices."""
    s = ctx.read_json("script/script.json")
    lines = s.get("lines") or [ln for c in s["clips"] for ln in c.get("lines", [])]
    if not lines:
        raise StageError("the script has no dialogue lines; re-run Script")
    plan = dlg.plan_shots(lines)
    cast = dlg.cast_for(ctx.project_data())
    ctx.write_json("scenes/dialogue.json", {"lines": [{"speaker": ln["speaker"], "text": ln["text"]} for ln in lines],
                                            "plan": plan, "cast": {k: cast[k]["name"] for k in dlg.SPEAKERS}})
    index = {}
    for c in s["clips"]:
        ps = [plan[ln["i"]] for ln in c.get("lines", [])]
        index[str(c["index"] + 1)] = {
            "planned_by": "dialogue", "style": "night", "moods": ["neutral"], "actors": 2, "panels": 0, "badges": [], "props": [],
            "gestures": sorted({p["gesture"] for p in ps if p.get("gesture")}),
            "shots": [("wide" if p["shot"] == "wide" else f"close-up {cast[p['shot']]['name']}") for p in ps],
            "notes": " / ".join(f"{cast[ln['speaker']]['name']}: {ln['text']}" for ln in c.get("lines", [])),
            "fixes": [], "file": "scenes/dialogue.json", "updated_at": time.time()}
        ctx.log(f"clip {c['index'] + 1}: " + ", ".join(index[str(c['index'] + 1)]["shots"]))
    ctx.write_json("scenes/index.json", index)
    wides = sum(1 for p in plan if p["shot"] == "wide")
    ctx.log(f"dialogue plan: {len(plan)} lines, {wides} wide shot(s), {len(plan) - wides} close-ups, all hard cuts")
    return {"outputs": ["scenes/dialogue.json", "scenes/index.json"]}


@stage("scene_plan", "Plan 3D scenes",
       description="AI scene plan per clip for the three.js renderer: checked, repaired, keyword plan as fallback.")
async def scene_plan(ctx) -> dict:
    from ..agent.runner import AgentError
    from ..render import threejs as tj
    if dlg.is_dialogue(ctx.project_data()):
        return await _dialogue_scene_plan(ctx)
    if ctx.settings["render"]["backend"] != "local-threejs":
        ctx.log(f"render backend is {ctx.settings['render']['backend']}: 3D scene plans are only used by local-threejs; skipping")
        return {"outputs": []}
    p = ctx.project_data()
    a = ctx.read_json("direction/phase-a.json")
    specs = _clip_specs(ctx, p)
    cfg = ctx.settings["render"].get("threejs", {})
    wpm = float(ctx.settings.get("speaking_wpm", 150))
    only = set(ctx.params.get("only") or [])
    force = bool(ctx.params.get("force")) or bool(only)
    index = ctx.read_json("scenes/index.json", default={}) if ctx.path("scenes/index.json").exists() else {}
    planned = 0
    for n, sp in enumerate(specs):
        if only and sp.index + 1 not in only:
            continue
        ctx.check_cancelled()
        rel = f"scenes/clip-{sp.index + 1:02d}.json"
        old = ctx.read_json(rel, default={}) if ctx.path(rel).exists() else {}
        key = _prompt_hash(f"{sp.vo}|{sp.prompt}|{tj.style_for(sp, cfg)}|{cfg.get('mood', 'auto')}|{sp.ratio}")
        if old and (("_planned_by" not in old) or old.get("_planned_by") == "editor") and not ctx.params.get("overwrite_edits"):
            ctx.log(f"clip {sp.index + 1}: keeping your edited {rel}")
            continue
        if old.get("_key") == key and not force:
            ctx.log(f"clip {sp.index + 1}: plan is up to date")
            continue
        words = len((sp.vo or "").split())
        talk = (0.4, round(min(sp.duration - 0.3, 0.4 + words / (wpm / 60)), 2))
        draft = tj.auto_scene(sp, cfg, talk)
        row = a["rows"][sp.index] if sp.index < len(a.get("rows", [])) else {}
        w, h = dims(sp.ratio, sp.resolution)
        scene, fixes, errs, by, notes, feedback = draft, [], [], "keywords", "", ""
        from ..render import assets as A
        known = A.list_assets(ctx.project)
        for attempt in (1, 2):
            try:
                res = await ctx.agent.run(tasks.scene_plan(sp.index + 1, len(specs), row, sp.vo, draft["style"], draft["theme"],
                                                           sp.ratio, sp.duration, list(talk), tj.CATALOG, draft, feedback,
                                                           [{"key": k["key"], "name": k["name"]} for k in known]), ctx)
            except AgentError as e:
                ctx.log(f"clip {sp.index + 1}: AI plan failed ({str(e)[:200]}); using the keyword plan", "warn")
                break
            body = {k: v for k, v in res.items() if k not in ("notes", "_fixture")}
            # frame size, fps, length and seed are the app's, never the model's (it may echo them back, even as strings)
            tech = ("version", "width", "height", "fps", "duration", "seed", "quality")
            candidate = {**{k: draft[k] for k in ("style", "theme")}, **body, **{k: draft[k] for k in tech}}
            candidate.setdefault("transition", draft["transition"])
            try:
                fixed, fx, er = tj.check_and_repair(candidate, sp.vo, sp.duration, h > w, {k["key"] for k in known})
            except Exception as e:                                  # a shape the repairer does not know: retry, then keywords
                fixed, fx, er = candidate, [], [f"the plan has a malformed field ({type(e).__name__}: {str(e)[:120]}); "
                                                "follow the JSON schema types exactly"]
            want = tj.seam_transition(sp.index, len(specs), fixed.get("transition"))
            if want != fixed.get("transition"):
                fx.append(f"transition {fixed.get('transition')} -> {want} (no fade to black between clips)")
                fixed["transition"] = want
            if not er:
                scene, fixes, by, notes = fixed, fx, "fixture (dry run)" if res.get("_fixture") else "ai", res.get("notes", "")
                break
            feedback = "; ".join(er[:6])
            ctx.log(f"clip {sp.index + 1}: AI plan rejected (attempt {attempt}): {feedback}", "warn")
            errs = er
        if by == "keywords" and errs:
            ctx.log(f"clip {sp.index + 1}: using the keyword plan after {len(errs)} problem(s) in the AI plan", "warn")
        for f in fixes:
            ctx.log(f"clip {sp.index + 1}: repaired: {f}", "warn")
        await _resolve_assets(ctx, scene, scene.get("style", draft["style"]))
        scene.update({"_planned_by": by, "_key": key, "_notes": notes, "_fixes": fixes})
        ctx.write_json(rel, scene)
        hero = scene["actors"][0]
        moods = scene["mood"] if isinstance(scene["mood"], list) else [{"mood": scene["mood"]}]
        index[str(sp.index + 1)] = {
            "planned_by": by, "notes": notes, "fixes": fixes, "style": scene.get("style"),
            "moods": [m["mood"] for m in moods], "gestures": [g["gesture"] for g in hero.get("gestures", [])],
            "props": [(scene.get("assets", {}).get(pr["type"][7:], {}).get("name", pr["type"][7:]) + " ✦") if pr["type"].startswith("custom:") else pr["type"]
                      for pr in scene.get("props", [])], "actors": len(scene["actors"]),
            "shots": [(k["shot"] if isinstance(k.get("shot"), str) else (k.get("shot") or {}).get("type", "custom")) for k in scene["camera"]],
            "panels": len(scene.get("panels") or []), "badges": [b_["text"] for b_ in scene.get("badges") or []],
            "updated_at": time.time(), "file": rel}
        ctx.write_json("scenes/index.json", index)
        planned += 1
        ctx.log(f"clip {sp.index + 1}: planned by {by} · {scene.get('style')} · mood {' → '.join(index[str(sp.index + 1)]['moods'])} · "
                f"gestures {', '.join(index[str(sp.index + 1)]['gestures']) or '-'} · props {', '.join(index[str(sp.index + 1)]['props']) or '-'}"
                + (f" · “{notes[:120]}”" if notes else ""))
        ctx.progress((n + 1) / len(specs), f"clip {sp.index + 1} planned ({by})")
    ctx.log(f"{planned} scene plan(s) written; the render uses scenes/clip-NN.json")
    return {"outputs": ["scenes/"]}


@stage("render", "Render clips", lane="render",
       description="One clip at a time with retries; cost gate before any paid clip; hard per-video budget cap.")
async def render(ctx) -> dict:
    p = ctx.project_data()
    r = ctx.settings["render"]
    backend_name = r["backend"] if not ctx.dry_run else "mock"
    if ctx.dry_run and r["backend"] != "mock":
        ctx.log(f"dry run is on: using the mock backend instead of {r['backend']}", "warn")
    specs = _clip_specs(ctx, p)
    if dlg.is_dialogue(p) and backend_name not in ("local-threejs", "mock"):
        raise StageError(f"dialogue shorts render with the three.js renderer (two characters, a cut per line); "
                         f"Settings → Render → Backend is {backend_name}. Choose local-threejs.")
    if not ctx.dry_run:
        from .studio import placeholders, rewrite_gaps
        gaps = placeholders([{"index": sp.index, "vo": sp.vo} for sp in specs])
        if gaps and ctx.settings.get("script_gaps", "ask") == "rewrite":
            ctx.log("the script has gaps; rewriting those lines without a figure (Settings → Script gaps)")
            ctx.write_json("script/script.json", await rewrite_gaps(ctx, ctx.read_json("script/script.json")))
            specs = _clip_specs(ctx, p)
            gaps = placeholders([{"index": sp.index, "vo": sp.vo} for sp in specs])
        if gaps:
            raise StageError("the script still has gaps for you to fill: " + ", ".join(
                f"{{{{{g['name']}}}}} (clip {', '.join(map(str, g['clips']))})" for g in gaps)
                + ". Type your value in the box at the top of the Render page (or Studio → Script), or press "
                "Rewrite without the number. Settings → Script gaps → rewrite automatically skips this stop.")
    only = set(ctx.params.get("only") or [])
    force = bool(ctx.params.get("force"))
    todo = []
    for sp in specs:
        meta_p = ctx.path(f"clips/clip-{sp.index + 1:02d}.json")
        meta = json.loads(meta_p.read_text()) if meta_p.exists() else {}
        done = (sp.out_path.exists() and meta.get("status") == "done" and meta.get("prompt_hash") == _prompt_hash(sp.prompt)
                and meta.get("backend") == backend_name)
        if only:
            if (sp.index + 1) in only:
                todo.append(sp)
        elif force or not done:
            todo.append(sp)
    if not todo:
        ctx.log("all clips already rendered for the current prompts (use 'regenerate' to redo one)")
        return {"outputs": ["clips/"]}
    pricing = load_pricing()
    try:
        est = estimate(pricing, backend_name, r["resolution"], len(todo), 10.0)
    except PricingUnknown as e:
        raise StageError(str(e)) from e
    cap_usd = float(r["budget_cap_usd"])
    spent = render_spend(ctx.project)
    ctx.write_json("clips/estimate.json", {**est.as_dict(), "budget_cap_usd": cap_usd, "already_spent_usd": round(spent, 4),
                                           "clips": [sp.index + 1 for sp in todo]})
    if est.base_usd > 0:
        within = spent + est.max_usd <= cap_usd
        ctx.require_gate("render_cost", {"estimate": est.as_dict(), "clips": [sp.index + 1 for sp in todo],
                                         "prompts": [_prompt_hash(sp.prompt) for sp in todo], "cap": cap_usd},
                         options=None, default_choice="approved", auto_allowed=within,
                         auto_reason=(f"estimate ${est.max_usd:.2f} (incl. retry allowance) within cap ${cap_usd:.2f}"
                                      if within else f"estimate ${est.max_usd:.2f} + spent ${spent:.2f} exceeds cap ${cap_usd:.2f}"))
    else:
        ctx.log(f"{backend_name}: $0 ({'runs on this machine' if backend_name in LOCAL_BACKENDS else 'placeholder clips'}), "
                "no cost gate needed")
    try:
        backend = get_backend(backend_name)
    except RenderError as e:
        raise StageError(str(e)) from e
    if backend_name == "local-comfyui" and ctx.settings["agent"]["provider"] in ("local", "hybrid"):
        from ..agent.local import unload
        await unload(ctx.settings, ctx.log)
    prev: ClipResult | None = None
    if todo[0].index > 0:
        prev_png = ctx.path(f"clips/clip-{todo[0].index:02d}.last.png")
        prev_meta = ctx.path(f"clips/clip-{todo[0].index:02d}.json")
        if prev_png.exists():
            pm = json.loads(prev_meta.read_text()) if prev_meta.exists() else {}
            prev = ClipResult(todo[0].index - 1, ctx.path(f"clips/clip-{todo[0].index:02d}.mp4"), 10.0, 0.0, backend_name,
                              interaction_id=pm.get("interaction_id"), last_frame=prev_png)
    max_retries = int(r.get("max_retries", 2))
    trackers = {sp.index: ClipTracker(ctx, sp.index, backend_name, max_retries + 1) for sp in todo}
    for t in trackers.values():
        t.queued()
    t_job = time.time()
    for n, sp in enumerate(todo):
        ctx.check_cancelled()
        tr = trackers[sp.index]
        nxt = clip_cost(pricing, backend_name, sp.resolution, sp.duration)
        spent = render_spend(ctx.project)
        if not within_budget(spent, nxt, cap_usd):
            ctx.log(f"budget cap reached: spent ${spent:.2f}, next clip ${nxt:.2f}, cap ${cap_usd:.2f}. Stopping.", "error")
            tr.finish("failed", error="budget cap reached")
            raise StageError("budget cap reached; raise it in Settings or regenerate fewer clips")
        ctx.progress(n / len(todo), f"clip {sp.index + 1} rendering ({n + 1}/{len(todo)})")
        attempt, delay = 0, 5.0
        while True:
            attempt += 1
            tr.attempt_start(attempt)
            try:
                res = await backend.render_clip(sp, prev if sp.continuity != "none" else None, tr.log)
                info = probe(res.path)  # a truncated download fails here and is retried like any render error
                break
            except (asyncio.CancelledError, JobCancelled):
                tr.finish("cancelled", error="cancelled by you")
                raise
            except Exception as e:
                # download/ffmpeg/network errors used to escape the retry loop and leave the clip stuck on "rendering"
                err = e if isinstance(e, RenderError) else RenderError(f"{type(e).__name__}: {e}")
                ctx.log(f"clip {sp.index + 1} attempt {attempt} failed: {err}", "warn")
                will_retry = err.retryable and attempt <= max_retries
                tr.attempt_failed(str(err), retry_in=delay if will_retry else None, retryable=err.retryable)
                if not will_retry:
                    tr.finish("failed", error=str(err))
                    why = "" if err.retryable else " (not retried: retrying would fail the same way)"
                    raise StageError(f"clip {sp.index + 1} failed after {attempt} attempt(s): {err}{why}") from e
                try:
                    ctx.check_cancelled()
                except JobCancelled:
                    tr.finish("cancelled", error="cancelled by you")
                    raise
                await asyncio.sleep(delay)
                delay *= 2
        ctx.add_cost(res.cost_usd, f"clip {sp.index + 1}")
        ratio_ok = not st.wrong_orientation(info, sp.ratio)
        if not ratio_ok:
            ctx.log(f"clip {sp.index + 1} came back {info['width']}x{info['height']}, not {sp.ratio}; stitch will crop it "
                    "to fill the frame, or regenerate it", "warn")
        tr.finish("done", cost_usd=res.cost_usd, interaction_id=res.interaction_id, prompt_hash=_prompt_hash(sp.prompt),
                  duration=info["duration"], width=info["width"], height=info["height"], has_audio=info["has_audio"],
                  ratio_ok=ratio_ok, continuity=sp.continuity, meta=res.meta)
        prev = res
        avg = (time.time() - t_job) / (n + 1)
        left = len(todo) - n - 1
        ctx.progress((n + 1) / len(todo), f"clip {sp.index + 1} done ({n + 1}/{len(todo)})"
                     + (f", ~{_fmt_eta(avg * left)} left" if left else ""))
    return {"outputs": ["clips/"]}


async def _final_qa(ctx, n: int, starts: list[float], events: list) -> dict:
    """Quality report on the exported file (frames, A/V length, unexpected black dips, caption overlaps)."""
    qa = await th(st.final_qa, ctx.path("final/final.mp4"), 24.0, starts, events)
    clip_qa = {k: ctx.read_json(f"clips/clip-{k:02d}.json", default={}).get("meta", {}).get("qa") for k in range(1, n + 1)}
    qa["clips"] = {k: v for k, v in clip_qa.items() if v}
    ctx.write_json("final/qa.json", qa)
    for prob in qa["problems"]:
        ctx.log("QA: " + prob, "warn")
    if not qa["problems"]:
        ctx.log(f"QA: {qa['frames']} frames, audio and video both {qa['video_seconds']:.2f}s, no unexpected black frames, "
                "no caption overlaps")
    return qa


async def _stitch_dialogue(ctx, p: dict, s: dict, n: int, stitched, starts: list[float], lengths: list[float], w: int, h: int) -> dict:
    """Dialogue shorts: line captions at the top from the render's own timing (no transcription needed), a quiet
    room-tone bed under the voices (ducked while anyone speaks), loudness, the quality report."""
    from ..analysis.transcript import Word
    metas = [ctx.read_json(f"clips/clip-{k:02d}.json", default={}) for k in range(1, n + 1)]
    lines = dlg.caption_lines(metas, dlg.script_lines(s), starts, lengths)
    timed = any((m.get("meta") or {}).get("lines") for m in metas)
    method = "dialogue lines (timing from the render)" if timed else "dialogue lines (estimated)"
    words = [Word(x["text"], x["start"], x["end"]) for x in lines]
    ctx.write_json("final/words.json", {"method": method, "words": words_json(words),
                                        "lines": [{k: x[k] for k in ("i", "speaker", "text", "start", "end")} for x in lines]})
    ctx.write_text("final/final.srt", to_srt(words, words_per_cue=1))
    ass, violations = cap.build_line_ass(lines, p["ratio"], w, h, captions=bool(ctx.settings["captions"].get("enabled", True)))
    for v in violations:
        ctx.log("safe zone: " + v, "warn")
    ass_path = ctx.write_text("final/captions.ass", ass)
    captioned = ctx.path("final/captioned.mp4")
    await th(st.burn_ass, stitched, ass_path, captioned)
    ctx.progress(0.6, "line captions burned in")
    dcfg = ctx.settings.get("dialogue", {})
    bed = str(dcfg.get("bed", "room"))
    mixed = captioned
    if bed != "none":
        mixed = ctx.path("final/bedded.mp4")
        try:
            await th(st.add_bed, captioned, mixed, bed, float(dcfg.get("bed_db", -30)))
            ctx.log(f"sound bed: {'room tone' if bed == 'room' else Path(bed).name} at {dcfg.get('bed_db', -30)} dB, dips under the voices")
        except Exception as e:
            mixed = captioned
            ctx.log(f"sound bed skipped ({type(e).__name__}: {str(e)[:160]})", "warn")
    ctx.progress(0.7, "sound bed")
    loud = ctx.settings["loudness"]
    report = await th(st.loudnorm, mixed, ctx.path("final/final.mp4"), loud["integrated_lufs"], loud["true_peak_db"])
    info = probe(ctx.path("final/final.mp4"))
    from ..render.media import run_ffmpeg
    await th(run_ffmpeg, ["-ss", "1.2", "-i", str(ctx.path("final/final.mp4")), "-frames:v", "1", str(ctx.path("final/poster.png"))])
    ctx.write_json("final/loudness.json", {**report, **info, "caption_timing": method, "safe_zone_violations": violations})
    ctx.progress(0.9, "quality checks")
    await _final_qa(ctx, n, starts, [(x["start"], x["end"], k, 0) for k, x in enumerate(lines)])
    loud_txt = (f"{report['after_i']:.1f} LUFS (target {report['target_i']})" if report.get("after_i") is not None
                else "audio is silent, loudness not normalised")
    ctx.log(f"final.mp4: {info['duration']:.1f}s {info['width']}x{info['height']}, {loud_txt}, {len(lines)} dialogue lines, "
            f"captions: {method}")
    return {"outputs": ["final/final.mp4", "final/poster.png", "final/final.srt", "final/captions.ass", "final/words.json",
                        "final/loudness.json", "final/qa.json"]}


@stage("stitch", "Stitch, captions, loudness", description="ffmpeg concat, word-timed captions, hook card, -16 LUFS.")
async def stitch_stage(ctx) -> dict:
    p = ctx.project_data()
    s = ctx.read_json("script/script.json")
    a = ctx.read_json("direction/phase-a.json")
    n = int(p["duration"]) // 10
    clips = [ctx.path(f"clips/clip-{k:02d}.mp4") for k in range(1, n + 1)]
    missing = [c.name for c in clips if not c.exists()]
    if missing:
        raise StageError(f"missing clips: {', '.join(missing)} (run render)")
    res_name = ctx.settings["render"]["resolution"]
    w, h = dims(p["ratio"], res_name if res_name in ("360p", "720p", "1080p") else "1080p")
    stitched = ctx.path("final/stitched.mp4")
    wrong = [c.name for c in clips if st.wrong_orientation(probe(c), p["ratio"])]
    if wrong:
        ctx.log(f"{', '.join(wrong)} not {p['ratio']}: cropped from the centre to fill the frame "
                "(regenerate them for a proper framing)", "warn")
    await th(st.concat, clips, stitched, p["ratio"], res_name if res_name != "4k" else "1080p")
    ctx.progress(0.35, "concatenated")
    lengths = [(i := probe(c))["video_duration"] or i["duration"] for c in clips]
    starts = [sum(lengths[:k]) for k in range(len(lengths))]
    backend_used = ctx.read_json("clips/clip-01.json", default={}).get("backend", "mock")
    words, method = None, "estimate"
    dialogue_mode = s.get("mode") == "dialogue"
    if dialogue_mode:
        return await _stitch_dialogue(ctx, p, s, n, stitched, starts, lengths, w, h)
    if backend_used != "mock":
        cs = ctx.settings["captions"]
        if cs.get("engine") == "groq":
            words = await th(cap.groq_words, stitched, ctx.log, cs.get("groq_model", "whisper-large-v3-turbo"))
            method = "Groq Whisper" if words else method
        if not words:
            words = await th(cap.whisper_words, stitched, ctx.log, cs.get("whisper_model", "base.en"), cs.get("whisper_device", "auto"))
            method = "faster-whisper" if words else "estimate (no word timing available)"
    if not words:
        # the local backends record where the voice really is in each clip; use it so captions follow the audio
        windows = [ctx.read_json(f"clips/clip-{k:02d}.json", default={}).get("meta", {}).get("speech_window") for k in range(1, n + 1)]
        words = cap.estimate_words([c["vo"] for c in s["clips"]], durations=lengths, windows=windows)
        if any(windows):
            method = "estimate from each clip's voice timing"
    ctx.write_json("final/words.json", {"method": method, "words": words_json(words)})
    ctx.write_text("final/final.srt", to_srt(words))
    # the on-screen card you approved at the hook gate wins over the director's suggestion
    hook_card = s["hook"].get("write") or a.get("hook_card")
    callouts = [{"t": starts[min(o["clip"], n) - 1] + 3.0, "text": o["text"], "hold": 2.2} for o in a.get("overlays", [])
                if o.get("clip", 1) != 1 and o.get("text")]
    ass, violations = cap.build_ass(words, p["ratio"], w, h, hook_card=hook_card, callouts=callouts,
                                    words_per_page=int(ctx.settings["captions"].get("words_per_page", 3)),
                                    captions=bool(ctx.settings["captions"].get("enabled", True)))
    for v in violations:
        ctx.log("safe zone: " + v, "warn")
    ass_path = ctx.write_text("final/captions.ass", ass)
    captioned = ctx.path("final/captioned.mp4")
    await th(st.burn_ass, stitched, ass_path, captioned)
    ctx.progress(0.7, "captions burned in")
    loud = ctx.settings["loudness"]
    report = await th(st.loudnorm, captioned, ctx.path("final/final.mp4"), loud["integrated_lufs"], loud["true_peak_db"])
    info = probe(ctx.path("final/final.mp4"))
    from ..render.media import run_ffmpeg
    await th(run_ffmpeg, ["-ss", "1.2", "-i", str(ctx.path("final/final.mp4")), "-frames:v", "1", str(ctx.path("final/poster.png"))])
    ctx.write_json("final/loudness.json", {**report, **info, "caption_timing": method, "safe_zone_violations": violations})
    # quality report on the exported file (frames, A/V length, unexpected black dips, caption overlaps)
    ctx.progress(0.9, "quality checks")
    events = cap.page_events(cap.phrase_pages(cap.dedupe_words(words), int(ctx.settings["captions"].get("words_per_page", 3))))
    await _final_qa(ctx, n, starts, events)
    loud_txt = (f"{report['after_i']:.1f} LUFS (target {report['target_i']})" if report.get("after_i") is not None
                else "audio is silent, loudness not normalised")
    if report.get("skipped"):
        ctx.log("loudness: " + report["skipped"] + " (the clips have no sound; check the render prompts' audio lines)", "warn")
    ctx.log(f"final.mp4: {info['duration']:.1f}s {info['width']}x{info['height']}, {loud_txt}, captions timed by {method}")
    return {"outputs": ["final/final.mp4", "final/poster.png", "final/final.srt", "final/captions.ass", "final/words.json", "final/loudness.json", "final/qa.json"]}


POLICY_NOTES = [
    "YouTube inauthentic-content policy (15 Jul 2025): mass-produced or repetitive AI content with generic templates is not "
    "monetizable; vary music and imagery across videos and make sure the insight is yours. "
    "https://support.google.com/youtube/answer/1311392",
    "Do not present the narrator as a human financial/health/legal expert; YouTube will not monetize AI personas presented that way.",
    "Nothing has been posted. Publish manually.",
]


@stage("package", "Package", description="Titles + thumbnail pairing lint, SEO, chapters, IG caption, humanizer, cut-downs.",
       skills=["yt-package", "yt-seo", "yt-chapters", "ig-caption", "ig-human", "yt-shorts", "ig-repurpose"],
       tools=["yt-package/title.py", "yt-chapters/chapters.py", "ig-caption/caption.py", "ig-human/humanize.py", "ig-human/detect.py"])
async def package(ctx) -> dict:
    p = ctx.project_data()
    s = ctx.read_json("script/script.json")
    fmt = fmt_for_project(p)
    srt_path = ctx.path("final/final.srt")
    srt = srt_path.read_text(encoding="utf-8") if srt_path.exists() else ""
    chapters = {"valid": False, "chapters": [], "note": "not applicable to Shorts/Reels"}
    if fmt == "long" and srt:
        chapters = await th(tools.chapters, srt, max(3, int(p["duration"]) // 60))
    narration = "\n".join(c["vo"] for c in s["clips"])
    pk = await ctx.agent.run(tasks.package(s["title"], narration, s["topic"], s["hook"], int(p["duration"]),
                                           p.get("platforms", []), chapters.get("chapters", [])), ctx)
    # title x thumbnail pairing: lint every title against each thumbnail text, keep the best pair
    pairs = []
    for thumb in pk["thumbnail_text"]:
        for row in await th(tools.title_lint, pk["titles"], thumb):
            pairs.append({**row, "thumb": thumb})
    pairs.sort(key=lambda r: -r["score"])
    # humanize the long text blocks
    desc_h = await th(tools.humanize, pk["description"])
    cap_h = await th(tools.humanize, pk["ig_caption"])
    desc_d = await th(tools.detect, desc_h["text"])
    cap_d = await th(tools.detect, cap_h["text"])
    cap_lint = await th(tools.caption_lint, cap_h["text"], pk.get("ig_keywords") or [])
    ch_lines = []
    if chapters.get("valid"):
        titles = pk.get("chapter_titles") or []
        for k, c in enumerate(chapters["chapters"]):
            ch_lines.append(f"{c['label']} {titles[k] if k < len(titles) else c['draft_title']}")
    result = {"titles": pairs[:10], "best": pairs[0] if pairs else None, "thumbnail_brief": pk["thumbnail_brief"],
              "description": desc_h["text"], "description_detect": desc_d, "tags": pk["tags"], "queries": pk["queries"],
              "chapters": chapters, "chapter_lines": ch_lines, "ig_caption": cap_h["text"], "ig_caption_lint": cap_lint,
              "ig_caption_detect": cap_d, "cutdowns": pk["cutdowns"], "policy_notes": POLICY_NOTES,
              "claims_to_source": s.get("claims_to_source", []), "_fixture": pk.get("_fixture", False)}
    ctx.write_json("package/package.json", result)
    best = result["best"] or {}
    blocks = ["# Copy blocks (nothing has been posted; paste these yourself)", "",
              "## YouTube title", "```", best.get("title", ""), "```", "## Thumbnail text", "```", best.get("thumb", ""), "```",
              "## Thumbnail brief", pk["thumbnail_brief"], "", "## Description", "```", desc_h["text"].strip(),
              *(["", *ch_lines] if ch_lines else []), "```", "## Tags", "```", ", ".join(pk["tags"]), "```",
              "## Instagram caption", "```", cap_h["text"].strip(), "```", "## Claims to verify before publishing",
              *[f"- {c}" for c in result["claims_to_source"]], "", "## Policy notes", *[f"- {n}" for n in POLICY_NOTES]]
    ctx.write_text("package/copy-blocks.md", "\n".join(blocks) + "\n")
    ctx.log(f"best pairing: '{best.get('title')}' + thumbnail '{best.get('thumb')}' (score {best.get('score')}); "
            f"caption lint {cap_lint['verdict']}; description human score {desc_d.get('human_score')}")
    return {"outputs": ["package/package.json", "package/copy-blocks.md"]}


@stage("learn", "Learn loop", description="Retention CSV + IG insights -> findings -> niche profile updates.",
       skills=["yt-retention", "ig-audit"], tools=["yt-retention/retention.py"])
async def learn(ctx) -> dict:
    p = ctx.project_data()
    csv = ctx.path("research/learn/retention.csv")
    ig_txt_p = ctx.path("research/learn/ig-insights.txt")
    ig_txt = ig_txt_p.read_text(encoding="utf-8") if ig_txt_p.exists() else ""
    if not csv.exists() and not ig_txt:
        raise StageError("upload your YouTube Studio retention CSV or paste Instagram insights first")
    duration = float(p["duration"])
    retention = None
    if csv.exists():
        srt = ctx.path("final/final.srt")
        retention = await th(tools.retention, csv, srt if srt.exists() else None, duration)
        ctx.log(f"hook leak {retention['hook_leak']}%, {len(retention['cliffs'])} cliff(s)")
    s = ctx.read_json("script/script.json")
    read = await ctx.agent.run(tasks.learn_read(retention, ig_txt, s.get("plan", []), duration), ctx)
    learned_path = "research/learned.json"
    learned = ctx.read_json(learned_path, default=[]) if ctx.path(learned_path).exists() else []
    for adj in read["adjustments"]:
        learned.append({**adj, "from_video": s["title"]})
    ctx.write_json(learned_path, learned)
    videos = [json.loads(f.read_text(encoding="utf-8")) for f in sorted(ctx.path("research/patterns").glob("*.json"))]
    profile = build_profile(videos, learned)
    profile["format"] = fmt_for_project(p)
    ctx.write_json("research/niche-profile.json", profile)
    ctx.write_json("research/learn/report.json", {"retention": retention, "read": read, "learned_total": len(learned)})
    ctx.log(f"{len(read['adjustments'])} profile adjustment(s); next video's beat placement will use them")
    return {"outputs": ["research/learn/report.json", "research/learned.json", "research/niche-profile.json"]}


class FileCtx:
    """Just enough of a job context to build clip specs outside a job (scene editor endpoints)."""
    def __init__(self, project: str):
        from .. import paths
        from ..settings import load_settings
        self.project, self.settings = project, load_settings()
        self._paths = paths

    def path(self, rel: str) -> Path:
        return self._paths.safe_project_path(self.project, rel)

    def read_json(self, rel: str, default=None):
        f = self.path(rel)
        if not f.exists():
            if default is not None:
                return default
            raise StageError(f"missing input {rel}: run the earlier stage first")
        return json.loads(f.read_text(encoding="utf-8"))

    def project_data(self) -> dict:
        return db.get_project(self.project)["data"]


def clip_spec_for(project: str, n: int) -> tuple[ClipSpec, tuple[float, float], FileCtx]:
    ctx = FileCtx(project)
    specs = _clip_specs(ctx, ctx.project_data())
    if not 1 <= n <= len(specs):
        raise StageError(f"clip {n} does not exist (this video has {len(specs)} clips)")
    sp = specs[n - 1]
    wpm = float(ctx.settings.get("speaking_wpm", 150))
    talk = (0.4, round(min(sp.duration - 0.3, 0.4 + len((sp.vo or "").split()) / (wpm / 60)), 2))
    return sp, talk, ctx
