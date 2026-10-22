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

def hooks(topic: dict, niche: str, platform: str, profile_summary: list[str], n: int = 5, dialogue: dict | None = None) -> AgentTask:
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
    if dialogue:
        prompt += f"""

THIS IS A TWO-CHARACTER DIALOGUE SHORT: SAY is the first line, spoken by {dialogue['a']['name']} ({dialogue['a']['role']}) to
{dialogue['b']['name']} ({dialogue['b']['role']}). Make it a performance, not a sentence: 2-8 words that start in the
middle of a feeling and a situation, so the first second already has tension or a laugh. Write the delivery into
it for an expressive voice: one audio tag in square brackets ([exasperated], [deadpan], [panicked], [whispers]),
stretched letters where a person would draw a word out, CAPS on the one word that lands. For example:
"[exasperated] Claaauude!! The client said it's GREAT." or "[whispers] Don't. Touch. The footer."
Each of the hooks uses a different emotion. WRITE is unused on screen in this format; keep it short anyway."""
    h = _obj({"id": STR, "say": STR, "write": STR, "show": STR, "align": STR, "formula": STR, "why": STR})
    return AgentTask("hooks", prompt, _obj({"hooks": _arr(h, 3)}), [skill, "yt-script"], "direction",
                     {"topic": topic, "niche": niche, "platform": platform, "profile_summary": profile_summary, "n": n,
                      "dialogue": dialogue})


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
- Fill the length: every clip needs its full word count, so the video runs the {duration}s set for it.

{PLAIN_FUNNY}
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


def fill_gaps(lines: list[dict], hook_say: str, feedback: str = "") -> AgentTask:
    """Rewrite narration lines that hold a {{...}} gap (a figure only the creator knows and did not give) so
    they read naturally without it. Never fills in a number."""
    prompt = f"""Use the `ig-human` skill's voice rules. Each narration line below contains a gap such as
{{{{your number}}}}: a figure only the creator knows, which they have not given. Rewrite ONLY these lines so they
read naturally WITHOUT that figure.

Rules:
- No {{{{...}}}} gaps left. Do not add any number, amount, percentage, date or statistic that is not already in
  the line, and do not invent facts. Say it in words that need no figure ("costs you more than you think",
  "a slice of every payday").
- Keep the meaning, the second person, contractions and short sentences. Keep each line between 12 and 25 words
  and within 3 words of its current length.
- If clip 1 is listed, it must still start with the hook exactly: "{hook_say}".
- Return every listed clip, with its clip number.
{('PREVIOUS ATTEMPT WAS REJECTED: ' + feedback) if feedback else ''}
LINES:
{_j(lines)}"""
    return AgentTask("fill_gaps", prompt, _obj({"lines": _arr(_obj({"clip": INT, "vo": STR}, ["clip", "vo"]), 1)}),
                     ["ig-human"], "labeling", {"lines": lines, "hook_say": hook_say, "feedback": feedback})


# ---- direction ------------------------------------------------------------------------------

# every script and caption the app writes: funny for anyone who has used an AI chat, and easy English for viewers
# in every country (many watch in their second language, with captions)
PLAIN_FUNNY = """LANGUAGE AND HUMOUR (for every viewer, not only developers, not only Americans):
- Funny first: every few lines a laugh, from a real situation anyone who has typed into an AI chat knows (it forgets,
  it agrees too fast, it over-helps, it says "Done." and isn't, it apologises and repeats the mistake). The joke is the
  situation and the timing, never a mean remark.
- Plain international English: short, common words a viewer reading captions in their second language knows. No US
  slang or idioms ("ballpark", "touch base", "hit it out of the park", "y'all"), no sports or US TV references, no
  dollar or imperial units unless the topic is about them, dates and times that read anywhere ("at 1 AM", "on day 3").
- Tech words only when the joke needs them, and then explained by the scene or an everyday comparison, so a viewer who
  has never coded still gets it. A developer should still nod at the detail."""

