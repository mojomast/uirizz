"""Approval gate and audit log for A2UI actions.

A card click is a request, never permission. This module records every click
in an append-only, hash-chained log, decides (fail-closed) whether the click
asks for a side effect, and only lets a side effect proceed after the user's
own typed chat reply says yes. Nothing a card, a model, or a tool result says
can approve an action.

States of a gated action (``status``):

* ``pending_confirmation``: clicked, waiting for the user's typed yes or no.
* ``approved``: the user typed an explicit yes after the pending notice was shown.
* ``denied``: the user typed an explicit no.
* ``expired``: no decision (or an unused approval) inside ``APPROVAL_TTL_S``.
* ``superseded``: a newer click on the same control replaced it.
* ``completed`` / ``failed`` / ``cancelled``: the outcome recorded via the tool.
* ``recorded``: a click that was explicitly read-only; it never gates anything.
"""

from __future__ import annotations

import hashlib
import json
import re
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from uirizz_plugin.store import _plugin_data_dir

try:  # POSIX cross-process append lock; fall back to the thread lock elsewhere.
    import fcntl  # type: ignore
except ImportError:  # pragma: no cover
    fcntl = None  # type: ignore[assignment]

APPROVAL_TTL_S = 600
MAX_LOG_BYTES = 5 * 1024 * 1024
MAX_CONTEXT_BYTES = 2048
MAX_STR = 200
AUDIT_DEFAULT_LIMIT = 50
AUDIT_MAX_LIMIT = 200

# Tools that stay available while an action is waiting for the user's yes.
# Everything else (shell, files, network, messaging, code execution) is vetoed.
SAFE_TOOLS_WHILE_PENDING = frozenset(
    {"a2ui_render", "skill_view", "skills_list", "tool_search", "clarify"}
)

OUTCOMES = ("done", "failed", "cancelled")

_MARKER_KEYS = ("side_effect", "sideEffect", "requires_confirmation", "requiresConfirmation")
_READ_ONLY_KEYS = ("read_only", "readOnly")
_TRUE = {"true", "1", "yes"}
_FALSE = {"false", "0", "no"}

# Verbs that always gate, whatever the card claims about itself.
_DANGEROUS = frozenset(
    """deploy release promote rollback merge approve publish push send submit delete
    remove destroy drop pay purchase buy order transfer charge refund cancel revoke
    grant install exec execute run restart shutdown kill post email sms invite share
    unsubscribe wire commit write save apply confirm abort ship launch trigger nudge
    notify comment close assign sign reset wipe erase upload download""".split()
)

_CTRL = re.compile(r"[\x00-\x1f\x7f]")
_SECRET_KEY = re.compile(
    r"(pass|secret|token|key|pin|ssn|card|cvv|auth|cookie|session|bearer|credential)", re.I
)
_TOKEN_SPLIT = re.compile(r"[^A-Za-z0-9]+")
_CAMEL = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")

_YES = re.compile(
    r"^(?:yes|y|yep|yeah|confirm|confirmed|approve|approved|proceed|do it|go ahead)"
    r"(?: (?:yes|please|confirm|confirmed|approve|go ahead|do it|proceed))*"
    r"(?: ([a-f0-9]{6,12}))?$"
)
_NO = re.compile(
    r"^(?:no|n|nope|cancel|deny|denied|decline|stop|abort|don't|dont|do not|never mind|nevermind)"
    r"(?: (?:no|please|cancel|stop|abort|thanks|thank you))*"
    r"(?: ([a-f0-9]{6,12}))?$"
)

_lock = threading.RLock()


class GateError(ValueError):
    def __init__(self, code: str, error: str, fix: str) -> None:
        super().__init__(error)
        self.code = code
        self.error = error
        self.fix = fix


# ---------------------------------------------------------------- sanitizing


def _clean(value: Any) -> str:
    return _CTRL.sub("", str(value) if value is not None else "")


def sanitize_context(value: Any, *, key: str = "") -> Any:
    """Strip control characters, redact secret-looking keys, cap sizes."""
    if key and _SECRET_KEY.search(key):
        return "[redacted]"
    if isinstance(value, dict):
        return {_clean(k)[:80]: sanitize_context(v, key=str(k)) for k, v in list(value.items())[:40]}
    if isinstance(value, list):
        return [sanitize_context(v) for v in value[:40]]
    if isinstance(value, str):
        text = _clean(value)
        return text if len(text) <= MAX_STR else text[:MAX_STR] + "…"
    if isinstance(value, (bool, int, float)) or value is None:
        return value
    return _clean(value)[:MAX_STR]


