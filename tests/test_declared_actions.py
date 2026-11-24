"""Declared actions: a click is bound to one exact tool call, approved once.

Covers the approval checklist from current agent-HITL practice: approval runs
the reviewed call and nothing else; altered arguments, other sessions, expiry,
and replay are rejected; concurrent calls cannot use one approval twice;
denial runs nothing and does not re-ask; a lost outcome shows as unknown.
"""

from __future__ import annotations

import json
import threading

import pytest

from uirizz_plugin import actions, bindings, gate
from uirizz_plugin.hooks import post_tool_call, pre_llm_call, pre_tool_call
from uirizz_plugin.store import put_surface, set_store_dir
from uirizz_plugin.tools import handle_a2ui_render, parse_tool_result

SID = "sess-actions"
SURF = "surf-deploy"

ACTIONS_YAML = """
actions:
  deploy_service:
    title: "Deploy {service} {version} to {env}"
    tool: mcp_github_dispatch_workflow
    args:
      repo: "acme/{service}"
      workflow: deploy.yml
      ref: main
      idempotency_key: "{operation_id}"
      inputs: {version: "{version}", env: "{env}", token_hint: "{service}"}
    params:
      service: {type: string, enum: [checkout-api, search-api]}
      version: {type: string, pattern: "^v[0-9]+$"}
      env: {type: string, enum: [staging, production]}
    risk: high
  snooze_alert:
    title: "Snooze {alert} for {minutes} min"
    tool: mcp_pagerduty_snooze
    args: {incident_id: "{alert}", duration: "{minutes}"}
    params:
      alert: {type: string}
      minutes: {type: integer, minimum: 5, maximum: 120, default: 30}
    risk: low
    auto_approve: true
  send_note:
    title: "Send a note to {to}"
    tool: send_message
    args: {to: "{to}", body: "{body}", tags: "{tags}"}
    params:
      to: {type: string, pattern: "^[a-z]+$"}
      body: {type: string, maxLength: 200}
      tags: {type: array, items: {type: string}, default: []}
    limits: {per_hour: 2}
  broken_one:
    title: "Uses {nope}"
    tool: something
    args: {x: "{nope}"}
"""

DEPLOY_CTX = {"service": "checkout-api", "version": "v24", "env": "production"}
DEPLOY_ARGS = {
    "repo": "acme/checkout-api",
    "workflow": "deploy.yml",
    "ref": "main",
    "inputs": {"version": "v24", "env": "production", "token_hint": "checkout-api"},
}


@pytest.fixture(autouse=True)
def _env(tmp_path):
    set_store_dir(tmp_path)
    bindings.set_actions_dir(tmp_path)
    (tmp_path / "actions.yaml").write_text(ACTIONS_YAML, encoding="utf-8")
    put_surface({"surface_id": SURF, "revision": 1, "fallback_text": "Card", "messages": [],
                 "component_count": 1, "component_ids": ["root"]})
    yield tmp_path
    bindings.set_actions_dir(None)
    for name in list(bindings._api_defs):
        bindings.unregister_action(name)
    set_store_dir(None)


def _click(event, context, session=SID):
    return actions.record_action(surface_id=SURF, session_id=session, event=event, context=context)


def _turn(text, session=SID):
    out = pre_llm_call(session_id=session, user_message=text)
    return (out or {}).get("context", "")


def _act(action_id):
    return next(a for a in gate.session_actions(None) if a["action_id"] == action_id)


def _deploy_args(action_id):
    return {**DEPLOY_ARGS, "idempotency_key": action_id}


def _call(tool, args, session=SID, call_id="call-1"):
    return pre_tool_call(session_id=session, tool_name=tool, args=args, tool_call_id=call_id)


def _done(tool, args, status="ok", session=SID, call_id="call-1", **kw):
    return post_tool_call(session_id=session, tool_name=tool, args=args, tool_call_id=call_id,
                          status=status, **kw)


# ------------------------------------------------------------------ config


def test_valid_definitions_load_and_broken_ones_are_reported():
    report = bindings.status_report()
    names = [a["action"] for a in report["actions"]]
    assert names == ["deploy_service", "send_note", "snooze_alert"]
    assert any("broken_one" in e and "nope" in e for e in report["errors"])


