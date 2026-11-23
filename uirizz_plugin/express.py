"""Compile official A2UI Express into camelCase v1.0 JSONL."""

from __future__ import annotations

import json
import re
from typing import Any

from uirizz_plugin.catalog import BASIC_CATALOG_ID
from uirizz_plugin.validate import AdmissionError

_SENTINEL = re.compile(r"<a2ui\b", re.IGNORECASE)
_WRAPPED = re.compile(r"<a2ui[^>]*>(.*?)</a2ui>", re.IGNORECASE | re.DOTALL)
_SURFACE_STMT = re.compile(r"^\s*surface\s*\(", re.MULTILINE)
_CTRL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")
# Long enough to carry the compiler's line/column and enum list, short enough
# to keep a retry cheap.
_DETAIL_MAX = 600


def _unavailable(exc: BaseException | None = None) -> AdmissionError:
    return AdmissionError(
        "express_unavailable",
        "A2UI Express compilation is not available in this build.",
        "Install a2ui-agent-sdk and retry, or send jsonl as raw A2UI v1.0 envelopes.",
    )


def _detail(exc: BaseException) -> str:
    """The compiler's own message (line, column, allowed enum values), sanitized."""
    text = _CTRL.sub(" ", str(exc) or type(exc).__name__).strip()
    text = text.replace(" - Help: Please correct the syntax error in your Express DSL.", "")
    if len(text) > _DETAIL_MAX:
        text = text[: _DETAIL_MAX - 3] + "..."
    return text


def _express_error(exc: BaseException) -> AdmissionError:
    detail = _detail(exc)
    fix = "Fix the line the compiler names and resend. See op=describe topic=express for signatures."
    if "Surface not found" in detail:
        fix = "A present needs a `root = ...` line. For a data-only change use op=update."
    return AdmissionError(
        "express_error",
        f"The Express source could not be compiled: {detail}",
        fix,
    )


def _dump_message(message: Any) -> dict[str, Any]:
    if hasattr(message, "model_dump"):
        dumped = message.model_dump(by_alias=True, mode="json", exclude_none=True)
        if isinstance(dumped, dict):
            return dumped
    if isinstance(message, dict):
        return message
    raise _express_error(TypeError(type(message).__name__))


def _messages_from_parts(parts: Any) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    if not parts:
        return messages
    for part in parts:
        payload = getattr(part, "a2ui", None)
        if payload is None:
            continue
        items = payload if isinstance(payload, list) else [payload]
        for item in items:
            messages.append(_dump_message(item))
    return messages


def _processor():
    try:
        from a2ui.core.basic_catalog import BasicCatalog, ProtocolVersion
        from a2ui.core.schema.v1_0.renderer_capabilities import (
            A2uiRendererCapabilities,
            V10Capabilities,
        )
        from a2ui.inference_formats.express import ExpressFormatFactory
        from a2ui.processor import A2uiGenerator, CatalogConfig
    except ImportError as exc:
        raise _unavailable(exc) from exc

    try:
        catalog = BasicCatalog(ProtocolVersion.V1_0)
        generator = A2uiGenerator(
            catalogs=[CatalogConfig(catalog=catalog)],
            inference_format_factory=ExpressFormatFactory(),
        )
        caps = A2uiRendererCapabilities(
            v1_0=V10Capabilities(supported_catalog_ids=[BASIC_CATALOG_ID])
        )
        return generator.create_processor(caps)
    except AdmissionError:
        raise
    except Exception as exc:
        raise _unavailable(exc) from exc


def _unwrap(source: str) -> str:
    match = _WRAPPED.search(source)
    return match.group(1) if match else source


def _state_for(processor, prior_messages: list[dict[str, Any]] | None):
    """Mirror the stored surface so an update can be checked against it.

    The SDK calls this the canvas pattern: one RendererState per surface, so a
    data-only update (`$/kpi/rps = 42`) compiles to updateDataModel instead of
    failing with "Surface not found".
    """
    if not prior_messages:
        return None
    try:
        state = processor.create_state()
        state.apply([dict(m) for m in prior_messages])
        return state
    except Exception:  # noqa: BLE001 - fall back to a stateless compile
        return None


def compile_express(
    source: str,
    *,
    prior_messages: list[dict[str, Any]] | None = None,
    surface_id: str | None = None,
) -> str:
    """Return camelCase A2UI v1.0 JSONL for raw or <a2ui>-wrapped Express.

    With ``prior_messages`` and ``surface_id`` (op=update), the source is
    compiled against the stored surface, and a missing ``surface(...)`` header
    is added for the model so it can send only what changed.
    """
    if not isinstance(source, str) or not source.strip():
        raise AdmissionError(
            "invalid_payload",
            "Express source was empty.",
            "Send Express inside the express argument, optionally wrapped in <a2ui> tags.",
        )
    processor = _processor()
    state = _state_for(processor, prior_messages)
    if state is not None and surface_id:
        body = _unwrap(source)
        if not _SURFACE_STMT.search(body):
            body = f'surface("{surface_id}", update=true)\n{body}'
        try:
            parts = processor.parse_response(f"<a2ui>{body}</a2ui>", wrapped=True, state=state)
            messages = _messages_from_parts(parts)
        except AdmissionError:
            raise
        except Exception as exc:
            raise _express_error(exc) from exc
        if not messages:
            raise _express_error(ValueError("no A2UI messages"))
        return "\n".join(json.dumps(item, ensure_ascii=False, separators=(",", ":")) for item in messages)
    wrapped = bool(_SENTINEL.search(source))
    try:
        parts = processor.parse_response(source, wrapped=wrapped)
        messages = _messages_from_parts(parts)
        if not messages and wrapped:
            parts = processor.parse_response(source, wrapped=False)
            messages = _messages_from_parts(parts)
        elif not messages and not wrapped:
            parts = processor.parse_response(f"<a2ui>{source}</a2ui>", wrapped=True)
            messages = _messages_from_parts(parts)
    except AdmissionError:
        raise
    except Exception as exc:
        raise _express_error(exc) from exc
    if not messages:
        raise _express_error(ValueError("no A2UI messages"))
    return "\n".join(json.dumps(item, ensure_ascii=False, separators=(",", ":")) for item in messages)
