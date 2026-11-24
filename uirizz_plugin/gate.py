"""Approval gate and audit log for A2UI actions.

A card click is a request, never permission. This module records every click
in an append-only, hash-chained log (unkeyed: it catches accidental edits, not
a deliberate rewrite by someone who can write the file), decides (fail-closed) whether the click
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

Declared actions (see ``bindings.py``) add a bound call to the click: the
approval covers that one tool name plus a hash of its exact arguments. They add:

* ``rejected``: the click's params failed validation or a rate limit; nothing to approve.
* ``executing``: ``pre_tool_call`` let the approved call through (the approval is used up).
* ``unknown``: the call was cancelled mid-flight or never reported back; check before retrying.

For declared actions ``completed`` / ``failed`` come from ``post_tool_call``,
not from the model.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator

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
# How long a bound call may stay "executing" before it is shown as unknown.
EXECUTING_TTL_S = 3600
# Statuses that count toward a declared action's per-hour limit.
_COUNTED = {"approved", "executing", "completed", "failed", "unknown"}
# Finished or refused bound calls whose exact replay is blocked for a while.
_NO_REPLAY = {"executing", "completed", "failed", "unknown", "denied", "cancelled", "expired"}

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
_held = threading.local()


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


def _lock_path() -> Path:
    return _audit_dir() / "actions.lock"


@contextmanager
def _locked() -> Iterator[None]:
    """Hold the gate lock: this process's threads and every other process.

    The lock lives on a separate ``actions.lock`` file that is never rotated,
    so a process waiting for it can never end up appending to a log file that
    was just renamed away. Re-entrant within one thread, so a locked section
    can call ``_append`` and the readers.
    """
    with _lock:
        if getattr(_held, "depth", 0):
            _held.depth += 1
            try:
                yield
            finally:
                _held.depth -= 1
            return
        with open(_lock_path(), "a+", encoding="utf-8") as lock_fh:
            if fcntl is not None:
                fcntl.flock(lock_fh.fileno(), fcntl.LOCK_EX)
            _held.depth = 1
            try:
                yield
            finally:
                _held.depth = 0
                if fcntl is not None:
                    fcntl.flock(lock_fh.fileno(), fcntl.LOCK_UN)


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


def _chain(prev: str, seq: int, entry: dict[str, Any], *, keep_time: bool = False) -> dict[str, Any]:
    body = dict(entry)
    for k in ("hash", "prev", "seq"):
        body.pop(k, None)
    body["seq"] = seq + 1
    if not keep_time or "_t" not in body:
        body["ts"] = _iso(_now())
        body["_t"] = _now()
    body["prev"] = prev
    body["hash"] = _digest(prev, {k: v for k, v in body.items() if k != "hash"})
    return body


def _append(entry: dict[str, Any]) -> dict[str, Any]:
    """Append one chained entry, rotating the log if it got too big.

    Runs under :func:`_locked`, so the append and any rotation are one step
    for every thread and process.
    """
    path = _log_path()
    with _locked():
        with open(path, "a+", encoding="utf-8") as fh:
            # Also lock the log itself, for older uirizz versions that only know this lock.
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
                body = _chain(prev, seq, entry)
                fh.seek(0, 2)
                fh.write(json.dumps(body, ensure_ascii=False, separators=(",", ":")) + "\n")
                fh.flush()
                size = fh.tell()
            finally:
                if fcntl is not None:
                    fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        if size > MAX_LOG_BYTES:
            _rotate(path)
    return body


# How far back rotation must carry entries: the per-hour limit window.
_CARRY_WINDOW_S = 3600


def _carry_ids(entries: list[dict[str, Any]], now: float) -> set[str]:
    """Actions whose state the gate still needs after a rotation.

    Open actions (pending, approved, executing), anything clicked inside the
    per-hour window (rate limits), and anything decided inside the approval
    window (replay block). Everything else stays only in the backup.
    """
    keep: set[str] = set()
    for aid, act in _fold(entries, now).items():
        if act["status"] in ("pending_confirmation", "approved", "executing"):
            keep.add(aid)
        elif now - float(act.get("_t") or 0) <= max(_CARRY_WINDOW_S, APPROVAL_TTL_S):
            keep.add(aid)
        elif act.get("decided_t") and now - float(act["decided_t"]) <= APPROVAL_TTL_S:
            keep.add(aid)
    return keep


def _rotate(path: Path) -> None:
    """Roll the log over, carrying the live state into the new file. Call under ``_locked``.

    The old file becomes ``actions.jsonl.1`` (one backup). The new file starts
    with a ``rotated`` entry whose ``prev`` is the old file's last hash, then
    copies of every entry of the actions the gate still needs (original times
    kept, ``carried: true``), re-chained. The log is swapped in with one
    atomic rename, so readers never see an empty log.
    """
    entries = []
    for line in _read_lines(path):
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            entries.append(item)
    if not entries:
        return
    now = _now()
    keep = _carry_ids(entries, now)
    last = entries[-1]
    body = _chain(str(last.get("hash", "0" * 64)), 0, {
        "type": "rotated", "from_seq": last.get("seq"), "carried_actions": len(keep)})
    out = [body]
    for e in entries:
        if e.get("type") in ("action", "announced", "decision", "outcome", "consumed", "released",
                             "executed", "outcome_announced", "note", "delivered") and e.get("action_id") in keep:
            carried = {k: v for k, v in e.items() if k not in ("hash", "prev", "seq")}
            carried["carried"] = True
            body = _chain(body["hash"], body["seq"], carried, keep_time=True)
            out.append(body)
    backup = path.with_suffix(".jsonl.1")
    tmp_backup = path.with_suffix(".jsonl.1.tmp")
    tmp_new = path.with_suffix(".jsonl.tmp")
    with open(tmp_new, "w", encoding="utf-8") as fh:
        for item in out:
            fh.write(json.dumps(item, ensure_ascii=False, separators=(",", ":")) + "\n")
        fh.flush()
        os.fsync(fh.fileno())
    with open(path, "rb") as src, open(tmp_backup, "wb") as dst:
        dst.write(src.read())
        dst.flush()
        os.fsync(dst.fileno())
    os.replace(tmp_backup, backup)
    os.replace(tmp_new, path)


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
                "status": (
                    "rejected" if e.get("rejected")
                    else "pending_confirmation" if e.get("requires_confirmation") else "recorded"
                ),
                "announced": False,
                "decided_t": None,
                "decision_by": None,
                "outcome": None,
                "binding": e.get("binding"),
                "rejected": e.get("rejected"),
                "consumed_t": None,
                "tool_call_id": None,
                "error_type": None,
                "outcome_announced": False,
                "delivered": False,
                "notes": [],
            }
        elif isinstance(aid, str) and aid in actions:
            act = actions[aid]
            if kind == "announced":
                act["announced"] = True
            elif kind == "decision":
                act["status"] = e.get("decision")
                act["decided_t"] = e.get("_t")
                act["decision_by"] = e.get("source")
                if e.get("reason"):
                    act["rejected"] = e.get("reason")
            elif kind == "outcome":
                act["outcome"] = e.get("outcome")
                act["status"] = {"done": "completed", "failed": "failed", "cancelled": "cancelled"}.get(
                    str(e.get("outcome")), act["status"])
            elif kind == "consumed" and act["status"] == "approved":
                act["status"] = "executing"
                act["consumed_t"] = e.get("_t")
                act["tool_call_id"] = e.get("tool_call_id")
            elif kind == "released" and act["status"] == "executing":
                act["status"] = "approved"
                act["consumed_t"] = None
                act["tool_call_id"] = None
            elif kind == "executed" and act["status"] == "executing":
                act["status"] = str(e.get("result_status") or "unknown")
                act["outcome"] = {"completed": "done", "failed": "failed"}.get(act["status"], "unknown")
                act["error_type"] = e.get("error_type")
                act["decided_t"] = act["decided_t"] or e.get("_t")
            elif kind == "outcome_announced":
                act["outcome_announced"] = True
            elif kind == "note":
                act["notes"].append(e.get("note"))
            elif kind == "delivered":
                act["delivered"] = True
    for act in actions.values():
        if act["status"] == "pending_confirmation" and now - float(act["_t"] or 0) > APPROVAL_TTL_S:
            act["status"] = "expired"
        elif act["status"] == "approved" and now - float(act["decided_t"] or 0) > APPROVAL_TTL_S:
            act["status"] = "expired"
        elif act["status"] == "executing" and now - float(act["consumed_t"] or 0) > EXECUTING_TTL_S:
            act["status"] = "unknown"
            act["outcome"] = "unknown"
    return actions


def session_actions(session_id: str | None, now: float | None = None) -> list[dict[str, Any]]:
    folded = _fold(read_entries(), now)
    items = [a for a in folded.values() if not session_id or a["session_id"] == session_id]
    return sorted(items, key=lambda a: a["_t"] or 0)


def _short(action_id: str) -> str:
    return action_id.replace("act-", "")[:6]


# ------------------------------------------------------------------ writers


def _recent_count(action_name: str, now: float | None = None) -> int:
    now = _now() if now is None else now
    count = 0
    for act in _fold(read_entries(), now).values():
        b = act.get("binding") or {}
        if b.get("action") == action_name and act["status"] in _COUNTED:
            if now - float(act.get("_t") or 0) <= 3600:
                count += 1
    return count


def log_action(**kwargs: Any) -> dict[str, Any]:
    """Record a click (see :func:`_log_action`). Read, decide and write are one locked step."""
    with _locked():
        return _log_action(**kwargs)


def _log_action(
    *,
    surface_id: str,
    session_id: str,
    event: str,
    context: Any,
    surface: dict[str, Any] | None,
    source_component_id: Any = None,
    client_timestamp: Any = None,
) -> dict[str, Any]:
    """Record a click. Never authorizes anything. Returns the audit entry.

    A click on a declared action is validated and bound to one exact tool call.
    Only a ``risk: low`` action the user marked ``auto_approve`` in their own
    actions file is approved by the click; that is the user's standing
    approval for that one bound call, not the card's.
    """
    action_id = "act-" + uuid.uuid4().hex[:12]
    binding: dict[str, Any] | None = None
    rejected: str | None = None
    declared = None
    try:
        from uirizz_plugin import bindings as _bindings

        declared = _bindings.get_action(str(event))
    except Exception:  # noqa: BLE001 - a broken registry must not open the gate
        declared = None
    if declared is not None:
        try:
            bound = _bindings.bind(declared, context, operation_id=action_id)
            binding = bound.record()
            if declared.per_hour and _recent_count(declared.name) >= declared.per_hour:
                rejected = f"rate limit: {declared.per_hour} per hour for {declared.name}"
        except _bindings.ParamError as exc:
            rejected = f"invalid params: {exc}"
            binding = {"action": declared.name, "tool": declared.tool, "risk": declared.risk,
                       "title": declared.title}
        gated = rejected is None
        reason = rejected or f"declared action ({declared.risk} risk)"
    else:
        gated, reason = classify(event, context, definition_contexts(surface, str(event)))
    entry = _append(
        {
            "type": "action",
            "action_id": action_id,
            "session_id": _clean(session_id),
            "surface_id": _clean(surface_id),
            "event": _clean(event)[:120],
            "context": _bounded_context(context),
            "source_component_id": _clean(source_component_id)[:120] if source_component_id else None,
            "client_timestamp": _clean(client_timestamp)[:64] if client_timestamp else None,
            "requires_confirmation": gated,
            "reason": reason,
            "binding": binding,
            "rejected": rejected,
        }
    )
    if gated and binding and binding.get("auto_approve") and not _bindings.exec_like(binding.get("tool")):
        _append({"type": "decision", "action_id": action_id, "decision": "approved",
                 "source": "policy:auto_approve"})
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


def _code_required(act: dict[str, Any]) -> bool:
    """Whether a typed yes must carry this action's code.

    Only a declared action with ``risk: low`` may be approved by a bare yes,
    and only when it is the one open question. Medium, high and free-form
    (undeclared) side effects always need ``yes <code>``.
    """
    b = act.get("binding")
    return not (isinstance(b, dict) and b.get("risk") == "low")


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
    """Resolve pending actions from a typed reply (see :func:`_observe`), as one locked step."""
    with _locked():
        return _observe(session_id, text)


def _over_limit(act: dict[str, Any]) -> str | None:
    """Re-check a declared action's per-hour limit at approval time."""
    b = act.get("binding")
    if not isinstance(b, dict) or not b.get("action"):
        return None
    try:
        from uirizz_plugin import bindings as _bindings

        declared = _bindings.get_action(str(b["action"]))
    except Exception:  # noqa: BLE001 - the click-time check already ran
        return None
    if declared is None or not declared.per_hour:
        return None
    if _recent_count(declared.name) >= declared.per_hour:
        return f"rate limit: {declared.per_hour} per hour for {declared.name}"
    return None


