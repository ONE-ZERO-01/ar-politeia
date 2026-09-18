#!/usr/bin/env python3
"""V1H: extend V1F's frozen numerical resolution limits to metrics V1F recorded.

V1H runs no simulator and creates no run directory. It re-reads V1F's retained
``replicate_metrics.csv`` and re-derives, with V1F's own bound primitive
(``run_v1_calibration._weak_bound``), the per-layer bounds that produced
``numerical_calibration.json``.

The extension is published **only** if V1F's four frozen limits reproduce
bit-for-bit. A near miss is a failed extension, not a second opinion: if the
numbers do not reproduce then whatever this script computed is a fresh
measurement of a different object, and calling it an extension would launder a new
number into an old one.

No ceiling is invented for the newly covered metric. A ceiling is a pre-registered
failure threshold, so choosing one after seeing the data would be an unregistered
threshold. The extended metric therefore clears only the two criteria that need no
new number (the fine-vs-finest trend, and its storage-order bound being dominated
by discretization), and its ceiling is recorded as null together with the reason.
"""

from __future__ import annotations

import argparse
import csv
import platform
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence

from landscape_study import sha256_file, write_json
from run_landscape_study import load_json, project_path
from run_v1_calibration import CALIBRATION_METRICS, _weak_bound

EXPERIMENT = "V1H-CALIBRATION-EXTENSION-C4"
SOURCE_EXPERIMENT = "V1F-NONFLAT-CALIBRATION-C4"

# The fields of every bound V1F recorded. Recomputing all of them (not just the
# surviving maximum) is what makes "same computation path" checkable rather than
# merely plausible: a bound that agrees only after a max() hides disagreement.
BOUND_FIELDS = (
    "absolute_mean_difference",
    "signed_mean_difference",
    "paired_sample_sd",
    "standard_error",
    "two_se_bound",
    "replicates",
)

CEILING_POLICY = (
    "No ceiling is invented for an extended metric: a ceiling is a pre-registered "
    "failure threshold, so writing one after seeing the data would be an "
    "unregistered threshold. Freeze it together with the scientific SESOI."
)

# Metrics deliberately left out, each with the reason. Named rather than omitted
# so that a reader sees a decision instead of a gap.
OUT_OF_SCOPE = {
    "mean_wealth": (
        "Not extended. It is absent from the retained replicate_metrics.csv because "
        "V1F ran before snapshot_metrics computed it, so recovering it needs a "
        "raw-snapshot pass (~28 GB) rather than a CSV re-analysis. The design "
        "registers it as a level audit, not an estimand (design section 15.5)."
    ),
}


def _require_umi() -> None:
    if platform.node().split(".", 1)[0] != "umi":
        raise RuntimeError("V1H must run on host umi (the retained CSV lives there)")


def _series(
    rows: Sequence[Mapping[str, str]],
    *,
    component: str,
    dt: float,
    metric: str,
    landscape: str | None = None,
    storage_order: str | None = None,
) -> Dict[int, float]:
    """One (component, dt, metric) column keyed by seed, refusing ambiguity."""
    values: Dict[int, float] = {}
    landscapes: set[str] = set()
    for row in rows:
        if row["calibration_component"] != component:
            continue
        if abs(float(row["dt"]) - dt) > 1e-12:
            continue
        if landscape is not None and row["landscape"] != landscape:
            continue
        if storage_order is not None and row.get("storage_order") != storage_order:
            continue
        seed = int(row["seed"])
        if seed in values:
            raise RuntimeError(
                f"the retained table carries two {component} rows for seed {seed} "
                f"at dt={dt!r}; the layer is not uniquely determined"
            )
        landscapes.add(row["landscape"])
        values[seed] = float(row[metric])
    if not values:
        raise RuntimeError(
            f"the retained table has no {component} rows at dt={dt!r} "
            f"(storage_order={storage_order!r})"
        )
    if len(landscapes) != 1:
        raise RuntimeError(
            f"the {component}/{storage_order} layer spans landscapes "
            f"{sorted(landscapes)}; a storage-order bound is only defined within "
            "one landscape"
        )
    return values


