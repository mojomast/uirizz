"""Hook registration. Accept **kwargs. Do not register transform_llm_output."""

from __future__ import annotations

from typing import Any


def pre_llm_call(**kwargs: Any):
    """Inject structured user-action context for the current session only."""
    try:
        from uirizz_plugin.actions import pre_llm_call_context

        return pre_llm_call_context(**kwargs)
    except Exception:
        return None


def register_hooks(ctx) -> None:
    if not hasattr(ctx, "register_hook"):
        return
    ctx.register_hook("pre_llm_call", pre_llm_call)
