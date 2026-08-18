"""Tests for the deterministic per-cycle evidence existence gate."""

import json
from pathlib import Path

from autoresearcher.foundation.evidence_check import main, run_check


def _write_cycle_output(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def _make_run_dir(tmp_path: Path) -> Path:
    run_dir = tmp_path / "research"
    (run_dir / "jobs").mkdir(parents=True)
    (run_dir / "jobs" / "result.json").write_text(
        '{"ok": true}', encoding="utf-8"
    )
    return run_dir


def test_blocks_fabricated_evidence_path(tmp_path):
    run_dir = _make_run_dir(tmp_path)
    cycle_output = run_dir / "cycle-output.json"
    _write_cycle_output(
        cycle_output,
        {
            "claims": [
                {
                    "claim_id": "C1",
                    "verdict": "supported",
                    "evidence": ["jobs/result.json"],
                },
                {
                    "claim_id": "C2",
                    "verdict": "contradicted",
                    "evidence": ["jobs/does-not-exist.json"],
                },
            ],
            "evidence_paths": ["jobs/result.json"],
        },
    )
    report = run_check(cycle_output, run_dir)
    assert not report["pass"]
    assert any("does-not-exist.json" in item for item in report["problems"])


def test_passes_run_dir_and_workspace_prefixed_paths(tmp_path):
    run_dir = _make_run_dir(tmp_path)
    cycle_output = run_dir / "cycle-output.json"
    _write_cycle_output(
        cycle_output,
        {
            "claims": [
                {
                    "claim_id": "C1",
                    "verdict": "supported",
                    # run-dir relative (audit convention)
                    "evidence": ["jobs/result.json"],
                },
                {
                    "claim_id": "C2",
                    "verdict": "supported",
                    # workspace-prefixed variant must also resolve
                    "evidence": ["research/jobs/result.json"],
                },
            ],
            "evidence_paths": [],
        },
    )
    report = run_check(cycle_output, run_dir)
    assert report["pass"], report["problems"]


def test_verdict_without_evidence_is_blocked(tmp_path):
    run_dir = _make_run_dir(tmp_path)
    cycle_output = run_dir / "cycle-output.json"
    _write_cycle_output(
        cycle_output,
        {
            "claims": [
                {"claim_id": "C1", "verdict": "supported", "evidence": []},
                {"claim_id": "C2", "verdict": "inconclusive", "evidence": []},
            ],
            "evidence_paths": [],
        },
    )
    report = run_check(cycle_output, run_dir)
    assert not report["pass"]
    problems = " ".join(report["problems"])
    assert "C1" in problems
    assert "C2" not in problems  # inconclusive may lack evidence


def test_rejects_absolute_and_escaping_paths(tmp_path):
    run_dir = _make_run_dir(tmp_path)
    outside = tmp_path.parent / "outside.json"
    cycle_output = run_dir / "cycle-output.json"
    _write_cycle_output(
        cycle_output,
        {
            "claims": [],
            "evidence_paths": [str(outside), "../../etc/hosts"],
        },
    )
    report = run_check(cycle_output, run_dir)
    assert not report["pass"]
    assert len(report["problems"]) == 2


def test_missing_cycle_output_blocked(tmp_path):
    run_dir = _make_run_dir(tmp_path)
    cycle_output = run_dir / "cycle-output.json"  # 文件不存在
    report = run_check(cycle_output, run_dir)
    assert not report["pass"]
    assert any("unreadable" in p for p in report["problems"])


def test_invalid_json_cycle_output_blocked(tmp_path):
    run_dir = _make_run_dir(tmp_path)
    cycle_output = run_dir / "cycle-output.json"
    cycle_output.write_text("{ not valid json", encoding="utf-8")
    report = run_check(cycle_output, run_dir)
    assert not report["pass"]
    assert any("unreadable" in p for p in report["problems"])


def test_main_exit_codes_and_output_file(tmp_path):
    run_dir = _make_run_dir(tmp_path)
    cycle_output = run_dir / "cycle-output.json"
    _write_cycle_output(
        cycle_output,
        {
            "claims": [
                {
                    "claim_id": "C1",
                    "verdict": "supported",
                    "evidence": ["jobs/result.json"],
                }
            ],
            "evidence_paths": ["jobs/result.json"],
        },
    )
    output = tmp_path / "report.json"
    code = main(
        [
            "--cycle-output", str(cycle_output),
            "--run-dir", str(run_dir),
            "--output", str(output),
        ]
    )
    assert code == 0
    assert json.loads(output.read_text(encoding="utf-8"))["pass"] is True

    _write_cycle_output(
        cycle_output,
        {"claims": [], "evidence_paths": ["jobs/fabricated.json"]},
    )
    code = main(
        ["--cycle-output", str(cycle_output), "--run-dir", str(run_dir)]
    )
    assert code == 1