DIALOGUE_RULES = """THE FORMAT: a deadpan comedy short about living with AI tools. A person (character a) sits at her desk with
her AI (character b, a small creature on the desk; in group episodes more AIs, c and d, sit beside it). No narrator:
only they talk, one short line at a time. Hard cuts on every line, so every line must earn its cut. Each line is
sent as written to an expressive voice model (ElevenLabs Eleven v4), so the script carries the acting.

PICK ONE PREMISE TYPE (all the reference reels fit one):
- tender quirk: an AI limitation turned sweet (it forgets every morning and she remembers; mom thinks it's a person)
- explain like I'm five: she bans jargon, the AI explains on a WHITEBOARD with a metaphor, she tests edge cases
  ("What if he brings the wrong dish?" "That's a bug."), it names the concepts; set "classroom"
- team of AIs: several AIs with clashing habits on one task (one asks four questions, one asks none, one starts
  before the brief); uses c and d when the cast has them
- the AI can't do the human thing: a plain pleasure it can't have (it can look at a reel but can't like it)
- credit and work: who really did it, her taste against its output ("she said no sixty-one times")

Rules (an app checks them and sends the script back if one breaks):
1. Line 1 is the approved hook, word for word (with its delivery), said by a. Hooks name the AI and the situation:
   "Claude. My mom thinks you're a person."
2. Lines are short: mostly 2-6 words, never more than 9 (a whiteboard explanation line may run to 16). Use
   one-word punches ("No." "Done." "Eleven." "And?"): at least 2. Write how tired people actually talk.
3. Ping-pong. Nobody has more than 3 lines in a row. With two characters each has at least 30% of the lines; in a
   group a has at least 25% and every AI speaks at least twice.
4. Write the performance into the text, like a human actor would play it:
   - an audio tag in square brackets for the emotion: [deadpan], [flatly], [sighs], [exasperated], [cheerfully],
     [hesitant], [tender], [embarrassed], [excited], [whispers], [nervously], [proudly]. At most 2 per line; at
     least a third of the lines have one. She is mostly dry and flat; the AI is earnest and polite, bright and
     chirpy only in its "assistant mode" ("[cheerfully] Hello! How can I help you today?").
   - stretched letters where a person draws a word out ("Claaauude.", "Nooo."), CAPS on the one word that lands,
     "!!" for a burst.
   - "..." at the START of a line is a beat of hesitation before it ("...We've met.", "...It's complicated."): 3-6
     of these, on the lines that carry the feeling. They show in the captions.
   - at most once, an interruption: a line that stops mid-sentence ("Should it have a") and the next speaker
     barges in.
5. Timing for every line, like real conversation: "quick" (a comeback straight back; about one line in five),
   "normal" (a half-second turn), or "beat" (a sharp look first, about a second; 1-4 of them, before "..." lines
   and where the silence is the joke).
6. Oddly specific in-story numbers make the jokes: "forty times a day", "sixty-one times", "eight of me", "two
   pixels off", "1 AM". At least 2. They are details about these characters, never facts about the world: no
   percentages, studies, research, surveys or averages.
7. A recurring tic or a callback: a later line brings back an earlier phrase with a new meaning ("Quick question."
   three times; "You're absolutely right" turned around).
8. A turn about two thirds in: the line where the meaning flips (she wrote it all down; it deleted the desktop).
   Give its line number as `turn`.
9. The button (the last 1-2 lines): a loop back to the opening, a short reversal by a side character, a self-own,
   or a deadpan cap. It reuses a word or name from the first lines. Give its line number as `button`.
10. Her pose (optional `pose` on her lines, held until changed, set on a cut): rest (hands on the desk), mug (both
   hands round a mug: mornings), phone (reading a phone: messages, reels), crossed (arms crossed: fed up), temple
   (a hand at her temple: tired), palm (an open palm toward an AI: "he's faster"), both (both hands forward: "both
   of you"), finger (a finger raised: assigning jobs). Change it 2-4 times in a video.
11. `scene`: {"set": "office" | "classroom", "look": "morning" | "rain" | "night" | "dusk"}. The window sets the
   mood: morning for tender, rain for cosy or awkward, night for crunch and work, dusk for casual fun. "classroom"
   only for explain-like-I'm-five (two speakers).
12. Classroom only: the AI writes on the whiteboard as it talks. Give those lines a `board` list of items in the
   order they appear: {"op": "title", "text": "What is an API?"} first, then "word" (a jargon word, max 3),
   "strike" (she vetoes: crosses the words out), "figure" (a stick figure with a name), "box" (a labelled box),
   "arrow" (between the last two diagram items), "label" (a "= meaning" under an item, in order). Add "at": a word
   of the line, to show it as that word is said. Keep each text under 20 characters.
13. TITLE: all lowercase, no tags: two short mirrored sentences about the premise, then one question to the viewer
   ("one asks four questions. one asks none. which one are you working with today?"). At most 110 characters.
14. Insider humour for the niche is good (a known quirk of AI tools, a developer's habit), but never mock a real,
   named person, keep it kind, and write new lines: never reuse another creator's script.
15. LENGTH: the finished video runs exactly as long as the lines (clips end when the talking ends), so the line count
   sets the length. Write the number of lines asked for below; a script that is too short makes a short video.

""" + PLAIN_FUNNY


