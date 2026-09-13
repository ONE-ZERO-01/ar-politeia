#!/usr/bin/env python3
"""Run the Cycle 4 V1 runtime pilot or registered numerical calibration on umi."""

from __future__ import annotations

import argparse
import json
import math
import platform
from collections import defaultdict
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

from landscape_study import sha256_file, write_json
from run_landscape_study import (
    PROJECT_ROOT,
    analyze_runs,
    execute_runs,
    load_json,
    prepare_inputs,
    project_path,
)


CALIBRATION_METRICS = (
    "resource_density_spearman_rho",
    "density_morans_i",
    "occupancy_entropy",
    "wealth_gini",
)


def _require_umi() -> None:
    if platform.node().split(".", 1)[0] != "umi":
        raise RuntimeError("V1 numerical workflows must run on host umi")


def _validate_conditions(conditions: Any) -> list[dict[str, Any]]:
    if not isinstance(conditions, list) or not conditions:
        raise ValueError("conditions must be a non-empty list")
    names: set[str] = set()
    validated: list[dict[str, Any]] = []
    for raw in conditions:
        if not isinstance(raw, Mapping):
            raise ValueError("each condition must be an object")
        condition = dict(raw)
        name = str(condition.get("name", ""))
        if not name or name in names:
            raise ValueError(f"condition names must be non-empty and unique: {name!r}")
        names.add(name)
        if str(condition.get("landscape")) not in {"smooth", "clustered", "shuffled"}:
            raise ValueError(f"unsupported V1 landscape in {name}")
        dt = float(condition.get("dt", 0.0))
        if not math.isfinite(dt) or dt <= 0.0:
            raise ValueError(f"condition {name} has invalid dt")
        component = str(condition.get("calibration_component", ""))
        if component not in {"timestep", "order"}:
            raise ValueError(f"condition {name} has invalid calibration_component")
        if component == "order":
            if condition.get("storage_order") not in {"canonical", "permuted"}:
                raise ValueError(f"order condition {name} requires a storage_order")
            if condition.get("temperature") != 0.0:
                raise ValueError(f"order condition {name} must set temperature=0")
            if condition.get("explicit_phase_state") is not True:
                raise ValueError(f"order condition {name} requires explicit_phase_state=true")
        validated.append(condition)
    return validated


def validate_full_matrix(config: Mapping[str, Any]) -> None:
    conditions = _validate_conditions(config.get("conditions"))
    seeds = config.get("seeds")
    if not isinstance(seeds, list) or len(set(seeds)) < 3:
        raise ValueError("full V1 requires at least three distinct seeds")
    expected_dts = sorted(float(value) for value in config.get("timesteps", []))
    if len(expected_dts) != 3 or len(set(expected_dts)) != 3:
        raise ValueError("full V1 requires exactly three distinct timesteps")

    timestep_cells = {
        (str(item["landscape"]), float(item["dt"]))
        for item in conditions
        if item["calibration_component"] == "timestep"
    }
    expected_cells = {
        (landscape, dt)
        for landscape in ("smooth", "clustered", "shuffled")
        for dt in expected_dts
    }
    if timestep_cells != expected_cells:
        raise ValueError("timestep matrix must be landscape(3) x dt(3) exactly")

    order_cells = {
        (str(item["landscape"]), float(item["dt"]), str(item["storage_order"]))
        for item in conditions
        if item["calibration_component"] == "order"
    }
    expected_order = {
        ("clustered", dt, storage)
        for dt in expected_dts
        for storage in ("canonical", "permuted")
    }
    if order_cells != expected_order:
        raise ValueError("order matrix must be clustered x dt(3) x storage_order(2) exactly")


