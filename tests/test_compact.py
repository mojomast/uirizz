from __future__ import annotations

import pytest

from uirizz_plugin import store
from uirizz_plugin.compact import compact_messages, maybe_compact
from uirizz_plugin.tools import handle_a2ui_render, parse_tool_result

CAT = "https://a2ui.org/specification/v1_0/catalogs/basic/catalog.json"


def _create(components, data=None, **extra):
    body = {"surfaceId": "s", "catalogId": CAT, "components": components, **extra}
    if data is not None:
        body["dataModel"] = data
    return {"version": "1.0", "createSurface": body}


def _comps(*c):
    return {"version": "1.0", "updateComponents": {"surfaceId": "s", "components": list(c)}}


def _data(path=None, value="__absent__"):
    body = {"surfaceId": "s"}
    if path is not None:
        body["path"] = path
    if value != "__absent__":
        body["value"] = value
    return {"version": "1.0", "updateDataModel": body}


def _model(msgs):
    out = compact_messages(msgs)
    assert len(out) == 1
    return out[0]["createSurface"]["dataModel"]


def test_components_override_and_append():
    msgs = [
        _create([{"id": "root", "component": "Text", "text": "a"}, {"id": "b", "component": "Text", "text": "b"}], theme={"x": 1}),
        _comps({"id": "root", "component": "Text", "text": "A2"}, {"id": "c", "component": "Text", "text": "c"}),
    ]
    out = compact_messages(msgs)
    assert len(out) == 1 and out[0]["version"] == "1.0"
    cs = out[0]["createSurface"]
    assert cs["surfaceId"] == "s" and cs["catalogId"] == CAT and cs["theme"] == {"x": 1}
    assert [c["id"] for c in cs["components"]] == ["root", "b", "c"]
    assert cs["components"][0]["text"] == "A2"


def test_nested_path_upsert():
    assert _model([_create([], {"a": 1}), _data("/x/y/z", 5)]) == {"a": 1, "x": {"y": {"z": 5}}}


def test_array_index():
    m = _model([_create([], {"l": [1, 2, 3]}), _data("/l/1", 9), _data("/l/-", 4), _data("/l/0", None)])
    assert m == {"l": [9, 3, 4]}


def test_root_replace():
    assert _model([_create([], {"a": 1}), _data(None, {"b": 2})]) == {"b": 2}
    assert _model([_create([], {"a": 1}), _data("/", {"b": 2})]) == {"b": 2}


def test_delete_null_and_absent():
    m = _model([_create([], {"a": 1, "b": 2, "c": 3}), _data("/a", None), _data("/b")])
    assert m == {"c": 3}


def test_escaped_pointers():
    m = _model([_create([], {}), _data("/a~1b", 1), _data("/m~0n", 2)])
    assert m == {"a/b": 1, "m~n": 2}


def test_delete_surface_unchanged():
    msgs = [_create([]), _data("/a", 1), {"version": "1.0", "deleteSurface": {"surfaceId": "s"}}]
    assert compact_messages(msgs) == msgs


def test_unknown_keys_unchanged():
    msgs = [_create([]), {"version": "1.0", "mystery": {}}]
    assert compact_messages(msgs) == msgs
    bad = [_create([]), {"version": "1.0", "updateDataModel": {"surfaceId": "s", "path": "/a", "value": 1, "extra": 1}}]
    assert compact_messages(bad) == bad


def test_maybe_compact_threshold():
    msgs = [_create([], {})] + [_data("/n", i) for i in range(5)]
    assert maybe_compact(msgs, threshold=10) is msgs
    assert len(maybe_compact(msgs, threshold=5)) == 1


@pytest.fixture
def _store(tmp_path):
    store.set_store_dir(tmp_path / "surfaces")
    yield
    store.set_store_dir(None)


def test_e2e_sixty_updates_compact(_store):
    pytest.importorskip("a2ui", reason="a2ui-agent-sdk is required for Express")
    r = parse_tool_result(handle_a2ui_render({
        "op": "present", "surface_id": "ctr",
        "express": '$/n = 0\nroot = Text(formatString("${/n}"))', "fallback_text": "n",
    }))
    assert r["ok"], r
    for i in range(1, 61):
        r = parse_tool_result(handle_a2ui_render({
            "op": "update", "surface_id": "ctr", "express": f"$/n = {i}", "fallback_text": "n",
        }))
        assert r["ok"], r
    rec = store.get_surface("ctr")
    assert rec["revision"] == 61
    assert len(rec["messages"]) <= 41
    model = {}
    for env in rec["messages"]:
        if "createSurface" in env:
            model = env["createSurface"].get("dataModel", {})
        else:
            model = _apply_simple(model, env["updateDataModel"])
    assert model == {"n": 60}


def _apply_simple(model, body):
    model = dict(model)
    model[body["path"].lstrip("/")] = body["value"]
    return model
