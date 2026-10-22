"""Two-character dialogue shorts: a person and a mascot trading short, deadpan lines at a late-night desk.

Pieces, in pipeline order:
- the cast (names, voices, looks) with defaults, per project;
- the writing rules for the genre and a checker for them (`dialogue_flags`);
- grouping the lines into the video's 10 s clips (`group_lines`), never splitting a line;
- the shot plan per line (`plan_shots`): the speaker's close-up, a wide two-shot on pauses, repeats and the
  ending, all hard cuts; with faces, gestures and gaze. Deterministic, so it costs nothing and never drifts;
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


# ---- timing estimates and clips ---------------------------------------------------------------

LEAD, TAIL, GAP, PAUSE = 0.25, 0.35, 0.32, 0.35
PAUSE_RE = re.compile(r"^\s*(\.\.\.|…)")


def words(text: str) -> int:
    return len(re.findall(r"[\w'’-]+", text or ""))


def line_seconds(text: str, wpm: float) -> float:
    """Spoken length estimate of one line (short lines still take a beat to say)."""
    return max(0.55, words(text) / (wpm / 60) + 0.15)


def _load(secs: list[float], pauses: list[bool], i: int, j: int) -> float:
    """Seconds lines i..j-1 take inside one clip: speech, the gaps between them, the pause beats."""
    return sum(secs[i:j]) + GAP * (j - i - 1) + PAUSE * sum(1 for k in range(i + 1, j) if pauses[k])


def group_lines(lines: list[dict], n_clips: int, wpm: float, clip_len: float = 10.0, stretch: float = 1.0) -> list[list[int]] | None:
    """Split the lines (in order, never splitting one) into exactly n_clips groups, as evenly as possible.
    None when they cannot fit: more lines than clips allow, or too few lines to give every clip one."""
    n = len(lines)
    if n < n_clips or n_clips < 1:
        return None
    secs = [line_seconds(ln["text"], wpm) for ln in lines]
    pauses = [bool(PAUSE_RE.match(ln["text"])) for ln in lines]
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
                load = _load(secs, pauses, i, j)
                v = max(best[k - 1][i], load)
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
    """The script's clips: each carries its lines and, for the rest of the pipeline, the joined text."""
    out = []
    for k, g in enumerate(groups):
        ls = [{"i": i, "speaker": lines[i]["speaker"], "text": lines[i]["text"]} for i in g]
        out.append({"index": k, "stage": "dialogue", "vo": " ".join(ln["text"] for ln in ls), "lines": ls, "beats": []})
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
    return [w for w in re.findall(r"[a-z][a-z'’-]*|\d+", (text or "").lower()) if w not in STOP]


