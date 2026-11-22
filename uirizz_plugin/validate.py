"""Admit A2UI v1.0 payloads against the official Basic Catalog allowlist."""

from __future__ import annotations

import json
from typing import Any, Callable, Iterable

from uirizz_plugin.catalog import BASIC_CATALOG_ID, LIMITS, MVP_COMPONENTS
from uirizz_plugin.urls import UrlPolicyError, validate_https_public_url

ALLOWED_OPS_MESSAGES = ("createSurface", "updateComponents", "updateDataModel", "deleteSurface")
DEFERRED_COMPONENTS = frozenset({"Video", "AudioPlayer"})
# Image property names that may carry a URL in the official Basic Catalog.
_URL_KEYS = frozenset({"url", "posterUrl"})


class AdmissionError(ValueError):
    def __init__(self, code: str, error: str, fix: str) -> None:
        super().__init__(error)
        self.code = code
        self.error = error
        self.fix = fix


def _as_error(exc: UrlPolicyError) -> AdmissionError:
    return AdmissionError(exc.code, exc.error, exc.fix)


def parse_jsonl(text: str) -> list[dict[str, Any]]:
    if not isinstance(text, str) or not text.strip():
        raise AdmissionError(
            "missing_payload",
            "No A2UI payload was provided.",
            "Send express or jsonl with at least one v1.0 envelope.",
        )
    raw = text.encode("utf-8")
    if len(raw) > LIMITS["max_payload_bytes"]:
        raise AdmissionError(
            "oversize",
            "Payload exceeds the 256 KiB limit.",
            "Shrink the surface so the payload is at most 262144 bytes.",
        )
    messages: list[dict[str, Any]] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            item = json.loads(stripped)
        except json.JSONDecodeError:
            raise AdmissionError(
                "invalid_payload",
                f"Line {lineno} is not valid JSON.",
                "Send one A2UI v1.0 envelope per JSONL line.",
            ) from None
        if not isinstance(item, dict):
            raise AdmissionError(
                "invalid_payload",
                f"Line {lineno} must be a JSON object.",
                "Send one A2UI v1.0 envelope per JSONL line.",
            )
        messages.append(item)
    if not messages:
        raise AdmissionError(
            "missing_payload",
            "JSONL contained no envelopes.",
            "Send at least one A2UI v1.0 envelope.",
        )
    return messages


def _message_key(envelope: dict[str, Any]) -> str:
    version = envelope.get("version")
    if version != "1.0":
        raise AdmissionError(
            "invalid_payload",
            "Only A2UI protocol 1.0 is accepted.",
            "Set version to 1.0. v0.8 and v0.9 payloads are not admitted.",
        )
    keys = [k for k in envelope if k != "version"]
    if len(keys) != 1:
        raise AdmissionError(
            "invalid_payload",
            "Each envelope must have version and exactly one message key.",
            "Use createSurface, updateComponents, updateDataModel, or deleteSurface.",
        )
    key = keys[0]
    if key not in ALLOWED_OPS_MESSAGES:
        raise AdmissionError(
            "invalid_payload",
            f"Unsupported message {key}.",
            "Use createSurface, updateComponents, updateDataModel, or deleteSurface.",
        )
    body = envelope[key]
    if not isinstance(body, dict):
        raise AdmissionError(
            "invalid_payload",
            f"{key} must be an object.",
            "Follow the A2UI v1.0 envelope shape.",
        )
    return key


def _walk_for_urls(value: Any, urls: list[str]) -> None:
    if isinstance(value, dict):
        for k, v in value.items():
            if k in _URL_KEYS and isinstance(v, str):
                urls.append(v)
            else:
                _walk_for_urls(v, urls)
    elif isinstance(value, list):
        for item in value:
            _walk_for_urls(item, urls)


def _component_type(comp: dict[str, Any]) -> str:
    typ = comp.get("component")
    if not isinstance(typ, str) or not typ:
        raise AdmissionError(
            "invalid_payload",
            "Each component needs a component type.",
            "Use an official Basic Catalog type such as Text or Card.",
        )
    return typ


def collect_components(messages: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    for envelope in messages:
        key = _message_key(envelope)
        body = envelope[key]
        if key == "createSurface":
            catalog = body.get("catalogId")
            if catalog is not None and catalog != BASIC_CATALOG_ID:
                raise AdmissionError(
                    "unknown_component",
                    "Only the official Basic Catalog v1.0 is admitted.",
                    f"Set catalogId to {BASIC_CATALOG_ID}.",
                )
            comps = body.get("components") or []
        elif key == "updateComponents":
            comps = body.get("components") or []
        else:
            continue
        if not isinstance(comps, list):
            raise AdmissionError(
                "invalid_payload",
                "components must be a list.",
                "Send a flat list of component objects.",
            )
        for comp in comps:
            if not isinstance(comp, dict):
                raise AdmissionError(
                    "invalid_payload",
                    "Each component must be an object.",
                    "Send catalog-valid component objects with an id and type.",
                )
            found.append(comp)
    return found


def admit_jsonl(
    text: str,
    *,
    resolver: Callable[[str], list[str]] | None = None,
    require_root: bool = True,
) -> dict[str, Any]:
    messages = parse_jsonl(text)
    components = collect_components(messages)
    if len(components) > LIMITS["max_components"]:
        raise AdmissionError(
            "oversize",
            f"Surface has {len(components)} components; the cap is {LIMITS['max_components']}.",
            f"Keep the surface to at most {LIMITS['max_components']} components.",
        )
    ids: set[str] = set()
    for comp in components:
        typ = _component_type(comp)
        if typ in DEFERRED_COMPONENTS:
            raise AdmissionError(
                "unknown_component",
                f"Component {typ} is not enabled in this version.",
                "Use Image, Text, layout, and form components from the Basic Catalog. Video and AudioPlayer are deferred.",
            )
        if typ not in MVP_COMPONENTS:
            raise AdmissionError(
                "unknown_component",
                f"Component {typ} is not in the official Basic Catalog allowlist.",
                "Use only official Basic Catalog v1.0 components (except Video and AudioPlayer).",
            )
        cid = comp.get("id")
        if not isinstance(cid, str) or not cid:
            raise AdmissionError(
                "invalid_payload",
                "Each component needs a string id.",
                "Give every component a unique id.",
            )
        if cid in ids:
            raise AdmissionError(
                "invalid_payload",
                f"Duplicate component id {cid}.",
                "Give every component a unique id.",
            )
        ids.add(cid)
        extra_catalog = comp.get("@catalogId")
        if extra_catalog is not None and extra_catalog != BASIC_CATALOG_ID:
            raise AdmissionError(
                "unknown_component",
                "Per-component catalogs other than the official Basic Catalog are rejected.",
                "Omit @catalogId, or set it to the official Basic Catalog id.",
            )

    if require_root and components and "root" not in ids:
        raise AdmissionError(
            "invalid_payload",
            "A present surface must include a component with id root.",
            "Add a root component (for example a Column or Card) and reference children from it.",
        )

    urls: list[str] = []
    for envelope in messages:
        _walk_for_urls(envelope, urls)
    for raw in urls:
        try:
            validate_https_public_url(raw, resolver=resolver)
        except UrlPolicyError as exc:
            raise _as_error(exc) from None

    surface_id = None
    for envelope in messages:
        key = _message_key(envelope)
        sid = envelope[key].get("surfaceId") or envelope[key].get("surface_id")
        if isinstance(sid, str) and sid:
            surface_id = sid
            break
    return {
        "messages": messages,
        "component_count": len(components),
        "component_ids": sorted(ids),
        "surface_id": surface_id,
    }
