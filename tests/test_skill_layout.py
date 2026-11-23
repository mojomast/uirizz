"""Skill and describe/schema must teach wide A2UI layouts (RESEARCH.md §10)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "uirizz" / "SKILL.md"

# Baseline measured 2026-11-22 on feat/mvp (SKILL.md before this change): 676.
# Keep growth compact; the existing hard cap in test_tokens.py is 2000.
SKILL_BASELINE_O200K = 676
SKILL_LAYOUT_CAP_O200K = 1400
SCHEMA_O200K_BUDGET = 500


def _count(text: str) -> int:
    tiktoken = pytest.importorskip(
        "tiktoken",
        reason="pip install tiktoken  (included in uirizz[dev])",
    )
    return len(tiktoken.get_encoding("o200k_base").encode(text))


def test_skill_teaches_wide_layout_practice():
    text = SKILL.read_text(encoding="utf-8")
    lower = text.lower()
    # Weighted Row/Column composition (no grid in the Basic Catalog).
    assert "weight" in lower
    # KPI row recipe.
    assert "kpi" in lower
    # Master/detail split.
    assert "master" in lower and "detail" in lower
    assert "2:3" in text or "2 : 3" in text or "weight=2" in lower
    # Tabs / Modal / List guidance.
    assert "tabs" in lower and "modal" in lower and "list" in lower
    # Live updates via the data model.
    assert "updatedatamodel" in lower or "update data model" in lower or "update_data_model" in lower
    # Icon names work; glyph text is a fallback, not the default advice after the font fix.
    assert "icon" in lower
    # Slider steps are divisions, not a unit increment.
    assert "steps" in lower
    # Catalog gaps.
    for missing in ("chart", "table", "badge", "map"):
        assert missing in lower, f"skill should say the catalog lacks {missing}"


def test_skill_layout_token_growth_is_reasonable():
    text = SKILL.read_text(encoding="utf-8")
    n = _count(text)
    assert n < SKILL_LAYOUT_CAP_O200K, (
        f"skill is {n} o200k tokens; layout-guidance cap is {SKILL_LAYOUT_CAP_O200K} "
        f"(baseline was {SKILL_BASELINE_O200K})"
    )
    # Bound growth so the section stays compact, but allow a short addition.
    assert n > SKILL_BASELINE_O200K, "skill should gain the layout section (token count did not grow)"


def test_tool_schema_mentions_weighted_layout():
    from uirizz_plugin.tools import A2UI_RENDER_SCHEMA

    blob = json.dumps(A2UI_RENDER_SCHEMA, ensure_ascii=False)
    lower = blob.lower()
    assert "weight" in lower or "weighted" in lower
    n = _count(json.dumps(A2UI_RENDER_SCHEMA, separators=(",", ":"), ensure_ascii=False))
    assert n < SCHEMA_O200K_BUDGET, f"schema is {n} o200k tokens; budget is {SCHEMA_O200K_BUDGET}"


def test_describe_includes_layout_guidance():
    from uirizz_plugin.tools import describe_payload

    payload = describe_payload()
    assert "layout" in payload
    blob = json.dumps(payload).lower()
    assert "weight" in blob
    assert "updatedatamodel" in blob or "data model" in blob or "update_data_model" in blob
