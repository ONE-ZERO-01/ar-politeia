"""Tests for the claim and finding derivation.

``research/claims.json`` and ``research/findings.json`` are derived from the run
artifacts so that a claim's evidence cannot be typed.  These tests pin the rule that
makes the derivation trustworthy: the plan's status stays the claim's status, and a
record that does not corroborate it stops the derivation instead of becoming a
quiet edit.
"""

from __future__ import annotations

import importlib.util
import json
import shutil
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parents[1]
MODULE_PATH = (
    REPO_ROOT / "research" / "src" / "experiments" / "prepare_cycle4_confirmation.py"
)
SPEC = importlib.util.spec_from_file_location("prepare_cycle4_confirmation", MODULE_PATH)
assert SPEC and SPEC.loader
promotion = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(promotion)


def _write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _job(root: Path, name: str, result: dict, *, keep: str = "record.json") -> Path:
    """One finished job: a record, a kept artifact, and a manifest citing it."""
    job_dir = root / "research" / "jobs" / name
    job_dir.mkdir(parents=True)
    _write_json(job_dir / "result.json", result)
    _write_json(job_dir / keep, {"artifact": name})
    _write_json(
        job_dir / "manifest.json",
        {
            "exit_code": 0,
            "artifacts": [
                promotion._tracked_evidence(job_dir, keep),
                promotion._tracked_evidence(job_dir, "result.json"),
            ],
        },
    )
    return job_dir


def _plan(root: Path, claims: list) -> None:
    _write_json(
        root / "research" / "plan.json",
        {"project_id": "ar-politeia", "cycle": 4, "claims": claims},
    )


def _claim(claim_id: str, status: str, experiments: list, **extra) -> dict:
    return {
        "id": claim_id,
        "status": status,
        "type": extra.pop("type", "core"),
        "text": f"{claim_id} statement",
        "falsification": f"{claim_id} falsification criterion",
        "experiments": experiments,
        **extra,
    }


def _derive(root: Path) -> dict:
    return promotion.derive_claims(root)


# ── derivation ──


def test_a_supported_claim_rests_on_the_record_the_plan_requires(tmp_path):
    _plan(
        tmp_path,
        [
            _claim(
                "C1",
                "supported",
                ["E1-A", "E1-B"],
                type="calibration",
            )
        ],
    )
    _job(tmp_path, "E1-A", {"pass": False, "gate_layers": {"invariants": False}})
    _job(tmp_path, "E1-B", {"pass": True, "gate_layers": {"invariants": True, "precision": True}})
    report = _derive(tmp_path)
    assert report["verdicts"] == {"C1": "supported"}

    findings = json.loads((tmp_path / "research" / "findings.json").read_text())
    finding = findings["findings"][0]
    # The decisive record is the last on the plan's list, which is the most
    # downstream; the earlier negative is carried as a named antecedent.
    assert finding["decisive_record"]["experiment"] == "E1-B"
    assert finding["decisive_record"]["standing"] == "completed"
    assert [item["experiment"] for item in finding["negative_antecedents"]] == ["E1-A"]
    assert finding["falsification_check"]["conditions"] == {
        "invariants": True,
        "precision": True,
    }
    assert finding["falsification_check"]["criterion"] == "C1 falsification criterion"
    # The failed run's artifacts are not evidence for a supported claim.
    assert "jobs/E1-A/record.json" not in finding["evidence"]
    assert "jobs/E1-B/record.json" in finding["evidence"]


def test_an_unrun_claim_is_evidenced_by_the_plan_that_records_it_as_unrun(tmp_path):
    _plan(tmp_path, [_claim("C4", "deferred", ["E3"], blocked_by="not yet authorized")])
    report = _derive(tmp_path)
    assert report["verdicts"] == {"C4": "inconclusive"}
    finding = json.loads((tmp_path / "research" / "findings.json").read_text())["findings"][0]
    assert finding["evidence"] == ["plan.json"]
    assert finding["blocked_reason"] == "not yet authorized"
    assert finding["falsification_check"]["conditions"] == {}
    assert "decisive_record" not in finding


def test_a_valid_null_is_recorded_as_not_supported(tmp_path):
    _plan(tmp_path, [_claim("C3", "refuted", ["E2"])])
    _job(tmp_path, "E2", {"analysis_gate_pass": True, "claim_supported": False})
    report = _derive(tmp_path)
    assert report["verdicts"] == {"C3": "not_supported"}


def test_the_ledger_carries_the_same_verdicts_as_the_findings(tmp_path):
    _plan(tmp_path, [_claim("C3", "supported", ["E2"])])
    _job(tmp_path, "E2", {"analysis_gate_pass": True, "claim_supported": True})
    _derive(tmp_path)
    claims = json.loads((tmp_path / "research" / "claims.json").read_text())
    findings = json.loads((tmp_path / "research" / "findings.json").read_text())
    assert [claim["claim_id"] for claim in claims["claims"]] == ["C3"]
    assert claims["claims"][0]["verdict"] == findings["findings"][0]["verdict"]
    assert claims["claims"][0]["evidence"] == findings["findings"][0]["evidence"]


# ── refusals ──


