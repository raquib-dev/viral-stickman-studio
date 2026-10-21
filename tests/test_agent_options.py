"""The live Agent SDK path cannot call Claude in CI, but its options must be valid for the installed SDK."""
from backend.app.agent import tasks
from backend.app.agent.runner import DENIED_TOOLS, build_options
from backend.app.paths import REPO_ROOT, SKILLS
from backend.app.settings import load_settings


def test_options_load_project_skills_read_only_with_structured_output():
    t = tasks.phase_a("T", [{"index": 0, "stage": "golden-hook", "vo": "x"}], "9:16", 10, "1", "dark", [], "male")
    o = build_options(t, load_settings())
    assert o.cwd == str(REPO_ROOT) and o.setting_sources == ["user", "project"]
    assert o.skills == ["directing-stickman-videos"] and (SKILLS / "directing-stickman-videos" / "SKILL.md").exists()
    assert o.permission_mode == "dontAsk"
    assert set(DENIED_TOOLS) <= set(o.disallowed_tools) and "Write" not in o.allowed_tools
    assert o.output_format["type"] == "json_schema" and o.output_format["schema"]["required"]
    assert o.model == load_settings()["models"]["direction"]
    assert "Never publish" in o.system_prompt["append"]


def test_every_task_names_only_vendored_skills():
    built = [tasks.voice_draft("youtube", ["x"], "n"), tasks.discovery_read("youtube", {}, "n"),
             tasks.topic_candidates("n", [], [], []), tasks.hooks({}, "n", "shorts", []),
             tasks.script({}, {}, 60, "shorts", [], [], "n"), tasks.structural_rewrite("x", []),
             tasks.phase_b("md", [], "9:16", 60, "1", "dark", {}),
             tasks.package("t", "n", {}, {}, 60, [], []), tasks.learn_read(None, "", [], 60)]
    for t in built:
        for s in t.skills:
            assert (SKILLS / s / "SKILL.md").exists(), (t.name, s)
