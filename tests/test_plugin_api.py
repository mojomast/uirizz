"""Desktop ctx.rest backend: read a stored surface for live card refresh."""

from __future__ import annotations

import json

import pytest

from uirizz_plugin.catalog import BASIC_CATALOG_ID
from uirizz_plugin.store import put_surface, set_store_dir


@pytest.fixture(autouse=True)
def _store(tmp_path):
    set_store_dir(tmp_path)
    yield
    set_store_dir(None)


def _record(surface_id: str, revision: int = 1) -> dict:
    return {
        "surface_id": surface_id,
        "revision": revision,
        "fallback_text": "Hello",
        "messages": [
            {
                "version": "1.0",
                "createSurface": {
                    "surfaceId": surface_id,
                    "catalogId": BASIC_CATALOG_ID,
                    "components": [{"id": "root", "component": "Text", "text": "Hello"}],
                },
            }
        ],
        "component_count": 1,
        "component_ids": ["root"],
    }


def test_get_surface_payload_for_rest():
    from uirizz_plugin.api import surface_payload

    put_surface(_record("live", revision=2))
    body = surface_payload("live")
    assert body["ok"] is True
    assert body["surface_id"] == "live"
    assert body["revision"] == 2
    assert body["fallback_text"] == "Hello"
    assert body["messages"][0]["version"] == "1.0"
    # JSON-serializable for ctx.rest
    json.dumps(body)


def test_missing_surface_is_not_found():
    from uirizz_plugin.api import surface_payload

    body = surface_payload("missing")
    assert body["ok"] is False
    assert body["code"] == "not_found"


def test_dashboard_router_exports_surface_route():
    from dashboard.plugin_api import router

    paths = []
    for route in getattr(router, "routes", []):
        paths.append(getattr(route, "path", None))
    assert any(p and "surfaces" in p for p in paths)


def test_post_action_is_recorded_for_the_session():
    from dashboard.plugin_api import _record_action
    from uirizz_plugin.hooks import pre_llm_call

    body = _record_action(
        {
            "surface_id": "demo",
            "session_id": "sess-1",
            "event": "ok",
            "context": {"n": 1},
        }
    )
    assert body["ok"] is True
    result = pre_llm_call(session_id="sess-1")
    text = result if isinstance(result, str) else result["context"]
    assert "surface_id=" in text
    assert "demo" in text
    assert "ok" in text
    missing = _record_action({"surface_id": "demo", "event": "ok"})
    assert missing["ok"] is False
    assert missing["code"] == "invalid_payload"