def test_a_record_that_contradicts_the_plan_status_is_refused(tmp_path):
    """The plan's status governs; the generator proves the records agree with it."""
    _plan(tmp_path, [_claim("C1", "supported", ["E1"])])
    _job(tmp_path, "E1", {"pass": False})
    with pytest.raises(RuntimeError, match="requires a decisive record with standing"):
        _derive(tmp_path)


def test_a_supported_claim_whose_run_was_a_valid_null_is_refused(tmp_path):
    _plan(tmp_path, [_claim("C2", "supported", ["E1"])])
    _job(tmp_path, "E1", {"analysis_gate_pass": True, "claim_supported": False})
    with pytest.raises(RuntimeError, match="E1 records 'passed_gate_valid_null'"):
        _derive(tmp_path)


def test_a_deferred_claim_whose_run_produced_a_verdict_is_refused(tmp_path):
    _plan(tmp_path, [_claim("C2", "deferred", ["E1"])])
    _job(tmp_path, "E1", {"analysis_gate_pass": True, "claim_supported": True})
    with pytest.raises(RuntimeError, match="requires a decisive record with standing"):
        _derive(tmp_path)


def test_an_unknown_plan_status_is_refused(tmp_path):
    _plan(tmp_path, [_claim("C1", "probably fine", ["E1"])])
    with pytest.raises(RuntimeError, match="no registered corroboration rule"):
        _derive(tmp_path)


def test_a_decisive_run_with_no_manifest_cannot_be_evidenced(tmp_path):
    _plan(tmp_path, [_claim("C1", "supported", ["E1"])])
    job_dir = tmp_path / "research" / "jobs" / "E1"
    job_dir.mkdir(parents=True)
    _write_json(job_dir / "result.json", {"pass": True})
    with pytest.raises(RuntimeError, match="has no manifest"):
        _derive(tmp_path)


def test_evidence_that_does_not_resolve_is_refused(tmp_path):
    _plan(tmp_path, [_claim("C1", "supported", ["E1"])])
    job_dir = _job(tmp_path, "E1", {"pass": True})
    _write_json(
        job_dir / "manifest.json",
        {
            "exit_code": 0,
            "artifacts": [{"path": "jobs/E1/gone.json", "sha256": "0" * 64, "size": 1}],
        },
    )
    with pytest.raises(RuntimeError, match="does not resolve under the run directory"):
        _derive(tmp_path)


def test_evidence_whose_hash_does_not_match_is_refused(tmp_path):
    _plan(tmp_path, [_claim("C1", "supported", ["E1"])])
    job_dir = _job(tmp_path, "E1", {"pass": True})
    _write_json(
        job_dir / "manifest.json",
        {
            "exit_code": 0,
            "artifacts": [
                {
                    "path": "jobs/E1/record.json",
                    "sha256": "0" * 64,
                    "size": (job_dir / "record.json").stat().st_size,
                }
            ],
        },
    )
    with pytest.raises(RuntimeError, match="unattested evidence"):
        _derive(tmp_path)


# ── the records actually in git ──


def _repo_tree(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    shutil.copytree(
        REPO_ROOT / "research",
        root / "research",
        ignore=shutil.ignore_patterns("workspace", "__pycache__"),
    )
    return root


def test_the_committed_ledger_is_what_the_derivation_produces(tmp_path):
    """Structural equality, so neither file can have been typed.

    ``generated_at`` is the one field that legitimately differs between two runs;
    everything a reader relies on has to match the committed bytes exactly.  If this
    fails, research/claims.json or research/findings.json has been edited by hand or
    the derivation changed, and the two are no longer the same thing.
    """
    root = _repo_tree(tmp_path)
    promotion.derive_claims(root)
    for name in ("claims.json", "findings.json"):
        committed = json.loads((REPO_ROOT / "research" / name).read_text())
        derived = json.loads((root / "research" / name).read_text())
        stamp = committed.pop("generated_at")
        derived.pop("generated_at")
        assert committed == derived, name
        assert isinstance(stamp, str) and "T" in stamp, name


def test_the_derivation_is_idempotent(tmp_path):
    root = _repo_tree(tmp_path)
    promotion.derive_claims(root)
    before = {
        name: (root / "research" / name).read_bytes()
        for name in ("claims.json", "findings.json")
    }
    promotion.derive_claims(root)
    for name, raw in before.items():
        # ``generated_at`` is the one field that moves; everything a reader relies
        # on must not.
        first = json.loads(raw)
        second = json.loads((root / "research" / name).read_text())
        first.pop("generated_at")
        second.pop("generated_at")
        assert first == second, name


def test_the_repository_ledger_covers_every_planned_claim():
    plan = json.loads((REPO_ROOT / "research" / "plan.json").read_text())
    ledger = json.loads((REPO_ROOT / "research" / "claims.json").read_text())
    findings = json.loads((REPO_ROOT / "research" / "findings.json").read_text())
    planned = {claim["id"] for claim in plan["claims"]}
    assert {claim["claim_id"] for claim in ledger["claims"]} == planned
    assert {finding["claim_id"] for finding in findings["findings"]} == planned
    for claim in ledger["claims"]:
        assert claim["evidence"], claim["claim_id"]
