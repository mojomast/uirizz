"""Express output is rebound to the stored surface_id and carries no nulls."""

from __future__ import annotations

import json

import pytest

from uirizz_plugin.store import get_surface, set_store_dir
from uirizz_plugin.tools import handle_a2ui_render, parse_tool_result

pytest.importorskip("a2ui", reason="a2ui-agent-sdk must be installed")

A = 'root = Card(Column([Text("Orders: 12")]))'
B = 'root = Card(Column([Text("Orders: 13")]))'


@pytest.fixture(autouse=True)
def _store(tmp_path):
    set_store_dir(tmp_path)
    yield
    set_store_dir(None)


def test_present_and_update_bind_to_surface_id_without_nulls():
    r1 = parse_tool_result(
        handle_a2ui_render({"op": "present", "surface_id": "s1", "fallback_text": "x", "express": A})
    )
    r2 = parse_tool_result(handle_a2ui_render({"op": "update", "surface_id": "s1", "express": B}))
    assert r1["ok"] and r2["ok"] and r2["revision"] == 2
    messages = get_surface("s1")["messages"]
    assert [next(k for k in m if k != "version") for m in messages] == ["createSurface", "updateComponents"]
    for m in messages:
        body = m.get("createSurface") or m.get("updateComponents")
        assert body["surfaceId"] == "s1"
    assert ":null" not in json.dumps(messages, separators=(",", ":"))
