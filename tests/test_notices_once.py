"""RED for wave A slice T5b: per-turn uirizz context is announced once.

Today a pending approval repeats its full instruction paragraph on every turn
for up to 600 s, and the active-cards hint repeats on every turn with no TTL.
After the first full notice, later turns get a short reminder that still names
the action, its code and the reply that approves it. The cards hint repeats
only when the set of cards changes. The approval gate itself is unchanged:
pre_tool_call still blocks, and only a typed yes after the notice approves.
"""

from __future__ import annotations

import pytest

from uirizz_plugin import actions, gate
from uirizz_plugin.hooks import pre_llm_call, pre_tool_call
from uirizz_plugin.store import put_surface, set_store_dir

SID = "sess-once"
SURF = "demo"


@pytest.fixture(autouse=True)
def _store(tmp_path):
    set_store_dir(tmp_path)
    yield
    set_store_dir(None)


def _surface(revision=1, conversation_id=None):
    rec = {"surface_id": SURF, "revision": revision, "fallback_text": "Card", "messages": [],
           "component_count": 1, "component_ids": ["root"], "session_id": SID}
    if conversation_id:
        rec["conversation_id"] = conversation_id
    put_surface(rec)


def _click():
    return actions.record_action(surface_id=SURF, session_id=SID, event="deploy", context={"side_effect": True})


def _code(rec):
    return rec["action_id"].replace("act-", "")[:6]


def _turn(text, **kw):
    out = pre_llm_call(session_id=SID, user_message=text, **kw)
    return (out or {}).get("context", "")


def _status(aid):
    return next(a["status"] for a in gate.session_actions(None) if a["action_id"] == aid)


def test_full_notice_once_then_a_short_reminder():
    _surface()
    rec = _click()
    first = _turn("I clicked deploy")
    assert "status=pending_confirmation" in first and "not approval" in first
    second = _turn("what now?")
    assert "status=pending_confirmation" in second
    assert _code(rec) in second
    assert "Update the same surface" not in second
    gate_part = second[second.index("Approval gate"):]
    assert len(gate_part) < 300, f"reminder is {len(gate_part)} chars"


def test_yes_after_a_reminder_still_approves():
    _surface()
    rec = _click()
    _turn("I clicked deploy")
    _turn("hmm")
    _turn("Yes " + _code(rec))
    assert _status(rec["action_id"]) == "approved"


def test_tools_stay_blocked_while_only_the_reminder_shows():
    _surface()
    _click()
    _turn("I clicked deploy")
    _turn("hmm")
    assert pre_tool_call(session_id=SID, tool_name="send_message")["action"] == "block"


def test_cards_hint_repeats_only_when_cards_change():
    _surface(revision=1, conversation_id="c1")
    first = _turn("hello", conversation_id="c1")
    assert "uirizz cards already in this chat" in first
    second = _turn("again", conversation_id="c1")
    assert "uirizz cards already in this chat" not in second
    _surface(revision=2, conversation_id="c1")
    third = _turn("after an update", conversation_id="c1")
    assert "uirizz cards already in this chat" in third and "rev 2" in third
