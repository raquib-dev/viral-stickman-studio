"""Stages 5-6: hooks (GATE: topic), script (GATE: hook), director Phase A, Phase B (GATE: Phase A)."""
from __future__ import annotations

import hashlib
import re
import time

from .. import db
from ..agent import tasks
from ..agent.skillref import COLOR_NOTATION, anchor_for, female_voice_block, male_voice_block
from ..analysis import blueprint as bp
from ..analysis.profile import plan_beats
from ..jobs import StageError, stage
from ..tools import runner as tools
from .common import fmt_for_project, primary_hook_panel, split_sentences, th, word_count

MIN_WORDS, MAX_WORDS = 12, 25   # per 10 s clip (director skill: 20-25; floor keeps clips from going silent)
ADVISORY_NOTES = ("Beat 1 has no number", "Loops:", "Length is on target")


@stage("hooks", "Hooks", description="Five hooks against the formulas, scored by both hookscore.py panels.",
       skills=["yt-script", "ig-reel"], tools=["yt-script/hookscore.py", "ig-reel/hookscore.py"])
async def hooks(ctx) -> dict:
    p = ctx.project_data()
    tdata = ctx.read_json("research/topics.json")
    topics = tdata["topics"]
    if not topics:
        raise StageError("no topics to choose from")
    choice = ctx.require_gate("topic", {"topic_ids": [t["id"] for t in topics], "scores": [t["score"] for t in topics]},
                              options=[{"id": t["id"], "label": t["title"]} for t in topics],
                              default_choice=topics[0]["id"], auto_reason="top-ranked topic")
    topic = next(t for t in topics if t["id"] == choice)
    ctx.log(f"topic: {topic['title']}")
    fmt = fmt_for_project(p)
    profile = ctx.read_json("research/niche-profile.json")
    res = await ctx.agent.run(tasks.hooks(topic, p["niche"], fmt, profile["summary"]), ctx)
    says = [h["say"] for h in res["hooks"]]
    yt = {r["hook"]: r for r in await th(tools.yt_hookscore, says)}
    ig = {r["hook"]: r for r in await th(tools.ig_hookscore, says)}
    igf = await th(tools.ig_formula, says)
    panel = primary_hook_panel(fmt, p.get("platforms", []))
    scored = []
    for h in res["hooks"]:
        key = h["say"].replace("\n", " ").strip()
        y, i = yt.get(key, {}), ig.get(key, {})
        ys, is_ = float(y.get("verdict", 0)), float(i.get("score", 0))
        rank_score = {"yt": ys, "ig": is_, "mean": (ys + is_) / 2}[panel]
        flags = list(i.get("flags", []))
        if abs(ys - is_) > 20:
            flags.append(f"panels disagree by {abs(ys - is_):.0f} points (yt {ys:.0f} vs ig {is_:.0f})")
        secs = word_count(h["say"]) / (float(ctx.settings.get("speaking_wpm", 150)) / 60)
        too_long = secs > 3.0
        if too_long:
            flags.append(f"SAY takes ~{secs:.1f}s at {ctx.settings.get('speaking_wpm', 150)} wpm; the blueprint requires the opening line within 3 s")
        if word_count(h["write"]) > 5:
            flags.append("on-screen WRITE line is over 5 words")
        if set(re.findall(r"[a-z]{4,}", h["write"].lower())) & set(re.findall(r"[a-z]{4,}", h["say"].lower())):
            flags.append("WRITE repeats words from SAY (alignment rule: different words, same idea)")
        scored.append({**h, "yt": y, "ig": i, "formula_yt": y.get("formula"), "formula_ig": igf.get(key, {}).get("name"),
                       "rank_score": round(rank_score, 1), "dealbreakers": i.get("flags", []), "flags": flags,
                       "over_3s": too_long, "seconds": round(secs, 1)})
    # ig dealbreakers and hooks that break the 3-second rule rank below the rest (the user can still pick them)
    scored.sort(key=lambda h: (bool(h["dealbreakers"]), h["over_3s"], -h["rank_score"]))
    for k, h in enumerate(scored, 1):
        h["rank"] = k
    ctx.write_json("script/hooks.json", {"topic": topic, "panel": panel, "hooks": scored,
                                         "note": "hookscore.py is a heuristic (AUC 0.83 bad-vs-real, ~0.56 hit-vs-miss per its authors)."})
    for h in scored[:2]:
        ctx.log(f"hook #{h['rank']} {h['rank_score']:.0f} ({panel}): {h['say']}")
    return {"outputs": ["script/hooks.json"]}


