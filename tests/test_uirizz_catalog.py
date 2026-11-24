"""The uirizz/1 catalog: Express compile, admission, caps, and describe."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from uirizz_plugin import store
from uirizz_plugin.catalog import BASIC_CATALOG_ID, UIRIZZ_CATALOG_ID
from uirizz_plugin.tools import handle_a2ui_render, parse_tool_result
from uirizz_plugin.validate import AdmissionError, admit_jsonl

pytest.importorskip("a2ui", reason="a2ui-agent-sdk is required for Express")

ROOT = Path(__file__).resolve().parents[1]

SOURCE = """$/sales = [{month: "Jan", revenue: 120, cost: 80}, {month: "Feb", revenue: 150, cost: 85}]
$/kv = [{key: "Owner", value: "Kyle"}]
$/ev = [{date: "2026-11-20", title: "Deploy v24", status: "good"}]
$/spark = [1, 3, 2, 5]
root = Column([Row([Metric("Revenue", "$150k", "+4%", "up", "good", $/spark, weight=1), Progress(40, 100, "Migration", weight=1), Badge("Healthy", "good")]), Chart("line", $/sales, "month", [{field: "revenue", label: "Revenue"}], title="Revenue", format="currency", currency="USD", selection=$/ui/picked, action=Event("drill", {month: $/ui/picked, read_only: true})), DataTable($/sales, [{field: "month", label: "Month"}, {field: "revenue", label: "Revenue", align: "end", format: "number"}], pageSize=5), Callout("Costs rose 6%.", "warning", "Heads up"), KeyValueList($/kv), Timeline($/ev), CodeBlock("print(1)", "python")])
"""


@pytest.fixture(autouse=True)
def _store(tmp_path):
    store.set_store_dir(tmp_path / "surfaces")
    yield
    store.set_store_dir(None)


def _call(**args):
    return parse_tool_result(handle_a2ui_render(args))


def _jsonl(catalog_id, components, data=None):
    lines = [{"version": "1.0", "createSurface": {"surfaceId": "s", "catalogId": catalog_id}}]
    lines.append({"version": "1.0", "updateComponents": {"surfaceId": "s", "components": components}})
    if data is not None:
        lines.append({"version": "1.0", "updateDataModel": {"surfaceId": "s", "path": "/", "value": data}})
    return "\n".join(json.dumps(x) for x in lines)


def _chart(data):
    return [
        {"id": "root", "component": "Column", "children": ["c"]},
        {"id": "c", "component": "Chart", "type": "line", "data": data, "x": "m", "series": [{"field": "v"}]},
    ]


def test_present_all_nine_components():
    out = _call(op="present", express=SOURCE, fallback_text="dashboard")
    assert out["ok"], out
    record = store.get_surface(out["surface_id"])
    create = next(m["createSurface"] for m in record["messages"] if "createSurface" in m)
    assert create["catalogId"] == UIRIZZ_CATALOG_ID
    types = {c["component"] for c in create.get("components", [])}
    types |= {c["component"] for m in record["messages"] if "updateComponents" in m for c in m["updateComponents"]["components"]}
    assert {"Chart", "DataTable", "Metric", "Progress", "Badge", "Callout", "KeyValueList", "Timeline", "CodeBlock"} <= types


def test_bad_enum_reports_allowed_values():
    out = _call(op="present", express='root = Chart("radar", $/d, "m", [{field: "v"}])', fallback_text="x")
    assert not out["ok"] and out["code"] == "express_error"
    assert "line" in out["error"] and "donut" in out["error"]


def test_chart_rejected_under_basic_admitted_under_uirizz():
    with pytest.raises(AdmissionError) as exc:
        admit_jsonl(_jsonl(BASIC_CATALOG_ID, _chart("/d")))
    assert exc.value.code == "unknown_component"
    admitted = admit_jsonl(_jsonl(UIRIZZ_CATALOG_ID, _chart({"path": "/d"})))
    assert admitted["component_count"] == 2


def test_unknown_catalog_rejected():
    with pytest.raises(AdmissionError):
        admit_jsonl(_jsonl("https://example.com/other.json", _chart({"path": "/d"})))


def test_literal_501_rows_rejected_500_ok():
    rows = lambda n: [{"m": i, "v": i} for i in range(n)]
    admit_jsonl(_jsonl(UIRIZZ_CATALOG_ID, _chart(rows(500))))
    with pytest.raises(AdmissionError) as exc:
        admit_jsonl(_jsonl(UIRIZZ_CATALOG_ID, _chart(rows(501))))
    assert exc.value.code == "oversize" and exc.value.fix


def test_data_model_array_cap():
    comps = [{"id": "root", "component": "Text", "text": "x"}]
    admit_jsonl(_jsonl(UIRIZZ_CATALOG_ID, comps, {"a": list(range(5000))}))
    with pytest.raises(AdmissionError) as exc:
        admit_jsonl(_jsonl(UIRIZZ_CATALOG_ID, comps, {"a": {"b": list(range(5001))}}))
    assert exc.value.code == "oversize"


def test_video_still_rejected_under_uirizz():
    comps = [{"id": "root", "component": "Video", "url": "https://example.com/a.mp4"}]
    with pytest.raises(AdmissionError):
        admit_jsonl(_jsonl(UIRIZZ_CATALOG_ID, comps))


def test_data_only_update_on_chart_surface():
    first = _call(op="present", express=SOURCE, fallback_text="dashboard")
    assert first["ok"], first
    out = _call(
        op="update",
        surface_id=first["surface_id"],
        express='$/sales = [{month: "Mar", revenue: 200, cost: 90}]',
    )
    assert out["ok"], out
    record = store.get_surface(first["surface_id"])
    last = record["messages"][-1]
    assert "updateDataModel" in last and last["updateDataModel"]["path"] == "/sales"
    assert record["revision"] == 2


def test_build_catalog_is_current():
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "build_catalog.py"), "--check"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_describe_components_topic_does_not_crash():
    out = _call(op="describe", topic="components")
    assert out["ok"] or out["code"] == "not_found"
    base = _call(op="describe")
    assert base["uirizz_catalog_id"] == UIRIZZ_CATALOG_ID
    assert "Chart" in base["uirizz_components"] and "Text" in base["components"]
