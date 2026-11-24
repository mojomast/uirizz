"""generate_fallback skips a component it cannot render, and says which one."""

from __future__ import annotations

import logging

from uirizz_plugin.fallback import generate_fallback


def _msgs(*components):
    return [{"version": "1.0", "createSurface": {
        "surfaceId": "s", "dataModel": {"rows": [1, 2]},
        "components": list(components)}}]


def test_unrenderable_component_is_skipped_and_logged(caplog):
    # "²" passes str.isdigit() but int() rejects it, so resolving this path raises.
    bad = {"id": "bad", "component": "DataTable", "rows": {"@path": "/rows/\u00b2"}}
    good = {"id": "ok", "component": "Text", "text": "Still here"}
    with caplog.at_level(logging.WARNING, logger="uirizz_plugin.fallback"):
        assert generate_fallback(_msgs(bad, good)) == "Still here"
    skipped = [r for r in caplog.records if r.name == "uirizz_plugin.fallback"]
    assert len(skipped) == 1
    assert "bad" in skipped[0].getMessage() and "DataTable" in skipped[0].getMessage()
    assert "ValueError" in skipped[0].getMessage()


def test_renderable_components_log_nothing(caplog):
    with caplog.at_level(logging.DEBUG, logger="uirizz_plugin.fallback"):
        assert generate_fallback(_msgs({"id": "t", "component": "Text", "text": "Hi"})) == "Hi"
    assert not [r for r in caplog.records if r.name == "uirizz_plugin.fallback"]
