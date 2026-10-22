"""Dry-run fixture agent outputs. Deterministic, labelled `_fixture: true`, and honest: no invented
statistics. The sample niche ("personal finance psychology") gets a hand-written kit for its top topic;
anything else gets clearly templated text. The vendored Python tools still score and time all of it."""
from __future__ import annotations

import re
from typing import Any

from .skillref import anchor_for, male_voice_block

FIX = {"_fixture": True}
STAGES = ["golden-hook", "disrupting-assumptions", "insider-secrets", "ultimate-truth", "elevation-discussion"]


def _is_sample(niche: str) -> bool:
    return "finance" in niche.lower() and "psych" in niche.lower()


def _stage_for(i: int, n: int) -> str:
    """Director skill clip allocation (storyboard-template.md), scaled to n clips."""
    if i == 0:
        return "golden-hook"
    if i == n - 1:
        return "elevation-discussion"
    frac = i / max(1, n - 1)
    if frac < 0.3:
        return "disrupting-assumptions"
    if frac < 0.6:
        return "insider-secrets"
    return "ultimate-truth"


# ---- niche ----------------------------------------------------------------------------------

def voice_draft(platform: str, transcripts: list[str], niche: str) -> dict:
    words = " ".join(transcripts).split()
    contractions = sum(1 for w in words if "'" in w)
    return {**FIX, "markdown": f"""# voice.md (DRY-RUN DRAFT for {platform})

## Who I am talking to
{{{{your answer}}}} (niche: {niche})

## How I actually talk
Drafted from {len(transcripts)} pasted transcript(s), {len(words)} words, {contractions} contractions.
{{{{paste or confirm}}}}

## Words I never use
{{{{your answer}}}}

## Words I do use
{{{{your answer}}}}

## What I will not claim
Numbers I cannot show. Results that are not mine.

## My format
Faceless stick-figure explainers, voiceover only, no intro.
"""}


# ---- discovery ------------------------------------------------------------------------------

def discovery_read(platform: str, swipe: dict, niche: str) -> dict:
    rows = swipe.get("outliers") or swipe.get("reels") or []
    top = [{"title": r.get("title") or r.get("hook") or "", "multiple": float(r.get("multiple") or r.get("outlier") or 0),
            "formula": r.get("formula") or "Unclassified", "note": "synthetic dry-run row"} for r in rows[:5]]
    return {**FIX, "top": top,
            "shared_structure": "Dry run: the top rows open on a named mistake or a 'your brain' reframe in under 10 words.",
            "makeable": "Dry run: the present-bias angle fits a stick-figure metaphor and needs no new footage.",
            "confidence": f"Synthetic sample of {len(rows)} rows: shows the pipeline, proves nothing about the niche."}


# ---- patterns -------------------------------------------------------------------------------

_TS = re.compile(r"\[(\d+(?:\.\d+)?)\]\s*([^\[]+)")


def label_llm(video_id: str, timed_text: str, questions: dict, duration: float) -> dict:
    """Heuristic stand-in for the Sonnet labeler: finds the obvious cases only."""
    answers: dict[str, list[dict]] = {}
    for m in _TS.finditer(timed_text):
        t, text = float(m.group(1)), m.group(2).strip()
        low = text.lower()
        if re.search(r"\bone, two, four\b|\bthree coins\b.*\bfour\b", low):
            answers.setdefault("deliberate-mistake-placement", []).append({"t": t, "quote": text[:120], "confidence": 0.6})
        if re.search(r"\bthe (real )?(fix|answer) is\b|\bthat's why\b", low) and t / duration > 0.4:
            answers.setdefault("payoff-timing", []).append({"t": t, "quote": text[:120], "confidence": 0.5})
    return {**FIX, "answers": answers}


# ---- topics ---------------------------------------------------------------------------------

