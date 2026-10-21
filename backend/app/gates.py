"""Gates: approval points tied to the exact payload that was approved.

A downstream stage calls ctx.require_gate(name, payload, ...). If the gate was approved for the same
payload hash, the stored choice is returned. If the payload changed (an edited Phase A, a new ratio or
style), the gate re-opens: the director skill's rule "a global change invalidates approval".

Gate mode per gate in settings: "pause" waits for the user; "auto" decides with the default choice
(top-ranked topic, top-scored hook, Phase A as written). The paid render gate only auto-approves when
the estimate is within the budget cap (the render stage passes auto_allowed accordingly).
"""
from __future__ import annotations

import hashlib
import json
import time
from typing import Any

from . import db
from .jobs import GatePending, bus

GATES = {
    "topic": "Pick the topic",
    "hook": "Pick the hook",
    "phase_a": "Approve the director's Phase A",
    "render_cost": "Confirm the render cost",
}
# the stage whose job opens each gate (and has to run again once it is approved)
GATE_STAGE = {"topic": "hooks", "hook": "script", "phase_a": "direction_b", "render_cost": "render"}


def payload_hash(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()[:16]


def require(ctx, name: str, payload: Any, options: list | None, default_choice: Any,
            auto_allowed: bool, auto_reason: str) -> Any:
    h = payload_hash(payload)
    g = db.get_gate(ctx.project, name)
    if g and g["status"] == "approved" and g["payload_hash"] == h:
        ctx.log(f"gate '{name}' already approved ({g['decided_by']})")
        return g["choice"]
    mode = ctx.settings.get("gates", {}).get(name, "pause")
    record = {"payload": {"data": payload, "options": options, "default_choice": default_choice},
              "payload_hash": h, "opened_at": time.time()}
    if mode == "auto" and auto_allowed:
        db.put_gate(ctx.project, name, status="approved", choice=default_choice, note=auto_reason or "auto by setting",
                    decided_by="auto (setting)", decided_at=time.time(), **record)
        ctx.log(f"gate '{name}' auto-approved by your setting" + (f": {auto_reason}" if auto_reason else ""), "gate")
        bus.publish(ctx.project, {"type": "gate", "name": name, "status": "approved", "decided_by": "auto"})
        return default_choice
    if mode == "auto" and not auto_allowed:
        ctx.log(f"gate '{name}' is set to auto but cannot auto-approve: {auto_reason}", "warn")
    if g and g["status"] == "approved" and g["payload_hash"] != h:
        ctx.log(f"gate '{name}' re-opened: the content changed since you approved it", "gate")
    db.put_gate(ctx.project, name, status="pending", choice=None, note=None, decided_by=None, decided_at=None, **record)
    bus.publish(ctx.project, {"type": "gate", "name": name, "status": "pending"})
    raise GatePending(name)


def decide(project: str, name: str, action: str, choice: Any = None, note: str = "") -> dict:
    if name not in GATES:
        raise KeyError(name)
    g = db.get_gate(project, name)
    if not g:
        raise ValueError(f"gate {name} has not been opened yet")
    if action == "approve":
        if choice is None:
            choice = g["payload"].get("default_choice")
        opts = g["payload"].get("options")
        if opts is not None and choice is not None and choice not in [o.get("id") if isinstance(o, dict) else o for o in opts]:
            raise ValueError(f"choice {choice!r} is not one of the gate's options")
        db.put_gate(project, name, status="approved", choice=choice, note=note, decided_by="you", decided_at=time.time())
    elif action == "reject":
        db.put_gate(project, name, status="rejected", choice=None, note=note, decided_by="you", decided_at=time.time())
    else:
        raise ValueError("action must be approve or reject")
    bus.publish(project, {"type": "gate", "name": name, "status": "approved" if action == "approve" else "rejected"})
    return db.get_gate(project, name)


def reopen_with_payload(project: str, name: str, payload: Any) -> None:
    """Used when the user edits gated content in the UI before approving (e.g. Phase A text)."""
    g = db.get_gate(project, name)
    if not g:
        return
    data = dict(g["payload"])
    data["data"] = payload
    db.put_gate(project, name, payload=data, payload_hash=payload_hash(payload), status="pending")