def _script_flags(clips: list[dict], beats_report: dict, hook_say: str, duration: int) -> list[str]:
    flags = []
    for r in beats_report["beats"]:
        for f in r["flags"]:
            flags.append(f"beat {r['n']} '{r['text'][:40]}': {f}")
    for n in beats_report["notes"]:
        if not n.startswith(ADVISORY_NOTES):
            flags.append(n)
    for c in clips:
        wc = word_count(c["vo"])
        if wc > MAX_WORDS:
            flags.append(f"clip {c['index'] + 1}: {wc} words (max {MAX_WORDS} for a 10 s Omni clip)")
        if wc < MIN_WORDS:
            flags.append(f"clip {c['index'] + 1}: {wc} words (min {MIN_WORDS})")
    if not clips[0]["vo"].startswith(hook_say.strip()[:30]):
        flags.append("clip 1 must open with the approved hook's SAY line verbatim")
    asks = [s for c in clips for s in split_sentences(c["vo"]) if any(p.search(s) for p in bp.patterns("cta-one-at-payoff"))]
    if len(asks) != 1:
        flags.append(f"{len(asks)} asks found; exactly one is required")
    if len(clips) != duration // 10:
        flags.append(f"{len(clips)} clips for {duration}s; need {duration // 10}")
    return flags


@stage("script", "Script", description="5-stage script placed by the niche profile; beats.py timing; ig-human pass.",
       skills=["yt-script", "ig-reel", "ig-human"], tools=["ig-reel/beats.py", "ig-human/humanize.py", "ig-human/detect.py"])
async def script(ctx) -> dict:
    p = ctx.project_data()
    hk = ctx.read_json("script/hooks.json")
    ranked = hk["hooks"]
    choice = ctx.require_gate("hook", {"topic": hk["topic"]["id"], "hooks": [h["say"] for h in ranked]},
                              options=[{"id": h["id"], "label": h["say"]} for h in ranked],
                              default_choice=ranked[0]["id"], auto_reason="top-scored hook")
    hook = next(h for h in ranked if h["id"] == choice)
    topic = hk["topic"]
    duration = int(p["duration"])
    fmt = fmt_for_project(p)
    profile = ctx.read_json("research/niche-profile.json")
    plan = plan_beats(duration, fmt, profile)
    ctx.write_json("script/plan.json", plan)
    wpm = float(ctx.settings.get("speaking_wpm", 150))
    revise = None
    for attempt in range(1, 4):
        res = await ctx.agent.run(tasks.script(topic, hook, duration, fmt, plan, profile["summary"], p["niche"], revise=revise), ctx)
        clips = res["clips"]
        lines = [s for c in clips for s in split_sentences(c["vo"])]
        report = await th(tools.beats, "\n".join(lines), wpm, duration)
        flags = _script_flags(clips, report, hook["say"], duration)
        ctx.log(f"script attempt {attempt}: {report['total_words']} words, ~{report['total_seconds']:.1f}s at {wpm:.0f} wpm, "
                f"{len(flags)} flag(s)")
        if not flags:
            break
        for f in flags:
            ctx.log("  flag: " + f, "warn")
        revise = {"clips": clips, "flags": flags}
    else:
        ctx.log("flags remain after 3 attempts: shown in Studio for you to fix by hand", "warn")
    ctx.progress(0.6, "humanizing")
    # ig-human: humanize.py then structural rewrite of flagged lines, then detect.py before/after
    raw = "\n".join(c["vo"] for c in clips)
    hum = await th(tools.humanize, raw)
    text = hum["text"].rstrip("\n")
    structural = hum["report"].get("structures") or hum["report"].get("structural") or []
    if structural:
        text = (await ctx.agent.run(tasks.structural_rewrite(text, structural), ctx))["text"].rstrip("\n")
    new_lines = text.split("\n")
    if len(new_lines) == len(clips):
        for c, line in zip(clips, new_lines):
            c["vo"] = line.strip()
    else:
        ctx.log("humanizer changed the line count; keeping the original narration", "warn")
    before = await th(tools.detect, raw)
    after = await th(tools.detect, "\n".join(c["vo"] for c in clips))
    final_lines = [s for c in clips for s in split_sentences(c["vo"])]
    final_report = await th(tools.beats, "\n".join(final_lines), wpm, duration)
    final_flags = _script_flags(clips, final_report, hook["say"], duration)
    data = {**res, "clips": clips, "hook": hook, "topic": topic, "duration": duration, "format": fmt, "wpm": wpm,
            "flags": final_flags, "plan": plan}
    ctx.write_json("script/script.json", data)
    ctx.write_json("script/beats.json", final_report)
    ctx.write_json("script/human.json", {"humanize_report": hum["report"], "detect_before": before, "detect_after": after})
    md = [f"# {res['title']}", "", f"Hook: {hook['say']}  (on screen: {hook['write']})", ""]
    for c in clips:
        md += [f"## Clip {c['index'] + 1} ({c['index'] * 10}-{c['index'] * 10 + 10}s) - {c['stage']}", c["vo"],
               f"_planned beats: {', '.join(c.get('beats') or []) or '-'}_", ""]
    if res.get("claims_to_source"):
        md += ["## Claims to verify before publishing", *[f"- {x}" for x in res["claims_to_source"]]]
    if res.get("mistake"):
        md += ["", f"## Deliberate mistake (intentional, visual only)", str(res["mistake"])]
    ctx.write_text("script/script.md", "\n".join(md) + "\n")
    ctx.log(f"human score {before.get('human_score')} -> {after.get('human_score')} ({after.get('verdict')}); "
            f"{len(final_flags)} flag(s) remaining")
    return {"outputs": ["script/script.json", "script/script.md", "script/beats.json", "script/human.json", "script/plan.json"]}


