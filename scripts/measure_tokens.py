#!/usr/bin/env python3
"""Print o200k and cl100k token counts for the skill and tool schema."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "uirizz" / "SKILL.md"


def main() -> int:
    try:
        import tiktoken
    except ImportError:
        print("pip install tiktoken  (included in uirizz[dev])", file=sys.stderr)
        return 1

    sys.path.insert(0, str(ROOT))
    from uirizz_plugin.tools import A2UI_RENDER_SCHEMA

    skill = SKILL.read_text(encoding="utf-8")
    schema = json.dumps(A2UI_RENDER_SCHEMA, separators=(",", ":"), ensure_ascii=False)
    for label, text in (("skill", skill), ("schema", schema)):
        print(f"{label}:")
        for name in ("o200k_base", "cl100k_base"):
            n = len(tiktoken.get_encoding(name).encode(text))
            print(f"  {name}: {n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
