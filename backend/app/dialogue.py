"""Dialogue shorts: a person and one to three AI mascots trading short, deadpan lines at a desk (or at a whiteboard).

Pieces, in pipeline order:
- the cast (names, voices, looks) with defaults, per project: a (the person), b (the main AI) and optional c, d
  (extra AIs for group episodes);
- the scene: the set (office desk, or the classroom whiteboard for explainers) and the look outside the window
  (morning, rain, night, dusk);
- the writing rules for the genre and a checker for them (`dialogue_flags`);
- grouping the lines into the video's 10 s clips (`group_lines`), never splitting a line;
- delivery: each line carries its performance for an expressive voice (ElevenLabs v4 audio tags like
  [exasperated], stretched words like "Claaauude!!", CAPS emphasis) and a timing (quick, normal, or a beat:
  a sharp look before answering); tags are removed for captions and for voices that cannot perform them;
- the direction per line (`plan_shots`), modelled on measured reference reels: her medium close-up, each AI
  at desk height with her soft behind it (alternating sides), a frontal wide every 8-12 lines and for the last
  line; the classroom adds the board shot. Hard cuts about 0.15 s before each speaker's first word, her pose set
  per shot, faces from the words and tags. Deterministic, so it costs nothing and never drifts;
- timing the voiced lines inside a clip (`layout`) and turning that into a renderer scene (`build_scene`);
- caption events per line (`caption_lines`).
The renderer's layout numbers (desk, positions) come from renderer/catalog.json (sets.office, sets.classroom).
"""
from __future__ import annotations

import copy
import json
import math
import re
from pathlib import Path

from .paths import REPO_ROOT

CATALOG = json.loads((REPO_ROOT / "renderer" / "catalog.json").read_text(encoding="utf-8"))
OFFICE = CATALOG["sets"]["office"]
CLASSROOM = CATALOG["sets"]["classroom"]
SPEAKERS = ("a", "b")                 # always present
ALL_SPEAKERS = ("a", "b", "c", "d")   # c, d: extra AIs, when enabled in the cast
SETS = ("office", "classroom")
LOOKS = ("morning", "rain", "night", "dusk")
POSES = ("rest", "mug", "phone", "crossed", "temple", "palm", "both", "finger")
BOARD_OPS = ("title", "word", "strike", "figure", "box", "arrow", "label")

DEFAULT_CAST = {
    "a": {"name": "Mia", "role": "a tired, exacting developer who says no a lot", "kind": "chibi", "voice": "female",
          "appearance": {"skin": "#f1c7a5", "hair": "#2b1d16", "hair_style": "long", "top": "#f2b31b", "shirt": "#1d1d22",
                         "bottom": "#2c3140", "shoes": "#2a2a2e", "glasses": "round", "headphones": False, "variant": 0}},
    "b": {"name": "Claude", "role": "an earnest, literal AI assistant that asks one question too many", "kind": "mascot",
          "voice": "mascot", "appearance": {"shape": "flower", "color": "#e8743c"}},
    "c": {"name": "Codex", "role": "a terse AI that acts first and never asks; its answer is usually \"Done.\"",
          "kind": "mascot", "voice": "mascot2", "enabled": False,
          "appearance": {"shape": "cloud", "color": "#3f63f2", "color2": "#8b3fd8", "feet": "#2a2f8f"}},
    "d": {"name": "Cursor", "role": "an eager AI that starts before it is asked", "kind": "mascot", "voice": "mascot3",
          "enabled": False, "pitch": 1.12, "appearance": {"shape": "cube", "color": "#2b2e36", "eyes": "#ffffff"}},
}
KINDS = {"a": ("chibi", "stickman"), "b": ("mascot", "chibi", "stickman"), "c": ("mascot",), "d": ("mascot",)}
VOICES = ("female", "male", "mascot", "mascot2", "mascot3")


