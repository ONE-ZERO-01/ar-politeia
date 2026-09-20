"""The pre-submission gate, run against the committed repository.

``audit`` is the mandatory pre-submission gate, and until 2026-09-20 it had never
passed on a Cycle 4 record: 70 issues, 66 of them a single path convention.  That is
the failure mode this file guards against -- not a gate that is wrong, but a gate
nobody noticed could not be satisfied.  It runs the gate end to end on what is in
git, and it also pins the two residuals the gate reports, so they stay visible
instead of quietly becoming part of the background.
"""

from __future__ import annotations

import json
from pathlib import Path

from autoresearcher.foundation import audit

REPO_ROOT = Path(__file__).parents[1]
RUN_DIR = REPO_ROOT / "research"
CLAIMS_FILE = RUN_DIR / "claims.json"


def test_the_audit_gate_passes_on_the_committed_repository():
    result = audit.run(RUN_DIR, CLAIMS_FILE)
    assert result["failed_checks"] == []
    assert result["all_checks_passed"] is True
    assert result["total_claims"] == 4
    assert result["total_evidence_files"] > 0


def test_the_gate_reports_the_adjudicated_failure_it_admitted():
    """An exemption that is not visible in the bundle is an exemption nobody audits."""
    result = audit.run(RUN_DIR, CLAIMS_FILE)
    assert [entry["job"] for entry in result["adjudicated_failures"]] == [
        "V1-NONFLAT-CALIBRATION-C4"
    ]
    adjudication = result["adjudicated_failures"][0]
    assert adjudication["exit_code"] == 1
    assert adjudication["verdict"] == "superseded"
    assert (RUN_DIR / adjudication["design"]).is_file()
    assert adjudication["reason"].strip()


def test_the_gate_names_the_jobs_it_cannot_see():
    """Six jobs record a result and no manifest, so the exit-code check misses them.

    Reported rather than failed: all six predate the manifest convention, and
    manufacturing manifests now would mean inventing their exit codes -- the one
    thing this gate exists to prevent.  The list is pinned so it cannot grow
    unnoticed.
    """
    result = audit.run(RUN_DIR, CLAIMS_FILE)
    assert result["jobs_without_manifest"] == [
        "B0-DYNAMICS-PILOT",
        "B0-DYNAMICS-PILOT-C2",
        "E0-NUMERICS",
        "E0-NUMERICS-C2",
        "E3-ROBUSTNESS-HOLDOUT",
        "V0-SIMULATOR-TESTS-C4",
    ]