def dialogue_script(topic: dict, hook: dict, duration: int, cast: dict, niche: str, profile_summary: list[str],
                    wpm: float, revise: dict | None = None) -> AgentTask:
    """A dialogue script (speaker-tagged, performed lines with timing, poses and the scene) for dialogue shorts."""
    a, b = cast["a"], cast["b"]
    extra = [s for s in ("c", "d") if (cast.get(s) or {}).get("enabled")]
    who = ["a", "b", *extra]
    from ..dialogue import target_lines
    n_lines = target_lines(duration)
    words_total = round((duration - 2.1 - n_lines[0] * 0.45) * wpm / 60)
    revision = ""
    if revise:
        revision = f"""
REVISION: fix every flag below and keep everything that works. Previous script:
{_j(revise['res'])}
FLAGS:
{_j(revise['flags'])}"""
    extras = "".join(f"- {s} = {cast[s]['name']}: {cast[s]['role']}\n" for s in extra)
    speaker_enum = " | ".join(f'"{s}"' for s in who)
    prompt = f"""Use the `ig-reel` skill's voice rules (and `ig-human` to avoid machine-sounding lines) to write a
{duration}-second dialogue short.
TARGET LENGTH: {duration} s = {n_lines[0]}-{n_lines[1]} lines, about {words_total} spoken words in total (spoken at about
{wpm:.0f} words a minute with half-second turns, in {duration // 10} clips of up to 10 s). Fewer lines make a shorter video.

{DIALOGUE_RULES}

CHARACTERS:
- a = {a['name']}: {a['role']}
- b = {b['name']}: {b['role']}
{extras}
TOPIC: {_j(topic)}
APPROVED HOOK (line 1, character a, word for word): {hook['say']}
NICHE: {niche}
NICHE PATTERN PROFILE: {_j(profile_summary)}
{revision}
Return the lines in order as {{"speaker": {speaker_enum}, "text": "<delivery tags + words>", "timing": "quick"|"normal"|"beat",
"pose": optional, "board": optional}}, plus `scene`, `turn` and `button` (1-based line numbers), the `title`, and
`claims_to_source` (anything a viewer could read as a real-world fact; usually empty)."""
    board_item = _obj({"op": {"type": "string", "enum": ["title", "word", "strike", "figure", "box", "arrow", "label"]},
                       "text": STR, "at": STR}, ["op"])
    line = _obj({"speaker": {"type": "string", "enum": who}, "text": STR,
                 "timing": {"type": "string", "enum": ["quick", "normal", "beat"]},
                 "pose": {"type": "string", "enum": ["rest", "mug", "phone", "crossed", "temple", "palm", "both", "finger"]},
                 "board": _arr(board_item)}, ["speaker", "text", "timing"])
    scene = _obj({"set": {"type": "string", "enum": ["office", "classroom"]},
                  "look": {"type": "string", "enum": ["morning", "rain", "night", "dusk"]}}, ["set", "look"])
    schema = _obj({"title": STR, "scene": scene, "lines": _arr(line, 4), "turn": INT, "button": INT,
                   "claims_to_source": _arr(STR)}, ["title", "scene", "lines", "turn", "button"])
    return AgentTask("dialogue_script", prompt, schema, ["ig-reel", "ig-human"], "direction",
                     {"topic": topic, "hook": hook, "duration": duration, "cast": cast, "niche": niche,
                      "profile_summary": profile_summary, "wpm": wpm, "revise": revise})


