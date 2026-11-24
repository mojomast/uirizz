"""`uirizz verify --anchors`: recompute the audit chain against external anchors.

BEST-PRACTICE item 3 (owner decision 2026-11-24 15:04 ET). A collector outside uirizz
writes rizzstack.audit-anchor/1 records {log_id, seq, head_hash, ts, reason} every 100
entries and on rotation (workflow contrib/rizzstack-observability/audit_anchor.py).
The verifier fails on any mismatch or gap: a re-hashed rewrite, a truncated log, a
deleted anchor, a rotation that does not continue its backup, or a broken chain.
"""
from __future__ import annotations

import json

import pytest

from uirizz_plugin import anchors, gate
from uirizz_plugin.store import set_store_dir

SCHEMA = "rizzstack.audit-anchor/1"


@pytest.fixture(autouse=True)
def _store(tmp_path):
    set_store_dir(tmp_path)
    yield
    set_store_dir(None)


def _fill(n):
    for i in range(n):
        gate._append({"type": "note", "action_id": f"act-{i:04d}", "note": "x"})
    return gate.read_entries()


def _anchors_for(entries, every=100):
    log_id = entries[0]["hash"]
    return [{"schema": SCHEMA, "log_id": log_id, "seq": e["seq"], "head_hash": e["hash"],
             "ts": "2026-11-24T20:00:00Z", "reason": "interval"} for e in entries if e["seq"] % every == 0]


def _rewrite(entries):
    """Re-hash a whole segment after an edit, as a careful forger would."""
    prev = entries[0]["prev"]
    for e in entries:
        e["prev"] = prev
        e["hash"] = gate._digest(prev, {k: v for k, v in e.items() if k != "hash"})
        prev = e["hash"]
    gate._log_path().write_text("".join(json.dumps(e, separators=(",", ":")) + "\n" for e in entries))


def test_matching_anchors_pass():
    entries = _fill(250)
    out = anchors.verify_anchors(_anchors_for(entries))
    assert out["ok"] is True and out["checked"] == 2 and out["problems"] == []


def test_rehashed_rewrite_is_caught_although_the_chain_itself_verifies():
    entries = _fill(250)
    recorded = _anchors_for(entries)
    entries[41]["note"] = "edited"
    _rewrite(entries)
    assert gate.verify_chain()["ok"] is True  # the chain alone can't tell
    out = anchors.verify_anchors(recorded)
    assert out["ok"] is False
    assert {p["kind"] for p in out["problems"]} == {"mismatch"}


def test_truncation_below_an_anchor_is_a_gap():
    entries = _fill(250)
    recorded = _anchors_for(entries)
    _rewrite(entries[:150])
    out = anchors.verify_anchors(recorded)
    assert out["ok"] is False
    assert [(p["kind"], p["seq"]) for p in out["problems"]] == [("truncated", 200)]


def test_a_deleted_anchor_is_a_gap():
    entries = _fill(350)
    recorded = [a for a in _anchors_for(entries) if a["seq"] != 200]
    out = anchors.verify_anchors(recorded)
    assert out["ok"] is False
    assert [(p["kind"], p["seq"]) for p in out["problems"]] == [("anchor_gap", 200)]


def test_broken_chain_fails_even_without_anchors():
    entries = _fill(5)
    entries[2]["note"] = "edited"
    gate._log_path().write_text("".join(json.dumps(e, separators=(",", ":")) + "\n" for e in entries))
    out = anchors.verify_anchors([])
    assert out["ok"] is False and out["problems"][0]["kind"] == "chain_broken"


def test_rotation_anchor_checks_the_backup_and_the_continuation():
    old = _fill(137)
    gate._rotate(gate._log_path())
    backup = old
    rotation = {"schema": SCHEMA, "log_id": backup[0]["hash"], "seq": 137, "head_hash": backup[-1]["hash"],
                "ts": "2026-11-24T20:00:00Z", "reason": "rotation"}
    good = _anchors_for(backup) + [rotation]
    assert anchors.verify_anchors(good)["ok"] is True
    forged = dict(rotation, head_hash="f" * 64)
    assert anchors.verify_anchors(_anchors_for(backup) + [forged])["ok"] is False


def test_anchors_for_rotated_away_segments_are_unverifiable_not_passing_silently():
    _fill(3)
    ghost = {"schema": SCHEMA, "log_id": "e" * 64, "seq": 100, "head_hash": "d" * 64,
             "ts": "2026-11-24T20:00:00Z", "reason": "interval"}
    out = anchors.verify_anchors([ghost])
    assert out["ok"] is True and out["checked"] == 0 and out["unverifiable"] == 1


def test_malformed_anchor_fails_closed():
    entries = _fill(100)
    bad = dict(_anchors_for(entries)[0], schema="rizzstack.audit-anchor/2")
    out = anchors.verify_anchors([bad])
    assert out["ok"] is False and out["problems"][0]["kind"] == "malformed"


def test_cli_verify_anchors(tmp_path, capsys):
    entries = _fill(120)
    path = tmp_path / "anchors.jsonl"
    path.write_text("".join(json.dumps(a) + "\n" for a in _anchors_for(entries)))
    assert anchors.main(["verify", "--anchors", str(path)]) == 0
    assert json.loads(capsys.readouterr().out)["ok"] is True
    path.write_text(path.read_text().replace(entries[99]["hash"], "0" * 64))
    assert anchors.main(["verify", "--anchors", str(path)]) == 1
    path.write_text("{not json\n")
    assert anchors.main(["verify", "--anchors", str(path)]) == 1
