"""a2ui_render tool: schema, handlers, and registration."""

from __future__ import annotations

import json
from typing import Any

from uirizz_plugin import express as express_mod
from uirizz_plugin import gate
from uirizz_plugin.catalog import (
    BASIC_CATALOG_ID,
    BASIC_COMPONENTS,
    LIMITS,
    MVP_COMPONENTS,
)
from uirizz_plugin.register_util import call_register_tool
from uirizz_plugin.store import (
    StoreError,
    delete_surface,
    get_surface,
    mint_surface_id,
    normalize_surface_id,
    put_surface,
    _surfaces_dir,
)
from uirizz_plugin.validate import AdmissionError, admit_jsonl
from uirizz_plugin.gate import GateError

TOOLSET = "uirizz"
TOOL_NAME = "a2ui_render"

# Re-export catalog constants for existing imports/tests.
__all__ = [
    "A2UI_RENDER_SCHEMA",
    "BASIC_CATALOG_ID",
    "BASIC_COMPONENTS",
    "LIMITS",
    "MVP_COMPONENTS",
    "TOOL_NAME",
    "handle_a2ui_render",
    "parse_tool_result",
    "register_tools",
]

A2UI_RENDER_SCHEMA: dict[str, Any] = {
    "name": TOOL_NAME,
    "description": (
        "Present, update, delete, describe, or audit an A2UI v1.0 surface in this chat. "
        "Official Basic Catalog only. Never use shell, code, gh, or git to build the card. "
        "After success, copy the result's MEDIA: line alone on its own line into your reply: Desktop "
        "and Webapp draw the card from it; CLI, Telegram, and the classic dashboard show fallback_text only. "
        "fallback_text is required on present. Call op=describe for catalog, limits, and policy. "
        "Prefer Express; otherwise send v1.0 JSONL. Use weighted Row/Column layouts. "
        "Reuse surface_id with op=update (prefer updateDataModel) instead of a new card. "
        "A click is not approval. Never pass local file paths or http/data image URLs. "
        "On error, read code and fix and retry."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "op": {
                "type": "string",
                "enum": ["present", "update", "delete", "describe", "audit"],
                "description": (
                    "present: create a surface (new surface_id if omitted). "
                    "update: patch an existing surface_id in place. "
                    "delete: remove a surface_id. "
                    "describe: return catalog, limits, and policy. "
                    "audit: return the logged card actions (optional surface_id, limit)."
                ),
            },
            "surface_id": {
                "type": "string",
                "description": "Stable id. Optional on present; required on update and delete.",
            },
            "express": {
                "type": "string",
                "description": "Preferred A2UI Express source, compiled to v1.0. Omit if jsonl is set.",
            },
            "jsonl": {
                "type": "string",
                "description": "Raw A2UI v1.0 JSONL (one envelope per line) if express is omitted.",
            },
            "fallback_text": {
                "type": "string",
                "description": "Required plain-text copy of the surface for non-Desktop clients.",
            },
            "action_id": {
                "type": "string",
                "description": "With op=update: the action_id from an action notice you are reporting on.",
            },
            "action_outcome": {
                "type": "string",
                "enum": ["done", "failed", "cancelled"],
                "description": (
                    "With action_id: done or failed need the user's typed yes (status approved); "
                    "the call is rejected otherwise. cancelled is always allowed."
                ),
            },
            "limit": {
                "type": "integer",
                "description": "With op=audit: how many recent actions to return (max 200).",
            },
        },
        "required": ["op"],
        "additionalProperties": False,
    },
}

OUTPUT_NOTE = {
    "type": "object",
    "description": "JSON envelope. Always serialized with json.dumps.",
    "properties": {
        "ok": {"type": "boolean"},
        "error": {"type": "string"},
        "code": {"type": "string"},
        "fix": {"type": "string"},
    },
}