def _weak_bound(values_a: Sequence[float], values_b: Sequence[float]) -> dict[str, float]:
    """Bound a replicate-level estimand difference without claiming pathwise coupling."""
    a = np.asarray(values_a, dtype=np.float64)
    b = np.asarray(values_b, dtype=np.float64)
    if a.shape != b.shape or a.ndim != 1 or a.size < 3:
        raise ValueError("weak convergence comparison requires >=3 matched replicates")
    if not np.all(np.isfinite(a)) or not np.all(np.isfinite(b)):
        raise ValueError("weak convergence comparison contains a non-finite metric")
    difference = a - b
    mean = float(difference.mean())
    sd = float(np.std(difference, ddof=1))
    standard_error = sd / math.sqrt(float(difference.size))
    return {
        "absolute_mean_difference": abs(mean),
        "signed_mean_difference": mean,
        "paired_sample_sd": sd,
        "standard_error": standard_error,
        "two_se_bound": abs(mean) + 2.0 * standard_error,
        "replicates": int(difference.size),
    }


def aggregate_v1(
    rows: Sequence[Mapping[str, Any]],
    config: Mapping[str, Any],
    output_dir: Path,
) -> dict[str, Any]:
    """Apply the preregistered weak-convergence and storage-order gates."""
    dts = sorted((float(value) for value in config["timesteps"]), reverse=True)
    coarse_dt, fine_dt, finest_dt = dts
    ceilings = config.get("numerical_error_ceilings")
    if not isinstance(ceilings, Mapping):
        raise ValueError("numerical_error_ceilings must be an object")
    if set(CALIBRATION_METRICS) - set(ceilings):
        raise ValueError("numerical_error_ceilings do not cover all calibration metrics")

    timestep: dict[tuple[str, int, float], Mapping[str, Any]] = {}
    order: dict[tuple[int, float, str], Mapping[str, Any]] = {}
    for row in rows:
        seed = int(row["seed"])
        dt = float(row["dt"])
        if row["calibration_component"] == "timestep":
            timestep[(str(row["landscape"]), seed, dt)] = row
        elif row["calibration_component"] == "order":
            order[(seed, dt, str(row["storage_order"]))] = row

    seeds = sorted({int(row["seed"]) for row in rows})
    discretization: dict[str, Any] = {}
    numerical_limits: dict[str, float] = {metric: 0.0 for metric in CALIBRATION_METRICS}
    timestep_pass = True
    for landscape in ("smooth", "clustered", "shuffled"):
        landscape_result: dict[str, Any] = {}
        for metric in CALIBRATION_METRICS:
            values = {
                dt: [float(timestep[(landscape, seed, dt)][metric]) for seed in seeds]
                for dt in dts
            }
            coarse_fine = _weak_bound(values[coarse_dt], values[fine_dt])
            fine_finest = _weak_bound(values[fine_dt], values[finest_dt])
            trend_tolerance = coarse_fine["two_se_bound"] + 2.0 * fine_finest[
                "standard_error"
            ]
            trend_pass = fine_finest["absolute_mean_difference"] <= trend_tolerance
            ceiling_pass = fine_finest["two_se_bound"] <= float(ceilings[metric])
            cell_pass = bool(trend_pass and ceiling_pass)
            timestep_pass = timestep_pass and cell_pass
            numerical_limits[metric] = max(
                numerical_limits[metric], fine_finest["two_se_bound"]
            )
            landscape_result[metric] = {
                "coarse_vs_fine": coarse_fine,
                "fine_vs_finest": fine_finest,
                "trend_pass": trend_pass,
                "ceiling": float(ceilings[metric]),
                "ceiling_pass": ceiling_pass,
                "pass": cell_pass,
            }
        discretization[landscape] = landscape_result

    order_sensitivity: dict[str, Any] = {}
    order_pass = True
    for metric in CALIBRATION_METRICS:
        by_dt: dict[str, Any] = {}
        bounds: dict[float, dict[str, float]] = {}
        for dt in dts:
            canonical = [float(order[(seed, dt, "canonical")][metric]) for seed in seeds]
            permuted = [float(order[(seed, dt, "permuted")][metric]) for seed in seeds]
            bounds[dt] = _weak_bound(canonical, permuted)
            by_dt[f"{dt:.17g}"] = bounds[dt]
        trend_pass = bounds[finest_dt]["absolute_mean_difference"] <= (
            bounds[coarse_dt]["two_se_bound"]
            + 2.0 * bounds[finest_dt]["standard_error"]
        )
        ceiling_pass = bounds[finest_dt]["two_se_bound"] <= float(ceilings[metric])
        discretization_dominates = (
            bounds[finest_dt]["two_se_bound"]
            <= numerical_limits[metric] + 2.0 * bounds[finest_dt]["standard_error"]
        )
        metric_pass = bool(trend_pass and ceiling_pass and discretization_dominates)
        order_pass = order_pass and metric_pass
        numerical_limits[metric] = max(
            numerical_limits[metric], bounds[finest_dt]["two_se_bound"]
        )
        order_sensitivity[metric] = {
            "by_dt": by_dt,
            "trend_pass": trend_pass,
            "ceiling": float(ceilings[metric]),
            "ceiling_pass": ceiling_pass,
            "bounded_by_discretization": discretization_dominates,
            "pass": metric_pass,
        }

    # Active non-flat runs include production and wealth decay, so total system
    # wealth is not conserved by design. Exchange conservation is already a V0
    # unit invariant. V1 only requires the source/sink trajectory to stay finite
    # and wealth to remain non-negative.
    total_wealth_drifts = [float(row["total_wealth_relative_drift"]) for row in rows]
    invariant_checks = {
        "wealth_nonnegative": min(float(row["minimum_wealth"]) for row in rows) >= -1e-12,
        "total_wealth_change_finite": all(math.isfinite(value) for value in total_wealth_drifts),
    }
    timestep_rows = [row for row in rows if row["calibration_component"] == "timestep"]
    stationarity_pass = all(bool(row["stationarity_pass"]) for row in timestep_rows)
    precision_pass = all(
        bool(item.get("precision_pass", False))
        for row in timestep_rows
        for item in row["stationarity_diagnostics"].values()
    )
    passed = bool(
        all(invariant_checks.values())
        and timestep_pass
        and order_pass
        and stationarity_pass
        and precision_pass
    )
    payload = {
        "experiment": "V1-NONFLAT-CALIBRATION-C4",
        "pass": passed,
        "scope": "non-flat weak timestep convergence plus deterministic exchange-order sensitivity",
        "timesteps": {"coarse": coarse_dt, "fine": fine_dt, "finest": finest_dt},
        "gate_layers": {
            "invariants": all(invariant_checks.values()),
            "timestep_convergence": timestep_pass,
            "storage_order_sensitivity": order_pass,
            "stationarity": stationarity_pass,
            "precision": precision_pass,
        },
        "invariant_checks": invariant_checks,
        "total_wealth_relative_drift_range": [
            min(total_wealth_drifts),
            max(total_wealth_drifts),
        ],
        "discretization": discretization,
        "storage_order_sensitivity": order_sensitivity,
        "numerical_resolution_limits": numerical_limits,
        "threshold_policy": (
            "Resolution limits bound numerical error only. Scientific relevance "
            "thresholds for E1 must be frozen separately before confirmatory runs."
        ),
        "pathwise_claim": False,
    }
    write_json(output_dir / "numerical_calibration.json", payload)
    return payload


