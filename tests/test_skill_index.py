"""RED for wave A slice T5a: the uirizz SKILL.md stays an index.

The skill is loaded into every card chat. The Express worked example and its
syntax notes duplicate ``op=describe topic=express``; keep a one-line pointer
and the safety rules, and move the example out. The wide-layout section stays
(RESEARCH.md section 10 and tests/test_skill_layout.py pin it).
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "uirizz" / "SKILL.md"
EXPRESS = ROOT / "skills" / "uirizz" / "references" / "express.md"


def _text() -> str:
    return SKILL.read_text(encoding="utf-8")


def test_skill_is_at_most_4000_chars():
    assert len(_text()) <= 4000, f"SKILL.md is {len(_text())} chars"


def test_no_inline_express_example():
    text = _text()
    assert "```express" not in text
    assert "## Express essentials" not in text


def test_express_is_one_pointer_to_the_topic():
    text = _text()
    pointers = [line for line in text.splitlines() if "topic=express" in line]
    assert pointers, "SKILL.md must point at op=describe topic=express"


def test_the_express_reference_keeps_the_moved_notes():
    ref = EXPRESS.read_text(encoding="utf-8").lower()
    for phrase in ("card", "weight", "updatedatamodel", "camelcase", "?required"):
        assert phrase in ref, phrase


def test_safety_rules_stay_in_the_skill():
    lower = _text().lower()
    assert "click is not approval" in lower
    assert "fallback_text" in lower and "required" in lower
    assert "side_effect" in lower and "read_only" in lower
    assert re.search(r"yes <code>", _text())
