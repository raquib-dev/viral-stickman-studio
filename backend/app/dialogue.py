"""Two-character dialogue shorts: a person and a mascot trading short, deadpan lines at a late-night desk.

Pieces, in pipeline order:
- the cast (names, voices, looks) with defaults, per project;
- the writing rules for the genre and a checker for them (`dialogue_flags`);
- grouping the lines into the video's 10 s clips (`group_lines`), never splitting a line;
- delivery: each line carries its performance for an expressive voice (ElevenLabs v4 audio tags like
  [exasperated], stretched words like "Claaauude!!", CAPS emphasis) and a timing (quick, normal, or a beat:
  a sharp look before answering); tags are removed for captions and for voices that cannot perform them;
- the direction per line (`plan_shots`): a vocabulary of shots (centred and off-centre close-ups, over-the-
  shoulder shots, a medium two-shot, two wides) rotated by rules, hard cuts, faces from the words and tags.
  Deterministic, so it costs nothing and never drifts;
- timing the voiced lines inside a clip (`layout`) and turning that into a renderer scene (`build_scene`);
- caption events per line (`caption_lines`).
The renderer's layout numbers (desk, positions) come from renderer/catalog.json (sets.office).
"""
from __future__ import annotations

import copy
import json
import re
from pathlib import Path

from .paths import REPO_ROOT

CATALOG = json.loads((REPO_ROOT / "renderer" / "catalog.json").read_text(encoding="utf-8"))
OFFICE = CATALOG["sets"]["office"]
SPEAKERS = ("a", "b")

DEFAULT_CAST = {
    "a": {"name": "Mia", "role": "a tired, exacting developer who says no a lot", "kind": "chibi", "voice": "female",
          "appearance": {"skin": "#f1c7a5", "hair": "#2b1d16", "hair_style": "long", "top": "#f2b31b", "shirt": "#1d1d22",
                         "bottom": "#2c3140", "shoes": "#2a2a2e", "glasses": "round", "headphones": True, "variant": 0}},
    "b": {"name": "Claude", "role": "an eager, literal AI coding assistant", "kind": "mascot", "voice": "mascot",
          "appearance": {"shape": "flower", "color": "#e8743c"}},
}
KINDS = {"a": ("chibi", "stickman"), "b": ("mascot", "chibi", "stickman")}
VOICES = ("female", "male", "mascot")


def _merge(a: dict, b: dict) -> dict:
    out = copy.deepcopy(a)
    for k, v in (b or {}).items():
        out[k] = _merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def cast_for(project: dict) -> dict:
    """The project's cast over the defaults, with unknown kinds/voices replaced by the defaults."""
    cast = _merge(DEFAULT_CAST, project.get("cast") or {})
    for s in SPEAKERS:
        c = cast[s]
        if c.get("kind") not in KINDS[s]:
            c["kind"] = DEFAULT_CAST[s]["kind"]
        if c.get("voice") not in VOICES:
            c["voice"] = DEFAULT_CAST[s]["voice"]
        c["name"] = str(c.get("name") or DEFAULT_CAST[s]["name"]).strip()[:40]
    return cast


def is_dialogue(project: dict) -> bool:
    return project.get("format") == "dialogue"


# ---- delivery: tags, stretched words, timing ------------------------------------------------------

TAG_RE = re.compile(r"\[([^\[\]]{1,40})\]")
PLAN_VERSION = 2       # bump when the direction rules change, so saved shot plans are redone
LEAD, TAIL = 0.22, 0.3
# silence before a line, by its timing: an answer that comes straight back, a normal turn, or a beat (a sharp
# look first). Floors are how far each can shrink when a clip is full.
GAPS = {"quick": 0.06, "normal": 0.2, "beat": 0.75}
GAP_FLOOR = {"quick": 0.02, "normal": 0.08, "beat": 0.4}
TIMINGS = tuple(GAPS)
PAUSE_RE = re.compile(r"^\s*(\.\.\.|…)")


