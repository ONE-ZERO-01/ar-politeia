#!/usr/bin/env python3
"""Diagnose V1E independent-replicate requirements on fixed umi outputs."""

from __future__ import annotations

import argparse
import csv
import math
import platform
from pathlib import Path
from typing import Any, Mapping

from scipy.stats import chi2

from landscape_study import sha256_file, write_json
from run_landscape_study import load_json, project_path


def _require_umi() -> None:
    if platform.node().split(".", 1)[0] != "umi":
        raise RuntimeError("V1ED diagnostics must run on host umi")


def _required_replicates(
    *,
    sample_sd: float,
    threshold: float,
    mean: float | None,
    bound_kind: str,
    current_replicates: int,
    upper_sd_alpha: float,
) -> dict[str, Any]:
    if sample_sd < 0.0 or threshold <= 0.0 or current_replicates < 3:
        raise ValueError("invalid replicate-requirement inputs")
    if bound_kind == "absolute":
        denominator = threshold
    elif bound_kind in {"relative_to_absolute_mean", "relative_to_larger_window_mean"}:
        if mean is None or abs(mean) <= 1e-12:
            raise ValueError("relative precision requires a nonzero mean")
        denominator = threshold * abs(mean)
    else:
        raise ValueError(f"unsupported bound_kind: {bound_kind}")
    point = max(3, int(math.ceil((2.0 * sample_sd / denominator) ** 2)))
    degrees_freedom = current_replicates - 1
    lower_quantile = float(chi2.ppf(upper_sd_alpha, degrees_freedom))
    upper_sd = sample_sd * math.sqrt(degrees_freedom / lower_quantile)
    conservative = max(3, int(math.ceil((2.0 * upper_sd / denominator) ** 2)))
    return {
        "point_estimate": point,
        "upper_sd_alpha": upper_sd_alpha,
        "upper_sample_sd": upper_sd,
        "conservative_estimate": conservative,
        "calculation": "n such that 2*SD/sqrt(n) <= declared precision width",
    }


def _next_power_of_two(value: int) -> int:
    return 1 << (max(1, value) - 1).bit_length()


