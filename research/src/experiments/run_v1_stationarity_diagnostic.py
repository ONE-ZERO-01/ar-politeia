#!/usr/bin/env python3
"""Reanalyse completed V1 snapshots under fixed stationarity windows on umi."""

from __future__ import annotations

import argparse
import json
import math
import platform
from collections import Counter
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

from landscape_study import (
    metric_status,
    read_snapshot_csv,
    sha256_file,
    snapshot_metrics,
    stationarity_diagnostics,
    write_json,
)
from run_landscape_study import (
    absolute_drift_tolerance_for_metric,
    load_json,
    project_path,
)


STATIONARY_METRICS = (
    "resource_density_spearman_rho",
    "density_morans_i",
    "occupancy_entropy",
    "wealth_gini",
    "wealth_variance",
    "zero_wealth_fraction",
)


def _require_umi() -> None:
    if platform.node().split(".", 1)[0] != "umi":
        raise RuntimeError("V1D snapshot diagnostics must run on host umi")


def _finite_positive_values(raw: Any, name: str, *, integral: bool) -> list[float]:
    if not isinstance(raw, list) or not raw:
        raise ValueError(f"{name} must be a non-empty list")
    values = [float(value) for value in raw]
    if any(not math.isfinite(value) or value <= 0.0 for value in values):
        raise ValueError(f"{name} must contain finite positive values")
    if integral and any(not value.is_integer() for value in values):
        raise ValueError(f"{name} must contain integers")
    if len(set(values)) != len(values):
        raise ValueError(f"{name} must not contain duplicates")
    return values


def _load_metric_series(
    spec: Mapping[str, Any], *, snapshots_needed: int, bounds: Sequence[float]
) -> dict[str, list[float]]:
    run_dir = project_path(str(spec["run_dir"]), must_exist=True)
    completion = load_json(run_dir / "completion.json")
    if completion.get("status") != "completed":
        raise RuntimeError(f"source run is incomplete: {spec['run_id']}")
    snapshots = sorted(run_dir.glob("snap_*.csv"))
    if len(snapshots) < snapshots_needed:
        raise RuntimeError(
            f"{spec['run_id']} has {len(snapshots)} snapshots, needs {snapshots_needed}"
        )
    resource = np.load(
        project_path(str(spec["resource_npy"]), must_exist=True), allow_pickle=False
    )
    rows = [
        snapshot_metrics(
            read_snapshot_csv(path),
            resource,
            tuple(float(value) for value in bounds),
        )
        for path in snapshots[-snapshots_needed:]
    ]
    return {
        metric: [float(row[metric]) for row in rows] for metric in STATIONARY_METRICS
    }


def _diagnose_layer(
    specs: Sequence[Mapping[str, Any]],
    series_by_run: Mapping[str, Mapping[str, Sequence[float]]],
    *,
    window: int,
    reversal_span_sigma: float,
    max_normalized_drift: float,
    min_effective_samples: float,
) -> dict[str, Any]:
    stationarity_failures: Counter[str] = Counter()
    precision_failures: Counter[str] = Counter()
    components: Counter[str] = Counter()
    stationarity_bad_runs: list[str] = []
    precision_bad_runs: list[str] = []
    undefined_or_invalid: Counter[str] = Counter()

    for spec in specs:
        run_id = str(spec["run_id"])
        run_stationary = True
        run_precise = True
        for metric in STATIONARY_METRICS:
            values = list(series_by_run[run_id][metric][-window:])
            status = metric_status(metric, float(np.mean(values)))
            if status["status"] != "valid":
                undefined_or_invalid[metric] += 1
                stationarity_failures[metric] += 1
                run_stationary = False
                continue
            diagnostic = stationarity_diagnostics(
                values,
                max_normalized_drift=max_normalized_drift,
                min_effective_samples=min_effective_samples,
                absolute_drift_tolerance=absolute_drift_tolerance_for_metric(metric),
                reversal_span_sigma=reversal_span_sigma,
            )
            if not bool(diagnostic["stationarity_pass"]):
                stationarity_failures[metric] += 1
                run_stationary = False
            if not bool(diagnostic["drift_pass"]):
                components["drift"] += 1
            if not bool(diagnostic["monotonic_pass"]):
                components["window_shape_reversal"] += 1
            if not bool(diagnostic["precision_pass"]):
                precision_failures[metric] += 1
                components["precision"] += 1
                run_precise = False
        if not run_stationary:
            stationarity_bad_runs.append(run_id)
        if not run_precise:
            precision_bad_runs.append(run_id)

    return {
        "runs": len(specs),
        "stationarity_passed_runs": len(specs) - len(stationarity_bad_runs),
        "stationarity_failed_runs": len(stationarity_bad_runs),
        "precision_passed_runs": len(specs) - len(precision_bad_runs),
        "precision_failed_runs": len(precision_bad_runs),
        "stationarity_failure_count_by_metric": {
            metric: stationarity_failures[metric] for metric in STATIONARY_METRICS
        },
        "precision_failure_count_by_metric": {
            metric: precision_failures[metric]
            for metric in STATIONARY_METRICS
            if precision_failures[metric]
        },
        "diagnostic_failure_components": {
            "window_shape_reversal": components["window_shape_reversal"],
            "drift": components["drift"],
            "precision": components["precision"],
        },
        "undefined_or_invalid_count_by_metric": {
            metric: undefined_or_invalid[metric]
            for metric in STATIONARY_METRICS
            if undefined_or_invalid[metric]
        },
        "stationarity_failed_run_ids": stationarity_bad_runs,
        "precision_failed_run_ids": precision_bad_runs,
    }


