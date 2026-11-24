"""Track C item 18: read-only clicks survive the process boundary.

On a real Hermes host the dashboard REST router (which records the click) and
the agent (whose pre_llm_call delivers it) can run in different processes, for
example ``hermes dashboard`` and ``hermes gateway`` as separate services. An
in-memory queue silently dropped those clicks. They now come from the audit
log on disk, are delivered once, and the queue is bounded.
"""

from __future__ import annotations

import multiprocessing as mp
import sys

import pytest

from uirizz_plugin import actions, gate
from uirizz_plugin.hooks import pre_llm_call
from uirizz_plugin.store import put_surface, set_store_dir

SID = "sess-pending"
SURF = "surf-pending"

fork_only = pytest.mark.skipif(
    sys.platform == "win32" or "fork" not in mp.get_all_start_methods(), reason="needs fork"
)


@pytest.fixture(autouse=True)
def _env(tmp_path):
    set_store_dir(tmp_path)
    getattr(actions, "_PENDING", {}).clear()
    put_surface({"surface_id": SURF, "revision": 1, "fallback_text": "Card", "messages": [],
                 "component_count": 1, "component_ids": ["root"]})
    yield
    set_store_dir(None)


def _ctx(session=SID):
    out = pre_llm_call(session_id=session, user_message="next")
    return (out or {}).get("context", "")


def _click(event, context=None, session=SID):
    return actions.record_action(surface_id=SURF, session_id=session, event=event,
                                 context={"read_only": True, **(context or {})})


def _click_in_child(event):
    _click(event)


@fork_only
def test_click_recorded_in_another_process_reaches_the_agent():
    proc = mp.get_context("fork").Process(target=_click_in_child, args=("choose_plan",))
    proc.start()
    proc.join(timeout=30)
    assert proc.exitcode == 0
    text = _ctx()
    assert "event=choose_plan" in text
    assert "event=choose_plan" not in _ctx()  # delivered once


def test_each_click_is_delivered_once_even_after_in_memory_state_is_lost():
    _click("filter_region", {"region": "eu"})
    getattr(actions, "_PENDING", {}).clear()  # a fresh agent process has no memory of it
    assert "event=filter_region" in _ctx()
    assert "event=filter_region" not in _ctx()


def test_queue_is_bounded_to_the_newest_clicks():
    for i in range(50):
        _click(f"pick_{i:02d}")
    text = _ctx()
    assert text.count("Third-party UI event data") == actions.MAX_PENDING_CLICKS
    assert "event=pick_49" in text and "event=pick_00" not in text
    assert _ctx() == ""  # the dropped ones are not delivered later either


def test_stale_clicks_are_not_delivered(monkeypatch):
    clock = {"t": 2_000_000.0}
    monkeypatch.setattr(gate, "_now", lambda: clock["t"])
    _click("open_details")
    clock["t"] += actions.PENDING_CLICK_TTL_S + 1
    assert _ctx() == ""


def test_delivered_context_is_redacted_like_the_audit_log():
    _click("show_account", {"token": "abc123", "note": "hi"})
    text = _ctx()
    assert "abc123" not in text and "[redacted]" in text


def test_clicks_stay_in_their_session():
    _click("choose_plan", session="other-session")
    assert _ctx() == ""
    assert "event=choose_plan" in _ctx(session="other-session")
