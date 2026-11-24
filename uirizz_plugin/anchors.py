"""Verify the action audit chain against external anchors (rizzstack.audit-anchor/1).

A collector outside uirizz records ``{log_id, seq, head_hash, ts, reason}`` every
100 entries of a log segment and when a segment rotates out (workflow
``contrib/rizzstack-observability/audit_anchor.py``). The hash chain alone only
catches clumsy edits: a rewrite that re-hashes every later entry still chains.
Anchors written elsewhere catch that, plus truncation and deleted anchors.

``log_id`` is the hash of a segment's first entry. uirizz keeps the current log
and one rotation backup, so anchors for older segments are reported as
unverifiable, never as passing checks.

    uirizz verify --anchors FILE [--log PATH]    # exit 0 ok, 1 failed or unreadable
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from uirizz_plugin import gate

SCHEMA = "rizzstack.audit-anchor/1"
_HEX64 = re.compile(r"^[0-9a-f]{64}$")


def _problem(kind: str, anchor: dict[str, Any] | None = None, detail: str = "") -> dict[str, Any]:
    out: dict[str, Any] = {"kind": kind}
    if anchor is not None:
        out.update({"log_id": str(anchor.get("log_id", ""))[:64], "seq": anchor.get("seq"),
                    "reason": anchor.get("reason")})
    if detail:
        out["detail"] = detail
    return out


def _well_formed(anchor: Any) -> bool:
    if not isinstance(anchor, dict) or anchor.get("schema") != SCHEMA:
        return False
    seq = anchor.get("seq")
    return (isinstance(seq, int) and not isinstance(seq, bool) and seq >= 1
            and all(isinstance(anchor.get(k), str) and _HEX64.match(anchor[k]) for k in ("log_id", "head_hash"))
            and anchor.get("reason") in ("interval", "rotation"))


def _chain_breaks(entries: list[dict[str, Any]]) -> int | None:
    """Index of the first entry that does not hash or link, or None."""
    prev = entries[0].get("prev") if entries else None
    for index, entry in enumerate(entries):
        body = {k: v for k, v in entry.items() if k != "hash"}
        if entry.get("prev") != prev or entry.get("seq") != index + 1:
            return index
        if gate._digest(str(entry.get("prev", "")), body) != entry.get("hash"):
            return index
        prev = entry.get("hash")
    return None


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    """Entries of a JSONL file; an unparseable line raises ValueError (fail closed)."""
    if not path.is_file():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            item = json.loads(line)
            if not isinstance(item, dict):
                raise ValueError("not an object")
            out.append(item)
    return out


def _segments(log: Path) -> tuple[dict[str, list[dict[str, Any]]], list[dict[str, Any]], list[dict[str, Any]]]:
    current = _read_jsonl(log)
    backup = _read_jsonl(log.with_name(log.name + ".1"))
    segs = {seg[0]["hash"]: seg for seg in (backup, current) if seg and isinstance(seg[0].get("hash"), str)}
    return segs, backup, current


def _check_one(anchor: dict[str, Any], seg: list[dict[str, Any]], backup: list[dict[str, Any]],
               current: list[dict[str, Any]]) -> dict[str, Any] | None:
    seq = anchor["seq"]
    if seq > len(seg):
        return _problem("truncated", anchor, f"segment ends at seq {len(seg)}")
    if seg[seq - 1].get("hash") != anchor["head_hash"]:
        return _problem("mismatch", anchor)
    if anchor["reason"] == "rotation":
        if seq != len(seg):
            return _problem("mismatch", anchor, "rotation anchor is not the segment's last entry")
        if seg is backup and current and current[0].get("prev") != anchor["head_hash"]:
            return _problem("mismatch", anchor, "current log does not continue the rotated segment")
    return None


def _anchor_gaps(anchors: list[dict[str, Any]], every: int) -> list[dict[str, Any]]:
    """Interval anchors missing below the highest one recorded for a segment."""
    by_log: dict[str, set[int]] = {}
    for a in anchors:
        if a["reason"] == "interval":
            by_log.setdefault(a["log_id"], set()).add(a["seq"])
    gaps = []
    for log_id, seqs in sorted(by_log.items()):
        for seq in range(every, max(seqs), every):
            if seq not in seqs:
                gaps.append(_problem("anchor_gap", {"log_id": log_id, "seq": seq, "reason": "interval"}))
    return gaps


def verify_anchors(anchors: list[Any], log: Path | None = None, every: int = 100) -> dict[str, Any]:
    """Check the audit log (and its backup) chain and every anchor. Pure read."""
    log = log or gate._log_path(create=False)
    segs, backup, current = _segments(log)
    problems = [_problem("chain_broken", detail=f"segment {lid[:12]} entry {i + 1}")
                for lid, seg in segs.items() if (i := _chain_breaks(seg)) is not None]
    good = [a for a in anchors if _well_formed(a)]
    problems += [_problem("malformed", a if isinstance(a, dict) else None) for a in anchors if not _well_formed(a)]
    checked = unverifiable = 0
    for anchor in good:
        seg = segs.get(anchor["log_id"])
        if seg is None:
            unverifiable += 1
            continue
        checked += 1
        found = _check_one(anchor, seg, backup, current)
        if found:
            problems.append(found)
    problems += _anchor_gaps(good, every)
    return {"ok": not problems, "checked": checked, "unverifiable": unverifiable,
            "entries": len(current), "problems": problems}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="uirizz", description="uirizz audit tools")
    sub = parser.add_subparsers(dest="cmd", required=True)
    verify = sub.add_parser("verify", help="verify the audit chain against anchors")
    verify.add_argument("--anchors", required=True, type=Path)
    verify.add_argument("--log", type=Path, default=None, help="audit log (default: the plugin's)")
    args = parser.parse_args(argv)
    try:
        result = verify_anchors(_read_jsonl(args.anchors), args.log)
    except (OSError, ValueError) as exc:
        result = {"ok": False, "problems": [_problem("unreadable", detail=type(exc).__name__)]}
    print(json.dumps(result, sort_keys=True))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