def _bigrams(text: str) -> set[tuple[str, str]]:
    toks = re.findall(r"[a-z][a-z'’-]*|\d+", (text or "").lower())
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
    n_min, n_max = max(4, round(duration / 4)), round(duration / 1.6)
    names = {s: cast[s]["name"] for s in SPEAKERS}
    if not n_min <= n <= n_max:
        flags.append(f"{n} lines for {duration}s; write {n_min}-{n_max} (short lines, quick exchange)")
    if lines and lines[0].get("speaker") != "a":
        flags.append(f"the first line is {names['a']}'s")
    if lines and hook_say and _norm(lines[0].get("text", "")) != _norm(hook_say):
        flags.append(f"line 1 must be the approved hook, word for word: \"{hook_say}\"")
    run = 1
    for k, ln in enumerate(lines):
        if ln.get("speaker") not in SPEAKERS:
            flags.append(f"line {k + 1}: speaker must be \"a\" ({names['a']}) or \"b\" ({names['b']})")
            continue
        wc = words(ln.get("text", ""))
        if wc > MAX_LINE_WORDS:
            flags.append(f"line {k + 1} has {wc} words (max {MAX_LINE_WORDS}; most lines 2-7)")
        if wc == 0:
            flags.append(f"line {k + 1} is empty")
        if "{{" in ln.get("text", ""):
            flags.append(f"line {k + 1} has a {{{{gap}}}}: dialogue never needs a figure from the creator")
        if STAT_LIKE.search(ln.get("text", "")):
            flags.append(f"line {k + 1} sounds like a real-world statistic; keep every number inside the story")
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
        specifics = sum(1 for ln in lines if re.search(r"\d", ln.get("text", "")) or NUMBER_WORDS.search(ln.get("text", "")))
        if specifics < 2:
            flags.append("add oddly specific in-story details: at least 2 lines with a number (counts, times, sizes)")
        if not find_callback(lines):
            flags.append("no callback: a later line should echo an earlier phrase (at least 3 lines apart)")
        turn = res.get("turn")
        if not isinstance(turn, int) or not n / 2 <= turn <= n - 1:
            flags.append(f"mark the turn (the line where the meaning flips) as a line number in the second half (got {turn})")
        opening = set().union(*(set(_content(ln.get("text", ""))) for ln in lines[:3])) | {names["a"].lower(), names["b"].lower()}
        if not set().union(*(set(_content(ln.get("text", ""))) for ln in lines[-2:])) & opening:
            flags.append("the ending should loop back to the opening (reuse a word, a name or the situation from the first lines)")
    title = (res.get("title") or "").strip()
    if not title.endswith("?"):
        flags.append("the title ends with a question to the viewer")
    if title != title.lower():
        flags.append("the title is all lowercase (a quote, then the question)")
    if len(title) > 110:
        flags.append(f"the title is {len(title)} characters (max 110)")
    if n and title and len(set(_content(title)) & set().union(*(set(_content(ln.get("text", ""))) for ln in lines))) < 2:
        flags.append("the title should quote the script (share at least two of its words)")
    if n and group_lines(lines, duration // 10, wpm) is None:
        est = sum(line_seconds(ln.get("text", ""), wpm) for ln in lines) + GAP * max(0, n - 1)
        flags.append(f"the lines do not fit {duration // 10} clips of 10 s (about {est:.0f}s of speech and gaps; "
                     f"{'cut' if n >= duration // 10 else 'add'} lines)")
    return flags


def _norm(t: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (t or "").lower().replace("’", "'")).strip()


# ---- the shot plan --------------------------------------------------------------------------------

def _expr(text: str, speaker: str) -> str:
    t = text.strip()
    if PAUSE_RE.match(t):
        return "thinking" if speaker == "a" else "skeptical"
    if t.endswith("?"):
        return "confused" if speaker == "a" else "surprised"
    if t.endswith("!"):
        return "happy"
    if re.search(r"\b(no|not|never|can't|cannot|wrong|bad|off)\b", t, re.I):
        return "skeptical"
    return "neutral"


def plan_shots(lines: list[dict]) -> list[dict]:
    """Per line: the shot (the speaker's close-up, or "wide"), the speaker's face and a gesture. Rules: start on the
    first speaker's close-up; a wide two-shot when the same person speaks twice in a row (a new angle), on a pause
    beat when the last wide was 3+ lines ago, after 6 close-ups in a row, and for the last two lines (the button)."""
    n, out, since_wide = len(lines), [], 0
    wide_alt = 0
    for k, ln in enumerate(lines):
        s, text = ln["speaker"], ln["text"]
        wide = False
        if k > 0:
            if lines[k - 1]["speaker"] == s:
                wide = True
            elif PAUSE_RE.match(text) and since_wide >= 3:
                wide = True
            elif since_wide >= 6:
                wide = True
            if k >= n - 2 and n >= 4:
                wide = True
        since_wide = 0 if wide else since_wide + 1
        shot = "wide" if wide else s
        if wide:
            wide_alt += 1
        gesture = None
        if s == "a" and (text.strip().endswith("?") or PAUSE_RE.match(text)):
            gesture = "think"            # hand to the cheek
        if s == "b" and text.strip().endswith("!"):
            gesture = "cheer"            # the mascot hops
        out.append({"i": k, "speaker": s, "shot": shot, "wide_variant": wide_alt % 2 if wide else None,
                    "face": _expr(text, s), "gesture": gesture})
    return out


# ---- render-time timing ---------------------------------------------------------------------------

def layout(durs: list[float], pauses: list[bool], clip_len: float = 10.0, max_speedup: float = 1.25) -> dict:
    """Where each voiced line plays inside the clip. Gaps shrink (to 0.12 s) before speech speeds up (up to
    max_speedup); spare time widens the gaps a little (pause beats most), the rest is split before and after."""
    n = len(durs)
    if not n:
        return {"starts": [], "ends": [], "tempo": 1.0, "overflow": 0.0}
    want = [0.0] + [GAP + (PAUSE if pauses[k] else 0.0) for k in range(1, n)]
    speech = sum(durs)
    room = clip_len - LEAD - TAIL
    tempo, gaps = 1.0, list(want)
    if speech + sum(gaps) > room:
        floor = [0.0] + [0.12] * (n - 1)
        over = speech + sum(gaps) - room
        shrinkable = sum(g - f for g, f in zip(gaps, floor))
        if shrinkable >= over:
            gaps = [f + (g - f) * (1 - over / shrinkable) if shrinkable else f for g, f in zip(gaps, floor)]
        else:
            gaps = floor
            tempo = min(max_speedup, speech / max(0.1, room - sum(floor)))
    spoken = [d / tempo for d in durs]
    used = sum(spoken) + sum(gaps)
    lead, overflow = LEAD, max(0.0, used - room)
    spare = max(0.0, room - used)
    if spare > 0 and n > 1:
        weights = [0.0] + [2.0 if pauses[k] else 1.0 for k in range(1, n)]
        extra = min(spare * 0.6, 0.45 * sum(weights))
        gaps = [g + extra * w / sum(weights) for g, w in zip(gaps, weights)]
        spare -= extra
    lead += min(0.35, spare / 2)
    starts, ends, t = [], [], lead
    for d, g in zip(spoken, gaps):
        t += g
        starts.append(round(t, 3))
        t += d
        ends.append(round(min(clip_len, t), 3))
    return {"starts": starts, "ends": ends, "tempo": round(tempo, 3), "overflow": round(overflow, 3)}


# ---- the renderer scene -----------------------------------------------------------------------------

WIDE = [{"pos": [0.4, 1.25, 1.8], "look": [0.1, 0.96, -0.25], "fov": 38},
        {"pos": [-0.42, 1.22, 1.8], "look": [0.08, 0.95, -0.2], "fov": 40}]


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
    for p, t0, t1 in zip(plan, starts, ends):
        s, other = p["speaker"], ("b" if p["speaker"] == "a" else "a")
        cut_at = 0.0 if not cams else round(max(cams[-1]["t"] + 0.4, t0 - 0.12), 3)
        if p["shot"] == "wide":
            key = {"t": cut_at, "cut": True, **WIDE[p.get("wide_variant") or 0], "push": 0.04}
        else:
            side = 0.1 if s == "a" else 0.18          # the mascot's close-up keeps the person in the background
            key = {"t": cut_at, "cut": True, "shot": {"type": "closeup", "target": s, "side": side}, "push": 0.05}
        cams.append(key)
        actor[s]["face"].append({"t": round(max(0.0, t0 - 0.1), 3), "expr": p["face"]})
        actor[s]["face"].append({"t": round(t1 + 0.35, 3), "expr": "neutral"})
        if p.get("gesture") and not still:
            g = {"t": round(t0, 3), "gesture": p["gesture"], "dur": round(max(0.8, t1 - t0 + 0.4), 3)}
            if p["gesture"] == "think":
                g["side"] = "R"
            actor[s]["gestures"].append(g)
        # gaze: the person watches the mascot; the mascot turns to her while she talks and is back facing the
        # camera before its own close-up cuts in (so the turn never happens on screen)
        if still:
            pass                                          # gaze stays put: she watches the mascot, it faces the camera
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
            "camera": cams or [{"t": 0, "cut": True, "shot": {"type": "closeup", "target": "a"}}],
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
    """Every line with its absolute start/end in the video: from the render's timing when there is one, otherwise
    spread over the clip by word count (dry run)."""
    out = []
    for k, lines in enumerate(clip_lines):
        meta = (clips_meta[k] or {}).get("meta", {}) if k < len(clips_meta) else {}
        timed = meta.get("lines") or []
        if len(timed) == len(lines) and all("start" in x for x in timed):
            for ln, tm in zip(lines, timed):
                out.append({**ln, "start": round(starts[k] + tm["start"], 3), "end": round(starts[k] + tm["end"], 3)})
            continue
        w = [max(1, words(ln["text"])) for ln in lines]
        span = max(1.0, lengths[k] - LEAD - TAIL)
        t = starts[k] + LEAD
        for ln, n in zip(lines, w):
            d = span * n / sum(w)
            out.append({**ln, "start": round(t, 3), "end": round(t + d * 0.9, 3)})
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
