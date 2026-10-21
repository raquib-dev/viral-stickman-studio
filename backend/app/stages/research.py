"""Stages 1-4: niche setup, viral discovery, pattern extraction ("why it worked"), topic finder."""
from __future__ import annotations

import json

from .. import db
from ..agent import tasks
from ..analysis import blueprint as bp
from ..analysis.labeler import label_transcript
from ..analysis.profile import build_profile
from ..analysis.topics import score_candidates
from ..analysis.transcript import cues_to_words, parse_cues, to_srt, words_json
from ..jobs import StageError, stage
from ..sources import synthetic
from ..sources.transcripts import fetch_auto_captions, ytdlp_available
from ..tools import runner as tools
from .common import fmt_for_project, primary_hook_panel, th

VALID_STYLES = {"1", "2A", "2B", "3", "4", "5"}


@stage("niche", "Niche setup", description="Validate the brief; draft voice.md from your own videos.",
       skills=["yt-script", "ig-reel"])
async def niche(ctx) -> dict:
    p = ctx.project_data()
    errors = []
    if not p.get("niche"):
        errors.append("niche is empty")
    if p.get("ratio") not in ("16:9", "9:16"):
        errors.append("aspect ratio must be 16:9 or 9:16 (director skill setup gate)")
    if str(p.get("style")) not in VALID_STYLES:
        errors.append("style must be one of 1, 2A, 2B, 3, 4, 5 (director skill setup gate)")
    d = int(p.get("duration") or 60)
    if d % 10:
        rounded = max(10, int(round(d / 10.0)) * 10)
        ctx.log(f"duration {d}s rounded to {rounded}s (the director skill works in 10-second multiples)", "warn")
        p["duration"] = rounded
        db.upsert_project(ctx.project, db.get_project(ctx.project)["name"], p)
    if not p.get("platforms"):
        errors.append("pick at least one platform")
    if errors:
        raise StageError("; ".join(errors))
    if str(p["style"]) == "3":
        ctx.log("Style 3 needs story-specific cast cards; the dry-run fixture falls back to the Style 1 anchor.", "warn")
    fmt = fmt_for_project(p)
    ctx.write_json("project.json", p)
    ctx.write_json("research/niche.json", {"niche": p["niche"], "subtopics": p.get("subtopics", []),
                                           "format": fmt, "platforms": p["platforms"], "competitors": p.get("competitors", {})})
    outputs = ["project.json", "research/niche.json"]
    for platform in ("youtube", "instagram"):
        trs = [t for t in (p.get("voice_transcripts") or {}).get(platform, []) if t.strip()]
        if trs:
            res = await ctx.agent.run(tasks.voice_draft(platform, trs, p["niche"]), ctx)
            path = f"research/voice-draft-{platform}.md"
            ctx.write_text(path, res["markdown"])
            outputs.append(path)
            ctx.log(f"voice draft for {platform} written to {path}; apply it from the Niche screen")
    ctx.log(f"format: {fmt}, {p['ratio']}, {p['duration']}s, Style {p['style']} {p.get('theme', '')}")
    return {"outputs": outputs}


@stage("discover", "Viral discovery", description="Rank by outlier multiple over each channel's own median.",
       skills=["yt-viral", "ig-viral"], tools=["yt-viral/swipe.py", "ig-viral/swipe.py"])