def _assert_baseline_reproduction(
    actual: Mapping[str, Any], expected: Mapping[str, Any]
) -> dict[str, Any]:
    paths = {
        "stationarity_failed_runs": int(actual["stationarity_failed_runs"]),
        "precision_failed_runs": int(actual["precision_failed_runs"]),
        "window_shape_reversal": int(
            actual["diagnostic_failure_components"]["window_shape_reversal"]
        ),
        "drift": int(actual["diagnostic_failure_components"]["drift"]),
        "precision": int(actual["diagnostic_failure_components"]["precision"]),
    }
    registered = {key: int(expected[key]) for key in paths}
    if paths != registered:
        raise RuntimeError(
            "V1D baseline does not reproduce archived V1 counts: "
            f"actual={paths}, expected={registered}"
        )
    return {"pass": True, "actual": paths, "expected": registered}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    _require_umi()

    config_path = project_path(args.config, must_exist=True)
    config = load_json(config_path)
    if config.get("experiment_id") != "V1D-STATIONARITY-DIAGNOSTIC-C4":
        raise ValueError("unexpected experiment_id")
    output_dir = project_path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    source_workspace = project_path(str(config["source_workspace"]), must_exist=True)
    source_specs_path = source_workspace / "run_specs.json"
    source_specs_payload = load_json(source_specs_path)
    specs = source_specs_payload.get("runs")
    if not isinstance(specs, list) or len(specs) != int(config["expected_source_runs"]):
        raise RuntimeError("source run_specs count does not match V1D declaration")

    windows = [
        int(value)
        for value in _finite_positive_values(
            config["window_snapshots"], "window_snapshots", integral=True
        )
    ]
    sigmas = _finite_positive_values(
        config["reversal_span_sigma"], "reversal_span_sigma", integral=False
    )
    max_window = max(windows)
    bounds = config["bounds"]
    series_by_run = {
        str(spec["run_id"]): _load_metric_series(
            spec, snapshots_needed=max_window, bounds=bounds
        )
        for spec in specs
    }

    layers = {
        "timestep": [spec for spec in specs if spec["calibration_component"] == "timestep"],
        "order": [spec for spec in specs if spec["calibration_component"] == "order"],
    }
    comparisons: dict[str, Any] = {}
    for window in windows:
        for sigma in sigmas:
            key = f"window-{window}--sigma-{sigma:.17g}"
            comparisons[key] = {
                "window_snapshots": window,
                "window_time_span": (window - 1) * float(config["snapshot_time_interval"]),
                "reversal_span_sigma": sigma,
                "timestep_layer": _diagnose_layer(
                    layers["timestep"],
                    series_by_run,
                    window=window,
                    reversal_span_sigma=sigma,
                    max_normalized_drift=float(config["max_normalized_drift"]),
                    min_effective_samples=float(config["min_effective_samples"]),
                ),
                "order_layer": _diagnose_layer(
                    layers["order"],
                    series_by_run,
                    window=window,
                    reversal_span_sigma=sigma,
                    max_normalized_drift=float(config["max_normalized_drift"]),
                    min_effective_samples=float(config["min_effective_samples"]),
                ),
            }

    baseline_key = str(config["baseline_comparison_key"])
    if baseline_key not in comparisons:
        raise ValueError("baseline_comparison_key is not in the declared comparison grid")
    baseline_reproduction = _assert_baseline_reproduction(
        comparisons[baseline_key]["timestep_layer"], config["expected_v1_baseline"]
    )
    candidate_key = str(config["preregistered_v1b_candidate_key"])
    if candidate_key not in comparisons:
        raise ValueError("preregistered_v1b_candidate_key is not in the comparison grid")

    sensitivity = {
        "experiment": config["experiment_id"],
        "status": "completed",
        "pass": True,
        "non_evidentiary": True,
        "source_experiment": config["source_experiment"],
        "source_run_count": len(specs),
        "source_run_specs_sha256": sha256_file(source_specs_path),
        "baseline_reproduction": baseline_reproduction,
        "comparisons": comparisons,
        "preregistered_v1b_candidate": {
            "comparison_key": candidate_key,
            "result": comparisons[candidate_key],
            "selection_rule": config["candidate_selection_rule"],
            "evidence_boundary": (
                "This V1-derived diagnostic can specify V1B, but cannot change the "
                "archived V1 verdict or support a scientific landscape claim."
            ),
        },
    }
    output_path = output_dir / "window_sensitivity.json"
    write_json(output_path, sensitivity)
    result = {
        "experiment": config["experiment_id"],
        "status": "completed",
        "pass": True,
        "non_evidentiary": True,
        "source_run_count": len(specs),
        "baseline_reproduction": baseline_reproduction,
        "preregistered_v1b_candidate_key": candidate_key,
        "candidate_timestep_layer": comparisons[candidate_key]["timestep_layer"],
        "candidate_order_layer": comparisons[candidate_key]["order_layer"],
        "window_sensitivity_sha256": sha256_file(output_path),
        "config_sha256": sha256_file(config_path),
    }
    write_json(output_dir / "result.json", result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