def _seeds_present_across(
    per_dt: Mapping[float, Mapping[int, float]], dts: Sequence[float]
) -> List[int]:
    common = set(per_dt[dts[0]])
    for dt in dts[1:]:
        common &= set(per_dt[dt])
    seeds = sorted(common)
    if len(seeds) < 3:
        raise RuntimeError(
            f"only {len(seeds)} seeds are present at every timestep; a paired "
            "bound needs at least three matched replicates"
        )
    return seeds


def recompute_layer_bounds(
    rows: Sequence[Mapping[str, str]],
    *,
    timesteps: Sequence[float],
    metrics: Sequence[str],
) -> Dict[str, Any]:
    """Re-derive V1F's discretization and storage-order bounds from the table."""
    dts = sorted((float(value) for value in timesteps), reverse=True)
    if len(dts) != 3:
        raise ValueError("V1H requires exactly three timesteps")
    coarse_dt, fine_dt, finest_dt = dts

    missing = [metric for metric in metrics if metric not in rows[0]]
    if missing:
        raise RuntimeError(
            f"the retained table has no column for {missing}; an extension cannot "
            "quietly skip a requested metric (see OUT_OF_SCOPE for the ones left out)"
        )

    discretization: Dict[str, Any] = {}
    for landscape in ("smooth", "clustered", "shuffled"):
        cell: Dict[str, Any] = {}
        for metric in metrics:
            per_dt = {
                dt: _series(
                    rows, component="timestep", dt=dt, metric=metric, landscape=landscape
                )
                for dt in dts
            }
            seeds = _seeds_present_across(per_dt, dts)
            cell[metric] = {
                "coarse_vs_fine": _weak_bound(
                    [per_dt[coarse_dt][seed] for seed in seeds],
                    [per_dt[fine_dt][seed] for seed in seeds],
                ),
                "fine_vs_finest": _weak_bound(
                    [per_dt[fine_dt][seed] for seed in seeds],
                    [per_dt[finest_dt][seed] for seed in seeds],
                ),
            }
        discretization[landscape] = cell

    order: Dict[str, Any] = {}
    for metric in metrics:
        by_dt: Dict[str, Any] = {}
        for dt in dts:
            canonical = _series(
                rows,
                component="order",
                dt=dt,
                metric=metric,
                storage_order="canonical",
            )
            permuted = _series(
                rows,
                component="order",
                dt=dt,
                metric=metric,
                storage_order="permuted",
            )
            seeds = sorted(set(canonical) & set(permuted))
            if len(seeds) < 3:
                raise RuntimeError(
                    f"{metric}: only {len(seeds)} seeds carry both storage orders at "
                    f"dt={dt!r}"
                )
            by_dt[f"{dt:.17g}"] = _weak_bound(
                [canonical[seed] for seed in seeds],
                [permuted[seed] for seed in seeds],
            )
        order[metric] = by_dt

    return {
        "timesteps": [coarse_dt, fine_dt, finest_dt],
        "discretization": discretization,
        "storage_order": order,
    }


def frozen_mismatches(
    computed: Mapping[str, Any], frozen: Mapping[str, Any]
) -> List[str]:
    """Every recorded field that the recomputation does not reproduce exactly."""
    mismatches: List[str] = []
    recorded_discretization = frozen.get("discretization", {})
    for landscape, cell in computed["discretization"].items():
        for metric, layers in cell.items():
            recorded = recorded_discretization.get(landscape, {}).get(metric)
            if recorded is None:
                continue
            for layer in ("coarse_vs_fine", "fine_vs_finest"):
                for field in BOUND_FIELDS:
                    got = layers[layer][field]
                    want = recorded[layer][field]
                    if got != want:
                        mismatches.append(
                            f"discretization/{landscape}/{metric}/{layer}/{field}: "
                            f"recomputed {got!r} != frozen {want!r}"
                        )

    recorded_order = frozen.get("storage_order_sensitivity", {})
    for metric, by_dt in computed["storage_order"].items():
        recorded = recorded_order.get(metric)
        if not isinstance(recorded, Mapping):
            continue
        for dt_key, bound in by_dt.items():
            frozen_bound = recorded.get("by_dt", {}).get(dt_key)
            if frozen_bound is None:
                mismatches.append(
                    f"storage_order/{metric}/{dt_key}: the frozen calibration "
                    "records no bound for this timestep"
                )
                continue
            for field in BOUND_FIELDS:
                got = bound[field]
                want = frozen_bound[field]
                if got != want:
                    mismatches.append(
                        f"storage_order/{metric}/{dt_key}/{field}: recomputed "
                        f"{got!r} != frozen {want!r}"
                    )
    return mismatches


