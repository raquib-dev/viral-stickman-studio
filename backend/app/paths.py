"""Filesystem layout. Every project lives in projects/<slug>/ so it is inspectable outside the app."""
from __future__ import annotations

import os
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SKILLS = REPO_ROOT / ".claude" / "skills"
CONFIG = REPO_ROOT / "config"
DOCS = REPO_ROOT / "docs"
BLUEPRINT = DOCS / "research" / "virality-blueprint.json"
# Overridable so tests (and multiple installs) never touch the real folders.
PROJECTS = Path(os.environ.get("VSS_PROJECTS_DIR") or REPO_ROOT / "projects")
DATA = Path(os.environ.get("VSS_DATA_DIR") or REPO_ROOT / "data")
FRONTEND_DIST = REPO_ROOT / "frontend" / "dist"

SUBDIRS = ("research", "script", "direction", "clips", "final", "package")


def slugify(text: str, max_len: int = 40) -> str:
    """Short, Windows-safe folder names."""
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return (s[:max_len].rstrip("-")) or "project"


def project_dir(slug: str) -> Path:
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,39}", slug):
        raise ValueError(f"invalid project slug: {slug!r}")
    return PROJECTS / slug


def ensure_project_dirs(slug: str) -> Path:
    root = project_dir(slug)
    for sub in SUBDIRS:
        (root / sub).mkdir(parents=True, exist_ok=True)
    return root


def safe_project_path(slug: str, rel: str) -> Path:
    """Resolve a path inside a project folder, refusing anything that escapes it."""
    root = project_dir(slug).resolve()
    p = (root / rel).resolve()
    if root != p and root not in p.parents:
        raise ValueError("path escapes project folder")
    return p
