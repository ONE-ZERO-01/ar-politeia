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

# Captured before the autouse fixture blanks them, so the integration test can
# assert against the register the repository actually ships.
REAL_SEED_REUSE_COMPONENTS = promotion.SEED_REUSE_COMPONENTS
REAL_EVIDENCE_BEARING_JOBS = promotion.EVIDENCE_BEARING_JOBS

SOURCE_COMMIT = "a" * 40
V0G_COMMIT = "b" * 40


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _v1f_inputs(root: Path, *, binary_sha256: str | None = None) -> tuple[Path, Path, Path]:
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
            "binary_sha256": binary_sha256 or "b" * 64,
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
    binary = tmp_path / f"research/jobs/{promotion.V0G_ID}/workspace/build-off/src/politeia"
    binary.parent.mkdir(parents=True, exist_ok=True)
    binary.write_bytes(b"cycle4 reference executable")
    calibration, result, config = _v1f_inputs(
        tmp_path, binary_sha256=_sha256(binary)
    )
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
    promotion.finalize(tmp_path, v0g_result, binary)

    lock = json.loads((tmp_path / "research/parameter_lock.cycle4.json").read_text())
    e1_config = json.loads(
        (tmp_path / f"research/jobs/{promotion.E1_ID}/config.json").read_text()
    )
    assert lock["status"] == "final"
    assert lock["confirmatory_execution_authorized"] is True
    assert lock["authorized_experiments"] == [promotion.E1_ID]
    assert lock["source_commit"] == V0G_COMMIT
    assert lock["numerical_calibration"]["reference_binary_sha256"] == _sha256(binary)
    assert lock["simulator_validation"]["binary_sha256"] == _sha256(binary)
    assert e1_config["binary_sha256"] == _sha256(binary)
    assert e1_config["parameter_lock_sha256"] == _sha256(
        tmp_path / "research/parameter_lock.cycle4.json"
    )

    with pytest.raises(RuntimeError, match="final Cycle 4 parameter lock"):
        promotion.prepare(tmp_path, calibration, result, config, SOURCE_COMMIT)


def test_finalize_rejects_binary_that_is_not_the_calibrated_one(tmp_path, monkeypatch):
    """A post-calibration simulator source change yields a different binary.

    The V1F numerical resolution limits were measured on one exact artifact, so
    binding a rebuilt binary to E1-C4 must fail loudly instead of silently
    producing a lock whose calibration and executable do not correspond.
    """
    monkeypatch.setattr(promotion, "_require_real_commit", lambda *_: None)
    calibrated_sha = "c" * 64
    calibration, result, config = _v1f_inputs(tmp_path, binary_sha256=calibrated_sha)
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
    rebuilt = tmp_path / f"research/jobs/{promotion.V0G_ID}/workspace/build-off/src/politeia"
    rebuilt.parent.mkdir(parents=True, exist_ok=True)
    rebuilt.write_bytes(b"a source change after calibration produced this")
    assert _sha256(rebuilt) != calibrated_sha

    with pytest.raises(RuntimeError, match="not the calibrated reference binary"):
        promotion.finalize(tmp_path, v0g_result, rebuilt)
    # The lock must remain an unexecuted candidate.
    lock = json.loads((tmp_path / "research/parameter_lock.cycle4.json").read_text())
    assert lock["status"] == "candidate"
    assert lock["confirmatory_execution_authorized"] is False


def test_finalize_rejects_binary_outside_v0g_workspace(tmp_path, monkeypatch):
    monkeypatch.setattr(promotion, "_require_real_commit", lambda *_: None)
    stray = tmp_path / "elsewhere/politeia"
    stray.parent.mkdir(parents=True)
    stray.write_bytes(b"stray binary")
    calibration, result, config = _v1f_inputs(tmp_path, binary_sha256=_sha256(stray))
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
    with pytest.raises(RuntimeError, match="inside the V0G workspace"):
        promotion.finalize(tmp_path, v0g_result, stray)


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


