"""End-to-end dry run: personal finance psychology, stickman, 60s, 9:16, Style 1 dark.
FixtureAgent + mock render; real pack tools, real ffmpeg; gates on auto (set in conftest)."""
import json

import pytest

from backend.app import db, paths, pipeline
from backend.app.jobs import manager

pytestmark = pytest.mark.e2e


async def test_full_pipeline_niche_to_package():
    await manager.start()
    slug = "e2e-sample"
    data = {"name": "E2E sample", "niche": "personal finance psychology", "subtopics": ["saving", "spending"],
            "platforms": ["shorts", "reels"], "style": "1", "theme": "dark", "ratio": "9:16", "duration": 60,
            "competitors": {"youtube": [], "instagram": []}, "voice_pref": "male",
            "voice_transcripts": {"youtube": ["My own transcript, I'd say it like this."], "instagram": []}}
    db.upsert_project(slug, data["name"], data)
    pipeline.start(slug)
    await pipeline._tasks[slug]
    pl = db.get_pipeline(slug)
    assert pl["status"] == "completed", pl
    statuses = {s["stage"]: s["status"] for s in pipeline.stage_status(slug)}
    assert all(statuses[s] == "succeeded" for s in pipeline.PIPELINE), statuses

    root = paths.project_dir(slug)
    for rel in ["project.json", "research/discovery.json", "research/niche-profile.json", "research/topics.json",
                "research/voice-draft-youtube.md", "script/hooks.json", "script/script.json", "script/beats.json",
                "direction/phase-a.md", "direction/phase-b.md", "direction/prompts/clip-06.txt",
                "clips/clip-06.mp4", "final/final.mp4", "final/final.srt", "package/copy-blocks.md"]:
        assert (root / rel).exists(), rel

    disc = json.loads((root / "research/discovery.json").read_text())
    assert disc["synthetic"] is True and disc["youtube"]["outliers"]
    script = json.loads((root / "script/script.json").read_text())
    assert len(script["clips"]) == 6 and script["flags"] == [], script["flags"]
    assert all(12 <= len(c["vo"].split()) <= 25 for c in script["clips"])
    b = json.loads((root / "direction/phase-b.json").read_text())
    assert b["checks"] == [] and all(b["character_anchor"] in p["text"] for p in b["prompts"])
    loud = json.loads((root / "final/loudness.json").read_text())
    assert abs(loud["duration"] - 60.0) <= 0.5
    assert (loud["width"], loud["height"]) == (720, 1280)
    assert abs(loud["after_i"] - (-16.0)) <= 1.0
    assert loud["safe_zone_violations"] == []
    pkg = json.loads((root / "package/package.json").read_text())
    assert pkg["best"]["title"] and pkg["policy_notes"]
    assert {g["name"] for g in db.list_gates(slug)} == {"topic", "hook", "phase_a"}  # mock render is free: no cost gate
    await manager.stop()
