"""Functional tests for foundation/audit.py."""
import hashlib
import json
import tempfile
from pathlib import Path

import pytest

from autoresearcher.foundation.audit import main, run


def _write(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, (dict, list)):
        text = json.dumps(data, ensure_ascii=False, indent=2)
    else:
        text = str(data)
    path.write_text(text, encoding="utf-8")


def _sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _write_result(run_dir: Path, experiment_id: str, data) -> Path:
    result_path = run_dir / "jobs" / experiment_id / "result.json"
    _write(result_path, data)
    content = result_path.read_text(encoding="utf-8")
    _write(
        run_dir / "jobs" / experiment_id / "manifest.json",
        {
            "exit_code": 0,
            "artifacts": [
                {
                    "path": f"jobs/{experiment_id}/result.json",
                    "size": result_path.stat().st_size,
                    "sha256": _sha256(content),
                }
            ],
        },
    )
    return result_path


@pytest.fixture()
def run_dir():
    with tempfile.TemporaryDirectory() as td:
        yield Path(td)


def test_all_passes(run_dir):
    evidence1 = _write_result(run_dir, "E1", {"loss": 0.25, "acc": 0.95})
    evidence_content = evidence1.read_text(encoding="utf-8")

    claims = {
        "claims": [
            {"claim_id": "C1", "text": "Model achieves >90% accuracy",
             "evidence": ["jobs/E1/result.json"]},
        ]
    }
    _write(run_dir / "claims.json", claims)

    result = run(run_dir, run_dir / "claims.json")
    assert result["all_checks_passed"] is True
    assert result["total_claims"] == 1
    assert result["total_evidence_files"] == 1
    claim = result["claims"][0]
    assert claim["evidence"][0]["valid"] is True
    assert claim["evidence"][0]["sha256"] == _sha256(evidence_content)


def test_evidence_missing(run_dir):
    claims = {
        "claims": [
            {"claim_id": "C1", "text": "Claim with missing evidence",
             "evidence": ["jobs/E99/result.json"]},
        ]
    }
    _write(run_dir / "claims.json", claims)
    result = run(run_dir, run_dir / "claims.json")
    assert result["all_checks_passed"] is False
    assert any("missing" in (issue.lower() if issue else "") for issue in result["failed_checks"])


def test_evidence_empty(run_dir):
    empty_file = run_dir / "jobs" / "E1" / "result.json"
    _write(empty_file, "")
    claims = {
        "claims": [
            {"claim_id": "C1", "text": "Claim with empty evidence",
             "evidence": ["jobs/E1/result.json"]},
        ]
    }
    _write(run_dir / "claims.json", claims)
    result = run(run_dir, run_dir / "claims.json")
    assert result["all_checks_passed"] is False
    failed_text = json.dumps(result["failed_checks"])
    assert "empty" in failed_text.lower()


def test_evidence_has_nan(run_dir):
    _write(run_dir / "jobs" / "E1" / "result.json", {"loss": float("nan")})
    claims = {
        "claims": [
            {"claim_id": "C1", "text": "Claim with NaN evidence",
             "evidence": ["jobs/E1/result.json"]},
        ]
    }
    _write(run_dir / "claims.json", claims)
    result = run(run_dir, run_dir / "claims.json")
    assert result["all_checks_passed"] is False
    failed_text = json.dumps(result["failed_checks"])
    assert "nan" in failed_text.lower()


def test_manifest_nonzero_exit(run_dir):
    _write(run_dir / "jobs" / "E1" / "manifest.json", {"exit_code": 1})
    result = run(run_dir)
    assert result["all_checks_passed"] is False
    assert any("exit_code" in issue for issue in result["failed_checks"])


def test_jobs_without_manifest_reports_issue(run_dir):
    _write(run_dir / "jobs" / "E1" / "result.json", {"loss": 0.25})
    _write(run_dir / "claims.json", {"claims": []})
    result = run(run_dir, run_dir / "claims.json")
    assert result["all_checks_passed"] is False
    assert any("manifest.json" in issue for issue in result["failed_checks"])


def test_multiple_claims(run_dir):
    _write_result(run_dir, "E1", {"loss": 0.25})
    _write_result(run_dir, "E2", {"loss": 0.15})

    claims = {
        "claims": [
            {"claim_id": "C1", "text": "E1 result is valid",
             "evidence": ["jobs/E1/result.json"]},
            {"claim_id": "C2", "text": "E2 result is valid",
             "evidence": ["jobs/E2/result.json"]},
        ]
    }
    _write(run_dir / "claims.json", claims)
    result = run(run_dir, run_dir / "claims.json")
    assert result["all_checks_passed"] is True
    assert result["total_claims"] == 2
    assert result["total_evidence_files"] == 2


