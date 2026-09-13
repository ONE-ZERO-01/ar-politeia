#!/usr/bin/env python3
"""Diagnose V1B stationarity at the condition-ensemble estimand level on umi."""

from __future__ import annotations

import argparse
import math
import platform
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

from landscape_study import metric_status, sha256_file, stationarity_diagnostics, write_json
from run_landscape_study import absolute_drift_tolerance_for_metric, load_json, project_path
from run_v1_stationarity_diagnostic import (
    STATIONARY_METRICS,
    _diagnose_layer,
    _load_metric_series,
)


def _require_umi() -> None:
    if platform.node().split(".", 1)[0] != "umi":
        raise RuntimeError("V1BD diagnostics must run on host umi")


def _diagnostic(metric: str, values: Sequence[float], config: Mapping[str, Any]) -> dict[str, Any]:
    status = metric_status(metric, float(np.mean(values)))
    if status["status"] != "valid":
        return {"pass": False, "status": status["status"], "reason": status.get("reason")}
    return stationarity_diagnostics(
        values,
        max_normalized_drift=float(config["max_normalized_drift"]),
        min_effective_samples=float(config["min_effective_samples"]),
        absolute_drift_tolerance=absolute_drift_tolerance_for_metric(metric),
        reversal_span_sigma=float(config["reversal_span_sigma"]),
    )


def _summarize_segment(
    grouped_specs: Mapping[tuple[str, float], Sequence[Mapping[str, Any]]],
    series_by_run: Mapping[str, Mapping[str, Sequence[float]]],
    *,
    segment: slice,
    config: Mapping[str, Any],
) -> dict[str, Any]:
    conditions: dict[str, Any] = {}
    failed_metrics: Counter[str] = Counter()
    precision_failed_metrics: Counter[str] = Counter()
    failed_conditions = 0
    precision_failed_conditions = 0
    for (landscape, dt), specs in sorted(grouped_specs.items()):
        metrics: dict[str, Any] = {}
        individual_pass_counts: dict[str, int] = {}
        for metric in STATIONARY_METRICS:
            arrays = np.asarray(
                [series_by_run[str(spec["run_id"])][metric][segment] for spec in specs],
                dtype=np.float64,
            )
            ensemble = np.mean(arrays, axis=0)
            diagnostic = _diagnostic(metric, ensemble, config)
            individual = [_diagnostic(metric, row, config) for row in arrays]
            individual_pass_counts[metric] = sum(bool(item.get("pass", False)) for item in individual)
            if not bool(diagnostic.get("pass", False)):
                failed_metrics[metric] += 1
            if diagnostic.get("precision_pass") is False:
                precision_failed_metrics[metric] += 1
            metrics[metric] = {
                "ensemble": diagnostic,
                "individual_stationarity_passed": individual_pass_counts[metric],
                "individual_runs": len(specs),
            }
        stationarity_pass = all(bool(item["ensemble"].get("pass", False)) for item in metrics.values())
        precision_pass = all(
            item["ensemble"].get("precision_pass") is not False for item in metrics.values()
        )
        failed_conditions += int(not stationarity_pass)
        precision_failed_conditions += int(not precision_pass)
        key = f"{landscape}--dt-{dt:.17g}"
        conditions[key] = {
            "landscape": landscape,
            "dt": dt,
            "replicates": len(specs),
            "stationarity_pass": stationarity_pass,
            "precision_pass": precision_pass,
            "metrics": metrics,
        }
    return {
        "conditions": conditions,
        "condition_count": len(conditions),
        "stationarity_failed_conditions": failed_conditions,
        "precision_failed_conditions": precision_failed_conditions,
        "stationarity_failure_count_by_metric": dict(failed_metrics),
        "precision_failure_count_by_metric": dict(precision_failed_metrics),
    }


def _window_level_shifts(
    grouped_specs: Mapping[tuple[str, float], Sequence[Mapping[str, Any]]],
    series_by_run: Mapping[str, Mapping[str, Sequence[float]]],
    window: int,
) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for (landscape, dt), specs in sorted(grouped_specs.items()):
        metrics: dict[str, Any] = {}
        for metric in STATIONARY_METRICS:
            arrays = np.asarray(
                [series_by_run[str(spec["run_id"])][metric] for spec in specs], dtype=np.float64
            )
            previous_means = arrays[:, :window].mean(axis=1)
            tail_means = arrays[:, window:].mean(axis=1)
            differences = tail_means - previous_means
            metrics[metric] = {
                "mean_shift": float(np.mean(differences)),
                "absolute_mean_shift": abs(float(np.mean(differences))),
                "paired_sd": float(np.std(differences, ddof=1)),
                "standard_error": float(np.std(differences, ddof=1) / math.sqrt(len(specs))),
            }
        output[f"{landscape}--dt-{dt:.17g}"] = metrics
    return output


