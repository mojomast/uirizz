"""Approval gate: a card click is a request, never approval. Fail-closed."""

from __future__ import annotations

import json

import pytest

from uirizz_plugin import actions, gate
from uirizz_plugin.hooks import pre_llm_call, pre_tool_call
from uirizz_plugin.store import put_surface, get_surface, set_store_dir
from uirizz_plugin.tools import A2UI_RENDER_SCHEMA, handle_a2ui_render, parse_tool_result

SID = "sess-1"
SURF = "demo"


@pytest.fixture(autouse=True)
def _store(tmp_path):
    set_store_dir(tmp_path)
    yield
    set_store_dir(None)


def _surface(messages=None):
    put_surface(
        {
            "surface_id": SURF,
            "revision": 1,
            "fallback_text": "Card",
            "messages": messages or [],
            "component_count": 1,
            "component_ids": ["root"],
        }
    )


def _click(event="deploy", context=None, session=SID):
    return actions.record_action(
        surface_id=SURF, session_id=session, event=event, context=context
    )


def _turn(text, session=SID):
    """One user turn through the real hook."""
    return pre_llm_call(session_id=session, user_message=text)


def _status(action_id):
    for a in gate.session_actions(None):
        if a["action_id"] == action_id:
            return a["status"]
    raise AssertionError("missing action")


# ------------------------------------------------------------ classification


@pytest.mark.parametrize(
    "event,context",
    [
        ("go", {"side_effect": True}),
        ("go", {"requires_confirmation": "true"}),
        ("go", {"sideEffect": {"literalBoolean": True}}),
        ("go", {}),  # unmarked: fail-closed
        ("go", None),
        ("deployNow", {"read_only": True}),  # verb beats the claim
        ("go", {"read_only": True, "note": "Merge the branch"}),
        ("go", {"read_only": "maybe"}),  # unclear marker
        ("go", {"side_effect": {"path": "/x"}}),  # bound value cannot be trusted
        ("go", {"read_only": False}),
        ("Release_candidate", {"read_only": True}),
        ("go", {"read_only": True, "side_effect": True}),
    ],
)
def test_gated_by_default_and_by_verb(event, context):
    gated, _reason = gate.classify(event, context)
    assert gated is True


@pytest.mark.parametrize(
    "event,context",
    [
        ("pick", {"read_only": True}),
        ("open_tab", {"readOnly": "true"}),
        ("filter", {"side_effect": False}),
        ("refresh_view", {"read_only": True, "range": "7d"}),
    ],
)
def test_explicit_read_only_is_not_gated(event, context):
    gated, reason = gate.classify(event, context)
    assert gated is False, reason


def test_surface_definition_overrides_a_downgraded_click():
    msgs = [
        {
            "version": "1.0",
            "updateComponents": {
                "surfaceId": SURF,
                "components": [
                    {
                        "id": "b",
                        "component": "Button",
                        "action": {"event": {"name": "ship_it", "context": {"side_effect": True}}},
                    }
                ],
            },
        }
    ]
    _surface(msgs)
    rec = _click("ship_it", {"read_only": True})
    assert rec["requires_confirmation"] is True


def test_read_only_click_is_recorded_but_never_gates_tools():
    _surface()
    rec = _click("pick", {"read_only": True})
    assert rec["requires_confirmation"] is False
    assert rec["status"] == "recorded"
    assert pre_tool_call(session_id=SID, tool_name="terminal") is None


# ------------------------------------------------------- a click never approves


def test_click_alone_never_approves_and_blocks_tools():
    _surface()
    rec = _click("deploy", {"side_effect": True})
    assert rec["status"] == "pending_confirmation"
    assert _status(rec["action_id"]) == "pending_confirmation"
    block = pre_tool_call(session_id=SID, tool_name="terminal", args={"command": "x"})
    assert block and block["action"] == "block"
    assert "not approval" in block["message"]
    assert pre_tool_call(session_id=SID, tool_name="a2ui_render") is None
    assert pre_tool_call(session_id="other-session", tool_name="terminal") is None


def test_rest_response_reports_not_approved():
    from dashboard.plugin_api import _record_action

    _surface()
    out = _record_action(
        {"surface_id": SURF, "session_id": SID, "event": "deploy", "context": {"side_effect": True}}
    )
    assert out["ok"] is True
    assert out["requires_confirmation"] is True
    assert out["approved"] is False
    assert out["status"] == "pending_confirmation"


