from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest


MODULE_PATH = (
    Path(__file__).parents[1]
    / "research"
    / "src"
    / "experiments"
    / "prepare_cycle4_confirmation.py"
)
SPEC = importlib.util.spec_from_file_location("prepare_cycle4_confirmation", MODULE_PATH)
assert SPEC and SPEC.loader
promotion = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(promotion)

SOURCE_COMMIT = "a" * 40
V0G_COMMIT = "b" * 40


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _v1f_inputs(root: Path) -> tuple[Path, Path, Path]:
    calibration_path = root / "research/jobs/V1F-NONFLAT-CALIBRATION-C4/numerical_calibration.json"
    calibration = {
        "experiment": promotion.V1F_ID,
        "pass": True,
        "gate_layers": {
            "invariants": True,
            "timestep_convergence": True,
            "storage_order_sensitivity": True,
            "stationarity": True,
            "precision": True,
            "adjacent_window_stability": True,
        },
        "numerical_resolution_limits": {
            metric: 0.001 for metric in promotion.EFFECT_METRICS
        },
    }
    _write_json(calibration_path, calibration)
    config_path = root / "research/jobs/V1F-NONFLAT-CALIBRATION-C4/config.json"
    config = {
        "experiment_id": promotion.V1F_ID,
        "seeds": list(range(64)),
        "conditions": [
            {"name": f"{landscape}-dt-{dt}"}
            for landscape in ("smooth", "clustered", "shuffled")
            for dt in ("0.02", "0.01", "0.005")
        ] + [
            {"name": f"order-{order}-dt-{dt}"}
            for order in ("canonical", "permuted")
            for dt in ("0.02", "0.01", "0.005")
        ],
        "timesteps": [0.02, 0.01, 0.005],
        "population": 1000,
        "grid_shape": [64, 64],
        "total_time": 4500.0,
        "output_time_interval": 5.0,
        "steady_snapshots": 144,
        "omp_threads": 1,
        "parallel": 8,
        "per_run_timeout_seconds": 10800,
        **{
            key: value
            for key, value in promotion.MODEL_PARAMETERS.items()
            if key != "dt"
        },
        "independent_precision_absolute_half_widths": promotion.ABSOLUTE_GATE_BOUNDS,
        "independent_precision_relative_half_widths": {"wealth_variance": 0.2},
        "adjacent_window_absolute_bounds": promotion.ABSOLUTE_GATE_BOUNDS,
        "adjacent_window_relative_bounds": {"wealth_variance": 0.1},
    }
    _write_json(config_path, config)
    result_path = root / "research/jobs/V1F-NONFLAT-CALIBRATION-C4/result.json"
    _write_json(
        result_path,
        {
            "experiment": promotion.V1F_ID,
            "status": "completed",
            "pass": True,
            "execution_completed": True,
            "runs_completed": 960,
            "run_failures": 0,
            "calibration_sha256": _sha256(calibration_path),
            "config_sha256": _sha256(config_path),
        },
    )
    return calibration_path, result_path, config_path


def test_prepare_creates_deterministic_non_authorizing_candidate(tmp_path, monkeypatch):
    monkeypatch.setattr(promotion, "_require_real_commit", lambda *_: None)
    calibration, result, config = _v1f_inputs(tmp_path)
    promotion.prepare(tmp_path, calibration, result, config, SOURCE_COMMIT)

    lock_path = tmp_path / "research/parameter_lock.cycle4.json"
    first_lock = lock_path.read_bytes()
    lock = json.loads(first_lock)
    e1_config = json.loads(
        (tmp_path / f"research/jobs/{promotion.E1_ID}/config.json").read_text()
    )
    assert lock["status"] == "candidate"
    assert lock["confirmatory_execution_authorized"] is False
    assert lock["authorized_experiments"] == []
    assert lock["promotion_base_commit"] == SOURCE_COMMIT
    assert lock["source_commit"] == "pending clean V0G checkout"
    assert e1_config["seeds"] == list(promotion.E1_SEEDS)
    assert "binary_sha256" not in e1_config
    assert e1_config["numerical_calibration_sha256"] == _sha256(calibration)
    assert len(set(e1_config["seeds"])) == 64

    promotion.prepare(tmp_path, calibration, result, config, SOURCE_COMMIT)
    assert lock_path.read_bytes() == first_lock


