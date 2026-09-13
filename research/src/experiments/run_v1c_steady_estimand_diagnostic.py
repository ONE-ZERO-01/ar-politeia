#!/usr/bin/env python3
"""Diagnose V1C equilibration and independent-replicate precision on umi."""

from __future__ import annotations

import argparse
import math
import platform
from collections import defaultdict
from typing import Any, Mapping, Sequence

import numpy as np

from landscape_study import sha256_file, write_json
from run_landscape_study import load_json, project_path
from run_v1_stationarity_diagnostic import STATIONARY_METRICS, _load_metric_series
from run_v1b_ensemble_diagnostic import _summarize_segment


def _require_umi() -> None:
    if platform.node().split(".", 1)[0] != "umi":
        raise RuntimeError("V1CD diagnostics must run on host umi")


def _summary_counts(summary: Mapping[str, Any]) -> dict[str, Any]:
    keys = (
        "condition_count",
        "stationarity_failed_conditions",
        "precision_failed_conditions",
        "stationarity_failure_count_by_metric",
        "precision_failure_count_by_metric",
    )
    return {key: summary[key] for key in keys}


def _assert_expected(actual: Mapping[str, Any], expected: Mapping[str, Any]) -> None:
    normalized = {
        "condition_count": int(actual["condition_count"]),
        "stationarity_failed_conditions": int(actual["stationarity_failed_conditions"]),
        "precision_failed_conditions": int(actual["precision_failed_conditions"]),
        "stationarity_failure_count_by_metric": dict(
            actual["stationarity_failure_count_by_metric"]
        ),
        "precision_failure_count_by_metric": dict(actual["precision_failure_count_by_metric"]),
    }
    registered = {
        "condition_count": int(expected["condition_count"]),
        "stationarity_failed_conditions": int(expected["stationarity_failed_conditions"]),
        "precision_failed_conditions": int(expected["precision_failed_conditions"]),
        "stationarity_failure_count_by_metric": dict(
            expected["stationarity_failure_count_by_metric"]
        ),
        "precision_failure_count_by_metric": dict(expected["precision_failure_count_by_metric"]),
    }
    if normalized != registered:
        raise RuntimeError(f"V1CD failed to reproduce V1C: {normalized} != {registered}")


def _independent_replicate_precision(
    grouped_specs: Mapping[tuple[str, float], Sequence[Mapping[str, Any]]],
    series_by_run: Mapping[str, Mapping[str, Sequence[float]]],
    *,
    segment: slice,
    planning_half_widths: Mapping[str, float],
) -> dict[str, Any]:
    conditions: dict[str, Any] = {}
    for (landscape, dt), specs in sorted(grouped_specs.items()):
        metrics: dict[str, Any] = {}
        for metric in STATIONARY_METRICS:
            run_means = np.asarray(
                [np.mean(series_by_run[str(spec["run_id"])][metric][segment]) for spec in specs],
                dtype=np.float64,
            )
            sample_sd = float(np.std(run_means, ddof=1))
            standard_error = sample_sd / math.sqrt(len(run_means))
            two_se_half_width = 2.0 * standard_error
            target = planning_half_widths.get(metric)
            required = None
            if target is not None:
                required = max(3, int(math.ceil((2.0 * sample_sd / float(target)) ** 2)))
            metrics[metric] = {
                "replicates": len(run_means),
                "mean_of_run_window_means": float(np.mean(run_means)),
                "between_replicate_sample_sd": sample_sd,
                "standard_error": standard_error,
                "two_se_half_width": two_se_half_width,
                "planning_half_width": target,
                "planning_width_pass": None if target is None else two_se_half_width <= float(target),
                "estimated_replicates_for_planning_width": required,
            }
        conditions[f"{landscape}--dt-{dt:.17g}"] = metrics
    return {"conditions": conditions, "planning_only": True}