def test_no_claims_file(run_dir):
    result = run(run_dir, None)
    assert result["all_checks_passed"] is False
    assert any("missing" in issue.lower() for issue in result["failed_checks"])


def test_checksum_mismatch(run_dir):
    _write(run_dir / "jobs" / "E1" / "result.json", {"loss": 0.25})
    claims = {
        "claims": [
            {"claim_id": "C1", "text": "Claim with wrong checksum",
             "evidence": ["jobs/E1/result.json"],
             "sha256": "deadbeef"},
        ]
    }
    _write(run_dir / "claims.json", claims)
    result = run(run_dir, run_dir / "claims.json")
    assert result["all_checks_passed"] is False
    assert any("checksum" in issue.lower() for issue in result["failed_checks"])


def test_absolute_evidence_path_is_rejected(run_dir):
    claims = {
        "claims": [
            {
                "claim_id": "C1",
                "text": "External evidence must not enter the bundle",
                "evidence": ["/etc/hosts"],
            }
        ]
    }
    _write(run_dir / "claims.json", claims)
    result = run(run_dir, run_dir / "claims.json")
    assert result["all_checks_passed"] is False
    assert any("absolute" in issue.lower() for issue in result["failed_checks"])


def test_plan_claim_without_finding_is_rejected(run_dir):
    _write(run_dir / "plan.json", {"claims": [{"id": "C1"}, {"id": "C2"}]})
    _write(
        run_dir / "findings.json",
        {"findings": [{"claim_id": "C1", "verdict": "supported"}]},
    )
    _write(run_dir / "claims.json", {"claims": []})
    result = run(run_dir, run_dir / "claims.json")
    assert result["all_checks_passed"] is False
    assert any("no finding" in issue.lower() for issue in result["failed_checks"])


# ── adjudicated failures ──
#
# A job that failed and was superseded is not the same as a job that failed, and
# the gate's default is to reject the latter.  An exemption has to be earned by an
# explicit record, and each of these tests removes one of the things that earns it.


def _superseded_fixture(run_dir: Path, **overrides) -> None:
    _write_result(run_dir, "V1-OLD", {"pass": False})
    _write_result(run_dir, "V1B-NEW", {"pass": True})
    _write(run_dir / "v1b-design.md", "the design that superseded V1\n")
    manifest_path = run_dir / "jobs" / "V1-OLD" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["exit_code"] = 1
    adjudication = {
        "verdict": "superseded",
        "superseded_by": ["V1B-NEW"],
        "design": "v1b-design.md",
        "reason": "the frozen storage-order bound was measured at the wrong tolerance",
    }
    adjudication.update(overrides)
    if adjudication:
        manifest["adjudicated"] = adjudication
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def test_a_superseded_failure_is_admitted_and_reported(run_dir):
    _superseded_fixture(run_dir)
    result = run(run_dir)
    assert not any("exit_code" in issue for issue in result["failed_checks"])
    assert result["adjudicated_failures"] == [
        {
            "job": "V1-OLD",
            "exit_code": 1,
            "verdict": "superseded",
            "superseded_by": ["V1B-NEW"],
            "design": "v1b-design.md",
            "reason": "the frozen storage-order bound was measured at the wrong tolerance",
        }
    ]


def test_a_failure_with_no_adjudication_still_fails_the_gate(run_dir):
    _write_result(run_dir, "V1-OLD", {"pass": False})
    manifest_path = run_dir / "jobs" / "V1-OLD" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["exit_code"] = 1
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    result = run(run_dir)
    assert result["all_checks_passed"] is False
    assert any("exit_code=1" in issue for issue in result["failed_checks"])
    assert result["adjudicated_failures"] == []


@pytest.mark.parametrize(
    "overrides, fragment",
    [
        ({"verdict": "because i said so"}, "not one of"),
        ({"superseded_by": []}, "non-empty list"),
        ({"superseded_by": "V1B-NEW"}, "non-empty list"),
        ({"superseded_by": ["NO-SUCH-JOB"]}, "has no manifest.json"),
        ({"design": "no-such-design.md"}, "does not exist"),
        ({"design": "../outside.md"}, "escapes the run directory"),
        ({"reason": "   "}, "is empty"),
    ],
)
def test_an_adjudication_that_does_not_hold_is_an_issue(run_dir, overrides, fragment):
    _superseded_fixture(run_dir, **overrides)
    result = run(run_dir)
    assert result["all_checks_passed"] is False
    assert any(fragment in issue for issue in result["failed_checks"]), result["failed_checks"]
    assert result["adjudicated_failures"] == []


