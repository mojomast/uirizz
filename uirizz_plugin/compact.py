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


def _child(node: Any, key: Any) -> Any:
    """Descend one step, replacing a missing or scalar child with an empty dict."""
    nxt = node[key] if isinstance(node, list) else node.get(key)
    if not isinstance(nxt, (dict, list)):
        nxt = {}
        node[key] = nxt
    return nxt


def _set_list(node: list, idx: int, value: Any, delete: bool) -> None:
    if delete:
        if idx < len(node):
            node.pop(idx)
    elif idx < len(node):
        node[idx] = copy.deepcopy(value)
    elif idx == len(node):
        node.append(copy.deepcopy(value))
    else:
        raise _Unknown


def _set_last(node: Any, tok: str, value: Any, delete: bool) -> None:
    if isinstance(node, list):
        _set_list(node, _index(tok, len(node), allow_end=not delete), value, delete)
    elif delete:
        node.pop(tok, None)
    else:
        node[tok] = copy.deepcopy(value)


def _step(node: Any, tok: str) -> Any:
    if isinstance(node, dict):
        return _child(node, tok)
    idx = _index(tok, len(node), allow_end=False)
    if idx >= len(node):
        raise _Unknown
    return _child(node, idx)


def _apply(root: Any, path: Any, value: Any) -> Any:
    toks = _tokens(path)
    delete = value is None or value is _MISSING
    if not toks:
        return {} if delete else copy.deepcopy(value)
    if not isinstance(root, (dict, list)):
        root = {}
    node = root
    for tok in toks[:-1]:
        node = _step(node, tok)
    _set_last(node, toks[-1], value, delete)
    return root


class _Folder:
    """Accumulates one surface's state while folding its envelopes in order."""

    def __init__(self) -> None:
        self.create: dict | None = None
        self.order: list[str] = []
        self.comps: dict[str, Any] = {}
        self.data: Any = _MISSING
        self.version: Any = None

    def feed(self, env: Any) -> None:
        if not isinstance(env, dict):
            raise _Unknown
        kinds = [k for k in env if k != "version"]
        if len(kinds) != 1 or kinds[0] not in _KNOWN or kinds[0] == "deleteSurface":
            raise _Unknown
        if "version" in env:
            self.version = env["version"]
        body = env[kinds[0]]
        if not isinstance(body, dict):
            raise _Unknown
        getattr(self, "_" + kinds[0])(body)

    def _createSurface(self, body: dict) -> None:
        if self.create is not None:
            raise _Unknown
        self.create = {k: v for k, v in body.items() if k not in ("components", "dataModel")}
        if "dataModel" in body:
            self.data = copy.deepcopy(body["dataModel"])
        self._components(body.get("components", []))

    def _updateComponents(self, body: dict) -> None:
        if self.create is None or set(body) - {"surfaceId", "components"}:
            raise _Unknown
        self._components(body.get("components", []))

    def _updateDataModel(self, body: dict) -> None:
        if self.create is None or set(body) - {"surfaceId", "path", "value"}:
            raise _Unknown
        base = {} if self.data is _MISSING else self.data
        self.data = _apply(base, body.get("path"), body.get("value", _MISSING))

    def _components(self, items: Any) -> None:
        if not isinstance(items, list):
            raise _Unknown
        for c in items:
            if not isinstance(c, dict) or not isinstance(c.get("id"), str):
                raise _Unknown
            if c["id"] not in self.comps:
                self.order.append(c["id"])
            self.comps[c["id"]] = copy.deepcopy(c)

    def result(self) -> list:
        if self.create is None:
            raise _Unknown
        out = dict(self.create)
        out["components"] = [self.comps[i] for i in self.order]
        if self.data is not _MISSING:
            out["dataModel"] = self.data
        env_out: dict[str, Any] = {}
        if self.version is not None:
            env_out["version"] = self.version
        env_out["createSurface"] = out
        return [env_out]


def _fold(messages: list) -> list:
    folder = _Folder()
    for env in messages:
        folder.feed(env)
    return folder.result()


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