def clean(text: str) -> str:
    """The words as seen on screen: audio tags removed (stretched words and CAPS stay)."""
    return re.sub(r"\s{2,}", " ", TAG_RE.sub("", text or "")).strip()


def tags(text: str) -> list[str]:
    return [t.strip().lower() for t in TAG_RE.findall(text or "")]


def squash(text: str) -> str:
    """For comparing words: lower case, no punctuation, stretched letters collapsed ("Claaauude" -> "claude")."""
    t = re.sub(r"[^a-z0-9' ]+", " ", clean(text).lower().replace("’", "'"))
    return re.sub(r"\s+", " ", re.sub(r"([a-z])\1+", r"\1", t)).strip()


def timing_of(line: dict) -> str:
    t = line.get("timing")
    if t in GAPS:
        return t
    return "beat" if PAUSE_RE.match(clean(line.get("text", ""))) else "normal"


def words(text: str) -> int:
    return len(re.findall(r"[\w'’-]+", clean(text)))


def line_seconds(text: str, wpm: float) -> float:
    """Spoken length estimate of one line (stretched words take longer; short lines still take a moment)."""
    stretched = len(re.findall(r"([a-zA-Z])\1\1", clean(text)))
    return max(0.55, words(text) / (wpm / 60) + 0.15 + 0.25 * stretched)


def _load(secs: list[float], timings: list[str], i: int, j: int) -> float:
    """Seconds lines i..j-1 take inside one clip: speech plus the silences before lines 2..n of the clip."""
    return sum(secs[i:j]) + sum(GAPS[timings[k]] for k in range(i + 1, j))


def group_lines(lines: list[dict], n_clips: int, wpm: float, clip_len: float = 10.0, stretch: float = 1.0) -> list[list[int]] | None:
    """Split the lines (in order, never splitting one) into exactly n_clips groups, as evenly as possible.
    None when they cannot fit: more lines than clips allow, or too few lines to give every clip one."""
    n = len(lines)
    if n < n_clips or n_clips < 1:
        return None
    secs = [line_seconds(ln["text"], wpm) for ln in lines]
    timings = [timing_of(ln) for ln in lines]
    cap = (clip_len - LEAD - TAIL) * stretch
    INF = float("inf")
    # best[k][j] = smallest possible largest load when the first j lines fill k clips
    best = [[INF] * (n + 1) for _ in range(n_clips + 1)]
    cut = [[0] * (n + 1) for _ in range(n_clips + 1)]
    best[0][0] = 0.0
    for k in range(1, n_clips + 1):
        for j in range(k, n + 1):
            for i in range(k - 1, j):
                if best[k - 1][i] == INF:
                    continue
                v = max(best[k - 1][i], _load(secs, timings, i, j))
                if v < best[k][j]:
                    best[k][j], cut[k][j] = v, i
    if best[n_clips][n] > cap:
        return None
    groups, j = [], n
    for k in range(n_clips, 0, -1):
        i = cut[k][j]
        groups.append(list(range(i, j)))
        j = i
    return groups[::-1]


def clips_from_lines(lines: list[dict], groups: list[list[int]]) -> list[dict]:
    """The script's clips: each carries its lines (with their delivery and timing) and, for the rest of the
    pipeline, the joined on-screen text."""
    out = []
    for k, g in enumerate(groups):
        ls = [{"i": i, "speaker": lines[i]["speaker"], "text": lines[i]["text"], "timing": timing_of(lines[i])} for i in g]
        out.append({"index": k, "stage": "dialogue", "vo": " ".join(clean(ln["text"]) for ln in ls), "lines": ls, "beats": []})
    return out


# ---- the writing rules (phase 3) ----------------------------------------------------------------

