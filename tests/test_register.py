"""Fake-ctx registration: tools, hooks, skills, and JSON-string handlers."""

from __future__ import annotations

import inspect
import json
from pathlib import Path

from tests.fake_ctx import FakeCtx

ROOT = Path(__file__).resolve().parents[1]


def _load_manifest() -> dict:
    from ruamel.yaml import YAML

    yaml = YAML(typ="safe")
    yaml.allow_duplicate_keys = False
    data = yaml.load((ROOT / "plugin.yaml").read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


def test_register_matches_manifest_and_skips_transform_hook():
    import importlib.util

    spec = importlib.util.spec_from_file_location("uirizz_plugin_root", ROOT / "__init__.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    ctx = FakeCtx()
    module.register(ctx)

    manifest = _load_manifest()
    assert list(ctx.tools) == list(manifest["provides_tools"])
    assert list(ctx.hooks) == list(manifest["provides_hooks"])
    assert "transform_llm_output" not in ctx.hooks
    assert "uirizz" in ctx.skills
    assert ctx.skills["uirizz"].name == "SKILL.md"
    assert ctx.skills["uirizz"].is_file()


def test_pre_llm_call_accepts_kwargs():
    from uirizz_plugin.hooks import pre_llm_call

    params = inspect.signature(pre_llm_call).parameters
    assert any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values())
    assert pre_llm_call(session_id="s", messages=[], unexpected="x") is None


def test_every_op_returns_json_string():
    from uirizz_plugin.tools import handle_a2ui_render

    cases = [
        {"op": "describe"},
        {"op": "present", "fallback_text": "Hello", "jsonl": "{}"},
        {"op": "update", "surface_id": "s1", "jsonl": "{}"},
        {"op": "delete", "surface_id": "s1"},
        {"op": "nope"},
        {},
        None,
    ]
    for args in cases:
        result = handle_a2ui_render(args)  # type: ignore[arg-type]
        assert isinstance(result, str), args
        body = json.loads(result)
        assert isinstance(body, dict)
        assert "ok" in body
        if args == {"op": "describe"}:
            assert body["ok"] is True
            assert body["catalog_id"].endswith("basic/catalog.json")
            assert body["hooks"]["transform_llm_output"] is False
            assert "Text" in body["components"]
            assert "Video" not in body["components"]
        elif not args or (isinstance(args, dict) and args.get("op") == "nope"):
            assert body["ok"] is False
            assert body["code"] == "invalid_op"
            assert "fix" in body
        else:
            assert body["ok"] is False
            assert body["code"] == "not_implemented"
            assert "fix" in body