def _merge(a: dict, b: dict) -> dict:
    out = copy.deepcopy(a)
    for k, v in (b or {}).items():
        out[k] = _merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def cast_for(project: dict) -> dict:
    """The project's cast over the defaults, with unknown kinds/voices replaced by the defaults."""
    cast = _merge(DEFAULT_CAST, project.get("cast") or {})
    for s in ALL_SPEAKERS:
        c = cast[s]
        if c.get("kind") not in KINDS[s]:
            c["kind"] = DEFAULT_CAST[s]["kind"]
        if c.get("voice") not in VOICES:
            c["voice"] = DEFAULT_CAST[s]["voice"]
        c["name"] = str(c.get("name") or DEFAULT_CAST[s]["name"]).strip()[:40]
    return cast


def speakers(cast: dict) -> tuple[str, ...]:
    """The speakers in this cast: a and b, plus the extra AIs that are switched on."""
    return SPEAKERS + tuple(s for s in ("c", "d") if (cast.get(s) or {}).get("enabled"))


def scene_for(script: dict, settings: dict | None = None) -> dict:
    """The set and the window look: the Settings value when forced, else what the script picked, else the defaults
    (the office at night). The classroom needs board lines and only two speakers."""
    d = (settings or {}).get("dialogue", {})
    sc = script.get("scene") or {}
    lines = script.get("lines") or [ln for c in script.get("clips", []) for ln in c.get("lines", [])]
    st = d.get("set", "auto") if d.get("set", "auto") != "auto" else sc.get("set")
    st = st if st in SETS else "office"
    if st == "classroom" and any(ln.get("speaker") in ("c", "d") for ln in lines):
        st = "office"
    look = d.get("look", "auto") if d.get("look", "auto") != "auto" else sc.get("look")
    look = look if look in LOOKS else ("morning" if st == "classroom" else "night")
    return {"set": st, "look": look}


def is_dialogue(project: dict) -> bool:
    return project.get("format") == "dialogue"


# ---- delivery: tags, stretched words, timing ------------------------------------------------------

TAG_RE = re.compile(r"\[([^\[\]]{1,40})\]")
PLAN_VERSION = 3       # bump when the direction rules change, so saved shot plans are redone
# measured on the reference reels: the first word at 0.37 s, a median 0.47 s between lines (quick comebacks
# 0.15-0.3 s, beats 0.6-1.0 s), cuts 0.15 s before the next speaker's first word, about 1.6 s after the last word
LEAD, TAIL = 0.37, 0.15
CUT_LEAD = 0.15
# silence before a line, by its timing: an answer that comes straight back, a normal turn, or a beat (a sharp
# look first). Floors are how far each can shrink when a clip is full.
GAPS = {"quick": 0.2, "normal": 0.45, "beat": 0.9}
GAP_FLOOR = {"quick": 0.1, "normal": 0.25, "beat": 0.55}
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
        ls = [{"i": i, "speaker": lines[i]["speaker"], "text": lines[i]["text"], "timing": timing_of(lines[i]),
               **{k: lines[i][k] for k in ("pose", "board") if lines[i].get(k)}} for i in g]
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
MAX_BOARD_LINE_WORDS = 16      # an explainer line on the whiteboard shot may run longer


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
    who = speakers(cast)
    names = {s: cast[s]["name"] for s in who}
    scene = res.get("scene") or {}
    if not n_min <= n <= n_max:
        flags.append(f"{n} lines for {duration}s; write {n_min}-{n_max} (short lines, quick exchange)")
    if lines and lines[0].get("speaker") != "a":
        flags.append(f"the first line is {names['a']}'s")
    if lines and hook_say and squash(lines[0].get("text", "")) != squash(hook_say):
        flags.append(f"line 1 must be the approved hook, word for word: \"{hook_say}\"")
    run = 1
    for k, ln in enumerate(lines):
        if ln.get("speaker") not in who:
            flags.append(f"line {k + 1}: speaker must be one of " + ", ".join(f'"{s}" ({names[s]})' for s in who))
            continue
        text = ln.get("text", "")
        wc = words(text)
        cap = MAX_BOARD_LINE_WORDS if ln.get("board") else MAX_LINE_WORDS
        if wc > cap:
            flags.append(f"line {k + 1} has {wc} words (max {cap}; most lines 2-6)")
        if ln.get("pose") is not None and ln.get("pose") not in POSES:
            flags.append(f"line {k + 1}: pose must be one of {', '.join(POSES)}")
        for op in ln.get("board") or []:
            if not isinstance(op, dict) or op.get("op") not in BOARD_OPS:
                flags.append(f"line {k + 1}: board items are {{op: {'|'.join(BOARD_OPS)}, text}}")
                break
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
        avg = sum(words(ln.get("text", "")) for ln in lines if not ln.get("board")) / max(1, sum(1 for ln in lines if not ln.get("board")))
        if avg > 7.5:
            flags.append(f"lines average {avg:.1f} words; keep them short (2-6)")
        for s in who:
            share = sum(1 for ln in lines if ln.get("speaker") == s) / n
            need = 0.3 if s in SPEAKERS and len(who) == 2 else (0.25 if s == "a" else 0.08)
            if share < need:
                flags.append(f"{names[s]} has only {share:.0%} of the lines (at least {need:.0%})")
        short = sum(1 for ln in lines if words(ln.get("text", "")) <= 2)
        if short < 2:
            flags.append("use one- or two-word lines as punches (\"No.\" \"Done.\" \"You counted?\"): at least 2")
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
    if scene.get("set") is not None and scene.get("set") not in SETS:
        flags.append(f"scene.set must be one of {', '.join(SETS)}")
    if scene.get("look") is not None and scene.get("look") not in LOOKS:
        flags.append(f"scene.look must be one of {', '.join(LOOKS)}")
    if scene.get("set") == "classroom":
        ops = [op for ln in lines for op in (ln.get("board") or []) if isinstance(op, dict)]
        if not any(op.get("op") == "title" for op in ops):
            flags.append("a classroom explainer opens the board with a title item (the question being explained)")
        if len(ops) < 4:
            flags.append(f"the whiteboard needs at least 4 items across the explanation (got {len(ops)})")
        if any(ln.get("speaker") in ("c", "d") for ln in lines):
            flags.append("the classroom set has two speakers only (a and b)")
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