def _adjacent_window_shifts(
    grouped_specs: Mapping[tuple[str, float], Sequence[Mapping[str, Any]]],
    series_by_run: Mapping[str, Mapping[str, Sequence[float]]],
    *,
    window: int,
    planning_half_widths: Mapping[str, float],
) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for (landscape, dt), specs in sorted(grouped_specs.items()):
        metrics: dict[str, Any] = {}
        for metric in STATIONARY_METRICS:
            arrays = np.asarray(
                [series_by_run[str(spec["run_id"])][metric] for spec in specs],
                dtype=np.float64,
            )
            differences = arrays[:, window:].mean(axis=1) - arrays[:, :window].mean(axis=1)
            mean_shift = float(np.mean(differences))
            paired_sd = float(np.std(differences, ddof=1))
            bound = abs(mean_shift) + 2.0 * paired_sd / math.sqrt(len(specs))
            target = planning_half_widths.get(metric)
            metrics[metric] = {
                "mean_shift": mean_shift,
                "absolute_mean_shift": abs(mean_shift),
                "paired_sample_sd": paired_sd,
                "standard_error": paired_sd / math.sqrt(len(specs)),
                "absolute_shift_plus_two_se": bound,
                "planning_half_width": target,
                "planning_width_pass": None if target is None else bound <= float(target),
            }
        output[f"{landscape}--dt-{dt:.17g}"] = metrics
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    _require_umi()

    config_path = project_path(args.config, must_exist=True)
    config = load_json(config_path)
    if config.get("experiment_id") != "V1CD-STEADY-ESTIMAND-DIAGNOSTIC-C4":
        raise ValueError("unexpected experiment_id")
    output_dir = project_path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    source = project_path(str(config["source_workspace"]), must_exist=True)
    source_paths = {
        "run_specs": source / "run_specs.json",
        "calibration": source / "numerical_calibration.json",
        "ensemble_report": source / "ensemble_stationarity_report.json",
    }
    for key, path in source_paths.items():
        expected = str(config["source_sha256"][key])
        actual = sha256_file(path)
        if actual != expected:
            raise RuntimeError(f"source {key} checksum mismatch: {actual} != {expected}")

    specs = load_json(source_paths["run_specs"])["runs"]
    if len(specs) != int(config["expected_source_runs"]):
        raise RuntimeError("source run count does not match declaration")
    timestep_specs = [spec for spec in specs if spec["calibration_component"] == "timestep"]
    if len(timestep_specs) != int(config["expected_timestep_runs"]):
        raise RuntimeError("source timestep run count does not match declaration")

    window = int(config["window_snapshots"])
    series_by_run = {
        str(spec["run_id"]): _load_metric_series(
            spec, snapshots_needed=2 * window, bounds=config["bounds"]
        )
        for spec in timestep_specs
    }
    grouped: dict[tuple[str, float], list[Mapping[str, Any]]] = defaultdict(list)
    for spec in timestep_specs:
        grouped[(str(spec["landscape"]), float(spec["dt"]))].append(spec)

    diagnostic_config = {
        "max_normalized_drift": config["max_normalized_drift"],
        "min_effective_samples": config["min_effective_samples"],
        "reversal_span_sigma": config["reversal_span_sigma"],
    }
    previous = _summarize_segment(
        grouped, series_by_run, segment=slice(0, window), config=diagnostic_config
    )
    tail = _summarize_segment(
        grouped, series_by_run, segment=slice(window, 2 * window), config=diagnostic_config
    )
    tail_counts = _summary_counts(tail)
    _assert_expected(tail_counts, config["expected_v1c_tail"])
    planning_widths = {
        str(key): float(value) for key, value in config["planning_half_widths"].items()
    }
    payload = {
        "experiment": config["experiment_id"],
        "status": "completed",
        "pass": True,
        "non_evidentiary": True,
        "source_experiment": config["source_experiment"],
        "source_sha256": config["source_sha256"],
        "window_snapshots": window,
        "previous_window": previous,
        "tail_window": tail,
        "tail_baseline_reproduction": {
            "pass": True,
            "actual": tail_counts,
            "expected": config["expected_v1c_tail"],
        },
        "adjacent_window_shifts": _adjacent_window_shifts(
            grouped,
            series_by_run,
            window=window,
            planning_half_widths=planning_widths,
        ),
        "independent_replicate_precision": _independent_replicate_precision(
            grouped,
            series_by_run,
            segment=slice(window, 2 * window),
            planning_half_widths=planning_widths,
        ),
        "interpretation_boundary": (
            "This deterministic diagnosis cannot change V1C. Planning widths were frozen "
            "before the diagnosis and may only inform a new independently seeded design."
        ),
    }
    diagnostic_path = output_dir / "steady_estimand_diagnostic.json"
    write_json(diagnostic_path, payload)
    result = {
        "experiment": config["experiment_id"],
        "status": "completed",
        "pass": True,
        "non_evidentiary": True,
        "tail_baseline_reproduction": payload["tail_baseline_reproduction"],
        "previous_window_summary": _summary_counts(previous),
        "tail_window_summary": tail_counts,
        "diagnostic_sha256": sha256_file(diagnostic_path),
        "config_sha256": sha256_file(config_path),
    }
    write_json(output_dir / "result.json", result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