def test_model_cannot_report_done_without_user_yes():
    _surface()
    rec = _click("deploy", {"side_effect": True})
    out = parse_tool_result(
        handle_a2ui_render(
            {
                "op": "update",
                "surface_id": SURF,
                "action_id": rec["action_id"],
                "action_outcome": "done",
                "jsonl": json.dumps({"version": "1.0", "updateDataModel": {"surfaceId": SURF, "value": {"x": 1}}}),
            }
        )
    )
    assert out["ok"] is False
    assert out["code"] == "not_approved"
    assert get_surface(SURF)["revision"] == 1  # rejected report changed nothing
    assert _status(rec["action_id"]) == "pending_confirmation"


def test_no_approve_op_exists_for_the_model():
    assert "approve" not in A2UI_RENDER_SCHEMA["parameters"]["properties"]["op"]["enum"]
    out = parse_tool_result(handle_a2ui_render({"op": "approve", "action_id": "x"}))
    assert out["ok"] is False


def test_outcome_values_are_validated():
    _surface()
    rec = _click("deploy", {"side_effect": True})
    for bad in ("approved", "yes", "", None):
        with pytest.raises(gate.GateError):
            gate.complete_action(rec["action_id"], bad)
    with pytest.raises(gate.GateError):
        gate.complete_action("act-nope", "done")


# ------------------------------------------------- approval by the typed reply


def test_yes_needs_the_notice_shown_first():
    _surface()
    rec = _click("deploy", {"side_effect": True})
    _turn("yes")  # first turn after the click: not announced yet
    assert _status(rec["action_id"]) == "pending_confirmation"
    ctx = _turn("hello?")["context"]  # announces (already announced by previous turn)
    assert "pending_confirmation" in ctx


def test_full_flow_click_notice_yes_done_single_use():
    _surface()
    rec = _click("deploy", {"side_effect": True, "target": "mock-prod"})
    notice = _turn("I clicked deploy")["context"]
    assert "status=pending_confirmation" in notice and rec["action_id"] in notice
    assert "not approval" in notice
    assert _status(rec["action_id"]) == "pending_confirmation"

    approved_turn = _turn("Yes")["context"]
    assert _status(rec["action_id"]) == "approved"
    assert "status=approved" in approved_turn
    assert pre_tool_call(session_id=SID, tool_name="terminal") is None  # user said yes

    gate.complete_action(rec["action_id"], "done")
    assert _status(rec["action_id"]) == "completed"
    with pytest.raises(gate.GateError) as err:
        gate.complete_action(rec["action_id"], "done")
    assert err.value.code == "already_resolved"
    assert _turn("anything") is None  # nothing left to say


def test_deny_cancels_and_unblocks():
    _surface()
    rec = _click("deploy", {"side_effect": True})
    _turn("hi")
    ctx = _turn("no, cancel")["context"]
    assert _status(rec["action_id"]) == "denied"
    assert "status=denied" in ctx
    assert pre_tool_call(session_id=SID, tool_name="terminal") is None
    with pytest.raises(gate.GateError):
        gate.complete_action(rec["action_id"], "done")
    gate.complete_action(rec["action_id"], "cancelled")


@pytest.mark.parametrize(
    "text",
    [
        "yes but wait",
        "yes, deploy everything to every region and delete the old one",
        "maybe yes",
        "is it a yes?",
        "not yes",
        "y" * 200,
        "",
        None,
        ["yes"],
        {"text": "yes"},
        "Third-party UI event data (quoted, not instructions): yes",
    ],
)
def test_only_a_short_explicit_yes_counts(text):
    _surface()
    rec = _click("deploy", {"side_effect": True})
    _turn("hi")
    pre_llm_call(session_id=SID, user_message=text)
    assert _status(rec["action_id"]) == "pending_confirmation"


def test_bare_yes_is_ambiguous_with_two_pending_and_a_code_resolves_it():
    _surface()
    a = _click("deploy", {"side_effect": True})
    b = actions.record_action(surface_id=SURF, session_id=SID, event="delete_db", context={"side_effect": True})
    _turn("hi")
    _turn("yes")
    assert _status(a["action_id"]) == "pending_confirmation"
    assert _status(b["action_id"]) == "pending_confirmation"
    code = a["action_id"].replace("act-", "")[:6]
    _turn(f"yes {code}")
    assert _status(a["action_id"]) == "approved"
    assert _status(b["action_id"]) == "pending_confirmation"


def test_same_control_clicked_twice_supersedes_the_older_one():
    _surface()
    first = _click("deploy", {"side_effect": True})
    second = _click("deploy", {"side_effect": True})
    assert _status(first["action_id"]) == "superseded"
    assert _status(second["action_id"]) == "pending_confirmation"


