"""Hook registration. Accept **kwargs. Do not register transform_llm_output."""

from __future__ import annotations

from typing import Any


def pre_llm_call(**kwargs: Any) -> None:
    """Inject structured user-action context once the action log lands.

    Scaffold: no-op. Must never raise on unknown kwargs, and must not inspect
    or block tools from other plugins or sessions.
    """
    return None


def register_hooks(ctx) -> None:
    if not hasattr(ctx, "register_hook"):
        return
    ctx.register_hook("pre_llm_call", pre_llm_call)