# ---- direction: faces, poses and shots -------------------------------------------------------------

TAG_FACE = [(r"embarrass|sheepish|blush|mortif|flustered", "embarrassed"), (r"tender|fond|warm|content|softly smil", "content"),
            (r"worri|anxious|concern|uneasy", "worried"),
            (r"exasperat|annoy|groan|sigh|fed up|irritat|frustrat", "skeptical"), (r"deadpan|flat|sarcas|dry|unimpress", "skeptical"),
            (r"angry|furious|snap|shout", "angry"), (r"excit|cheer|happy|proud|delight|laugh|giggl|beam", "happy"),
            (r"surpris|gasp|shock|stunn", "surprised"), (r"nervous|unsure|hesita|confus|guilty|caught", "confused"),
            (r"whisper|quiet|soft|think|ponder", "thinking"), (r"sad|hurt|sulk|defeat", "sad")]


def _expr(text: str, speaker: str) -> str:
    """The face for a line: from its delivery tag when it has one, else from the words and punctuation. The AIs
    act with their eyes: an unsure or caught-out line gets small square eyes ("caught")."""
    face = None
    for tag in tags(text):
        for rx, f in TAG_FACE:
            if re.search(rx, tag):
                face = f
                break
        if face:
            break
    t = clean(text)
    if face is None:
        if PAUSE_RE.match(t):
            face = "thinking" if speaker == "a" else "caught"
        elif t.endswith("?"):
            face = "confused" if speaker == "a" else "surprised"
        elif t.endswith("!"):
            face = "happy"
        elif re.search(r"\b(no|not|never|can't|cannot|wrong|bad|off)\b", t, re.I):
            face = "skeptical"
        else:
            face = "neutral"
    if speaker != "a" and face in ("confused", "thinking", "worried", "embarrassed", "sad"):
        face = "caught"
    return face


