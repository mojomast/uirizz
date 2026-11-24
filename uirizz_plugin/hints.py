"""One-line hint listing the cards already shown in this chat."""

from __future__ import annotations

import json
import re
import threading

from uirizz_plugin.store import _surfaces_dir

_CTRL = re.compile(r"[\x00-\x1f\x7f]")
MAX_HINT = 600
_hint_lock = threading.Lock()
_last_hints = {}
PREFIX = (
    "uirizz cards already in this chat (to change one, call a2ui_render op=update "
    "with its surface_id instead of presenting again): "
)


def _title(text: object) -> str:
    for line in str(text or "").splitlines():
        clean = _CTRL.sub("", line).strip()
        if clean:
            return clean[:50]
    return ""


def _scope(session_id: object, conversation_id: object) -> tuple[str, str] | None:
    """(record key, wanted value): the conversation if known, else the session."""
    if isinstance(conversation_id, str) and conversation_id:
        return "conversation_id", conversation_id
    if isinstance(session_id, str) and session_id:
        return "session_id", session_id
    return None


def _read(path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None  # a card mid-write or corrupt is simply not listed


def _items(files, key: str, want: str, limit: int) -> list[str]:
    items: list[str] = []
    for path in files:
        if len(items) >= limit:
            break
        rec = _read(path)
        if isinstance(rec, dict) and rec.get(key) == want:
            sid = _CTRL.sub("", str(rec.get("surface_id") or path.stem))
            items.append(f'{sid} "{_title(rec.get("fallback_text"))}" rev {rec.get("revision", 1)}')
    return items


def active_cards_hint(session_id: str | None, conversation_id: str | None, limit: int = 5) -> str | None:
    scope = _scope(session_id, conversation_id)
    if scope is None:
        return None
    try:
        root = _surfaces_dir()
        files = sorted(root.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    except OSError:
        return None
    items = _items(files, scope[0], scope[1], limit)
    fingerprint = tuple(sorted(items))
    cache_key = (root, scope)
    with _hint_lock:
        if _last_hints.get(cache_key) == fingerprint:
            return None
        _last_hints[cache_key] = fingerprint
    if not items:
        return None
    return (PREFIX + "; ".join(items))[:MAX_HINT]
