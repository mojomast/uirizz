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


def pre_tool_call(**kwargs: Any):
    """Veto tools while a card action waits for the user's explicit yes.

    Fail-closed: if the gate cannot be checked, only the render tool and a few
    read-only helpers are allowed through.
    """
    tool = kwargs.get("tool_name")
    try:
        from uirizz_plugin.gate import tool_block_message

        message = tool_block_message(kwargs.get("session_id"), tool)
    except Exception:
        from uirizz_plugin.gate import SAFE_TOOLS_WHILE_PENDING

        if tool in SAFE_TOOLS_WHILE_PENDING:
            return None
        message = (
            "BLOCKED by the uirizz approval gate: the pending-action state could not be "
            "checked, so this tool is held. Use a2ui_render, or ask the user to retry."
        )
    if message:
        return {"action": "block", "message": message}
    return None


def register_hooks(ctx) -> None:
    if not hasattr(ctx, "register_hook"):
        return
    ctx.register_hook("pre_llm_call", pre_llm_call)
    ctx.register_hook("pre_tool_call", pre_tool_call)
