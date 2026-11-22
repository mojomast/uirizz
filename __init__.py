"""Hermes plugin entrypoint for uirizz. Registers the bundled skill, hook, and tool."""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def register(ctx) -> None:
    """Called by Hermes PluginManager. Keep this fast; lazy-import heavy deps in handlers."""
    skills_dir = Path(__file__).resolve().parent / "skills"
    if skills_dir.is_dir() and hasattr(ctx, "register_skill"):
        for child in sorted(p for p in skills_dir.iterdir() if p.is_dir()):
            skill_md = child / "SKILL.md"
            if skill_md.is_file():
                ctx.register_skill(child.name, skill_md)

    from uirizz_plugin.hooks import register_hooks
    from uirizz_plugin.tools import register_tools

    register_hooks(ctx)
    register_tools(ctx)