def derived_limits(computed: Mapping[str, Any], *, metrics: Sequence[str]) -> Dict[str, float]:
    """V1F's rule, unchanged: worst discretization bound, then the order leg.

    The order leg is the bound at the **finest** timestep only, not a maximum
    across timesteps. That distinction is the whole point of calling this a
    re-derivation: taking a max would yield a different, larger number that V1F
    never froze, so the four limits would not reproduce.
    """
    finest_dt = float(computed["timesteps"][-1])
    finest_key = f"{finest_dt:.17g}"
    limits = {metric: 0.0 for metric in metrics}
    for cell in computed["discretization"].values():
        for metric, layers in cell.items():
            limits[metric] = max(
                limits[metric], layers["fine_vs_finest"]["two_se_bound"]
            )
    for metric, by_dt in computed["storage_order"].items():
        limits[metric] = max(limits[metric], by_dt[finest_key]["two_se_bound"])
    return limits


def extension_checks(
    computed: Mapping[str, Any], *, metric: str, limit: float
) -> Dict[str, Any]:
    """The two criteria that need no new threshold, applied to an extended metric."""
    dts = computed["timesteps"]
    coarse_dt, fine_dt, finest_dt = dts
    coarse_key = f"{coarse_dt:.17g}"
    finest_key = f"{finest_dt:.17g}"

    per_landscape: Dict[str, Any] = {}
    trend_pass = True
    for landscape, cell in computed["discretization"].items():
        layers = cell[metric]
        tolerance = (
            layers["coarse_vs_fine"]["two_se_bound"]
            + 2.0 * layers["fine_vs_finest"]["standard_error"]
        )
        passed = layers["fine_vs_finest"]["absolute_mean_difference"] <= tolerance
        trend_pass = trend_pass and passed
        per_landscape[landscape] = {
            "fine_vs_finest_two_se_bound": layers["fine_vs_finest"]["two_se_bound"],
            "fine_vs_finest_absolute_mean_difference": layers["fine_vs_finest"][
                "absolute_mean_difference"
            ],
            "trend_tolerance": tolerance,
            "trend_pass": passed,
        }

    order = computed["storage_order"][metric]
    order_trend_pass = order[finest_key]["absolute_mean_difference"] <= (
        order[coarse_key]["two_se_bound"]
        + 2.0 * order[finest_key]["standard_error"]
    )
    bounded_by_discretization = order[finest_key]["two_se_bound"] <= (
        limit + 2.0 * order[finest_key]["standard_error"]
    )

    return {
        "metric": metric,
        "numerical_resolution_limit": limit,
        "ceiling": None,
        "ceiling_pass": None,
        "ceiling_policy": CEILING_POLICY,
        "discretization": per_landscape,
        "discretization_trend_pass": trend_pass,
        "storage_order": {
            "finest_dt_two_se_bound": order[finest_key]["two_se_bound"],
            "coarse_dt_two_se_bound": order[coarse_key]["two_se_bound"],
            "trend_pass": order_trend_pass,
            "bounded_by_discretization": bounded_by_discretization,
        },
        "pass": bool(
            trend_pass
            and order_trend_pass
            and bounded_by_discretization
        ),
    }