STOP = set("""a an the and or but so to of in on at for with from by is are was were be been being am i you he she it we they
me my your his her its our their this that these those there here not no yes do does did done have has had just very
really what who why how when where which then than too also into out up down over under again once only own same
all any some each few more most other such can can't cannot will would should could may might must shall
it's i'm you're that's don't didn't isn't wasn't won't i've you've we're they're okay ok oh""".split())
NUMBER_WORDS = re.compile(r"\b(one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|fifteen|twenty|thirty|forty|"
                          r"fifty|sixty|seventy|eighty|ninety|hundred|thousand|million|billion|half|dozen)\b", re.I)
STAT_LIKE = re.compile(r"%|\bpercent\b|\bstud(y|ies)\b|\bresearch\b|\bscientists?\b|\bstatistic|\bsurvey\b|\baccording to\b|"
                       r"\bdata shows?\b|\bon average\b", re.I)
MAX_LINE_WORDS = 9


def _content(text: str) -> list[str]:
    return [w for w in squash(text).split() if w not in STOP and w.strip("'")]


def _bigrams(text: str) -> set[tuple[str, str]]:
    toks = squash(text).split()
    return {(x, y) for x, y in zip(toks, toks[1:]) if not (x in STOP and y in STOP)}


def find_callback(lines: list[dict]) -> tuple[int, int] | None:
    """A line that echoes an earlier one at least 3 lines back (a shared phrase, or a shared distinctive word)."""
    for j in range(len(lines)):
        for i in range(0, j - 2):
            a, b = lines[i]["text"], lines[j]["text"]
            if _bigrams(a) & _bigrams(b):
                return (i, j)
            if {w for w in _content(a) if len(w) >= 4} & {w for w in _content(b) if len(w) >= 4}:
                return (i, j)
    return None


