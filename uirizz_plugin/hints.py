"""One-line hint listing the cards already shown in this chat."""

from __future__ import annotations

import json
import re

from uirizz_plugin.store import _surfaces_dir

_CTRL = re.compile(r"[\x00-\x1f\x7f]")
MAX_HINT = 600
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


def active_cards_hint(session_id: str | None, conversation_id: str | None, limit: int = 5) -> str | None:
    conv = conversation_id if isinstance(conversation_id, str) and conversation_id else None
    sess = session_id if isinstance(session_id, str) and session_id else None
    if conv is None and sess is None:
        return None
    key, want = ("conversation_id", conv) if conv else ("session_id", sess)
    try:
        files = sorted(_surfaces_dir().glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    except OSError:
        return None
    items: list[str] = []
    for path in files:
        if len(items) >= limit:
            break
        try:
            rec = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(rec, dict) or rec.get(key) != want:
            continue
        sid = _CTRL.sub("", str(rec.get("surface_id") or path.stem))
        items.append(f'{sid} "{_title(rec.get("fallback_text"))}" rev {rec.get("revision", 1)}')
    if not items:
        return None
    return (PREFIX + "; ".join(items))[:MAX_HINT]