def _bounded_context(context: Any) -> Any:
    safe = sanitize_context(context if context is not None else {})
    raw = json.dumps(safe, ensure_ascii=False, separators=(",", ":"))
    if len(raw.encode("utf-8")) <= MAX_CONTEXT_BYTES:
        return safe
    keys = sorted(safe) if isinstance(safe, dict) else []
    return {"_truncated": True, "keys": keys[:40]}


# ------------------------------------------------------------ classification


def _tri(value: Any) -> bool | None:
    """True / False for an unambiguous boolean, None when it cannot be trusted."""
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        low = value.strip().lower()
        if low in _TRUE:
            return True
        if low in _FALSE:
            return False
    return None


def _unwrap_literal(value: Any) -> Any:
    if isinstance(value, dict) and len(value) == 1:
        (only_key, only_val), = value.items()
        if isinstance(only_key, str) and only_key.startswith("literal"):
            return only_val
    return value


def _marks(context: Any) -> tuple[list[bool | None], list[bool | None]]:
    """Return (side-effect markers, read-only markers) found in an action context."""
    side: list[bool | None] = []
    read: list[bool | None] = []
    if isinstance(context, dict):
        for key, raw in context.items():
            value = _unwrap_literal(raw)
            if key in _MARKER_KEYS:
                side.append(_tri(value))
            elif key in _READ_ONLY_KEYS:
                read.append(_tri(value))
    return side, read


def _tokens(*parts: Any) -> set[str]:
    out: set[str] = set()
    for part in parts:
        text = _clean(part)
        for chunk in _TOKEN_SPLIT.split(_CAMEL.sub(" ", text)):
            low = chunk.lower()
            if not low:
                continue
            out.add(low)
            if low.endswith("s") and len(low) > 3:
                out.add(low[:-1])
            if low.endswith("ing") and len(low) > 5:
                out.add(low[:-3])
            if low.endswith("ed") and len(low) > 4:
                out.add(low[:-2])
    return out


def _walk_definition_contexts(node: Any, event: str, found: list[Any]) -> None:
    if isinstance(node, dict):
        ev = node.get("event")
        if isinstance(ev, dict) and ev.get("name") == event:
            found.append(ev.get("context"))
        for child in node.values():
            _walk_definition_contexts(child, event, found)
    elif isinstance(node, list):
        for child in node:
            _walk_definition_contexts(child, event, found)


def definition_contexts(surface: dict[str, Any] | None, event: str) -> list[Any]:
    """Contexts the stored surface itself declares for this event name."""
    found: list[Any] = []
    if isinstance(surface, dict):
        _walk_definition_contexts(surface.get("messages") or [], event, found)
    return found


def classify(
    event: Any, context: Any, definitions: Iterable[Any] = ()
) -> tuple[bool, str]:
    """Return (requires_confirmation, reason). Fail-closed.

    Gated unless the click is explicitly read-only AND neither the event name,
    the context, nor the stored surface definition points at a side effect.
    """
    contexts = [context, *definitions]
    sides: list[bool | None] = []
    reads: list[bool | None] = []
    for ctx in contexts:
        s, r = _marks(ctx)
        sides += s
        reads += r
    if any(v is True for v in sides):
        return True, "marked side_effect"
    if any(v is None for v in sides + reads):
        return True, "marker not a clear boolean"
    values: list[Any] = []
    for ctx in contexts:
        if isinstance(ctx, dict):
            values += [k for k in ctx] + [_unwrap_literal(v) for v in ctx.values() if isinstance(_unwrap_literal(v), str)]
    hit = _tokens(event, *values) & _DANGEROUS
    if hit:
        return True, "side-effect verb: " + ",".join(sorted(hit)[:3])
    read_only = any(v is True for v in reads) or any(v is False for v in sides)
    if read_only and not any(v is False for v in reads):
        return False, "explicit read_only"
    return True, "unmarked, fail-closed"


# ------------------------------------------------------------------ the log


