"""Skill and schema must teach when-to-use, hard rules, and recovery."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "uirizz" / "SKILL.md"
LAYOUT = ROOT / "skills" / "uirizz" / "references" / "layout.md"


def _lower(path: Path) -> str:
    return path.read_text(encoding="utf-8").lower()


def test_skill_when_to_use_and_when_not():
    text = _lower(SKILL)
    assert "when to use" in text
    assert "when not to use" in text
    assert "ordinary" in text or "q&a" in text or "prose" in text
    for tool in ("shell", "gh", "git"):
        assert tool in text, f"skill should forbid rendering via {tool}"


def test_skill_hard_rules():
    text = _lower(SKILL)
    assert "fallback_text" in text
    assert "required" in text
    assert "media:" in text
    assert "click is not approval" in text
    assert "op=update" in text or "op = update" in text
    assert "surface_id" in text


def test_skill_error_recovery():
    text = _lower(SKILL)
    assert "code" in text and "fix" in text
    assert "retry" in text
    assert "missing_fallback_text" in text or "fallback_text" in text


def test_layout_reference_has_worked_example():
    assert LAYOUT.is_file(), "progressive-disclosure layout reference is missing"
    text = LAYOUT.read_text(encoding="utf-8")
    lower = text.lower()
    assert "column(" in lower or "column(" in text.lower()
    assert "weight" in lower
    assert "updatedatamodel" in lower
    assert "fallback_text" in lower
    assert "side_effect" in lower


def test_schema_repeats_hard_rules():
    from uirizz_plugin.tools import A2UI_RENDER_SCHEMA

    blob = json.dumps(A2UI_RENDER_SCHEMA, ensure_ascii=False).lower()
    assert "shell" in blob
    assert "click is not approval" in blob
    assert "fallback_text" in blob
    assert "retry" in blob or "fix" in blob
    assert "updatedatamodel" in blob or "update_data_model" in blob