# shot vocabulary (measured on the reference reels):
#   office:    a_cu (her MCU, centred), a_third (her MCU off-centre), m_<s>_l / m_<s>_r (an AI at desk height, her
#              body soft behind it on the left / right of frame), wide (frontal, the whole desk)
#   classroom: board (3/4 wide: the whiteboard, the AI on its books with the pointer, her in profile), a_side (her
#              3/4 profile MCU), b_books (the AI on its books, close)
def shot_label(shot: str, names: dict) -> str:
    if shot == "wide":
        return "wide"
    if shot == "board":
        return "whiteboard"
    if shot == "a_cu":
        return f"{names.get('a', 'a')} close-up"
    if shot == "a_third":
        return f"{names.get('a', 'a')} close-up (off-centre)"
    if shot == "a_side":
        return f"{names.get('a', 'a')} close-up (profile)"
    if shot == "b_books":
        return f"{names.get('b', 'b')} close-up (on the books)"
    if shot.startswith("m_"):
        _, who, side = shot.split("_")
        return f"{names.get(who, who)} at desk height ({'angle 2' if side == 'l' else 'angle 1'})"
    # plans saved by older versions
    if shot in ("two", "wide0", "wide1"):
        return {"two": "two-shot", "wide0": "wide", "wide1": "wide (left)"}[shot]
    return shot


def _poses(lines: list[dict], look: str) -> list[str]:
    """Her pose per line: the script's when it names one, else the last one (a pose holds until changed). The
    default is a mug in her hands on a morning, hands on the desk otherwise."""
    cur = "mug" if look == "morning" else "rest"
    out = []
    for ln in lines:
        if ln.get("pose") in POSES:
            cur = ln["pose"]
        out.append(cur)
    return out


def plan_shots(lines: list[dict], scene: dict | None = None) -> list[dict]:
    """Per line: the shot, whether it cuts, the face, her pose and the board items. Direction rules (from the
    measured reference reels):
    - office: open on her close-up (a wide when three or more characters talk); her lines alternate centred and
      off-centre close-ups; each AI's line plays at desk height with her soft behind it, alternating sides; a wide
      after 9 lines without one, and the last line is always the wide (the pull-back follows);
    - classroom: lines that write on the board play on the board shot, her lines in profile, the AI's on its books;
    - the same speaker twice in a row keeps the shot (no cut), at most for two lines."""
    scene = scene or {"set": "office", "look": "night"}
    n, out = len(lines), []
    group = len({ln.get("speaker") for ln in lines}) > 2
    poses = _poses(lines, scene.get("look", "night"))
    a_count, side, since_wide, held = 0, {}, 0, 0
    for k, ln in enumerate(lines):
        s, text, tm = ln["speaker"], ln["text"], timing_of(ln)
        prev = out[-1] if out else None
        cut = True
        if scene.get("set") == "classroom":
            shot = "board" if (k == 0 or ln.get("board")) else ("a_side" if s == "a" else "b_books")
        elif k == 0:
            shot = "wide" if group else "a_cu"
        elif k == n - 1 and n >= 4:
            shot = "wide"
        elif since_wide >= 9 and s == "a":
            shot = "wide"
        elif s == "a":
            shot = ("a_cu", "a_cu", "a_third")[a_count % 3]
            a_count += 1
        else:
            side[s] = side.get(s, -1) + 1
            shot = f"m_{s}_{'r' if side[s] % 2 == 0 else 'l'}"
        # one speaker going on: hold the shot (no cut) once; a third line in a row gets a new framing
        if prev and lines[k - 1]["speaker"] == s and k != n - 1 and held < 1 and not (scene.get("set") == "classroom" and ln.get("board") and prev["shot"] != "board"):
            shot, cut = prev["shot"], False
            held += 1
        else:
            held = 0
        if cut and prev and shot == prev["shot"] and shot != "wide":
            if shot.startswith("m_"):
                shot = shot[:-1] + ("l" if shot.endswith("r") else "r")
            elif shot in ("a_cu", "a_third"):
                shot = "a_third" if shot == "a_cu" else "a_cu"
        since_wide = 0 if shot in ("wide", "board") else since_wide + 1
        gesture = None
        if s == "a" and (clean(text).endswith("?") or tm == "beat"):
            gesture = "think"            # hand to the cheek (lively motion only)
        if s != "a" and clean(text).endswith("!"):
            gesture = "cheer"            # the mascot hops (lively motion only)
        item = {"i": k, "speaker": s, "shot": shot, "cut": cut, "timing": tm, "face": _expr(text, s), "gesture": gesture,
                "pose": poses[k]}
        if ln.get("board"):
            item["board"] = [{"op": op.get("op"), "text": str(op.get("text", ""))[:28], **({"at": op["at"]} if op.get("at") else {})}
                             for op in ln["board"] if isinstance(op, dict) and op.get("op") in BOARD_OPS]
        out.append(item)
    return out


