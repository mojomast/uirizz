"""Track C items 16 and 17: log rotation keeps the gate's state, and the
read-decide-write steps are atomic across processes.

The concurrency tests fork real processes (the dashboard REST router and the
agent's hooks can run in different Hermes processes) and slow the read step
down so that, without a cross-process lock, every process decides on the same
stale view.
"""

from __future__ import annotations

import multiprocessing as mp
import sys
import time

import pytest

from uirizz_plugin import actions, bindings, gate
from uirizz_plugin.hooks import post_tool_call, pre_llm_call, pre_tool_call
from uirizz_plugin.store import put_surface, set_store_dir

SID = "sess-conc"
SURF = "surf-conc"

ACTIONS_YAML = """
actions:
  snooze_alert:
    title: "Snooze {alert}"
    tool: mcp_pagerduty_snooze
    args: {incident_id: "{alert}", duration: 30}
    params:
      alert: {type: string, pattern: "^INC-[0-9]+$"}
    risk: low
    auto_approve: true
  send_note:
    title: "Send a note to {to}"
    tool: send_message
    args: {to: "{to}"}
    params:
      to: {type: string, pattern: "^[a-z]+$"}
    risk: low
    limits: {per_hour: 2}
"""

fork_only = pytest.mark.skipif(
    sys.platform == "win32" or "fork" not in mp.get_all_start_methods(),
    reason="needs fork and POSIX file locks",
)


@pytest.fixture(autouse=True)
def _env(tmp_path):
    set_store_dir(tmp_path)
    bindings.set_actions_dir(tmp_path)
    (tmp_path / "actions.yaml").write_text(ACTIONS_YAML, encoding="utf-8")
    getattr(actions, "_PENDING", {}).clear()
    for surf in (SURF, "s2", "s3"):
        put_surface({"surface_id": surf, "revision": 1, "fallback_text": "Card", "messages": [],
                     "component_count": 1, "component_ids": ["root"]})
    yield tmp_path
    bindings.set_actions_dir(None)
    set_store_dir(None)


def _click(event, context, surface=SURF):
    return actions.record_action(surface_id=surface, session_id=SID, event=event, context=context)


def _act(action_id):
    return next(a for a in gate.session_actions(None) if a["action_id"] == action_id)


def _code(rec):
    return rec["action_id"].replace("act-", "")[:6]


def _fill_until_rotated(tmp_path, monkeypatch):
    """Append unrelated entries until the log rolls over at least once."""
    monkeypatch.setattr(gate, "MAX_LOG_BYTES", 6000)
    backup = tmp_path / "audit" / "actions.jsonl.1"
    for i in range(400):
        gate._append({"type": "note", "action_id": f"act-filler{i:04d}", "note": "x" * 40})
        if backup.exists():
            return
    raise AssertionError("log never rotated")


# ------------------------------------------------------------- item 16


def test_rotation_keeps_a_pending_action_pending(tmp_path, monkeypatch):
    rec = _click("deploy", {"side_effect": True})
    pre_llm_call(session_id=SID, user_message="hi")
    _fill_until_rotated(tmp_path, monkeypatch)
    assert _act(rec["action_id"])["status"] == "pending_confirmation"
    blocked = pre_tool_call(session_id=SID, tool_name="terminal", args={"command": "ls"})
    assert blocked and blocked["action"] == "block"
    pre_llm_call(session_id=SID, user_message="yes " + _code(rec))
    assert _act(rec["action_id"])["status"] == "approved"  # announced flag survived too


def test_rotation_keeps_the_hourly_rate_limit(tmp_path, monkeypatch):
    for surf in (SURF, "s2"):
        rec = _click("send_note", {"to": "kyle"}, surface=surf)
        pre_llm_call(session_id=SID, user_message="hm")
        pre_llm_call(session_id=SID, user_message="yes " + _code(rec))
        assert _act(rec["action_id"])["status"] == "approved"
        assert pre_tool_call(session_id=SID, tool_name="send_message", args={"to": "kyle"},
                             tool_call_id=f"c-{surf}") is None
        post_tool_call(session_id=SID, tool_name="send_message", args={"to": "kyle"},
                       tool_call_id=f"c-{surf}", status="ok")
    _fill_until_rotated(tmp_path, monkeypatch)
    third = _click("send_note", {"to": "kyle"}, surface="s3")
    assert third["status"] == "rejected" and "rate limit" in third["rejected"]


