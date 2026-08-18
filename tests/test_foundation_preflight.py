"""Functional tests for foundation/preflight.py."""
import json
import tempfile
from pathlib import Path

import pytest

from autoresearcher.foundation.preflight import check_experiment, run


def _write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


@pytest.fixture()
def exp_dir():
    with tempfile.TemporaryDirectory() as td:
        path = Path(td)
        _write(path / "data_checksums.txt", "dataset sha256: abc123")
        yield path


def test_all_pass_p0(exp_dir):
    _write(exp_dir / "commit.txt", "abc1234")
    _write(exp_dir / "env.lock", "python=3.9\nnumpy=1.24")
    _write(exp_dir / "config.yaml", "lr: 0.001")
    _write(exp_dir / "seeds.txt", "11\n23\n37")
    _write(exp_dir / "outputs.txt", "result.json\nplot.png")
    result = run(exp_dir, "P0")
    assert result["status"] == "ok"
    assert result["failed"] == []


def test_all_pass_p0_with_waiver(exp_dir):
    _write(exp_dir / "commit.txt", "abc1234")
    _write(exp_dir / "env.lock", "python=3.9\nnumpy=1.24")
    _write(exp_dir / "config.yaml", "lr: 0.001")
    _write(exp_dir / "seeds.txt", "11")
    _write(exp_dir / "seed_waiver.txt", "only 1 seed due to cost")
    _write(exp_dir / "outputs.txt", "result.json")
    result = run(exp_dir, "P0")
    assert result["status"] == "ok"
    assert result["failed"] == []


def test_all_pass_p1_with_few_seeds(exp_dir):
    _write(exp_dir / "commit.txt", "abc1234")
    _write(exp_dir / "env.lock", "python=3.9")
    _write(exp_dir / "config.yaml", "lr: 0.001")
    _write(exp_dir / "seeds.txt", "11")
    _write(exp_dir / "outputs.txt", "result.json")
    result = run(exp_dir, "P1")
    assert result["status"] == "ok"


def test_commit_dirty_blocked(exp_dir):
    _write(exp_dir / "commit.txt", "dirty")
    _write(exp_dir / "env.lock", "python=3.9")
    _write(exp_dir / "config.yaml", "lr: 0.001")
    _write(exp_dir / "seeds.txt", "11\n23\n37")
    _write(exp_dir / "outputs.txt", "result.json")
    result = run(exp_dir, "P0")
    assert result["status"] == "blocked"
    assert "commit_id" in result["failed"]


def test_env_missing_blocked(exp_dir):
    _write(exp_dir / "commit.txt", "abc1234")
    _write(exp_dir / "config.yaml", "lr: 0.001")
    _write(exp_dir / "seeds.txt", "11\n23\n37")
    _write(exp_dir / "outputs.txt", "result.json")
    result = run(exp_dir, "P0")
    assert result["status"] == "blocked"
    assert "env_snapshot" in result["failed"]


def test_env_empty_blocked(exp_dir):
    _write(exp_dir / "commit.txt", "abc1234")
    _write(exp_dir / "env.txt", "")
    _write(exp_dir / "config.yaml", "lr: 0.001")
    _write(exp_dir / "seeds.txt", "11\n23\n37")
    _write(exp_dir / "outputs.txt", "result.json")
    result = run(exp_dir, "P0")
    assert result["status"] == "blocked"
    assert "env_snapshot" in result["failed"]


def test_config_missing_blocked(exp_dir):
    _write(exp_dir / "commit.txt", "abc1234")
    _write(exp_dir / "env.lock", "python=3.9")
    _write(exp_dir / "seeds.txt", "11\n23\n37")
    _write(exp_dir / "outputs.txt", "result.json")
    result = run(exp_dir, "P0")
    assert result["status"] == "blocked"
    assert "config" in result["failed"]


def test_seeds_missing_blocked(exp_dir):
    _write(exp_dir / "commit.txt", "abc1234")
    _write(exp_dir / "env.lock", "python=3.9")
    _write(exp_dir / "config.yaml", "lr: 0.001")
    _write(exp_dir / "outputs.txt", "result.json")
    result = run(exp_dir, "P0")
    assert result["status"] == "blocked"
    assert "seeds" in result["failed"]


def test_seeds_empty_blocked(exp_dir):
    _write(exp_dir / "commit.txt", "abc1234")
    _write(exp_dir / "env.lock", "python=3.9")
    _write(exp_dir / "config.yaml", "lr: 0.001")
    _write(exp_dir / "seeds.txt", "")
    _write(exp_dir / "outputs.txt", "result.json")
    result = run(exp_dir, "P0")
    assert result["status"] == "blocked"
    assert "seeds" in result["failed"]


def test_artifacts_missing_blocked(exp_dir):
    _write(exp_dir / "commit.txt", "abc1234")
    _write(exp_dir / "env.lock", "python=3.9")
    _write(exp_dir / "config.yaml", "lr: 0.001")
    _write(exp_dir / "seeds.txt", "11\n23\n37")
    result = run(exp_dir, "P0")
    assert result["status"] == "blocked"
    assert "artifacts" in result["failed"]


def test_nan_in_json_blocked(exp_dir):
    _write(exp_dir / "commit.txt", "abc1234")
    _write(exp_dir / "env.lock", "python=3.9")
    _write(exp_dir / "seeds.txt", "11\n23\n37")
    _write(exp_dir / "outputs.txt", "result.json")
    _write(exp_dir / "config.json", json.dumps({"loss": float("nan")}))
    result = run(exp_dir, "P0")
    assert result["status"] == "blocked"
    assert "finite_json" in result["failed"]