async def discover(ctx) -> dict:
    p = ctx.project_data()
    fmt = fmt_for_project(p)
    disc = ctx.settings["discovery"]
    synthetic_mode = ctx.dry_run
    result: dict = {"synthetic": synthetic_mode, "format": fmt}

    # ---- YouTube
    rows: list[dict] = list(p.get("yt_rows_pasted") or [])
    if synthetic_mode:
        rows = synthetic.yt_rows(p["niche"])
        ctx.log("DRY RUN: using SYNTHETIC YouTube rows (not real data)", "warn")
    else:
        from ..settings import has_secret
        if has_secret("YOUTUBE_API_KEY"):
            from ..sources.youtube import YouTubeClient, YouTubeError
            try:
                yt = YouTubeClient(ctx.log)
                comps = (p.get("competitors") or {}).get("youtube", [])
                rows += await th(yt.discover, p["niche"], p.get("subtopics", []), comps, fmt,
                                 disc["videos_per_channel"], disc["max_channels"])
                result["quota_units"] = yt.units
            except YouTubeError as e:
                raise StageError(f"YouTube Data API: {e}") from e
        else:
            ctx.log("No YOUTUBE_API_KEY: YouTube discovery uses only rows you pasted.", "warn")
    ctx.progress(0.3, f"{len(rows)} YouTube rows")
    all_ranked = await th(tools.yt_swipe, rows, 0.0) if rows else {"outliers": [], "skipped_thin_channels": []}
    by_url = {r.get("url"): r for r in rows}
    ranked = [{**r, "platform": "youtube", "account": r["channel"], "baseline": r["median"],
               "duration": by_url.get(r["url"], {}).get("duration"), "synthetic": synthetic_mode}
              for r in all_ranked["outliers"]]
    min_mult = disc["yt_min_multiple"]
    yt_out = [r for r in ranked if r["multiple"] >= min_mult]
    db.replace_swipe(ctx.project, "youtube", "discover", ranked)
    result["youtube"] = {"rows": len(rows), "ranked": len(ranked), "outliers": yt_out,
                         "skipped_thin_channels": all_ranked.get("skipped_thin_channels", []), "min_multiple": min_mult}
    ctx.log(f"YouTube: {len(yt_out)} outliers at >= {min_mult}x of {len(ranked)} ranked videos")

    # ---- Instagram (paste-only; no API, no login)
    tsv = synthetic.ig_tsv() if synthetic_mode else _ig_tsv_from_paste(p.get("ig_rows") or [])
    if tsv:
        tsv_path = ctx.write_text("research/swipe-ig.tsv", tsv)
        ig = await th(tools.ig_swipe, tsv_path, ctx.path("research/swipe.md"))
        reels = [{**r, "platform": "instagram", "title": r["hook"], "multiple": r.get("outlier"),
                  "synthetic": synthetic_mode} for r in ig["reels"]]
        db.replace_swipe(ctx.project, "instagram", "discover", reels)
        signal = ctx.settings["discovery"]["ig_signal_multiple"]
        result["instagram"] = {**{k: v for k, v in ig.items() if k != "reels"}, "reels": reels,
                               "signal_multiple": signal, "signals": [r for r in reels if (r["multiple"] or 0) >= signal]}
        if ig.get("baseline") == "follower count":
            ctx.log("Instagram rows have no median: ranking falls back to follower count (weaker). Add medians.", "warn")
    else:
        result["instagram"] = None
        ctx.log("Instagram: no pasted reels yet (paste links + stats in Discover).")
    ctx.progress(0.55, "ranked")

    # ---- transcripts for the top outliers
    top = sorted(yt_out, key=lambda r: -r["multiple"])[:8]
    pasted = {t.get("url"): t for t in (p.get("pasted_transcripts") or [])}
    trs = []
    for i, r in enumerate(top):
        vid = f"yt{i + 1:02d}"
        cues = None
        if synthetic_mode:
            cues = synthetic.transcript(i, float(r.get("duration") or 58))
        elif r["url"] in pasted:
            cues = parse_cues(pasted[r["url"]]["text"])
        elif ytdlp_available():
            raw = await th(fetch_auto_captions, r["url"])
            cues = parse_cues(raw) if raw else None
        if not cues:
            ctx.log(f"no transcript for '{r['title'][:50]}' (paste it in Discover)", "warn")
            continue
        words = cues_to_words(cues)
        ctx.write_json(f"research/transcripts/{vid}.json", {"title": r["title"], "url": r["url"], "multiple": r["multiple"],
                                                            "duration": r.get("duration") or words[-1].e,
                                                            "synthetic": synthetic_mode, "words": words_json(words)})
        ctx.write_text(f"research/transcripts/{vid}.srt", to_srt(words))
        trs.append({"id": vid, "title": r["title"], "url": r["url"], "multiple": r["multiple"]})
        ctx.progress(0.55 + 0.3 * (i + 1) / max(1, len(top)), f"transcripts {i + 1}/{len(top)}")
    if not synthetic_mode and not ytdlp_available() and top:
        ctx.log("yt-dlp is not installed: install it (pip install yt-dlp) or paste transcripts.", "warn")
    result["transcripts"] = trs

    # ---- interpretation through the skills
    reads = {}
    if yt_out:
        reads["youtube"] = await ctx.agent.run(tasks.discovery_read("youtube", {"outliers": yt_out[:25]}, p["niche"]), ctx)
    if result["instagram"]:
        reads["instagram"] = await ctx.agent.run(tasks.discovery_read("instagram", {"reels": result["instagram"]["reels"][:25]}, p["niche"]), ctx)
    result["reads"] = reads
    ctx.write_json("research/discovery.json", result)
    return {"outputs": ["research/discovery.json", "research/swipe-ig.tsv", "research/swipe.md", "research/transcripts/"]}


def _ig_tsv_from_paste(rows: list[dict]) -> str:
    if not rows:
        return ""
    lines = ["account\tfollowers\tmedian\tviews\thook\turl\tlength\tcta"]
    for r in rows:
        cells = [str(r.get(k, "") or "").replace("\t", " ").replace("\n", " ") for k in
                 ("account", "followers", "median", "views", "hook", "url", "length", "cta")]
        lines.append("\t".join(cells))
    return "\n".join(lines) + "\n"