def _audit_dir() -> Path:
    path = _plugin_data_dir() / "audit"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _log_path(*, create: bool = True) -> Path:
    if create:
        return _audit_dir() / "actions.jsonl"
    return _plugin_data_dir() / "audit" / "actions.jsonl"


def _now() -> float:
    return time.time()


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _digest(prev: str, body: dict[str, Any]) -> str:
    blob = prev + json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _read_lines(path: Path) -> list[str]:
    if not path.is_file():
        return []
    return [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]


def _append(entry: dict[str, Any]) -> dict[str, Any]:
    """Append one chained entry. Cross-process safe on POSIX."""
    path = _log_path()
    with _lock:
        with open(path, "a+", encoding="utf-8") as fh:
            if fcntl is not None:
                fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
            try:
                fh.seek(0)
                lines = [ln for ln in fh.read().splitlines() if ln.strip()]
                prev = "0" * 64
                seq = 0
                if lines:
                    last = json.loads(lines[-1])
                    prev = str(last.get("hash", prev))
                    seq = int(last.get("seq", 0))
                body = dict(entry)
                body["seq"] = seq + 1
                body["ts"] = _iso(_now())
                body["_t"] = _now()
                body["prev"] = prev
                body["hash"] = _digest(prev, {k: v for k, v in body.items() if k != "hash"})
                fh.seek(0, 2)
                fh.write(json.dumps(body, ensure_ascii=False, separators=(",", ":")) + "\n")
                fh.flush()
                size = fh.tell()
            finally:
                if fcntl is not None:
                    fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        if size > MAX_LOG_BYTES:
            # Keep one backup; the new file starts a fresh chain.
            path.replace(path.with_suffix(".jsonl.1"))
    return body


def read_entries() -> list[dict[str, Any]]:
    """All parseable entries, oldest first. Raises GateError if the log is unreadable."""
    path = _log_path(create=False)
    try:
        lines = _read_lines(path)
    except OSError as exc:
        raise GateError("audit_unreadable", "The audit log could not be read.", "Check the plugin data directory.") from exc
    out: list[dict[str, Any]] = []
    for line in lines:
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            out.append(item)
    return out


def verify_chain() -> dict[str, Any]:
    """Check the hash chain of the current log file."""
    entries = read_entries()
    prev: str | None = None
    for index, entry in enumerate(entries):
        body = {k: v for k, v in entry.items() if k != "hash"}
        if prev is not None and entry.get("prev") != prev:
            return {"ok": False, "entries": len(entries), "broken_at": index}
        if _digest(str(entry.get("prev", "")), body) != entry.get("hash"):
            return {"ok": False, "entries": len(entries), "broken_at": index}
        prev = str(entry.get("hash"))
    return {"ok": True, "entries": len(entries)}


# ----------------------------------------------------------------- folding


def _fold(entries: list[dict[str, Any]], now: float | None = None) -> dict[str, dict[str, Any]]:
    now = _now() if now is None else now
    actions: dict[str, dict[str, Any]] = {}
    for e in entries:
        kind = e.get("type")
        aid = e.get("action_id")
        if kind == "action" and isinstance(aid, str):
            actions[aid] = {
                **{k: e.get(k) for k in (
                    "action_id", "session_id", "surface_id", "event", "context",
                    "source_component_id", "client_timestamp", "requires_confirmation",
                    "reason", "ts", "_t")},
                "status": "pending_confirmation" if e.get("requires_confirmation") else "recorded",
                "announced": False,
                "decided_t": None,
                "decision_by": None,
                "outcome": None,
            }
        elif isinstance(aid, str) and aid in actions:
            act = actions[aid]
            if kind == "announced":
                act["announced"] = True
            elif kind == "decision":
                act["status"] = e.get("decision")
                act["decided_t"] = e.get("_t")
                act["decision_by"] = e.get("source")
            elif kind == "outcome":
                act["outcome"] = e.get("outcome")
                act["status"] = {"done": "completed", "failed": "failed", "cancelled": "cancelled"}.get(
                    str(e.get("outcome")), act["status"])
    for act in actions.values():
        if act["status"] == "pending_confirmation" and now - float(act["_t"] or 0) > APPROVAL_TTL_S:
            act["status"] = "expired"
        elif act["status"] == "approved" and now - float(act["decided_t"] or 0) > APPROVAL_TTL_S:
            act["status"] = "expired"
    return actions