# ---- render-time timing ---------------------------------------------------------------------------

def clip_lead(first: bool, timing: str) -> float:
    """Silence before a clip's first line: 0.37 s at the start of the video; later clips continue the conversation,
    so the previous clip's tail plus this lead is the line's own gap."""
    return LEAD if first else max(0.05, GAPS.get(timing, GAPS["normal"]) - TAIL)


def layout(durs: list[float], timings: list[str], clip_len: float = 10.0, max_speedup: float = 1.25, pad: bool = True,
           lead: float | None = None) -> dict:
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
    lead0 = LEAD if lead is None else lead
    speech, room, tempo = sum(durs), clip_len - lead0 - TAIL, 1.0
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
    lead = lead0 + (min(0.3, max(0.0, room - used) / 2) if pad else 0.0)
    starts, ends, t = [], [], lead
    for d, g in zip(spoken, gaps):
        t += g
        starts.append(round(t, 3))
        t += d
        ends.append(round(min(clip_len, t), 3))
    return {"starts": starts, "ends": ends, "tempo": round(tempo, 3), "overflow": round(overflow, 3)}


def clip_end(timing: dict, clip_len: float = 10.0, fps: int = 24, tail: float = TAIL) -> float:
    """How long a dialogue clip runs: until its last line ends plus a short tail (whole frames), at most clip_len;
    the final clip's longer tail is the pull-back after the last word. Clips are not padded to 10 s, so the next
    clip's first line follows like a normal reply, not after dead air."""
    end = timing["ends"][-1] + tail if timing.get("ends") else clip_len
    return round(min(clip_len + max(0.0, tail - TAIL), max(2.0, end)) * fps) / fps


# ---- the renderer scene -----------------------------------------------------------------------------

def _head(pos: list[float], height: float) -> list[float]:
    return [pos[0], pos[1] + height, pos[2]]


def positions(cast: dict, scene: dict, who: tuple[str, ...]) -> dict:
    """Where everyone is: her behind the desk (or at the school desk), the AIs on the desk in front of her (the
    main one front left; in a group, three across), the explainer AI on its stack of books."""
    if scene.get("set") == "classroom":
        return {"a": CLASSROOM["person"], "b": CLASSROOM["mascot"]}
    pos = {"a": OFFICE["person"], "b": OFFICE["mascot"]}
    if len(who) > 2:
        pos.update({s: OFFICE["group"][s] for s in who if s != "a"})
    return pos


MASCOT_FACE = 0.16      # the mascot's face centre above its feet


