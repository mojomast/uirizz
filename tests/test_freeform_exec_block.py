"""Decision 2, option (b): a free-form yes never unlocks shell, exec or code tools.

A free-form (undeclared) card action is not bound to any tool call, so the
user's yes on it says nothing about which command may run. For the approval
window after such a yes, exec-like tools stay blocked unless a declared action
the user approved covers that exact call. Other tools keep today's behaviour
(option (c), denying every free-form side effect, is a separate 0.2.0 change).
"""

from __future__ import annotations

import pytest

from uirizz_plugin import actions, bindings, gate
from uirizz_plugin.hooks import pre_llm_call, pre_tool_call
from uirizz_plugin.store import put_surface, set_store_dir

SID = "sess-freeform-exec"
SURF = "surf-freeform-exec"

ACTIONS_YAML = """
actions:
  run_tests:
    title: "Run the test suite"
    tool: terminal
    args: {command: "pytest -q"}
    risk: high
"""


@pytest.fixture(autouse=True)
def _env(tmp_path):
    set_store_dir(tmp_path)
    bindings.set_actions_dir(tmp_path)
    (tmp_path / "actions.yaml").write_text(ACTIONS_YAML, encoding="utf-8")
    getattr(actions, "_PENDING", {}).clear()
    put_surface({"surface_id": SURF, "revision": 1, "fallback_text": "Card", "messages": [],
                 "component_count": 1, "component_ids": ["root"]})
    yield
    bindings.set_actions_dir(None)
    for name in list(bindings._api_defs):
        bindings.unregister_action(name)
    set_store_dir(None)


def _click(event, context):
    return actions.record_action(surface_id=SURF, session_id=SID, event=event, context=context)


def _turn(text):
    out = pre_llm_call(session_id=SID, user_message=text)
    return (out or {}).get("context", "")


def _call(tool, args, call_id="call-1"):
    return pre_tool_call(session_id=SID, tool_name=tool, args=args, tool_call_id=call_id)


def _act(action_id):
    return next(a for a in gate.session_actions(None) if a["action_id"] == action_id)


def _approve_free_form():
    rec = _click("deploy", {"side_effect": True})
    _turn("hi")
    _turn(f"yes {gate._short(rec['action_id'])}")
    assert _act(rec["action_id"])["status"] == "approved"
    return rec


@pytest.mark.parametrize(
    "tool,args",
    [("terminal", {"command": "deploy prod"}), ("execute_code", {"code": "print(1)"}),
     ("mcp_box_run_shell", {"cmd": "ls"}), ("process_manage", {"op": "spawn"})],
)
def test_free_form_yes_does_not_unlock_exec_tools(tool, args):
    rec = _approve_free_form()
    out = _call(tool, args)
    assert out is not None and out["action"] == "block"
    assert "free-form" in out["message"]
    assert gate._short(rec["action_id"]) in out["message"]


def test_exec_tools_stay_blocked_after_the_agent_marks_it_done():
    rec = _approve_free_form()
    gate.complete_action(rec["action_id"], "done")
    out = _call("terminal", {"command": "deploy prod"})
    assert out is not None and out["action"] == "block"


def test_free_form_yes_still_allows_non_exec_tools():
    _approve_free_form()
    assert _call("send_message", {"to": "kyle", "text": "deployed"}) is None


def test_a_declared_action_covers_its_exact_exec_call():
    _approve_free_form()
    rec = _click("run_tests", {})
    _turn("hi")
    _turn(f"yes {gate._short(rec['action_id'])}")
    assert _act(rec["action_id"])["status"] == "approved"
    other = _call("terminal", {"command": "rm -rf build"})
    assert other is not None and other["action"] == "block"
    assert _call("terminal", {"command": "pytest -q"}) is None


def test_denied_free_form_action_unlocks_nothing_and_blocks_nothing():
    rec = _click("deploy", {"side_effect": True})
    _turn("hi")
    _turn(f"no {gate._short(rec['action_id'])}")
    assert _act(rec["action_id"])["status"] == "denied"
    assert _call("terminal", {"command": "ls"}) is None


def test_block_ends_with_the_approval_window(monkeypatch):
    _approve_free_form()
    real_now = gate._now()
    monkeypatch.setattr(gate, "_now", lambda: real_now + gate.APPROVAL_TTL_S + 1)
    assert _call("terminal", {"command": "ls"}) is None