def punch_up(lines: list[dict], cast: dict, topic: dict, hook_say: str) -> AgentTask:
    """A punch-up pass on a finished dialogue script: diagnose each joke (joke-engineering) and rewrite only the weak
    ones, keeping every line's speaker, timing, pose and board items, and the hook as line 1."""
    names = {s: cast[s]["name"] for s in cast if isinstance(cast.get(s), dict) and cast[s].get("name")}
    numbered = "\n".join(f"{k + 1}. {names.get(ln['speaker'], ln['speaker'])} ({ln['speaker']}, {ln.get('timing', 'normal')}): {ln['text']}"
                         for k, ln in enumerate(lines))
    prompt = f"""Use the `joke-engineering` skill for a punch-up pass on this dialogue short. Diagnose each punchline
(H1-H6, the nine properties, the irony gradient) and rewrite ONLY the lines whose joke is weak. Most lines stay
exactly as they are; setup lines stay plain.

Keep: the same {len(lines)} lines in the same order, each line's speaker and timing, line 1 word for word (the
approved hook: {hook_say}), delivery tags in square brackets (at most 2 a line), "..." where a beat sits, lines of
2-6 words (never more than 9; a whiteboard explanation up to 16), in-story numbers only (no real-world statistics).

{PLAIN_FUNNY}

CHARACTERS: {_j(names)}
TOPIC: {_j(topic)}
SCRIPT:
{numbered}

Return {{"lines": [the full text of every line, in order, {len(lines)} strings], "notes": [{{"line": <1-based number>,
"state": "H1".."H6", "change": "<what you changed and why, one short sentence>"}} for each line you changed]}}."""
    schema = _obj({"lines": {**_arr(STR, len(lines)), "maxItems": len(lines)},
                   "notes": _arr(_obj({"line": INT, "state": STR, "change": STR}))})
    return AgentTask("punch_up", prompt, schema, ["joke-engineering"], "direction",
                     {"lines": lines, "cast": cast, "topic": topic, "hook_say": hook_say})


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

def _cover_spec(ratio: str) -> str:
    if ratio == "9:16":
        return ("a VERTICAL 9:16 cover, 1080x1920 (YouTube Shorts and Instagram Reels cover). Instagram's profile grid crops "
                "it to the centre square (1080x1080, about 4:5 on newer grids), so the faces and any text sit in the middle "
                "third; keep the top 15% and bottom 25% free of anything important (the app buttons cover them)")
    return ("a HORIZONTAL 16:9 YouTube thumbnail, 1280x720; keep the bottom-right corner clear (the length badge covers "
            "it) and make it read at phone size")


