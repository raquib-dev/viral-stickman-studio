"""Stages 7-9: render (GATE: cost, hard budget cap), stitch, package, learn."""
from __future__ import annotations

import asyncio
import hashlib
import json
import re
from pathlib import Path

from .. import db
from ..agent import tasks
from ..analysis import blueprint as bp
from ..analysis.profile import build_profile
from ..analysis.transcript import to_srt, words_from_json, words_json
from ..jobs import StageError, stage
from ..render import captions as cap
from ..render import stitch as st
from ..render.backends import get_backend
from ..render.base import ClipResult, ClipSpec, RenderError
from ..render.cost import PricingUnknown, clip_cost, estimate, within_budget
from ..render.media import dims, probe
from ..settings import load_pricing
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
                              vo=s["clips"][k]["vo"] if k < len(s["clips"]) else ""))
    return specs


def render_spend(project: str) -> float:
    return sum(j["cost_usd"] for j in db.list_jobs(project, 1000) if j["stage"] == "render")


@stage("render", "Render clips", lane="render",
       description="One clip at a time with retries; cost gate before any paid clip; hard per-video budget cap.")
async def render(ctx) -> dict:
    p = ctx.project_data()
    r = ctx.settings["render"]
    backend_name = r["backend"] if not ctx.dry_run else "mock"
    if ctx.dry_run and r["backend"] != "mock":
        ctx.log(f"dry run is on: using the mock backend instead of {r['backend']}", "warn")
    specs = _clip_specs(ctx, p)
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
        ctx.log(f"{backend_name}: free placeholder clips, no cost gate needed")
    try:
        backend = get_backend(backend_name)
    except RenderError as e:
        raise StageError(str(e)) from e
    prev: ClipResult | None = None
    if todo[0].index > 0:
        prev_png = ctx.path(f"clips/clip-{todo[0].index:02d}.last.png")
        prev_meta = ctx.path(f"clips/clip-{todo[0].index:02d}.json")
        if prev_png.exists():
            pm = json.loads(prev_meta.read_text()) if prev_meta.exists() else {}
            prev = ClipResult(todo[0].index - 1, ctx.path(f"clips/clip-{todo[0].index:02d}.mp4"), 10.0, 0.0, backend_name,
                              interaction_id=pm.get("interaction_id"), last_frame=prev_png)
    max_retries = int(r.get("max_retries", 2))
    for n, sp in enumerate(todo):
        ctx.check_cancelled()
        nxt = clip_cost(pricing, backend_name, sp.resolution, sp.duration)
        spent = render_spend(ctx.project)
        if not within_budget(spent, nxt, cap_usd):
            ctx.log(f"budget cap reached: spent ${spent:.2f}, next clip ${nxt:.2f}, cap ${cap_usd:.2f}. Stopping.", "error")
            raise StageError("budget cap reached; raise it in Settings or regenerate fewer clips")
        meta_path = f"clips/clip-{sp.index + 1:02d}.json"
        ctx.write_json(meta_path, {"index": sp.index, "status": "rendering", "backend": backend_name})
        attempt, delay = 0, 5.0
        while True:
            attempt += 1
            try:
                res = await backend.render_clip(sp, prev if sp.continuity != "none" else None, ctx.log)
                break
            except RenderError as e:
                ctx.log(f"clip {sp.index + 1} attempt {attempt} failed: {e}", "warn")
                if not e.retryable or attempt > max_retries:
                    ctx.write_json(meta_path, {"index": sp.index, "status": "failed", "backend": backend_name, "error": str(e)})
                    raise StageError(f"clip {sp.index + 1} failed after {attempt} attempt(s): {e}") from e
                await asyncio.sleep(delay)
                delay *= 2
        ctx.add_cost(res.cost_usd, f"clip {sp.index + 1}")
        info = probe(res.path)
        ctx.write_json(meta_path, {"index": sp.index, "status": "done", "backend": backend_name, "attempts": attempt,
                                   "cost_usd": res.cost_usd, "interaction_id": res.interaction_id,
                                   "prompt_hash": _prompt_hash(sp.prompt), "duration": info["duration"],
                                   "width": info["width"], "height": info["height"], "has_audio": info["has_audio"],
                                   "continuity": sp.continuity, "meta": res.meta})
        prev = res
        ctx.progress((n + 1) / len(todo), f"clip {sp.index + 1} done ({n + 1}/{len(todo)})")
    return {"outputs": ["clips/"]}


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
    await th(st.concat, clips, stitched, p["ratio"], res_name if res_name != "4k" else "1080p")
    ctx.progress(0.35, "concatenated")
    backend_used = json.loads(ctx.path("clips/clip-01.json").read_text()).get("backend", "mock")
    words, method = None, "estimate"
    if backend_used != "mock":
        words = await th(cap.whisper_words, stitched)
        method = "faster-whisper" if words else "estimate (faster-whisper not installed)"
    if not words:
        words = cap.estimate_words([c["vo"] for c in s["clips"]])
    ctx.write_json("final/words.json", {"method": method, "words": words_json(words)})
    ctx.write_text("final/final.srt", to_srt(words))
    # the on-screen card you approved at the hook gate wins over the director's suggestion
    hook_card = s["hook"].get("write") or a.get("hook_card")
    callouts = [{"t": (o["clip"] - 1) * 10 + 3.0, "text": o["text"], "hold": 2.2} for o in a.get("overlays", [])
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
    ctx.log(f"final.mp4: {info['duration']:.1f}s {info['width']}x{info['height']}, {report['after_i']:.1f} LUFS "
            f"(target {report['target_i']}), captions timed by {method}")
    return {"outputs": ["final/final.mp4", "final/poster.png", "final/final.srt", "final/captions.ass", "final/words.json", "final/loudness.json"]}


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