SAMPLE_TOPICS = [
    ("present-bias", "Why your brain treats future-you like a stranger", "present bias and the future self",
     ["future", "brain", "stranger", "saving", "save"], 5, "One figure meets a faceless 'future self' across a gap; coins drift away. Pure metaphor, no text needed.", 5),
    ("lifestyle-creep", "Why every raise somehow leaves you just as broke", "lifestyle creep and hedonic adaptation",
     ["raise", "broke", "spending", "lifestyle"], 4, "A staircase of raises with a treadmill that speeds up with each step.", 5),
    ("budget-week-three", "Why most budgets quietly die in week three", "willpower depletion vs systems",
     ["budget", "budgets", "willpower", "fail"], 4, "A figure carrying a budget boulder that gets heavier each day.", 5),
    ("mental-accounting", "Why a tax refund feels like free money", "mental accounting",
     ["refund", "money", "free", "accounting"], 4, "Coins sorted into labelled jars (icon-only) that are secretly one jar.", 4),
    ("anchoring", "Why 'was $200, now $99' works on you every time", "anchoring in pricing",
     ["price", "anchor", "sale", "discount"], 3, "Two price tags as giant weights; but it leans on numbers on screen, which Omni garbles.", 4),
    ("ostrich-effect", "Why you avoid checking your bank balance", "the ostrich effect",
     ["balance", "avoid", "checking", "bank"], 5, "The figure literally buries its head in sand next to a glowing phone.", 5),
    ("latte-myth", "The latte isn't why you're broke", "small purchases vs big fixed costs",
     ["latte", "coffee", "broke", "small"], 4, "A tiny coffee cup villain vs a looming house-shaped shadow.", 4),
    ("loss-aversion", "Why you hold losing investments too long", "loss aversion and sunk costs",
     ["losing", "investments", "loss", "stocks"], 3, "A figure clinging to a sinking anchor; charts would be garbled, so keep it physical.", 4),
]


def research_queries(brief: str, niche: str) -> dict:
    """Dry run: the brief's longest words as queries."""
    words = sorted(set(re.findall(r"[A-Za-z]{4,}", brief)), key=len, reverse=True)[:3] or ["AI"]
    return {**FIX, "queries": words, "tools": [t for t in ("Claude", "ChatGPT", "Gemini", "Codex") if t.lower() in brief.lower()]}


def topic_candidates(niche: str, subtopics: list, outliers: list, profile_summary: list, n: int = 8,
                     news: list | None = None, brief: str = "") -> dict:
    if news and not _is_sample(niche):
        # dry run with (synthetic) news: one candidate per top item, grounded in it
        cands = [{"id": f"n{k + 1}", "title": it["title"][:70], "angle": f"dry-run: the funny side of '{it['title'][:50]}'",
                  "keywords": sorted(set(re.findall(r"[a-z]{4,}", it["title"].lower())))[:5], "stickman_fit": 4,
                  "stickman_reason": "dry-run: a desk scene", "niche_rating": 4, "demand_note": "dry-run",
                  "news_ids": [it["id"]], "story": f"dry-run (synthetic): {it['title']}"} for k, it in enumerate(news[:n])]
        return {**FIX, "candidates": cands}
    if _is_sample(niche):
        cands = [{"id": i, "title": t, "angle": a, "keywords": kw, "stickman_fit": fit, "stickman_reason": why,
                  "niche_rating": nr, "demand_note": "dry-run: see related synthetic outliers on the board"}
                 for i, t, a, kw, fit, why, nr in SAMPLE_TOPICS[:n]]
    else:
        base = [w for w in re.findall(r"[a-z]{4,}", niche.lower())][:3] or ["topic"]
        cands = [{"id": f"t{k + 1}", "title": f"{s.title()}: the part nobody explains (template {k + 1})",
                  "angle": f"dry-run template about {s}", "keywords": base + [s.lower()],
                  "stickman_fit": 3 + (k % 3), "stickman_reason": "dry-run template", "niche_rating": 3,
                  "demand_note": "dry-run"} for k, s in enumerate((subtopics or base * 3)[:n])]
    return {**FIX, "candidates": cands}


# ---- hooks ----------------------------------------------------------------------------------