def session_actions(session_id: str | None, now: float | None = None) -> list[dict[str, Any]]:
    folded = _fold(read_entries(), now)
    items = [a for a in folded.values() if not session_id or a["session_id"] == session_id]
    return sorted(items, key=lambda a: a["_t"] or 0)


def _short(action_id: str) -> str:
    return action_id.replace("act-", "")[:6]


# ------------------------------------------------------------------ writers


def log_action(
    *,
    surface_id: str,
    session_id: str,
    event: str,
    context: Any,
    surface: dict[str, Any] | None,
    source_component_id: Any = None,
    client_timestamp: Any = None,
) -> dict[str, Any]:
    """Record a click. Never authorizes anything. Returns the audit entry."""
    gated, reason = classify(event, context, definition_contexts(surface, str(event)))
    entry = _append(
        {
            "type": "action",
            "action_id": "act-" + uuid.uuid4().hex[:12],
            "session_id": _clean(session_id),
            "surface_id": _clean(surface_id),
            "event": _clean(event)[:120],
            "context": _bounded_context(context),
            "source_component_id": _clean(source_component_id)[:120] if source_component_id else None,
            "client_timestamp": _clean(client_timestamp)[:64] if client_timestamp else None,
            "requires_confirmation": gated,
            "reason": reason,
        }
    )
    if gated:
        # A newer click on the same control replaces any older unresolved one.
        for old in session_actions(session_id):
            if (
                old["action_id"] != entry["action_id"]
                and old["status"] == "pending_confirmation"
                and old["surface_id"] == entry["surface_id"]
                and old["event"] == entry["event"]
            ):
                _append({"type": "decision", "action_id": old["action_id"],
                         "decision": "superseded", "source": "newer_click"})
    return entry


def mark_announced(action_id: str) -> None:
    _append({"type": "announced", "action_id": action_id})


def _parse_reply(text: Any) -> tuple[str, str | None] | None:
    """Return ('yes'|'no', optional code) for an explicit reply, else None."""
    if not isinstance(text, str) or len(text) > 120:
        return None
    norm = re.sub(r"[,\s]+", " ", text.strip().lower()).strip(" .!")
    m = _YES.match(norm)
    if m:
        return "yes", m.group(1)
    m = _NO.match(norm)
    if m:
        return "no", m.group(1)
    return None


def observe_user_message(session_id: str | None, text: Any) -> list[dict[str, Any]]:
    """Resolve pending actions from the user's typed chat reply. Returns decisions made.

    Fail-closed: only a short explicit yes/no counts, only after the pending
    notice was shown in an earlier turn, only for this session, and a bare yes
    with more than one candidate decides nothing.
    """
    if not isinstance(session_id, str) or not session_id:
        return []
    reply = _parse_reply(text)
    if reply is None:
        return []
    verdict, code = reply
    pending = [
        a for a in session_actions(session_id)
        if a["status"] == "pending_confirmation" and a["announced"]
    ]
    if not pending:
        return []
    if code:
        pending = [a for a in pending if _short(a["action_id"]).startswith(code[:6])]
        if not pending:
            return []
    elif verdict == "yes" and len(pending) > 1:
        return []
    decided = []
    excerpt = _clean(text).strip()[:80]
    for act in pending:
        decision = "approved" if verdict == "yes" else "denied"
        _append({"type": "decision", "action_id": act["action_id"], "decision": decision,
                 "source": "user_message", "evidence": excerpt})
        decided.append({"action_id": act["action_id"], "decision": decision})
    return decided


def complete_action(action_id: Any, outcome: Any) -> dict[str, Any]:
    """Record the outcome of an action. 'done' needs a live user approval."""
    if not isinstance(action_id, str) or not action_id:
        raise GateError("invalid_payload", "action_id is required with action_outcome.",
                        "Pass the action_id from the action notice.")
    if outcome not in OUTCOMES:
        raise GateError("invalid_payload", "action_outcome must be done, failed, or cancelled.",
                        "Set action_outcome to one of done, failed, cancelled.")
    folded = _fold(read_entries())
    act = folded.get(action_id)
    if act is None:
        raise GateError("unknown_action", "No such action_id in the audit log.",
                        "Use the action_id quoted in the action notice.")
    status = act["status"]
    if status in ("completed", "failed", "cancelled"):
        raise GateError("already_resolved", f"Action {action_id} is already {status}.",
                        "Each approval is single-use.")
    if outcome in ("done", "failed") and act["requires_confirmation"] and status != "approved":
        raise GateError(
            "not_approved",
            f"Action {action_id} is {status}, not approved. A card click is not approval.",
            "Show a confirm step and wait for the user to type yes in chat. Do not mark it done.",
        )
    _append({"type": "outcome", "action_id": action_id, "outcome": outcome})
    return {"action_id": action_id, "outcome": outcome}


