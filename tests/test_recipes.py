"""Every Express block the skill teaches must compile, admit, and gate correctly.

The skill is only as good as its examples: a recipe that stopped compiling
would teach the model a broken pattern. This keeps references/ honest in CI.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from uirizz_plugin import store
from uirizz_plugin.tools import handle_a2ui_render, parse_tool_result

pytest.importorskip("a2ui", reason="a2ui-agent-sdk is required for Express")

ROOT = Path(__file__).resolve().parents[1]
SKILL_DIR = ROOT / "skills" / "uirizz"
FILES = [SKILL_DIR / "SKILL.md", *sorted((SKILL_DIR / "references").glob("*.md"))]
BLOCK = re.compile(r"```express\n(.*?)```", re.DOTALL)
UPDATE_BLOCK = re.compile(r"```express-update\n(.*?)```", re.DOTALL)


def _blocks(pattern):
    found = []
    for path in FILES:
        for i, src in enumerate(pattern.findall(path.read_text(encoding="utf-8")), 1):
            found.append(pytest.param(src, id=f"{path.name}#{i}"))
    return found


@pytest.fixture(autouse=True)
def _store(tmp_path):
    store.set_store_dir(tmp_path / "surfaces")
    yield
    store.set_store_dir(None)


@pytest.mark.parametrize("source", _blocks(BLOCK))
def test_recipe_presents(source):
    out = parse_tool_result(
        handle_a2ui_render({"op": "present", "express": source, "fallback_text": "x"})
    )
    assert out["ok"] is True, out
    assert out["component_count"] <= 100


def test_there_are_enough_recipes():
    assert len(_blocks(BLOCK)) >= 8


def _update_pairs():
    """Each express-update block, paired with the nearest express block before it."""
    pairs = []
    fence = re.compile(r"```(express|express-update)\n(.*?)```", re.DOTALL)
    for path in FILES:
        base = None
        for i, m in enumerate(fence.finditer(path.read_text(encoding="utf-8")), 1):
            if m.group(1) == "express":
                base = m.group(2)
            elif base is not None:
                pairs.append(pytest.param(base, m.group(2), id=f"{path.name}#{i}"))
    return pairs


@pytest.mark.parametrize("base, update", _update_pairs())
def test_update_snippets_apply_to_their_recipe(base, update):
    p = parse_tool_result(
        handle_a2ui_render({"op": "present", "express": base, "fallback_text": "x"})
    )
    u = parse_tool_result(
        handle_a2ui_render({"op": "update", "surface_id": p["surface_id"], "express": update})
    )
    assert u["ok"] is True, u


def test_every_update_snippet_has_a_base():
    assert len(_update_pairs()) == len(_blocks(UPDATE_BLOCK)) >= 2


def test_recipe_buttons_are_marked():
    """Every Event in a recipe says read_only or side_effect, as the skill teaches."""
    for path in FILES:
        for src in BLOCK.findall(path.read_text(encoding="utf-8")):
            for ctx in re.findall(r"Event\(\"[a-z_]+\"(?:, (\{.*?\}))?\)", src):
                assert "read_only: true" in ctx or "side_effect: true" in ctx, (path.name, ctx)