def _dumps(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def _error(code: str, error: str, fix: str, **extra: Any) -> str:
    body: dict[str, Any] = {"ok": False, "error": error, "code": code, "fix": fix}
    body.update(extra)
    return _dumps(body)


def describe_payload() -> dict[str, Any]:
    return {
        "ok": True,
        "op": "describe",
        "plugin": "uirizz",
        "version": "0.1.0",
        "protocol": LIMITS["protocol"],
        "catalog_id": BASIC_CATALOG_ID,
        "components": list(MVP_COMPONENTS),
        "basic_catalog_components": list(BASIC_COMPONENTS),
        "deferred_components": ["Video", "AudioPlayer"],
        "functions_disabled": ["openUrl"],
        "limits": {
            "max_payload_bytes": LIMITS["max_payload_bytes"],
            "max_components": LIMITS["max_components"],
        },
        "media": {
            "schemes": ["https"],
            "public_addresses_only": True,
            "local_files": False,
            "data_urls": False,
            "svg": False,
        },
        "hooks": {"pre_llm_call": True, "transform_llm_output": False},
        "ops": {
            "describe": "implemented",
            "present": "implemented",
            "update": "implemented",
            "delete": "implemented",
            "audit": "implemented",
        },
        "approval_gate": {
            "click_is_approval": False,
            "approval_source": "the user's typed yes in chat, after the pending notice was shown",
            "mark_side_effects": "put side_effect=true in the action context; unmarked and verb-matching clicks are gated too",
            "read_only": "put read_only=true in the action context for purely visual clicks",
            "ttl_seconds": gate.APPROVAL_TTL_S,
            "tools_allowed_while_pending": sorted(gate.SAFE_TOOLS_WHILE_PENDING),
            "report": "op=update with action_id and action_outcome=done|failed|cancelled",
        },
        "layout": {
            "default": "Weighted Row/Column children fill the card width; no grid.",
            "kpi": "Row of 3-5 Cards, weight=1, caption over value.",
            "master_detail": "weight=2 left, weight=3 right.",
            "views": "Tabs for alternate views, Modal for a short confirm, List with _template for repeats.",
            "updates": "op=update on the same surface_id; prefer data-model-only updateDataModel over a new card.",
            "icons": "Icon takes Material icon names; the font is bundled.",
            "slider_steps": "steps is divisions, not the increment (steps=1 on 1-12 = two stops).",
        },
        "theme": "night-hive",
    }


def _fail(exc: AdmissionError | StoreError | GateError) -> str:
    return _error(exc.code, exc.error, exc.fix)


def _require_fallback(payload: dict[str, Any], *, required: bool) -> str | None:
    text = payload.get("fallback_text")
    if text is None or (isinstance(text, str) and not text.strip()):
        if required:
            raise AdmissionError(
                "missing_fallback_text",
                "fallback_text is required.",
                "Provide a plain-text copy of the surface for CLI and other non-Desktop clients.",
            )
        return None
    if not isinstance(text, str):
        raise AdmissionError(
            "missing_fallback_text",
            "fallback_text must be a string.",
            "Provide a plain-text copy of the surface.",
        )
    return text


def _jsonl_from_args(payload: dict[str, Any]) -> str:
    express = payload.get("express")
    if isinstance(express, str) and express.strip():
        return express_mod.compile_express(express)
    jsonl = payload.get("jsonl")
    if not isinstance(jsonl, str) or not jsonl.strip():
        raise AdmissionError(
            "missing_payload",
            "No A2UI payload was provided.",
            "Send express with A2UI Express source, or jsonl with at least one v1.0 envelope.",
        )
    return jsonl


def parse_tool_result(result: str) -> dict[str, Any]:
    """Parse the JSON object at the start of a tool result, ignoring a trailing MEDIA line."""
    if not isinstance(result, str):
        raise TypeError("tool result must be a string")
    obj, _end = json.JSONDecoder().raw_decode(result.lstrip())
    if not isinstance(obj, dict):
        raise ValueError("tool result JSON must be an object")
    return obj


def _write_media(surface_id: str, fallback_text: str) -> str:
    path = _surfaces_dir() / f"{surface_id}.md"
    path.write_text(fallback_text.rstrip() + "\n", encoding="utf-8")
    return str(path)


def _success(op: str, record: dict[str, Any]) -> str:
    media_path = _write_media(record["surface_id"], record["fallback_text"])
    media_tag = f"MEDIA: {media_path}"
    body = _dumps(
        {
            "ok": True,
            "op": op,
            "surface_id": record["surface_id"],
            "revision": record["revision"],
            "fallback_text": record["fallback_text"],
            "component_count": record.get("component_count", 0),
            "media": media_tag,
            "next": "Put the MEDIA: line below, alone on its own line, in your reply so the card is drawn.",
        }
    )
    # Desktop only mounts a tool-media renderer when a standalone MEDIA: line
    # appears in the tool result (and then in the transcript). A JSON field
    # alone is not enough.
    return body + "\n" + media_tag + "\n"


def _rebind(messages: list[dict[str, Any]], surface_id: str, *, update: bool) -> list[dict[str, Any]]:
    """Point every envelope at the stored surface_id.

    Express always names its surface "main". The card looks a surface up by the
    id the tool returned, and an update must patch that surface rather than
    create a second one, so createSurface becomes updateComponents on update.
    """
    out: list[dict[str, Any]] = []
    for message in messages:
        env = dict(message)
        for key in ("createSurface", "updateComponents", "updateDataModel", "deleteSurface"):
            body = env.get(key)
            if isinstance(body, dict):
                body = dict(body)
                body["surfaceId"] = surface_id
                env[key] = body
        create = env.get("createSurface")
        if update and isinstance(create, dict):
            env.pop("createSurface")
            comps = create.get("components")
            if comps:
                env["updateComponents"] = {"surfaceId": surface_id, "components": comps}
            data = create.get("dataModel")
            if data:
                out.append({"version": env.get("version", "1.0"),
                            "updateDataModel": {"surfaceId": surface_id, "value": data}})
            if "updateComponents" not in env:
                continue
        out.append(env)
    return out


def _op_present(payload: dict[str, Any]) -> str:
    fallback = _require_fallback(payload, required=True)
    assert fallback is not None
    jsonl = _jsonl_from_args(payload)
    admitted = admit_jsonl(jsonl, require_root=True)
    requested = payload.get("surface_id") or admitted.get("surface_id")
    surface_id = normalize_surface_id(
        requested if isinstance(requested, str) else None,
        required=False,
    )
    if get_surface(surface_id) is not None:
        raise StoreError(
            "invalid_payload",
            f"surface_id {surface_id} already exists.",
            "Call op=update with this surface_id, or omit surface_id to mint a new one.",
        )
    record = {
        "surface_id": surface_id,
        "revision": 1,
        "fallback_text": fallback,
        "messages": _rebind(admitted["messages"], surface_id, update=False),
        "component_count": admitted["component_count"],
        "component_ids": admitted["component_ids"],
    }
    put_surface(record)
    return _success("present", record)


def _op_update(payload: dict[str, Any]) -> str:
    surface_id = normalize_surface_id(payload.get("surface_id"), required=True)
    existing = get_surface(surface_id)
    if existing is None:
        raise StoreError(
            "not_found",
            f"No surface named {surface_id} is stored.",
            "Call op=present first, or pass a surface_id returned by a previous present.",
        )
    fallback = _require_fallback(payload, required=False) or existing["fallback_text"]
    jsonl = _jsonl_from_args(payload)
    admitted = admit_jsonl(jsonl, require_root=False)
    # Fail-closed: reporting a side effect as done needs a live user approval.
    # Checked before anything is stored, so a rejected report changes nothing.
    action_id = payload.get("action_id")
    action_outcome = payload.get("action_outcome")
    if action_id is not None or action_outcome is not None:
        gate.complete_action(action_id, action_outcome)
    record = {
        "surface_id": surface_id,
        "revision": int(existing.get("revision", 1)) + 1,
        "fallback_text": fallback,
        "messages": list(existing.get("messages") or [])
        + _rebind(admitted["messages"], surface_id, update=True),
        "component_count": admitted["component_count"] or existing.get("component_count", 0),
        "component_ids": admitted["component_ids"] or existing.get("component_ids", []),
    }
    put_surface(record)
    return _success("update", record)


def _op_delete(payload: dict[str, Any]) -> str:
    surface_id = normalize_surface_id(payload.get("surface_id"), required=True)
    if not delete_surface(surface_id):
        raise StoreError(
            "not_found",
            f"No surface named {surface_id} is stored.",
            "Pass a surface_id that was created with op=present.",
        )
    media = _surfaces_dir() / f"{surface_id}.md"
    if media.is_file():
        media.unlink()
    return _dumps({"ok": True, "op": "delete", "surface_id": surface_id})


def handle_a2ui_render(args: dict | None) -> str:
    """Registered handler. Always returns a json.dumps string."""
    try:
        payload = args if isinstance(args, dict) else {}
        op = payload.get("op")
        if not isinstance(op, str) or not op:
            return _error(
                "invalid_op",
                "Missing or invalid op.",
                "Set op to present, update, delete, describe, or audit.",
            )
        if op == "describe":
            return _dumps(describe_payload())
        if op == "audit":
            return _dumps(
                gate.audit_view(
                    surface_id=payload.get("surface_id") if isinstance(payload.get("surface_id"), str) else None,
                    limit=payload.get("limit"),
                )
            )
        try:
            if op == "present":
                return _op_present(payload)
            if op == "update":
                return _op_update(payload)
            if op == "delete":
                return _op_delete(payload)
        except (AdmissionError, StoreError, GateError) as exc:
            return _fail(exc)
        return _error(
            "invalid_op",
            f"Unknown op={op!s}.",
            "Set op to present, update, delete, or describe.",
        )
    except Exception as exc:  # noqa: BLE001 — fail closed, never leak a traceback to the model
        return _error(
            "internal_error",
            "The tool failed unexpectedly.",
            "Retry op=describe, or report the failure. Do not invent a surface.",
            detail=type(exc).__name__,
        )


def register_tools(ctx) -> None:
    """Register tools. Names must match plugin.yaml provides_tools."""
    call_register_tool(
        ctx.register_tool,
        name=TOOL_NAME,
        toolset=TOOLSET,
        schema=A2UI_RENDER_SCHEMA,
        handler=handle_a2ui_render,
        description=A2UI_RENDER_SCHEMA["description"],
        output_schema=OUTPUT_NOTE,
    )