def test_exp_dir_not_exist():
    exp_dir = Path("/tmp/_no_such_dir_preflight_test_")
    result = run(exp_dir, "P0")
    assert result["status"] == "blocked"
    assert "exp_dir" in result.get("failed", []) or result["checks"] == 0


def test_multiple_blocked_aggregates(exp_dir):
    """All checks fail — should report all failures."""
    result = run(exp_dir, "P0")
    assert result["status"] == "blocked"
    assert len(result["failed"]) >= 5  # commit, env, config, seeds, artifacts


def test_data_checksums_missing_blocked(exp_dir):
    _write(exp_dir / "commit.txt", "abc1234")
    _write(exp_dir / "env.lock", "python=3.9")
    _write(exp_dir / "config.yaml", "lr: 0.001")
    _write(exp_dir / "seeds.txt", "11\n23\n37")
    _write(exp_dir / "outputs.txt", "result.json")
    (exp_dir / "data_checksums.txt").unlink()
    result = run(exp_dir, "P0")
    assert result["status"] == "blocked"
    assert "data_checksums" in result["failed"]


def test_experiment_check_binds_files_and_rejects_commit_mismatch(exp_dir):
    _write(exp_dir / "config.json", "{}")
    _write(exp_dir / "env.txt", "python=3.11")
    experiment = {
        "id": "E1",
        "priority": "P0",
        "mode": "local",
        "command": ["python", "run.py"],
        "config": "config.json",
        "commit_id": "old",
        "seeds": [1, 2, 3],
        "env_snapshot": "env.txt",
        "data_checksums": {"dataset": "abc"},
        "artifacts": ["result.json"],
    }
    result = check_experiment(experiment, exp_dir, "new")
    assert result["status"] == "blocked"
    assert "commit_id" in result["failed"]
    assert len(result["bindings"]["config_sha256"]) == 64


def _local_experiment_with_strategy(exp_dir):
    _write(exp_dir / "config.json", "{}")
    _write(exp_dir / "env.txt", "python=3.11")
    return {
        "id": "E-HPC",
        "priority": "P0",
        "mode": "local",
        "command": ["python3", "screen.py"],
        "config": "config.json",
        "commit_id": "abc",
        "seeds": [1, 2, 3],
        "env_snapshot": "env.txt",
        "data_checksums": {"dataset": "abc"},
        "artifacts": ["screen.json", "method_validation.json"],
        "computational_strategy": {
            "approach": "Use two-particle Benettin for screening",
            "evidence_role": "screening",
            "supports_core_claim": False,
            "evidence_boundary": "Candidate selection only",
            "reference_method": "variational Lyapunov equations",
            "validation_points": [
                "largest estimated lambda",
                "near-zero lambda",
                "transition boundary",
            ],
            "agreement": {
                "metrics": ["lambda"],
                "rtol": 0.1,
                "atol": 0.001,
            },
            "reference_validation_required": True,
            "validation_artifact": "method_validation.json",
        },
    }


def test_screening_strategy_requires_reference_validation_contract(exp_dir):
    experiment = _local_experiment_with_strategy(exp_dir)
    strategy = experiment["computational_strategy"]
    for field in (
        "reference_method",
        "validation_points",
        "agreement",
        "reference_validation_required",
        "validation_artifact",
    ):
        strategy.pop(field)
    result = check_experiment(experiment, exp_dir, "abc")
    assert result["status"] == "ok"
    assert "computational_strategy" not in result["failed"]


def test_screening_strategy_cannot_replace_reference_evidence(exp_dir):
    experiment = _local_experiment_with_strategy(exp_dir)
    strategy = experiment["computational_strategy"]
    strategy["supports_core_claim"] = True
    strategy.pop("reference_method")
    strategy.pop("validation_points")
    strategy.pop("agreement")
    strategy.pop("validation_artifact")
    result = check_experiment(experiment, exp_dir, "abc")
    assert result["status"] == "blocked"
    assert "computational_strategy" in result["failed"]
    detail = next(
        item["detail"]
        for item in result["details"]
        if item["check"] == "computational_strategy"
    )
    assert "reference_method" in detail
    assert "validation_artifact" in detail


def test_strategy_validation_report_must_be_declared_artifact(exp_dir):
    experiment = _local_experiment_with_strategy(exp_dir)
    experiment["computational_strategy"]["supports_core_claim"] = True
    experiment["artifacts"].remove("method_validation.json")
    result = check_experiment(experiment, exp_dir, "abc")
    assert result["status"] == "blocked"
    assert "computational_strategy" in result["failed"]


def test_directory_preflight_checks_computational_strategy_file(exp_dir):
    experiment = _local_experiment_with_strategy(exp_dir)
    _write(exp_dir / "commit.txt", "abc")
    _write(exp_dir / "seeds.txt", "1\n2\n3")
    _write(
        exp_dir / "outputs.txt",
        "screen.json\nmethod_validation.json\n",
    )
    _write(
        exp_dir / "computational_strategy.json",
        json.dumps(experiment["computational_strategy"]),
    )
    result = run(exp_dir, "P0")
    assert result["status"] == "ok"


def test_directory_preflight_blocks_unvalidated_screening(exp_dir):
    experiment = _local_experiment_with_strategy(exp_dir)
    experiment["computational_strategy"]["supports_core_claim"] = True
    experiment["computational_strategy"]["validation_points"] = []
    _write(exp_dir / "commit.txt", "abc")
    _write(exp_dir / "seeds.txt", "1\n2\n3")
    _write(exp_dir / "outputs.txt", "screen.json\n")
    _write(
        exp_dir / "computational_strategy.json",
        json.dumps(experiment["computational_strategy"]),
    )
    result = run(exp_dir, "P0")
    assert result["status"] == "blocked"
    assert "computational_strategy" in result["failed"]
