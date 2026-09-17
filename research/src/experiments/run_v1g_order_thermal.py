#!/usr/bin/env python3
"""V1G: is the storage-order channel bounded at the reference temperature?

V1F's ``order`` layer is *forced* to ``temperature = 0.0`` (``run_v1_calibration``
validates that), so the frozen numerical bounds were measured with the only
random quantity that is consumed by array index switched off. The reference
configuration E1-C4/E2-C4 actually run uses ``temperature = 0.5``, where the
Langevin thermal noise is drawn per array slot from a stateful RNG. Row order
therefore chooses which particle receives which noise realisation, and that
coupling has never been measured (S18).

V1G is exactly V1F's order layer with one parameter changed: ``T = 0.0 -> 0.5``.
Same landscape (``clustered``), same dt, same duration, same window, and the
same 64 frozen V1F seeds, with a bitwise-identical *physical* initial state in
two row orders (explicit phase state, so the initial momenta come from the file
and not from a position-dependent draw). The comparison is paired per seed and
uses the same conservative ``|mean| + 2*SE`` primitive V1F used, so V1G's bound
is directly comparable to the frozen ``numerical_resolution_limits``.

This is a **diagnostic**, not a confirmatory experiment: it produces no
scientific claim about E1/E2 and must not be cited as evidence for one. It
answers a single question — does the already-frozen numerical error ceiling
cover the storage-order channel at the reference temperature? — and its verdict
decides whether the ledger's S18 stays an open item (``bounded``) or becomes a
C++ change plus recalibration (``exceeds-frozen-limit``, i.e. the frozen ceiling
lacks a leg and the thermal noise should be keyed by stable GID like S07 did for
the exchange noise).

The bound is only as strong as its seed count, and 64 is V1F's, not more.
"""

from __future__ import annotations

import argparse
import json
import platform
from pathlib import Path
from typing import Any, Mapping, Sequence

from landscape_study import sha256_file, write_json
from run_landscape_study import (
    PROJECT_ROOT,
    analyze_runs,
    execute_runs,
    load_json,
    prepare_inputs,
    project_path,
)
from run_v1_calibration import CALIBRATION_METRICS, _weak_bound

EXPERIMENT_ID = "V1G-ORDER-THERMAL-C4"
REFERENCE_EXPERIMENT = "E1-MATCHED-LANDSCAPES-C4"
PARAMETER_LOCK = "research/parameter_lock.cycle4.json"
V1F_CALIBRATION = "research/jobs/V1F-NONFLAT-CALIBRATION-C4/numerical_calibration.json"
V1F_SEEDS = "research/jobs/V1F-NONFLAT-CALIBRATION-C4/seeds.txt"
REFERENCE_CONFIG = f"research/jobs/{REFERENCE_EXPERIMENT}/config.json"

# What the probe holds fixed. Each is cross-checked against the reference
# experiment's tracked config, so if the reference protocol moves, V1G stops
# being comparable and must be redesigned rather than silently drifting.
FIXED_PROTOCOL_KEYS = (
    "temperature",
    "dt",
    "total_time",
    "output_time_interval",
    "steady_snapshots",
    "population",
    "grid_shape",
    "bounds",
)
ORDER_LANDSCAPE = "clustered"


def _require_umi() -> None:
    if platform.node().split(".", 1)[0] != "umi":
        raise RuntimeError("V1G must run on host umi (numerical experiments live there)")


def load_frozen_bound(project_root: Path) -> dict[str, Any]:
    """Read the frozen ceiling straight out of the lock, verifying the chain.

    The thresholds must not be re-derived, re-rounded, or copied: the whole
    point is to compare against the numbers the authorization actually froze.
    So the values are read through the lock and the tracked calibration file is
    re-hashed, and the binary bound in ``simulator_validation`` is required to
    agree with the one in ``numerical_calibration`` (the S14 cross-check).
    """
    lock = load_json(project_root / PARAMETER_LOCK)
    calibration = lock["numerical_calibration"]
    tracked = project_root / str(calibration["path"])
    actual_sha = sha256_file(tracked)
    if actual_sha != calibration["sha256"]:
        raise RuntimeError(
            "the tracked V1F calibration no longer matches the lock "
            f"({actual_sha} != {calibration['sha256']}); V1G's thresholds would "
            "not be the frozen ones"
        )
    document = load_json(tracked)
    limits = calibration["numerical_resolution_limits"]
    if document["numerical_resolution_limits"] != limits:
        raise RuntimeError(
            "the lock and the tracked calibration disagree on the numerical "
            "resolution limits"
        )
    binary_sha256 = str(calibration["reference_binary_sha256"])
    validated = str(lock["simulator_validation"]["binary_sha256"])
    if validated != binary_sha256:
        raise RuntimeError(
            "the lock binds two different reference binaries (S14): "
            f"{validated} vs {binary_sha256}"
        )
    return {
        "limits": {metric: float(limits[metric]) for metric in CALIBRATION_METRICS},
        "binary_sha256": binary_sha256,
        "calibration_sha256": actual_sha,
        "calibration_path": str(calibration["path"]),
        "t0_order_layer": {
            metric: document["storage_order_sensitivity"][metric]
            for metric in CALIBRATION_METRICS
            if metric in document.get("storage_order_sensitivity", {})
        },
    }