def _e1_fixture(root: Path) -> tuple[Path, Path]:
    """Build a minimal but internally consistent finished E1-C4 run.

    The fixture mirrors the shape of the real workspace: 64 seeds x 2 matched
    conditions, one completion marker and health file per run, the eight
    jobctl-declared artifacts, and a paired-effects verdict that agrees with the
    steady and ensemble reports it was derived from.
    """
    binary = (
        root
        / "research/jobs/V0G-SIMULATOR-TESTS-C4/workspace/build-off/src/politeia"
    )
    binary.parent.mkdir(parents=True, exist_ok=True)
    binary.write_bytes(b"cycle4 calibrated reference executable")
    binary_sha256 = _sha256(binary)

    lock_path = root / "research/parameter_lock.cycle4.json"
    _write_json(
        lock_path,
        {
            "lock_id": "ar-politeia-cycle4-confirmatory-v1",
            "status": "final",
            "confirmatory_execution_authorized": True,
            "authorized_experiments": [promotion.E1_ID],
            "source_commit": V0G_COMMIT,
            "numerical_calibration": {"reference_binary_sha256": binary_sha256},
            "design_contract": {
                "conditions": list(promotion.E1_CONDITIONS),
                "run_count": promotion.E1_RUN_COUNT,
                "seed_count": promotion.E1_SEED_COUNT,
            },
        },
    )

    job_dir = root / f"research/jobs/{promotion.E1_ID}"
    config_path = job_dir / "config.json"
    _write_json(
        config_path,
        {
            "experiment_id": promotion.E1_ID,
            "binary": binary.relative_to(root).as_posix(),
            "binary_sha256": binary_sha256,
            "parameter_lock_sha256": _sha256(lock_path),
            "seeds": list(range(promotion.E1_SEED_COUNT)),
        },
    )

    workspace = job_dir / "workspace"
    runs = []
    for seed in range(promotion.E1_SEED_COUNT):
        for condition in promotion.E1_CONDITIONS:
            run_id = f"seed-{seed}--{condition}"
            run_dir = workspace / "runs" / run_id
            run_dir.mkdir(parents=True)
            snapshot = run_dir / "snap_00000010.csv"
            snapshot.write_text(f"gid,w\n{seed},1.0\n", encoding="utf-8")
            _write_json(
                run_dir / "completion.json",
                {
                    "status": "completed",
                    "run_id": run_id,
                    "binary_sha256": binary_sha256,
                    "omp_threads": 1,
                    "final_snapshot": snapshot.name,
                    "final_snapshot_sha256": _sha256(snapshot),
                    "elapsed_seconds": 2.0,
                },
            )
            _write_json(run_dir / "health.json", {"windows": []})
            runs.append({"run_id": run_id, "seed": seed, "condition": condition})

    _write_json(workspace / "run_specs.json", {"runs": runs})
    _write_json(workspace / "matched_input_audit.json", {"pass": True})
    _write_json(
        workspace / "parameter_lock_audit.json",
        {
            "pass": True,
            "parameter_lock_sha256": _sha256(lock_path),
            "parameter_lock_status": "final",
        },
    )
    (workspace / "replicate_metrics.csv").write_text("run_id\n", encoding="utf-8")
    _write_json(
        workspace / "stationarity_report.json",
        {"experiment": promotion.E1_ID, "pass": True},
    )
    _write_json(
        workspace / "ensemble_stationarity_report.json",
        {"experiment": promotion.E1_ID, "stationarity_valid": True},
    )
    _write_json(
        workspace / "steady_estimand_report.json",
        {
            "experiment": promotion.E1_ID,
            "replicates_per_condition": promotion.E1_SEED_COUNT,
            "tail_stationarity_valid": True,
            "adjacent_window_stability_valid": True,
            "independent_replicate_precision_valid": True,
            "conditions": {
                name: {"condition": name} for name in promotion.E1_CONDITIONS
            },
        },
    )
    _write_json(
        workspace / "paired_effects.json",
        {
            "experiment": promotion.E1_ID,
            "comparison": "clustered-minus-shuffled",
            "analysis_gate_pass": True,
            "claim_supported": True,
            "valid_null_or_equivalence": False,
            "gates": {key: True for key in promotion.E1_PAIRED_GATES},
            "execution_invariant_checks": {"wealth_nonnegative": True},
            "temporal_ess_diagnostic_pass": False,
        },
    )
    _write_json(
        workspace / "result.json",
        {
            "experiment": promotion.E1_ID,
            "status": "completed",
            "pass": True,
            "config_sha256": _sha256(config_path),
            "parameter_lock_sha256": _sha256(lock_path),
            "evidence_boundary": "Synthetic generative mechanism only.",
        },
    )

    jobctl_dir = root / f".autoresearcher/jobs/{promotion.E1_ID}"
    _write_json(jobctl_dir / "spec.json", {"commit_id": V0G_COMMIT})
    _write_json(
        jobctl_dir / "result.json",
        {
            "exit_code": 0,
            "timed_out": False,
            "wall_seconds": 60.0,
            "artifacts": [
                {
                    "path": f"research/jobs/{promotion.E1_ID}/workspace/{name}",
                    "contained_in_cwd": True,
                    "valid": True,
                }
                for name in promotion.E1_WORKSPACE_ARTIFACTS
            ],
        },
    )
    return job_dir, jobctl_dir


def test_archive_e1_archives_a_passing_run(tmp_path):
    job_dir, jobctl_dir = _e1_fixture(tmp_path)

    result = promotion.archive_e1(tmp_path, job_dir, jobctl_dir)

    assert result["status"] == "completed_passed_gate_claim_supported"
    assert result["analysis_gate_pass"] is True
    assert result["claim_supported"] is True
    assert result["runs_completed"] == promotion.E1_RUN_COUNT
    assert result["run_failures"] == 0
    assert all(result["gates"].values())
    assert result["elapsed_cpu_hours"] == pytest.approx(
        promotion.E1_RUN_COUNT * 2.0 / 3600.0
    )
    # The verdict is copied verbatim, never recomputed or reinterpreted.
    assert (job_dir / "paired_effects.json").read_bytes() == (
        job_dir / "workspace/paired_effects.json"
    ).read_bytes()
    assert result["paired_effects_sha256"] == _sha256(job_dir / "paired_effects.json")
    assert json.loads((job_dir / "result.json").read_text()) == result
    assert set(result["workspace_artifact_sha256"]) == set(
        promotion.E1_WORKSPACE_ARTIFACTS
    ) | set(promotion.E1_UNDECLARED_PROVENANCE)
    manifest = json.loads((job_dir / "manifest.json").read_text())
    assert manifest["jobctl_reconcile"] == "completed"
    assert manifest["archived_after_run"] is True
    assert len(manifest["artifacts"]) == len(promotion.E1_WORKSPACE_ARTIFACTS)
    assert set(manifest["undeclared_provenance_sha256"]) == set(
        promotion.E1_UNDECLARED_PROVENANCE
    )


