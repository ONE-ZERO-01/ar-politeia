"""Deterministic input generation and metrics for AR-Politeia Cycle 1.

This module contains no experiment launcher.  It is safe to unit-test locally;
authoritative numerical simulations are run only on ``umi`` by
``run_landscape_study.py`` once job manifests pass preflight.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Sequence, Tuple

import numpy as np


Array = np.ndarray


def generate_clustered_resource(
    shape: Tuple[int, int],
    seed: int,
    *,
    centers: int = 5,
    sigma_fraction: Tuple[float, float] = (0.06, 0.18),
) -> Array:
    """Generate a positive clustered resource field with mean exactly one."""
    rows, cols = shape
    if rows < 2 or cols < 2:
        raise ValueError("landscape dimensions must both be at least two")
    if centers < 1:
        raise ValueError("centers must be positive")

    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0.0:1.0:complex(rows), 0.0:1.0:complex(cols)]
    field = np.zeros(shape, dtype=np.float64)
    sigma_low, sigma_high = sigma_fraction
    for _ in range(centers):
        center_x, center_y = rng.uniform(0.1, 0.9, size=2)
        sigma_x, sigma_y = rng.uniform(sigma_low, sigma_high, size=2)
        amplitude = float(rng.lognormal(mean=0.0, sigma=0.35))
        field += amplitude * np.exp(
            -0.5
            * (
                ((xx - center_x) / sigma_x) ** 2
                + ((yy - center_y) / sigma_y) ** 2
            )
        )

    field -= float(field.min())
    mean = float(field.mean())
    if not math.isfinite(mean) or mean <= 0.0:
        raise RuntimeError("generated resource field is degenerate")
    field /= mean
    return field


def make_matched_landscapes(
    shape: Tuple[int, int], seed: int
) -> Mapping[str, Array]:
    """Return clustered, exact-histogram shuffled, and total-matched flat fields."""
    clustered = generate_clustered_resource(shape, seed)
    rng = np.random.default_rng(seed + 1_000_003)
    shuffled = clustered.ravel().copy()
    rng.shuffle(shuffled)
    shuffled = shuffled.reshape(shape)
    flat = np.full(shape, float(clustered.mean()), dtype=np.float64)
    return {"clustered": clustered, "shuffled": shuffled, "flat": flat}


def audit_matched_landscapes(clustered: Array, shuffled: Array) -> Dict[str, Any]:
    """Machine-check the exact inputs required by the confirmatory comparison."""
    same_shape = clustered.shape == shuffled.shape
    exact_histogram = same_shape and np.array_equal(
        np.sort(clustered, axis=None), np.sort(shuffled, axis=None)
    )
    total_clustered = float(np.sum(clustered, dtype=np.float64))
    total_shuffled = float(np.sum(shuffled, dtype=np.float64))
    total_difference = abs(total_clustered - total_shuffled)
    finite_nonnegative = bool(
        np.isfinite(clustered).all()
        and np.isfinite(shuffled).all()
        and np.min(clustered) >= 0.0
        and np.min(shuffled) >= 0.0
    )
    passed = bool(
        same_shape
        and exact_histogram
        and total_difference <= 1e-12 * max(1.0, abs(total_clustered))
        and finite_nonnegative
    )
    return {
        "pass": passed,
        "same_shape": same_shape,
        "exact_histogram": exact_histogram,
        "finite_nonnegative": finite_nonnegative,
        "total_clustered": total_clustered,
        "total_shuffled": total_shuffled,
        "total_absolute_difference": total_difference,
        "shape": list(clustered.shape),
    }


def resource_to_elevation(resource: Array) -> Array:
    """Convert resource intensity to elevation used by the C++ potential loader.

    The simulator defines grid potential as ``-(h_max - elevation)``.  With
    ``elevation = resource_max - resource``, ``-potential`` therefore equals
    ``resource - resource_min``.  Cycle 1 fields are generated with min zero.
    """
    resource = np.asarray(resource, dtype=np.float64)
    shifted = resource - float(np.min(resource))
    return float(np.max(shifted)) - shifted


def write_esri_ascii(
    path: Path,
    resource: Array,
    *,
    xllcorner: float = 0.0,
    yllcorner: float = 0.0,
    cellsize: float = 1.0,
) -> str:
    """Write a resource field as an ESRI ASCII elevation grid; return SHA-256."""
    if cellsize <= 0.0:
        raise ValueError("cellsize must be positive")
    elevation = resource_to_elevation(resource)
    rows, cols = elevation.shape
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        handle.write(f"ncols {cols}\n")
        handle.write(f"nrows {rows}\n")
        handle.write(f"xllcorner {xllcorner:.17g}\n")
        handle.write(f"yllcorner {yllcorner:.17g}\n")
        handle.write(f"cellsize {cellsize:.17g}\n")
        handle.write("NODATA_value -9999\n")
        np.savetxt(handle, elevation, fmt="%.17g")
    return sha256_file(path)


def write_initial_conditions(
    path: Path,
    count: int,
    seed: int,
    *,
    bounds: Tuple[float, float, float, float],
    mean_wealth: float = 5.0,
    wealth_log_sigma: float = 0.01,
) -> str:
    """Write paired initial conditions with a non-degenerate wealth perturbation."""
    if count < 1:
        raise ValueError("count must be positive")
    xmin, xmax, ymin, ymax = bounds
    if not (xmin < xmax and ymin < ymax):
        raise ValueError("invalid bounds")
    if mean_wealth <= 0.0 or wealth_log_sigma < 0.0:
        raise ValueError("invalid wealth parameters")

    rng = np.random.default_rng(seed)
    x = rng.uniform(xmin, xmax, size=count)
    y = rng.uniform(ymin, ymax, size=count)
    wealth = rng.lognormal(mean=0.0, sigma=wealth_log_sigma, size=count)
    wealth *= mean_wealth / float(wealth.mean())

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["x", "y", "w", "eps", "age"])
        for values in zip(x, y, wealth):
            writer.writerow(
                [f"{values[0]:.17g}", f"{values[1]:.17g}", f"{values[2]:.17g}", "1", "20"]
            )
    return sha256_file(path)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def density_grid(
    x: Array,
    y: Array,
    shape: Tuple[int, int],
    bounds: Tuple[float, float, float, float],
) -> Array:
    """Bin particle positions onto a row-major grid matching a resource field."""
    rows, cols = shape
    xmin, xmax, ymin, ymax = bounds
    histogram, _, _ = np.histogram2d(
        y,
        x,
        bins=(rows, cols),
        range=((ymin, ymax), (xmin, xmax)),
    )
    return histogram.astype(np.float64, copy=False)


def _average_ranks(values: Array) -> Array:
    flat = np.asarray(values, dtype=np.float64).ravel()
    order = np.argsort(flat, kind="mergesort")
    ranks = np.empty(flat.size, dtype=np.float64)
    start = 0
    while start < flat.size:
        end = start + 1
        while end < flat.size and flat[order[end]] == flat[order[start]]:
            end += 1
        ranks[order[start:end]] = 0.5 * (start + end - 1) + 1.0
        start = end
    return ranks


def spearman_correlation(lhs: Array, rhs: Array) -> float:
    """Spearman correlation with average ranks and defined zero for constants."""
    left = _average_ranks(lhs)
    right = _average_ranks(rhs)
    left -= float(left.mean())
    right -= float(right.mean())
    denominator = math.sqrt(float(np.dot(left, left) * np.dot(right, right)))
    if denominator == 0.0:
        return 0.0
    return float(np.dot(left, right) / denominator)


def morans_i(field: Array) -> float:
    """Global Moran's I using a symmetric four-neighbour lattice."""
    values = np.asarray(field, dtype=np.float64)
    centered = values - float(values.mean())
    denominator = float(np.sum(centered * centered))
    if denominator == 0.0:
        return 0.0

    horizontal = float(np.sum(centered[:, :-1] * centered[:, 1:]))
    vertical = float(np.sum(centered[:-1, :] * centered[1:, :]))
    pair_sum = 2.0 * (horizontal + vertical)
    rows, cols = values.shape
    weight_sum = 2.0 * (rows * (cols - 1) + (rows - 1) * cols)
    return float(values.size / weight_sum * pair_sum / denominator)