@pytest.mark.parametrize(
    "raw, needle",
    [
        ({"title": "x", "tool": "t", "risk": "high", "auto_approve": True}, "auto_approve"),
        ({"title": "x", "tool": "a2ui_render"}, "a2ui_render"),
        ({"title": "x", "tool": "bad tool!"}, "tool"),
        ({"title": "x", "tool": "t", "params": {"operation_id": {}}}, "reserved"),
        ({"title": "x", "tool": "t", "risk": "extreme"}, "risk"),
        ({"title": "x", "tool": "t", "surprise": 1}, "unknown keys"),
        ({"title": "x", "tool": "t", "params": {"p": {"type": "string", "pattern": "("}}}, "pattern"),
        ({"title": "x", "tool": "t", "limits": {"per_hour": 0}}, "per_hour"),
    ],
)
def test_definition_errors_are_precise(raw, needle):
    with pytest.raises(bindings.ActionConfigError) as err:
        bindings.parse_definition("thing", raw)
    assert needle in str(err.value)


def test_json_file_works_too(tmp_path):
    (tmp_path / "actions.yaml").unlink()
    (tmp_path / "actions.json").write_text(json.dumps({"actions": {"ping_host": {
        "title": "Ping {host}", "tool": "ping", "args": {"host": "{host}"},
        "params": {"host": {"type": "string"}}, "risk": "low"}}}), encoding="utf-8")
    assert [a["action"] for a in bindings.status_report()["actions"]] == ["ping_host"]


def test_check_command_exits_nonzero_on_errors(capsys):
    assert bindings.main(["check"]) == 1
    assert "broken_one" in capsys.readouterr().out


def test_register_action_api_and_file_wins():
    bindings.register_action("open_ticket", title="Open {title}", tool="linear_create",
                             args={"title": "{title}"}, params={"title": {"type": "string"}})
    bindings.register_action("send_note", title="API version", tool="other_tool")
    report = bindings.status_report()
    assert "open_ticket" in [a["action"] for a in report["actions"]]
    assert bindings.get_action("send_note").tool == "send_message"  # the user's file wins
    assert report["shadowed_api_actions"] == ["send_note"]


# ------------------------------------------------------------------ binding


def test_binding_keeps_types_renders_strings_and_operation_id():
    action = bindings.get_action("snooze_alert")
    b = bindings.bind(action, {"alert": "INC-1", "minutes": "45"}, operation_id="act-x")
    assert b.args == {"incident_id": "INC-1", "duration": 45}  # whole placeholder keeps int
    assert b.title == "Snooze INC-1 for 45 min"
    d = bindings.bind(bindings.get_action("deploy_service"), DEPLOY_CTX, operation_id="act-y")
    assert d.args["idempotency_key"] == "act-y"
    assert d.args_hash == bindings.call_hash("mcp_github_dispatch_workflow", d.args)


@pytest.mark.parametrize(
    "ctx, needle",
    [
        ({**DEPLOY_CTX, "env": "prod"}, "must be one of"),
        ({**DEPLOY_CTX, "version": "24"}, "does not match"),
        ({k: v for k, v in DEPLOY_CTX.items() if k != "env"}, "env: required"),
        ({**DEPLOY_CTX, "force": True}, "unknown params"),
        ({**DEPLOY_CTX, "service": ["checkout-api"]}, "expected text"),
    ],
)
def test_bad_params_are_rejected_with_reasons(ctx, needle):
    with pytest.raises(bindings.ParamError) as err:
        bindings.bind(bindings.get_action("deploy_service"), ctx, operation_id="a")
    assert needle in str(err.value)


def test_canonical_hash_ignores_key_order_and_integral_floats():
    assert bindings.call_hash("t", {"a": 1, "b": [2.0]}) == bindings.call_hash("t", {"b": [2], "a": 1.0})
    assert bindings.call_hash("t", {"a": 1}) != bindings.call_hash("u", {"a": 1})


# ------------------------------------------------------------------ full flows


def test_high_risk_flow_needs_code_then_runs_exactly_once():
    rec = _click("deploy_service", {**DEPLOY_CTX, "side_effect": True})
    aid = rec["action_id"]
    assert rec["status"] == "pending_confirmation" and rec["declared"]
    assert rec["binding"]["title"] == "Deploy checkout-api v24 to production"
    assert rec["binding"]["code_required"] is True
    assert rec["binding"]["args"]["inputs"]["token_hint"] == "[redacted]"  # display only

    notice = _turn("I clicked deploy")
    assert "Deploy checkout-api v24 to production" in notice and f"yes {gate._short(aid)}" in notice
    assert _call("terminal", {"command": "ls"})["action"] == "block"

    notice = _turn("yes")  # bare yes is not enough for risk high
    assert _act(aid)["status"] == "pending_confirmation"
    assert "without the code" in notice

    notice = _turn(f"yes {gate._short(aid)}")
    assert _act(aid)["status"] == "approved"
    assert "mcp_github_dispatch_workflow" in notice and '"idempotency_key"' in notice

    args = _deploy_args(aid)
    other = _call("terminal", {"command": "deploy prod"})
    assert other["action"] == "block" and "has not run yet" in other["message"]
    altered = _call("mcp_github_dispatch_workflow", {**args, "ref": "hotfix"})
    assert altered["action"] == "block" and "differ" in altered["message"]

    assert _call("mcp_github_dispatch_workflow", args) is None
    assert _act(aid)["status"] == "executing"
    replay = _call("mcp_github_dispatch_workflow", args, call_id="call-2")
    assert replay["action"] == "block" and "already" in replay["message"]

    _done("mcp_github_dispatch_workflow", args, "ok")
    assert _act(aid)["status"] == "completed"
    assert "status=completed" in _turn("ok?")
    assert _turn("thanks") == ""  # the outcome is announced once
    with pytest.raises(gate.GateError) as err:
        gate.complete_action(aid, "done")
    assert err.value.code == "recorded_automatically"
    assert _call("terminal", {"command": "ls"}) is None  # gate is idle again


