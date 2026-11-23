"""Regressions found while reviewing how a model actually authors uirizz cards.

1. Express always compiles to surface "main"; a second present collided.
2. Express compile errors dropped the compiler's line/column and enum list.
3. Data-only Express updates failed: the compile had no record of the surface.
4. Non-gated clicks were re-injected into every later turn.
"""

from __future__ import annotations

import json

import pytest

from uirizz_plugin import store
from uirizz_plugin.tools import handle_a2ui_render, parse_tool_result

pytest.importorskip("a2ui", reason="a2ui-agent-sdk is required for Express")


@pytest.fixture(autouse=True)
def _store(tmp_path):
    store.set_store_dir(tmp_path / "surfaces")
    yield
    store.set_store_dir(None)


def _call(**args):
    return parse_tool_result(handle_a2ui_render(args))


def test_two_express_presents_without_surface_id_get_distinct_ids():
    a = _call(op="present", express='root = Text("A")', fallback_text="A")
    b = _call(op="present", express='root = Text("B")', fallback_text="B")
    assert a["ok"] and b["ok"], b
    assert a["surface_id"] != b["surface_id"]
    assert "main" not in (a["surface_id"], b["surface_id"])


def test_explicit_surface_id_is_still_honoured():
    a = _call(op="present", surface_id="deploy-1", express='root = Text("A")', fallback_text="A")
    assert a["surface_id"] == "deploy-1"


@pytest.mark.parametrize(
    "source, needle",
    [
        ('root = Column([Text("Title", "h1")])', "caption"),
        ('root = Row([Icon("trending_up")])', "accountCircle"),
        ('root = Table([Text("a")])', "Table"),
        ('root = Column([Text("a")\nfoo = Bar(', "line 2"),
    ],
)
def test_express_errors_carry_compiler_detail(source, needle):
    out = _call(op="present", express=source, fallback_text="x")
    assert out["ok"] is False
    assert out["code"] == "express_error"
    assert needle.lower() in out["error"].lower()
    assert len(out["error"]) < 800


def test_missing_root_gets_a_specific_fix():
    out = _call(op="present", express='x = Text("hi")', fallback_text="x")
    assert out["code"] == "express_error"
    assert "root" in out["fix"]


def test_data_only_express_update_compiles_to_update_data_model():
    p = _call(
        op="present",
        express='$/kpi/rps = 10\nroot = Card(Text(formatString("${/kpi/rps} rps")))',
        fallback_text="10 rps",
    )
    sid = p["surface_id"]
    u = _call(op="update", surface_id=sid, express="$/kpi/rps = 42")
    assert u["ok"], u
    assert u["revision"] == 2
    last = store.get_surface(sid)["messages"][-1]
    assert last["updateDataModel"] == {"surfaceId": sid, "path": "/kpi/rps", "value": 42}
    # No components were resent.
    assert not any("updateComponents" in m for m in store.get_surface(sid)["messages"][1:])


def test_structural_express_update_still_works():
    p = _call(op="present", express='root = Column([Text("one")])', fallback_text="1")
    u = _call(op="update", surface_id=p["surface_id"], express='root = Column([Text("one"), Text("two")])')
    assert u["ok"], u


def test_non_gated_clicks_are_delivered_once():
    from uirizz_plugin import actions

    p = _call(op="present", express='root = Text("x")', fallback_text="x")
    actions.record_action(p["surface_id"], "sess-1", "refresh", {"read_only": True})
    first = actions.pending_context_for_session("sess-1")
    assert first and "refresh" in first
    assert actions.pending_context_for_session("sess-1") is None


@pytest.mark.parametrize("topic", ["recipes", "express"])
def test_describe_topics_return_bundled_references(topic):
    out = json.loads(handle_a2ui_render({"op": "describe", "topic": topic}))
    assert out["ok"] and out["topic"] == topic and len(out["text"]) > 500


def test_describe_unknown_topic_fails_closed():
    out = json.loads(handle_a2ui_render({"op": "describe", "topic": "nope"}))
    assert out["ok"] is False and out["code"] == "invalid_payload"


def test_compile_express_rejects_injected_surface_id():
    from uirizz_plugin.express import compile_express
    from uirizz_plugin.validate import AdmissionError

    p = _call(
        op="present",
        express='$/kpi/rps = 10\nroot = Card(Text(formatString("${/kpi/rps} rps")))',
        fallback_text="10 rps",
    )
    prior = store.get_surface(p["surface_id"])["messages"]
    with pytest.raises(AdmissionError) as caught:
        compile_express(
            "$/kpi/rps = 42",
            prior_messages=prior,
            surface_id='x"); root = Text("injected") #',
        )
    assert caught.value.code == "invalid_payload"


def test_detail_redacts_paths_and_tracebacks():
    from uirizz_plugin.express import _detail

    class Fake(Exception):
        pass

    long = _detail(Fake("N" * 900))
    assert len(long) == 600 and long.endswith("...")
    ctrl = _detail(Fake("line 1\x00\x07 oops - Help: Please correct the syntax error in your Express DSL."))
    assert "\x00" not in ctrl and "Please correct" not in ctrl
    leaked = _detail(Fake("failed at /home/box/secret/key.pem"))
    assert "/home/" not in leaked and "<redacted>" in leaked
    tb = _detail(
        Fake(
            'Traceback (most recent call last):\n  File "/opt/uirizz/express.py", line 9\nValueError: bad enum'
        )
    )
    assert "Traceback" not in tb and "/opt/" not in tb
    assert "bad enum" in tb or tb == "internal compiler error"


def test_describe_topic_is_allowlisted_and_fails_closed(tmp_path, monkeypatch):
    from uirizz_plugin import tools as tools_mod

    for topic in ("../etc/passwd", "recipes.md", "layout", "express/../../tools.py"):
        out = json.loads(handle_a2ui_render({"op": "describe", "topic": topic}))
        assert out["ok"] is False and out["code"] == "invalid_payload"
    monkeypatch.setattr(tools_mod, "_REFERENCES", tmp_path / "missing")
    out = json.loads(handle_a2ui_render({"op": "describe", "topic": "recipes"}))
    assert out["ok"] is False and out["code"] == "not_found"