def _observe(session_id: str | None, text: Any) -> list[dict[str, Any]]:
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
    elif verdict == "yes" and (len(pending) > 1 or _code_required(pending[0])):
        # A bare "yes" may answer some other question. It approves only a lone
        # low-risk declared action; everything else needs `yes <code>`.
        for act in pending:
            _append({"type": "note", "action_id": act["action_id"], "note": "needs_code"})
        return []
    decided = []
    excerpt = _clean(text).strip()[:80]
    for act in pending:
        decision = "approved" if verdict == "yes" else "denied"
        limit = _over_limit(act) if decision == "approved" else None
        if limit:
            _append({"type": "decision", "action_id": act["action_id"], "decision": "rejected",
                     "source": "rate_limit", "reason": limit, "evidence": excerpt})
            decided.append({"action_id": act["action_id"], "decision": "rejected"})
            continue
        _append({"type": "decision", "action_id": act["action_id"], "decision": decision,
                 "source": "user_message", "evidence": excerpt})
        decided.append({"action_id": act["action_id"], "decision": decision})
    return decided


def complete_action(action_id: Any, outcome: Any) -> dict[str, Any]:
    """Record the outcome of an action. 'done' needs a live user approval."""
    with _locked():
        return _complete_action(action_id, outcome)


def _complete_action(action_id: Any, outcome: Any) -> dict[str, Any]:
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
    if act.get("binding") and act.get("rejected") is None and outcome in ("done", "failed"):
        raise GateError(
            "recorded_automatically",
            f"Action {action_id} is a declared action; its outcome is recorded from the tool call.",
            "Do not report done or failed. Update the card to show the status the notice gave you.",
        )
    if act.get("binding") and status in ("executing", "unknown"):
        raise GateError(
            "already_running",
            f"Action {action_id} is {status}; it can no longer be cancelled from the card.",
            "Tell the user the current status. For unknown, ask them to check before trying again.",
        )
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


