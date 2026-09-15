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

from landscape_study import (
    metric_status,
    read_snapshot_csv,
    sha256_file,
    snapshot_metrics,
    write_json,
)
from run_landscape_study import (
    PROJECT_ROOT,
    _stationarity_for_metric,
    analyze_runs,
    execute_runs,
    load_json,
    prepare_inputs,
    project_path,
    stationary_metrics_for_experiment,
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
    gate_unit = config.get("stationarity_gate_unit", "run")
    if gate_unit not in {
        "run",
        "condition_ensemble",
        "condition_ensemble_two_window",
    }:
        raise ValueError(
            "stationarity_gate_unit must be run, condition_ensemble, or "
            "condition_ensemble_two_window"
        )
    if gate_unit == "condition_ensemble_two_window":
        _validate_two_window_contract(config)


def _validate_two_window_contract(config: Mapping[str, Any]) -> None:
    window = int(config.get("steady_snapshots", 0))
    if window < 3:
        raise ValueError("two-window gate requires steady_snapshots >= 3")
    output_interval = float(config.get("output_time_interval", 0.0))
    total_time = float(config.get("total_time", 0.0))
    if output_interval <= 0.0 or total_time / output_interval < 2 * window:
        raise ValueError("two-window gate requires at least 2*steady_snapshots outputs")
    stationary_metrics = stationary_metrics_for_experiment(str(config["experiment_id"]))
    absolute = config.get("independent_precision_absolute_half_widths")
    relative = config.get("independent_precision_relative_half_widths")
    adjacent_absolute = config.get("adjacent_window_absolute_bounds")
    adjacent_relative = config.get("adjacent_window_relative_bounds")
    for name, value in (
        ("independent_precision_absolute_half_widths", absolute),
        ("independent_precision_relative_half_widths", relative),
        ("adjacent_window_absolute_bounds", adjacent_absolute),
        ("adjacent_window_relative_bounds", adjacent_relative),
    ):
        if not isinstance(value, Mapping):
            raise ValueError(f"{name} must be an object")
        for metric, threshold in value.items():
            if metric not in stationary_metrics:
                raise ValueError(f"{name} contains unsupported metric {metric}")
            numeric = float(threshold)
            if not math.isfinite(numeric) or numeric <= 0.0:
                raise ValueError(f"{name}.{metric} must be finite and positive")
    if set(absolute) & set(relative):
        raise ValueError("independent precision metric cannot have both absolute and relative bounds")
    if set(adjacent_absolute) & set(adjacent_relative):
        raise ValueError("adjacent-window metric cannot have both absolute and relative bounds")
    if set(absolute) | set(relative) != set(stationary_metrics):
        raise ValueError("independent precision bounds must cover every stationary metric")
    if set(adjacent_absolute) | set(adjacent_relative) != set(stationary_metrics):
        raise ValueError("adjacent-window bounds must cover every stationary metric")


def aggregate_condition_ensemble_stationarity(
    specs: Sequence[Mapping[str, Any]],
    config: Mapping[str, Any],
    output_dir: Path,
) -> dict[str, Any]:
    """Evaluate stationarity for each landscape×dt ensemble-mean time series."""
    timestep_specs = [spec for spec in specs if spec["calibration_component"] == "timestep"]
    grouped: dict[tuple[str, float], list[Mapping[str, Any]]] = defaultdict(list)
    for spec in timestep_specs:
        grouped[(str(spec["landscape"]), float(spec["dt"]))].append(spec)
    expected_replicates = len(config["seeds"])
    if len(grouped) != 9 or any(len(items) != expected_replicates for items in grouped.values()):
        raise RuntimeError("condition-ensemble gate requires a complete 3x3 timestep matrix")

    window = int(config["steady_snapshots"])
    bounds = tuple(float(value) for value in config["bounds"])
    stationary_metrics = stationary_metrics_for_experiment(str(config["experiment_id"]))
    conditions: dict[str, Any] = {}
    for (landscape, dt), condition_specs in sorted(grouped.items()):
        series_by_metric: dict[str, list[list[float]]] = {
            metric: [] for metric in stationary_metrics
        }
        for spec in condition_specs:
            run_dir = project_path(spec["run_dir"], must_exist=True)
            snapshots = sorted(run_dir.glob("snap_*.csv"))
            if len(snapshots) < window:
                raise RuntimeError(f"{spec['run_id']} has fewer than {window} snapshots")
            resource = np.load(
                project_path(spec["resource_npy"], must_exist=True), allow_pickle=False
            )
            rows = [
                snapshot_metrics(read_snapshot_csv(path), resource, bounds)
                for path in snapshots[-window:]
            ]
            for metric in stationary_metrics:
                series_by_metric[metric].append([float(row[metric]) for row in rows])

        diagnostics: dict[str, Any] = {}
        for metric, replicate_series in series_by_metric.items():
            ensemble_series = np.mean(np.asarray(replicate_series, dtype=np.float64), axis=0)
            status = metric_status(metric, float(np.mean(ensemble_series)))
            diagnostics[metric] = _stationarity_for_metric(
                metric,
                ensemble_series,
                status,
                max_normalized_drift=float(config["stationarity_max_normalized_drift"]),
                min_effective_samples=float(config["stationarity_min_ess"]),
                reversal_span_sigma=float(config.get("stationarity_reversal_span_sigma", 1.0)),
            )
        stationarity_pass = all(bool(item.get("pass", False)) for item in diagnostics.values())
        precision_pass = all(
            item.get("precision_pass") is not False for item in diagnostics.values()
        )
        conditions[f"{landscape}--dt-{dt:.17g}"] = {
            "landscape": landscape,
            "dt": dt,
            "replicates": len(condition_specs),
            "stationarity_pass": stationarity_pass,
            "precision_pass": precision_pass,
            "metrics": diagnostics,
        }
    payload = {
        "experiment": config["experiment_id"],
        "gate_unit": "condition_ensemble",
        "window_snapshots": window,
        "replicates_per_condition": expected_replicates,
        "stationarity_valid": all(item["stationarity_pass"] for item in conditions.values()),
        "precision_valid": all(item["precision_pass"] for item in conditions.values()),
        "conditions": conditions,
    }
    payload["pass"] = bool(payload["stationarity_valid"] and payload["precision_valid"])
    write_json(output_dir / "ensemble_stationarity_report.json", payload)
    return payload


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


def _independent_precision_summary(
    values: Sequence[float],
    *,
    absolute_half_width: float | None = None,
    relative_half_width: float | None = None,
) -> dict[str, Any]:
    data = np.asarray(values, dtype=np.float64)
    if data.ndim != 1 or data.size < 3 or not np.all(np.isfinite(data)):
        raise ValueError("independent precision requires >=3 finite replicate values")
    if (absolute_half_width is None) == (relative_half_width is None):
        raise ValueError("independent precision requires exactly one bound type")
    mean = float(np.mean(data))
    sample_sd = float(np.std(data, ddof=1))
    standard_error = sample_sd / math.sqrt(float(data.size))
    two_se_half_width = 2.0 * standard_error
    if absolute_half_width is not None:
        threshold = float(absolute_half_width)
        observed = two_se_half_width
        kind = "absolute"
    else:
        threshold = float(relative_half_width)
        observed = two_se_half_width / max(abs(mean), 1e-12)
        kind = "relative_to_absolute_mean"
    return {
        "replicates": int(data.size),
        "mean": mean,
        "sample_sd": sample_sd,
        "standard_error": standard_error,
        "two_se_half_width": two_se_half_width,
        "bound_kind": kind,
        "observed_bound": observed,
        "threshold": threshold,
        "pass": bool(observed <= threshold),
    }


def _adjacent_window_summary(
    previous: Sequence[float],
    tail: Sequence[float],
    *,
    absolute_bound: float | None = None,
    relative_bound: float | None = None,
) -> dict[str, Any]:
    if (absolute_bound is None) == (relative_bound is None):
        raise ValueError("adjacent-window stability requires exactly one bound type")
    weak = _weak_bound(tail, previous)
    if absolute_bound is not None:
        threshold = float(absolute_bound)
        observed = float(weak["two_se_bound"])
        kind = "absolute"
    else:
        previous_mean = abs(float(np.mean(np.asarray(previous, dtype=np.float64))))
        tail_mean = abs(float(np.mean(np.asarray(tail, dtype=np.float64))))
        threshold = float(relative_bound)
        observed = float(weak["two_se_bound"]) / max(previous_mean, tail_mean, 1e-12)
        kind = "relative_to_larger_window_mean"
    return {
        **weak,
        "bound_kind": kind,
        "observed_bound": observed,
        "threshold": threshold,
        "pass": bool(observed <= threshold),
    }


def aggregate_two_window_steady_estimand(
    specs: Sequence[Mapping[str, Any]],
    config: Mapping[str, Any],
    output_dir: Path,
) -> dict[str, Any]:
    """Gate late-window dynamics separately from independent-seed precision."""
    _validate_two_window_contract(config)
    timestep_specs = [spec for spec in specs if spec["calibration_component"] == "timestep"]
    grouped: dict[tuple[str, float], list[Mapping[str, Any]]] = defaultdict(list)
    for spec in timestep_specs:
        grouped[(str(spec["landscape"]), float(spec["dt"]))].append(spec)
    expected_replicates = len(config["seeds"])
    if len(grouped) != 9 or any(len(items) != expected_replicates for items in grouped.values()):
        raise RuntimeError("two-window gate requires a complete 3x3 timestep matrix")

    window = int(config["steady_snapshots"])
    bounds = tuple(float(value) for value in config["bounds"])
    metrics = stationary_metrics_for_experiment(str(config["experiment_id"]))
    precision_absolute = config["independent_precision_absolute_half_widths"]
    precision_relative = config["independent_precision_relative_half_widths"]
    adjacent_absolute = config["adjacent_window_absolute_bounds"]
    adjacent_relative = config["adjacent_window_relative_bounds"]
    conditions: dict[str, Any] = {}

    for (landscape, dt), condition_specs in sorted(grouped.items()):
        replicate_series: dict[str, list[list[float]]] = {metric: [] for metric in metrics}
        for spec in condition_specs:
            run_dir = project_path(spec["run_dir"], must_exist=True)
            snapshots = sorted(run_dir.glob("snap_*.csv"))
            if len(snapshots) < 2 * window:
                raise RuntimeError(f"{spec['run_id']} has fewer than {2 * window} snapshots")
            resource = np.load(project_path(spec["resource_npy"], must_exist=True), allow_pickle=False)
            rows = [
                snapshot_metrics(read_snapshot_csv(path), resource, bounds)
                for path in snapshots[-2 * window :]
            ]
            for metric in metrics:
                replicate_series[metric].append([float(row[metric]) for row in rows])

        metric_reports: dict[str, Any] = {}
        for metric, raw_series in replicate_series.items():
            arrays = np.asarray(raw_series, dtype=np.float64)
            previous_arrays = arrays[:, :window]
            tail_arrays = arrays[:, window:]
            previous_run_means = previous_arrays.mean(axis=1)
            tail_run_means = tail_arrays.mean(axis=1)
            tail_ensemble = tail_arrays.mean(axis=0)
            status = metric_status(metric, float(np.mean(tail_ensemble)))
            temporal = _stationarity_for_metric(
                metric,
                tail_ensemble,
                status,
                max_normalized_drift=float(config["stationarity_max_normalized_drift"]),
                min_effective_samples=float(config["stationarity_min_ess"]),
                reversal_span_sigma=float(config.get("stationarity_reversal_span_sigma", 1.0)),
            )
            precision = _independent_precision_summary(
                tail_run_means,
                absolute_half_width=(
                    float(precision_absolute[metric]) if metric in precision_absolute else None
                ),
                relative_half_width=(
                    float(precision_relative[metric]) if metric in precision_relative else None
                ),
            )
            adjacent = _adjacent_window_summary(
                previous_run_means,
                tail_run_means,
                absolute_bound=(
                    float(adjacent_absolute[metric]) if metric in adjacent_absolute else None
                ),
                relative_bound=(
                    float(adjacent_relative[metric]) if metric in adjacent_relative else None
                ),
            )
            metric_reports[metric] = {
                "tail_temporal_diagnostic": temporal,
                "adjacent_window_stability": adjacent,
                "independent_replicate_precision": precision,
            }

        tail_stationarity_pass = all(
            bool(item["tail_temporal_diagnostic"].get("stationarity_pass", False))
            for item in metric_reports.values()
        )
        temporal_ess_pass = all(
            bool(item["tail_temporal_diagnostic"].get("precision_pass", False))
            for item in metric_reports.values()
        )
        adjacent_pass = all(
            bool(item["adjacent_window_stability"]["pass"])
            for item in metric_reports.values()
        )
        precision_pass = all(
            bool(item["independent_replicate_precision"]["pass"])
            for item in metric_reports.values()
        )
        conditions[f"{landscape}--dt-{dt:.17g}"] = {
            "landscape": landscape,
            "dt": dt,
            "replicates": len(condition_specs),
            "tail_stationarity_pass": tail_stationarity_pass,
            "adjacent_window_stability_pass": adjacent_pass,
            "independent_replicate_precision_pass": precision_pass,
            "temporal_ess_diagnostic_pass": temporal_ess_pass,
            "metrics": metric_reports,
        }

    tail_stationarity_valid = all(
        item["tail_stationarity_pass"] for item in conditions.values()
    )
    adjacent_valid = all(
        item["adjacent_window_stability_pass"] for item in conditions.values()
    )
    precision_valid = all(
        item["independent_replicate_precision_pass"] for item in conditions.values()
    )
    temporal_ess_valid = all(
        item["temporal_ess_diagnostic_pass"] for item in conditions.values()
    )
    payload = {
        "experiment": config["experiment_id"],
        "gate_unit": "condition_ensemble_two_window",
        "window_snapshots": window,
        "replicates_per_condition": expected_replicates,
        "tail_stationarity_valid": tail_stationarity_valid,
        "adjacent_window_stability_valid": adjacent_valid,
        "independent_replicate_precision_valid": precision_valid,
        "temporal_ess_diagnostic_valid": temporal_ess_valid,
        "conditions": conditions,
        "pass": bool(tail_stationarity_valid and adjacent_valid and precision_valid),
        "temporal_ess_policy": (
            "Reported as a dynamical autocorrelation diagnostic. Precision of the "
            "condition estimand is gated on independent seed-level window means."
        ),
    }
    write_json(output_dir / "steady_estimand_report.json", payload)

    legacy_conditions: dict[str, Any] = {}
    for key, item in conditions.items():
        legacy_conditions[key] = {
            "landscape": item["landscape"],
            "dt": item["dt"],
            "replicates": item["replicates"],
            "stationarity_pass": item["tail_stationarity_pass"],
            "precision_pass": item["temporal_ess_diagnostic_pass"],
            "metrics": {
                metric: report["tail_temporal_diagnostic"]
                for metric, report in item["metrics"].items()
            },
        }
    legacy = {
        "experiment": config["experiment_id"],
        "gate_unit": "condition_ensemble_temporal_diagnostic",
        "window_snapshots": window,
        "replicates_per_condition": expected_replicates,
        "stationarity_valid": tail_stationarity_valid,
        "precision_valid": temporal_ess_valid,
        "conditions": legacy_conditions,
        "pass": bool(tail_stationarity_valid and temporal_ess_valid),
        "gate_role": "diagnostic_only_for_condition_ensemble_two_window",
    }
    write_json(output_dir / "ensemble_stationarity_report.json", legacy)
    return payload


def aggregate_v1(
    rows: Sequence[Mapping[str, Any]],
    config: Mapping[str, Any],
    output_dir: Path,
    ensemble_stationarity: Mapping[str, Any] | None = None,
    steady_estimand: Mapping[str, Any] | None = None,
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
    stationarity_gate_unit = str(config.get("stationarity_gate_unit", "run"))
    adjacent_window_pass: bool | None = None
    if stationarity_gate_unit == "condition_ensemble_two_window":
        if steady_estimand is None:
            raise ValueError("condition_ensemble_two_window gate requires a steady report")
        stationarity_pass = bool(
            steady_estimand["tail_stationarity_valid"]
            and steady_estimand["adjacent_window_stability_valid"]
        )
        adjacent_window_pass = bool(steady_estimand["adjacent_window_stability_valid"])
        precision_pass = bool(steady_estimand["independent_replicate_precision_valid"])
    elif stationarity_gate_unit == "condition_ensemble":
        if ensemble_stationarity is None:
            raise ValueError("condition_ensemble gate requires an ensemble report")
        stationarity_pass = bool(ensemble_stationarity["stationarity_valid"])
        precision_pass = bool(ensemble_stationarity["precision_valid"])
    else:
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
        "experiment": str(config.get("experiment_id", "V1-NONFLAT-CALIBRATION-C4")),
        "pass": passed,
        "scope": "non-flat weak timestep convergence plus deterministic exchange-order sensitivity",
        "timesteps": {"coarse": coarse_dt, "fine": fine_dt, "finest": finest_dt},
        "gate_layers": {
            "invariants": all(invariant_checks.values()),
            "timestep_convergence": timestep_pass,
            "storage_order_sensitivity": order_pass,
            "stationarity": stationarity_pass,
            "precision": precision_pass,
            "adjacent_window_stability": adjacent_window_pass,
        },
        "stationarity_gate_unit": stationarity_gate_unit,
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
    if experiment not in {
        "V1P-RUNTIME-PILOT-C4",
        "V1-NONFLAT-CALIBRATION-C4",
        "V1B-NONFLAT-CALIBRATION-C4",
        "V1C-NONFLAT-CALIBRATION-C4",
        "V1E-NONFLAT-CALIBRATION-C4",
        "V1F-NONFLAT-CALIBRATION-C4",
    }:
        raise ValueError("unexpected experiment_id")
    _validate_conditions(config.get("conditions"))
    if experiment != "V1P-RUNTIME-PILOT-C4":
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
        ensemble_stationarity = None
        steady_estimand = None
        gate_unit = config.get("stationarity_gate_unit", "run")
        if gate_unit == "condition_ensemble":
            ensemble_stationarity = aggregate_condition_ensemble_stationarity(
                specs, config, output_dir
            )
        elif gate_unit == "condition_ensemble_two_window":
            steady_estimand = aggregate_two_window_steady_estimand(
                specs, config, output_dir
            )
        payload = aggregate_v1(
            rows,
            config,
            output_dir,
            ensemble_stationarity=ensemble_stationarity,
            steady_estimand=steady_estimand,
        )
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
    # A completed calibration may legitimately falsify its numerical gate.
    # jobctl's process exit code represents execution integrity, while
    # payload["pass"] represents the scientific/numerical verdict. Returning
    # non-zero for a valid negative result incorrectly labels all artifacts as
    # an execution failure and prevents normal reconciliation.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
