"""present, update, delete, and admission failures for a2ui_render."""

from __future__ import annotations

import json

import pytest

from uirizz_plugin.catalog import BASIC_CATALOG_ID, LIMITS
from uirizz_plugin.store import get_surface, set_store_dir
from uirizz_plugin.tools import handle_a2ui_render
from uirizz_plugin.urls import validate_https_public_url


def _load(result: str) -> dict:
    assert isinstance(result, str)
    body = json.loads(result)
    assert isinstance(body, dict)
    return body


def _surface(text: str = "Hello", *, extra_components=None, image_url=None, catalog=BASIC_CATALOG_ID) -> str:
    components = extra_components or [{"id": "root", "component": "Text", "text": text}]
    if image_url is not None:
        components = [
            {"id": "root", "component": "Column", "children": ["title", "pic"]},
            {"id": "title", "component": "Text", "text": text},
            {"id": "pic", "component": "Image", "url": image_url},
        ]
    envelope = {
        "version": "1.0",
        "createSurface": {
            "surfaceId": "demo",
            "catalogId": catalog,
            "components": components,
        },
    }
    return json.dumps(envelope, separators=(",", ":"))


@pytest.fixture(autouse=True)
def _store(tmp_path):
    set_store_dir(tmp_path)
    yield
    set_store_dir(None)


def test_present_golden_and_update_same_id_does_not_mint_another():
    first = _load(
        handle_a2ui_render(
            {
                "op": "present",
                "surface_id": "demo",
                "fallback_text": "Hello there",
                "jsonl": _surface(),
            }
        )
    )
    assert first["ok"] is True
    assert first["surface_id"] == "demo"
    assert first["revision"] == 1
    assert first["fallback_text"] == "Hello there"
    assert first["media"].startswith("MEDIA: ")
    stored = get_surface("demo")
    assert stored is not None
    assert stored["revision"] == 1

    patch = json.dumps(
        {
            "version": "1.0",
            "updateDataModel": {"surfaceId": "demo", "path": "/", "value": {"n": 2}},
        },
        separators=(",", ":"),
    )
    second = _load(
        handle_a2ui_render(
            {
                "op": "update",
                "surface_id": "demo",
                "jsonl": patch,
            }
        )
    )
    assert second["ok"] is True
    assert second["surface_id"] == "demo"
    assert second["revision"] == 2
    assert get_surface("demo")["revision"] == 2
    assert get_surface("other") is None


def test_second_present_with_new_id_does_not_mutate_first():
    handle_a2ui_render(
        {"op": "present", "surface_id": "a", "fallback_text": "A", "jsonl": _surface("A")}
    )
    handle_a2ui_render(
        {"op": "present", "surface_id": "b", "fallback_text": "B", "jsonl": _surface("B")}
    )
    assert get_surface("a")["fallback_text"] == "A"
    assert get_surface("b")["fallback_text"] == "B"
    deleted = _load(handle_a2ui_render({"op": "delete", "surface_id": "a"}))
    assert deleted["ok"] is True
    assert get_surface("a") is None
    assert get_surface("b") is not None


def test_present_requires_fallback_text():
    body = _load(handle_a2ui_render({"op": "present", "jsonl": _surface()}))
    assert body["ok"] is False
    assert body["code"] == "missing_fallback_text"
    assert "fix" in body


def test_update_and_delete_require_surface_id():
    for op in ("update", "delete"):
        body = _load(handle_a2ui_render({"op": op, "jsonl": _surface()}))
        assert body["ok"] is False
        assert body["code"] == "missing_surface_id"


def test_rejects_unknown_component():
    jsonl = _surface(extra_components=[{"id": "root", "component": "DataTable", "rows": []}])
    body = _load(
        handle_a2ui_render({"op": "present", "fallback_text": "nope", "jsonl": jsonl})
    )
    assert body["ok"] is False
    assert body["code"] == "unknown_component"


def test_rejects_video_and_oversize_payload():
    video = _surface(extra_components=[{"id": "root", "component": "Video", "url": "https://ex/v.mp4"}])
    body = _load(
        handle_a2ui_render({"op": "present", "fallback_text": "nope", "jsonl": video})
    )
    assert body["ok"] is False
    assert body["code"] == "unknown_component"

    huge = "x" * (LIMITS["max_payload_bytes"] + 10)
    body = _load(
        handle_a2ui_render({"op": "present", "fallback_text": "nope", "jsonl": huge})
    )
    assert body["ok"] is False
    assert body["code"] == "oversize"


def test_rejects_http_and_private_image_urls_during_present(monkeypatch):
    # Guard the admission path so it cannot call the real DNS resolver.
    def explode(host: str):
        raise AssertionError(f"must not resolve {host}")

    monkeypatch.setattr(
        "uirizz_plugin.validate.validate_https_public_url",
        lambda url, resolver=None: validate_https_public_url(url, resolver=explode),
    )
    for raw in (
        "http://example.com/a.png",
        "https://127.0.0.1/a.png",
        "https://169.254.169.254/a.png",
        "data:image/svg+xml;utf8,<svg></svg>",
        "/tmp/photo.png",
    ):
        body = _load(
            handle_a2ui_render(
                {
                    "op": "present",
                    "fallback_text": "nope",
                    "jsonl": _surface(image_url=raw),
                }
            )
        )
        assert body["ok"] is False, raw
        assert body["code"] == "invalid_media_url", raw


def test_express_without_sdk_fails_closed():
    body = _load(
        handle_a2ui_render(
            {"op": "present", "fallback_text": "Hi", "express": "root = Text('Hi')"}
        )
    )
    assert body["ok"] is False
    assert body["code"] == "express_unavailable"
