"""a2ui_render tool: schema, handlers, and registration."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from uirizz_plugin import express as express_mod
from uirizz_plugin import gate
from uirizz_plugin.catalog import (
    BASIC_CATALOG_ID,
    BASIC_COMPONENTS,
    LIMITS,
    MVP_COMPONENTS,
    UIRIZZ_CATALOG_ID,
    UIRIZZ_COMPONENTS,
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
    "UIRIZZ_CATALOG_ID",
    "UIRIZZ_COMPONENTS",
    "TOOL_NAME",
    "handle_a2ui_render",
    "parse_tool_result",
    "register_tools",
]

A2UI_RENDER_SCHEMA: dict[str, Any] = {
    "name": TOOL_NAME,
    "description": (
        "Draw a live A2UI card in Desktop/Webapp chat when the user will scan, compare, "
        "fill in, pick or watch structured data (status, comparison, form, list, progress, "
        "confirm). Not for prose, code or one-line answers. Never use shell, code, gh or git "
        "to build a card. First use: skill_view('uirizz:uirizz'); op=describe topic=recipes "
        "has tested Express. present needs fallback_text; then put the result's MEDIA: line "
        "alone in your reply. Same view: op=update on that surface_id (data-only `$/path = "
        "value` lines become updateDataModel); never re-present. Weighted Row/Column layouts. "
        "A click is not approval. No local paths or http/data images. On error, read code and "
        "fix, then retry."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "op": {
                "type": "string",
                "enum": ["present", "update", "delete", "describe", "audit"],
                "description": "present new card; update same card; describe catalog or topic; audit card actions.",
            },
            "surface_id": {
                "type": "string",
                "description": "Returned by present. Required on update and delete.",
            },
            "express": {
                "type": "string",
                "description": "A2UI Express source (preferred).",
            },
            "jsonl": {
                "type": "string",
                "description": "Raw A2UI v1.0 JSONL, one envelope per line, if not using express.",
            },
            "fallback_text": {
                "type": "string",
                "description": "Required on present: plain-text copy with the same facts, for CLI and chat apps.",
            },
            "topic": {
                "type": "string",
                "enum": ["recipes", "express", "actions", "components"],
                "description": "With op=describe: recipes, Express cheat sheet, actions, or components.",
            },
            "action_id": {
                "type": "string",
                "description": "With op=update: the action_id from an approval-gate notice.",
            },
            "action_outcome": {
                "type": "string",
                "enum": ["done", "failed", "cancelled"],
                "description": "done/failed need status=approved (the user's typed yes); declared actions record their own.",
            },
            "limit": {
                "type": "integer",
                "description": "With op=audit: max actions (200).",
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


_REFERENCES = Path(__file__).resolve().parent.parent / "skills" / "uirizz" / "references"
DESCRIBE_TOPICS = {"recipes": "recipes.md", "express": "express.md", "actions": None, "components": "components.md"}

_ACTIONS_HOWTO = (
    "Declared actions bind a button to one exact tool call. Wire one with "
    "Event(\"<action>\", {<param>: <value or $/path>}); no side_effect marker is needed. "
    "uirizz validates the params on click, shows its own confirm panel, and after the "
    "user's typed yes (\"yes <code>\" for risk high) lets only that call run, once. "
    "Outcomes are recorded automatically. Only actions listed here exist; never invent one."
)


def describe_topic(topic: str) -> dict[str, Any]:
    """Return a bundled reference file, so the model never depends on skill_view paths."""
    if topic == "actions":
        from uirizz_plugin import bindings

        report = bindings.status_report()
        return {"ok": True, "op": "describe", "topic": "actions", "howto": _ACTIONS_HOWTO, **report}
    name = DESCRIBE_TOPICS.get(topic)
    if name is None:
        raise AdmissionError(
            "invalid_payload",
            f"Unknown describe topic {topic!s}.",
            "Use topic=recipes, express, actions or components, or omit topic.",
        )
    path = _REFERENCES / name
    if not path.is_file():
        raise AdmissionError(
            "not_found",
            f"Reference {name} is not bundled in this install.",
            "Call op=describe without topic.",
        )
    return {"ok": True, "op": "describe", "topic": topic, "text": path.read_text(encoding="utf-8")}


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
        "uirizz_catalog_id": UIRIZZ_CATALOG_ID,
        "uirizz_components": list(UIRIZZ_COMPONENTS),
        "uirizz_note": (
            "Chart, DataTable, Metric, Progress, Badge, Callout, KeyValueList, Timeline and "
            "CodeBlock are available in Express and in jsonl with catalogId set to uirizz_catalog_id. "
            "op=describe topic=components has props and examples."
        ),
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
            "declared_actions": (
                "op=describe topic=actions lists buttons bound to one exact tool call. After the "
                "user's yes only that call runs, once; post_tool_call records the outcome."
            ),
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
        "topics": {
            "recipes": "op=describe topic=recipes: tested Express for status, compare, form, pick, list, confirm, progress, tabs",
            "express": "op=describe topic=express: grammar, signatures, icon names, gotchas",
            "actions": "op=describe topic=actions: buttons bound to exact tool calls (deploy, send, ...)",
            "components": "op=describe topic=components: Chart, DataTable, Metric, Progress, Badge, Callout, KeyValueList, Timeline, CodeBlock",
        },
    }


def _fail(exc: AdmissionError | StoreError | GateError) -> str:
    return _error(exc.code, exc.error, exc.fix)


def _require_fallback(
    payload: dict[str, Any],
    *,
    required: bool,
    messages: list[dict[str, Any]] | None = None,
) -> str | None:
    text = payload.get("fallback_text")
    if text is None or (isinstance(text, str) and not text.strip()):
        if required and messages is not None:
            from uirizz_plugin.fallback import generate_fallback

            generated = generate_fallback(messages)
            if generated.strip():
                return generated
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


def _jsonl_from_args(
    payload: dict[str, Any],
    *,
    prior: dict[str, Any] | None = None,
) -> str:
    express = payload.get("express")
    if isinstance(express, str) and express.strip():
        if prior is not None:
            return express_mod.compile_express(
                express,
                prior_messages=list(prior.get("messages") or []),
                surface_id=prior.get("surface_id"),
            )
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


def _action_warnings(messages: list[dict[str, Any]]) -> list[str]:
    try:
        from uirizz_plugin.bindings import surface_warnings

        return surface_warnings(messages)
    except Exception:  # noqa: BLE001 - warnings are advisory
        return []


def _success(op: str, record: dict[str, Any], warnings: list[str] | None = None) -> str:
    media_path = _write_media(record["surface_id"], record["fallback_text"])
    media_tag = f"MEDIA: {media_path}"
    extra: dict[str, Any] = {}
    if warnings:
        extra["action_warnings"] = warnings
        extra["action_fix"] = "These buttons will be rejected when clicked. See op=describe topic=actions."
    body = _dumps(
        {
            **extra,
            "ok": True,
            "op": op,
            "surface_id": record["surface_id"],
            "revision": record["revision"],
            "fallback_text": record["fallback_text"],
            "component_count": record.get("component_count", 0),
            "media": media_tag,
            "next": (
                "Put the MEDIA: line below, alone on its own line, in your reply so the card is drawn."
                if op == "present"
                else "The card already in the chat refreshes itself; do not paste this MEDIA: line again."
            ),
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


def _clean_id(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _check_conversation(existing: dict[str, Any], conversation_id: str | None) -> None:
    stored = _clean_id(existing.get("conversation_id"))
    if stored and conversation_id and stored != conversation_id:
        raise StoreError(
            "wrong_conversation",
            "That card belongs to another conversation.",
            "Present a new card in this conversation.",
        )


def _op_present(
    payload: dict[str, Any],
    session_id: str | None = None,
    conversation_id: str | None = None,
) -> str:
    jsonl = _jsonl_from_args(payload)
    admitted = admit_jsonl(jsonl, require_root=True)
    had_fallback = isinstance(payload.get("fallback_text"), str) and bool(payload["fallback_text"].strip())
    fallback = _require_fallback(payload, required=True, messages=admitted["messages"])
    assert fallback is not None
    # Express compiles every surface as "main". Using that as the stored id made
    # every second present collide with the first (possibly another chat's) card.
    # Only an explicit surface_id, or a surfaceId the model wrote in raw jsonl,
    # is honoured; otherwise a fresh id is minted.
    used_express = isinstance(payload.get("express"), str) and bool(payload["express"].strip())
    requested = payload.get("surface_id") or (None if used_express else admitted.get("surface_id"))
    surface_id = normalize_surface_id(
        requested if isinstance(requested, str) else None,
        required=False,
    )
    if get_surface(surface_id) is not None:
        raise StoreError(
            "invalid_payload",
            f"surface_id {surface_id} already exists.",
            "To change that card call op=update with this surface_id; for a new card omit surface_id.",
        )
    record = {
        "surface_id": surface_id,
        "revision": 1,
        "fallback_text": fallback,
        "messages": _rebind(admitted["messages"], surface_id, update=False),
        "component_count": admitted["component_count"],
        "component_ids": admitted["component_ids"],
        "session_id": session_id,
        "conversation_id": conversation_id,
    }
    put_surface(record)
    out = _success("present", record, _action_warnings(record["messages"]))
    if not had_fallback:
        out = _mark_generated(out)
    return out


def _mark_generated(result: str) -> str:
    body = parse_tool_result(result)
    tail = result.lstrip()[len(_dumps(body)):]
    body["fallback_generated"] = True
    return _dumps(body) + tail


def _op_update(
    payload: dict[str, Any],
    session_id: str | None = None,
    conversation_id: str | None = None,
) -> str:
    surface_id = normalize_surface_id(payload.get("surface_id"), required=True)
    existing = get_surface(surface_id)
    if existing is None:
        raise StoreError(
            "not_found",
            f"No surface named {surface_id} is stored.",
            "Call op=present first, or pass a surface_id returned by a previous present.",
        )
    _check_conversation(existing, conversation_id)
    fallback = _require_fallback(payload, required=False) or existing["fallback_text"]
    jsonl = _jsonl_from_args(payload, prior=existing)
    admitted = admit_jsonl(
        jsonl,
        require_root=False,
        uirizz_surface=any(
            isinstance(m.get("createSurface"), dict)
            and m["createSurface"].get("catalogId") == UIRIZZ_CATALOG_ID
            for m in (existing.get("messages") or [])
        ),
    )
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
        "session_id": existing.get("session_id"),
        "conversation_id": existing.get("conversation_id"),
    }
    put_surface(record)
    return _success("update", record, _action_warnings(_rebind(admitted["messages"], surface_id, update=True)))


def _op_delete(
    payload: dict[str, Any],
    session_id: str | None = None,
    conversation_id: str | None = None,
) -> str:
    surface_id = normalize_surface_id(payload.get("surface_id"), required=True)
    existing = get_surface(surface_id)
    if existing is not None:
        _check_conversation(existing, conversation_id)
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


def handle_a2ui_render(args: dict | None, **kwargs: Any) -> str:
    """Registered handler. Always returns a json.dumps string."""
    try:
        payload = args if isinstance(args, dict) else {}
        session_id = _clean_id(kwargs.get("session_id"))
        conversation_id = _clean_id(kwargs.get("conversation_id"))
        op = payload.get("op")
        if not isinstance(op, str) or not op:
            return _error(
                "invalid_op",
                "Missing or invalid op.",
                "Set op to present, update, delete, describe, or audit.",
            )
        if op == "describe":
            topic = payload.get("topic")
            if isinstance(topic, str) and topic:
                try:
                    return _dumps(describe_topic(topic))
                except AdmissionError as exc:
                    return _fail(exc)
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
                return _op_present(payload, session_id, conversation_id)
            if op == "update":
                return _op_update(payload, session_id, conversation_id)
            if op == "delete":
                return _op_delete(payload, session_id, conversation_id)
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
