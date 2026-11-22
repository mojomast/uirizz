"""Compile official A2UI Express into camelCase v1.0 JSONL."""

from __future__ import annotations

import json
import re
from typing import Any

from uirizz_plugin.catalog import BASIC_CATALOG_ID
from uirizz_plugin.validate import AdmissionError

_SENTINEL = re.compile(r"<a2ui\b", re.IGNORECASE)


def _unavailable(exc: BaseException | None = None) -> AdmissionError:
    return AdmissionError(
        "express_unavailable",
        "A2UI Express compilation is not available in this build.",
        "Install a2ui-agent-sdk and retry, or send jsonl as raw A2UI v1.0 envelopes.",
    )


def _express_error(exc: BaseException) -> AdmissionError:
    return AdmissionError(
        "express_error",
        "The Express source could not be compiled.",
        "Correct the Express syntax, or send jsonl as raw A2UI v1.0 envelopes.",
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


def compile_express(source: str) -> str:
    """Return camelCase A2UI v1.0 JSONL for raw or <a2ui>-wrapped Express."""
    if not isinstance(source, str) or not source.strip():
        raise AdmissionError(
            "invalid_payload",
            "Express source was empty.",
            "Send Express inside the express argument, optionally wrapped in <a2ui> tags.",
        )
    processor = _processor()
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
