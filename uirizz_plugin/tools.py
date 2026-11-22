"""a2ui_render tool: schema, handlers, and registration."""

from __future__ import annotations

import json
from typing import Any

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
    "register_tools",
]

A2UI_RENDER_SCHEMA: dict[str, Any] = {
    "name": TOOL_NAME,
    "description": (
        "Present, update, delete, or describe an A2UI v1.0 surface in this chat. "
        "Use official Basic Catalog components only. Desktop and Webapp render a "
        "MEDIA: file from the result; CLI, Telegram, and the classic dashboard "
        "show fallback_text only. Call op=describe for the catalog, limits, and "
        "media policy. Prefer Express; otherwise send v1.0 JSONL. Reuse "
        "surface_id with op=update instead of creating a new card. Never pass "
        "local file paths or http/data image URLs."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "op": {
                "type": "string",
                "enum": ["present", "update", "delete", "describe"],
                "description": (
                    "present: create a surface (new surface_id if omitted). "
                    "update: patch an existing surface_id in place. "
                    "delete: remove a surface_id. "
                    "describe: return catalog, limits, and policy."
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
        },
        "theme": "night-hive",
    }


def _fail(exc: AdmissionError | StoreError) -> str:
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
    jsonl = payload.get("jsonl")
    if isinstance(express, str) and express.strip():
        raise AdmissionError(
            "express_unavailable",
            "A2UI Express compilation is not enabled in this build.",
            "Send jsonl as raw A2UI v1.0 envelopes (one per line) instead of express.",
        )
    if not isinstance(jsonl, str) or not jsonl.strip():
        raise AdmissionError(
            "missing_payload",
            "No A2UI payload was provided.",
            "Send jsonl with at least one v1.0 envelope, or express once compilation is available.",
        )
    return jsonl


def _write_media(surface_id: str, fallback_text: str) -> str:
    path = _surfaces_dir() / f"{surface_id}.md"
    path.write_text(fallback_text.rstrip() + "\n", encoding="utf-8")
    return str(path)


def _success(op: str, record: dict[str, Any]) -> str:
    media_path = _write_media(record["surface_id"], record["fallback_text"])
    return _dumps(
        {
            "ok": True,
            "op": op,
            "surface_id": record["surface_id"],
            "revision": record["revision"],
            "fallback_text": record["fallback_text"],
            "component_count": record.get("component_count", 0),
            "media": f"MEDIA: {media_path}",
        }
    )


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
        "messages": admitted["messages"],
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
    record = {
        "surface_id": surface_id,
        "revision": int(existing.get("revision", 1)) + 1,
        "fallback_text": fallback,
        "messages": list(existing.get("messages") or []) + admitted["messages"],
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
                "Set op to present, update, delete, or describe.",
            )
        if op == "describe":
            return _dumps(describe_payload())
        try:
            if op == "present":
                return _op_present(payload)
            if op == "update":
                return _op_update(payload)
            if op == "delete":
                return _op_delete(payload)
        except (AdmissionError, StoreError) as exc:
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