def test_prepare_rejects_failed_or_incomplete_v1f(tmp_path, monkeypatch):
    monkeypatch.setattr(promotion, "_require_real_commit", lambda *_: None)
    calibration, result, config = _v1f_inputs(tmp_path)
    payload = json.loads(calibration.read_text())
    payload["gate_layers"]["precision"] = False
    _write_json(calibration, payload)
    result_payload = json.loads(result.read_text())
    result_payload["calibration_sha256"] = _sha256(calibration)
    _write_json(result, result_payload)
    with pytest.raises(RuntimeError, match="did not pass every"):
        promotion.prepare(tmp_path, calibration, result, config, SOURCE_COMMIT)


def test_finalize_requires_v0g_and_binds_exact_binary(tmp_path, monkeypatch):
    monkeypatch.setattr(promotion, "_require_real_commit", lambda *_: None)
    calibration, result, config = _v1f_inputs(tmp_path)
    promotion.prepare(tmp_path, calibration, result, config, SOURCE_COMMIT)
    v0g_result = tmp_path / f"research/jobs/{promotion.V0G_ID}/workspace/result.json"
    _write_json(
        v0g_result,
        {
            "experiment": promotion.V0G_ID,
            "status": "completed",
            "pass": True,
            "environment": {
                "host": "umi",
                "working_tree_clean": True,
                "source_commit": V0G_COMMIT,
            },
            "pytest": {"returncode": 0},
            "builds": [
                {"openmp": False, "pass": True},
                {"openmp": True, "pass": True},
            ],
        },
    )
    binary = tmp_path / f"research/jobs/{promotion.V0G_ID}/workspace/build-off/src/politeia"
    binary.parent.mkdir(parents=True, exist_ok=True)
    binary.write_bytes(b"cycle4 reference executable")
    promotion.finalize(tmp_path, v0g_result, binary)

    lock = json.loads((tmp_path / "research/parameter_lock.cycle4.json").read_text())
    e1_config = json.loads(
        (tmp_path / f"research/jobs/{promotion.E1_ID}/config.json").read_text()
    )
    assert lock["status"] == "final"
    assert lock["confirmatory_execution_authorized"] is True
    assert lock["authorized_experiments"] == [promotion.E1_ID]
    assert lock["source_commit"] == V0G_COMMIT
    assert lock["simulator_validation"]["binary_sha256"] == _sha256(binary)
    assert e1_config["binary_sha256"] == _sha256(binary)
    assert e1_config["parameter_lock_sha256"] == _sha256(
        tmp_path / "research/parameter_lock.cycle4.json"
    )

    with pytest.raises(RuntimeError, match="final Cycle 4 parameter lock"):
        promotion.prepare(tmp_path, calibration, result, config, SOURCE_COMMIT)


def test_promotion_refuses_to_rewrite_after_e1_outcomes_exist(tmp_path, monkeypatch):
    monkeypatch.setattr(promotion, "_require_real_commit", lambda *_: None)
    calibration, result, config = _v1f_inputs(tmp_path)
    outcome = tmp_path / f"research/jobs/{promotion.E1_ID}/workspace/result.json"
    _write_json(outcome, {"experiment": promotion.E1_ID})
    with pytest.raises(RuntimeError, match="after E1 outcomes exist"):
        promotion.prepare(tmp_path, calibration, result, config, SOURCE_COMMIT)


def test_require_real_commit_rejects_fabricated_sha(tmp_path):
    """A well-formed but nonexistent SHA must fail loudly at prepare time."""
    import subprocess

    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / "seed.txt").write_text("x\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "t"],
        cwd=tmp_path,
        check=True,
    )
    real = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=tmp_path, capture_output=True, text=True, check=True
    ).stdout.strip()
    promotion._require_real_commit(tmp_path, real)

    fabricated = real[:7] + "0" * 33
    assert fabricated != real
    with pytest.raises(ValueError, match="does not resolve to a commit"):
        promotion._require_real_commit(tmp_path, fabricated)


