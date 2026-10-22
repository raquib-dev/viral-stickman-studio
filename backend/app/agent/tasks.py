"""Task builders: one prompt + JSON schema per skill call. Prompts name the vendored skill to use,
pass the repo-local voice files, and say exactly what to return. Context dicts are also what the
dry-run fixture agent receives."""
from __future__ import annotations

import json
from typing import Any

from .runner import AgentTask

VOICE_YT = "config/voice/youtube.md"
VOICE_IG = "config/voice/instagram.md"

STR = {"type": "string"}
NUM = {"type": "number"}
INT = {"type": "integer"}


def _obj(props: dict, required: list[str] | None = None) -> dict:
    return {"type": "object", "properties": props, "required": required or list(props), "additionalProperties": True}


def _arr(items: dict, min_items: int = 0) -> dict:
    return {"type": "array", "items": items, "minItems": min_items}


def _j(x: Any) -> str:
    return json.dumps(x, indent=1, ensure_ascii=False)


# ---- niche ----------------------------------------------------------------------------------

def voice_draft(platform: str, transcripts: list[str], niche: str) -> AgentTask:
    skill, path = ("yt-script", VOICE_YT) if platform == "youtube" else ("ig-reel", VOICE_IG)
    prompt = f"""Use the `{skill}` skill's voice-profile step. The user gave three of their own {platform} videos
(transcripts below). Infer their voice and write a complete voice.md following the template currently at
{path} (read it first). Do not invent results, numbers or claims; leave fields you cannot infer as
`{{{{your answer}}}}`. Niche: {niche}.

TRANSCRIPTS:
{_j(transcripts)}

Return {{"markdown": "<the full voice.md>"}}."""
    return AgentTask("voice_draft", prompt, _obj({"markdown": STR}), [skill], "research",
                     {"platform": platform, "transcripts": transcripts, "niche": niche})


# ---- discovery ------------------------------------------------------------------------------

def discovery_read(platform: str, swipe: dict, niche: str) -> AgentTask:
    skill = "yt-viral" if platform == "youtube" else "ig-viral"
    prompt = f"""Use the `{skill}` skill's "Reading the output" guidance on this swipe.py JSON for the niche
"{niche}". Report the top five with multiples and formula, the ONE structural thing they share, and which
the user could make this week. Say the sample size and your confidence in plain words. The formula label
is a judgement about the words, not why the video worked: say so.

SWIPE JSON:
{_j(swipe)[:12000]}"""
    schema = _obj({"top": _arr(_obj({"title": STR, "multiple": NUM, "formula": STR, "note": STR})),
                   "shared_structure": STR, "makeable": STR, "confidence": STR})
    return AgentTask("discovery_read", prompt, schema, [skill], "research",
                     {"platform": platform, "swipe": swipe, "niche": niche})


# ---- patterns -------------------------------------------------------------------------------

def label_llm(video_id: str, timed_text: str, questions: dict[str, str], duration: float) -> AgentTask:
    prompt = f"""Label this transcript against the virality blueprint (docs/research/virality-blueprint.json).
Answer each question with zero or more items {{"t": seconds, "quote": "...", "confidence": 0-1}}. Use the
[seconds] markers for t. Only label what the words show; these are judgements about the words, not
proof of why the video performed. Duration: {duration:.1f}s.

QUESTIONS (by blueprint type):
{_j(questions)}

TRANSCRIPT:
{timed_text[:16000]}"""
    item = _obj({"t": NUM, "quote": STR, "confidence": NUM}, ["t", "quote"])
    schema = _obj({"answers": {"type": "object", "additionalProperties": _arr(item)}})
    return AgentTask("label_llm", prompt, schema, [], "labeling",
                     {"video_id": video_id, "timed_text": timed_text, "questions": questions, "duration": duration})


# ---- topics ---------------------------------------------------------------------------------