def build_extension(
    config: Mapping[str, Any],
    rows: Sequence[Mapping[str, str]],
    frozen: Mapping[str, Any],
) -> Dict[str, Any]:
    """Assemble the extension payload, or raise if faithfulness cannot be shown."""
    extension_metrics = [str(name) for name in config["extension_metrics"]]
    overlap = sorted(set(extension_metrics) & set(CALIBRATION_METRICS))
    if overlap:
        raise ValueError(f"extension metrics already frozen by V1F: {overlap}")

    metrics = [*CALIBRATION_METRICS, *extension_metrics]
    computed = recompute_layer_bounds(
        rows, timesteps=config["timesteps"], metrics=metrics
    )
    mismatches = frozen_mismatches(computed, frozen)
    if mismatches:
        raise RuntimeError(
            "the recomputation does not reproduce V1F bit-for-bit "
            f"({len(mismatches)} field(s), first: {mismatches[0]}); an extension "
            "must re-derive the frozen limits, not restate them"
        )

    limits = derived_limits(computed, metrics=metrics)
    reproduced: Dict[str, Any] = {}
    for metric in CALIBRATION_METRICS:
        frozen_value = float(frozen["numerical_resolution_limits"][metric])
        recomputed = limits[metric]
        if recomputed != frozen_value:
            raise RuntimeError(
                f"{metric}: recomputed limit {recomputed!r} != frozen {frozen_value!r}"
            )
        reproduced[metric] = {
            "recomputed": recomputed,
            "frozen": frozen_value,
            "bit_equal": True,
        }

    extensions = {
        metric: extension_checks(computed, metric=metric, limit=limits[metric])
        for metric in extension_metrics
    }
    passed = all(bool(item["pass"]) for item in extensions.values())

    return {
        "experiment": EXPERIMENT,
        "status": "completed",
        "pass": passed,
        "scope": (
            "numerical calibration extension by re-analysis of retained V1F data; "
            "runs no simulation and supports no landscape-effect claim"
        ),
        "extends": {
            "experiment": SOURCE_EXPERIMENT,
            "sha256": str(config["source_calibration_sha256"]),
            "path": str(config["source_calibration"]),
        },
        "source_replicate_metrics": {
            "path": str(config["source_replicate_metrics"]),
            "sha256": str(config["source_replicate_metrics_sha256"]),
        },
        "faithfulness": {
            "field_mismatches": 0,
            "metrics_compared": list(CALIBRATION_METRICS),
            "reproduced_limits": reproduced,
            "method": (
                "recomputed with V1F's own _weak_bound from the retained "
                "replicate_metrics.csv; every recorded bound field compared exactly"
            ),
        },
        "numerical_resolution_limits": limits,
        "extension_metrics": extension_metrics,
        "extensions": extensions,
        "out_of_scope": OUT_OF_SCOPE,
        "threshold_policy": (
            "Resolution limits bound numerical error only. Scientific relevance "
            "thresholds for E2-C4 must be frozen separately before confirmatory runs."
        ),
        "pathwise_claim": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    _require_umi()

    config = load_json(project_path(args.config, must_exist=True))
    if config.get("experiment_id") != EXPERIMENT:
        raise ValueError(f"unexpected experiment_id: {config.get('experiment_id')!r}")

    calibration_path = project_path(config["source_calibration"], must_exist=True)
    if sha256_file(calibration_path) != config["source_calibration_sha256"]:
        raise RuntimeError("the source calibration does not match its declared sha256")
    metrics_path = project_path(config["source_replicate_metrics"], must_exist=True)
    if sha256_file(metrics_path) != config["source_replicate_metrics_sha256"]:
        raise RuntimeError("the retained table does not match its declared sha256")

    frozen = load_json(calibration_path)
    if frozen.get("experiment") != SOURCE_EXPERIMENT or frozen.get("pass") is not True:
        raise RuntimeError("the source calibration is not a passing V1F calibration")

    with metrics_path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    payload = build_extension(config, rows, frozen)
    # Only the conclusion artifact is written here. ``result.json`` is derived from
    # it by the promotion step, so that the summarised fields cannot drift from the
    # report they claim to summarise.
    write_json(Path(args.output_dir) / "numerical_calibration_extended.json", payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
