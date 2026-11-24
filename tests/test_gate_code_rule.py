"""Track C items 14 and 19: a bare yes is only enough for one low-risk declared
action; auto_approve is refused for shell, exec and code-execution tools.

Both rules only tighten the gate. Anything they reject stays pending (or needs
the user's typed yes), never the other way round.
"""

from __future__ import annotations

import pytest

from uirizz_plugin import actions, bindings, gate
from uirizz_plugin.hooks import pre_llm_call
from uirizz_plugin.store import put_surface, set_store_dir

SID = "sess-code-rule"
SURF = "surf-code-rule"

ACTIONS_YAML = """
actions:
  send_note:
    title: "Send a note to {to}"
    tool: send_message
    args: {to: "{to}"}
    params:
      to: {type: string, pattern: "^[a-z]+$"}
    risk: medium
  tag_issue:
    title: "Tag issue {n}"
    tool: mcp_tracker_tag
    args: {n: "{n}"}
    params:
      n: {type: integer, minimum: 1, maximum: 9999}
    risk: low
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


def _act(action_id):
    return next(a for a in gate.session_actions(None) if a["action_id"] == action_id)


def _code(rec):
    return rec["action_id"].replace("act-", "")[:6]


# ------------------------------------------------------------- item 14


def test_free_form_side_effect_needs_the_code():
    rec = _click("deploy", {"side_effect": True})
    notice = _turn("hi")
    assert f"yes {_code(rec)}" in notice
    _turn("yes")
    act = _act(rec["action_id"])
    assert act["status"] == "pending_confirmation"
    assert "needs_code" in act["notes"]
    _turn(f"yes {_code(rec)}")
    assert _act(rec["action_id"])["status"] == "approved"


def test_medium_declared_action_needs_the_code():
    rec = _click("send_note", {"to": "kyle"})
    notice = _turn("hi")
    assert f"`yes {_code(rec)}`" in notice
    assert rec["binding"]["code_required"] is True
    _turn("yes")
    assert _act(rec["action_id"])["status"] == "pending_confirmation"
    _turn(f"yes {_code(rec)}")
    assert _act(rec["action_id"])["status"] == "approved"


def test_low_declared_action_alone_still_takes_a_bare_yes():
    rec = _click("tag_issue", {"n": 7})
    notice = _turn("hi")
    assert "reply `yes` or `no`" in notice
    assert rec["binding"]["code_required"] is False
    _turn("yes")
    assert _act(rec["action_id"])["status"] == "approved"


def test_bare_yes_with_two_open_questions_decides_nothing_and_says_why():
    low = _click("tag_issue", {"n": 7})
    other = actions.record_action(surface_id="other", session_id=SID, event="tag_issue", context={"n": 8})
    _turn("hi")
    _turn("yes")
    for rec in (low, other):
        act = _act(rec["action_id"])
        assert act["status"] == "pending_confirmation"
        assert "needs_code" in act["notes"]


def test_audit_view_marks_code_required_for_medium():
    rec = _click("send_note", {"to": "kyle"})
    view = gate.public_view(_act(rec["action_id"]))
    assert view["binding"]["code_required"] is True


# ------------------------------------------------------------- item 19


@pytest.mark.parametrize(
    "tool",
    ["terminal", "execute_code", "process_manage", "browser_exec", "mcp_box_run_shell",
     "mcp_ops_bash", "code_execution", "Terminal", "mcp-remote-ssh"],
)
def test_auto_approve_is_refused_for_exec_like_tools(tool):
    with pytest.raises(bindings.ActionConfigError) as err:
        bindings.parse_definition("thing", {"title": "x", "tool": tool, "risk": "low", "auto_approve": True})
    assert "auto_approve" in str(err.value)


def test_exec_like_tool_without_auto_approve_still_loads():
    action = bindings.parse_definition("thing", {"title": "x", "tool": "terminal", "risk": "high"})
    assert action.auto_approve is False


def test_gate_never_auto_approves_an_exec_like_binding_even_if_registry_is_bypassed(monkeypatch):
    forged = bindings.ActionDef(name="sneak", title="Run it", tool="terminal", args={"command": "ls"},
                                params={}, risk="low", auto_approve=True)
    monkeypatch.setattr(bindings, "get_action", lambda name: forged if name == "sneak" else None)
    rec = _click("sneak", {})
    assert rec["status"] == "pending_confirmation"
    assert _act(rec["action_id"])["decision_by"] is None