def topic_candidates(niche: str, subtopics: list[str], outliers: list[dict], profile_summary: list[str],
                     n: int = 8) -> AgentTask:
    prompt = f"""Generate {n} candidate video topics for the niche "{niche}" (sub-topics: {', '.join(subtopics) or '-'}),
using the `yt-viral` and `ig-viral` skills' idea of re-skinning what outliers prove, plus gaps: topics with
demand where few good videos exist. For each, rate stick-figure fit 1-5 with this rubric: a concrete
physical metaphor exists; no real people's faces needed; does not depend on on-screen text or precise
charts (diffusion garbles them); one idea per video. Also rate niche fit 1-5. Do not invent statistics;
a demand note may only reference the outliers below.

OUTLIERS (multiple over own-channel median; synthetic rows are labelled):
{_j(outliers[:40])}

NICHE PATTERN PROFILE:
{_j(profile_summary)}"""
    cand = _obj({"id": STR, "title": STR, "angle": STR, "keywords": _arr(STR), "stickman_fit": NUM,
                 "stickman_reason": STR, "niche_rating": NUM, "demand_note": STR})
    return AgentTask("topic_candidates", prompt, _obj({"candidates": _arr(cand, 3)}), ["yt-viral", "ig-viral"],
                     "research", {"niche": niche, "subtopics": subtopics, "outliers": outliers,
                                  "profile_summary": profile_summary, "n": n})


# ---- hooks and script -----------------------------------------------------------------------

def hooks(topic: dict, niche: str, platform: str, profile_summary: list[str], n: int = 5) -> AgentTask:
    skill, voice = ("ig-reel", VOICE_IG) if platform in ("reels", "shorts") else ("yt-script", VOICE_YT)
    prompt = f"""Use the `{skill}` skill (and `yt-script` hooks.json as a second formula set) to write {n} hooks
for this topic, from at least three DIFFERENT formulas. Read the voice profile at {voice}. For each hook
give the papercut-style layers: SAY (spoken line, opens the gap within ~10 words, lands within 3 seconds),
WRITE (2-5 word on-screen card that does not repeat SAY's words), SHOW (frame 0, already mid-action, a
stick-figure moment), ALIGN (the one idea all three point at). No greeting, no "in this video", no
invented numbers ({{{{your number}}}} if needed). Do not score them; the app runs both hookscore.py tools.

TOPIC: {_j(topic)}
NICHE: {niche}
NICHE PATTERN PROFILE: {_j(profile_summary)}"""
    h = _obj({"id": STR, "say": STR, "write": STR, "show": STR, "align": STR, "formula": STR, "why": STR})
    return AgentTask("hooks", prompt, _obj({"hooks": _arr(h, 3)}), [skill, "yt-script"], "direction",
                     {"topic": topic, "niche": niche, "platform": platform, "profile_summary": profile_summary, "n": n})


def script(topic: dict, hook: dict, duration: int, platform: str, plan: list[dict], profile_summary: list[str],
           niche: str, words_per_clip: tuple[int, int] = (18, 25), revise: dict | None = None) -> AgentTask:
    n_clips = duration // 10
    skill = "ig-reel" if platform in ("reels", "shorts") else "yt-script"
    revision = ""
    if revise:
        revision = f"""
REVISION: fix every flag below and keep everything else. Previous clips:
{_j(revise['clips'])}
FLAGS (beats.py / detect.py / app checks):
{_j(revise['flags'])}"""
    prompt = f"""Use the `{skill}` skill's script flow and the directing-stickman-videos 5-stage arc
(Golden Hook -> Disrupting Assumptions -> Unveiling Insider Secrets -> Ultimate Truth -> Elevation &
Discussion) to write the narration for a {duration}s video = {n_clips} clips of ~10s each.
- Each clip's VO is {words_per_clip[0]}-{words_per_clip[1]} spoken words (Omni speaks it inside the clip; shorten rather than speed up).
- Clip 1 opens with the approved hook's SAY line verbatim.
- Place beats at the planned times below (from the niche pattern profile, else blueprint defaults):
  stakes line, re-hooks ("but here's the catch"), payoff, exactly ONE ask, and the last line repeats a word from the hook (loop).
- If a deliberate mistake is planned, it must be visual or trivial only, never in a fact or number; describe it in "mistake".
- Second person, contractions, short lines. Never invent statistics; use {{{{your number}}}} where a figure is needed.
- Read the voice profile at {"config/voice/instagram.md" if skill == "ig-reel" else "config/voice/youtube.md"}.

TOPIC: {_j(topic)}
APPROVED HOOK: {_j(hook)}
NICHE: {niche}
PLANNED BEATS: {_j(plan)}
NICHE PROFILE: {_j(profile_summary)}{revision}"""
    clip = _obj({"index": INT, "stage": {"enum": ["golden-hook", "disrupting-assumptions", "insider-secrets",
                                                   "ultimate-truth", "elevation-discussion"]},
                 "vo": STR, "beats": _arr(STR)})
    schema = _obj({"title": STR, "clips": {**_arr(clip, n_clips), "maxItems": n_clips}, "loop_word": STR,
                   "ask": STR, "mistake": {"type": ["object", "null"]}, "claims_to_source": _arr(STR)})
    return AgentTask("script", prompt, schema, [skill, "directing-stickman-videos"], "direction",
                     {"topic": topic, "hook": hook, "duration": duration, "platform": platform, "plan": plan,
                      "profile_summary": profile_summary, "niche": niche, "revise": revise})


