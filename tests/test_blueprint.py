"""Validate docs/research/virality-blueprint.json against its JSON Schema and the rules the app relies on."""
import json
import re
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
RESEARCH = ROOT / "docs" / "research"
BLUEPRINT = json.loads((RESEARCH / "virality-blueprint.json").read_text(encoding="utf-8"))
SCHEMA = json.loads((RESEARCH / "virality-blueprint.schema.json").read_text(encoding="utf-8"))

REQUIRED_TYPES = {
    "hook-placement", "rehook-cadence", "pattern-interrupt-cadence", "callout-placement",
    "deliberate-mistake-placement", "stakes-line", "payoff-timing", "cta-placement", "loop-ending",
}


def test_schema_is_valid_draft_2020_12():
    Draft202012Validator.check_schema(SCHEMA)


def test_blueprint_matches_schema():
    errors = sorted(Draft202012Validator(SCHEMA).iter_errors(BLUEPRINT), key=lambda e: list(e.path))
    assert not errors, "\n".join(f"{list(e.path)}: {e.message}" for e in errors)


def test_every_required_rule_type_is_covered():
    assert REQUIRED_TYPES <= {r["type"] for r in BLUEPRINT["rules"]}


def test_rule_ids_are_unique():
    ids = [r["id"] for r in BLUEPRINT["rules"]]
    assert len(ids) == len(set(ids))


@pytest.mark.parametrize("rule", BLUEPRINT["rules"], ids=lambda r: r["id"])
def test_regex_patterns_compile(rule):
    for pattern in rule["how_to_detect"].get("patterns", []):
        re.compile(pattern)


@pytest.mark.parametrize("rule", BLUEPRINT["rules"], ids=lambda r: r["id"])
def test_timing_window_is_ordered(rule):
    t = rule["timing"]
    if "from" in t and "to" in t:
        assert t["from"] <= t["to"]
    if "min_count" in t and "max_count" in t:
        assert t["min_count"] <= t["max_count"]


@pytest.mark.parametrize("rule", BLUEPRINT["rules"], ids=lambda r: r["id"])
def test_repo_evidence_points_at_real_files(rule):
    for ev in rule["evidence"]:
        if ev["url"].startswith("repo:"):
            rel = ev["url"][5:]
            if rel.startswith("vendor/"):
                continue  # read-only references, gitignored; fetched by scripts/fetch_vendor.sh
            assert (ROOT / rel).exists(), f"{rule['id']}: missing {rel}"


def test_web_evidence_is_cited_in_research_docs():
    """Every external URL in the blueprint must appear in one of the research write-ups, so no number
    or claim enters the rulebook without its written context."""
    corpus = "".join(p.read_text(encoding="utf-8") for p in RESEARCH.glob("*.md"))
    missing = sorted({ev["url"] for r in BLUEPRINT["rules"] for ev in r["evidence"]
                      if ev["url"].startswith("https://") and ev["url"] not in corpus})
    assert not missing, f"URLs not cited in docs/research/*.md: {missing}"


def test_lore_only_rules_are_never_mandatory():
    for r in BLUEPRINT["rules"]:
        if {ev["strength"] for ev in r["evidence"]} <= {"lore"}:
            assert r.get("severity") != "must", f"{r['id']} rests on lore alone"
