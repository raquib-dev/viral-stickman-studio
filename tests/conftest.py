"""Point the app at throwaway folders BEFORE any backend module is imported, so tests never touch
config/settings.json, projects/ or data/."""
import json
import os
import shutil
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_TMP = Path(tempfile.mkdtemp(prefix="vss-tests-"))
_settings = json.loads((ROOT / "config" / "settings.json").read_text())
_settings.update({"dry_run": True})
_settings["gates"] = {k: "auto" for k in _settings["gates"]}
_settings["render"]["backend"] = "mock"
(_TMP / "settings.json").write_text(json.dumps(_settings))
os.environ["VSS_SETTINGS_FILE"] = str(_TMP / "settings.json")
os.environ["VSS_DATA_DIR"] = str(_TMP / "data")
os.environ["VSS_PROJECTS_DIR"] = str(_TMP / "projects")
for k in ("ANTHROPIC_API_KEY", "GEMINI_API_KEY", "FAL_KEY", "YOUTUBE_API_KEY"):
    os.environ.pop(k, None)

import pytest  # noqa: E402


@pytest.fixture(scope="session")
def tmp_root() -> Path:
    return _TMP


def pytest_sessionfinish(session, exitstatus):
    shutil.rmtree(_TMP, ignore_errors=True)
