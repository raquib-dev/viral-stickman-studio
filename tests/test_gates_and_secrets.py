import json

import pytest

from backend.app import db, gates, settings
from backend.app.jobs import GatePending


class Ctx:
    def __init__(self, mode="pause"):
        self.project = "gate-unit"
        self.settings = {"gates": {"phase_a": mode}}
        self.logs = []

    def log(self, t, level="info"):
        self.logs.append(t)


def test_gate_pause_then_approve_then_reopen_on_change():
    c = Ctx()
    with pytest.raises(GatePending):
        gates.require(c, "phase_a", {"sha": "1"}, None, "approved", True, "")
    gates.decide(c.project, "phase_a", "approve")
    assert gates.require(c, "phase_a", {"sha": "1"}, None, "approved", True, "") == "approved"
    with pytest.raises(GatePending):  # an edited Phase A invalidates the approval
        gates.require(c, "phase_a", {"sha": "2"}, None, "approved", True, "")
    assert any("re-opened" in t for t in c.logs)


def test_gate_auto_mode_and_refusal():
    c = Ctx("auto")
    c.project = "gate-auto"
    assert gates.require(c, "phase_a", {"x": 1}, None, "approved", True, "test") == "approved"
    c.project = "gate-auto-2"
    with pytest.raises(GatePending):
        gates.require(c, "phase_a", {"x": 1}, None, "approved", False, "over budget")


def test_gate_choice_must_be_an_option():
    c = Ctx()
    c.project = "gate-opts"
    c.settings = {"gates": {"topic": "pause"}}
    with pytest.raises(GatePending):
        gates.require(c, "topic", {"t": [1]}, [{"id": "a"}, {"id": "b"}], "a", True, "")
    with pytest.raises(ValueError):
        gates.decide(c.project, "topic", "approve", choice="zzz")
    assert gates.decide(c.project, "topic", "approve", choice="b")["choice"] == "b"


def test_keys_are_redacted_and_never_public(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "AIzaSyTESTKEY1234567890abcdefghij")
    settings.reload_env()
    try:
        assert "[REDACTED]" in settings.redact("key=AIzaSyTESTKEY1234567890abcdefghij")
        jid = db.create_job("redact", "niche")
        row = db.add_log(jid, "info", "calling with AIzaSyTESTKEY1234567890abcdefghij")
        assert "AIzaSy" not in row["text"]
        assert "AIzaSy" not in json.dumps(db.job_logs(jid))
        pub = settings.public_settings()
        assert pub["keys"]["gemini_api_key"] is True and "AIzaSy" not in json.dumps(pub)
        assert "[REDACTED]" in settings.redact("sk-ant-abcdefghijklmnop")
    finally:
        monkeypatch.delenv("GEMINI_API_KEY")
        settings.reload_env()


def test_settings_reject_secrets():
    with pytest.raises(ValueError):
        settings.validate_settings({**settings.load_settings(), "gemini_api_key": "x"})