def structural_rewrite(text: str, flags: list) -> AgentTask:
    prompt = f"""Use the `ig-human` skill. humanize.py already fixed characters and the slop lexicon. Rewrite ONLY
the structural tells flagged below by hand, keeping meaning, line breaks and the clip structure (one line
per clip). Keep every line within its word budget. Return the full text.

FLAGS: {_j(flags)}

TEXT:
{text}"""
    return AgentTask("structural_rewrite", prompt, _obj({"text": STR}), ["ig-human"], "labeling",
                     {"text": text, "flags": flags})


# ---- direction ------------------------------------------------------------------------------

def phase_a(title: str, clips: list[dict], ratio: str, duration: int, style: str, theme: str,
            annotations: list[dict], voice_pref: str, revision_note: str = "") -> AgentTask:
    prompt = f"""Use the `directing-stickman-videos` skill. Setup is complete (do not ask again):
- source: the approved narration below (keep it word for word unless a clip exceeds 25 words)
- aspect ratio: {ratio}
- target duration: {duration}s ({duration // 10} clips)
- visual style: Style {style}{' ' + theme if style == '1' else ''}
- narrator preference: {voice_pref}
Produce PHASE A ONLY (the director's proposal) following references/storyboard-template.md, in English.
Do NOT produce Phase B prompts: approval happens in the app. Respect these timeline annotations from the
virality blueprint / niche profile (re-hook here, pattern interrupt here, etc.) when staging each row:
{_j(annotations)}
{('REVISION REQUESTED BY THE USER: ' + revision_note) if revision_note else ''}

TITLE: {title}
NARRATION BY CLIP:
{_j(clips)}"""
    row = _obj({"clip": INT, "time": STR, "purpose": STR, "scene": STR, "motion": STR, "vo": STR, "bgm": STR})
    schema = _obj({"markdown": STR, "voice_profile": STR, "palette": _arr(_obj({"color": STR, "meaning": STR})),
                   "rows": _arr(row, 1), "overlays": _arr(_obj({"clip": INT, "text": STR, "placement": STR})),
                   "hook_card": STR})
    return AgentTask("phase_a", prompt, schema, ["directing-stickman-videos"], "direction",
                     {"title": title, "clips": clips, "ratio": ratio, "duration": duration, "style": style,
                      "theme": theme, "annotations": annotations, "voice_pref": voice_pref,
                      "revision_note": revision_note})


APP_BLOCKS = """The app inserts the two frozen blocks itself, copied verbatim from the skill's reference files.
Do NOT write the character anchor or the voice block yourself. In every prompt, put a line containing only
{{ANCHOR}} where the character anchor belongs (right after the canvas/environment line) and a line containing
only {{VOICE}} where the voice block belongs (right after the dialogue line). Return character_anchor and
voice_block as empty strings."""