def test_a_superseding_run_that_itself_failed_supersedes_nothing(run_dir):
    _superseded_fixture(run_dir)
    _write_result(run_dir, "V1B-NEW", {"pass": False})
    manifest_path = run_dir / "jobs" / "V1B-NEW" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["exit_code"] = 2
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    result = run(run_dir)
    assert any("supersedes nothing" in issue for issue in result["failed_checks"])


def test_an_absent_adjudication_key_is_not_an_exemption(run_dir):
    _write_result(run_dir, "V1-OLD", {"pass": False})
    manifest_path = run_dir / "jobs" / "V1-OLD" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["exit_code"] = 1
    manifest["adjudicated"] = None
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    result = run(run_dir)
    assert any("is not an object" in issue for issue in result["failed_checks"])


def test_a_job_with_a_result_but_no_manifest_is_named_not_ignored(run_dir):
    """Reported, not failed: manufacturing a manifest now would invent an exit code."""
    _write(run_dir / "jobs" / "OLD-JOB" / "result.json", {"pass": False})
    _write_result(run_dir, "E1", {"pass": True})
    _write(run_dir / "claims.json", {"claims": []})
    result = run(run_dir, run_dir / "claims.json")
    assert result["jobs_without_manifest"] == ["OLD-JOB"]
    assert result["all_checks_passed"] is True


# ── the claims file and findings.json must describe the same claims ──
#
# They are written at different times by different steps, so a disagreement means
# one of them is stale and the bundle would cite a claim the record does not make.


def _agreement_fixture(run_dir: Path, *, claim: dict, finding: dict) -> None:
    _write_result(run_dir, "E1", {"loss": 0.25})
    _write(run_dir / "claims.json", {"claims": [claim]})
    _write(run_dir / "findings.json", {"findings": [finding]})


def test_claims_and_findings_that_agree_pass(run_dir):
    _agreement_fixture(
        run_dir,
        claim={"claim_id": "C1", "verdict": "supported", "evidence": ["jobs/E1/result.json"]},
        finding={"claim_id": "C1", "verdict": "supported", "evidence": ["jobs/E1/result.json"]},
    )
    result = run(run_dir, run_dir / "claims.json")
    assert result["all_checks_passed"] is True, result["failed_checks"]


def test_a_disagreeing_verdict_is_an_issue(run_dir):
    _agreement_fixture(
        run_dir,
        claim={"claim_id": "C1", "verdict": "supported", "evidence": ["jobs/E1/result.json"]},
        finding={"claim_id": "C1", "verdict": "inconclusive", "evidence": ["jobs/E1/result.json"]},
    )
    result = run(run_dir, run_dir / "claims.json")
    assert any("records verdict" in issue for issue in result["failed_checks"])


def test_differing_evidence_is_an_issue(run_dir):
    _agreement_fixture(
        run_dir,
        claim={"claim_id": "C1", "evidence": ["jobs/E1/result.json", "plan.json"]},
        finding={"claim_id": "C1", "evidence": ["jobs/E1/result.json"]},
    )
    result = run(run_dir, run_dir / "claims.json")
    assert any("different evidence" in issue for issue in result["failed_checks"])


def test_a_paper_claim_with_no_verdict_is_not_failed_for_lacking_one(run_dir):
    """A journal claims file may legitimately state a claim without a verdict."""
    _agreement_fixture(
        run_dir,
        claim={"claim_id": "C1", "evidence": ["jobs/E1/result.json"]},
        finding={"claim_id": "C1", "verdict": "supported", "evidence": ["jobs/E1/result.json"]},
    )
    result = run(run_dir, run_dir / "claims.json")
    assert result["all_checks_passed"] is True, result["failed_checks"]


# ── the command line ──


def test_the_documented_bare_command_audits_the_run_directory(tmp_path, monkeypatch):
    """The gate's own docs have always shown the bare command; it has to work."""
    run_dir = tmp_path / "research"
    _write_result(run_dir, "E1", {"loss": 0.25})
    _write(
        run_dir / "claims.json",
        {"claims": [{"claim_id": "C1", "evidence": ["jobs/E1/result.json"]}]},
    )
    monkeypatch.chdir(tmp_path)
    main([])  # exits with SystemExit(1) on failure, so no exception means it passed


def test_the_bundle_records_what_it_audited(tmp_path):
    """A bundle that does not say what it covers can be mistaken for another."""
    run_dir = tmp_path / "research"
    _write_result(run_dir, "E1", {"loss": 0.25})
    _write(
        run_dir / "claims.json",
        {"claims": [{"claim_id": "C1", "evidence": ["jobs/E1/result.json"]}]},
    )
    result = run(run_dir, run_dir / "claims.json")
    assert result["run_dir"] == str(run_dir.resolve())
    assert result["claims_file"] == str((run_dir / "claims.json").resolve())