def test_rotation_keeps_the_replay_block(tmp_path, monkeypatch):
    rec = _click("snooze_alert", {"alert": "INC-7"})
    args = {"incident_id": "INC-7", "duration": 30}
    assert pre_tool_call(session_id=SID, tool_name="mcp_pagerduty_snooze", args=args, tool_call_id="c1") is None
    post_tool_call(session_id=SID, tool_name="mcp_pagerduty_snooze", args=args, tool_call_id="c1", status="ok")
    assert _act(rec["action_id"])["status"] == "completed"
    _fill_until_rotated(tmp_path, monkeypatch)
    replay = pre_tool_call(session_id=SID, tool_name="mcp_pagerduty_snooze", args=args, tool_call_id="c2")
    assert replay and replay["action"] == "block" and "already" in replay["message"]


def test_rotated_log_starts_with_a_link_to_the_old_chain(tmp_path, monkeypatch):
    _click("deploy", {"side_effect": True})
    _fill_until_rotated(tmp_path, monkeypatch)
    old = gate._read_lines(tmp_path / "audit" / "actions.jsonl.1")
    import json

    first = json.loads(gate._read_lines(tmp_path / "audit" / "actions.jsonl")[0])
    assert first["type"] == "rotated"
    assert first["prev"] == json.loads(old[-1])["hash"]
    assert gate.verify_chain()["ok"] is True


# ------------------------------------------------------------- item 17


def _slow_reads(delay=0.25):
    real = gate.session_actions

    def slow(*a, **kw):
        time.sleep(delay)  # let the other processes append first
        out = real(*a, **kw)
        time.sleep(delay)  # and decide on a view that is already stale
        return out

    gate.session_actions = slow  # child process only


def _child_consume(barrier, results, args):
    _slow_reads()
    barrier.wait()
    out = pre_tool_call(session_id=SID, tool_name="mcp_pagerduty_snooze", args=args, tool_call_id=None)
    results.put("ran" if out is None else "blocked")


def _child_click(barrier, results):
    _slow_reads()
    barrier.wait()
    rec = _click("deploy", {"side_effect": True})
    results.put(rec["action_id"])


def _run(target, n, *extra):
    ctx = mp.get_context("fork")
    barrier, results = ctx.Barrier(n), ctx.Queue()
    procs = [ctx.Process(target=target, args=(barrier, results, *extra)) for _ in range(n)]
    for p in procs:
        p.start()
    out = [results.get(timeout=60) for _ in procs]
    for p in procs:
        p.join(timeout=60)
    return out


@fork_only
def test_one_approval_is_consumed_once_across_processes():
    rec = _click("snooze_alert", {"alert": "INC-9"})
    assert rec["status"] == "approved"
    args = {"incident_id": "INC-9", "duration": 30}
    out = _run(_child_consume, 4, args)
    assert sorted(out) == ["blocked", "blocked", "blocked", "ran"]
    assert _act(rec["action_id"])["status"] == "executing"


@fork_only
def test_concurrent_clicks_on_one_control_leave_one_pending():
    ids = _run(_child_click, 4)
    statuses = sorted(_act(i)["status"] for i in ids)
    assert statuses == ["pending_confirmation", "superseded", "superseded", "superseded"]


def test_rate_limit_is_checked_again_when_the_user_approves():
    recs = [_click("send_note", {"to": "kyle"}, surface=s) for s in (SURF, "s2", "s3")]
    assert all(r["status"] == "pending_confirmation" for r in recs)  # none approved yet
    pre_llm_call(session_id=SID, user_message="hm")
    for rec in recs:
        pre_llm_call(session_id=SID, user_message="yes " + _code(rec))
    statuses = [_act(r["action_id"])["status"] for r in recs]
    assert statuses == ["approved", "approved", "rejected"]
    assert "rate limit" in (_act(recs[2]["action_id"])["rejected"] or "")
