"""Functional tests for foundation/audit.py."""
import hashlib
import json
import tempfile
from pathlib import Path

import pytest

from autoresearcher.foundation.audit import run


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
