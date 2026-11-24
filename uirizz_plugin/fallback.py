"""Generate plain-text fallback copy from admitted A2UI messages. Never raises."""

from __future__ import annotations

import logging
import re
from typing import Any

log = logging.getLogger(__name__)

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


def _text(comp: dict[str, Any], data: Any) -> list[str]:
    text = _literal(comp.get("text"))
    text = re.sub(r"^\s*#+\s*", "", text).strip() if text else ""
    return [text] if text else []


def _metric(comp: dict[str, Any], data: Any) -> list[str]:
    label, value, delta = (_val(comp.get(k), data) for k in ("label", "value", "delta"))
    if not (label or value):
        return []
    line = f"{label}: {value}" if label and value else (label or value or "")
    return [line + f" ({delta})" if delta else line]


def _badge(comp: dict[str, Any], data: Any) -> list[str]:
    text = _val(comp.get("text"), data) or _val(comp.get("label"), data)
    return [text] if text else []


def _callout(comp: dict[str, Any], data: Any) -> list[str]:
    title, text = _val(comp.get("title"), data), _val(comp.get("text"), data)
    if title and text:
        return [f"{title}: {text}"]
    return [title or text or ""] if (title or text) else []


def _progress(comp: dict[str, Any], data: Any) -> list[str]:
    label, value, mx = (_val(comp.get(k), data) for k in ("label", "value", "max"))
    if value is None:
        return []
    return [f"{label + ': ' if label else ''}{value}/{mx if mx is not None else 100}"]


def _series_name(s: Any, data: Any) -> str | None:
    if isinstance(s, dict):
        return _val(s.get("label") or s.get("name") or s.get("key"), data)
    return _literal(s)


def _chart_title(comp: dict[str, Any], data: Any) -> str | None:
    title = _val(comp.get("title"), data)
    if title:
        return title
    series = comp.get("series")
    names = [n for n in (_series_name(s, data) for s in series) if n] if isinstance(series, list) else []
    x = _val(comp.get("x"), data)
    if x and names:
        return f"{x} vs {', '.join(names)}"
    return x or ", ".join(names) or None


def _with_rows(line: str, n: int | None) -> str:
    return line if n is None else line + f", {n} rows"


def _chart(comp: dict[str, Any], data: Any) -> list[str]:
    title = _chart_title(comp, data)
    n = _bound_len(comp.get("data"), data)
    if n is None:
        n = _bound_len(comp.get("rows"), data)
    return [_with_rows(f"Chart: {title}" if title else "Chart", n)]


def _row_cells(row: Any, cols: list[tuple[str | None, str | None]]) -> list[str]:
    if isinstance(row, dict) and cols:
        pairs = [(label, _literal(row.get(key))) for key, label in cols]
    elif isinstance(row, list):
        pairs = [(c[1], v) for c, v in zip(cols, (_literal(x) for x in row))]
    else:
        return []
    return [f"{label}={v}" for label, v in pairs if v is not None]


def _datatable(comp: dict[str, Any], data: Any) -> list[str]:
    title = _val(comp.get("title"), data)
    raw_rows = comp.get("rows", comp.get("data"))
    out = [_with_rows(f"Table: {title}" if title else "Table", _bound_len(raw_rows, data))]
    columns = comp.get("columns")
    cols = [_col_key_label(c) for c in (columns or []) if isinstance(columns, list)][:4]
    cols = [c for c in cols if c[0]]
    for row in _rows(raw_rows, data)[:5]:
        cells = _row_cells(row, cols)
        if cells:
            out.append("; ".join(cells))
    return out


def _key_values(comp: dict[str, Any], data: Any) -> list[str]:
    out = []
    items = comp.get("items") or comp.get("entries") or comp.get("pairs")
    for item in (i for i in _rows(items, data)[:10] if isinstance(i, dict)):
        k = _val(item.get("key", item.get("label")), data)
        v = _val(item.get("value"), data)
        if k and v is not None:
            out.append(f"{k}: {v}")
    return out


def _timeline(comp: dict[str, Any], data: Any) -> list[str]:
    out = []
    items = comp.get("items") or comp.get("events")
    for item in (i for i in _rows(items, data)[:10] if isinstance(i, dict)):
        d = _val(item.get("date", item.get("time")), data)
        t = _val(item.get("title", item.get("label")), data)
        text = " ".join(x for x in (d, t) if x)
        if text:
            out.append(text)
    return out


_RENDERERS = {
    "Text": _text, "Metric": _metric, "Badge": _badge, "Callout": _callout,
    "Progress": _progress, "Chart": _chart, "DataTable": _datatable,
    "KeyValueList": _key_values, "Timeline": _timeline,
}


def _lines_for(comp: dict[str, Any], data: Any) -> list[str]:
    kind = comp.get("component")
    render = _RENDERERS.get(kind) if isinstance(kind, str) else None
    return render(comp, data) if render else []


def _collect(messages: Any) -> tuple[Any, list[dict[str, Any]]]:
    """(data model, components) from createSurface/updateComponents envelopes, in order."""
    data: Any = {}
    comps: list[dict[str, Any]] = []
    for msg in (m for m in (messages if isinstance(messages, list) else []) if isinstance(m, dict)):
        create = msg.get("createSurface")
        if isinstance(create, dict):
            if isinstance(create.get("dataModel"), (dict, list)):
                data = create["dataModel"]
            comps += [c for c in (create.get("components") or []) if isinstance(c, dict)]
        update = msg.get("updateComponents")
        if isinstance(update, dict):
            comps += [c for c in (update.get("components") or []) if isinstance(c, dict)]
    return data, comps


def _safe_lines(comp: dict[str, Any], data: Any) -> list[str]:
    """One component's lines; an unrenderable component is skipped and logged."""
    try:
        return _lines_for(comp, data)
    except Exception as exc:  # noqa: BLE001 - fallback copy must never raise
        log.warning("uirizz fallback skipped component %r (%s): %s",
                    _CTRL.sub("", str(comp.get("id")))[:64],
                    _CTRL.sub("", str(comp.get("component")))[:32], type(exc).__name__)
        return []


def generate_fallback(messages: Any) -> str:
    """Plain text (max 1500 chars) for the surface in ``messages``. Never raises."""
    try:
        data, comps = _collect(messages)
        lines = [line for comp in comps for line in _safe_lines(comp, data)]
        text = "\n".join(lines).strip()
        if len(text) > MAX_CHARS:
            text = text[: MAX_CHARS - 1].rstrip() + "…"
        return text
    except Exception:  # noqa: BLE001 - fallback copy must never raise
        return ""