def camera_key(shot: str, t: float, cast: dict, pos: dict | None = None, scene: dict | None = None) -> dict:
    """A cut camera key for a shot of the vocabulary, framed from the set's layout."""
    pos = pos or {"a": OFFICE["person"], "b": OFFICE["mascot"]}
    key = {"t": round(t, 3), "cut": True}
    A = _head(pos["a"], 1.17)                          # her head centre at rest
    if shot == "board":
        bx, by, bz = CLASSROOM["board_center"]
        return {**key, "pos": [0.26, 1.42, 3.05], "look": [-0.05, 1.2, -1.0], "fov": 44, "push": 0.03,
                "focus": [bx, by, bz], "aperture": 0.012}
    if shot == "a_side":                               # her face in 3/4 profile, turned toward the board
        f = CLASSROOM["person_facing"] + 0.6
        return {**key, "pos": [round(A[0] + math.sin(f) * 1.85, 3), 1.16, round(A[2] + math.cos(f) * 1.85, 3)],
                "look": [A[0], A[1] - 0.14, A[2]], "fov": 34, "push": 0.04}
    if shot == "b_books":
        return {**key, "shot": {"type": "closeup", "target": "b", "side": 0.25, "offset": 0.12}, "push": 0.05}
    if shot in ("wide", "wide0", "wide1", "two"):
        if len(pos) > 2:                               # a group: wide enough for every AI on the desk
            return {**key, "pos": [A[0] + 0.11, 1.25, 3.0], "look": [A[0] + 0.12, 0.9, -0.3], "fov": 42, "push": 0.03}
        return {**key, "pos": [A[0] - 0.06, 1.2, 2.35], "look": [A[0] - 0.05, 0.9, -0.3], "fov": 40, "push": 0.03}
    if shot == "a_cu":
        return {**key, "shot": {"type": "closeup", "target": "a", "side": 0.0, "zoom": 1.42}, "push": 0.05}
    if shot == "a_third":
        return {**key, "shot": {"type": "closeup", "target": "a", "side": 0.22, "offset": 0.2, "zoom": 1.38}, "push": 0.04}
    if shot.startswith("m_"):
        _, who, side = shot.split("_")
        M = pos.get(who, OFFICE["mascot"])
        F = [M[0], M[1] + MASCOT_FACE, M[2]]
        # her torso lands behind the AI on one side: the camera sits low in front of the AI, swung a little
        # sideways; the AI takes the opposite third
        # the camera circles the AI to a side where her body falls behind it on the chosen side of the frame (she
        # sits behind and to one side of it, so one variant is nearly frontal and the other comes from wide of
        # her); the AI is turned to face each angle (`yaw`: a cheat on the cut) and sits in the opposite third
        rel = math.atan2(A[0] - F[0], F[2] - A[2])        # where she is, seen from in front of the AI (+: to its right)
        if rel >= 0:                                   # she is to its right: frontal (her right) or from its left (her left)
            theta = 0.05 if side == "r" else -(rel + 0.5)
        else:                                          # she is to its left (an AI right of her, near the monitor):
            theta = -0.05 if side == "r" else -0.32    # two frontal angles, her on the left in both
        dist, sgn = 0.95, (1 if side == "r" else -1)
        cam = [F[0] + math.sin(theta) * dist, F[1] + 0.02, F[2] + math.cos(theta) * dist]
        d = [-math.sin(theta), -math.cos(theta)]                 # the view direction (x, z)
        right = [-d[1], d[0]]
        look = [F[0] + d[0] * 0.3 + right[0] * 0.07 * sgn, F[1] + 0.09, F[2] + d[1] * 0.3 + right[1] * 0.07 * sgn]
        return {**key, "pos": [round(v, 3) for v in cam], "look": [round(v, 3) for v in look], "fov": 38, "push": 0.04,
                "focus": [round(v, 3) for v in (F[0], F[1], F[2] + 0.08)],
                "_yaw": [who, round(theta, 3)]}
    # plans saved by older versions
    return {**key, "shot": {"type": "closeup", "target": shot.split("_")[0] if "_" in shot else "a", "side": 0.1}, "push": 0.05}


def board_events(plan: list[dict], timing: dict | None, before: list[dict] | None = None) -> list[dict]:
    """Whiteboard writes in time: earlier clips' items already up (t -1), this clip's items as their words are
    spoken (at the `at` word when given, else spread over the line)."""
    ev = [{"t": -1.0, **op} for op in (before or [])]
    if not timing:
        return ev
    for p, t0, t1 in zip(plan, timing["starts"], timing["ends"]):
        ops = p.get("board") or []
        for j, op in enumerate(ops):
            at = op.get("at")
            frac = 0.15 + 0.7 * j / max(1, len(ops))
            if at:
                ws = [squash(w) for w in clean(p.get("text", "")).split()] if p.get("text") else []
                if squash(at) in ws:
                    frac = ws.index(squash(at)) / max(1, len(ws))
            ev.append({"t": round(t0 + frac * max(0.1, t1 - t0), 3), "op": op["op"], "text": op.get("text", "")})
    return ev