# ------------------------------------------------------------ model-facing


def public_view(act: dict[str, Any]) -> dict[str, Any]:
    return {
        "action_id": act["action_id"],
        "code": _short(act["action_id"]),
        "ts": act["ts"],
        "session_id": act["session_id"],
        "surface_id": act["surface_id"],
        "event": act["event"],
        "context": act["context"],
        "source_component_id": act["source_component_id"],
        "requires_confirmation": bool(act["requires_confirmation"]),
        "reason": act["reason"],
        "status": act["status"],
        "decision_by": act["decision_by"],
        "outcome": act["outcome"],
    }


def audit_view(
    *, session_id: str | None = None, surface_id: str | None = None, limit: Any = None
) -> dict[str, Any]:
    try:
        n = int(limit) if limit is not None else AUDIT_DEFAULT_LIMIT
    except (TypeError, ValueError):
        n = AUDIT_DEFAULT_LIMIT
    n = max(1, min(n, AUDIT_MAX_LIMIT))
    acts = session_actions(session_id)
    if surface_id:
        acts = [a for a in acts if a["surface_id"] == surface_id]
    chain = verify_chain()
    return {
        "ok": True,
        "chain_ok": chain["ok"],
        "total": len(acts),
        "actions": [public_view(a) for a in acts[-n:]],
    }


def gate_notice(session_id: str | None) -> str | None:
    """Text for the model about actions that need, or just got, a decision."""
    if not isinstance(session_id, str) or not session_id:
        return None
    parts: list[str] = []
    for act in session_actions(session_id):
        status = act["status"]
        aid = act["action_id"]
        head = (
            f"Approval gate: action_id={aid} code={_short(aid)} surface_id={_clean(act['surface_id'])} "
            f"event={_clean(act['event'])}"
        )
        if status == "pending_confirmation":
            if not act["announced"]:
                mark_announced(aid)
            parts.append(
                f"{head} status=pending_confirmation. The user's card click is a request, not "
                "approval. Do NOT perform the side effect and do not call tools other than "
                f"a2ui_render. Update the same surface to show a confirm step naming exactly what "
                f"will happen, and ask the user to reply yes (or 'yes {_short(aid)}') or no in chat. "
                "Only the user's typed chat reply counts."
            )
        elif status == "approved" and act["outcome"] is None:
            parts.append(
                f"{head} status=approved. The user typed an explicit yes. Carry out only this one "
                "action, once, within the user's original request and safety limits, then call "
                f"a2ui_render op=update with action_id={aid} and action_outcome=done (or failed)."
            )
        elif status == "denied" and act["outcome"] is None:
            parts.append(
                f"{head} status=denied. The user said no. Do nothing; call a2ui_render op=update "
                f"with action_id={aid} and action_outcome=cancelled and show it cancelled."
            )
    if not parts:
        return None
    return _CTRL.sub(" ", " ".join(parts))


def tool_block_message(session_id: str | None, tool_name: Any) -> str | None:
    """A veto message if a pending confirmation forbids this tool right now."""
    name = tool_name if isinstance(tool_name, str) else ""
    if name in SAFE_TOOLS_WHILE_PENDING:
        return None
    for act in session_actions(session_id if isinstance(session_id, str) and session_id else None):
        if act["status"] == "pending_confirmation":
            return (
                "BLOCKED by the uirizz approval gate: the card action "
                f"'{_clean(act['event'])}' (code {_short(act['action_id'])}) is waiting for the "
                "user's explicit yes in chat. A card click is not approval. Show a confirm step "
                "with a2ui_render and wait for the user to type yes or no. Tool "
                f"'{_clean(name)}' stays blocked until they answer or the request expires."
            )
    return None
