"""Skill and tool schema must stay within the researched token budgets."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "uirizz" / "SKILL.md"

# Well under the 2k skill target. hermes-a2ui's skill was ~7,689 o200k.
SKILL_O200K_BUDGET = 2000
# Lean composable schema; plan draft was 313 o200k. Leave a little headroom.
SCHEMA_O200K_BUDGET = 500


def _encoding(name: str):
    tiktoken = pytest.importorskip(
        "tiktoken",
        reason="pip install tiktoken  (included in uirizz[dev])",
    )
    return tiktoken.get_encoding(name)


def _count(text: str, encoding_name: str = "o200k_base") -> int:
    return len(_encoding(encoding_name).encode(text))


def test_skill_under_token_budget():
    text = SKILL.read_text(encoding="utf-8")
    n = _count(text)
    assert n < SKILL_O200K_BUDGET, f"skill is {n} o200k tokens; budget is {SKILL_O200K_BUDGET}"
    # Also keep a record for cl100k_base without enforcing a second cap.
    _ = _count(text, "cl100k_base")


def test_tool_schema_under_token_budget():
    from uirizz_plugin.tools import A2UI_RENDER_SCHEMA

    text = json.dumps(A2UI_RENDER_SCHEMA, separators=(",", ":"), ensure_ascii=False)
    n = _count(text)
    assert n < SCHEMA_O200K_BUDGET, f"schema is {n} o200k tokens; budget is {SCHEMA_O200K_BUDGET}"