def test_medium_risk_needs_the_code_since_track_c_14():
    rec = _click("send_note", {"to": "kyle", "body": "hi"})
    _turn("sent?")
    _turn("yes")  # a bare yes may answer another question
    assert _act(rec["action_id"])["status"] == "pending_confirmation"
    _turn("yes " + rec["action_id"].replace("act-", "")[:6])
    assert _act(rec["action_id"])["status"] == "approved"
    assert _call("send_message", {"to": "kyle", "body": "hi", "tags": []}) is None


def test_denial_runs_nothing_blocks_the_exact_call_and_does_not_re_ask():
    rec = _click("deploy_service", DEPLOY_CTX)
    _turn("hm")
    notice = _turn("no")
    assert _act(rec["action_id"])["status"] == "denied"
    assert "Do not ask again" in notice
    assert _turn("ok") == ""
    blocked = _call("mcp_github_dispatch_workflow", _deploy_args(rec["action_id"]))
    assert blocked["action"] == "block" and "denied" in blocked["message"]
    assert _call("terminal", {"command": "ls"}) is None


def test_low_risk_auto_approve_is_still_bound_to_the_call():
    rec = _click("snooze_alert", {"alert": "INC-7"})
    assert rec["status"] == "approved"
    assert _act(rec["action_id"])["decision_by"] == "policy:auto_approve"
    wrong = _call("mcp_pagerduty_snooze", {"incident_id": "INC-7", "duration": 120})
    assert wrong["action"] == "block"
    assert _call("mcp_pagerduty_snooze", {"incident_id": "INC-7", "duration": 30}) is None


def test_invalid_click_is_rejected_and_explained_without_blocking():
    rec = _click("deploy_service", {**DEPLOY_CTX, "env": "prod"})
    assert rec["status"] == "rejected" and "must be one of" in rec["rejected"]
    assert _call("terminal", {"command": "ls"}) is None
    notice = _turn("why nothing?")
    assert "status=rejected" in notice and "topic=actions" in notice


def test_rate_limit_rejects_extra_clicks():
    for _ in range(2):
        rec = _click("send_note", {"to": "kyle", "body": "x"})
        _turn("x")
        _turn("yes " + rec["action_id"].replace("act-", "")[:6])
        assert _act(rec["action_id"])["status"] == "approved"
    third = _click("send_note", {"to": "kyle", "body": "x"})
    assert third["status"] == "rejected" and "rate limit" in third["rejected"]


def test_approval_cannot_be_used_from_another_session():
    rec = _click("snooze_alert", {"alert": "INC-9"})
    args = {"incident_id": "INC-9", "duration": 30}
    assert _call("mcp_pagerduty_snooze", args, session="intruder") is None  # not under this gate
    assert _act(rec["action_id"])["status"] == "approved"  # and it did not consume A's approval


def test_expired_approval_is_not_usable(monkeypatch):
    rec = _click("snooze_alert", {"alert": "INC-3"})
    real = gate._now()
    monkeypatch.setattr(gate, "_now", lambda: real + gate.APPROVAL_TTL_S + 5)
    assert _act(rec["action_id"])["status"] == "expired"
    assert _call("mcp_pagerduty_snooze", {"incident_id": "INC-3", "duration": 30}) is None
    assert _act(rec["action_id"])["status"] == "expired"  # nothing was consumed


def test_concurrent_calls_cannot_use_one_approval_twice():
    rec = _click("snooze_alert", {"alert": "INC-5"})
    args = {"incident_id": "INC-5", "duration": 30}
    results = []
    barrier = threading.Barrier(8)

    def worker(i):
        barrier.wait()
        results.append(_call("mcp_pagerduty_snooze", args, call_id=f"c{i}"))

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert sum(r is None for r in results) == 1
    assert _act(rec["action_id"])["status"] == "executing"