def _annotations(plan: list[dict]) -> list[dict]:
    out = []
    for b in plan:
        try:
            rule = bp.rule(b["rule_id"])
            how = rule["how_to_stage_in_stickman"]
        except KeyError:
            how = ""
        out.append({**b, "label": b["type"].replace("-", " "), "how_to_stage": how})
    return out


@stage("direction_a", "Director Phase A", description="directing-stickman-videos Phase A with blueprint marks on the timeline.",
       skills=["directing-stickman-videos"])
async def direction_a(ctx) -> dict:
    p = ctx.project_data()
    s = ctx.read_json("script/script.json")
    ann = _annotations(s["plan"])
    ctx.write_json("direction/phase-a.annotations.json", ann)
    g = db.get_gate(ctx.project, "phase_a")
    note = ctx.params.get("revision_note") or (g["note"] if g and g["status"] == "rejected" else "")
    clips = [{"index": c["index"], "stage": c["stage"], "vo": c["vo"]} for c in s["clips"]]
    res = await ctx.agent.run(tasks.phase_a(s["title"], clips, p["ratio"], int(p["duration"]), str(p["style"]),
                                            p.get("theme", "dark"), ann, p.get("voice_pref", "male"), note), ctx)
    ctx.write_text("direction/phase-a.md", res["markdown"])
    ctx.write_json("direction/phase-a.json", res)
    return {"outputs": ["direction/phase-a.md", "direction/phase-a.json", "direction/phase-a.annotations.json"]}


def phase_a_gate_payload(ctx_or_root, p: dict) -> dict:
    md = (ctx_or_root.path("direction/phase-a.md") if hasattr(ctx_or_root, "path") else ctx_or_root / "direction/phase-a.md").read_text(encoding="utf-8")
    return {"phase_a_sha": hashlib.sha256(md.encode()).hexdigest()[:16], "ratio": p["ratio"],
            "duration": int(p["duration"]), "style": str(p["style"]), "theme": p.get("theme", "dark")}


FIXED_ANCHOR_STYLES = ("1", "4", "5")  # styles with one tested anchor in the skill; 2A/2B/3 are per-story


def assemble_phase_b(res: dict, style: str, theme: str, voice_pref: str, app_inserts: bool) -> list[str]:
    """Put the frozen character anchor and voice block into every prompt verbatim, from the skill's own
    reference files. Small local models paraphrase long blocks, which breaks the skill's continuity
    method; the app owns these two blocks, the model writes the scenes. Returns what it changed."""
    fixes = []
    anchor = res.get("character_anchor", "").strip()
    if style in FIXED_ANCHOR_STYLES:
        canon = anchor_for(style, theme)
        faceless = canon.replace("occasional simple line expressions, no detailed facial features,", "no face, no eyes, no mouth,")
        if anchor not in (canon, faceless):
            if anchor:
                fixes.append("character anchor replaced with the skill's tested text (the model's version differed)")
            anchor = canon
    voice = res.get("voice_block", "").strip()
    if app_inserts or not voice:
        skill_voice = female_voice_block() if voice_pref == "female" else male_voice_block()
        if voice and voice != skill_voice:
            fixes.append("voice block replaced with the skill's tested text")
        voice = skill_voice
    res["character_anchor"], res["voice_block"] = anchor, voice
    for pr in res.get("prompts", []):
        text = pr["text"].replace("{{ANCHOR}}", anchor).replace("{{VOICE}}", voice)
        if anchor and style not in ("2A", "2B", "3") and anchor not in text:
            lines = text.split("\n")
            text = "\n".join([*lines[:1], anchor, *lines[1:]])  # after the opening format line
            if not app_inserts:
                fixes.append(f"clip {pr['clip']}: inserted the character anchor verbatim")
        if voice not in text:
            text = text.rstrip() + "\n" + voice
            if not app_inserts:
                fixes.append(f"clip {pr['clip']}: inserted the voice block verbatim")
        pr["text"] = text
    return fixes