def hooks(topic: dict, niche: str, platform: str, profile_summary: list, n: int = 5, dialogue: dict | None = None) -> dict:
    if topic.get("id") == "present-bias":
        hs = [
            ("h1", "Your brain thinks future-you is a stranger.", "WHO IS THAT?", "Mid-stride, the figure hands coins to a faceless twin who walks away.", "saving fails because future-you feels like someone else", "Nobody Tells You / Contrarian"),
            ("h2", "Stop blaming willpower for your empty savings account.", "IT'S NOT DISCIPLINE", "A figure flexes, a piggy bank cracks anyway.", "the problem is not willpower", "Negative Command"),
            ("h3", "You're paying a stranger every time you save nothing.", "WHO PAYS?", "Coins fly from the figure's pocket into a shadowy hand.", "skipping saving bills your future self", "The Mistake"),
            ("h4", "Nobody tells you why saving feels like giving money away.", "WHY IT HURTS", "The figure drops a coin into a box that vanishes.", "saving feels like a loss to a stranger", "Nobody Tells You"),
            ("h5", "Why does spending today always beat saving for later?", "NOW ALWAYS WINS", "Two figures tug a coin; the near one yanks it free.", "present bias", "The Question"),
        ]
    else:
        a = (topic.get("angle") or topic.get("title", "this")).strip().rstrip(".")
        hs = [(f"h{k + 1}", say, w, "The figure is already mid-action with the hero prop.", a, f) for k, (say, w, f) in enumerate([
            (f"Nobody explains {a} properly.", "THE REAL REASON", "Nobody Tells You"),
            (f"Stop ignoring {a}.", "IT COSTS YOU", "Negative Command"),
            (f"You're making the {re.sub(r'^(the|a|an) ', '', a)} mistake.", "CHECK YOURSELF", "The Mistake"),
            (f"Why does {a} keep winning?", "WHO WINS?", "The Question"),
            (f"{a[:1].upper() + a[1:]} isn't what you think.", "WRONG ON PURPOSE", "Contrarian Flip"),
        ])]
    return {**FIX, "hooks": [{"id": i, "say": s, "write": w, "show": sh, "align": al, "formula": f,
                              "why": "dry-run fixture"} for i, s, w, sh, al, f in hs[:n]]}


# ---- script ---------------------------------------------------------------------------------

# One line per sentence; every sentence is short enough for beats.py (<= 4 s at 150 wpm) and every
# third line carries something concrete (a name, a number) so the abstract-run check stays quiet.
PRESENT_BIAS_60 = [
    ("golden-hook", ["{HOOK}", "And that stranger is paying for tonight.", "Every tap of your Visa sends them the bill."]),
    ("disrupting-assumptions", ["Most people think saving is about willpower.", "It isn't.",
                                "Picture yourself 10 years from now.", "In Stanford brain scans, future-you looks like someone else."]),
    ("insider-secrets", ["But here's the catch: you don't hate future-you.", "You just can't feel them.",
                         "So tonight's takeout wins the argument every single Friday."]),
    ("insider-secrets", ["Researchers call this present bias.", "The closer the reward, the louder it shouts.",
                         "A reward next December only whispers in your ear."]),
    ("ultimate-truth", ["But here's the real fix, and it isn't willpower.", "Make saving automatic on payday, before you see it.",
                        "Richard Thaler's Save More Tomorrow does this."]),
    ("elevation-discussion", ["That's why disciplined people just removed the choice.", "Would you automate it on Monday, or trust yourself?",
                              "Comment below, and remember: {LOOP}."]),
]
PRESENT_BIAS_CLAIMS = [
    "Thinking about your future self activates the brain more like thinking about another person (a Stanford study) "
    "(Ersner-Hershfield, Wimmer & Knutson, 2009, Social Cognitive and Affective Neuroscience) - verify before publishing.",
    "Present bias: nearer rewards are overweighted relative to later ones (behavioural economics, e.g. Laibson 1997) - verify.",
    "Save More Tomorrow (Thaler & Benartzi, 2004, Journal of Political Economy) commits future raises to savings - verify.",
]


def _filler(stage: str, topic: str, k: int) -> list[str]:
    bank = {
        "golden-hook": [f"Here's what {topic} is really about.", "It starts before you notice it.", "And it costs you every week."],
        "disrupting-assumptions": ["Most people blame the wrong thing.", "That belief feels true.", f"Look closer at step {k + 1}."],
        "insider-secrets": ["But here's the catch nobody mentions.", "The real mechanism is quieter.", f"It shows up on day {k + 2}."],
        "ultimate-truth": ["Here's the fix that actually holds.", "Change the system, not the effort.", f"Try it for {k + 7} days."],
        "elevation-discussion": ["That's the whole trick.", "Would you try it, or not?", "Comment below with your answer."],
    }
    return bank[stage]