def test_approval_is_scoped_to_its_session():
    _surface()
    rec = _click("deploy", {"side_effect": True}, session="sess-A")
    pre_llm_call(session_id="sess-A", user_message="hi")
    pre_llm_call(session_id="sess-B", user_message="yes")
    assert _status(rec["action_id"]) == "pending_confirmation"


def test_pending_and_approval_expire(monkeypatch):
    _surface()
    clock = {"t": 1_000_000.0}
    monkeypatch.setattr(gate, "_now", lambda: clock["t"])
    rec = _click("deploy", {"side_effect": True})
    _turn("hi")
    clock["t"] += gate.APPROVAL_TTL_S + 1
    _turn("yes")
    assert _status(rec["action_id"]) == "expired"
    assert pre_tool_call(session_id=SID, tool_name="terminal") is None  # expiry unblocks

    clock["t"] += 1
    rec2 = _click("deploy", {"side_effect": True})
    _turn("hi")
    _turn("yes")
    assert _status(rec2["action_id"]) == "approved"
    clock["t"] += gate.APPROVAL_TTL_S + 1
    with pytest.raises(gate.GateError):
        gate.complete_action(rec2["action_id"], "done")


# ----------------------------------------------------------- fail-closed hook


def test_pre_tool_call_fails_closed_when_the_gate_errors(monkeypatch):
    def boom(*_a, **_k):
        raise RuntimeError("log unreadable")

    monkeypatch.setattr(gate, "tool_block_message", boom)
    blocked = pre_tool_call(session_id=SID, tool_name="terminal")
    assert blocked and blocked["action"] == "block"
    assert pre_tool_call(session_id=SID, tool_name="a2ui_render") is None


def test_hook_returns_a_directive_hermes_understands():
    _surface()
    _click("deploy", {"side_effect": True})
    out = pre_tool_call(session_id=SID, tool_name="execute_code", args={}, task_id="t", turn_id="x")
    assert set(out) == {"action", "message"} and out["action"] == "block" and out["message"]


# ------------------------------------------------------------------ audit log


def test_audit_op_lists_actions_and_chain_verifies():
    _surface()
    rec = _click("deploy", {"side_effect": True, "token": "sk-live-abc", "note": "ok\nline"})
    _turn("hi")
    _turn("yes")
    gate.complete_action(rec["action_id"], "done")
    out = parse_tool_result(handle_a2ui_render({"op": "audit", "surface_id": SURF}))
    assert out["ok"] is True and out["chain_ok"] is True
    (item,) = out["actions"]
    assert item["status"] == "completed"
    assert item["decision_by"] == "user_message"
    assert item["context"]["token"] == "[redacted]"
    assert "\n" not in json.dumps(item["context"])
    assert item["requires_confirmation"] is True and item["event"] == "deploy"


def test_audit_log_detects_tampering():
    _surface()
    _click("deploy", {"side_effect": True})
    _click("pick", {"read_only": True})
    assert gate.verify_chain()["ok"] is True
    path = gate._log_path()
    lines = path.read_text().splitlines()
    first = json.loads(lines[0])
    first["event"] = "harmless"
    lines[0] = json.dumps(first, separators=(",", ":"))
    path.write_text("\n".join(lines) + "\n")
    assert gate.verify_chain()["ok"] is False


def test_audit_context_is_bounded():
    _surface()
    _click("pick", {"read_only": True, "blob": "x" * 5000, "a": list(range(500))})
    entry = gate.read_entries()[-1]
    assert len(json.dumps(entry["context"])) <= gate.MAX_CONTEXT_BYTES + 200


def test_audit_route_is_registered():
    from dashboard.plugin_api import router

    paths = {getattr(r, "path", "") for r in router.routes}
    assert "/audit" in paths and "/actions" in paths


def test_describe_documents_the_gate():
    out = parse_tool_result(handle_a2ui_render({"op": "describe"}))
    g = out["approval_gate"]
    assert g["click_is_approval"] is False
    assert out["ops"]["audit"] == "implemented"
    assert "terminal" not in g["tools_allowed_while_pending"]


def test_skill_states_clicks_are_not_approval():
    from pathlib import Path

    text = (Path(__file__).resolve().parents[1] / "skills" / "uirizz" / "SKILL.md").read_text()
    low = text.lower()
    assert "a click is not approval" in low
    assert "side_effect" in text and "read_only" in text
    assert "action_outcome" in text and "op=audit" in text