def check_phase_b(res: dict, n: int, style: str, theme: str) -> list[str]:
    errs = []
    prompts = res["prompts"]
    if len(prompts) != n:
        errs.append(f"{len(prompts)} prompts, expected {n}")
    anchor, voice = res["character_anchor"].strip(), res["voice_block"].strip()
    for pr in prompts:
        if style not in ("2A", "2B", "3") and anchor not in pr["text"]:
            errs.append(f"clip {pr['clip']}: character anchor is not repeated verbatim")
        if voice not in pr["text"]:
            errs.append(f"clip {pr['clip']}: voice block is not repeated verbatim")
        if COLOR_NOTATION.search(pr["text"]):
            errs.append(f"clip {pr['clip']}: technical colour notation found")
    if style == "1":
        expected = anchor_for("1", theme)
        if anchor != expected and anchor != anchor_for("1", theme).replace(
                "occasional simple line expressions, no detailed facial features,", "no face, no eyes, no mouth,"):
            errs.append("Style 1 anchor differs from the skill's tested base (style-catalog.md)")
    return errs


@stage("direction_b", "Director Phase B", description="Per-clip Omni Flash prompts after Phase A approval; anchors verified.",
       skills=["directing-stickman-videos"])
async def direction_b(ctx) -> dict:
    p = ctx.project_data()
    payload = phase_a_gate_payload(ctx, p)
    ctx.require_gate("phase_a", payload, options=None, default_choice="approved", auto_reason="Phase A as written")
    g = db.get_gate(ctx.project, "phase_a")
    a = ctx.read_json("direction/phase-a.json")
    md = ctx.read_text("direction/phase-a.md")
    approval = {"approved_by": g["decided_by"], "at": time.strftime("%Y-%m-%d %H:%M", time.localtime(g["decided_at"] or time.time())),
                "note": g.get("note") or "", "phase_a_sha": payload["phase_a_sha"]}
    # a non-Claude model writes direction only in "local"/"groq" mode (the hybrids send direction to Claude)
    app_inserts = not ctx.dry_run and ctx.settings.get("agent", {}).get("provider") in ("local", "groq")
    res = await ctx.agent.run(tasks.phase_b(md, a["rows"], p["ratio"], int(p["duration"]), str(p["style"]),
                                            p.get("theme", "dark"), approval, app_inserts), ctx)
    if app_inserts:
        ctx.log("local model: the app inserts the frozen anchor and voice block verbatim from the skill files")
    for fix in assemble_phase_b(res, str(p["style"]), p.get("theme", "dark"), p.get("voice_pref", "male"), app_inserts):
        ctx.log("repaired: " + fix, "warn")
    errs = check_phase_b(res, int(p["duration"]) // 10, str(p["style"]), p.get("theme", "dark"))
    ctx.write_json("direction/phase-b.json", {**res, "checks": errs, "approval": approval})
    out = [f"# Phase B - Omni Flash production package", "", "## Global continuity block", res["global_block"], "",
           "## Frozen character anchor", "```text", res["character_anchor"], "```", "", "## Frozen voice block", "```text",
           res["voice_block"], "```", ""]
    for pr in res["prompts"]:
        ctx.write_text(f"direction/prompts/clip-{pr['clip']:02d}.txt", pr["text"] + "\n")
        out += [f"## Clip {pr['clip']}", "```text", pr["text"], "```", ""]
    out += ["## Stitching guide", res["stitching_guide"], "", "## Voice and music continuity", res["audio_note"]]
    ctx.write_text("direction/phase-b.md", "\n".join(out) + "\n")
    if errs:
        for e in errs:
            ctx.log("check: " + e, "error")
        raise StageError(f"Phase B failed {len(errs)} check(s): {errs[0]}")
    ctx.log(f"{len(res['prompts'])} prompts; anchor + voice block verbatim in every clip; no colour notation")
    return {"outputs": ["direction/phase-b.md", "direction/phase-b.json", "direction/prompts/"]}
