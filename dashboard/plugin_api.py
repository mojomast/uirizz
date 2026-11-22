"""Dashboard REST router exposing stored surfaces for live card refresh."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from uirizz_plugin.api import surface_payload

try:
    from fastapi import APIRouter
except ImportError:
    APIRouter = None  # type: ignore[assignment]

def _record_action(body: dict[str, Any]) -> dict[str, Any]:
    from uirizz_plugin.actions import record_action

    surface_id = body.get("surface_id")
    session_id = body.get("session_id")
    event = body.get("event")
    if not isinstance(surface_id, str) or not surface_id:
        return {
            "ok": False,
            "code": "invalid_payload",
            "error": "surface_id is required.",
            "fix": "POST a surface_id from the rendered card.",
        }
    if not isinstance(session_id, str) or not session_id:
        return {
            "ok": False,
            "code": "invalid_payload",
            "error": "session_id is required.",
            "fix": "POST the chat session_id with the action.",
        }
    if not isinstance(event, str) or not event:
        return {
            "ok": False,
            "code": "invalid_payload",
            "error": "event is required.",
            "fix": "POST the UI event name.",
        }
    rec = record_action(
        surface_id=surface_id,
        session_id=session_id,
        event=event,
        context=body.get("context") or {},
    )
    return {
        "ok": True,
        "surface_id": rec["surface_id"],
        "event": rec["event"],
        "session_id": rec["session_id"],
    }


if APIRouter is not None:
    router = APIRouter()

    @router.get("/surfaces/{surface_id}")
    def get_surface(surface_id: str) -> dict[str, Any]:
        return surface_payload(surface_id)

    @router.post("/actions")
    def post_action(body: dict[str, Any]) -> dict[str, Any]:
        return _record_action(body)

else:

    class _FallbackRouter:
        def __init__(self) -> None:
            self.routes = [
                SimpleNamespace(path="/surfaces/{surface_id}"),
                SimpleNamespace(path="/actions"),
            ]

    router = _FallbackRouter()
