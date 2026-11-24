"""Conversation-scoped cards, active-card hints, generated fallback, [card] guard."""

from __future__ import annotations

import pytest

from uirizz_plugin import actions, gate
from uirizz_plugin.fallback import generate_fallback
from uirizz_plugin.hints import active_cards_hint
from uirizz_plugin.hooks import pre_llm_call
from uirizz_plugin.store import _path_for, get_surface, put_surface, set_store_dir
from uirizz_plugin.tools import handle_a2ui_render, parse_tool_result


@pytest.fixture(autouse=True)
def _store(tmp_path):
    set_store_dir(tmp_path)
    actions._PENDING.clear()
    yield
    set_store_dir(None)
    actions._PENDING.clear()


def _present(text="Hi", **kw):
    out = parse_tool_result(
        handle_a2ui_render({"op": "present", "express": f'root = Text("{text}")', "fallback_text": text}, **kw)
    )
    assert out["ok"] is True, out
    return out["surface_id"]


def _update(sid, **kw):
    return parse_tool_result(
        handle_a2ui_render({"op": "update", "surface_id": sid, "express": 'root = Text("New")'}, **kw)
    )


def test_ids_are_stored_and_kept_on_update():
    sid = _present(session_id="s1", conversation_id="c1")
    rec = get_surface(sid)
    assert (rec["session_id"], rec["conversation_id"]) == ("s1", "c1")
    assert _update(sid, session_id="s2", conversation_id="c1")["ok"] is True
    rec = get_surface(sid)
    assert (rec["session_id"], rec["conversation_id"]) == ("s1", "c1")


def test_wrong_conversation_refused_for_update_and_delete():
    sid = _present(conversation_id="c1")
    for body in (
        _update(sid, conversation_id="c2"),
        parse_tool_result(handle_a2ui_render({"op": "delete", "surface_id": sid}, conversation_id="c2")),
    ):
        assert body["ok"] is False
        assert body["code"] == "wrong_conversation"
        assert body["error"] == "That card belongs to another conversation."
        assert body["fix"] == "Present a new card in this conversation."
    assert get_surface(sid) is not None


def test_missing_ids_are_allowed():
    sid = _present(conversation_id="c1")
    assert _update(sid)["ok"] is True  # call without id
    legacy = _present()  # stored without ids
    assert _update(legacy, conversation_id="c9")["ok"] is True


def test_hint_in_pre_llm_call_for_right_conversation_only():
    sid = _present("Deploy status", session_id="s1", conversation_id="c1")
    ctx = pre_llm_call(session_id="s1", conversation_id="c1", user_message="hello")
    assert ctx and sid in ctx["context"] and '"Deploy status" rev 1' in ctx["context"]
    assert "op=update" in ctx["context"]
    assert pre_llm_call(session_id="s1", conversation_id="c2", user_message="hello") is None
    # falls back to session_id when there is no conversation_id
    assert sid in pre_llm_call(session_id="s1", user_message="hello")["context"]


def test_hint_capped_at_five_cards_and_600_chars():
    import os

    for i in range(8):
        sid = _present(f"Card {i}", conversation_id="c1")
        os.utime(_path_for(sid), (1000 + i, 1000 + i))
    hint = active_cards_hint(None, "c1")
    assert hint.count(" rev ") == 5
    assert "Card 7" in hint and "Card 2" not in hint
    for i in range(5):
        put_surface({"surface_id": f"long-{i}", "revision": 1, "conversation_id": "c9",
                     "fallback_text": "x" * 200, "messages": []})
    assert len(active_cards_hint(None, "c9")) <= 600
    assert active_cards_hint(None, "nobody") is None


def test_hint_title_first_line_stripped():
    put_surface({"surface_id": "t1", "revision": 2, "conversation_id": "c1",
                 "fallback_text": "\n\x07  Real title\nsecond", "messages": []})
    assert '"Real title" rev 2' in active_cards_hint(None, "c1")


def test_card_prefixed_yes_is_not_approval():
    put_surface({"surface_id": "demo", "revision": 1, "fallback_text": "Card", "messages": []})
    rec = actions.record_action(surface_id="demo", session_id="s1", event="deploy",
                                context={"side_effect": True})
    pre_llm_call(session_id="s1", user_message="hi")  # shows the notice (announced)
    for text in ("[card] yes", "  [CARD] yes please"):
        pre_llm_call(session_id="s1", user_message=text)
        status = next(a["status"] for a in gate.session_actions(None) if a["action_id"] == rec["action_id"])
        assert status == "pending_confirmation"
    pre_llm_call(session_id="s1", user_message="yes")
    status = next(a["status"] for a in gate.session_actions(None) if a["action_id"] == rec["action_id"])
    assert status == "approved"


def test_generate_fallback_text_metric_datatable():
    msgs = [{
        "version": "1.0",
        "createSurface": {
            "surfaceId": "s",
            "dataModel": {"rows": [{"n": "a", "v": 1}, {"n": "b", "v": 2}]},
            "components": [
                {"id": "root", "component": "Column", "children": ["h", "m", "t", "dyn"]},
                {"id": "h", "component": "Text", "text": "## Overview"},
                {"id": "dyn", "component": "Text", "text": {"@path": "/x"}},
                {"id": "m", "component": "Metric", "label": "Uptime", "value": "99.9%", "delta": "+0.1"},
                {"id": "t", "component": "DataTable", "title": "Hosts",
                 "columns": [{"key": "n", "label": "Name"}, {"key": "v", "label": "Val"}],
                 "rows": {"@path": "/rows"}},
                {"id": "u", "component": "Mystery"},
            ],
        },
    }]
    text = generate_fallback(msgs)
    assert text.splitlines() == [
        "Overview", "Uptime: 99.9% (+0.1)", "Table: Hosts, 2 rows", "Name=a; Val=1", "Name=b; Val=2",
    ]
    assert generate_fallback("garbage") == ""
    assert len(generate_fallback([{"updateComponents": {"components": [
        {"id": str(i), "component": "Text", "text": "x" * 100} for i in range(50)]}}])) <= 1500
