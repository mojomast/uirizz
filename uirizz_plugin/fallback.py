"""Generate plain-text fallback copy from admitted A2UI messages. Never raises."""

from __future__ import annotations

import re
from typing import Any

MAX_CHARS = 1500
_CTRL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


def _resolve(value: Any, data: Any) -> Any:
    """Literal value, or the data-model value for {"@path": ...} / {"path": ...}."""
    if isinstance(value, dict):
        path = value.get("@path", value.get("path"))
        if isinstance(path, str):
            cur = data
            for part in [p for p in path.split("/") if p]:
                if isinstance(cur, dict) and part in cur:
                    cur = cur[part]
                elif isinstance(cur, list) and part.isdigit() and int(part) < len(cur):
                    cur = cur[int(part)]
                else:
                    return None
            return cur
        return None
    return value


def _literal(value: Any) -> str | None:
    """A literal scalar as text; bindings and structures are skipped."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (str, int, float)):
        text = _CTRL.sub("", str(value)).strip()
        return text or None
    return None


def _val(value: Any, data: Any) -> str | None:
    if isinstance(value, dict):
        value = _resolve(value, data)
    return _literal(value)


def _bound_len(value: Any, data: Any) -> int | None:
    if isinstance(value, list):
        return len(value)
    if isinstance(value, dict):
        resolved = _resolve(value, data)
        if isinstance(resolved, list):
            return len(resolved)
    return None


def _rows(value: Any, data: Any) -> list[Any]:
    if isinstance(value, dict):
        value = _resolve(value, data)
    return value if isinstance(value, list) else []


def _col_key_label(col: Any) -> tuple[str | None, str | None]:
    if isinstance(col, str):
        return col, col
    if isinstance(col, dict):
        key = col.get("key") or col.get("field") or col.get("id")
        label = col.get("label") or col.get("title") or col.get("header") or key
        return (str(key) if key else None, str(label) if label else None)
    return None, None


def _lines_for(comp: dict[str, Any], data: Any) -> list[str]:
    kind = comp.get("component")
    out: list[str] = []
    if kind == "Text":
        text = _literal(comp.get("text"))
        if text:
            text = re.sub(r"^\s*#+\s*", "", text).strip()
            if text:
                out.append(text)
    elif kind == "Metric":
        label, value, delta = (_val(comp.get(k), data) for k in ("label", "value", "delta"))
        if label or value:
            line = f"{label}: {value}" if label and value else (label or value or "")
            if delta:
                line += f" ({delta})"
            out.append(line)
    elif kind == "Badge":
        text = _val(comp.get("text"), data) or _val(comp.get("label"), data)
        if text:
            out.append(text)
    elif kind == "Callout":
        title, text = _val(comp.get("title"), data), _val(comp.get("text"), data)
        if title and text:
            out.append(f"{title}: {text}")
        elif title or text:
            out.append(title or text or "")
    elif kind == "Progress":
        label, value, mx = (_val(comp.get(k), data) for k in ("label", "value", "max"))
        if value is not None:
            out.append(f"{label + ': ' if label else ''}{value}/{mx if mx is not None else 100}")
    elif kind == "Chart":
        title = _val(comp.get("title"), data)
        if not title:
            series = comp.get("series")
            names: list[str] = []
            if isinstance(series, list):
                for s in series:
                    n = _val(s.get("label") or s.get("name") or s.get("key"), data) if isinstance(s, dict) else _literal(s)
                    if n:
                        names.append(n)
            x = _val(comp.get("x"), data)
            if x and names:
                title = f"{x} vs {', '.join(names)}"
            else:
                title = x or ", ".join(names) or None
        line = f"Chart: {title}" if title else "Chart"
        n = _bound_len(comp.get("data"), data)
        if n is None:
            n = _bound_len(comp.get("rows"), data)
        if n is not None:
            line += f", {n} rows"
        out.append(line)
    elif kind == "DataTable":
        title = _val(comp.get("title"), data)
        raw_rows = comp.get("rows", comp.get("data"))
        rows = _rows(raw_rows, data)
        line = f"Table: {title}" if title else "Table"
        n = _bound_len(raw_rows, data)
        if n is not None:
            line += f", {n} rows"
        out.append(line)
        cols = [_col_key_label(c) for c in (comp.get("columns") or []) if isinstance(comp.get("columns"), list)][:4]
        cols = [c for c in cols if c[0]]
        for row in rows[:5]:
            if isinstance(row, dict) and cols:
                cells = []
                for key, label in cols:
                    v = _literal(row.get(key))
                    if v is not None:
                        cells.append(f"{label}={v}")
                if cells:
                    out.append("; ".join(cells))
            elif isinstance(row, list):
                cells = [f"{c[1]}={v}" for c, v in zip(cols, (_literal(x) for x in row)) if v is not None]
                if cells:
                    out.append("; ".join(cells))
    elif kind == "KeyValueList":
        items = comp.get("items") or comp.get("entries") or comp.get("pairs")
        for item in _rows(items, data)[:10]:
            if isinstance(item, dict):
                k = _val(item.get("key", item.get("label")), data)
                v = _val(item.get("value"), data)
                if k and v is not None:
                    out.append(f"{k}: {v}")
    elif kind == "Timeline":
        items = comp.get("items") or comp.get("events")
        for item in _rows(items, data)[:10]:
            if isinstance(item, dict):
                d = _val(item.get("date", item.get("time")), data)
                t = _val(item.get("title", item.get("label")), data)
                text = " ".join(x for x in (d, t) if x)
                if text:
                    out.append(text)
    return out


def generate_fallback(messages: Any) -> str:
    """Plain text (max 1500 chars) for the surface in ``messages``. Never raises."""
    try:
        data: Any = {}
        comps: list[dict[str, Any]] = []
        for msg in messages if isinstance(messages, list) else []:
            if not isinstance(msg, dict):
                continue
            create = msg.get("createSurface")
            if isinstance(create, dict):
                if isinstance(create.get("dataModel"), (dict, list)):
                    data = create["dataModel"]
                comps += [c for c in (create.get("components") or []) if isinstance(c, dict)]
            update = msg.get("updateComponents")
            if isinstance(update, dict):
                comps += [c for c in (update.get("components") or []) if isinstance(c, dict)]
        lines: list[str] = []
        for comp in comps:
            try:
                lines += _lines_for(comp, data)
            except Exception:  # noqa: BLE001 - unknown shapes are skipped
                continue
        text = "\n".join(lines).strip()
        if len(text) > MAX_CHARS:
            text = text[: MAX_CHARS - 1].rstrip() + "…"
        return text
    except Exception:  # noqa: BLE001
        return ""