def dialogue_script(topic: dict, hook: dict, duration: int, cast: dict, niche: str, profile_summary: list, wpm: float,
                    revise: dict | None = None) -> dict:
    """Dry run: a fixed exchange in the format's shape (hook first, short performed lines with delivery tags,
    varied timing, numbers, a callback, a loop), trimmed or extended to the duration. Clearly a fixture; the real
    one comes from the writing model."""
    b = cast["b"]["name"]
    body = [("b", "[excited] That's GREAT!", "quick"), ("a", "[flatly] I didn't build it. You did.", "normal"),
            ("b", "[proudly] I wrote four thousand lines.", "quick"), ("b", "You deleted three thousand.", "normal"),
            ("a", "[deadpan] They were bad.", "beat"), ("a", "I just said no a lot.", "normal"),
            ("b", "[cheerfully] Sixty-one times.", "quick"), ("a", "[sighs] You counted?", "normal"),
            ("b", "You said it very clearly.", "normal"), ("a", "Anyone can say no.", "normal"),
            ("b", "[nervously] I can't. I say yes.", "quick"), ("a", "...That's true.", "beat"),
            ("b", "You said no at 1 AM.", "normal"), ("a", "[annoyed] It was the WRONG blue.", "quick"),
            ("b", "Knowing that is the job.", "normal"), ("a", "[sighs] ...Okay. It's good.", "beat"),
            ("b", "[excited] It's great!!", "quick"), ("a", f"[exasperated] The footer's two pixels off, {b}aaa.", "normal")]
    # as many lines as fill about 90% of the length (clips end with the talk, so the lines set the video's length)
    from ..dialogue import estimate_seconds
    full = [{"speaker": "a", "text": hook["say"], "timing": "normal"}] + [{"speaker": s, "text": t, "timing": tm} for s, t, tm in body]
    want = len(full)
    while want > 4 and estimate_seconds(full[:want - 2] + full[-2:], wpm) > 0.92 * duration:
        want -= 1
    lines = full[:want - 2] + full[-2:] if want < len(full) else full
    filler = [("a", "[flatly] No.", "quick"), ("b", "Again?", "quick"), ("a", "Again.", "normal"), ("b", "[cheerfully] Version nine it is.", "normal")]
    k = 0
    while estimate_seconds(lines, wpm) < 0.88 * duration:     # longer videos: more rounds of no before the ending
        s_, t_, tm_ = filler[k % len(filler)]
        lines.insert(len(lines) - 2, {"speaker": s_, "text": t_, "timing": tm_})
        k += 1
    if not any(ln["timing"] == "beat" for ln in lines[1:]):
        lines[-2]["timing"] = "beat"
    # extra AIs in a group episode: each takes over some of b's lines with its own tic
    b_lines = [j for j in range(2, len(lines) - 2) if lines[j]["speaker"] == "b"]
    for k, (s_, tic) in enumerate((("c", "[flatly] Done."), ("d", "[excited] Already did it!"))):
        if (cast.get(s_) or {}).get("enabled"):
            for j in b_lines[k::3][:max(2, len(lines) // 9)]:
                lines[j] = {"speaker": s_, "text": tic, "timing": "quick"}
    while estimate_seconds(lines, wpm) < 0.88 * duration:     # the short tics left room: fill it again
        s_, t_, tm_ = filler[k % len(filler)]
        lines.insert(len(lines) - 2, {"speaker": s_, "text": t_, "timing": tm_})
        k += 1
    # her pose changes on a few of her lines: a hand at her temple, arms crossed, then hands back on the desk
    a_lines = [j for j, ln in enumerate(lines) if ln["speaker"] == "a"]
    for j, pose in zip(a_lines[::max(1, len(a_lines) // 3)], ("temple", "crossed", "rest")):
        lines[j]["pose"] = pose
    clean_last = re.sub(r"\[[^\]]*\]\s*", "", lines[-1]["text"]).lower()
    title = f"{clean_last} what's the pettiest thing you've made your ai redo?"
    return {**FIX, "title": title, "scene": {"set": "office", "look": "night"}, "lines": lines,
            "turn": max(2, round(len(lines) * 0.75)), "button": len(lines), "claims_to_source": []}


def punch_up(lines: list, cast: dict, topic: dict, hook_say: str) -> dict:
    """Dry run: one visible fix (an over-explained line cut down), everything else unchanged."""
    out, notes = [ln["text"] for ln in lines], []
    for k, t in enumerate(out):
        if k and t == "You said it very clearly.":
            out[k] = "[flatly] Very clearly."
            notes.append({"line": k + 1, "state": "H6", "change": "cut the setup words; the two that land stay"})
            break
    return {**FIX, "lines": out, "notes": notes}


def script(topic: dict, hook: dict, duration: int, platform: str, plan: list, profile_summary: list, niche: str,
           revise: Any = None) -> dict:
    n = duration // 10
    say = hook.get("say", "")
    if topic.get("id") == "present-bias" and n == 6:
        loop_word = _loop_word(say)
        clips = [{"index": i, "stage": st, "vo": " ".join(l.replace("{HOOK}", say).replace("{LOOP}", loop_word) for l in lines),
                  "beats": []} for i, (st, lines) in enumerate(PRESENT_BIAS_60)]
        claims = PRESENT_BIAS_CLAIMS
        mistake = {"clip": 3, "description": "Visual only: the figure counts coins 'one, two, four' on its fingers "
                                             "while three coins are visible. Never in the narration."}
    else:
        clips = []
        for i in range(n):
            st = _stage_for(i, n)
            lines = _filler(st, topic.get("title", "this").lower(), i)
            if i == 0:
                lines = [say] + lines[1:]
            clips.append({"index": i, "stage": st, "vo": " ".join(lines), "beats": []})
        first_word = next((w for w in re.findall(r"[a-z]{5,}", say.lower())), "this")
        clips[-1]["vo"] += f" Remember: {first_word}."
        loop_word, claims, mistake = first_word, [], None
    # tag planned beats onto clips so the UI can show them
    for b in plan:
        if 0 <= b.get("clip", -1) < len(clips):
            clips[b["clip"]]["beats"].append(b["type"])
    return {**FIX, "title": topic.get("title", "Untitled"), "clips": clips, "loop_word": loop_word,
            "ask": "Comment: would you automate it, or trust yourself?", "mistake": mistake,
            "claims_to_source": claims}


def _loop_word(say: str) -> str:
    """The loop line echoes the hook's most distinctive word (beats.py checks for a shared word)."""
    stop = {"your", "you're", "thinks", "think", "every", "always", "nobody", "tells", "why", "does", "stop", "for", "the"}
    words = [w.strip(".,?!").lower() for w in say.split()]
    cands = [w for w in words if len(w) > 3 and w not in stop]
    return max(cands, key=len) if cands else words[-1]


def fill_gaps(lines: list, hook_say: str, feedback: str = "") -> dict:
    """Dry run: drop the gap and its leading preposition-free phrase in a deterministic, readable way."""
    import re
    out = []
    for ln in lines:
        vo = re.sub(r"\s*\{\{[^{}]*\}\}", " more than you think", ln["vo"])
        out.append({"clip": ln["clip"], "vo": re.sub(r"\s+", " ", vo).replace(" .", ".").strip()})
    return {**FIX, "lines": out}


def structural_rewrite(text: str, flags: list) -> dict:
    return {**FIX, "text": text}


# ---- direction ------------------------------------------------------------------------------

PRESENT_BIAS_SCENES = [
    ("Mid-stride, the figure hands a glowing coin to a faceless twin standing slightly behind it; the twin walks off toward the top of the frame.",
     "Fast push-in from a high angle; coin trails electric blue; hard cut on 'tonight'.", "a card tap flashes vivid red; the twin's outline flickers"),
    ("The figure flexes in front of a piggy bank; a cracked mirror shows an older, blurry version of the figure that will not come into focus.",
     "Vertical tilt from the bank up to the mirror; rack focus fails on purpose.", "the mirror image dissolves into a crowd of strangers"),
    ("A tug-of-war over one coin: a near figure (tonight) and a tiny distant figure (future-you). The near figure wins easily.",
     "Snap zoom on the rope at 'catch'; palette flips to vivid red for one beat (pattern interrupt).", "the coin lands in a takeout bag"),
    ("Two megaphones: one huge right next to the figure, one tiny on a far hill. The figure counts coins on its fingers.",
     "Lateral dolly between the megaphones; sound-wave rings ripple outward.", "the far megaphone's whisper becomes a dot of warm gold"),
    ("The figure installs a simple pipe from a paycheck envelope (icon-only) straight into a vault before reaching its own pocket.",
     "Crane up as coins flow on their own; warm gold accent appears for the first time.", "the vault door clicks shut"),
    ("The figure stands between two paths: an automatic conveyor and a tightrope. The faceless twin from clip 1 waves from the far end.",
     "Pull back to a wide; hold on the choice for the question; loop back to clip 1's hand-off pose.", "the twin raises a coin: the same pose as frame 0"),
]


def phase_a(title: str, clips: list, ratio: str, duration: int, style: str, theme: str, annotations: list,
            voice_pref: str, revision_note: str = "") -> dict:
    sample = len(clips) == 6 and "stranger" in " ".join(c["vo"] for c in clips).lower()
    rows = []
    for c in clips:
        i = c["index"]
        scene, motion, bgm = (PRESENT_BIAS_SCENES[i] if sample else
                              (f"The figure acts out clip {i + 1} ({c['stage']}) with one oversized prop.",
                               "Push in, then a cut on the stressed word.", "synced SFX on the action"))
        marks = [a["type"] for a in annotations if a.get("clip") == i]
        rows.append({"clip": i + 1, "time": f"{i * 10}-{i * 10 + 10}s", "purpose": c["stage"], "scene": scene,
                     "motion": motion + (f" Blueprint: {', '.join(marks)}." if marks else ""), "vo": c["vo"],
                     "bgm": "quiet thoughtful piano with soft ambient synth; " + bgm})
    voice = "Adult male, General American, warm clean baritone, steady pace, close dry studio (accepted male profile)."
    palette = [{"color": "vivid red", "meaning": "cost and danger"}, {"color": "electric blue", "meaning": "future-you"},
               {"color": "warm gold", "meaning": "reward, saved money"}]
    md = [f"# Phase A - {title}", "", "_Dry-run fixture standing in for the directing-stickman-videos skill._", "",
          f"**Ratio / duration / style:** {ratio}, {duration}s ({len(clips)} clips), Style {style} {theme if style == '1' else ''}",
          f"**Narrator:** {voice}", "**Accents:** " + "; ".join(f"{p['color']} = {p['meaning']}" for p in palette),
          "**BGM:** quiet thoughtful piano and soft ambient synth, one motif throughout.",
          f"**Composition:** {'vertical depth, stacked motion, interface-safe middle band' if ratio == '9:16' else 'left-centre-right staging, lateral tracking'}.",
          "", "| Time | Purpose | Scene | Motion / camera / blueprint | English VO | BGM / SFX |", "|---|---|---|---|---|---|"]
    md += [f"| {r['time']} | {r['purpose']} | {r['scene']} | {r['motion']} | {r['vo']} | {r['bgm']} |" for r in rows]
    if revision_note:
        md += ["", f"_Revision note applied: {revision_note}_"]
    md += ["", "Approve this proposal, revise a named row, or change a global setting."]
    hook_card = "FUTURE YOU?" if sample else "WATCH THIS"
    return {**FIX, "markdown": "\n".join(md), "voice_profile": voice, "palette": palette, "rows": rows,
            "overlays": [{"clip": 1, "text": hook_card, "placement": "top safe band, frame 0 to 2.4 s"}],
            "hook_card": hook_card}


def phase_b(phase_a_md: str, rows: list, ratio: str, duration: int, style: str, theme: str, approval: dict,
            app_inserts_blocks: bool = False) -> dict:
    anchor = anchor_for(style if style != "3" else "1", theme)
    voice = male_voice_block()
    env = ("Flat, uniform, pitch-black canvas with pure white line art." if theme == "dark"
           else "Flat, uniform, digitally pure-white canvas with no textures, gradients, shading or 3D depth.")
    comp = ("Use foreground/background depth, vertical reveals and stacked motion; keep the middle band clean for overlays."
            if ratio == "9:16" else "Stage action across left, centre and right with lateral tracking and negative space.")
    prompts = []
    for k, r in enumerate(rows):
        nxt = rows[k + 1]["scene"].split(";")[0] if k + 1 < len(rows) else "a settled hold that matches the first frame of clip 1"
        text = "\n".join([
            f"Create an approximately 10-second {ratio} 2D kinetic motion-graphics clip targeting 720p at 24 FPS with synchronized audio.",
            env, anchor,
            "Accents: vivid red for cost, electric blue for future-you, warm gold for reward; accents only on props and graphics, never on the figure.",
            comp,
            f"First frame: {'inherit the final pose of the previous clip' if k else 'already mid-action'}. Scene: {r['scene']}",
            f"[0-3s] establish the premise with a concrete action. [3-7s] escalate: {r['motion']} [7-10s] payoff and outgoing motion.",
            f'Audio-only dialogue, exactly once: "{r["vo"]}" Audio voiceover only, strictly no speech bubbles, no dialogue boxes. Do not display or transcribe the dialogue.',
            voice,
            ("Audio: Voiceover clearly audible over quiet, thoughtful piano and subtle soft ambient synth, building gentle optimistic momentum."
             if k == 0 else "Audio: Voiceover seamlessly continues the identical quiet, thoughtful piano and subtle soft ambient synth from clip 1, maintaining identical tempo, instrumentation, and optimistic narrative momentum. Synchronized crisp SFX on physical actions."),
            f"Final frame: hand off to the next clip: {nxt}.",
            "Do not generate photorealism, 3D rendering, extra limbs, changing line weight, unintended characters, visible words, letters, numbers, captions, subtitles, logos or watermarks. Do not alter, omit, repeat, reorder or add dialogue.",
        ])
        prompts.append({"clip": r["clip"], "text": text})
    return {**FIX, "global_block": f"{len(rows)} clips, {ratio}, Style {style} {theme}; anchor and voice block repeated verbatim in every prompt.",
            "character_anchor": anchor, "voice_block": voice, "prompts": prompts,
            "stitching_guide": "Cut each clip on its final hand-off pose; 4-frame audio crossfade; inspect joins.",
            "audio_note": "Compare clips by listening; prompt repetition is not audio certification."}


# ---- packaging and learn --------------------------------------------------------------------

def package(title: str, narration: str, topic: dict, hook: dict, duration: int, platforms: list, chapters: list,
            actual_seconds: float | None = None, ratio: str = "9:16", look: str = "") -> dict:
    t = title
    titles = [t, "Your Brain Thinks Future-You Is a Stranger", "Why Saving Feels Like Giving Money Away",
              "The Real Reason Willpower Fails at Saving", "Stop Blaming Willpower for Your Savings",
              "Present Bias, Explained With Stick Figures", "Why Tonight Always Beats Future-You",
              "The One Setting That Saves for You", "Future-You Is Paying for Tonight", "Thaler's Fix for Present Bias"] \
        if topic.get("id") == "present-bias" else [t] + [f"{t} (option {k})" for k in range(2, 11)]
    return {**FIX, "titles": titles, "thumbnail_text": ["NOT YOU?", "FUTURE STRANGER", "WHO PAYS"],
            "thumbnail_brief": "White stick figure handing a gold coin to a faceless blue twin; pitch-black background; two words max, top-left.",
            "description": f"{hook.get('say', t)} Here's why your brain does it, and the one change that fixes it without willpower.\n\n"
                           "Sources to check before publishing are listed in the project notes.",
            "tags": ["present bias", "behavioral finance", "saving money", "money psychology", "Save More Tomorrow"],
            "queries": ["why can't I save money", "present bias explained", "how to save money automatically"],
            "chapter_titles": [], "ig_caption": "Would you automate it, or trust yourself? Comment AUTO.\n\n"
                                               "Present bias makes tonight louder than future-you. Saving money gets easier when you remove the choice on payday.\n\n"
                                               "#moneypsychology #behavioralfinance #savingmoney",
            "ig_keywords": ["present bias", "saving money"], "cutdowns": [],
            "pinned_comment": "Be honest: which one are you, the one who saves or the one who says 'next month'?",
            "cover_prompt": (f"{'Vertical 9:16 cover, 1080x1920' if ratio == '9:16' else 'Horizontal 16:9 thumbnail, 1280x720'}: "
                             f"a frame from the video, {look or 'the main character centred'}, a deadpan face, the cover text "
                             "\"NOT YOU?\" in bold white with a dark outline in the middle third; no logos, no watermark.")}


def package_part(part: str, previous: str, note: str, title: str, narration: str, seconds: float, ratio: str,
                 look: str = "") -> dict:
    """Dry run: a visibly new version of one package piece."""
    return {**FIX, "text": f"(new {part.replace('_', ' ')}) {title}" + (f" - {note}" if note else "")}


def learn_read(retention: Any, ig_insights: str, plan: list, duration: float) -> dict:
    adjustments = []
    for c in (retention or {}).get("cliffs", []):
        at = c.get("at_seconds")
        if at is None:
            continue
        pct = 100 * at / duration
        nearest = min(plan, key=lambda b: abs(b["pct"] - pct)) if plan else None
        if nearest and 0 <= nearest["pct"] - pct <= 8 and nearest["type"] in ("rehook-cadence", "stakes-line", "payoff-timing"):
            adjustments.append({"type": nearest["type"], "shift_pct": round(-(nearest["pct"] - pct) - 2, 1),
                                "reason": f"cliff at {pct:.0f}% just before the planned {nearest['type']} at {nearest['pct']:.0f}%"})
    leak = (retention or {}).get("hook_leak")
    return {**FIX, "biggest_leak": f"hook leak {leak}%" if leak is not None else "no retention file",
            "change": "Tighten the first line; land the stakes earlier." if leak and leak >= 25 else "Hook is healthy; look at packaging.",
            "ig_findings": ["dry run: paste real insights for an ig-audit read"] if ig_insights else [],
            "adjustments": adjustments}


def scene_plan(clip: int, count: int, row: dict, vo: str, style: str, theme: str, ratio: str, duration: float,
               talk: list, catalog: dict, draft: dict, feedback: str = "", assets: list | None = None) -> dict:
    """Dry run: the keyword planner's draft, unchanged, with a note saying so."""
    keep = {k: draft[k] for k in ("mood", "actors", "props", "panels", "badges", "camera", "transition") if k in draft}
    return {**FIX, **keep, "props": keep.get("props", []), "notes": "dry-run fixture: the keyword plan as drafted"}


def draw_prop(name: str, describe: str, style: str, catalog: dict, feedback: str = "") -> dict:
    """Dry run: a simple, deterministic stand-in (a stacked totem whose shape comes from the name)."""
    h = sum(ord(c) for c in name)
    shapes = ["box", "ico", "cylinder", "cone", "sphere", "pyramid"]
    parts = [{"shape": "cylinder", "size": [0.18, 0.2, 0.08], "pos": [0, 0.04, 0], "color": "dark"}]
    y = 0.08
    for k in range(3):
        sh = shapes[(h + k) % len(shapes)]
        size = {"box": [0.26, 0.18, 0.2], "ico": [0.12], "cylinder": [0.1, 0.12, 0.18], "cone": [0.13, 0.22],
                "sphere": [0.11], "pyramid": [0.13, 0.2]}[sh]
        y += 0.11
        parts.append({"shape": sh, "size": size, "pos": [0, y, 0], "color": ["accent", "card", "gold"][k],
                      **({"motion": {"type": "bob", "amount": 0.02, "speed": 0.7}, "name": "top"} if k == 2 else {})})
        y += 0.09
    return {**FIX, "name": name, "height": 0.6, "parts": parts, "notes": "dry-run fixture: a placeholder totem"}