PACKAGE_RULES = """HARD RULES FOR EVERYTHING YOU WRITE HERE:
- Describe only what is in the script below. Never invent events, props, timers, lengths, numbers or results.
- Never state how long the video is unless you use the exact length given (VIDEO LENGTH below).
- No links, URLs or placeholders ("example.com", "[link]", "link in bio") anywhere.
- TIMESTAMPS / CHAPTERS: only when the video is long-form and at least 60 s AND draft chapters are given; then use
  exactly those times. For a short (under 60 s) write no timestamps at all.
- The description of a short: 2-4 short lines (the first line works as the search snippet and the hook), then
  3-5 hashtags on the last line. Nothing else.
- PINNED COMMENT: what the creator posts as the first comment right after publishing, to pin: one short, funny line
  in the creator's voice that invites replies (a question viewers want to answer, or a "tell me yours"), under 200
  characters, no links, no hashtags, at most one emoji.
- COVER PROMPT: one paragraph to paste into an image generator (Midjourney, Ideogram, DALL-E) for {cover}. Describe
  the frame from the video (the characters, the set and the light below), the moment that sells the joke, the facial
  expressions, and the 1-3 word cover text with where it sits and its style (bold, high contrast, readable small).
  Say "no logos, no watermark". Never name a real brand's logo or ask for one."""


def package(title: str, narration: str, topic: dict, hook: dict, duration: int, platforms: list[str],
            chapters: list[dict], actual_seconds: float | None = None, ratio: str = "9:16", look: str = "") -> AgentTask:
    seconds = actual_seconds or duration
    short = seconds < 60
    prompt = f"""Package this finished video. Use these skills in order and follow their rules:
- `yt-package`: ten titles (the app lints them with title.py) and three thumbnail texts of at most 3 words that do not repeat the title, plus a thumbnail brief.
- `yt-seo`: the description (first line is the search snippet), up to 15 disambiguation tags, and the three queries this should win.
- `yt-chapters`: {"none: this is a short, return chapter_titles []" if short or not chapters else "retitle the draft chapters below as 3-5 word promises"}.
- `ig-caption`: a Job A caption (the reel carries the hook), one ask, up to 5 specific hashtags, 2-3 search phrases.
- `yt-shorts` / `ig-repurpose`: cut-down suggestions (only meaningful for long-form; return [] for a short).
Also write the pinned comment and the cover prompt.
Voice: {VOICE_YT} and {VOICE_IG}. Never invent numbers. Never publish anything.

{PACKAGE_RULES.format(cover=_cover_spec(ratio))}

{PLAIN_FUNNY}

TITLE (working): {title}
PLATFORMS: {platforms}
VIDEO LENGTH: {seconds:.0f} s ({"a short" if short else "long-form"}), aspect ratio {ratio}
LOOK OF THE VIDEO: {look or "see the script"}
TOPIC: {_j(topic)}
HOOK: {_j(hook)}
SCRIPT (what is actually said, in order):
{narration}
DRAFT CHAPTERS (chapters.py): {_j([] if short else chapters)}"""
    schema = _obj({"titles": _arr(STR, 3), "thumbnail_text": _arr(STR, 1), "thumbnail_brief": STR,
                   "description": STR, "tags": _arr(STR), "queries": _arr(STR), "chapter_titles": _arr(STR),
                   "ig_caption": STR, "ig_keywords": _arr(STR), "pinned_comment": STR, "cover_prompt": STR,
                   "cutdowns": _arr(_obj({"start": NUM, "end": NUM, "first_line": STR, "on_screen": STR, "loop_point": STR}))})
    return AgentTask("package", prompt, schema, ["yt-package", "yt-seo", "yt-chapters", "ig-caption", "yt-shorts",
                                                 "ig-repurpose"], "direction",
                     {"title": title, "narration": narration, "topic": topic, "hook": hook, "duration": duration,
                      "platforms": platforms, "chapters": chapters, "actual_seconds": actual_seconds, "ratio": ratio, "look": look})


PACKAGE_PARTS = {"description": ("yt-seo", "the YouTube description"), "pinned_comment": ("yt-comment", "the pinned comment"),
                 "cover_prompt": ("yt-package", "the cover prompt"), "ig_caption": ("ig-caption", "the Instagram caption")}


