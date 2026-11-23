"""Declared actions: card buttons bound to one exact Hermes tool call.

A declared action turns a card event name into a concrete, typed tool call:

    deploy_service:
      title: "Deploy {service} {version} to {env}"
      tool: mcp_github_dispatch_workflow
      args: {repo: "acme/{service}", inputs: {version: "{version}", env: "{env}"}}
      params:
        service: {type: string, enum: [checkout-api, search-api]}
        version: {type: string, pattern: "^v[0-9]+$"}
        env: {type: string, enum: [staging, production]}
      risk: high

When a card fires ``Event("deploy_service", {...})`` the click context is
validated against ``params``, the tool call is rendered from ``args``, and the
approval gate approves *that call* (tool name plus a hash of the canonical
arguments), once. uirizz never executes anything itself: Hermes runs the tool
the user already configured, and ``pre_tool_call`` / ``post_tool_call`` enforce
and record it.

Definitions come from the user's ``actions.yaml`` / ``actions.json`` in the
plugin data directory, or from other plugins through :func:`register_action`.
User files win on a name collision. Secrets never belong in a definition; the
tool's own configuration holds credentials.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

RISKS = ("low", "medium", "high")
DEFAULT_RISK = "medium"
PARAM_TYPES = ("string", "integer", "number", "boolean", "array")
OPERATION_ID = "operation_id"  # reserved template variable: the stable action_id

_NAME = re.compile(r"^[a-z][a-z0-9_]{1,63}$")
_TOOL = re.compile(r"^[A-Za-z0-9_.:\-]{1,128}$")
_PLACEHOLDER = re.compile(r"\{([a-z_][a-z0-9_]{0,63})\}")
_WHOLE = re.compile(r"^\{([a-z_][a-z0-9_]{0,63})\}$")
_SECRET_KEY = re.compile(
    r"(pass|secret|token|key|pin|ssn|card|cvv|auth|cookie|session|bearer|credential)", re.I
)
_CTRL = re.compile(r"[\x00-\x1f\x7f]")

MAX_STRING = 1000
MAX_ARRAY = 50
MAX_PATTERN = 200
MAX_ACTIONS = 200
FILE_NAMES = ("actions.yaml", "actions.yml", "actions.json")


class ActionConfigError(ValueError):
    """A definition is invalid. Carries a model- and human-readable reason."""


class ParamError(ValueError):
    """A click's context does not satisfy the action's params."""


@dataclass(frozen=True)
class ActionDef:
    name: str
    title: str
    tool: str
    args: Any
    params: dict[str, dict[str, Any]]
    risk: str = DEFAULT_RISK
    auto_approve: bool = False
    per_hour: int | None = None
    description: str = ""
    source: str = "file"

    def public(self) -> dict[str, Any]:
        """What the model sees with op=describe topic=actions."""
        params = {}
        for key, spec in self.params.items():
            shown = {k: v for k, v in spec.items() if k in (
                "type", "enum", "pattern", "minimum", "maximum", "minLength",
                "maxLength", "default", "description", "items")}
            shown["required"] = "default" not in spec and not spec.get("optional", False)
            params[key] = shown
        out: dict[str, Any] = {
            "action": self.name,
            "title": self.title,
            "tool": self.tool,
            "risk": self.risk,
            "auto_approve": self.auto_approve,
            "params": params,
        }
        if self.description:
            out["description"] = self.description
        if self.per_hour:
            out["per_hour"] = self.per_hour
        return out


@dataclass
class Binding:
    """A rendered, validated call for one click."""

    action: str
    tool: str
    args: Any
    args_hash: str
    title: str
    risk: str
    auto_approve: bool
    params: dict[str, Any] = field(default_factory=dict)

    def record(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "tool": self.tool,
            "args": self.args,
            "args_hash": self.args_hash,
            "title": self.title,
            "risk": self.risk,
            "auto_approve": self.auto_approve,
            "params": self.params,
        }


# --------------------------------------------------------------- hashing


def canonical(value: Any) -> str:
    """Canonical JSON for hashing: sorted keys, no whitespace, integral floats as ints."""

    def norm(v: Any) -> Any:
        if isinstance(v, bool) or v is None or isinstance(v, str):
            return v
        if isinstance(v, float) and v.is_integer():
            return int(v)
        if isinstance(v, (int, float)):
            return v
        if isinstance(v, dict):
            return {str(k): norm(x) for k, x in v.items()}
        if isinstance(v, (list, tuple)):
            return [norm(x) for x in v]
        return str(v)

    return json.dumps(norm(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def call_hash(tool: str, args: Any) -> str:
    return hashlib.sha256((str(tool) + "\n" + canonical(args)).encode("utf-8")).hexdigest()


def redact(value: Any, *, key: str = "") -> Any:
    """Display copy of args: secret-looking keys hidden, strings bounded."""
    if key and _SECRET_KEY.search(key):
        return "[redacted]"
    if isinstance(value, dict):
        return {str(k): redact(v, key=str(k)) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v) for v in value[:MAX_ARRAY]]
    if isinstance(value, str):
        text = _CTRL.sub(" ", value)
        return text if len(text) <= 300 else text[:297] + "..."
    return value


# --------------------------------------------------------------- validation


def _check_param_spec(action: str, key: str, spec: Any) -> dict[str, Any]:
    if not _PLACEHOLDER.fullmatch("{" + str(key) + "}"):
        raise ActionConfigError(f"{action}: param name {key!r} must be lowercase letters, digits, underscore")
    if key == OPERATION_ID:
        raise ActionConfigError(f"{action}: {OPERATION_ID!r} is reserved")
    if not isinstance(spec, dict):
        raise ActionConfigError(f"{action}.params.{key}: must be a mapping")
    typ = spec.get("type", "string")
    if typ not in PARAM_TYPES:
        raise ActionConfigError(f"{action}.params.{key}.type: one of {', '.join(PARAM_TYPES)}")
    out = dict(spec)
    out["type"] = typ
    if "enum" in out:
        if not isinstance(out["enum"], list) or not out["enum"]:
            raise ActionConfigError(f"{action}.params.{key}.enum: a non-empty list")
    if "pattern" in out:
        pat = out["pattern"]
        if not isinstance(pat, str) or len(pat) > MAX_PATTERN:
            raise ActionConfigError(f"{action}.params.{key}.pattern: a string under {MAX_PATTERN} chars")
        try:
            re.compile(pat)
        except re.error as exc:
            raise ActionConfigError(f"{action}.params.{key}.pattern: {exc}") from exc
    if typ == "array":
        items = out.get("items", {"type": "string"})
        if not isinstance(items, dict) or items.get("type", "string") not in ("string", "integer", "number", "boolean"):
            raise ActionConfigError(f"{action}.params.{key}.items: a scalar type")
        out["items"] = {"type": items.get("type", "string"), **{k: v for k, v in items.items() if k != "type"}}
    if "default" in out:
        try:
            coerce_param(action, key, out, out["default"])
        except ParamError as exc:
            raise ActionConfigError(f"{action}.params.{key}.default: {exc}") from exc
    return out


def _placeholders(node: Any, found: set[str]) -> None:
    if isinstance(node, str):
        found.update(_PLACEHOLDER.findall(node))
    elif isinstance(node, dict):
        for k, v in node.items():
            _placeholders(str(k), found)
            _placeholders(v, found)
    elif isinstance(node, list):
        for v in node:
            _placeholders(v, found)


def parse_definition(name: Any, raw: Any, *, source: str = "file") -> ActionDef:
    """Validate one definition. Raises ActionConfigError with a precise reason."""
    if not isinstance(name, str) or not _NAME.match(name):
        raise ActionConfigError(f"action name {name!r}: lowercase, start with a letter, 2-64 chars of a-z 0-9 _")
    if not isinstance(raw, dict):
        raise ActionConfigError(f"{name}: definition must be a mapping")
    allowed = {"title", "tool", "args", "params", "risk", "auto_approve", "limits", "description"}
    extra = set(raw) - allowed
    if extra:
        raise ActionConfigError(f"{name}: unknown keys {sorted(extra)}")
    tool = raw.get("tool")
    if not isinstance(tool, str) or not _TOOL.match(tool):
        raise ActionConfigError(f"{name}.tool: the Hermes tool name to call")
    if tool == "a2ui_render":
        raise ActionConfigError(f"{name}.tool: a2ui_render cannot be a declared action")
    title = raw.get("title")
    if not isinstance(title, str) or not title.strip() or len(title) > 200:
        raise ActionConfigError(f"{name}.title: a short sentence saying what will happen")
    risk = raw.get("risk", DEFAULT_RISK)
    if risk not in RISKS:
        raise ActionConfigError(f"{name}.risk: one of {', '.join(RISKS)}")
    auto = raw.get("auto_approve", False)
    if not isinstance(auto, bool):
        raise ActionConfigError(f"{name}.auto_approve: true or false")
    if auto and risk != "low":
        raise ActionConfigError(f"{name}.auto_approve: only allowed with risk: low")
    params_raw = raw.get("params", {}) or {}
    if not isinstance(params_raw, dict):
        raise ActionConfigError(f"{name}.params: a mapping of param name to spec")
    params = {str(k): _check_param_spec(name, str(k), v) for k, v in params_raw.items()}
    args = raw.get("args", {})
    if not isinstance(args, (dict, list)):
        raise ActionConfigError(f"{name}.args: a mapping (the tool's arguments)")
    used: set[str] = set()
    _placeholders(args, used)
    title_used = set(_PLACEHOLDER.findall(title))
    unknown = (used | title_used) - set(params) - {OPERATION_ID}
    if unknown:
        raise ActionConfigError(f"{name}: placeholders {sorted(unknown)} are not declared in params")
    limits = raw.get("limits", {}) or {}
    if not isinstance(limits, dict) or set(limits) - {"per_hour"}:
        raise ActionConfigError(f"{name}.limits: only per_hour is supported")
    per_hour = limits.get("per_hour")
    if per_hour is not None and (not isinstance(per_hour, int) or isinstance(per_hour, bool) or per_hour < 1):
        raise ActionConfigError(f"{name}.limits.per_hour: a positive integer")
    desc = raw.get("description", "")
    if not isinstance(desc, str):
        raise ActionConfigError(f"{name}.description: a string")
    return ActionDef(
        name=name, title=title.strip(), tool=tool, args=copy.deepcopy(args), params=params,
        risk=risk, auto_approve=auto, per_hour=per_hour, description=desc[:300], source=source,
    )


# --------------------------------------------------------------- params


def _unwrap(value: Any) -> Any:
    # Renderers send resolved values; tolerate a stray {"literalString": x}.
    if isinstance(value, dict) and len(value) == 1:
        (k, v), = value.items()
        if isinstance(k, str) and k.startswith("literal"):
            return v
    return value


def _coerce_scalar(action: str, key: str, typ: str, value: Any) -> Any:
    where = f"{key}"
    if typ == "string":
        if isinstance(value, bool) or not isinstance(value, (str, int, float)):
            raise ParamError(f"{where}: expected text")
        text = str(value)
        if len(text) > MAX_STRING:
            raise ParamError(f"{where}: longer than {MAX_STRING} characters")
        if _CTRL.search(text.replace("\n", "").replace("\t", "")):
            raise ParamError(f"{where}: control characters are not allowed")
        return text
    if typ == "integer":
        if isinstance(value, bool):
            raise ParamError(f"{where}: expected a whole number")
        if isinstance(value, int):
            return value
        if isinstance(value, float) and value.is_integer():
            return int(value)
        if isinstance(value, str) and re.fullmatch(r"-?[0-9]{1,15}", value.strip()):
            return int(value.strip())
        raise ParamError(f"{where}: expected a whole number")
    if typ == "number":
        if isinstance(value, bool):
            raise ParamError(f"{where}: expected a number")
        if isinstance(value, (int, float)):
            return value
        if isinstance(value, str) and re.fullmatch(r"-?[0-9]{1,15}(\.[0-9]{1,15})?", value.strip()):
            num = float(value.strip())
            return int(num) if num.is_integer() else num
        raise ParamError(f"{where}: expected a number")
    if typ == "boolean":
        if isinstance(value, bool):
            return value
        if isinstance(value, str) and value.strip().lower() in ("true", "false"):
            return value.strip().lower() == "true"
        raise ParamError(f"{where}: expected true or false")
    raise ParamError(f"{where}: unsupported type")


def _check_constraints(key: str, spec: dict[str, Any], value: Any) -> None:
    if "enum" in spec and value not in spec["enum"]:
        allowed = ", ".join(json.dumps(v) for v in spec["enum"][:20])
        raise ParamError(f"{key}: must be one of {allowed}")
    if isinstance(value, str):
        if "pattern" in spec and not re.fullmatch(spec["pattern"], value):
            raise ParamError(f"{key}: does not match {spec['pattern']}")
        if "minLength" in spec and len(value) < int(spec["minLength"]):
            raise ParamError(f"{key}: at least {spec['minLength']} characters")
        if "maxLength" in spec and len(value) > int(spec["maxLength"]):
            raise ParamError(f"{key}: at most {spec['maxLength']} characters")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in spec and value < spec["minimum"]:
            raise ParamError(f"{key}: at least {spec['minimum']}")
        if "maximum" in spec and value > spec["maximum"]:
            raise ParamError(f"{key}: at most {spec['maximum']}")


def coerce_param(action: str, key: str, spec: dict[str, Any], value: Any) -> Any:
    value = _unwrap(value)
    typ = spec.get("type", "string")
    if typ == "array":
        if isinstance(value, (str, int, float)) and not isinstance(value, bool):
            value = [value]  # a single-choice picker may send one value
        if not isinstance(value, list):
            raise ParamError(f"{key}: expected a list")
        if len(value) > MAX_ARRAY:
            raise ParamError(f"{key}: at most {MAX_ARRAY} items")
        items = spec.get("items", {"type": "string"})
        out = [_coerce_scalar(action, f"{key}[{i}]", items.get("type", "string"), _unwrap(v)) for i, v in enumerate(value)]
        for i, item in enumerate(out):
            _check_constraints(f"{key}[{i}]", items, item)
        if "minItems" in spec and len(out) < int(spec["minItems"]):
            raise ParamError(f"{key}: at least {spec['minItems']} items")
        if "maxItems" in spec and len(out) > int(spec["maxItems"]):
            raise ParamError(f"{key}: at most {spec['maxItems']} items")
        return out
    coerced = _coerce_scalar(action, key, typ, value)
    _check_constraints(key, spec, coerced)
    return coerced


_MARKERS = {"side_effect", "sideEffect", "read_only", "readOnly", "requires_confirmation", "requiresConfirmation"}


def validate_params(action: ActionDef, context: Any) -> dict[str, Any]:
    """Return typed params from a click context, or raise ParamError listing every problem."""
    ctx = context if isinstance(context, dict) else {}
    problems: list[str] = []
    out: dict[str, Any] = {}
    unknown = sorted(set(ctx) - set(action.params) - _MARKERS)
    if unknown:
        problems.append(f"unknown params {unknown}")
    for key, spec in action.params.items():
        if key in ctx and ctx[key] is not None and ctx[key] != "" and ctx[key] != []:
            try:
                out[key] = coerce_param(action.name, key, spec, ctx[key])
            except ParamError as exc:
                problems.append(str(exc))
        elif "default" in spec:
            out[key] = copy.deepcopy(spec["default"])
        elif spec.get("optional"):
            continue
        else:
            problems.append(f"{key}: required")
    if problems:
        raise ParamError("; ".join(problems))
    return out


# --------------------------------------------------------------- rendering


def _render(node: Any, values: dict[str, Any]) -> Any:
    if isinstance(node, str):
        whole = _WHOLE.match(node)
        if whole and whole.group(1) in values:
            return copy.deepcopy(values[whole.group(1)])  # keep the param's type
        return _PLACEHOLDER.sub(
            lambda m: _as_text(values[m.group(1)]) if m.group(1) in values else "", node
        )
    if isinstance(node, dict):
        return {k: _render(v, values) for k, v in node.items()}
    if isinstance(node, list):
        return [_render(v, values) for v in node]
    return copy.deepcopy(node)


def _as_text(value: Any) -> str:
    if isinstance(value, list):
        return ", ".join(_as_text(v) for v in value)
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def bind(action: ActionDef, context: Any, *, operation_id: str) -> Binding:
    """Validate a click against the definition and render the exact call."""
    params = validate_params(action, context)
    values = dict(params)
    values[OPERATION_ID] = operation_id
    args = _render(action.args, values)
    title = _render(action.title, values)
    return Binding(
        action=action.name,
        tool=action.tool,
        args=args,
        args_hash=call_hash(action.tool, args),
        title=_CTRL.sub(" ", str(title))[:300],
        risk=action.risk,
        auto_approve=action.auto_approve,
        params=params,
    )


# --------------------------------------------------------------- registry

_lock = threading.RLock()
_api_defs: dict[str, ActionDef] = {}
_api_errors: list[str] = []
_file_cache: dict[str, Any] = {"key": None, "defs": {}, "errors": [], "path": None}
_dir_override: Path | None = None


def set_actions_dir(path: Path | None) -> None:
    """Tests point the loader at a directory. Production uses the plugin data dir."""
    global _dir_override
    with _lock:
        _dir_override = path
        _file_cache.update({"key": None, "defs": {}, "errors": [], "path": None})


def _actions_dir() -> Path:
    if _dir_override is not None:
        return _dir_override
    from uirizz_plugin.store import _plugin_data_dir

    return _plugin_data_dir()


def _find_file() -> Path | None:
    base = _actions_dir()
    for name in FILE_NAMES:
        candidate = base / name
        if candidate.is_file():
            return candidate
    return None


def _parse_file(path: Path) -> tuple[dict[str, ActionDef], list[str]]:
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".json":
        doc = json.loads(text)
    else:
        import yaml  # PyYAML ships with a2ui-agent-sdk

        doc = yaml.safe_load(text)
    if doc is None:
        return {}, []
    if not isinstance(doc, dict) or not isinstance(doc.get("actions", {}), dict):
        return {}, [f"{path.name}: top level must be a mapping with an 'actions' mapping"]
    defs: dict[str, ActionDef] = {}
    errors: list[str] = []
    for name, raw in list((doc.get("actions") or {}).items())[:MAX_ACTIONS]:
        try:
            defs[name] = parse_definition(name, raw, source=path.name)
        except ActionConfigError as exc:
            errors.append(str(exc))
    return defs, errors


def _file_defs() -> tuple[dict[str, ActionDef], list[str], str | None]:
    with _lock:
        path = _find_file()
        if path is None:
            _file_cache.update({"key": None, "defs": {}, "errors": [], "path": None})
            return {}, [], None
        try:
            stat = path.stat()
            key = (str(path), stat.st_mtime_ns, stat.st_size)
        except OSError:
            return {}, [f"{path.name}: unreadable"], str(path)
        if _file_cache["key"] != key:
            try:
                defs, errors = _parse_file(path)
            except Exception as exc:  # noqa: BLE001 - a broken file disables file actions, nothing else
                defs, errors = {}, [f"{path.name}: {type(exc).__name__}: {str(exc)[:200]}"]
            _file_cache.update({"key": key, "defs": defs, "errors": errors, "path": str(path)})
        return dict(_file_cache["defs"]), list(_file_cache["errors"]), _file_cache["path"]


def register_action(name: str, **definition: Any) -> ActionDef:
    """Register a declared action from another Hermes plugin.

    Same keys as the YAML file: ``tool``, ``title``, ``args``, ``params``,
    ``risk``, ``auto_approve``, ``limits``, ``description``. A definition in
    the user's own actions file with the same name wins.
    """
    action = parse_definition(name, definition, source="api")
    with _lock:
        _api_defs[name] = action
    return action


def unregister_action(name: str) -> None:
    with _lock:
        _api_defs.pop(name, None)


def all_actions() -> dict[str, ActionDef]:
    file_defs, _errors, _path = _file_defs()
    with _lock:
        merged = dict(_api_defs)
    merged.update(file_defs)  # the user's file wins
    return merged


def get_action(name: Any) -> ActionDef | None:
    if not isinstance(name, str) or not _NAME.match(name):
        return None
    return all_actions().get(name)


def status_report() -> dict[str, Any]:
    """Loaded actions plus every config problem, for describe and the check command."""
    file_defs, errors, path = _file_defs()
    with _lock:
        api = dict(_api_defs)
    shadowed = sorted(set(api) & set(file_defs))
    merged = dict(api)
    merged.update(file_defs)
    return {
        "file": path,
        "searched": [str(_actions_dir() / n) for n in FILE_NAMES],
        "actions": [merged[k].public() for k in sorted(merged)],
        "errors": errors,
        "shadowed_api_actions": shadowed,
    }


def _events(node: Any, found: list[tuple[str, Any]]) -> None:
    if isinstance(node, dict):
        ev = node.get("event")
        if isinstance(ev, dict) and isinstance(ev.get("name"), str):
            found.append((ev["name"], ev.get("context")))
        for child in node.values():
            _events(child, found)
    elif isinstance(node, list):
        for child in node:
            _events(child, found)


def surface_warnings(messages: list[dict[str, Any]]) -> list[str]:
    """Problems with declared-action buttons on a surface, found at present time.

    Bound values (``{"path": ...}``) are checked when clicked; only unknown or
    missing keys and invalid literal values are reported here.
    """
    actions = all_actions()
    if not actions:
        return []
    found: list[tuple[str, Any]] = []
    _events(messages, found)
    out: list[str] = []
    for name, ctx in found:
        action = actions.get(name)
        if action is None:
            continue
        ctx = ctx if isinstance(ctx, dict) else {}
        unknown = sorted(set(ctx) - set(action.params) - _MARKERS)
        if unknown:
            out.append(f"{name}: unknown params {unknown}")
        for key, spec in action.params.items():
            if key not in ctx:
                if "default" not in spec and not spec.get("optional"):
                    out.append(f"{name}: missing param {key}")
                continue
            value = _unwrap(ctx[key])
            if isinstance(value, dict):
                continue  # a data binding, resolved at click time
            try:
                coerce_param(name, key, spec, value)
            except ParamError as exc:
                out.append(f"{name}: {exc}")
    return out[:20]


def main(argv: list[str] | None = None) -> int:
    """``python -m uirizz_plugin.bindings check [FILE]``: validate an actions file."""
    import sys

    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] != "check":
        print("usage: python -m uirizz_plugin.bindings check [actions.yaml|actions.json]")
        return 2
    if len(args) > 1:
        path = Path(args[1])
        defs, errors = _parse_file(path)
        report = {"file": str(path), "actions": [d.public() for d in defs.values()], "errors": errors}
    else:
        report = status_report()
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 1 if report["errors"] else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