def dialogue_flags(res: dict, cast: dict, hook_say: str, duration: int, wpm: float) -> list[str]:
    """Everything that breaks the genre's rules, as readable flags (the writer gets them back to fix)."""
    lines, flags = res.get("lines") or [], []
    n = len(lines)
    n_min, n_max = max(4, round(duration / 3.6)), round(duration / 1.5)
    names = {s: cast[s]["name"] for s in SPEAKERS}
    if not n_min <= n <= n_max:
        flags.append(f"{n} lines for {duration}s; write {n_min}-{n_max} (short lines, quick exchange)")
    if lines and lines[0].get("speaker") != "a":
        flags.append(f"the first line is {names['a']}'s")
    if lines and hook_say and squash(lines[0].get("text", "")) != squash(hook_say):
        flags.append(f"line 1 must be the approved hook, word for word: \"{hook_say}\"")
    run = 1
    for k, ln in enumerate(lines):
        if ln.get("speaker") not in SPEAKERS:
            flags.append(f"line {k + 1}: speaker must be \"a\" ({names['a']}) or \"b\" ({names['b']})")
            continue
        text = ln.get("text", "")
        wc = words(text)
        if wc > MAX_LINE_WORDS:
            flags.append(f"line {k + 1} has {wc} words (max {MAX_LINE_WORDS}; most lines 2-7)")
        if wc == 0:
            flags.append(f"line {k + 1} is empty")
        if "{{" in text:
            flags.append(f"line {k + 1} has a {{{{gap}}}}: dialogue never needs a figure from the creator")
        if STAT_LIKE.search(clean(text)):
            flags.append(f"line {k + 1} sounds like a real-world statistic; keep every number inside the story")
        tg = tags(text)
        if len(tg) > 2:
            flags.append(f"line {k + 1} has {len(tg)} delivery tags (max 2)")
        if any(len(t.split()) > 3 for t in tg):
            flags.append(f"line {k + 1}: keep delivery tags to 1-3 words, e.g. [exasperated], [deadpan], [sighs]")
        if ln.get("timing") not in TIMINGS:
            flags.append(f"line {k + 1}: timing must be quick, normal or beat")
        run = run + 1 if k and lines[k - 1].get("speaker") == ln.get("speaker") else 1
        if run == 4:
            flags.append(f"line {k + 1}: {names[ln['speaker']]} has 4 lines in a row (max 3)")
    if n:
        avg = sum(words(ln.get("text", "")) for ln in lines) / n
        if avg > 7.5:
            flags.append(f"lines average {avg:.1f} words; keep them short (2-7)")
        for s in SPEAKERS:
            share = sum(1 for ln in lines if ln.get("speaker") == s) / n
            if share < 0.3:
                flags.append(f"{names[s]} has only {share:.0%} of the lines (at least 30%)")
        performed = sum(1 for ln in lines if tags(ln.get("text", "")) or re.search(r"([a-zA-Z])\1\1|!!", clean(ln.get("text", ""))))
        if performed < max(2, n // 3):
            flags.append(f"write the performance into the lines: only {performed} of {n} carry a delivery tag or a stretched "
                         "word; aim for at least a third ([exasperated] Claaauude!!)")
        timings = [ln.get("timing") for ln in lines[1:]]
        if timings.count("quick") < 2:
            flags.append("vary the rhythm: at least 2 lines answer straight back (timing quick)")
        if not 1 <= timings.count("beat") <= max(2, n // 4):
            flags.append(f"use 1-{max(2, n // 4)} beats (timing beat: a sharp look before the answer)")
        specifics = sum(1 for ln in lines if re.search(r"\d", clean(ln.get("text", ""))) or NUMBER_WORDS.search(clean(ln.get("text", ""))))
        if specifics < 2:
            flags.append("add oddly specific in-story details: at least 2 lines with a number (counts, times, sizes)")
        if not find_callback(lines):
            flags.append("no callback: a later line should echo an earlier phrase (at least 3 lines apart)")
        turn = res.get("turn")
        if not isinstance(turn, int) or not n / 2 <= turn <= n - 1:
            flags.append(f"mark the turn (the line where the meaning flips) as a line number in the second half (got {turn})")
        opening = set().union(*(set(_content(ln.get("text", ""))) for ln in lines[:3])) | {squash(names["a"]), squash(names["b"])}
        if not set().union(*(set(_content(ln.get("text", ""))) for ln in lines[-2:])) & opening:
            flags.append("the ending should loop back to the opening (reuse a word, a name or the situation from the first lines)")
    title = (res.get("title") or "").strip()
    if not title.endswith("?"):
        flags.append("the title ends with a question to the viewer")
    if title != title.lower():
        flags.append("the title is all lowercase (a quote, then the question)")
    if len(title) > 110:
        flags.append(f"the title is {len(title)} characters (max 110)")
    if "[" in title:
        flags.append("no delivery tags in the title")
    if n and title and len(set(_content(title)) & set().union(*(set(_content(ln.get("text", ""))) for ln in lines))) < 2:
        flags.append("the title should quote the script (share at least two of its words)")
    if n and group_lines(lines, duration // 10, wpm) is None:
        est = sum(line_seconds(ln.get("text", ""), wpm) for ln in lines) + sum(GAPS[timing_of(ln)] for ln in lines[1:])
        flags.append(f"the lines do not fit {duration // 10} clips of 10 s (about {est:.0f}s of speech and gaps; "
                     f"{'cut' if n >= duration // 10 else 'add'} lines)")
    return flags


def _norm(t: str) -> str:
    return squash(t)


# ---- direction: faces and shots ------------------------------------------------------------------

TAG_FACE = [(r"exasperat|annoy|groan|sigh|fed up|irritat|frustrat", "skeptical"), (r"deadpan|flat|sarcas|dry|unimpress", "skeptical"),
            (r"angry|furious|snap|shout", "angry"), (r"excit|cheer|happy|proud|delight|laugh|giggl|beam", "happy"),
            (r"surpris|gasp|shock|stunn", "surprised"), (r"nervous|unsure|hesita|confus", "confused"),
            (r"whisper|quiet|soft|think|ponder", "thinking"), (r"sad|hurt|sulk|defeat", "sad")]


def _expr(text: str, speaker: str) -> str:
    """The face for a line: from its delivery tag when it has one, else from the words and punctuation."""
    for tag in tags(text):
        for rx, face in TAG_FACE:
            if re.search(rx, tag):
                return face
    t = clean(text)
    if PAUSE_RE.match(t):
        return "thinking" if speaker == "a" else "skeptical"
    if t.endswith("?"):
        return "confused" if speaker == "a" else "surprised"
    if t.endswith("!"):
        return "happy"
    if re.search(r"\b(no|not|never|can't|cannot|wrong|bad|off)\b", t, re.I):
        return "skeptical"
    return "neutral"


# shot vocabulary: per speaker a centred close-up, an off-centre close-up (rule of thirds) and a shot with the
# other character in frame (over the mascot's shoulder onto her; a low angle on the mascot with her behind); for
# both: a medium two-shot and two wides
SINGLE = ("cu", "third", "ots")


def shot_label(shot: str, names: dict) -> str:
    if shot in ("two", "wide0", "wide1"):
        return {"two": "two-shot", "wide0": "wide", "wide1": "wide (left)"}[shot]
    who, kind = shot.split("_", 1)
    both = "low angle, both in frame" if who == "b" else "over the shoulder"
    return f"{names.get(who, who)} " + {"cu": "close-up", "third": "close-up (off-centre)", "ots": both}[kind]


def plan_shots(lines: list[dict]) -> list[dict]:
    """Per line: the shot, the face and a gesture. Direction rules:
    - open on the speaker's centred close-up (the hook lands in the face);
    - a beat (a sharp look before answering) plays in the responder's centred close-up, cut before they speak;
    - quick answers play over the shoulder, so both characters are in frame for the back-and-forth;
    - the same person speaking twice in a row gets a new angle: the two-shot or a wide;
    - otherwise each speaker rotates off-centre close-up -> over the shoulder -> close-up, never the same framing
      twice in a row, and a two-shot or wide comes at least every 5 lines;
    - the button (last line) plays wide, the line before it as a two-shot."""
    n, out = len(lines), []
    rot = {s: 0 for s in SPEAKERS}
    since_both, wide_alt = 0, 0
    order = ("third", "ots", "cu")
    for k, ln in enumerate(lines):
        s, text, tm = ln["speaker"], ln["text"], timing_of(ln)
        prev = out[-1]["shot"] if out else None
        if k == 0:
            shot = f"{s}_cu"
        elif n >= 4 and k == n - 1:
            shot = f"wide{wide_alt % 2}"
        elif n >= 4 and k == n - 2:
            shot = "two"
        elif lines[k - 1]["speaker"] == s:
            shot = "two" if prev != "two" else f"wide{wide_alt % 2}"
        elif tm == "beat":
            shot = f"{s}_cu"
        elif tm == "quick":
            shot = f"{s}_ots"
        elif since_both >= 4:
            shot = "two" if prev != "two" else f"wide{wide_alt % 2}"
        else:
            shot = f"{s}_{order[rot[s] % 3]}"
            rot[s] += 1
        if shot == prev:                                  # never the same framing twice in a row
            shot = f"{s}_{order[(order.index(shot.split('_', 1)[1]) + 1) % 3]}" if "_" in shot else ("two" if shot != "two" else "wide0")
        if shot.startswith("wide"):
            wide_alt += 1
        both = shot in ("two", "wide0", "wide1") or shot.endswith("_ots")
        since_both = 0 if both else since_both + 1
        gesture = None
        if s == "a" and (clean(text).endswith("?") or tm == "beat"):
            gesture = "think"            # hand to the cheek (lively motion only)
        if s == "b" and clean(text).endswith("!"):
            gesture = "cheer"            # the mascot hops (lively motion only)
        out.append({"i": k, "speaker": s, "shot": shot, "timing": tm, "face": _expr(text, s), "gesture": gesture})
    return out


# ---- render-time timing ---------------------------------------------------------------------------

def layout(durs: list[float], timings: list[str], clip_len: float = 10.0, max_speedup: float = 1.25, pad: bool = True) -> dict:
    """Where each voiced line plays inside the clip. The silence before a line follows its timing (quick 0.06 s,
    normal 0.2 s, a beat 0.75 s); when the clip is full the gaps shrink to their floors before speech speeds up
    (up to max_speedup). Spare time goes to the start and the end of the clip, never into the conversation;
    pad=False keeps the lead short (the clip is then cut to clip_end(), so there is no spare time)."""
    n = len(durs)
    if not n:
        return {"starts": [], "ends": [], "tempo": 1.0, "overflow": 0.0}
    tms = [t if t in GAPS else "normal" for t in timings]
    gaps = [0.0] + [GAPS[tms[k]] for k in range(1, n)]
    floor = [0.0] + [GAP_FLOOR[tms[k]] for k in range(1, n)]
    speech, room, tempo = sum(durs), clip_len - LEAD - TAIL, 1.0
    if speech + sum(gaps) > room:
        over = speech + sum(gaps) - room
        shrinkable = sum(g - f for g, f in zip(gaps, floor))
        if shrinkable >= over:
            gaps = [f + (g - f) * (1 - over / shrinkable) if shrinkable else f for g, f in zip(gaps, floor)]
        else:
            gaps = floor
            tempo = min(max_speedup, speech / max(0.1, room - sum(floor)))
    spoken = [d / tempo for d in durs]
    used = sum(spoken) + sum(gaps)
    overflow = max(0.0, used - room)
    lead = LEAD + (min(0.3, max(0.0, room - used) / 2) if pad else 0.0)
    starts, ends, t = [], [], lead
    for d, g in zip(spoken, gaps):
        t += g
        starts.append(round(t, 3))
        t += d
        ends.append(round(min(clip_len, t), 3))
    return {"starts": starts, "ends": ends, "tempo": round(tempo, 3), "overflow": round(overflow, 3)}


def clip_end(timing: dict, clip_len: float = 10.0, fps: int = 24) -> float:
    """How long a dialogue clip runs: until its last line ends plus a short tail, at most clip_len (whole frames).
    Clips are not padded to 10 s, so the next clip's first line follows like a normal reply, not after dead air."""
    end = timing["ends"][-1] + TAIL if timing.get("ends") else clip_len
    return round(min(clip_len, max(2.0, end)) * fps) / fps


# ---- the renderer scene -----------------------------------------------------------------------------

def _head(pos: list[float], height: float) -> list[float]:
    return [pos[0], pos[1] + height, pos[2]]


def camera_key(shot: str, t: float, cast: dict) -> dict:
    """A cut camera key for a shot of the vocabulary, framed for the office set's layout."""
    A = _head(OFFICE["person"], 1.17)                 # the chibi's head centre at rest
    B = _head(OFFICE["mascot"], 0.16)                 # the mascot's face centre
    key = {"t": round(t, 3), "cut": True}
    if shot == "two":
        return {**key, "pos": [0.32, 1.12, 1.3], "look": [0.1, 0.98, -0.22], "fov": 36, "push": 0.03}
    if shot in ("wide0", "wide1"):
        w = {"wide0": {"pos": [0.4, 1.25, 1.8], "look": [0.1, 0.96, -0.25], "fov": 38},
             "wide1": {"pos": [-0.42, 1.22, 1.8], "look": [0.08, 0.95, -0.2], "fov": 40}}[shot]
        return {**key, **w, "push": 0.04}
    who, kind = shot.split("_", 1)
    if cast["b"]["kind"] != "mascot" and kind == "ots":
        kind = "third"                                 # over-the-shoulder framings are laid out for the mascot
    if kind == "cu":
        return {**key, "shot": {"type": "closeup", "target": who, "side": 0.1 if who == "a" else 0.18}, "push": 0.06}
    if kind == "third":
        return {**key, "shot": {"type": "closeup", "target": who, "side": 0.3 if who == "a" else -0.22,
                                "offset": 0.22 if who == "a" else -0.2}, "push": 0.04}
    if who == "a":                                     # over the mascot's shoulder onto her: it soft in the corner
        return {**key, "pos": [0.46, 0.93, 0.66], "look": [A[0] + 0.04, A[1] - 0.06, A[2]], "fov": 34, "push": 0.03}
    # the mascot sits in front of her facing the camera, so "both in frame" for it is a low angle from the desk:
    # the mascot big in the foreground, her soft behind and above
    return {**key, "pos": [-0.06, 0.8, 0.95], "look": [0.22, 0.97, -0.05], "fov": 40, "push": 0.03}


def build_scene(plan: list[dict], timing: dict, cast: dict, mouths: dict, fps: int, width: int, height: int,
                duration: float, seed: int, quality: str, theme: str = "dark", dof: float = 0.035, motion: str = "still") -> dict:
    """A version 2 scene for one clip: the person behind the desk, the mascot on it, a hard cut per line.
    motion "still" (default): the characters do not move; only faces change (expressions, blinks, lip sync).
    motion "lively": nods, hand beats, a hand to the cheek on questions, the mascot hops and turns."""
    still = motion != "lively"
    idle = {"t": 0, "clip": "Idle", "speed": 0} if still else {"t": 0, "clip": "Idle"}
    starts, ends = timing["starts"], timing["ends"]
    a, b = cast["a"], cast["b"]
    actor = {
        # hands rest on the desk from before the clip starts (t -1), so they never reach in at a clip's first frame
        "a": {"id": "a", "kind": a["kind"], "appearance": a.get("appearance", {}), "position": OFFICE["person"], "still": still,
              "anim": [idle], "face": [{"t": 0, "expr": "neutral"}], "gaze_max": 0.45,
              "gestures": [{"t": -1, "gesture": "rest", "side": "both", "dur": duration + 2}], "look": [{"t": 0, "at": "b"}]},
        "b": {"id": "b", "kind": b["kind"], "appearance": b.get("appearance", {}), "position": OFFICE["mascot"], "facing": -0.2,
              "still": still, "face": [{"t": 0, "expr": "neutral"}], "gestures": [], "look": [{"t": 0, "at": "camera"}]},
    }
    if b["kind"] != "mascot":                       # a second person stands beside the desk instead
        actor["b"]["position"] = [-0.85, 0, -0.3]       # the free side of the desk (the monitor is on the right)
        actor["b"]["facing"] = 0.5
        actor["b"]["anim"] = [idle]
    cams = []
    for k, (p, t0, t1) in enumerate(zip(plan, starts, ends)):
        s = p["speaker"]
        tm = p.get("timing", "normal")
        prev_end = ends[k - 1] if k else 0.0
        if not cams:
            cut_at = 0.0
        elif tm == "beat":                             # cut to the responder as the other finishes: the look plays
            cut_at = max(cams[-1]["t"] + 0.4, prev_end + 0.05)
        elif tm == "quick":
            cut_at = max(cams[-1]["t"] + 0.4, t0 - 0.04)
        else:
            cut_at = max(cams[-1]["t"] + 0.4, t0 - 0.12)
        cut_at = min(cut_at, max(t0, cams[-1]["t"] + 0.4) if cams else 0.0)
        cams.append(camera_key(p["shot"], cut_at, cast))
        if tm == "beat":
            actor[s]["face"].append({"t": round(max(0.0, prev_end), 3), "expr": "skeptical"})   # the sharp look
        actor[s]["face"].append({"t": round(max(0.0, t0 - 0.08), 3), "expr": p["face"]})
        actor[s]["face"].append({"t": round(t1 + 0.35, 3), "expr": "neutral"})
        if p.get("gesture") and not still:
            g = {"t": round(t0, 3), "gesture": p["gesture"], "dur": round(max(0.8, t1 - t0 + 0.4), 3)}
            if p["gesture"] == "think":
                g["side"] = "R"
            actor[s]["gestures"].append(g)
        # gaze: the person watches the mascot; in lively motion the mascot turns to her while she talks and is back
        # facing the camera before its own shot cuts in (so the turn never happens on screen)
        if still:
            pass
        elif s == "a" and b["kind"] == "mascot":
            actor["b"]["look"].append({"t": round(t0 + 0.2, 3), "at": "a"})
        else:
            actor["b"]["look"].append({"t": round(max(0.0, cut_at - 0.45), 3), "at": "camera"})
    for s in SPEAKERS:
        for key in ("face", "look", "gestures"):
            actor[s][key] = sorted(actor[s][key], key=lambda k: k["t"])
        if mouths.get(s):
            actor[s]["mouth"] = {"fps": fps, "values": mouths[s]}
    return {"version": 2, "width": width, "height": height, "fps": fps, "duration": duration, "style": "night", "theme": theme,
            "mood": [{"t": 0, "mood": "neutral"}], "seed": seed, "quality": quality, "handheld": 0.003,
            "dof": {"aperture": dof, "maxblur": 0.03}, "actors": [actor["a"], actor["b"]], "props": [],
            "camera": cams or [camera_key("a_cu", 0.0, cast)],
            "transition": {"in": "none", "out": "none"}, "_planned_by": "dialogue"}


def speaker_mouths(envelope: list[float], plan: list[dict], timing: dict, fps: int) -> dict:
    """Split the clip's voice loudness per speaker (each mouth moves only while its own lines play)."""
    out = {s: [0.0] * len(envelope) for s in SPEAKERS}
    for p, t0, t1 in zip(plan, timing["starts"], timing["ends"]):
        for f in range(max(0, int(t0 * fps)), min(len(envelope), int(t1 * fps) + 2)):
            out[p["speaker"]][f] = envelope[f]
    return out


# ---- captions -------------------------------------------------------------------------------------

def caption_lines(clips_meta: list[dict], clip_lines: list[list[dict]], starts: list[float], lengths: list[float]) -> list[dict]:
    """Every line with its absolute start/end in the video and its on-screen text (no audio tags): from the
    render's timing when there is one, otherwise spread over the clip by word count (dry run)."""
    out = []
    for k, lines in enumerate(clip_lines):
        meta = (clips_meta[k] or {}).get("meta", {}) if k < len(clips_meta) else {}
        timed = meta.get("lines") or []
        if len(timed) == len(lines) and all("start" in x for x in timed):
            for ln, tm in zip(lines, timed):
                out.append({**ln, "text": clean(ln["text"]), "start": round(starts[k] + tm["start"], 3),
                            "end": round(starts[k] + tm["end"], 3)})
            continue
        w = [max(1, words(ln["text"])) for ln in lines]
        span = max(1.0, lengths[k] - LEAD - TAIL)
        t = starts[k] + LEAD
        for ln, n in zip(lines, w):
            d = span * n / sum(w)
            out.append({**ln, "text": clean(ln["text"]), "start": round(t, 3), "end": round(t + d * 0.9, 3)})
            t += d
    # never overlap: a line ends before the next one starts
    for x, y in zip(out, out[1:]):
        x["end"] = round(min(x["end"] + 0.25, y["start"] - 0.02), 3)
    if out:
        out[-1]["end"] = round(out[-1]["end"] + 0.25, 3)
    return out


def script_lines(script: dict) -> list[list[dict]]:
    return [c.get("lines") or [] for c in script.get("clips", [])]


def plan_path(root: Path) -> Path:
    return root / "scenes" / "dialogue.json"