def reference_protocol(project_root: Path) -> dict[str, Any]:
    config = load_json(project_root / REFERENCE_CONFIG)
    return {key: config[key] for key in FIXED_PROTOCOL_KEYS}


def frozen_v1f_seeds(project_root: Path) -> list[int]:
    text = (project_root / V1F_SEEDS).read_text(encoding="utf-8")
    return [int(line) for line in text.split() if line.strip()]


def validate_v1g_config(
    config: Mapping[str, Any],
    *,
    reference: Mapping[str, Any],
    expected_seeds: Sequence[int],
) -> list[dict[str, Any]]:
    """Fail fast on anything that would make the comparison non-comparable."""
    if str(config.get("experiment_id", "")) != EXPERIMENT_ID:
        raise ValueError(f"unexpected experiment_id: {config.get('experiment_id')!r}")

    for key in FIXED_PROTOCOL_KEYS:
        if key not in config:
            raise ValueError(f"V1G config must pin {key}")
        if config[key] != reference[key]:
            raise ValueError(
                f"V1G must run the reference protocol; {key} is "
                f"{config[key]!r} but {REFERENCE_EXPERIMENT} uses {reference[key]!r}"
            )

    seeds = [int(seed) for seed in config.get("seeds", [])]
    if sorted(seeds) != sorted(int(seed) for seed in expected_seeds):
        raise ValueError(
            "V1G must reuse the frozen V1F seeds so its bound is comparable to "
            "the frozen order-layer bound at T=0"
        )

    raw_conditions = config.get("conditions")
    if not isinstance(raw_conditions, list) or not raw_conditions:
        raise ValueError("V1G requires a non-empty conditions list")
    conditions: list[dict[str, Any]] = []
    for raw in raw_conditions:
        condition = dict(raw)
        name = str(condition.get("name", ""))
        if not name:
            raise ValueError("each V1G condition needs a name")
        if str(condition.get("landscape")) != ORDER_LANDSCAPE:
            raise ValueError(
                f"V1G holds the landscape fixed at {ORDER_LANDSCAPE!r}"
            )
        if float(condition.get("dt", 0.0)) != float(reference["dt"]):
            raise ValueError("V1G holds dt fixed at the reference dt")
        if condition.get("storage_order") not in {"canonical", "permuted"}:
            raise ValueError(f"V1G condition {name} needs a storage_order")
        if condition.get("explicit_phase_state") is not True:
            # Without this the initial momenta are drawn per row position, so
            # the two orders would not share a physical initial state and the
            # difference would conflate row order with different initial data.
            raise ValueError(
                f"V1G condition {name} requires explicit_phase_state=true"
            )
        if float(condition.get("temperature", -1.0)) != float(reference["temperature"]):
            raise ValueError(
                f"V1G condition {name} must run at the reference temperature "
                f"{reference['temperature']}; T=0 would reproduce V1F instead"
            )
        conditions.append(condition)

    orders = sorted(str(item["storage_order"]) for item in conditions)
    if orders != ["canonical", "permuted"]:
        raise ValueError(f"V1G requires exactly one canonical and one permuted cell, got {orders}")
    return conditions