def take_recorded_clicks(session_id: str, *, limit: int, ttl_s: float) -> list[dict[str, Any]]:
    """Read-only clicks for this session not yet shown to the agent, newest ``limit``.

    Reads the audit log on disk, so a click recorded by the dashboard process
    reaches the agent process. Marks every undelivered one as delivered (also
    the ones dropped for age or the limit), in one locked step, so each click
    is shown at most once and the backlog cannot grow without bound.
    """
    with _locked():
        now = _now()
        fresh = [a for a in session_actions(session_id, now)
                 if a["status"] == "recorded" and not a.get("delivered")]
        for act in fresh:
            _append({"type": "delivered", "action_id": act["action_id"]})
        live = [a for a in fresh if now - float(a.get("_t") or 0) <= ttl_s]
        return live[-limit:] if limit > 0 else []


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
        "binding": _binding_view(act),
        "rejected": act.get("rejected"),
        "error_type": act.get("error_type"),
        "needs_code": "needs_code" in (act.get("notes") or []),
    }


def _binding_view(act: dict[str, Any]) -> dict[str, Any] | None:
    """What a card or the audit view may show: no raw secret-looking values."""
    b = act.get("binding")
    if not isinstance(b, dict):
        return None
    from uirizz_plugin.bindings import redact

    return {
        "action": b.get("action"),
        "title": _clean(b.get("title"))[:300],
        "tool": b.get("tool"),
        "args": redact(b.get("args")) if "args" in b else None,
        "risk": b.get("risk"),
        "auto_approve": bool(b.get("auto_approve")),
        "code_required": _code_required(act),
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


def _call_json(b: dict[str, Any]) -> str:
    return _CTRL.sub(" ", json.dumps(b.get("args"), ensure_ascii=False, sort_keys=True))


def gate_notice(session_id: str | None) -> str | None:
    """Text for the model about actions that need, or just got, a decision."""
    with _locked():
        return _gate_notice(session_id)


def _gate_notice(session_id: str | None) -> str | None:
    if not isinstance(session_id, str) or not session_id:
        return None
    parts: list[str] = []
    for act in session_actions(session_id):
        status = act["status"]
        aid = act["action_id"]
        b = act.get("binding") if isinstance(act.get("binding"), dict) else None
        head = (
            f"Approval gate: action_id={aid} code={_short(aid)} surface_id={_clean(act['surface_id'])} "
            f"event={_clean(act['event'])}"
        )
        if b:
            head += f" declared_action={_clean(b.get('action'))} risk={_clean(b.get('risk'))}"
        if status == "rejected" and not act["outcome_announced"]:
            _append({"type": "outcome_announced", "action_id": aid})
            parts.append(
                f"{head} status=rejected ({_clean(act.get('rejected'))[:300]}). Nothing will run. "
                "Fix the card's Event context or tell the user why; see op=describe topic=actions."
            )
        elif status == "pending_confirmation":
            if not act["announced"]:
                mark_announced(aid)
            reply = f"yes {_short(aid)}" if _code_required(act) else "yes"
            extra = ""
            if "needs_code" in (act.get("notes") or []):
                extra = " The user replied yes without the code; this action needs the code. "
            if b:
                parts.append(
                    f"{head} status=pending_confirmation. The card shows uirizz's own confirm panel: "
                    f"\"{_clean(b.get('title'))}\" (tool {_clean(b.get('tool'))}).{extra} Tell the user "
                    f"exactly that, and ask them to reply `{reply}` or `no` in chat. Do NOT call "
                    "other tools; a click is not approval."
                )
            else:
                parts.append(
                    f"{head} status=pending_confirmation. The user's card click is a request, not "
                    "approval. Do NOT perform the side effect and do not call tools other than "
                    f"a2ui_render. Update the same surface to show a confirm step naming exactly what "
                    f"will happen, and ask the user to reply `{reply}` or `no` in chat.{extra}"
                    "Only the user's typed chat reply counts."
                )
        elif status == "approved" and act["outcome"] is None:
            if b:
                parts.append(
                    f"{head} status=approved. Call tool `{_clean(b.get('tool'))}` once with exactly "
                    f"these arguments: {_call_json(b)}. Any other tool or argument is blocked until it "
                    "runs. uirizz records the result itself; do not report action_outcome. To drop it "
                    f"instead, call a2ui_render op=update with action_id={aid} action_outcome=cancelled."
                )
            else:
                parts.append(
                    f"{head} status=approved. The user typed an explicit yes. Carry out only this one "
                    "action, once, within the user's original request and safety limits, then call "
                    f"a2ui_render op=update with action_id={aid} and action_outcome=done (or failed)."
                )
        elif status == "denied" and act["outcome"] is None:
            if b:
                if not act["outcome_announced"]:
                    _append({"type": "outcome_announced", "action_id": aid})
                    parts.append(
                        f"{head} status=denied. The user said no. Nothing runs. Do not ask again "
                        "unless the user brings it up; update the card to show it was cancelled."
                    )
            else:
                parts.append(
                    f"{head} status=denied. The user said no. Do nothing; call a2ui_render op=update "
                    f"with action_id={aid} and action_outcome=cancelled and show it cancelled."
                )
        elif b and status in ("completed", "failed", "unknown") and not act["outcome_announced"]:
            _append({"type": "outcome_announced", "action_id": aid})
            if status == "completed":
                tail = "The tool call succeeded. Update the card to show it is done."
            elif status == "failed":
                tail = (f"The tool call failed ({_clean(act.get('error_type') or 'error')}). Update the "
                        "card and tell the user; do not retry without a new click and approval.")
            else:
                tail = ("The outcome is unknown (cancelled or no result). Do not retry; ask the user to "
                        "check the target system first.")
            parts.append(f"{head} status={status}. {tail}")
    if not parts:
        return None
    return _CTRL.sub(" ", " ".join(parts))


_FREEFORM_DONE = frozenset({"approved", "completed", "failed", "cancelled"})


def _freeform_exec_block(acts: list[dict[str, Any]], name: str) -> str | None:
    """Option (b): a free-form yes never unlocks shell, exec or code tools.

    A free-form action has no bound call, so its yes can't say which command
    may run. For APPROVAL_TTL_S after that yes, even once the agent marks it
    done, exec-like tools are blocked unless a declared action covers the exact
    call (that case returns earlier in tool_block_message).
    """
    from uirizz_plugin.bindings import exec_like

    if not exec_like(name):
        return None
    now = _now()
    for act in acts:
        bound = isinstance(act.get("binding"), dict) and act["binding"].get("args_hash")
        decided = float(act.get("decided_t") or 0)
        if (not bound and act.get("requires_confirmation") and act["status"] in _FREEFORM_DONE
                and decided and now - decided <= APPROVAL_TTL_S):
            return (
                "BLOCKED by the uirizz approval gate: the user's yes on the free-form card action "
                f"'{_clean(act['event'])}' (code {_short(act['action_id'])}) is not bound to any tool "
                f"call, so it does not cover shell, exec or code tools like '{_clean(name)}'. Ask the "
                "user to approve a declared action that names this exact call."
            )
    return None


def tool_block_message(
    session_id: str | None,
    tool_name: Any,
    args: Any = None,
    tool_call_id: Any = None,
    *,
    has_args: bool | None = None,
) -> str | None:
    """A veto message if the gate forbids this tool call right now, else None.

    * While any action waits for the user's yes, only safe tools run.
    * While a declared action is approved, only its exact bound call runs, once
      (the check and the "consumed" record are one atomic step).
    * An exact replay of a bound call that already ran, or that the user
      denied, is blocked for the approval window.
    """
    name = tool_name if isinstance(tool_name, str) else ""
    if name in SAFE_TOOLS_WHILE_PENDING:
        return None
    sid = session_id if isinstance(session_id, str) and session_id else None
    if has_args is None:
        has_args = args is not None
    with _locked():
        acts = session_actions(sid)
        for act in acts:
            if act["status"] == "pending_confirmation":
                return (
                    "BLOCKED by the uirizz approval gate: the card action "
                    f"'{_clean(act['event'])}' (code {_short(act['action_id'])}) is waiting for the "
                    "user's explicit yes in chat. A card click is not approval. Show a confirm step "
                    "with a2ui_render and wait for the user to type yes or no. Tool "
                    f"'{_clean(name)}' stays blocked until they answer or the request expires."
                )
        if sid is None:
            return None
        from uirizz_plugin.bindings import call_hash

        digest = call_hash(name, args) if has_args else None
        approved = [a for a in acts if a["status"] == "approved" and isinstance(a.get("binding"), dict)
                    and a["binding"].get("args_hash")]
        for act in approved:
            b = act["binding"]
            if name == b.get("tool") and digest == b.get("args_hash"):
                _append({"type": "consumed", "action_id": act["action_id"],
                         "tool_call_id": _clean(tool_call_id)[:120] if tool_call_id else None,
                         "args_hash": digest})
                return None
        if approved:
            b = approved[0]["binding"]
            aid = approved[0]["action_id"]
            if not has_args:
                why = "this host did not pass the tool arguments, so the approved call cannot be verified"
            elif name == b.get("tool"):
                why = "the arguments differ from what the user approved"
            else:
                why = f"the user approved one call to '{_clean(b.get('tool'))}' and it has not run yet"
            return (
                f"BLOCKED by the uirizz approval gate: {why}. Call '{_clean(b.get('tool'))}' with exactly "
                f"{_call_json(b)}, or cancel it with a2ui_render op=update action_id={aid} "
                "action_outcome=cancelled. Changing the call needs a new click and a new yes."
            )
        freeform = _freeform_exec_block(acts, name)
        if freeform:
            return freeform
        if digest is not None:
            now = _now()
            for act in acts:
                b = act.get("binding")
                if (isinstance(b, dict) and act["status"] in _NO_REPLAY and name == b.get("tool")
                        and digest == b.get("args_hash")
                        and now - float(act.get("decided_t") or act.get("_t") or 0) <= APPROVAL_TTL_S):
                    return (
                        f"BLOCKED by the uirizz approval gate: this exact call was already "
                        f"{act['status']} for action {act['action_id']}. Each approval runs once; a new "
                        "attempt needs a new click and the user's yes."
                    )
    return None


_RESULT_STATUS = {"ok": "completed", "success": "completed", "error": "failed", "cancelled": "unknown"}


def record_tool_result(
    session_id: str | None,
    tool_name: Any,
    args: Any = None,
    tool_call_id: Any = None,
    status: Any = None,
    error_type: Any = None,
    *,
    has_args: bool | None = None,
) -> dict[str, Any] | None:
    """post_tool_call: close the bound call that pre_tool_call let through.

    ok -> completed, error -> failed, cancelled -> unknown (it may have run),
    blocked (a later hook vetoed it) -> released back to approved.
    """
    name = tool_name if isinstance(tool_name, str) else ""
    sid = session_id if isinstance(session_id, str) and session_id else None
    if sid is None or not name or name in SAFE_TOOLS_WHILE_PENDING:
        return None
    if has_args is None:
        has_args = args is not None
    from uirizz_plugin.bindings import call_hash

    digest = call_hash(name, args) if has_args else None
    call_id = _clean(tool_call_id)[:120] if tool_call_id else None
    with _locked():
        executing = [a for a in session_actions(sid) if a["status"] == "executing"
                     and isinstance(a.get("binding"), dict) and a["binding"].get("tool") == name]
        match = None
        if call_id:
            match = next((a for a in executing if a.get("tool_call_id") == call_id), None)
        if match is None and digest is not None:
            match = next((a for a in executing if a["binding"].get("args_hash") == digest), None)
        if match is None:
            return None
        aid = match["action_id"]
        st = str(status or "").lower()
        if st == "blocked":
            _append({"type": "released", "action_id": aid})
            return {"action_id": aid, "status": "approved"}
        result = _RESULT_STATUS.get(st, "unknown")
        if digest is not None and digest != match["binding"].get("args_hash"):
            # Something rewrote the arguments after the gate checked them.
            result = "unknown"
            error_type = "args_changed_after_approval"
        _append({"type": "executed", "action_id": aid, "result_status": result,
                 "error_type": _clean(error_type)[:80] if error_type else None})
        return {"action_id": aid, "status": result}
