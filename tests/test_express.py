"""Official A2UI Express compiles to admitted v1.0 JSONL."""

from __future__ import annotations

import json

import pytest

from uirizz_plugin.catalog import BASIC_CATALOG_ID
from uirizz_plugin.store import set_store_dir
from uirizz_plugin.tools import handle_a2ui_render

pytest.importorskip("a2ui", reason="a2ui-agent-sdk must be installed")

EXPRESS = """
root = Card(
  Column([
    Text("Hello from Express"),
    Button(Text("OK"), action=Event("ok", {}))
  ])
)
"""


def _load(result: str) -> dict:
    assert isinstance(result, str)
    body = json.loads(result)
    assert isinstance(body, dict)
    return body


@pytest.fixture(autouse=True)
def _store(tmp_path):
    set_store_dir(tmp_path)
    yield
    set_store_dir(None)


def test_compile_express_to_jsonl():
    from uirizz_plugin.express import compile_express

    jsonl = compile_express(EXPRESS)
    assert isinstance(jsonl, str)
    lines = [ln for ln in jsonl.splitlines() if ln.strip()]
    assert lines
    envelopes = [json.loads(ln) for ln in lines]
    assert all(env["version"] == "1.0" for env in envelopes)
    kinds = {k for env in envelopes for k in env if k != "version"}
    assert "createSurface" in kinds
    text = jsonl
    assert BASIC_CATALOG_ID in text
    assert "Hello from Express" in text
    assert "create_surface" not in text  # wire JSON uses camelCase


def test_present_accepts_raw_and_sentinel_express():
    raw = _load(
        handle_a2ui_render(
            {
                "op": "present",
                "surface_id": "hello-express",
                "fallback_text": "Hello from Express. Click OK.",
                "express": EXPRESS,
            }
        )
    )
    assert raw["ok"] is True
    assert raw["surface_id"] == "hello-express"
    assert raw["media"].startswith("MEDIA: ")
    assert raw["component_count"] >= 1

    wrapped = _load(
        handle_a2ui_render(
            {
                "op": "present",
                "surface_id": "hello-wrapped",
                "fallback_text": "Hello from Express. Click OK.",
                "express": f"<a2ui>{EXPRESS}</a2ui>",
            }
        )
    )
    assert wrapped["ok"] is True
    assert wrapped["surface_id"] == "hello-wrapped"


def test_invalid_express_fails_closed():
    body = _load(
        handle_a2ui_render(
            {
                "op": "present",
                "fallback_text": "nope",
                "express": "this is not valid express %%%",
            }
        )
    )
    assert body["ok"] is False
    assert body["code"] in {"invalid_payload", "express_error"}
    assert "fix" in body
    assert "ok" in body