@pytest.mark.parametrize(
    "status, expected",
    [("ok", "completed"), ("error", "failed"), ("cancelled", "unknown")],
)
def test_post_tool_call_maps_outcomes(status, expected):
    rec = _click("snooze_alert", {"alert": "INC-2"})
    args = {"incident_id": "INC-2", "duration": 30}
    assert _call("mcp_pagerduty_snooze", args) is None
    _done("mcp_pagerduty_snooze", args, status, error_type="timeout" if status == "error" else None)
    act = _act(rec["action_id"])
    assert act["status"] == expected
    if status == "error":
        assert act["error_type"] == "timeout"


def test_blocked_by_a_later_hook_releases_the_approval():
    rec = _click("snooze_alert", {"alert": "INC-4"})
    args = {"incident_id": "INC-4", "duration": 30}
    assert _call("mcp_pagerduty_snooze", args) is None
    _done("mcp_pagerduty_snooze", args, "blocked")
    assert _act(rec["action_id"])["status"] == "approved"
    assert _call("mcp_pagerduty_snooze", args, call_id="call-2") is None


def test_args_rewritten_after_the_gate_mark_the_outcome_unknown():
    rec = _click("snooze_alert", {"alert": "INC-6"})
    args = {"incident_id": "INC-6", "duration": 30}
    assert _call("mcp_pagerduty_snooze", args) is None
    _done("mcp_pagerduty_snooze", {**args, "duration": 999}, "ok")
    act = _act(rec["action_id"])
    assert act["status"] == "unknown" and act["error_type"] == "args_changed_after_approval"


def test_host_without_args_fails_closed_for_bound_calls():
    _click("snooze_alert", {"alert": "INC-8"})
    out = pre_tool_call(session_id=SID, tool_name="mcp_pagerduty_snooze")
    assert out["action"] == "block" and "cannot be verified" in out["message"]


def test_cancel_before_running_but_not_after():
    rec = _click("snooze_alert", {"alert": "INC-10"})
    gate.complete_action(rec["action_id"], "cancelled")
    assert _act(rec["action_id"])["status"] == "cancelled"
    rec2 = _click("snooze_alert", {"alert": "INC-11"})
    assert _call("mcp_pagerduty_snooze", {"incident_id": "INC-11", "duration": 30}) is None
    with pytest.raises(gate.GateError) as err:
        gate.complete_action(rec2["action_id"], "cancelled")
    assert err.value.code == "already_running"


def test_audit_view_shows_redacted_binding():
    _click("deploy_service", DEPLOY_CTX)
    view = gate.audit_view(session_id=SID)
    b = view["actions"][-1]["binding"]
    assert b["title"].startswith("Deploy") and b["args"]["inputs"]["token_hint"] == "[redacted]"
    assert view["chain_ok"] is True


# ------------------------------------------------------------------ tool surface


def test_describe_topic_actions_lists_actions_and_errors():
    out = json.loads(handle_a2ui_render({"op": "describe", "topic": "actions"}))
    assert out["ok"] and "never invent one" in out["howto"]
    deploy = next(a for a in out["actions"] if a["action"] == "deploy_service")
    assert deploy["risk"] == "high" and deploy["params"]["env"]["enum"] == ["staging", "production"]
    assert out["errors"]


def test_present_warns_about_misused_declared_actions():
    src = ('root = Row([Button(Text("Deploy"), action=Event("deploy_service", '
           '{service: "checkout-api", env: "prod", force: true})), '
           'Button(Text("Snooze"), action=Event("snooze_alert", {alert: $/alert}))])')
    out = parse_tool_result(handle_a2ui_render({"op": "present", "express": src, "fallback_text": "x"}))
    assert out["ok"] is True
    warnings = " ".join(out["action_warnings"])
    assert "unknown params ['force']" in warnings
    assert "missing param version" in warnings
    assert "must be one of" in warnings
    assert "snooze_alert" not in warnings  # a $/path binding is checked at click time


def test_undeclared_events_need_the_code_then_behave_as_before():
    rec = _click("deploy", {"side_effect": True})
    assert rec["declared"] is False and rec["binding"] is None
    _turn("x")
    _turn("yes")  # Track C #14: free-form side effects need `yes <code>`
    assert _act(rec["action_id"])["status"] == "pending_confirmation"
    _turn("yes " + rec["action_id"].replace("act-", "")[:6])
    assert _act(rec["action_id"])["status"] == "approved"
    assert _call("terminal", {"command": "anything"}) is None  # unbound approval, as today


def test_shipped_example_file_is_valid():
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "docs" / "actions.example.yaml"
    defs, errors = bindings._parse_file(path)
    assert errors == []
    assert set(defs) == {"deploy_service", "post_status", "snooze_alert"}
    assert defs["deploy_service"].risk == "high" and defs["snooze_alert"].auto_approve
