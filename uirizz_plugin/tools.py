"""a2ui_render tool: schema, handlers, and registration."""

from __future__ import annotations

import json
from typing import Any

from uirizz_plugin.register_util import call_register_tool

TOOLSET = "uirizz"
TOOL_NAME = "a2ui_render"

BASIC_CATALOG_ID = "https://a2ui.org/specification/v1_0/catalogs/basic/catalog.json"

BASIC_COMPONENTS = (
    "Text",
    "Image",
    "Icon",
    "Video",
    "AudioPlayer",
    "Row",
    "Column",
    "List",
    "Card",
    "Tabs",
    "Divider",
    "Modal",
    "Button",
    "TextField",
    "CheckBox",
    "ChoicePicker",
    "Slider",
    "DateTimeInput",
)

# Video and AudioPlayer stay in the official catalog list for describe(), but
# admission will reject them until a later cut proves the same URL guard.
MVP_COMPONENTS = tuple(
    name for name in BASIC_COMPONENTS if name not in {"Video", "AudioPlayer"}
)

LIMITS = {
    "max_payload_bytes": 256 * 1024,
    "max_components": 100,
    "protocol": "1.0",
}

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

_IMPLEMENTED_OPS = frozenset({"describe"})


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
            "present": "not_implemented",
            "update": "not_implemented",
            "delete": "not_implemented",
        },
        "theme": "night-hive",
    }


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
        if op in {"present", "update", "delete"}:
            return _error(
                "not_implemented",
                f"op={op} is not implemented in this scaffold.",
                "Use op=describe for now. present, update, and delete will land on a feature branch.",
                op=op,
            )
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
            # Keep the exception class only; no stack, paths, or secrets.
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
