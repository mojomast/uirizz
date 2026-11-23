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
        source_component_id=body.get("source_component_id"),
        client_timestamp=body.get("timestamp"),
    )
    return {
        "ok": True,
        "surface_id": rec["surface_id"],
        "event": rec["event"],
        "session_id": rec["session_id"],
        "action_id": rec["action_id"],
        "requires_confirmation": rec["requires_confirmation"],
        "status": rec["status"],
        # Plugin-rendered confirm for declared actions: title, tool, redacted
        # args, risk, and whether the typed yes needs the code.
        "binding": rec.get("binding"),
        "rejected": rec.get("rejected"),
        # A click never approves anything. The only exception is a low-risk
        # declared action the user marked auto_approve in their own actions file.
        "approved": rec["status"] == "approved",
    }


def _audit(surface_id: str | None, session_id: str | None, limit: int | None) -> dict[str, Any]:
    from uirizz_plugin.gate import audit_view

    return audit_view(session_id=session_id, surface_id=surface_id, limit=limit)


if APIRouter is not None:
    router = APIRouter()

    @router.get("/surfaces/{surface_id}")
    def get_surface(surface_id: str) -> dict[str, Any]:
        return surface_payload(surface_id)

    @router.post("/actions")
    def post_action(body: dict[str, Any]) -> dict[str, Any]:
        try:
            return _record_action(body)
        except Exception:  # noqa: BLE001 — fail closed; nothing was approved
            return {
                "ok": False,
                "code": "record_failed",
                "error": "The action could not be logged, so it was not accepted.",
                "fix": "Retry the click.",
                "approved": False,
            }

    @router.get("/audit")
    def get_audit(
        surface_id: str | None = None, session_id: str | None = None, limit: int | None = None
    ) -> dict[str, Any]:
        try:
            return _audit(surface_id, session_id, limit)
        except Exception:  # noqa: BLE001
            return {"ok": False, "code": "audit_unavailable", "error": "The audit log could not be read.", "fix": "Check the plugin data directory."}

else:

    class _FallbackRouter:
        def __init__(self) -> None:
            self.routes = [
                SimpleNamespace(path="/surfaces/{surface_id}"),
                SimpleNamespace(path="/actions"),
                SimpleNamespace(path="/audit"),
            ]

    router = _FallbackRouter()