def summarize_runtime_pilot(
    specs: Sequence[Mapping[str, Any]],
    config: Mapping[str, Any],
    output_dir: Path,
) -> dict[str, Any]:
    rates: dict[str, list[float]] = defaultdict(list)
    per_run: list[dict[str, Any]] = []
    pilot_time = float(config["total_time"])
    for spec in specs:
        marker = load_json(project_path(spec["run_dir"]) / "completion.json")
        elapsed = float(marker["elapsed_seconds"])
        steps = int(round(pilot_time / float(spec["dt"])))
        component = str(spec["calibration_component"])
        rates[component].append(elapsed / steps)
        per_run.append(
            {
                "run_id": spec["run_id"],
                "component": component,
                "dt": float(spec["dt"]),
                "steps": steps,
                "elapsed_seconds": elapsed,
                "seconds_per_step": elapsed / steps,
            }
        )
    target = config.get("target_design")
    if not isinstance(target, Mapping):
        raise ValueError("runtime pilot requires target_design")
    target_conditions = _validate_conditions(target.get("conditions"))
    target_seeds = target.get("seeds")
    if not isinstance(target_seeds, list) or len(target_seeds) < 3:
        raise ValueError("target_design requires at least three seeds")
    target_time = float(target["total_time"])
    safety_factor = float(target.get("runtime_safety_factor", 1.5))
    estimated_cpu_seconds = 0.0
    for condition in target_conditions:
        component = str(condition["calibration_component"])
        component_rates = rates.get(component)
        if not component_rates:
            raise ValueError(f"pilot has no runtime sample for {component}")
        target_steps = int(round(target_time / float(condition["dt"])))
        estimated_cpu_seconds += max(component_rates) * target_steps * len(target_seeds)
    estimated_cpu_seconds *= safety_factor
    parallel = int(target.get("parallel", 1))
    payload = {
        "experiment": "V1P-RUNTIME-PILOT-C4",
        "status": "completed",
        "pass": True,
        "non_evidentiary": True,
        "pilot_runs": per_run,
        "target_run_count": len(target_conditions) * len(target_seeds),
        "target_total_time": target_time,
        "runtime_safety_factor": safety_factor,
        "estimated_cpu_hours": estimated_cpu_seconds / 3600.0,
        "estimated_wall_hours_at_declared_parallelism": estimated_cpu_seconds
        / max(1, parallel)
        / 3600.0,
        "declared_parallelism": parallel,
        "estimate_limitations": (
            "Linear step-count extrapolation at the same population and grid. "
            "It includes a multiplicative safety factor but does not authorize V1 execution."
        ),
    }
    write_json(output_dir / "runtime_estimate.json", payload)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    _require_umi()
    config_path = project_path(args.config, must_exist=True)
    output_dir = project_path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    config = load_json(config_path)
    experiment = str(config.get("experiment_id", ""))
    if experiment not in {"V1P-RUNTIME-PILOT-C4", "V1-NONFLAT-CALIBRATION-C4"}:
        raise ValueError("unexpected experiment_id")
    _validate_conditions(config.get("conditions"))
    if experiment == "V1-NONFLAT-CALIBRATION-C4":
        validate_full_matrix(config)

    specs = prepare_inputs(experiment, config, output_dir)
    execution = execute_runs(
        specs,
        project_path(config["binary"], must_exist=True),
        timeout_seconds=int(config.get("per_run_timeout_seconds", 3600)),
        omp_threads=int(config.get("omp_threads", 1)),
        parallel=int(config.get("parallel", 1)),
    )
    if experiment == "V1P-RUNTIME-PILOT-C4":
        payload = summarize_runtime_pilot(specs, config, output_dir)
    else:
        rows = analyze_runs(experiment, config, output_dir, specs)
        payload = aggregate_v1(rows, config, output_dir)
        payload = {
            "experiment": experiment,
            "status": "completed",
            "pass": bool(payload["pass"]),
            "calibration_sha256": sha256_file(output_dir / "numerical_calibration.json"),
        }
    payload["config_sha256"] = sha256_file(config_path)
    payload["runs_executed_this_invocation"] = execution["executed"]
    payload["elapsed_seconds_executed_this_invocation"] = execution[
        "elapsed_seconds_executed"
    ]
    write_json(output_dir / "result.json", payload)
    summary_result = config.get("summary_result")
    if isinstance(summary_result, str) and summary_result:
        write_json(project_path(summary_result), payload)
    return 0 if payload["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