def test_archive_v1f_cross_checks_runs_and_writes_tracked_evidence(tmp_path):
    calibration_path, _result_path, config_path = _v1f_inputs(tmp_path)
    job_dir = config_path.parent
    workspace = job_dir / "workspace"
    workspace.mkdir()
    binary = tmp_path / "research/jobs/V0F-SIMULATOR-TESTS-C4/workspace/build-off/src/politeia"
    binary.parent.mkdir(parents=True)
    binary.write_bytes(b"v1f reference binary")
    binary_sha256 = _sha256(binary)

    config = json.loads(config_path.read_text())
    config["binary"] = binary.relative_to(tmp_path).as_posix()
    _write_json(config_path, config)
    workspace_calibration = workspace / "numerical_calibration.json"
    workspace_calibration.write_bytes(calibration_path.read_bytes())
    calibration_sha256 = _sha256(workspace_calibration)

    run_specs = []
    for index in range(960):
        run_id = f"run-{index:04d}"
        run_specs.append({"run_id": run_id})
        run_dir = workspace / "runs" / run_id
        run_dir.mkdir(parents=True)
        _write_json(
            run_dir / "completion.json",
            {
                "status": "completed",
                "run_id": run_id,
                "binary_sha256": binary_sha256,
                "omp_threads": 1,
                "elapsed_seconds": 1.0,
            },
        )
        _write_json(run_dir / "health.json", {"pass": True})
    _write_json(workspace / "run_specs.json", {"runs": run_specs})
    _write_json(workspace / "matched_input_audit.json", {"pass": True})
    (workspace / "replicate_metrics.csv").write_text("run_id\n", encoding="utf-8")
    _write_json(workspace / "stationarity_report.json", {"pass": True})
    _write_json(workspace / "ensemble_stationarity_report.json", {"pass": True})
    conditions = {
        f"condition-{index}": {
            "tail_stationarity_pass": True,
            "adjacent_window_stability_pass": True,
            "independent_replicate_precision_pass": True,
            "temporal_ess_diagnostic_pass": True,
            "metrics": {},
        }
        for index in range(9)
    }
    _write_json(
        workspace / "steady_estimand_report.json",
        {
            "replicates_per_condition": 64,
            "tail_stationarity_valid": True,
            "adjacent_window_stability_valid": True,
            "independent_replicate_precision_valid": True,
            "temporal_ess_diagnostic_valid": True,
            "conditions": conditions,
        },
    )
    _write_json(
        workspace / "result.json",
        {
            "experiment": promotion.V1F_ID,
            "status": "completed",
            "pass": True,
            "calibration_sha256": calibration_sha256,
            "config_sha256": _sha256(config_path),
        },
    )
    jobctl_dir = tmp_path / f".autoresearcher/jobs/{promotion.V1F_ID}"
    _write_json(
        jobctl_dir / "spec.json",
        {
            "commit_id": SOURCE_COMMIT,
            "config_sha256": _sha256(config_path),
        },
    )
    _write_json(
        jobctl_dir / "result.json",
        {
            "exit_code": 0,
            "timed_out": False,
            "wall_seconds": 120.0,
            "artifacts": [
                {"path": name, "valid": True}
                for name in promotion.V1F_WORKSPACE_ARTIFACTS
            ],
        },
    )

    final_marker = workspace / "runs/run-0959/completion.json"
    final_marker_payload = json.loads(final_marker.read_text())
    final_marker.unlink()
    with pytest.raises(RuntimeError, match="completion markers are incomplete: 959/960"):
        promotion.archive_v1f(tmp_path, job_dir, jobctl_dir)
    _write_json(final_marker, final_marker_payload)

    result = promotion.archive_v1f(tmp_path, job_dir, jobctl_dir)
    assert result["status"] == "completed_passed_gate"
    assert result["runs_completed"] == 960
    assert result["run_failures"] == 0
    assert result["elapsed_cpu_hours"] == pytest.approx(960 / 3600)
    assert result["binary_sha256"] == binary_sha256
    assert json.loads((job_dir / "result.json").read_text()) == result
    manifest = json.loads((job_dir / "manifest.json").read_text())
    assert manifest["jobctl_reconcile"] == "completed"
    assert len(manifest["artifacts"]) == len(promotion.V1F_WORKSPACE_ARTIFACTS)
