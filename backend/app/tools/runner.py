"""Thin, typed wrappers around the vendored skill-pack Python tools.

Every tool is called as a subprocess with `sys.executable` (never a bare `python`, which is a Store
stub on some Windows machines) and `--json`. Exit-code policy (docs/repo-analysis.md C14): several
tools exit 1 to mean "verdict is not PASS/READY/STRONG"; that is a result, not an error. We trust the
JSON on stdout and raise only when there is none.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from ..paths import SKILLS


class ToolError(RuntimeError):
    pass


def tool_path(skill: str, script: str) -> Path:
    p = SKILLS / skill / script
    if not p.exists():
        raise ToolError(f"vendored tool missing: {p}")
    return p


def run_tool(skill: str, script: str, args: list[str], stdin: str | None = None,
             timeout: float = 120) -> Any:
    cmd = [sys.executable, "-X", "utf8", str(tool_path(skill, script)), *args]
    env = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}
    proc = subprocess.run(cmd, input=stdin, capture_output=True, text=True, encoding="utf-8",
                          timeout=timeout, env=env, cwd=str(SKILLS / skill))
    out = proc.stdout.strip()
    if proc.returncode not in (0, 1) or not out:
        raise ToolError(f"{skill}/{script} exited {proc.returncode}: {proc.stderr.strip()[:400]}")
    try:
        return json.loads(out)
    except json.JSONDecodeError as e:
        raise ToolError(f"{skill}/{script} returned non-JSON output: {out[:200]}") from e


def _tmp(text: str, suffix: str) -> str:
    fd, path = tempfile.mkstemp(suffix=suffix, prefix="vss-")
    with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    return path


def _with_file(text: str, suffix: str, fn):
    path = _tmp(text, suffix)
    try:
        return fn(path)
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


# ---- hooks ----------------------------------------------------------------------------------

def yt_hookscore(hooks: list[str]) -> list[dict]:
    """YouTube panel: SPECIFICITY/ADDRESS/STAKES/CURIOSITY/BREVITY + formula (21)."""
    hooks = [h.replace("\n", " ").strip() for h in hooks if h.strip()]
    if not hooks:
        return []
    res = _with_file("\n".join(hooks) + "\n", ".txt", lambda p: run_tool("yt-script", "hookscore.py", ["--json", p]))
    return res if isinstance(res, list) else [res]


def ig_hookscore(hooks: list[str]) -> list[dict]:
    """Instagram panel: LENGTH/SPECIFICITY/STAKES/FRONTLOAD/ADDRESS + dealbreakers."""
    hooks = [h.replace("\n", " ").strip() for h in hooks if h.strip()]
    if not hooks:
        return []
    res = _with_file("\n".join(hooks) + "\n", ".txt", lambda p: run_tool("ig-reel", "hookscore.py", ["--json", p]))
    return res if isinstance(res, list) else [res]


def ig_formula(hooks: list[str]) -> dict[str, dict]:
    """Classify hooks with ig-reel/hooks.json via ig-viral/swipe.py (the tool that owns that classifier)."""
    hooks = [h.replace("\n", " ").replace("\t", " ").strip() for h in hooks if h.strip()]
    if not hooks:
        return {}
    tsv = "account\tmedian\tviews\thook\n" + "".join(f"@x\t1\t1\t{h}\n" for h in hooks)
    res = _with_file(tsv, ".tsv", lambda p: run_tool("ig-viral", "swipe.py", ["--json", p]))
    return {r["hook"]: {"id": r.get("formula_id"), "name": r.get("formula")} for r in res["reels"]}


# ---- script ---------------------------------------------------------------------------------

def beats(script_text: str, wpm: float = 150, target: float | None = None) -> dict:
    args = ["--json", "--wpm", str(wpm)]
    if target:
        args += ["--target", str(target)]
    return _with_file(script_text, ".txt", lambda p: run_tool("ig-reel", "beats.py", [p, *args]))


def humanize(text: str) -> dict:
    return _with_file(text, ".txt", lambda p: run_tool("ig-human", "humanize.py", [p, "--json"]))


def detect(text: str) -> dict:
    return _with_file(text, ".txt", lambda p: run_tool("ig-human", "detect.py", [p, "--json"]))


# ---- discovery ------------------------------------------------------------------------------

def yt_swipe(rows: list[dict], min_multiple: float = 2.0) -> dict:
    return _with_file(json.dumps(rows), ".json",
                      lambda p: run_tool("yt-viral", "swipe.py", [p, "--min", str(min_multiple), "--json"]))


def ig_swipe(tsv_path: Path, out_md: Path | None = None) -> dict:
    args = [str(tsv_path), "--json"]
    if out_md:
        args += ["--out", str(out_md)]
    return run_tool("ig-viral", "swipe.py", args)


# ---- packaging / learn ----------------------------------------------------------------------

def title_lint(titles: list[str], thumb: str | None = None) -> list[dict]:
    args = ["--json"]
    if thumb:
        args += ["--thumb", thumb]
    titles = [t.replace("\n", " ").strip() for t in titles if t.strip()]
    return _with_file("\n".join(titles) + "\n", ".txt", lambda p: run_tool("yt-package", "title.py", [p, *args]))


def chapters(srt_text: str, target: int = 7) -> dict:
    return _with_file(srt_text, ".srt", lambda p: run_tool("yt-chapters", "chapters.py", [p, "--target", str(target), "--json"]))


def caption_lint(text: str, keywords: list[str] | None = None) -> dict:
    args = ["--json"]
    if keywords:
        args += ["--keywords", ",".join(keywords)]
    return _with_file(text, ".txt", lambda p: run_tool("ig-caption", "caption.py", [p, *args]))


def retention(csv_path: Path, srt_path: Path | None = None, duration: float | None = None) -> dict:
    args = [str(csv_path), "--json"]
    if srt_path:
        args += ["--transcript", str(srt_path)]
    if duration:
        args += ["--duration", str(duration)]
    return run_tool("yt-retention", "retention.py", args)


def deadair(srt_text: str) -> dict:
    return _with_file(srt_text, ".srt", lambda p: run_tool("yt-edit", "deadair.py", [p, "--json"]))