def test_archive_e1_is_idempotent(tmp_path):
    job_dir, jobctl_dir = _e1_fixture(tmp_path)
    first = promotion.archive_e1(tmp_path, job_dir, jobctl_dir)
    first_bytes = (job_dir / "result.json").read_bytes()

    second = promotion.archive_e1(tmp_path, job_dir, jobctl_dir)

    assert second == first
    assert (job_dir / "result.json").read_bytes() == first_bytes


def test_archive_e1_rejects_a_marker_whose_payload_was_lost(tmp_path):
    """A marker must be tied to the snapshot it claims, not just to a count."""
    job_dir, jobctl_dir = _e1_fixture(tmp_path)
    victim = job_dir / "workspace/runs/seed-7--shuffled/snap_00000010.csv"
    victim.write_text("gid,w\n7,999.0\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="final snapshot is missing or does not match"):
        promotion.archive_e1(tmp_path, job_dir, jobctl_dir)


def test_archive_e1_rejects_incomplete_markers(tmp_path):
    job_dir, jobctl_dir = _e1_fixture(tmp_path)
    (job_dir / "workspace/runs/seed-7--shuffled/completion.json").unlink()

    with pytest.raises(RuntimeError, match="completion markers are incomplete: 127/128"):
        promotion.archive_e1(tmp_path, job_dir, jobctl_dir)


def test_archive_e1_rejects_a_marker_bound_to_another_binary(tmp_path):
    job_dir, jobctl_dir = _e1_fixture(tmp_path)
    marker_path = job_dir / "workspace/runs/seed-7--shuffled/completion.json"
    marker = json.loads(marker_path.read_text())
    marker["binary_sha256"] = "d" * 64
    _write_json(marker_path, marker)

    with pytest.raises(RuntimeError, match="do not bind the calibrated reference binary"):
        promotion.archive_e1(tmp_path, job_dir, jobctl_dir)


def test_archive_e1_rejects_an_unauthorized_lock(tmp_path):
    job_dir, jobctl_dir = _e1_fixture(tmp_path)
    lock_path = tmp_path / "research/parameter_lock.cycle4.json"
    lock = json.loads(lock_path.read_text())
    lock["status"] = "candidate"
    lock["confirmatory_execution_authorized"] = False
    lock["authorized_experiments"] = []
    _write_json(lock_path, lock)

    with pytest.raises(RuntimeError, match="not authorized by a final"):
        promotion.archive_e1(tmp_path, job_dir, jobctl_dir)


def test_archive_e1_rejects_verdict_disagreeing_with_steady_report(tmp_path):
    job_dir, jobctl_dir = _e1_fixture(tmp_path)
    steady_path = job_dir / "workspace/steady_estimand_report.json"
    steady = json.loads(steady_path.read_text())
    steady["independent_replicate_precision_valid"] = False
    _write_json(steady_path, steady)

    with pytest.raises(RuntimeError, match="disagree on independent_replicate_precision"):
        promotion.archive_e1(tmp_path, job_dir, jobctl_dir)


def test_archive_e1_rejects_gate_verdict_disagreeing_with_its_own_gate_block(tmp_path):
    """The archive must never let a verdict be edited independently of its gates."""
    job_dir, jobctl_dir = _e1_fixture(tmp_path)
    paired_path = job_dir / "workspace/paired_effects.json"
    paired = json.loads(paired_path.read_text())
    paired["analysis_gate_pass"] = False
    paired["claim_supported"] = False
    _write_json(paired_path, paired)

    with pytest.raises(RuntimeError, match="verdict disagrees with its gate block"):
        promotion.archive_e1(tmp_path, job_dir, jobctl_dir)


def test_archive_e1_rejects_a_claim_that_fails_a_gate(tmp_path):
    """A verdict may not be recorded as passing while one of its gates failed."""
    job_dir, jobctl_dir = _e1_fixture(tmp_path)
    paired_path = job_dir / "workspace/paired_effects.json"
    paired = json.loads(paired_path.read_text())
    paired["gates"]["tail_stationarity"] = False
    # Keep analysis_gate_pass True and the steady/ensemble reports agreeing with
    # the failing gate, so the only broken invariant is the conjunction itself.
    _write_json(paired_path, paired)
    steady_path = job_dir / "workspace/steady_estimand_report.json"
    steady = json.loads(steady_path.read_text())
    steady["tail_stationarity_valid"] = False
    _write_json(steady_path, steady)
    ensemble_path = job_dir / "workspace/ensemble_stationarity_report.json"
    ensemble = json.loads(ensemble_path.read_text())
    ensemble["stationarity_valid"] = False
    _write_json(ensemble_path, ensemble)

    with pytest.raises(RuntimeError, match="verdict disagrees with its gate block"):
        promotion.archive_e1(tmp_path, job_dir, jobctl_dir)


def test_archive_e1_rejects_a_declared_artifact_mismatch(tmp_path):
    job_dir, jobctl_dir = _e1_fixture(tmp_path)
    result_path = jobctl_dir / "result.json"
    payload = json.loads(result_path.read_text())
    payload["artifacts"] = payload["artifacts"][:-1]
    _write_json(result_path, payload)

    with pytest.raises(RuntimeError, match="artifact declaration differs"):
        promotion.archive_e1(tmp_path, job_dir, jobctl_dir)


def test_archive_e1_rejects_an_artifact_declared_outside_the_workspace(tmp_path):
    job_dir, jobctl_dir = _e1_fixture(tmp_path)
    result_path = jobctl_dir / "result.json"
    payload = json.loads(result_path.read_text())
    payload["artifacts"][3]["contained_in_cwd"] = False
    _write_json(result_path, payload)

    with pytest.raises(RuntimeError, match="outside its workspace"):
        promotion.archive_e1(tmp_path, job_dir, jobctl_dir)


def test_archive_e1_rejects_a_failed_matched_input_audit(tmp_path):
    job_dir, jobctl_dir = _e1_fixture(tmp_path)
    audit_path = job_dir / "workspace/matched_input_audit.json"
    _write_json(audit_path, {"pass": False})

    with pytest.raises(RuntimeError, match="matched-input audit did not pass"):
        promotion.archive_e1(tmp_path, job_dir, jobctl_dir)


def test_archive_e1_records_a_valid_null_without_a_claim(tmp_path):
    job_dir, jobctl_dir = _e1_fixture(tmp_path)
    paired_path = job_dir / "workspace/paired_effects.json"
    paired = json.loads(paired_path.read_text())
    paired["claim_supported"] = False
    paired["valid_null_or_equivalence"] = True
    _write_json(paired_path, paired)

    result = promotion.archive_e1(tmp_path, job_dir, jobctl_dir)

    assert result["status"] == "completed_passed_gate_valid_null"
    assert result["analysis_gate_pass"] is True
    assert result["claim_supported"] is False
    assert result["valid_null_or_equivalence"] is True


def test_archive_e1_records_a_failed_gate_without_a_claim(tmp_path):
    job_dir, jobctl_dir = _e1_fixture(tmp_path)
    paired_path = job_dir / "workspace/paired_effects.json"
    paired = json.loads(paired_path.read_text())
    paired["analysis_gate_pass"] = False
    paired["claim_supported"] = False
    paired["gates"]["tail_stationarity"] = False
    _write_json(paired_path, paired)
    steady_path = job_dir / "workspace/steady_estimand_report.json"
    steady = json.loads(steady_path.read_text())
    steady["tail_stationarity_valid"] = False
    _write_json(steady_path, steady)
    ensemble_path = job_dir / "workspace/ensemble_stationarity_report.json"
    ensemble = json.loads(ensemble_path.read_text())
    ensemble["stationarity_valid"] = False
    _write_json(ensemble_path, ensemble)

    result = promotion.archive_e1(tmp_path, job_dir, jobctl_dir)

    assert result["status"] == "completed_failed_gate"
    assert result["analysis_gate_pass"] is False
    assert result["claim_supported"] is False
    assert result["gates"]["tail_stationarity"] is False


def test_archive_e1_rejects_a_run_outside_the_frozen_design(tmp_path):
    job_dir, jobctl_dir = _e1_fixture(tmp_path)
    specs_path = job_dir / "workspace/run_specs.json"
    specs = json.loads(specs_path.read_text())
    specs["runs"][0]["condition"] = "flat"
    _write_json(specs_path, specs)

    with pytest.raises(RuntimeError, match="do not cover the frozen seed x condition design"):
        promotion.archive_e1(tmp_path, job_dir, jobctl_dir)


def _resync_lock_sha(root: Path, job_dir: Path) -> None:
    """Re-point every lock-hash binding after the lock itself was mutated."""
    lock_sha = _sha256(root / "research/parameter_lock.cycle4.json")
    config_path = job_dir / "config.json"
    config = json.loads(config_path.read_text())
    config["parameter_lock_sha256"] = lock_sha
    _write_json(config_path, config)
    workspace = job_dir / "workspace"
    result_path = workspace / "result.json"
    result = json.loads(result_path.read_text())
    result["config_sha256"] = _sha256(config_path)
    result["parameter_lock_sha256"] = lock_sha
    _write_json(result_path, result)
    audit_path = workspace / "parameter_lock_audit.json"
    audit = json.loads(audit_path.read_text())
    audit["parameter_lock_sha256"] = lock_sha
    _write_json(audit_path, audit)


def test_archive_e1_rejects_a_lock_that_froze_another_design(tmp_path):
    """An executed design may not be re-pointed at a different pre-registration."""
    job_dir, jobctl_dir = _e1_fixture(tmp_path)
    lock_path = tmp_path / "research/parameter_lock.cycle4.json"
    lock = json.loads(lock_path.read_text())
    lock["design_contract"]["run_count"] = 256
    _write_json(lock_path, lock)
    _resync_lock_sha(tmp_path, job_dir)

    with pytest.raises(RuntimeError, match="does not freeze the E1-C4 design"):
        promotion.archive_e1(tmp_path, job_dir, jobctl_dir)


def test_archive_e1_rejects_a_lock_without_a_design_contract(tmp_path):
    job_dir, jobctl_dir = _e1_fixture(tmp_path)
    lock_path = tmp_path / "research/parameter_lock.cycle4.json"
    lock = json.loads(lock_path.read_text())
    lock.pop("design_contract")
    _write_json(lock_path, lock)
    _resync_lock_sha(tmp_path, job_dir)

    with pytest.raises(RuntimeError, match="has no design contract"):
        promotion.archive_e1(tmp_path, job_dir, jobctl_dir)


def test_cli_exposes_archive_e1():
    module = importlib.util.module_from_spec(SPEC)
    SPEC.loader.exec_module(module)
    parser_source = (MODULE_PATH).read_text(encoding="utf-8")
    assert '"archive-e1"' in parser_source
    assert "archive_e1(" in parser_source
    assert module.E1_RUN_COUNT == 128


# ---------------------------------------------------------------------------
# Seeds mutual-exclusion ledger
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _isolated_seed_register(monkeypatch):
    """Run each test against an empty reuse register by default.

    Component verification refers to real job directories and real tracked
    documents by design, so the ledger-mechanics tests must not depend on the
    repository's specific job names. Tests that exercise authorisation install
    their own register and evidence set.
    """
    monkeypatch.setattr(promotion, "SEED_REUSE_COMPONENTS", ())
    monkeypatch.setattr(promotion, "EVIDENCE_BEARING_JOBS", ())


def _seed_job(
    root: Path,
    name: str,
    *,
    seeds: list[int] | None = None,
    seeds_txt: str | None = None,
    config: dict | None = None,
    result: dict | None = None,
    waiver: bool = False,
) -> Path:
    """Materialise one job directory with only the seed channels a test needs."""
    job_dir = root / "research/jobs" / name
    job_dir.mkdir(parents=True, exist_ok=True)
    if waiver:
        (job_dir / "seed_waiver.txt").write_text("declared in test\n", encoding="utf-8")
    if seeds_txt is not None:
        (job_dir / "seeds.txt").write_text(seeds_txt, encoding="utf-8")
    elif seeds is not None:
        (job_dir / "seeds.txt").write_text(
            "\n".join(str(seed) for seed in seeds) + "\n", encoding="utf-8"
        )
    payload = dict(config or {})
    if seeds is not None and "seeds" not in payload:
        payload["seeds"] = list(seeds)
    if payload:
        _write_json(job_dir / "config.json", payload)
    if result is not None:
        _write_json(job_dir / "result.json", result)
    return job_dir


def _audit(root: Path, **kwargs):
    return promotion.audit_seeds(root / "research/jobs", **kwargs)


def test_seed_ledger_harvests_every_channel(tmp_path):
    job_dir = _seed_job(
        tmp_path,
        "JOB-A",
        seeds=[11, 13],
        result={"runs": ["seed-11--smooth", "seed-13--clustered"]},
    )
    record = promotion._harvest_job_seeds(job_dir)
    assert record["seeds"] == [11, 13]
    assert set(record["channels"]) == {"seeds.txt", "declared:config.json", "runids:result.json"}


def test_seed_ledger_recovers_seeds_from_run_ids_alone(tmp_path):
    """An undeclared run-identifier seed counts as consumption by default."""
    job_dir = _seed_job(
        tmp_path,
        "JOB-A",
        seeds_txt="",
        result={"runs": ["seed-6101--smooth", "seed-6203--smooth"]},
    )
    record = promotion._harvest_job_seeds(job_dir)
    assert record["seeds"] == [6101, 6203]
    assert "runids:result.json" in record["channels"]


def test_seed_ledger_reclassifies_a_declared_reanalysis_job(tmp_path):
    """V1D labels its inputs with V1's runs; those are not its own draws."""
    job_dir = _seed_job(
        tmp_path,
        "V1D-STATIONARITY-DIAGNOSTIC-C4",
        seeds_txt="",
        config={"source_experiment": "V1-NONFLAT-CALIBRATION-C4"},
        result={"runs": ["seed-6101--smooth", "seed-6203--smooth"]},
    )
    record = promotion._harvest_job_seeds(job_dir)
    assert record["seeds"] == []
    assert record["references"]["result.json:run_ids"] == [6101, 6203]
    assert record["reference_job"] is True


def test_seed_ledger_requires_a_reanalysis_to_name_its_source(tmp_path):
    """A reference declaration must be corroborated by the job's own config."""
    job_dir = _seed_job(
        tmp_path,
        "V1D-STATIONARITY-DIAGNOSTIC-C4",
        seeds_txt="",
        result={"runs": ["seed-6101--smooth"]},
    )
    with pytest.raises(RuntimeError, match="registered as a reanalysis"):
        promotion._harvest_job_seeds(job_dir)


def test_seed_ledger_records_sentinels_without_counting_them(tmp_path):
    job_dir = _seed_job(tmp_path, "JOB-A", seeds_txt="none\n")
    record = promotion._harvest_job_seeds(job_dir)
    assert record["seeds"] == []
    assert record["sentinels"] == ["none"]


def test_seed_ledger_treats_nested_seeds_as_references(tmp_path):
    """V1P points at another design's seeds; that is not a consumption."""
    job_dir = _seed_job(
        tmp_path,
        "V1P-RUNTIME-PILOT-C4",
        seeds_txt="6007\n",
        config={"seeds": [6007], "target_design": {"seeds": [6101, 6203]}},
    )
    record = promotion._harvest_job_seeds(job_dir)
    assert record["seeds"] == [6007]
    assert record["references"] == {"config.json:nested": [6101, 6203]}


def test_audit_rejects_a_seed_repeated_inside_one_declaration(tmp_path):
    _seed_job(tmp_path, "JOB-A", seeds_txt="11 11\n", config={"seeds": [11]})
    with pytest.raises(RuntimeError, match="repeats seeds inside seeds.txt"):
        _audit(tmp_path)


def test_audit_rejects_a_stale_seeds_txt(tmp_path):
    _seed_job(tmp_path, "JOB-A", seeds_txt="11\n", config={"seeds": [13]})
    with pytest.raises(RuntimeError, match="one of the two is stale"):
        _audit(tmp_path)

def test_audit_rejects_an_unregistered_seed_overlap(tmp_path):
    """Two unrelated jobs sharing a seed breaks run independence."""
    _seed_job(tmp_path, "JOB-A", seeds=[11])
    _seed_job(tmp_path, "JOB-B", seeds=[11])
    with pytest.raises(RuntimeError, match="unregistered seed reuse"):
        _audit(tmp_path)


def test_audit_rejects_an_unregistered_sentinel(tmp_path):
    _seed_job(tmp_path, "JOB-A", seeds_txt="n/a\n")
    with pytest.raises(RuntimeError, match="not registered sentinels"):
        _audit(tmp_path)


def test_audit_accepts_a_declared_paired_rerun(tmp_path, monkeypatch):
    """V1G must reuse V1F's seeds, and the design that declares it must exist."""
    monkeypatch.setattr(
        promotion,
        "SEED_REUSE_COMPONENTS",
        (
            {
                "jobs": ("V1F-NONFLAT-CALIBRATION-C4", "V1G-ORDER-THERMAL-C4"),
                "status": "intended",
                "basis": "declared_paired_rerun",
                "citation": {
                    "path": "research/v1g-order-thermal-design.md",
                    "marker": "seeds | **V1F 冻结的 64 个**",
                },
                "reason": "the seed pairing is the estimand",
            },
        ),
    )
    design = tmp_path / "research/v1g-order-thermal-design.md"
    design.parent.mkdir(parents=True, exist_ok=True)
    design.write_text("| seeds | **V1F 冻结的 64 个**（...） |\n", encoding="utf-8")
    _seed_job(tmp_path, "V1F-NONFLAT-CALIBRATION-C4", seeds=[11003, 11027])
    _seed_job(tmp_path, "V1G-ORDER-THERMAL-C4", seeds=[11003, 11027])

    report = _audit(tmp_path)
    assert report["used_seed_count"] == 2
    assert [entry["status"] for entry in report["overlaps"]] == ["intended", "intended"]
    assert {entry["basis"] for entry in report["overlaps"]} == {"declared_paired_rerun"}


def _paired_component(tmp_path, monkeypatch, *, marker, write_document=True):
    monkeypatch.setattr(
        promotion,
        "SEED_REUSE_COMPONENTS",
        (
            {
                "jobs": ("V1F-NONFLAT-CALIBRATION-C4", "V1G-ORDER-THERMAL-C4"),
                "status": "intended",
                "basis": "declared_paired_rerun",
                "citation": {"path": "research/design.md", "marker": marker},
                "reason": "declared pairing",
            },
        ),
    )
    if write_document:
        document = tmp_path / "research/design.md"
        document.parent.mkdir(parents=True, exist_ok=True)
        document.write_text(marker + "\n", encoding="utf-8")
    _seed_job(tmp_path, "V1F-NONFLAT-CALIBRATION-C4", seeds=[11003])
    _seed_job(tmp_path, "V1G-ORDER-THERMAL-C4", seeds=[11003])


def test_audit_rejects_a_citation_whose_document_is_gone(tmp_path, monkeypatch):
    _paired_component(tmp_path, monkeypatch, marker="reuse declared", write_document=False)
    with pytest.raises(RuntimeError, match="is not in the tree"):
        _audit(tmp_path)


def test_audit_rejects_a_citation_whose_document_stopped_declaring_it(tmp_path, monkeypatch):
    """The document must still contain the declaration, not merely exist."""
    _paired_component(tmp_path, monkeypatch, marker="reuse declared")
    (tmp_path / "research/design.md").write_text("rewritten, no declaration\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="no longer contains the declaration"):
        _audit(tmp_path)


def test_audit_rejects_a_paired_rerun_without_a_citation(tmp_path, monkeypatch):
    monkeypatch.setattr(
        promotion,
        "SEED_REUSE_COMPONENTS",
        (
            {
                "jobs": ("V1F-NONFLAT-CALIBRATION-C4", "V1G-ORDER-THERMAL-C4"),
                "status": "intended",
                "basis": "declared_paired_rerun",
                "reason": "no citation",
            },
        ),
    )
    _seed_job(tmp_path, "V1F-NONFLAT-CALIBRATION-C4", seeds=[11003])
    _seed_job(tmp_path, "V1G-ORDER-THERMAL-C4", seeds=[11003])
    with pytest.raises(RuntimeError, match="no citation path and marker"):
        _audit(tmp_path)


def test_audit_rejects_an_unknown_basis(tmp_path, monkeypatch):
    monkeypatch.setattr(
        promotion,
        "SEED_REUSE_COMPONENTS",
        (
            {
                "jobs": ("JOB-A", "JOB-B"),
                "status": "intended",
                "basis": "because_i_said_so",
                "reason": "prose is not a basis",
            },
        ),
    )
    _seed_job(tmp_path, "JOB-A", seeds=[11])
    _seed_job(tmp_path, "JOB-B", seeds=[11])
    with pytest.raises(RuntimeError, match="expected one of"):
        _audit(tmp_path)


def test_audit_rejects_a_component_naming_a_missing_job(tmp_path, monkeypatch):
    monkeypatch.setattr(
        promotion,
        "SEED_REUSE_COMPONENTS",
        (
            {
                "jobs": ("JOB-A", "TYPO-JOB"),
                "status": "intended",
                "basis": "same_experiment_reexecution",
                "reason": "one experiment",
            },
        ),
    )
    _seed_job(tmp_path, "JOB-A", seeds=[11])
    with pytest.raises(RuntimeError, match="names jobs with no directory"):
        _audit(tmp_path)


def test_audit_rejects_a_reexecution_component_with_mixed_identities(tmp_path, monkeypatch):
    """``same_experiment_reexecution`` must be true, not merely asserted."""
    monkeypatch.setattr(
        promotion,
        "SEED_REUSE_COMPONENTS",
        (
            {
                "jobs": ("JOB-A", "JOB-B"),
                "status": "intended",
                "basis": "same_experiment_reexecution",
                "reason": "claims one experiment",
            },
        ),
    )
    _seed_job(tmp_path, "JOB-A", seeds=[11], config={"experiment_id": "ONE", "seeds": [11]})
    _seed_job(tmp_path, "JOB-B", seeds=[11], config={"experiment_id": "TWO", "seeds": [11]})
    with pytest.raises(RuntimeError, match="claims one experiment re-executed"):
        _audit(tmp_path)


def test_audit_accepts_a_true_reexecution_component(tmp_path, monkeypatch):
    monkeypatch.setattr(
        promotion,
        "SEED_REUSE_COMPONENTS",
        (
            {
                "jobs": ("JOB-A", "JOB-B"),
                "status": "intended",
                "basis": "same_experiment_reexecution",
                "reason": "one experiment, two cycle records",
            },
        ),
    )
    _seed_job(tmp_path, "JOB-A", seeds=[11], config={"experiment_id": "ONE", "seeds": [11]})
    _seed_job(tmp_path, "JOB-B", seeds=[11], config={"experiment_id": "ONE", "seeds": [11]})
    report = _audit(tmp_path)
    assert report["overlaps"][0]["basis"] == "same_experiment_reexecution"


def test_audit_refuses_a_collision_that_touches_evidence_seeds(tmp_path, monkeypatch):
    """An evidence-bearing pair may not be relabelled a 'harmless historical collision'.

    If the members of a component are themselves evidence-bearing, its shared
    seeds are inside the evidence set, so the disjointness the label relies on is
    false. This is the mutation that matters: without it, calling a V1F/V1G-style
    overlap "historical" would authorise it without a declared pairing.
    """
    monkeypatch.setattr(
        promotion,
        "SEED_REUSE_COMPONENTS",
        (
            {
                "jobs": ("V1F-NONFLAT-CALIBRATION-C4", "V1G-ORDER-THERMAL-C4"),
                "status": "grandfathered",
                "basis": "historical_collision",
                "reason": "thought harmless",
            },
        ),
    )
    monkeypatch.setattr(promotion, "EVIDENCE_BEARING_JOBS", ("V1F-NONFLAT-CALIBRATION-C4",))
    _seed_job(tmp_path, "V1F-NONFLAT-CALIBRATION-C4", seeds=[11003])
    _seed_job(tmp_path, "V1G-ORDER-THERMAL-C4", seeds=[11003])
    with pytest.raises(RuntimeError, match="can no longer be called harmless"):
        _audit(tmp_path)


def test_audit_accepts_a_collision_confined_to_the_historical_regime(tmp_path, monkeypatch):
    monkeypatch.setattr(
        promotion,
        "SEED_REUSE_COMPONENTS",
        (
            {
                "jobs": ("OLD-A", "OLD-B"),
                "status": "grandfathered",
                "basis": "historical_collision",
                "reason": "confined to the historical regime",
            },
        ),
    )
    monkeypatch.setattr(promotion, "EVIDENCE_BEARING_JOBS", ("V1F-NONFLAT-CALIBRATION-C4",))
    _seed_job(tmp_path, "OLD-A", seeds=[101])
    _seed_job(tmp_path, "OLD-B", seeds=[101])
    _seed_job(tmp_path, "V1F-NONFLAT-CALIBRATION-C4", seeds=[11003])
    report = _audit(tmp_path)
    assert report["overlaps"][0]["status"] == "grandfathered"
    assert report["evidence_seed_count"] == 1


def test_audit_rejects_an_evidence_job_name_that_does_not_exist(tmp_path, monkeypatch):
    """A typo in the evidence list would silently make disjointness vacuous."""
    monkeypatch.setattr(promotion, "EVIDENCE_BEARING_JOBS", ("TYPO-EVIDENCE-JOB",))
    _seed_job(tmp_path, "JOB-A", seeds=[11])
    with pytest.raises(RuntimeError, match="EVIDENCE_BEARING_JOBS names jobs with no directory"):
        _audit(tmp_path)


def test_audit_authorises_by_membership_not_by_status_label(tmp_path, monkeypatch):
    """The status field is descriptive; only component membership authorises.

    Relabelling a grandfathered component must not change whether its overlap is
    authorised, which is what stops a reader from mistaking ``status`` for a gate.
    """
    monkeypatch.setattr(
        promotion,
        "SEED_REUSE_COMPONENTS",
        (
            {
                "jobs": ("E1-MATCHED-LANDSCAPES", "E2-CHANNEL-ABLATION"),
                "status": "intended",
                "basis": "historical_collision",
                "reason": "relabelled on purpose",
            },
        ),
    )
    _seed_job(tmp_path, "E1-MATCHED-LANDSCAPES", seeds=[101])
    _seed_job(tmp_path, "E2-CHANNEL-ABLATION", seeds=[101])
    report = _audit(tmp_path)
    assert [entry["status"] for entry in report["overlaps"]] == ["intended"]


def test_audit_rejects_a_job_with_no_seed_evidence_and_no_waiver(tmp_path):
    """Silence is not proof of determinism; the job must declare a reason."""
    _seed_job(tmp_path, "JOB-A", seeds_txt="")
    with pytest.raises(RuntimeError, match="no seed evidence and holds no seed_waiver"):
        _audit(tmp_path)


def test_audit_accepts_a_waived_job_with_no_seed_evidence(tmp_path):
    """V0's deterministic tests legitimately record no seeds."""
    _seed_job(tmp_path, "JOB-A", seeds_txt="none\n", waiver=True)
    report = _audit(tmp_path)
    assert report["used_seed_count"] == 0
    assert report["jobs_without_seed_evidence"] == ["JOB-A"]


def test_audit_does_not_count_a_reanalysis_as_a_consumer(tmp_path):
    """V1D must not appear as a consumer of V1's seeds."""
    _seed_job(tmp_path, "V1-NONFLAT-CALIBRATION-C4", seeds=[6101])
    _seed_job(
        tmp_path,
        "V1D-STATIONARITY-DIAGNOSTIC-C4",
        seeds_txt="",
        waiver=True,
        config={"source_experiment": "V1-NONFLAT-CALIBRATION-C4"},
        result={"runs": ["seed-6101--smooth"]},
    )
    report = _audit(tmp_path)
    assert report["used_seed_count"] == 1
    assert report["overlaps"] == []
    assert report["references"]["V1D-STATIONARITY-DIAGNOSTIC-C4"]


def test_audit_detects_a_leak_hidden_from_the_config(tmp_path):
    """The run-id channel is what catches a seed the config never declares."""
    _seed_job(tmp_path, "V1-NONFLAT-CALIBRATION-C4", seeds=[6101], result={"runs": ["seed-6101"]})
    _seed_job(
        tmp_path,
        "JOB-B",
        seeds_txt="",
        result={"runs": ["seed-6101"]},
    )
    with pytest.raises(RuntimeError, match="unregistered seed reuse"):
        _audit(tmp_path)


def test_audit_reports_non_prime_seeds_without_failing(tmp_path):
    """Primality is a convention; frozen history violates it and cannot change."""
    _seed_job(tmp_path, "V1-NONFLAT-CALIBRATION-C4", seeds=[9, 11])
    report = _audit(tmp_path)
    assert report["non_prime_seeds"] == [9]
    assert report["used_seeds"] == [9, 11]


def test_audit_pool_excludes_used_seeds_and_proposes_smallest_primes(tmp_path):
    _seed_job(tmp_path, "V1-NONFLAT-CALIBRATION-C4", seeds=[12301])
    report = _audit(tmp_path, pool_min=12300, pool_max=12350, propose=2)
    assert 12301 not in report["pool"]["available_primes"]
    assert report["proposed_seeds"] == [12323, 12329]


def test_audit_pool_requires_both_bounds(tmp_path):
    _seed_job(tmp_path, "V1-NONFLAT-CALIBRATION-C4", seeds=[11])
    with pytest.raises(RuntimeError, match="pool bounds must be given together"):
        _audit(tmp_path, pool_min=12300)


def test_audit_pool_rejects_an_impossible_proposal(tmp_path):
    _seed_job(tmp_path, "V1-NONFLAT-CALIBRATION-C4", seeds=[11])
    with pytest.raises(RuntimeError, match="cannot propose"):
        _audit(tmp_path, pool_min=12300, pool_max=12310, propose=5)


def test_repository_ledger_holds_no_unregistered_overlap(monkeypatch):
    """Integration guard: the real ledger must stay leak-free as jobs accrue.

    Post-V1F experiments are absent from SEED_REUSE_COMPONENTS, so a new job that
    silently reuses an existing seed fails here rather than in a later analysis.
    """
    monkeypatch.setattr(promotion, "SEED_REUSE_COMPONENTS", REAL_SEED_REUSE_COMPONENTS)
    monkeypatch.setattr(promotion, "EVIDENCE_BEARING_JOBS", REAL_EVIDENCE_BEARING_JOBS)
    root = Path(__file__).parents[1]
    report = promotion.audit_seeds(root / "research/jobs")
    assert report["used_seed_count"] >= 211
    assert set(promotion.E1_SEEDS) <= set(report["used_seeds"])
    assert all(entry["reason"] is not None for entry in report["overlaps"])

    # V1D reanalyses V1's snapshots. Its run identifiers name the source runs, so
    # it must never be recorded as a consumer: doing so once manufactured a bogus
    # V1/V1D seed overlap and a component entry invented to legitimate it.
    v1d = report["jobs"]["V1D-STATIONARITY-DIAGNOSTIC-C4"]
    assert v1d["seeds"] == []
    assert v1d["reference_job"] is True
    assert v1d["references"]["result.json:run_ids"] == [6101, 6203, 6301, 6407, 6503]
    assert not any(
        "V1D-STATIONARITY-DIAGNOSTIC-C4" in entry["jobs"] for entry in report["overlaps"]
    )

    # Every job that records no seed provenance must justify that with a waiver.
    for job in report["jobs_without_seed_evidence"]:
        assert report["jobs"][job]["has_seed_waiver"] is True

    # Each authorisation must rest on a verified property, not on prose: the
    # component's basis is re-derived from the repository on every run.
    assert {entry["basis"] for entry in report["overlaps"]} == {
        "same_experiment_reexecution",
        "historical_collision",
        "declared_paired_rerun",
    }
    # The grandfathered collisions stay tolerable only while they miss every job
    # that the calibration bounds or the confirmatory claim depend on.
    assert report["evidence_seed_count"] == 174
    historical = {
        entry["seed"] for entry in report["overlaps"] if entry["status"] == "grandfathered"
    }
    evidence = {seed for job in promotion.EVIDENCE_BEARING_JOBS for seed in report["jobs"][job]["seeds"]}
    assert historical and not (historical & evidence)

