#!/usr/bin/env python3
"""Deterministically promote a passing V1F calibration into V0G/E1-C4 jobs.

This module creates declarations only.  It never executes the simulator and is
safe to test locally.  ``prepare`` creates a non-authorizing candidate lock and
the V0G/E1 declarations.  ``finalize`` requires a passing V0G result and its
rebuilt OpenMP-OFF binary before it makes the lock final and E1 executable.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import shutil
from pathlib import Path
from typing import Any, Mapping, Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[3]
V1F_ID = "V1F-NONFLAT-CALIBRATION-C4"
V0G_ID = "V0G-SIMULATOR-TESTS-C4"
E1_ID = "E1-MATCHED-LANDSCAPES-C4"

E1_SEEDS = (
    11657, 11677, 11681, 11689, 11699, 11701, 11717, 11719,
    11731, 11743, 11777, 11779, 11783, 11789, 11801, 11807,
    11813, 11821, 11827, 11831, 11833, 11839, 11863, 11867,
    11887, 11897, 11903, 11909, 11923, 11927, 11933, 11939,
    11941, 11953, 11959, 11969, 11971, 11981, 11987, 12007,
    12011, 12037, 12041, 12043, 12049, 12071, 12073, 12097,
    12101, 12107, 12109, 12113, 12119, 12143, 12149, 12157,
    12161, 12163, 12197, 12203, 12211, 12227, 12239, 12241,
)

EFFECT_METRICS = (
    "resource_density_spearman_rho",
    "density_morans_i",
    "occupancy_entropy",
    "wealth_gini",
)
SCIENTIFIC_SESOI = {
    "resource_density_spearman_rho": 0.05,
    "density_morans_i": 0.05,
    "occupancy_entropy": 0.025,
    "wealth_gini": 0.025,
}
ABSOLUTE_GATE_BOUNDS = {
    **SCIENTIFIC_SESOI,
    "zero_wealth_fraction": 0.01,
}
MODEL_PARAMETERS = {
    "bounds": [0.0, 100.0, 0.0, 100.0],
    "dt": 0.005,
    "total_time": 4500.0,
    "output_time_interval": 5.0,
    "steady_snapshots": 144,
    "stationarity_max_normalized_drift": 0.1,
    "stationarity_min_ess": 4.0,
    "stationarity_reversal_span_sigma": 2.0,
    "stationarity_gate_unit": "condition_ensemble_two_window",
    "temperature": 0.5,
    "friction": 1.0,
    "social_strength": 0.0,
    "interaction_range": 2.5,
    "exchange_rate": 0.5,
    "exchange_noise_strength": 0.05,
    "exchange_reversion_rate": 1.0,
    "epsilon_log_sigma": 0.5,
    "base_production": 0.01,
    "consumption_rate": 0.0,
    "wealth_decay_rate": 0.02,
    "terrain_force_scale": 1.0,
    "terrain_production_scale": 1.0,
    "mean_wealth": 5.0,
    "strict_numerics": True,
    "confirmative_mode": True,
}
V1F_WORKSPACE_ARTIFACTS = (
    "run_specs.json",
    "matched_input_audit.json",
    "replicate_metrics.csv",
    "stationarity_report.json",
    "ensemble_stationarity_report.json",
    "steady_estimand_report.json",
    "numerical_calibration.json",
    "result.json",
)


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return payload


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _relative(root: Path, path: Path) -> str:
    resolved_root = root.resolve()
    resolved_path = path.resolve()
    if resolved_path != resolved_root and resolved_root not in resolved_path.parents:
        raise ValueError(f"path escapes project root: {path}")
    return resolved_path.relative_to(resolved_root).as_posix()


def validate_v1f(
    calibration_path: Path, result_path: Path, config_path: Path
) -> dict[str, Any]:
    calibration = _read_json(calibration_path)
    result = _read_json(result_path)
    config = _read_json(config_path)
    if calibration.get("experiment") != V1F_ID or calibration.get("pass") is not True:
        raise RuntimeError("V1F calibration is missing or did not pass")
    if result.get("experiment") != V1F_ID or result.get("pass") is not True:
        raise RuntimeError("V1F result is missing or did not pass")
    if result.get("status") not in {
        "completed",
        "completed_passed_gate",
        "executed_passed",
    }:
        raise RuntimeError("V1F result is not complete")
    if result.get("execution_completed") is not True:
        raise RuntimeError("V1F execution completion is not certified")
    if config.get("experiment_id") != V1F_ID:
        raise RuntimeError("V1F config has the wrong experiment_id")
    seeds = config.get("seeds", [])
    conditions = config.get("conditions", [])
    if not all(isinstance(item, Mapping) for item in conditions) or (
        len(seeds) != 64
        or len(set(seeds)) != 64
        or len(conditions) != 15
        or len({item.get("name") for item in conditions}) != 15
    ):
        raise RuntimeError("V1F must bind exactly 64 seeds and 15 conditions")
    if result.get("runs_completed") != 960 or result.get("run_failures") != 0:
        raise RuntimeError("V1F does not contain a clean 960-run completion")

    required_layers = {
        "invariants",
        "timestep_convergence",
        "storage_order_sensitivity",
        "stationarity",
        "precision",
        "adjacent_window_stability",
    }
    layers = calibration.get("gate_layers")
    if not isinstance(layers, Mapping) or any(layers.get(key) is not True for key in required_layers):
        raise RuntimeError("V1F did not pass every numerical and steady-estimand gate")
    numerical = calibration.get("numerical_resolution_limits")
    if not isinstance(numerical, Mapping):
        raise RuntimeError("V1F has no numerical_resolution_limits")
    for metric in EFFECT_METRICS:
        value = numerical.get(metric)
        if not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
            raise RuntimeError(f"V1F numerical limit is invalid for {metric}")

    expected_calibration_sha = result.get("calibration_sha256")
    actual_calibration_sha = _sha256(calibration_path)
    if not isinstance(expected_calibration_sha, str) or len(expected_calibration_sha) != 64:
        raise RuntimeError("V1F result does not contain a calibration SHA-256")
    if expected_calibration_sha != actual_calibration_sha:
        raise RuntimeError("V1F result does not bind the supplied calibration")
    expected_config_sha = result.get("config_sha256")
    if not isinstance(expected_config_sha, str) or len(expected_config_sha) != 64:
        raise RuntimeError("V1F result does not contain a config SHA-256")
    if expected_config_sha != _sha256(config_path):
        raise RuntimeError("V1F result does not bind the supplied config")

    frozen_from_v1f = {
        "population": 1000,
        "grid_shape": [64, 64],
        "total_time": 4500.0,
        "output_time_interval": 5.0,
        "steady_snapshots": 144,
        "omp_threads": 1,
        "parallel": 8,
        "per_run_timeout_seconds": 10800,
    }
    for key, expected in frozen_from_v1f.items():
        if config.get(key) != expected:
            raise RuntimeError(f"V1F config changed frozen field {key}")
    for key, expected in MODEL_PARAMETERS.items():
        if key == "dt":
            continue
        if config.get(key) != expected:
            raise RuntimeError(f"V1F config changed frozen model field {key}")
    expected_gate_fields = {
        "independent_precision_absolute_half_widths": ABSOLUTE_GATE_BOUNDS,
        "independent_precision_relative_half_widths": {"wealth_variance": 0.2},
        "adjacent_window_absolute_bounds": ABSOLUTE_GATE_BOUNDS,
        "adjacent_window_relative_bounds": {"wealth_variance": 0.1},
    }
    for key, expected in expected_gate_fields.items():
        if config.get(key) != expected:
            raise RuntimeError(f"V1F config changed frozen gate field {key}")
    if sorted(float(value) for value in config.get("timesteps", [])) != [0.005, 0.01, 0.02]:
        raise RuntimeError("V1F does not contain the frozen three timesteps")
    expected_condition_names = {
        f"{landscape}-dt-{dt}"
        for landscape in ("smooth", "clustered", "shuffled")
        for dt in ("0.02", "0.01", "0.005")
    } | {
        f"order-{order}-dt-{dt}"
        for order in ("canonical", "permuted")
        for dt in ("0.02", "0.01", "0.005")
    }
    if {str(item["name"]) for item in conditions} != expected_condition_names:
        raise RuntimeError("V1F condition matrix differs from the frozen 15-cell design")
    if set(E1_SEEDS) & set(seeds):
        raise RuntimeError("E1 seeds overlap V1F calibration seeds")
    calibrated_binary_sha256 = result.get("binary_sha256")
    if (
        not isinstance(calibrated_binary_sha256, str)
        or len(calibrated_binary_sha256) != 64
        or any(character not in "0123456789abcdef" for character in calibrated_binary_sha256)
    ):
        raise RuntimeError("V1F archive does not bind the calibrated reference binary")
    return {
        "calibration": calibration,
        "calibration_sha256": actual_calibration_sha,
        "result_sha256": _sha256(result_path),
        "config_sha256": _sha256(config_path),
        "binary_sha256": calibrated_binary_sha256,
    }


def _failed_v1f_cells(
    calibration: Mapping[str, Any], steady: Mapping[str, Any]
) -> tuple[list[str], list[str], dict[str, int]]:
    timestep: list[str] = []
    for landscape, metrics in calibration.get("discretization", {}).items():
        if not isinstance(metrics, Mapping):
            continue
        for metric, values in metrics.items():
            if isinstance(values, Mapping) and values.get("pass") is not True:
                timestep.append(f"{landscape}/{metric}")
    storage = [
        str(metric)
        for metric, values in calibration.get("storage_order_sensitivity", {}).items()
        if isinstance(values, Mapping) and values.get("pass") is not True
    ]
    failed_precision_metrics: dict[str, int] = {}
    for condition in steady.get("conditions", {}).values():
        if not isinstance(condition, Mapping):
            continue
        for metric, values in condition.get("metrics", {}).items():
            if not isinstance(values, Mapping):
                continue
            precision = values.get("independent_replicate_precision")
            if isinstance(precision, Mapping) and precision.get("pass") is not True:
                failed_precision_metrics[str(metric)] = (
                    failed_precision_metrics.get(str(metric), 0) + 1
                )
    return sorted(timestep), sorted(storage), failed_precision_metrics


def archive_v1f(root: Path, job_dir: Path, jobctl_dir: Path) -> dict[str, Any]:
    """Validate and compact a completed V1F workspace into tracked evidence."""
    root = root.resolve()
    job_dir = job_dir.resolve()
    jobctl_dir = jobctl_dir.resolve()
    _relative(root, job_dir)
    _relative(root, jobctl_dir)
    if job_dir.name != V1F_ID or jobctl_dir.name != V1F_ID:
        raise ValueError("archive-v1f requires the V1F job and jobctl directories")

    config_path = job_dir / "config.json"
    workspace = job_dir / "workspace"
    config = _read_json(config_path)
    calibration_path = workspace / "numerical_calibration.json"
    calibration = _read_json(calibration_path)
    raw_result_path = workspace / "result.json"
    raw_result = _read_json(raw_result_path)
    steady_path = workspace / "steady_estimand_report.json"
    steady = _read_json(steady_path)
    matched_audit = _read_json(workspace / "matched_input_audit.json")
    jobctl_result = _read_json(jobctl_dir / "result.json")
    jobctl_spec = _read_json(jobctl_dir / "spec.json")

    if config.get("experiment_id") != V1F_ID:
        raise RuntimeError("V1F config has the wrong experiment_id")
    if raw_result.get("experiment") != V1F_ID or raw_result.get("status") != "completed":
        raise RuntimeError("V1F workspace result is not complete")
    if calibration.get("experiment") != V1F_ID:
        raise RuntimeError("V1F workspace calibration has the wrong experiment")
    if not isinstance(calibration.get("pass"), bool):
        raise RuntimeError("V1F calibration has no boolean verdict")
    if raw_result.get("pass") is not calibration.get("pass"):
        raise RuntimeError("V1F result and calibration verdicts disagree")
    if raw_result.get("calibration_sha256") != _sha256(calibration_path):
        raise RuntimeError("V1F workspace result does not bind its calibration")
    if raw_result.get("config_sha256") != _sha256(config_path):
        raise RuntimeError("V1F workspace result does not bind its config")
    if jobctl_spec.get("config_sha256") != _sha256(config_path):
        raise RuntimeError("jobctl spec does not bind the V1F config")
    jobctl_artifacts = jobctl_result.get("artifacts", [])
    if (
        jobctl_result.get("exit_code") != 0
        or jobctl_result.get("timed_out") is not False
        or not isinstance(jobctl_artifacts, list)
        or any(item.get("valid") is not True for item in jobctl_artifacts)
    ):
        raise RuntimeError("jobctl did not record a clean V1F execution")
    recorded_artifacts = {
        Path(str(item.get("path", ""))).name for item in jobctl_artifacts
    }
    if recorded_artifacts != set(V1F_WORKSPACE_ARTIFACTS):
        raise RuntimeError("jobctl artifact declaration differs from V1F outputs")
    if matched_audit.get("pass") is not True:
        raise RuntimeError("V1F matched-input audit did not pass")

    run_specs_payload = _read_json(workspace / "run_specs.json")
    run_specs = run_specs_payload.get("runs")
    if not isinstance(run_specs, list):
        raise RuntimeError("V1F run_specs.json has no runs list")
    expected_run_count = len(config.get("seeds", [])) * len(config.get("conditions", []))
    if expected_run_count != 960 or len(run_specs) != expected_run_count:
        raise RuntimeError("V1F must contain exactly 960 run specs")
    expected_run_ids = {str(spec.get("run_id")) for spec in run_specs}
    if len(expected_run_ids) != expected_run_count or "None" in expected_run_ids:
        raise RuntimeError("V1F run IDs are missing or duplicated")

    marker_paths = sorted((workspace / "runs").glob("*/completion.json"))
    if len(marker_paths) != expected_run_count:
        raise RuntimeError(
            f"V1F completion markers are incomplete: {len(marker_paths)}/{expected_run_count}"
        )
    markers = [_read_json(path) for path in marker_paths]
    marker_run_ids = {str(marker.get("run_id")) for marker in markers}
    if marker_run_ids != expected_run_ids:
        raise RuntimeError("V1F completion markers do not match run specs")
    if any(marker.get("status") != "completed" for marker in markers):
        raise RuntimeError("V1F contains a non-completed marker")
    health_paths = [path.parent / "health.json" for path in marker_paths]
    if any(not path.is_file() for path in health_paths):
        raise RuntimeError("V1F has a completed run without health.json")
    if any(not isinstance(_read_json(path), Mapping) for path in health_paths):
        raise RuntimeError("V1F contains an invalid health.json payload")
    binary_hashes = {marker.get("binary_sha256") for marker in markers}
    if len(binary_hashes) != 1 or not all(
        isinstance(value, str) and len(value) == 64 for value in binary_hashes
    ):
        raise RuntimeError("V1F completion markers do not bind one reference binary")
    binary_path = (root / str(config.get("binary", ""))).resolve()
    _relative(root, binary_path)
    if not binary_path.is_file() or _sha256(binary_path) not in binary_hashes:
        raise RuntimeError("V1F completion markers do not match the reference binary")
    if {marker.get("omp_threads") for marker in markers} != {1}:
        raise RuntimeError("V1F completion markers do not all use OMP=1")

    for name in V1F_WORKSPACE_ARTIFACTS:
        path = workspace / name
        if not path.is_file() or path.stat().st_size == 0:
            raise RuntimeError(f"V1F workspace artifact is missing or empty: {name}")
    artifact_hashes = {
        name: _sha256(workspace / name) for name in V1F_WORKSPACE_ARTIFACTS
    }
    failed_timestep, failed_storage, failed_precision = _failed_v1f_cells(
        calibration, steady
    )
    conditions = steady.get("conditions", {})
    if not isinstance(conditions, Mapping) or len(conditions) != 9:
        raise RuntimeError("V1F steady report must contain nine timestep conditions")
    if steady.get("replicates_per_condition") != 64:
        raise RuntimeError("V1F steady report must contain 64 replicates per condition")
    gate_layers = calibration.get("gate_layers", {})
    required_gate_layers = {
        "invariants",
        "timestep_convergence",
        "storage_order_sensitivity",
        "stationarity",
        "precision",
        "adjacent_window_stability",
    }
    if not isinstance(gate_layers, Mapping) or any(
        not isinstance(gate_layers.get(key), bool) for key in required_gate_layers
    ):
        raise RuntimeError("V1F calibration gate layers are incomplete")
    expected_steady_flags = {
        "stationarity": "tail_stationarity_valid",
        "adjacent_window_stability": "adjacent_window_stability_valid",
        "precision": "independent_replicate_precision_valid",
    }
    for calibration_key, steady_key in expected_steady_flags.items():
        if gate_layers.get(calibration_key) is not steady.get(steady_key):
            raise RuntimeError(
                f"V1F calibration and steady report disagree on {calibration_key}"
            )

    source_commit = jobctl_spec.get("commit_id")
    if (
        not isinstance(source_commit, str)
        or len(source_commit) != 40
        or any(character not in "0123456789abcdef" for character in source_commit)
    ):
        raise RuntimeError("jobctl spec does not contain a full lowercase source commit")
    elapsed_seconds = [float(marker.get("elapsed_seconds", 0.0)) for marker in markers]
    if any(not math.isfinite(value) or value < 0.0 for value in elapsed_seconds):
        raise RuntimeError("V1F completion markers contain invalid elapsed time")
    jobctl_wall_seconds = float(jobctl_result.get("wall_seconds", 0.0))
    if not math.isfinite(jobctl_wall_seconds) or jobctl_wall_seconds < 0.0:
        raise RuntimeError("jobctl result contains invalid wall time")

    tracked_calibration_path = job_dir / "numerical_calibration.json"
    tracked_calibration_temp = tracked_calibration_path.with_suffix(".json.tmp")
    shutil.copyfile(calibration_path, tracked_calibration_temp)
    os.replace(tracked_calibration_temp, tracked_calibration_path)
    compact_result = {
        "experiment": V1F_ID,
        "status": (
            "completed_passed_gate"
            if calibration.get("pass") is True
            else "completed_failed_gate"
        ),
        "pass": bool(calibration.get("pass")),
        "execution_completed": True,
        "runs_planned": expected_run_count,
        "runs_completed": len(markers),
        "run_failures": 0,
        "execution_host": "umi",
        "source_commit": source_commit,
        "binary_sha256": next(iter(binary_hashes)),
        "config_sha256": _sha256(config_path),
        "calibration_sha256": _sha256(tracked_calibration_path),
        "elapsed_cpu_hours": sum(elapsed_seconds) / 3600.0,
        "maximum_single_run_seconds": max(elapsed_seconds),
        "jobctl_wall_seconds": jobctl_wall_seconds,
        "gate_layers": {
            "invariants": gate_layers.get("invariants") is True,
            "timestep_convergence": gate_layers.get("timestep_convergence") is True,
            "storage_order_sensitivity": gate_layers.get("storage_order_sensitivity") is True,
            "tail_stationarity": gate_layers.get("stationarity") is True,
            "adjacent_window_stability": gate_layers.get("adjacent_window_stability") is True,
            "independent_replicate_precision": gate_layers.get("precision") is True,
        },
        "temporal_ess_diagnostic_valid": bool(
            steady.get("temporal_ess_diagnostic_valid")
        ),
        "steady_estimand_layer": {
            "conditions": len(conditions),
            "replicates_per_condition": steady.get("replicates_per_condition"),
            "tail_stationarity_failed_conditions": sum(
                item.get("tail_stationarity_pass") is not True
                for item in conditions.values()
            ),
            "adjacent_window_failed_conditions": sum(
                item.get("adjacent_window_stability_pass") is not True
                for item in conditions.values()
            ),
            "independent_precision_failed_conditions": sum(
                item.get("independent_replicate_precision_pass") is not True
                for item in conditions.values()
            ),
            "temporal_ess_diagnostic_failed_conditions": sum(
                item.get("temporal_ess_diagnostic_pass") is not True
                for item in conditions.values()
            ),
            "independent_precision_failed_metric_cells": sum(
                failed_precision.values()
            ),
            "failed_precision_metrics": failed_precision,
        },
        "numerical_resolution_limits": calibration.get(
            "numerical_resolution_limits", {}
        ),
        "failed_timestep_cells": failed_timestep,
        "failed_storage_order_metrics": failed_storage,
        "workspace_artifact_sha256": artifact_hashes,
        "conclusion": (
            "V1F completed 960/960 runs and passed every frozen calibration gate."
            if calibration.get("pass") is True
            else "V1F completed 960/960 runs but failed one or more frozen calibration gates."
        ),
        "next_action": (
            "Run Cycle 4 promotion prepare; E1 remains blocked until V0G and finalization pass."
            if calibration.get("pass") is True
            else "Archive the independent negative calibration and keep E1 blocked."
        ),
        "evidence_boundary": (
            "Independent numerical calibration only; no Cycle 4 landscape-effect claim is supported."
        ),
    }
    compact_result_path = job_dir / "result.json"
    _write_json(compact_result_path, compact_result)
    manifest = {
        "exit_code": 0,
        "timed_out": False,
        "wall_seconds": jobctl_result.get("wall_seconds"),
        "jobctl_reconcile": "completed",
        "artifacts": [
            {
                "path": f"workspace/{name}",
                "sha256": artifact_hashes[name],
                "valid": True,
            }
            for name in V1F_WORKSPACE_ARTIFACTS
        ],
    }
    _write_json(job_dir / "manifest.json", manifest)
    if compact_result["pass"] is True:
        validate_v1f(tracked_calibration_path, compact_result_path, config_path)
    return compact_result


def _candidate_lock(source_commit: str, v1f: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "lock_id": "ar-politeia-cycle4-confirmatory-v1",
        "status": "candidate",
        "confirmatory_execution_authorized": False,
        "locked_before_confirmatory_outcomes": True,
        "promotion_base_commit": source_commit,
        "source_commit": "pending clean V0G checkout",
        "analysis_commit": "pending clean V0G checkout",
        "authorized_experiments": [],
        "numerical_calibration": {
            "experiment": V1F_ID,
            "path": f"research/jobs/{V1F_ID}/numerical_calibration.json",
            "sha256": v1f["calibration_sha256"],
            "result_sha256": v1f["result_sha256"],
            "config_sha256": v1f["config_sha256"],
            # The numerical resolution limits were measured by executing this exact
            # binary. E1-C4 must execute the same artifact, so the SHA is carried
            # forward and enforced at finalize time.
            "reference_binary_sha256": v1f["binary_sha256"],
            "numerical_resolution_limits": v1f["calibration"]["numerical_resolution_limits"],
        },
        "parameters": {
            "population": 1000,
            "grid_shape": [64, 64],
            **MODEL_PARAMETERS,
            "wealth_log_sigma": 0.01,
            "mpi_enabled": False,
            "ranks": 1,
            "omp_threads": 1,
            "parallel": 8,
            "per_run_timeout_seconds": 10800,
            "familywise_alpha": 0.05,
            "bootstrap_samples": 10000,
            "analysis_seed": 9173,
            "scientific_sesoi": SCIENTIFIC_SESOI,
            "independent_precision_absolute_half_widths": ABSOLUTE_GATE_BOUNDS,
            "independent_precision_relative_half_widths": {"wealth_variance": 0.2},
            "adjacent_window_absolute_bounds": ABSOLUTE_GATE_BOUNDS,
            "adjacent_window_relative_bounds": {"wealth_variance": 0.1},
        },
        "design_contract": {
            "conditions": ["clustered", "shuffled"],
            "paired_difference": "clustered-minus-shuffled",
            "primary_family": list(EFFECT_METRICS[:3]),
            "secondary_family": ["wealth_gini"],
            "run_count": 128,
            "seed_count": 64,
            "full_initial_state_match_required": True,
            "resource_histogram_and_accessible_area_match_required": True,
            "temporal_ess_role": "diagnostic_only",
            "valid_null_policy": "A passed analysis gate without a primary effect beyond the effective threshold is retained as valid null/equivalence evidence.",
        },
        "amendment_policy": "After finalization, any outcome-informed change requires a new lock version and research cycle.",
    }


def _e1_config(root: Path, lock: Mapping[str, Any], *, binary_sha256: str | None) -> dict[str, Any]:
    lock_path = root / "research/parameter_lock.cycle4.json"
    config = {
        "experiment_id": E1_ID,
        "binary": f"research/jobs/{V0G_ID}/workspace/build-off/src/politeia",
        "summary_result": f"research/jobs/{E1_ID}/result.json",
        "numerical_calibration": f"research/jobs/{V1F_ID}/numerical_calibration.json",
        "numerical_calibration_sha256": lock["numerical_calibration"]["sha256"],
        "parameter_lock": "research/parameter_lock.cycle4.json",
        "parameter_lock_sha256": _sha256(lock_path),
        "seeds": list(E1_SEEDS),
        **lock["parameters"],
    }
    if binary_sha256 is not None:
        config["binary_sha256"] = binary_sha256
    return config


def _experiment(config: Mapping[str, Any], source_commit: str) -> dict[str, Any]:
    return {
        "id": E1_ID,
        "type": "command",
        "mode": "server",
        "priority": "P0",
        "claim_ids": ["C2-LANDSCAPE-C4"],
        "depends_on": [V1F_ID, V0G_ID],
        "objective": "Estimate the paired clustered-minus-shuffled Cycle 4 effect under the frozen V1F numerical and two-window steady-estimand contract.",
        "command": [
            "python3", "research/src/experiments/run_landscape_study.py",
            "--experiment", E1_ID,
            "--config", f"research/jobs/{E1_ID}/config.json",
            "--output-dir", f"research/jobs/{E1_ID}/workspace",
        ],
        "config": f"research/jobs/{E1_ID}/config.json",
        "config_sha256": "set after config.json is written",
        "commit_id": source_commit,
        "env_snapshot": f"research/jobs/{E1_ID}/env.txt",
        "seeds": list(E1_SEEDS),
        "data_checksums": {
            "external_data": "none",
            "generated_inputs": "SHA-256 values are written to workspace/matched_input_audit.json before execution",
            "dependency_calibration": config["numerical_calibration_sha256"],
            "parameter_lock": config["parameter_lock_sha256"],
            "reference_binary": config.get("binary_sha256", "pending V0G"),
        },
        "artifacts": [
            "result.json", "replicate_metrics.csv", "paired_effects.json",
            "matched_input_audit.json", "stationarity_report.json",
            "steady_estimand_report.json", "parameter_lock_audit.json", "run_specs.json",
        ],
        "timeout_seconds": 86400,
        "gpu_count": 0,
        "failure_policy": "Missing runs or failed invariant/stationarity/precision gates make the result inconclusive; a valid null is retained as evidence.",
    }


def _write_support_files(root: Path, source_commit: str, config: Mapping[str, Any]) -> None:
    e1_dir = root / f"research/jobs/{E1_ID}"
    e1_dir.mkdir(parents=True, exist_ok=True)
    (e1_dir / "commit.txt").write_text(source_commit + "\n", encoding="utf-8")
    (e1_dir / "env.txt").write_text(
        "host=umi\nexecution=CPU_reference\nomp_threads=1\nparallel=8\nmpi=OFF\n"
        f"gpu_count=0\nsource_commit={source_commit}\n",
        encoding="utf-8",
    )
    (e1_dir / "seeds.txt").write_text(
        "\n".join(str(seed) for seed in E1_SEEDS) + "\n", encoding="utf-8"
    )
    outputs = _experiment(config, source_commit)["artifacts"]
    (e1_dir / "outputs.txt").write_text("\n".join(outputs) + "\n", encoding="utf-8")
    (e1_dir / "data_checksums.txt").write_text(
        "external_data=none\n"
        f"dependency_calibration={config['numerical_calibration_sha256']}\n"
        f"parameter_lock={config['parameter_lock_sha256']}\n"
        f"reference_binary={config.get('binary_sha256', 'pending V0G')}\n",
        encoding="utf-8",
    )
    _write_json(
        e1_dir / "computational_strategy.json",
        {
            "approach": "Run 64 matched seed pairs as eight OMP=1 CPU reference processes.",
            "evidence_role": "confirmatory synthetic-mechanism experiment",
            "evidence_boundary": "Supports only the frozen synthetic landscape-mechanism claim, not a historical-state claim.",
            "supports_core_claim": True,
            "reference_method": "validated OpenMP-OFF C++ simulator binary",
            "validation_points": ["Python contract suite", "OpenMP OFF CTest", "OpenMP ON CTest"],
            "agreement": {"criterion": "all tests pass and the executed binary SHA-256 matches the declaration"},
            "reference_validation_required": True,
            "validation_artifact": "parameter_lock_audit.json",
        },
    )
    experiment = _experiment(config, source_commit)
    experiment["config_sha256"] = _sha256(e1_dir / "config.json")
    _write_json(e1_dir / "experiment.json", experiment)


def _assert_no_e1_outcomes(root: Path) -> None:
    e1_dir = root / f"research/jobs/{E1_ID}"
    forbidden = (
        e1_dir / "result.json",
        e1_dir / "paired_effects.json",
        e1_dir / "workspace/result.json",
        e1_dir / "workspace/paired_effects.json",
        e1_dir / "workspace/replicate_metrics.csv",
    )
    runs_dir = e1_dir / "workspace/runs"
    execution_started = runs_dir.exists() and any(
        runs_dir.rglob("completion.json")
    )
    if any(path.exists() for path in forbidden) or execution_started:
        raise RuntimeError("refusing to change the Cycle 4 lock after E1 outcomes exist")


def _assert_e1_seeds_unused(root: Path) -> None:
    e1_seed_set = set(E1_SEEDS)
    for path in (root / "research/jobs").glob("*/config.json"):
        if path.parent.name == E1_ID:
            continue
        payload = _read_json(path)
        seeds = payload.get("seeds", [])
        if isinstance(seeds, list) and e1_seed_set & set(seeds):
            overlap = sorted(e1_seed_set & set(seeds))
            raise RuntimeError(
                f"E1 seeds are no longer unseen; overlap in {path.parent.name}: {overlap}"
            )


def _require_real_commit(root: Path, source_commit: str) -> None:
    """Reject a source commit that is well-formed but does not exist.

    A fabricated or stale SHA would otherwise be written into the V0G
    declaration and the candidate lock, where it is descriptive only and
    therefore never fails loudly: V0G records its own live ``HEAD``, so the
    mismatch would surface only later as an inexplicable record. Fail here.

    The clean-working-tree requirement is deliberately *not* enforced here:
    ``prepare`` itself writes tracked declarations, so its own output makes the
    tree dirty and a second run would then refuse. That requirement belongs to
    V0G, which records ``working_tree_clean`` at run time, and to ``finalize``,
    which rejects a V0G result without it.
    """
    import subprocess

    probe = subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", f"{source_commit}^{{commit}}"],
        cwd=root,
        capture_output=True,
        text=True,
    )
    resolved = probe.stdout.strip()
    if probe.returncode != 0 or resolved != source_commit:
        raise ValueError(
            f"source_commit does not resolve to a commit in this repository: {source_commit}"
        )


def prepare(root: Path, calibration: Path, result: Path, v1f_config: Path, source_commit: str) -> None:
    if len(source_commit) != 40 or any(character not in "0123456789abcdef" for character in source_commit):
        raise ValueError("source_commit must be a full 40-character lowercase Git SHA")
    _require_real_commit(root, source_commit)
    for path in (calibration, result, v1f_config):
        _relative(root, path)
    _assert_no_e1_outcomes(root)
    _assert_e1_seeds_unused(root)
    v1f = validate_v1f(calibration, result, v1f_config)
    lock_path = root / "research/parameter_lock.cycle4.json"
    if lock_path.exists() and _read_json(lock_path).get("status") == "final":
        raise RuntimeError("refusing to replace the final Cycle 4 parameter lock")
    _write_json(lock_path, _candidate_lock(source_commit, v1f))

    v0g_dir = root / f"research/jobs/{V0G_ID}"
    v0g_dir.mkdir(parents=True, exist_ok=True)
    _write_json(
        v0g_dir / "config.json",
        {
            "experiment_id": V0G_ID,
            "source_commit": source_commit,
            "execution_host": "umi",
            "build_jobs": 4,
            "openmp_modes": [False, True],
            "mpi_enabled": False,
            "build_type": "Release",
            "run_pytest": True,
            "test_scope": "Final Cycle 4 lock/calibration/binary binding, matched E1-C4 runner, two-window gates, and all simulator invariants.",
        },
    )
    (v0g_dir / "commit.txt").write_text(source_commit + "\n", encoding="utf-8")
    (v0g_dir / "env.txt").write_text("host=umi\nexecution=python_pytest_and_cmake_ctest\nopenmp=OFF_and_ON\nmpi=OFF\nsimulation=none\n", encoding="utf-8")
    (v0g_dir / "seeds.txt").write_text("none\n", encoding="utf-8")
    (v0g_dir / "seed_waiver.txt").write_text("Implementation validation executes no numerical simulation.\n", encoding="utf-8")
    (v0g_dir / "outputs.txt").write_text("result.json\nenvironment.json\npytest.log\nctest-off.log\nctest-on.log\n", encoding="utf-8")
    (v0g_dir / "data_checksums.txt").write_text(f"source_tree=git_commit_{source_commit}\nexternal_data=none\n", encoding="utf-8")
    _write_json(v0g_dir / "computational_strategy.json", {
        "approach": "Run the full Python suite and rebuild/test the C++ reference with OpenMP OFF and ON on umi.",
        "evidence_role": "implementation validation",
        "evidence_boundary": "V0G validates code and bindings only and produces no scientific evidence.",
        "supports_core_claim": False,
    })

    lock = _read_json(lock_path)
    config = _e1_config(root, lock, binary_sha256=None)
    e1_dir = root / f"research/jobs/{E1_ID}"
    _write_json(e1_dir / "config.json", config)
    _write_support_files(root, source_commit, config)


def validate_v0g(result_path: Path) -> dict[str, Any]:
    result = _read_json(result_path)
    if result.get("experiment") != V0G_ID or result.get("pass") is not True:
        raise RuntimeError("V0G is missing or did not pass")
    if result.get("status") != "completed":
        raise RuntimeError("V0G did not complete")
    environment = result.get("environment")
    if not isinstance(environment, Mapping) or str(environment.get("host", "")).split(".", 1)[0] != "umi":
        raise RuntimeError("V0G was not executed on umi")
    if environment.get("working_tree_clean") is not True:
        raise RuntimeError("V0G did not validate a clean checkout")
    pytest_result = result.get("pytest")
    if not isinstance(pytest_result, Mapping) or pytest_result.get("returncode") != 0:
        raise RuntimeError("V0G Python suite did not pass")
    builds = result.get("builds")
    if not isinstance(builds, list) or len(builds) != 2:
        raise RuntimeError("V0G must contain OpenMP OFF and ON build results")
    modes = {item.get("openmp") for item in builds if isinstance(item, Mapping) and item.get("pass") is True}
    if modes != {False, True}:
        raise RuntimeError("V0G OpenMP OFF/ON CTest did not both pass")
    return result


def finalize(root: Path, v0g_result: Path, binary: Path) -> None:
    _relative(root, v0g_result)
    _relative(root, binary)
    _assert_no_e1_outcomes(root)
    result = validate_v0g(v0g_result)
    if not binary.is_file():
        raise FileNotFoundError(binary)
    lock_path = root / "research/parameter_lock.cycle4.json"
    lock = _read_json(lock_path)
    if lock.get("status") != "candidate" or lock.get("confirmatory_execution_authorized") is not False:
        raise RuntimeError("Cycle 4 lock is not an unexecuted candidate")
    validated_commit = result["environment"].get("source_commit")
    if (
        not isinstance(validated_commit, str)
        or len(validated_commit) != 40
        or any(character not in "0123456789abcdef" for character in validated_commit)
    ):
        raise RuntimeError("V0G did not record a full clean-checkout source commit")
    binary_sha256 = _sha256(binary)
    # The lock binds a SHA-256 of the simulator binary that E1-C4 will execute, so
    # the artifact must be the one the numerical calibration was measured on. Any
    # simulator source change after V1F silently produces a different binary; that
    # must fail loudly here rather than produce a lock whose calibration and
    # executable do not correspond.
    reference_binary_sha256 = (
        lock.get("numerical_calibration", {}).get("reference_binary_sha256")
        if isinstance(lock.get("numerical_calibration"), Mapping)
        else None
    )
    if (
        not isinstance(reference_binary_sha256, str)
        or len(reference_binary_sha256) != 64
    ):
        raise RuntimeError("candidate lock does not bind a calibrated reference binary")
    v0g_dir = (root / f"research/jobs/{V0G_ID}").resolve()
    resolved_binary = binary.resolve()
    if v0g_dir != resolved_binary and v0g_dir not in resolved_binary.parents:
        raise RuntimeError("finalize must bind a binary built inside the V0G workspace")
    if binary_sha256 != reference_binary_sha256:
        raise RuntimeError(
            "the binary bound for E1-C4 is not the calibrated reference binary: "
            f"calibrated {reference_binary_sha256}, rebuilt {binary_sha256}. "
            "The V1F numerical resolution limits were measured on the calibrated "
            "binary, so a simulator source change after calibration breaks the "
            "binding. Revert the simulator change (or recalibrate) before "
            "authorizing E1."
        )
    lock["status"] = "final"
    lock["confirmatory_execution_authorized"] = True
    lock["authorized_experiments"] = [E1_ID]
    lock["source_commit"] = validated_commit
    lock["analysis_commit"] = validated_commit
    lock["simulator_validation"] = {
        "experiment": V0G_ID,
        "result_sha256": _sha256(v0g_result),
        "validated_commit": validated_commit,
        "binary": _relative(root, binary),
        "binary_sha256": binary_sha256,
        "openmp_execution_mode": "OFF reference binary; OMP_NUM_THREADS=1",
    }
    _write_json(lock_path, lock)
    config = _e1_config(root, lock, binary_sha256=binary_sha256)
    e1_dir = root / f"research/jobs/{E1_ID}"
    _write_json(e1_dir / "config.json", config)
    _write_support_files(root, validated_commit, config)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    archive_parser = subparsers.add_parser("archive-v1f")
    archive_parser.add_argument(
        "--job-dir", default=f"research/jobs/{V1F_ID}"
    )
    archive_parser.add_argument(
        "--jobctl-dir", default=f".autoresearcher/jobs/{V1F_ID}"
    )
    prepare_parser = subparsers.add_parser("prepare")
    prepare_parser.add_argument("--calibration", required=True)
    prepare_parser.add_argument("--result", required=True)
    prepare_parser.add_argument("--v1f-config", required=True)
    prepare_parser.add_argument("--source-commit", required=True)
    finalize_parser = subparsers.add_parser("finalize")
    finalize_parser.add_argument("--v0g-result", required=True)
    finalize_parser.add_argument("--binary", required=True)
    args = parser.parse_args(argv)
    if args.command == "archive-v1f":
        archive_v1f(
            PROJECT_ROOT,
            (PROJECT_ROOT / args.job_dir).resolve(),
            (PROJECT_ROOT / args.jobctl_dir).resolve(),
        )
    elif args.command == "prepare":
        prepare(
            PROJECT_ROOT,
            (PROJECT_ROOT / args.calibration).resolve(),
            (PROJECT_ROOT / args.result).resolve(),
            (PROJECT_ROOT / args.v1f_config).resolve(),
            args.source_commit,
        )
    else:
        finalize(
            PROJECT_ROOT,
            (PROJECT_ROOT / args.v0g_result).resolve(),
            (PROJECT_ROOT / args.binary).resolve(),
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
