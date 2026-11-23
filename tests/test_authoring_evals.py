"""Authoring eval harness: good fixtures admit, bad fixtures return expected codes."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_authoring_evals_pass_fixture_contract():
    from evals.harness import run_authoring_evals

    report = run_authoring_evals(ROOT / "evals" / "fixtures")
    assert report["ok"] is True
    assert report["good_passed"] >= 1
    assert report["bad_passed"] >= 2
    assert report["failed"] == []