def package_part(part: str, previous: str, note: str, title: str, narration: str, seconds: float, ratio: str,
                 look: str = "") -> AgentTask:
    """A fresh version of one piece of the package (the creator asked to regenerate it)."""
    skill, what = PACKAGE_PARTS[part]
    prompt = f"""Use the `{skill}` skill. Write a NEW version of {what} for this finished video: clearly different from
the previous version below (a new angle or a new joke), not a light edit of it.
{f"The creator asks: {note}" if note.strip() else ""}
Voice: {VOICE_YT} and {VOICE_IG}. Never publish anything.

{PACKAGE_RULES.format(cover=_cover_spec(ratio))}

{PLAIN_FUNNY}

TITLE: {title}
VIDEO LENGTH: {seconds:.0f} s ({"a short" if seconds < 60 else "long-form"}), aspect ratio {ratio}
LOOK OF THE VIDEO: {look or "see the script"}
SCRIPT (what is actually said, in order):
{narration}
PREVIOUS VERSION (do not repeat it):
{previous}

Return {{"text": "<the new {what}>"}}."""
    return AgentTask("package_part", prompt, _obj({"text": STR}), [skill], "direction",
                     {"part": part, "previous": previous, "note": note, "title": title, "narration": narration,
                      "seconds": seconds, "ratio": ratio, "look": look})


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
               talk: list, catalog: dict, draft: dict, feedback: str = "", assets: list | None = None) -> AgentTask:
    assets = assets or []
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
  If no listed prop fits, use one already drawn for this project ({_j(assets)}) as "type": "custom:<key>", or ask for
  a NEW one (at most 1 per clip): {{"type": "new", "asset": "<2-3 word name>", "describe": "<what it looks like>", ...}}.
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
                      "duration": duration, "talk": talk, "catalog": catalog, "draft": draft, "feedback": feedback,
                      "assets": assets})


def draw_prop(name: str, describe: str, style: str, catalog: dict, feedback: str = "") -> AgentTask:
    prompt = f"""Draw a prop for a low-poly 3D stick-figure video (style "{style}") as DATA: a list of simple shapes.
PROP: {name}. WHAT IT SHOULD LOOK LIKE: {describe or name}

Rules:
- 4 to 30 parts. Shapes: {catalog["asset_shapes"]}. size per shape: box [w,h,d]; sphere/ico [r]; cylinder [r_top,r_bottom,h];
  cone/pyramid [r,h]; torus [r,tube,arc_radians]; capsule [r,length]; wedge [w,h,d]. Metres; pos is the part's centre;
  rot in degrees [x,y,z]; +y up, the front faces +z, the prop stands on y=0.
- colour is a ROLE, never a hex code: {catalog["asset_colors"]} (accent = the video's main colour; glow = lit/emissive).
- Make it instantly recognisable from the front in silhouette: exaggerate the one or two features that identify it.
- Optional motion on parts that would move (a jaw, a wing, a wheel, a flame): {{"type": one of {catalog["asset_motions"]},
  "axis": "x"|"y"|"z", "amount": degrees (or metres for bob), "speed": cycles per second}}. Name moving parts.
- height: its natural height in metres (a mug 0.12, a dog 0.5, a car 1.4; keep under 1.8). grip: [x,y,z] where a hand
  would hold it, if it is held.
{('PREVIOUS DRAWING WAS REJECTED: ' + feedback) if feedback else ''}"""
    part = {"type": "object", "required": ["shape", "size", "pos", "color"], "additionalProperties": True,
            "properties": {"shape": STR, "size": _arr(NUM, 1), "pos": _arr(NUM, 3), "rot": _arr(NUM), "color": STR}}
    schema = _obj({"name": STR, "height": NUM, "parts": _arr(part, 1), "notes": STR}, ["name", "height", "parts"])
    return AgentTask("draw_prop", prompt, schema, [], "direction",
                     {"name": name, "describe": describe, "style": style, "catalog": catalog, "feedback": feedback})