@stage("patterns", "Pattern extraction", description="Label every beat of the top outliers against the blueprint.",
       skills=[], tools=["yt-script/hookscore.py", "ig-reel/hookscore.py"])
async def patterns(ctx) -> dict:
    p = ctx.project_data()
    fmt = fmt_for_project(p)
    disc = ctx.read_json("research/discovery.json")
    questions = {r["type"]: r["how_to_detect"]["llm_question"] for r in bp.rules(fmt)
                 if r["how_to_detect"].get("llm_question") and r["type"] in bp.LABELED_TYPES}
    videos = []
    for i, t in enumerate(disc.get("transcripts", [])):
        tr = ctx.read_json(f"research/transcripts/{t['id']}.json")
        from ..analysis.transcript import sentences, words_from_json
        words = words_from_json(tr["words"])
        duration = float(tr.get("duration") or words[-1].e)
        timed = "\n".join(f"[{s.s:.1f}] {s.text}" for s in sentences(words))
        llm = await ctx.agent.run(tasks.label_llm(t["id"], timed, questions, duration), ctx)
        labels = label_transcript(words, duration, fmt, llm.get("answers"))
        hook_text = " ".join(w.w for w in words if w.s < 3.0) or sentences(words)[0].text
        yt = (await th(tools.yt_hookscore, [hook_text]))[0]
        ig = (await th(tools.ig_hookscore, [hook_text]))[0]
        igf = (await th(tools.ig_formula, [hook_text])).get(hook_text.replace("\n", " ").strip(), {})
        rec = {"id": t["id"], "title": t["title"], "url": t.get("url"), "multiple": t.get("multiple"),
               "duration": duration, "synthetic": tr.get("synthetic", False), "labels": labels,
               "hook": {"text": hook_text, "yt": yt, "ig": ig, "formula_yt": yt.get("formula"), "formula_ig": igf.get("name")}}
        ctx.write_json(f"research/patterns/{t['id']}.json", rec)
        videos.append(rec)
        ctx.progress((i + 1) / max(1, len(disc.get("transcripts", []))), f"labelled {i + 1} videos")
    learned = ctx.read_json("research/learned.json", default=[]) if ctx.path("research/learned.json").exists() else []
    profile = build_profile(videos, learned)
    profile["format"] = fmt
    profile["synthetic"] = bool(disc.get("synthetic"))
    profile["hook_formulas"] = _formula_counts(videos)
    ctx.write_json("research/niche-profile.json", profile)
    for line in profile["summary"]:
        ctx.log("profile: " + line)
    if not videos:
        ctx.log("No transcripts: the profile is empty and beat planning uses blueprint defaults.", "warn")
    return {"outputs": ["research/patterns/", "research/niche-profile.json"]}


def _formula_counts(videos: list[dict]) -> dict:
    out: dict[str, dict[str, int]] = {"yt": {}, "ig": {}}
    for v in videos:
        for k, key in (("yt", "formula_yt"), ("ig", "formula_ig")):
            name = v["hook"].get(key) or "Unclassified"
            out[k][name] = out[k].get(name, 0) + 1
    return out


@stage("topics", "Topic finder", description="Score candidates on outlier evidence, gaps, stick-figure fit and niche fit.",
       skills=["yt-viral", "ig-viral"])
async def topics(ctx) -> dict:
    p = ctx.project_data()
    profile = ctx.read_json("research/niche-profile.json")
    swipe = db.swipe_items(ctx.project)
    outliers = [{"title": s["title"] or s["hook"], "multiple": s["multiple"], "views": s["views"], "platform": s["platform"],
                 "synthetic": s["synthetic"]} for s in swipe if (s["multiple"] or 0) >= 1.5][:40]
    res = await ctx.agent.run(tasks.topic_candidates(p["niche"], p.get("subtopics", []), outliers, profile["summary"]), ctx)
    rows = [{"title": s["title"] or s["hook"], "hook": s["hook"], "multiple": s["multiple"], "views": s["views"],
             "url": s["url"], "platform": s["platform"], "synthetic": s["synthetic"]} for s in swipe]
    ranked = score_candidates(res["candidates"], rows, p["niche"] + " " + " ".join(p.get("subtopics", [])),
                              ctx.settings.get("topic_weights"))
    ctx.write_json("research/topics.json", {"weights": ctx.settings.get("topic_weights"), "topics": ranked,
                                            "synthetic_evidence": any(r["synthetic"] for r in rows)})
    for r in ranked[:3]:
        ctx.log(f"#{r['rank']} {r['score']:.2f} {r['title']}")
    return {"outputs": ["research/topics.json"]}
