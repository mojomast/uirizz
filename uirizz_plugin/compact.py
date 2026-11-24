"""Fold a surface's append-only envelope history into at most two envelopes."""

from __future__ import annotations

import copy
from typing import Any

_KNOWN = {"createSurface", "updateComponents", "updateDataModel", "deleteSurface"}
_MISSING = object()


class _Unknown(Exception):
    pass


def _tokens(path: Any) -> list[str]:
    if path is None:
        return []
    if not isinstance(path, str):
        raise _Unknown
    if path in ("", "/"):
        return []
    if not path.startswith("/"):
        raise _Unknown
    return [t.replace("~1", "/").replace("~0", "~") for t in path[1:].split("/")]


def _index(tok: str, length: int, allow_end: bool) -> int:
    if tok == "-" and allow_end:
        return length
    if not tok.isdigit():
        raise _Unknown
    return int(tok)


def _apply(root: Any, path: Any, value: Any) -> Any:
    toks = _tokens(path)
    delete = value is None or value is _MISSING
    if not toks:
        return {} if delete else copy.deepcopy(value)
    if not isinstance(root, (dict, list)):
        root = {}
    node = root
    for i, tok in enumerate(toks):
        last = i == len(toks) - 1
        if isinstance(node, dict):
            if last:
                if delete:
                    node.pop(tok, None)
                else:
                    node[tok] = copy.deepcopy(value)
                return root
            nxt = node.get(tok)
            if not isinstance(nxt, (dict, list)):
                nxt = {}
                node[tok] = nxt
            node = nxt
        else:
            idx = _index(tok, len(node), allow_end=last and not delete)
            if last:
                if delete:
                    if idx < len(node):
                        node.pop(idx)
                elif idx < len(node):
                    node[idx] = copy.deepcopy(value)
                elif idx == len(node):
                    node.append(copy.deepcopy(value))
                else:
                    raise _Unknown
                return root
            if idx >= len(node):
                raise _Unknown
            nxt = node[idx]
            if not isinstance(nxt, (dict, list)):
                nxt = {}
                node[idx] = nxt
            node = nxt
    return root


def _fold(messages: list) -> list:
    create: dict | None = None
    order: list[str] = []
    comps: dict[str, Any] = {}
    data: Any = _MISSING
    version = None
    for env in messages:
        if not isinstance(env, dict):
            raise _Unknown
        kinds = [k for k in env if k != "version"]
        if len(kinds) != 1 or kinds[0] not in _KNOWN or kinds[0] == "deleteSurface":
            raise _Unknown
        if "version" in env:
            version = env["version"]
        kind = kinds[0]
        body = env[kind]
        if not isinstance(body, dict):
            raise _Unknown
        if kind == "createSurface":
            if create is not None:
                raise _Unknown
            create = {k: v for k, v in body.items() if k not in ("components", "dataModel")}
            if "dataModel" in body:
                data = copy.deepcopy(body["dataModel"])
            items = body.get("components", [])
        elif kind == "updateComponents":
            if create is None or set(body) - {"surfaceId", "components"}:
                raise _Unknown
            items = body.get("components", [])
        else:
            if create is None or set(body) - {"surfaceId", "path", "value"}:
                raise _Unknown
            base = {} if data is _MISSING else data
            data = _apply(base, body.get("path"), body.get("value", _MISSING))
            continue
        if not isinstance(items, list):
            raise _Unknown
        for c in items:
            if not isinstance(c, dict) or not isinstance(c.get("id"), str):
                raise _Unknown
            if c["id"] not in comps:
                order.append(c["id"])
            comps[c["id"]] = copy.deepcopy(c)
    if create is None:
        raise _Unknown
    out = dict(create)
    out["components"] = [comps[i] for i in order]
    if data is not _MISSING:
        out["dataModel"] = data
    env_out: dict[str, Any] = {}
    if version is not None:
        env_out["version"] = version
    env_out["createSurface"] = out
    return [env_out]


def compact_messages(messages: list) -> list:
    """Fold history into one createSurface envelope; unchanged if anything is unfamiliar."""
    if not isinstance(messages, list) or not messages:
        return messages
    try:
        return _fold(messages)
    except (_Unknown, TypeError, ValueError, RecursionError):
        return messages


def maybe_compact(messages: list, threshold: int = 40) -> list:
    if isinstance(messages, list) and len(messages) > threshold:
        return compact_messages(messages)
    return messages