def paired_order_bound(
    rows: Sequence[Mapping[str, Any]],
    specs: Sequence[Mapping[str, Any]],
    *,
    limits: Mapping[str, float],
) -> dict[str, Any]:
    """Per-metric paired canonical-vs-permuted bound at the reference temperature."""
    if len(rows) != len(specs):
        raise ValueError("metric rows and run specs are not aligned")
    by_order: dict[str, dict[int, Mapping[str, Any]]] = {"canonical": {}, "permuted": {}}
    for row, spec in zip(rows, specs):
        order = str(spec["storage_order"])
        seed = int(spec["seed"])
        if order not in by_order:
            raise ValueError(f"unexpected storage_order in spec: {order!r}")
        if seed in by_order[order]:
            raise ValueError(f"duplicate {order} replicate for seed {seed}")
        by_order[order][seed] = row

    canonical_seeds = set(by_order["canonical"])
    permuted_seeds = set(by_order["permuted"])
    if canonical_seeds != permuted_seeds:
        raise ValueError("canonical and permuted replicates are not the same seed set")

    by_metric: dict[str, Any] = {}
    overall = True
    for metric in CALIBRATION_METRICS:
        seeds = sorted(canonical_seeds)
        bound = _weak_bound(
            [float(by_order["canonical"][seed][metric]) for seed in seeds],
            [float(by_order["permuted"][seed][metric]) for seed in seeds],
        )
        limit = float(limits[metric])
        bounded = bound["two_se_bound"] <= limit
        overall = overall and bounded
        by_metric[metric] = {
            "bound": bound,
            "frozen_numerical_resolution_limit": limit,
            "bounded": bounded,
        }
    return {"by_metric": by_metric, "pass": overall}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    _require_umi()

    project_root = PROJECT_ROOT
    config_path = project_path(args.config, must_exist=True)
    output_dir = project_path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    config = load_json(config_path)

    frozen = load_frozen_bound(project_root)
    reference = reference_protocol(project_root)
    seeds = frozen_v1f_seeds(project_root)
    validate_v1g_config(config, reference=reference, expected_seeds=seeds)

    binary = project_path(config["binary"], must_exist=True)
    binary_sha256 = sha256_file(binary)
    if binary_sha256 != frozen["binary_sha256"]:
        raise RuntimeError(
            "V1G must probe the calibrated reference binary: "
            f"{binary_sha256} != {frozen['binary_sha256']}"
        )

    specs = prepare_inputs(EXPERIMENT_ID, config, output_dir)
    expected_runs = 2 * len(seeds)
    if len(specs) != expected_runs:
        raise RuntimeError(f"expected {expected_runs} runs, prepared {len(specs)}")

    execution = execute_runs(
        specs,
        binary,
        timeout_seconds=int(config.get("per_run_timeout_seconds", 10800)),
        omp_threads=int(config.get("omp_threads", 1)),
        parallel=int(config.get("parallel", 1)),
    )
    rows = analyze_runs(EXPERIMENT_ID, config, output_dir, specs)
    if len(rows) != len(specs):
        raise RuntimeError("analyze_runs did not return one row per run")

    instability = [
        str(row.get("run_id", "?")) for row in rows if not bool(row.get("stationarity_pass"))
    ]
    result = paired_order_bound(rows, specs, limits=frozen["limits"])
    # Window health is reported, not gating: V1G is a two-cell diagnostic and
    # the calibrated gate unit is the 3x3 condition ensemble (two windows),
    # which a two-cell design cannot reproduce. Run-level failures are a caveat
    # on how much the bound can be trusted, not a verdict of their own.
    window_caveat = None
    if instability:
        window_caveat = (
            f"{len(instability)} of {len(rows)} runs fail the per-run steady-window "
            "checks; the bound below inherits that instability"
        )

    reference_comparison: dict[str, Any] = {}
    for metric in CALIBRATION_METRICS:
        t0 = frozen["t0_order_layer"].get(metric)
        if t0 is None:
            continue
        for dt_key, value in t0["by_dt"].items():
            if float(dt_key) == float(reference["dt"]):
                reference_comparison[metric] = {
                    "v1f_temperature": 0.0,
                    "v1f_two_se_bound": float(value["two_se_bound"]),
                    "v1g_two_se_bound": float(result["by_metric"][metric]["bound"]["two_se_bound"]),
                }

    report = {
        "experiment": EXPERIMENT_ID,
        "diagnostic_only": True,
        "scope": (
            "Measures the storage-order channel at the reference temperature. "
            "Produces no confirmatory scientific claim about E1/E2 and must not "
            "be cited as evidence for one."
        ),
        "binding": {
            "parameter_lock": PARAMETER_LOCK,
            "calibration_path": frozen["calibration_path"],
            "calibration_sha256": frozen["calibration_sha256"],
            "reference_binary_sha256": frozen["binary_sha256"],
        },
        "protocol": {
            "landscape": ORDER_LANDSCAPE,
            "temperature": reference["temperature"],
            "dt": reference["dt"],
            "total_time": reference["total_time"],
            "steady_snapshots": reference["steady_snapshots"],
            "replicates_per_order": len(seeds),
            "seeds": sorted(int(seed) for seed in seeds),
        },
        "run_count": len(specs),
        "execution": execution,
        "stationarity_failures": instability,
        "window_caveat": window_caveat,
        "by_metric": result["by_metric"],
        "reference_comparison_informational": reference_comparison,
        "pass": bool(result["pass"]),
        "verdict": "bounded" if result["pass"] else "exceeds-frozen-limit",
    }
    write_json(output_dir / "order_thermal_report.json", report)

    print(json.dumps({"pass": report["pass"], "verdict": report["verdict"]}, indent=1))
    for metric in CALIBRATION_METRICS:
        entry = report["by_metric"][metric]
        print(
            f"  {metric:32s} two_se_bound={entry['bound']['two_se_bound']:.6g} "
            f"limit={entry['frozen_numerical_resolution_limit']:.6g} "
            f"bound={'PASS' if entry['bounded'] else 'FAIL'}"
        )
    if window_caveat:
        print(f"  caveat: {window_caveat}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