def occupancy_entropy(density: Array) -> float:
    """Shannon entropy of occupied mass normalized to [0, 1]."""
    values = np.asarray(density, dtype=np.float64)
    total = float(values.sum())
    if total <= 0.0 or values.size <= 1:
        return 0.0
    probabilities = values.ravel() / total
    positive = probabilities[probabilities > 0.0]
    entropy = -float(np.sum(positive * np.log(positive)))
    return entropy / math.log(values.size)


def gini(values: Array) -> float:
    data = np.maximum(np.asarray(values, dtype=np.float64).ravel(), 0.0)
    if data.size <= 1 or float(data.sum()) == 0.0:
        return 0.0
    ordered = np.sort(data)
    indices = np.arange(1, ordered.size + 1, dtype=np.float64)
    return float(
        2.0 * np.dot(indices, ordered) / (ordered.size * ordered.sum())
        - (ordered.size + 1.0) / ordered.size
    )


def read_snapshot_csv(path: Path) -> Dict[str, Array]:
    table = np.genfromtxt(path, delimiter=",", names=True, dtype=None, encoding=None)
    if table.size == 0:
        raise ValueError(f"empty snapshot: {path}")
    table = np.atleast_1d(table)
    required = {"x", "y", "w"}
    names = set(table.dtype.names or ())
    if not required <= names:
        raise ValueError(f"snapshot lacks required columns {sorted(required - names)}")
    return {name: np.asarray(table[name], dtype=np.float64) for name in required}


def snapshot_metrics(
    snapshot: Mapping[str, Array],
    resource: Array,
    bounds: Tuple[float, float, float, float],
) -> Dict[str, float]:
    density = density_grid(snapshot["x"], snapshot["y"], resource.shape, bounds)
    return {
        "resource_density_spearman_rho": spearman_correlation(resource, density),
        "density_morans_i": morans_i(density),
        "occupancy_entropy": occupancy_entropy(density),
        "wealth_gini": gini(snapshot["w"]),
        "particle_count": float(np.sum(density)),
    }


def paired_bootstrap_mean_difference(
    treatment: Sequence[float],
    control: Sequence[float],
    *,
    seed: int,
    samples: int = 10_000,
) -> Dict[str, float]:
    """Paired bootstrap interval for a mean treatment-control effect."""
    treatment_array = np.asarray(treatment, dtype=np.float64)
    control_array = np.asarray(control, dtype=np.float64)
    if treatment_array.shape != control_array.shape or treatment_array.ndim != 1:
        raise ValueError("paired arrays must be one-dimensional with equal shape")
    if treatment_array.size < 2:
        raise ValueError("at least two paired observations are required")
    if samples < 100:
        raise ValueError("at least 100 bootstrap samples are required")
    differences = treatment_array - control_array
    rng = np.random.default_rng(seed)
    indices = rng.integers(0, differences.size, size=(samples, differences.size))
    means = differences[indices].mean(axis=1)
    low, high = np.quantile(means, [0.025, 0.975])
    return {
        "mean_difference": float(differences.mean()),
        "ci95_low": float(low),
        "ci95_high": float(high),
        "pairs": int(differences.size),
        "bootstrap_samples": int(samples),
    }


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
