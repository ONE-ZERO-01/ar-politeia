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


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return payload


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )


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
    return {
        "calibration": calibration,
        "calibration_sha256": actual_calibration_sha,
        "result_sha256": _sha256(result_path),
        "config_sha256": _sha256(config_path),
    }


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


def prepare(root: Path, calibration: Path, result: Path, v1f_config: Path, source_commit: str) -> None:
    if len(source_commit) != 40 or any(character not in "0123456789abcdef" for character in source_commit):
        raise ValueError("source_commit must be a full 40-character lowercase Git SHA")
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
    prepare_parser = subparsers.add_parser("prepare")
    prepare_parser.add_argument("--calibration", required=True)
    prepare_parser.add_argument("--result", required=True)
    prepare_parser.add_argument("--v1f-config", required=True)
    prepare_parser.add_argument("--source-commit", required=True)
    finalize_parser = subparsers.add_parser("finalize")
    finalize_parser.add_argument("--v0g-result", required=True)
    finalize_parser.add_argument("--binary", required=True)
    args = parser.parse_args(argv)
    if args.command == "prepare":
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