def _replicate_requirements(calibration: Mapping[str, Any]) -> list[dict[str, Any]]:
    requirements: list[dict[str, Any]] = []
    for landscape, metrics in calibration["discretization"].items():
        for metric, item in metrics.items():
            comparison = item["fine_vs_finest"]
            mean = float(comparison["absolute_mean_difference"])
            sd = float(comparison["paired_sample_sd"])
            ceiling = float(item["ceiling"])
            margin = ceiling - mean
            if margin <= 0.0:
                required = None
                reason = "observed absolute mean difference already exceeds ceiling"
            else:
                required = max(3, int(math.ceil((2.0 * sd / margin) ** 2)))
                reason = "n such that observed |mean| + 2*SD/sqrt(n) <= ceiling"
            requirements.append(
                {
                    "landscape": landscape,
                    "metric": metric,
                    "current_replicates": int(comparison["replicates"]),
                    "absolute_mean_difference": mean,
                    "paired_sd": sd,
                    "ceiling": ceiling,
                    "estimated_required_replicates": required,
                    "calculation": reason,
                }
            )
    return requirements


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    _require_umi()
    config_path = project_path(args.config, must_exist=True)
    config = load_json(config_path)
    if config.get("experiment_id") != "V1BD-ENSEMBLE-DIAGNOSTIC-C4":
        raise ValueError("unexpected experiment_id")
    output_dir = project_path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    source = project_path(config["source_workspace"], must_exist=True)
    specs_path = source / "run_specs.json"
    specs = load_json(specs_path)["runs"]
    if len(specs) != int(config["expected_source_runs"]):
        raise RuntimeError("source run count does not match declaration")
    timestep_specs = [spec for spec in specs if spec["calibration_component"] == "timestep"]
    window = int(config["window_snapshots"])
    required_snapshots = 2 * window
    series_by_run = {
        str(spec["run_id"]): _load_metric_series(
            spec, snapshots_needed=required_snapshots, bounds=config["bounds"]
        )
        for spec in timestep_specs
    }
    baseline = _diagnose_layer(
        timestep_specs,
        series_by_run,
        window=window,
        reversal_span_sigma=float(config["reversal_span_sigma"]),
        max_normalized_drift=float(config["max_normalized_drift"]),
        min_effective_samples=float(config["min_effective_samples"]),
    )
    observed = {
        "stationarity_failed_runs": baseline["stationarity_failed_runs"],
        "precision_failed_runs": baseline["precision_failed_runs"],
        "drift": baseline["diagnostic_failure_components"]["drift"],
        "window_shape_reversal": baseline["diagnostic_failure_components"][
            "window_shape_reversal"
        ],
        "precision": baseline["diagnostic_failure_components"]["precision"],
    }
    expected = {key: int(value) for key, value in config["expected_v1b_baseline"].items()}
    if observed != expected:
        raise RuntimeError(f"V1BD failed to reproduce V1B: {observed} != {expected}")

    grouped: dict[tuple[str, float], list[Mapping[str, Any]]] = defaultdict(list)
    for spec in timestep_specs:
        grouped[(str(spec["landscape"]), float(spec["dt"]))].append(spec)
    previous = _summarize_segment(
        grouped,
        series_by_run,
        segment=slice(0, window),
        config=config,
    )
    tail = _summarize_segment(
        grouped,
        series_by_run,
        segment=slice(window, 2 * window),
        config=config,
    )
    calibration_path = source / "numerical_calibration.json"
    calibration = load_json(calibration_path)
    requirements = _replicate_requirements(calibration)
    payload = {
        "experiment": config["experiment_id"],
        "status": "completed",
        "pass": True,
        "non_evidentiary": True,
        "source_experiment": config["source_experiment"],
        "source_run_specs_sha256": sha256_file(specs_path),
        "source_numerical_calibration_sha256": sha256_file(calibration_path),
        "baseline_reproduction": {"pass": True, "actual": observed, "expected": expected},
        "window_snapshots": window,
        "previous_window": previous,
        "tail_window": tail,
        "adjacent_window_level_shifts": _window_level_shifts(grouped, series_by_run, window),
        "replicate_requirements_if_observed_moments_persist": requirements,
        "interpretation_boundary": (
            "This diagnoses the estimand and sampling contract using V1B outcomes. "
            "It cannot change V1B and any selected contract requires new data."
        ),
    }
    diagnostic_path = output_dir / "ensemble_stationarity_diagnostic.json"
    write_json(diagnostic_path, payload)
    result = {
        "experiment": config["experiment_id"],
        "status": "completed",
        "pass": True,
        "non_evidentiary": True,
        "baseline_reproduction": payload["baseline_reproduction"],
        "previous_window_summary": {
            key: previous[key]
            for key in ("condition_count", "stationarity_failed_conditions", "precision_failed_conditions", "stationarity_failure_count_by_metric", "precision_failure_count_by_metric")
        },
        "tail_window_summary": {
            key: tail[key]
            for key in ("condition_count", "stationarity_failed_conditions", "precision_failed_conditions", "stationarity_failure_count_by_metric", "precision_failure_count_by_metric")
        },
        "maximum_estimated_required_replicates": max(
            item["estimated_required_replicates"] or 0 for item in requirements
        ),
        "diagnostic_sha256": sha256_file(diagnostic_path),
        "config_sha256": sha256_file(config_path),
    }
    write_json(output_dir / "result.json", result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
