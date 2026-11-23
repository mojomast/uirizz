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

        message = tool_block_message(
            kwargs.get("session_id"),
            tool,
            kwargs.get("args"),
            kwargs.get("tool_call_id"),
            has_args="args" in kwargs,
        )
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


def post_tool_call(**kwargs: Any):
    """Record the outcome of a declared action's bound call. Observer only."""
    try:
        from uirizz_plugin.gate import record_tool_result

        record_tool_result(
            kwargs.get("session_id"),
            kwargs.get("tool_name"),
            kwargs.get("args"),
            kwargs.get("tool_call_id"),
            kwargs.get("status"),
            kwargs.get("error_type"),
            has_args="args" in kwargs,
        )
    except Exception:  # noqa: BLE001 - an unrecorded result shows as unknown, never as done
        pass
    return None


def register_hooks(ctx) -> None:
    if not hasattr(ctx, "register_hook"):
        return
    ctx.register_hook("pre_llm_call", pre_llm_call)
    ctx.register_hook("pre_tool_call", pre_tool_call)
    ctx.register_hook("post_tool_call", post_tool_call)
