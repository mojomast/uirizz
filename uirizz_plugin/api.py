"""Read-only REST payload for a stored A2UI surface."""

from __future__ import annotations

from typing import Any

from uirizz_plugin.store import StoreError, get_surface, normalize_surface_id


def _not_found() -> dict[str, Any]:
    return {
        "ok": False,
        "code": "not_found",
        "error": "No surface is stored under that surface_id.",
        "fix": "Pass a surface_id returned by a2ui_render present or update.",
    }


def surface_payload(surface_id: str) -> dict[str, Any]:
    """Return the stored surface as a JSON-serializable dict."""
    try:
        safe_id = normalize_surface_id(surface_id, required=True)
    except StoreError:
        return _not_found()
    record = get_surface(safe_id)
    if record is None:
        return _not_found()
    return {
        "ok": True,
        "surface_id": record.get("surface_id", safe_id),
        "revision": record.get("revision", 1),
        "fallback_text": record.get("fallback_text", ""),
        "messages": record.get("messages", []),
    }