def phase_b(phase_a_md: str, rows: list[dict], ratio: str, duration: int, style: str, theme: str,
            approval: dict, app_inserts_blocks: bool = False) -> AgentTask:
    blocks = APP_BLOCKS if app_inserts_blocks else """Repeat the frozen character anchor and the complete
frozen voice block VERBATIM in every prompt; return those two blocks separately as character_anchor and
voice_block so the app can verify them."""
    prompt = f"""Use the `directing-stickman-videos` skill. The user APPROVED the current Phase A below
(approval record: {_j(approval)}). Now read references/omni-flash-prompt-contract.md and produce PHASE B:
the global continuity block, exactly {duration // 10} standalone prompts (one per clip, in order), the
stitching guide and the voice/music continuity note. {blocks}
No hex/RGB/Pantone colours, no visible text in generated clips.
Ratio {ratio}, Style {style}{' ' + theme if style == '1' else ''}.

APPROVED PHASE A:
{phase_a_md}"""
    schema = _obj({"global_block": STR, "character_anchor": STR, "voice_block": STR,
                   "prompts": {**_arr(_obj({"clip": INT, "text": STR}), duration // 10), "maxItems": duration // 10},
                   "stitching_guide": STR, "audio_note": STR})
    return AgentTask("phase_b", prompt, schema, ["directing-stickman-videos"], "direction",
                     {"phase_a_md": phase_a_md, "rows": rows, "ratio": ratio, "duration": duration, "style": style,
                      "theme": theme, "approval": approval})


# ---- packaging and learn --------------------------------------------------------------------

def package(title: str, narration: str, topic: dict, hook: dict, duration: int, platforms: list[str],
            chapters: list[dict]) -> AgentTask:
    prompt = f"""Package this finished video. Use these skills in order and follow their rules:
- `yt-package`: ten titles (the app lints them with title.py) and three thumbnail texts of at most 3 words that do not repeat the title, plus a thumbnail brief.
- `yt-seo`: the description (first two lines are the search snippet), up to 15 disambiguation tags, and the three queries this should win.
- `yt-chapters`: retitle the draft chapters below as 3-5 word promises (only if duration >= 60s and long-form).
- `ig-caption`: a Job A caption (the reel carries the hook), one ask, up to 5 specific hashtags, 2-3 search phrases.
- `yt-shorts` / `ig-repurpose`: cut-down suggestions (only meaningful for long-form; return [] for a short).
Voice: {VOICE_YT} and {VOICE_IG}. Never invent numbers. Never publish anything.

TITLE (working): {title}
PLATFORMS: {platforms}
DURATION: {duration}s
TOPIC: {_j(topic)}
HOOK: {_j(hook)}
NARRATION:
{narration}
DRAFT CHAPTERS (chapters.py): {_j(chapters)}"""
    schema = _obj({"titles": _arr(STR, 3), "thumbnail_text": _arr(STR, 1), "thumbnail_brief": STR,
                   "description": STR, "tags": _arr(STR), "queries": _arr(STR), "chapter_titles": _arr(STR),
                   "ig_caption": STR, "ig_keywords": _arr(STR),
                   "cutdowns": _arr(_obj({"start": NUM, "end": NUM, "first_line": STR, "on_screen": STR, "loop_point": STR}))})
    return AgentTask("package", prompt, schema, ["yt-package", "yt-seo", "yt-chapters", "ig-caption", "yt-shorts",
                                                 "ig-repurpose"], "direction",
                     {"title": title, "narration": narration, "topic": topic, "hook": hook, "duration": duration,
                      "platforms": platforms, "chapters": chapters})


def learn_read(retention: dict | None, ig_insights: str, plan: list[dict], duration: float) -> AgentTask:
    prompt = f"""Use `yt-retention` (on retention.py's JSON) and `ig-audit` (on the pasted Instagram insights).
Name the single biggest leak and one change for it. Then map each retention cliff to the nearest planned
beat below and propose shifts for the niche pattern profile, as {{"type": <blueprint type>, "shift_pct":
<negative = earlier>, "reason": "..."}}. Only propose a shift when a cliff sits within 8% before a planned
beat. Be honest about sample size (one video is one data point).

RETENTION (retention.py): {_j(retention)}
INSTAGRAM INSIGHTS (pasted): {ig_insights[:6000]}
PLANNED BEATS: {_j(plan)}
DURATION: {duration}s"""
    adj = _obj({"type": STR, "shift_pct": NUM, "reason": STR})
    schema = _obj({"biggest_leak": STR, "change": STR, "ig_findings": _arr(STR), "adjustments": _arr(adj)})
    return AgentTask("learn_read", prompt, schema, ["yt-retention", "ig-audit"], "research",
                     {"retention": retention, "ig_insights": ig_insights, "plan": plan, "duration": duration})


# ---- 3D scene planning (local-threejs renderer) ------------------------------------------------

def scene_plan(clip: int, count: int, row: dict, vo: str, style: str, theme: str, ratio: str, duration: float,
               talk: list, catalog: dict, draft: dict, feedback: str = "") -> AgentTask:
    lists = {k: catalog[k] for k in ("moods", "clips", "expressions", "gestures", "props", "hats", "shots", "transitions")}
    vertical = ratio == "9:16"
    prompt = f"""Following the director's approved Phase A intent (one clear action per beat, continuity between
clips), stage clip {clip} of {count} as a 3D scene for the app's three.js renderer: a low-poly 3D stickman in
style "{style}" ({theme}), {ratio}, {duration:.0f} s. You are writing DATA for a renderer, not code, not a video prompt.

THE BEAT (approved Phase A row): {_j(row)}
VOICEOVER (spoken {talk[0]:.1f}-{talk[1]:.1f} s): "{vo}"

Improve the DRAFT below (a keyword planner's guess) so the scene shows what this line means:
- mood: the colour of the beat from what it says; if the line turns ("but...", "until..."), add a second mood at
  the second where the turn is spoken (inside the voiceover window).
- 1-3 gestures timed to the words they illustrate; a facial expression arc; optional clip ("anim") moments.
- at most 2 props that are concrete things the line mentions or implies; a prop can be held (hold) or placed (pos).
- optional: one "note" panel (title + up to 3 lines of max 28 characters, using the voiceover's own words) or, for
  software topics only, one "code" panel (title is a file name, up to 3 short lines of plausible code).
- a badge only if the voiceover says a number; its text must use that exact number.
- camera: 2-4 keys using named shots that serve the beat (reveal wide, punch in on the payoff).
- a second actor (id "other") only if the line is about another person; then use a two_shot.
Frame layout ({'vertical 9:16' if vertical else 'wide 16:9'}, metres, the hero stands at x=0, z=0, faces +z):
  props beside the hero x={'±0.5..0.65' if vertical else '±0.8..1.2'}, on the floor y=0 or at chest height y=1.1-1.5, z=-0.3..0.3;
  panels y=1.9-2.4, z=-0.5..-1.5, width <= {'1.5' if vertical else '2.2'}; badges y about 2.15, z -0.4.
Times are seconds inside 0-{duration:.0f}. Use ONLY these names: {_j(lists)}
Never invent a statistic: no number may appear on screen unless the voiceover says it. Keep "notes" to one sentence
explaining your staging choice.
{('PREVIOUS ATTEMPT WAS REJECTED: ' + feedback) if feedback else ''}
DRAFT:
{_j(draft)}"""
    obj = {"type": "object", "additionalProperties": True}
    schema = _obj({"mood": _arr(_obj({"t": NUM, "mood": STR}), 1),
                   "actors": _arr({**obj, "required": ["id"], "properties": {"id": STR}}, 1),
                   "props": _arr(obj), "panels": _arr(obj), "badges": _arr(obj),
                   "camera": _arr({**obj, "required": ["t"], "properties": {"t": NUM}}, 1),
                   "transition": obj, "notes": STR},
                  ["mood", "actors", "camera", "notes"])
    # no skill attached: the Phase A row already carries the director's intent, and the skill text would
    # crowd a local model's context (the plan itself needs the room)
    return AgentTask("scene_plan", prompt, schema, [], "direction",
                     {"clip": clip, "count": count, "row": row, "vo": vo, "style": style, "theme": theme, "ratio": ratio,
                      "duration": duration, "talk": talk, "catalog": catalog, "draft": draft, "feedback": feedback})
