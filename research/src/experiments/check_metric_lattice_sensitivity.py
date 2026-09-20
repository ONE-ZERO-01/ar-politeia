"""Re-derive the measurement-lattice sensitivity of the spatial metrics.

The Cycle 4 primary spatial family contains statistics whose definition contains a
*lattice*: ``density_morans_i`` uses a four-neighbour (rook) weight matrix, and
``occupancy_entropy`` normalises by ``log(n_cells)``.  Both therefore change value
when the same particle configuration is binned onto a different lattice, with no
change in dynamics at all.  ``e3-cycle4-design.md`` §3 quotes the measured size of
that artefact; this script is what reproduces it.

The estimator is deliberately *not* the confirmatory one: it takes the final
snapshot of each completed run, not the tail-window mean.  It exists to quantify a
measurement artefact, and its output is a diagnostic, never a claim input.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import statistics
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Tuple

import numpy as np

from landscape_study import (
    density_grid,
    morans_i,
    occupancy_entropy,
    read_snapshot_csv,
)

# Metrics whose definition contains the measurement lattice.
LATTICE_SENSITIVE_METRICS = ("occupancy_entropy", "density_morans_i")

DEFAULT_RUN_ID_PATTERN = r"^seed-(?P<seed>\d+)--(?P<condition>.+)$"

DEFAULT_LATTICES = ((64, 64), (128, 128), (256, 256))

DEFAULT_BOUNDS = (0.0, 100.0, 0.0, 100.0)


def _metric_value(name: str, density: np.ndarray) -> float:
    if name == "occupancy_entropy":
        return occupancy_entropy(density)
    if name == "density_morans_i":
        return morans_i(density)
    raise ValueError(f"unknown lattice-sensitive metric: {name!r}")


def final_snapshot(run_dir: Path) -> Path:
    """Return the highest-numbered ``snap_*.csv`` in a completed run directory."""

    snapshots = sorted(
        run_dir.glob("snap_*.csv"),
        key=lambda path: int(path.stem.split("_")[1]),
    )
    if not snapshots:
        raise FileNotFoundError(f"no snapshots in {run_dir}")
    return snapshots[-1]


def discover_runs(
    runs_dir: Path, run_id_pattern: str = DEFAULT_RUN_ID_PATTERN
) -> Dict[Tuple[int, str], Path]:
    """Map ``(seed, condition)`` to a run directory, ignoring unmatched names."""

    pattern = re.compile(run_id_pattern)
    found: Dict[Tuple[int, str], Path] = {}
    for candidate in sorted(runs_dir.iterdir()):
        if not candidate.is_dir():
            continue
        match = pattern.match(candidate.name)
        if match is None:
            continue
        key = (int(match.group("seed")), str(match.group("condition")))
        if key in found:
            raise RuntimeError(f"duplicate run for {key}: {candidate}")
        found[key] = candidate
    return found


def lattice_sensitivity(
    runs_dir: Path,
    *,
    lattices: Sequence[Tuple[int, int]] = DEFAULT_LATTICES,
    bounds: Tuple[float, float, float, float] = DEFAULT_BOUNDS,
    metrics: Sequence[str] = LATTICE_SENSITIVE_METRICS,
    reference_condition: str = "clustered",
    baseline_condition: str = "shuffled",
    run_id_pattern: str = DEFAULT_RUN_ID_PATTERN,
) -> Dict[str, Any]:
    """Recompute paired effects on several lattices from fixed particle states."""

    runs = discover_runs(runs_dir, run_id_pattern)
    seeds = sorted({seed for seed, _ in runs})
    if not seeds:
        raise RuntimeError(f"no matching runs under {runs_dir}")

    conditions = (reference_condition, baseline_condition)
    per_lattice: List[Dict[str, Any]] = []
    for rows, cols in lattices:
        # Cache every snapshot once per lattice so the comparison holds the
        # particle configuration bitwise fixed and varies only the measurement.
        snapshots: Dict[Tuple[int, str], Dict[str, np.ndarray]] = {}
        for seed in seeds:
            for condition in conditions:
                key = (seed, condition)
                if key not in runs:
                    raise RuntimeError(f"missing run for {key}")
                snapshots[key] = read_snapshot_csv(final_snapshot(runs[key]))

        entry: Dict[str, Any] = {"lattice": [rows, cols], "metrics": {}}
        for metric in metrics:
            means: Dict[str, float] = {}
            for condition in conditions:
                values = [
                    _metric_value(
                        metric,
                        density_grid(
                            snapshots[(seed, condition)]["x"],
                            snapshots[(seed, condition)]["y"],
                            (rows, cols),
                            bounds,
                        ),
                    )
                    for seed in seeds
                ]
                means[condition] = float(statistics.fmean(values))
            entry["metrics"][metric] = {
                "condition_means": means,
                "paired_effect": means[reference_condition] - means[baseline_condition],
            }
        per_lattice.append(entry)

    transitions: Dict[str, List[Dict[str, Any]]] = {metric: [] for metric in metrics}
    for previous, current in zip(per_lattice, per_lattice[1:]):
        for metric in metrics:
            before = previous["metrics"][metric]["paired_effect"]
            after = current["metrics"][metric]["paired_effect"]
            transitions[metric].append(
                {
                    "from_lattice": previous["lattice"],
                    "to_lattice": current["lattice"],
                    "effect_before": before,
                    "effect_after": after,
                    "absolute_change": abs(after - before),
                }
            )

    return {
        "diagnostic": "measurement_lattice_sensitivity",
        "not_a_claim_input": True,
        "estimator": "final_snapshot",
        "runs_dir": str(runs_dir),
        "bounds": list(bounds),
        "seeds": seeds,
        "reference_condition": reference_condition,
        "baseline_condition": baseline_condition,
        "per_lattice": per_lattice,
        "adjacent_transitions": transitions,
    }


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs-dir", required=True, type=Path)
    parser.add_argument(
        "--lattices",
        default="64,128,256",
        help="comma-separated square lattice sizes, e.g. 64,128,256",
    )
    parser.add_argument(
        "--bounds",
        default="0,100,0,100",
        help="comma-separated xmin,xmax,ymin,ymax",
    )
    parser.add_argument("--run-id-pattern", default=DEFAULT_RUN_ID_PATTERN)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(list(argv) if argv is not None else None)

    lattices = tuple(
        (int(value), int(value)) for value in args.lattices.split(",") if value
    )
    if not lattices or any(size < 2 for size, _ in lattices):
        raise SystemExit("--lattices sizes must each be at least two")
    if len(lattices) < 2:
        raise SystemExit("--lattices needs at least two sizes to compare")
    bounds_values = tuple(float(value) for value in args.bounds.split(","))
    if len(bounds_values) != 4:
        raise SystemExit("--bounds must have four values")

    payload = lattice_sensitivity(
        args.runs_dir,
        lattices=lattices,
        bounds=bounds_values,  # type: ignore[arg-type]
        run_id_pattern=args.run_id_pattern,
    )
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