def _paired_precision(
    csv_path: Path,
    *,
    finest_dt: float,
    metrics: Mapping[str, float],
    upper_sd_alpha: float,
) -> dict[str, Any]:
    values: dict[int, dict[str, dict[str, float]]] = {}
    with csv_path.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            if row["calibration_component"] != "timestep":
                continue
            if abs(float(row["dt"]) - finest_dt) > 1e-12:
                continue
            landscape = row["landscape"]
            if landscape not in {"clustered", "shuffled"}:
                continue
            seed = int(row["seed"])
            values.setdefault(seed, {})[landscape] = {
                metric: float(row[metric]) for metric in metrics
            }
    if not values or any(set(item) != {"clustered", "shuffled"} for item in values.values()):
        raise RuntimeError("paired precision requires complete clustered/shuffled seed pairs")
    output: dict[str, Any] = {}
    for metric, threshold in metrics.items():
        differences = [
            item["clustered"][metric] - item["shuffled"][metric]
            for _, item in sorted(values.items())
        ]
        count = len(differences)
        mean = sum(differences) / count
        sample_sd = math.sqrt(sum((value - mean) ** 2 for value in differences) / (count - 1))
        output[metric] = {
            "replicates": count,
            "paired_sample_sd": sample_sd,
            "precision_width": float(threshold),
            "requirements": _required_replicates(
                sample_sd=sample_sd,
                threshold=float(threshold),
                mean=None,
                bound_kind="absolute",
                current_replicates=count,
                upper_sd_alpha=upper_sd_alpha,
            ),
            "effect_direction_or_magnitude_used": False,
        }
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    _require_umi()
    config_path = project_path(args.config, must_exist=True)
    config = load_json(config_path)
    if config.get("experiment_id") != "V1ED-SAMPLING-DIAGNOSTIC-C4":
        raise ValueError("unexpected experiment_id")
    output_dir = project_path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    source = project_path(config["source_workspace"], must_exist=True)
    source_paths = {
        "steady_estimand_report": source / "steady_estimand_report.json",
        "replicate_metrics": source / "replicate_metrics.csv",
        "numerical_calibration": source / "numerical_calibration.json",
    }
    for key, path in source_paths.items():
        actual = sha256_file(path)
        expected = str(config["source_sha256"][key])
        if actual != expected:
            raise RuntimeError(f"source {key} checksum mismatch: {actual} != {expected}")

    report = load_json(source_paths["steady_estimand_report"])
    expected = config["expected_v1e_gate"]
    actual = {
        "tail_stationarity_valid": bool(report["tail_stationarity_valid"]),
        "adjacent_window_stability_valid": bool(report["adjacent_window_stability_valid"]),
        "independent_replicate_precision_valid": bool(
            report["independent_replicate_precision_valid"]
        ),
        "temporal_ess_diagnostic_valid": bool(report["temporal_ess_diagnostic_valid"]),
    }
    if actual != expected:
        raise RuntimeError(f"V1ED failed to reproduce V1E gate: {actual} != {expected}")

    alpha = float(config["upper_sd_alpha"])
    requirements: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    for condition, condition_report in report["conditions"].items():
        for metric, metric_report in condition_report["metrics"].items():
            precision = metric_report["independent_replicate_precision"]
            requirement = _required_replicates(
                sample_sd=float(precision["sample_sd"]),
                threshold=float(precision["threshold"]),
                mean=float(precision["mean"]),
                bound_kind=str(precision["bound_kind"]),
                current_replicates=int(precision["replicates"]),
                upper_sd_alpha=alpha,
            )
            item = {
                "condition": condition,
                "metric": metric,
                "current_pass": bool(precision["pass"]),
                "current_observed_bound": float(precision["observed_bound"]),
                "threshold": float(precision["threshold"]),
                "bound_kind": precision["bound_kind"],
                "requirements": requirement,
            }
            requirements.append(item)
            if not item["current_pass"]:
                failures.append(item)

    paired = _paired_precision(
        source_paths["replicate_metrics"],
        finest_dt=float(config["finest_dt"]),
        metrics=config["paired_precision_widths"],
        upper_sd_alpha=alpha,
    )
    maximum_point = max(item["requirements"]["point_estimate"] for item in requirements)
    maximum_conservative = max(
        item["requirements"]["conservative_estimate"] for item in requirements
    )
    recommended = _next_power_of_two(maximum_conservative)
    payload = {
        "experiment": config["experiment_id"],
        "status": "completed",
        "pass": True,
        "non_evidentiary": True,
        "source_experiment": config["source_experiment"],
        "source_sha256": config["source_sha256"],
        "baseline_reproduction": {"pass": True, "actual": actual, "expected": expected},
        "condition_precision_requirements": requirements,
        "failed_condition_precision_cells": failures,
        "paired_clustered_shuffled_precision_at_finest_dt": paired,
        "maximum_point_estimate": maximum_point,
        "maximum_conservative_estimate": maximum_conservative,
        "recommended_independent_replicates": recommended,
        "recommendation_policy": (
            "Round the largest one-sided upper-SD requirement to the next power of two. "
            "No effect direction or magnitude enters the paired requirement."
        ),
        "interpretation_boundary": (
            "This diagnoses V1E sampling only. It cannot change V1E and any selected "
            "replicate count requires new independent simulations."
        ),
    }
    diagnostic_path = output_dir / "sampling_diagnostic.json"
    write_json(diagnostic_path, payload)
    result = {
        "experiment": config["experiment_id"],
        "status": "completed",
        "pass": True,
        "non_evidentiary": True,
        "baseline_reproduction": payload["baseline_reproduction"],
        "failed_precision_cells": len(failures),
        "maximum_point_estimate": maximum_point,
        "maximum_conservative_estimate": maximum_conservative,
        "recommended_independent_replicates": recommended,
        "diagnostic_sha256": sha256_file(diagnostic_path),
        "config_sha256": sha256_file(config_path),
    }
    write_json(output_dir / "result.json", result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