def build_scene(plan: list[dict], timing: dict, cast: dict, mouths: dict, fps: int, width: int, height: int,
                duration: float, seed: int, quality: str, theme: str = "dark", dof: float = 0.035, motion: str = "still",
                scene: dict | None = None, final: bool = False, board_before: list[dict] | None = None,
                mascot_mouth: bool = False, prev_shot: str | None = None) -> dict:
    """A version 2 scene for one clip: her behind the desk, the AIs on it (or the classroom whiteboard), a hard cut
    about 0.15 s before each speaker's first word, her pose set per shot, the final clip's wide pulling back after
    the last word.
    motion "still" (default): the characters do not move; only faces change (expressions, blinks, lip sync).
    motion "lively": nods, hand beats, a hand to the cheek on questions, the mascots hop and turn."""
    scene = scene or {"set": "office", "look": "night"}
    classroom = scene.get("set") == "classroom"
    still = motion != "lively"
    idle = {"t": 0, "clip": "Idle", "speed": 0} if still else {"t": 0, "clip": "Idle"}
    starts, ends = timing["starts"], timing["ends"]
    who = ("a", "b") if classroom else speakers(cast)      # every AI in the cast sits on the desk all along
    pos = positions(cast, scene, who)
    a = cast["a"]
    actor = {"a": {"id": "a", "kind": a["kind"], "appearance": a.get("appearance", {}), "position": pos["a"], "still": still,
                   "anim": [idle], "face": [{"t": 0, "expr": "neutral"}], "gaze_max": 0.45, "gestures": [],
                   "look": [{"t": 0, "at": "b"}]}}
    if classroom:
        actor["a"]["facing"] = CLASSROOM["person_facing"]
        actor["a"]["gaze_max"] = 0.7
    for s in who[1:]:
        c = cast[s]
        ap = {**c.get("appearance", {}), "mouth": bool(mascot_mouth)}
        actor[s] = {"id": s, "kind": c["kind"], "appearance": ap, "position": pos.get(s, OFFICE["mascot"]),
                    "facing": 0.45 if classroom else 0.0, "still": still, "face": [{"t": 0, "expr": "neutral"}], "gestures": [],
                    "look": [{"t": 0, "at": "camera"}]}
        if c["kind"] != "mascot":                       # a second person stands beside the desk instead
            actor[s]["position"] = [-0.85, 0, -0.3]
            actor[s]["facing"] = 0.5
            actor[s]["anim"] = [idle]
    cams, cut_times = [], []
    for k, (p, t0, t1) in enumerate(zip(plan, starts, ends)):
        s = p["speaker"]
        if s not in actor:
            continue
        tm = p.get("timing", "normal")
        prev_end = ends[k - 1] if k else 0.0
        if not cams:
            cut_at = 0.0
        elif not p.get("cut", True):
            cut_at = None                               # the same speaker goes on in the same shot
        elif tm == "beat":                             # a reaction cut: the look plays before the answer
            cut_at = max(cams[-1]["t"] + 0.4, min(prev_end + 0.33, t0 - CUT_LEAD))
        else:
            cut_at = max(cams[-1]["t"] + 0.4, t0 - CUT_LEAD)
        if cut_at is not None:
            cut_at = min(cut_at, max(t0, cams[-1]["t"] + 0.4) if cams else 0.0)
            ck = camera_key(p["shot"], cut_at, cast, pos, scene)
            yaw = ck.pop("_yaw", None)
            if yaw and yaw[0] in actor:                 # the AI faces this camera from the cut on
                actor[yaw[0]].setdefault("_yaws", []).append({"t": -1.0 if not cams else round(cut_at, 3), "yaw": yaw[1]})
            elif cams and not classroom:                # other shots: the AIs face the front again
                for s2 in who[1:]:
                    if actor[s2].get("_yaws") and actor[s2]["_yaws"][-1]["yaw"] != 0.0:
                        actor[s2]["_yaws"].append({"t": round(cut_at, 3), "yaw": 0.0})
            cams.append(ck)
            cut_times.append((cut_at, p))
        if tm == "beat":
            actor[s]["face"].append({"t": round(max(0.0, prev_end), 3), "expr": "skeptical"})   # the sharp look
        actor[s]["face"].append({"t": round(max(0.0, t0 - 0.08), 3), "expr": p["face"]})
        actor[s]["face"].append({"t": round(t1 + 0.35, 3), "expr": "neutral" if p["face"] not in ("content", "embarrassed") else p["face"]})
        if p.get("gesture") and not still:
            g = {"t": round(t0, 3), "gesture": p["gesture"], "dur": round(max(0.8, t1 - t0 + 0.4), 3)}
            if p["gesture"] == "think":
                g["side"] = "R"
            actor[s]["gestures"].append(g)
        # she glances at whichever AI is talking (the main one otherwise); she never turns on her own shot
        if s != "a" and len(who) > 2:
            actor["a"]["look"].append({"t": round(max(0.0, (cut_at if cut_at is not None else t0) + 0.02), 3), "at": s})
        if not still and s == "a" and cast["b"]["kind"] == "mascot":
            actor["b"]["look"].append({"t": round(t0 + 0.2, 3), "at": "a"})
        elif not still and s != "a":
            actor["b"]["look"].append({"t": round(max(0.0, (cut_at or t0) - 0.45), 3), "at": "camera"})
    # her pose: set on each cut, held until the next one (a pose never changes on screen)
    spans = []
    for t, p in cut_times or [(0.0, plan[0] if plan else {"pose": "rest"})]:
        if not spans or (spans[-1][1].get("pose") or "rest") != (p.get("pose") or "rest"):   # one span per pose
            spans.append((t, p))
    for j, (t, p) in enumerate(spans):
        t_next = spans[j + 1][0] if j + 1 < len(spans) else duration + 1
        pose = p.get("pose", "rest") or "rest"
        start = -1.0 if j == 0 else t
        actor["a"]["gestures"].append({"t": round(start, 3), "gesture": pose, "snap": True, "dur": round(t_next - start, 3),
                                       **({"side": "R"} if pose in ("temple", "palm", "finger") else {})})
    # the final clip: the last shot (a wide) holds through the last line, then keeps pulling back
    if final and cams and ends and "pos" in cams[-1]:
        last = cams[-1]
        t_hold = round(max(last["t"] + 0.1, ends[-1]), 3)
        back = [round(v + d, 3) for v, d in zip(last["pos"], (0.0, 0.07, 0.5))]
        cams[-1] = {**last, "push": 0}
        cams.append({"t": t_hold, "pos": last["pos"], "look": last["look"], "fov": last["fov"]})
        cams.append({"t": round(duration, 3), "pos": back, "look": last["look"], "fov": last["fov"] + 2, "ease": "inOutSine"})
    for s in actor:
        yaws = actor[s].pop("_yaws", None)
        if yaws:
            actor[s]["facing"] = ([{"t": -1.0, "yaw": actor[s].get("facing", 0.0)}] if yaws[0]["t"] > -1 else []) + yaws
        for key in ("face", "look", "gestures"):
            actor[s][key] = sorted(actor[s][key], key=lambda k: k["t"])
        if mouths.get(s) and (s == "a" or mascot_mouth or cast[s]["kind"] != "mascot"):
            actor[s]["mouth"] = {"fps": fps, "values": mouths[s]}
    out = {"version": 2, "width": width, "height": height, "fps": fps, "duration": duration, "style": "night", "theme": theme,
           "set": scene.get("set", "office"), "look": scene.get("look", "night"),
           "layout": {"desk_mug": scene.get("desk_mug", not any(p.get("pose") == "mug" for p in plan))},
           "mood": [{"t": 0, "mood": "neutral"}], "seed": seed, "quality": quality, "handheld": 0.0,
           "dof": {"aperture": dof, "maxblur": 0.05}, "actors": list(actor.values()), "props": [],
           "camera": cams or [camera_key("a_cu", 0.0, cast, pos, scene)],
           "transition": {"in": "none", "out": "none"}, "_planned_by": "dialogue"}
    if classroom:
        out["board"] = {"events": board_events(plan, timing, board_before)}
    return out


def speaker_mouths(envelope: list[float], plan: list[dict], timing: dict, fps: int) -> dict:
    """Split the clip's voice loudness per speaker (each mouth moves only while its own lines play)."""
    out = {s: [0.0] * len(envelope) for s in ALL_SPEAKERS}
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
    # a caption stays up through the pause until the next line replaces it (never overlapping it); a long silence
    # (over 1.5 s) clears it
    for x, y in zip(out, out[1:]):
        x["end"] = round(y["start"] - 0.02 if y["start"] - x["end"] <= 1.5 else x["end"] + 0.25, 3)
    if out:
        out[-1]["end"] = round(out[-1]["end"] + 0.25, 3)
    return out


def script_lines(script: dict) -> list[list[dict]]:
    return [c.get("lines") or [] for c in script.get("clips", [])]


def plan_path(root: Path) -> Path:
    return root / "scenes" / "dialogue.json"
