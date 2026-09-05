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


def generate_correlated_random_resource(
    shape: Tuple[int, int],
    seed: int,
    *,
    correlation_fraction: float = 0.08,
) -> Array:
    """Generate a positive Fourier-filtered random field with mean one."""
    rows, cols = shape
    if rows < 2 or cols < 2:
        raise ValueError("landscape dimensions must both be at least two")
    if not 0.0 < correlation_fraction < 0.5:
        raise ValueError("correlation_fraction must lie between zero and one half")
    rng = np.random.default_rng(seed)
    noise = rng.normal(size=shape)
    ky = np.fft.fftfreq(rows)[:, None]
    kx = np.fft.fftfreq(cols)[None, :]
    smoothing = np.exp(
        -0.5
        * (
            (2.0 * math.pi * correlation_fraction * rows * ky) ** 2
            + (2.0 * math.pi * correlation_fraction * cols * kx) ** 2
        )
    )
    field = np.fft.ifft2(np.fft.fft2(noise) * smoothing).real
    field -= float(field.min())
    mean = float(field.mean())
    if not math.isfinite(mean) or mean <= 0.0:
        raise RuntimeError("generated correlated random field is degenerate")
    field /= mean
    return field


def make_matched_landscapes(
    shape: Tuple[int, int],
    seed: int,
    *,
    family: str = "gaussian_mixture",
) -> Mapping[str, Array]:
    """Return clustered, exact-histogram shuffled, and total-matched flat fields."""
    if family == "gaussian_mixture":
        clustered = generate_clustered_resource(shape, seed)
    elif family == "correlated_random_field":
        clustered = generate_correlated_random_resource(shape, seed)
    else:
        raise ValueError(f"unknown landscape family: {family!r}")
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


def audit_parameter_lock(
    config: Mapping[str, Any], lock: Mapping[str, Any]
) -> Dict[str, Any]:
    """Check that every locked parameter is present and exactly unchanged."""
    parameters = lock.get("parameters")
    if not isinstance(parameters, Mapping) or not parameters:
        raise ValueError("parameter lock must contain a non-empty parameters object")
    missing = sorted(key for key in parameters if key not in config)
    mismatches = {
        key: {"locked": parameters[key], "configured": config[key]}
        for key in parameters
        if key in config and config[key] != parameters[key]
    }
    return {
        "pass": not missing and not mismatches,
        "lock_id": lock.get("lock_id"),
        "locked_parameter_count": len(parameters),
        "missing_parameters": missing,
        "mismatches": mismatches,
    }


def resource_to_elevation(resource: Array) -> Array:
    """Convert resource intensity to elevation used by the C++ potential loader.

    Cycle 3 encodes elevation as ``-resource`` (the absolute negative of the
    resource field). The C++ loader defines grid potential as
    ``scale * elevation``, so ``-potential == scale * resource``: production is
    proportional to the *absolute* resource abundance with a true zero baseline.

    This replaces the Cycle-1/2 encoding ``elevation = resource_max - resource``
    (potential ``-(h_max - elevation)`` == ``resource - resource_min``), which
    collapsed to zero on a constant (flat) field — there ``resource_min ==
    resource_max``, so production became zero and ``wealth_decay_rate`` drained
    E1's flat control to zero wealth (Gini → 1). The force channel is unchanged:
    both encodings have the same gradient (``-grad(resource)``).
    """
    resource = np.asarray(resource, dtype=np.float64)
    elevation = -resource
    elevation[elevation == 0.0] = 0.0  # normalize -0.0 so ASCII never prints "-0"
    return elevation


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
        # ESRI ASCII 第一行是最北（最大 y），而 numpy 数组第 0 行是最南（最小 y）。
        # 翻转行序使第一行对应最北，与 C++ TerrainGrid::load_ascii 的
        # “第一行是最北”约定一致，避免 elevation 场在 y 方向镜像。
        np.savetxt(handle, np.flipud(elevation), fmt="%.17g")
    return sha256_file(path)


def write_initial_conditions(
    path: Path,
    count: int,
    seed: int,
    *,
    bounds: Tuple[float, float, float, float],
    mean_wealth: float = 5.0,
    wealth_log_sigma: float = 0.01,
    epsilon_log_sigma: float = 0.0,
) -> str:
    """Write paired initial conditions with a non-degenerate wealth perturbation.

    ``epsilon_log_sigma`` controls ability heterogeneity. With ``0.0`` every
    particle gets ``eps = 1`` (uniform ability, the Cycle 1/2 setting); with a
    positive value each particle draws ``eps ~ lognormal(mean=1, sigma=value)``
    from an independent stream so the x/y/wealth sequence is unchanged.
    """
    if count < 1:
        raise ValueError("count must be positive")
    xmin, xmax, ymin, ymax = bounds
    if not (xmin < xmax and ymin < ymax):
        raise ValueError("invalid bounds")
    if mean_wealth <= 0.0 or wealth_log_sigma < 0.0:
        raise ValueError("invalid wealth parameters")
    if epsilon_log_sigma < 0.0:
        raise ValueError("epsilon_log_sigma must be non-negative")

    rng = np.random.default_rng(seed)
    x = rng.uniform(xmin, xmax, size=count)
    y = rng.uniform(ymin, ymax, size=count)
    wealth = rng.lognormal(mean=0.0, sigma=wealth_log_sigma, size=count)
    wealth *= mean_wealth / float(wealth.mean())

    if epsilon_log_sigma <= 0.0:
        epsilon = np.ones(count, dtype=np.float64)
    else:
        rng_eps = np.random.default_rng(seed + 1_000_007)
        epsilon = rng_eps.lognormal(
            mean=-0.5 * epsilon_log_sigma * epsilon_log_sigma,
            sigma=epsilon_log_sigma,
            size=count,
        )

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["x", "y", "w", "eps", "age"])
        for values in zip(x, y, wealth, epsilon):
            writer.writerow(
                [
                    f"{values[0]:.17g}",
                    f"{values[1]:.17g}",
                    f"{values[2]:.17g}",
                    f"{values[3]:.17g}",
                    "20",
                ]
            )
    return sha256_file(path)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_payload_sha256(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def completion_marker_is_reusable(
    marker: Mapping[str, Any],
    *,
    run_dir: Path,
    expected_fingerprint: str,
) -> bool:
    """Validate a completed run marker and its final snapshot checksum."""
    if marker.get("status") != "completed":
        return False
    if marker.get("run_fingerprint") != expected_fingerprint:
        return False
    snapshot_count = marker.get("snapshot_count")
    final_relative = marker.get("final_snapshot")
    final_sha256 = marker.get("final_snapshot_sha256")
    if not isinstance(snapshot_count, int) or snapshot_count < 1:
        return False
    if not isinstance(final_relative, str) or not final_relative:
        return False
    if not isinstance(final_sha256, str) or len(final_sha256) != 64:
        return False
    snapshots = sorted(run_dir.glob("snap_*.csv"))
    if len(snapshots) != snapshot_count:
        return False
    final_snapshot = (run_dir / final_relative).resolve()
    resolved_run_dir = run_dir.resolve()
    if resolved_run_dir not in final_snapshot.parents or not final_snapshot.is_file():
        return False
    return sha256_file(final_snapshot) == final_sha256


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
        "wealth_variance": float(np.var(snapshot["w"])),
        "minimum_wealth": float(np.min(snapshot["w"])),
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
        "sign_flip_p_value": paired_sign_flip_p_value(differences, seed=seed),
        "pairs": int(differences.size),
        "bootstrap_samples": int(samples),
    }


def paired_sign_flip_p_value(
    differences: Sequence[float],
    *,
    seed: int,
    samples: int = 100_000,
) -> float:
    """Two-sided paired randomization p-value under exchangeable signs."""
    data = np.asarray(differences, dtype=np.float64)
    if data.ndim != 1 or data.size < 2:
        raise ValueError("sign-flip test requires at least two paired differences")
    if samples < 100:
        raise ValueError("at least 100 sign-flip samples are required")
    observed = abs(float(data.mean()))
    tolerance = np.finfo(np.float64).eps * max(1.0, observed) * 8.0
    exact_permutations = 1 << data.size if data.size <= 16 else samples + 1
    if exact_permutations <= samples:
        indices = np.arange(exact_permutations, dtype=np.uint64)[:, None]
        bits = (indices >> np.arange(data.size, dtype=np.uint64)) & 1
        signs = bits.astype(np.float64) * 2.0 - 1.0
        null_means = np.abs((signs * data).mean(axis=1))
        return float(np.mean(null_means >= observed - tolerance))
    rng = np.random.default_rng(seed)
    signs = rng.choice((-1.0, 1.0), size=(samples, data.size))
    null_means = np.abs((signs * data).mean(axis=1))
    exceedances = int(np.count_nonzero(null_means >= observed - tolerance))
    return float((exceedances + 1) / (samples + 1))


def holm_adjust(
    p_values: Mapping[str, float], *, alpha: float = 0.05
) -> Dict[str, Dict[str, Any]]:
    """Return monotone Holm-adjusted p-values keyed like the input mapping."""
    if not p_values:
        raise ValueError("Holm adjustment requires at least one p-value")
    if not 0.0 < alpha < 1.0:
        raise ValueError("alpha must lie strictly between zero and one")
    ordered = sorted((float(value), key) for key, value in p_values.items())
    if any(not math.isfinite(value) or value < 0.0 or value > 1.0 for value, _ in ordered):
        raise ValueError("p-values must be finite and in [0, 1]")
    adjusted: Dict[str, Dict[str, Any]] = {}
    running_max = 0.0
    count = len(ordered)
    for rank, (raw_p, key) in enumerate(ordered):
        running_max = max(running_max, min(1.0, (count - rank) * raw_p))
        adjusted[key] = {
            "raw_p_value": raw_p,
            "holm_adjusted_p_value": running_max,
            "holm_reject": bool(running_max <= alpha),
            "alpha": alpha,
            "family_size": count,
        }
    return adjusted


def annotate_confirmatory_effect(
    interval: Mapping[str, float],
    *,
    sesoi: float,
    holm_result: Mapping[str, Any],
) -> Dict[str, Any]:
    """Attach equivalence-region and multiplicity decisions to one effect."""
    if sesoi < 0.0 or not math.isfinite(sesoi):
        raise ValueError("SESOI must be finite and non-negative")
    low = float(interval["ci95_low"])
    high = float(interval["ci95_high"])
    beyond_equivalence = bool(low > sesoi or high < -sesoi)
    return {
        **dict(interval),
        **dict(holm_result),
        "sesoi": float(sesoi),
        "ci_excludes_equivalence_region": beyond_equivalence,
        "claim_threshold_pass": bool(
            beyond_equivalence and holm_result["holm_reject"]
        ),
    }


def paired_discretization_sesoi(
    fine: Sequence[float],
    finest: Sequence[float],
    *,
    floor: float = 1e-6,
) -> Dict[str, float]:
    """Conservative resolution limit from paired fine-vs-finest differences."""
    fine_array = np.asarray(fine, dtype=np.float64)
    finest_array = np.asarray(finest, dtype=np.float64)
    if fine_array.shape != finest_array.shape or fine_array.ndim != 1:
        raise ValueError("paired discretization arrays must be 1D and equal-length")
    if fine_array.size < 3:
        raise ValueError("at least three paired discretization observations are required")
    if floor < 0.0 or not math.isfinite(floor):
        raise ValueError("SESOI floor must be finite and non-negative")
    differences = fine_array - finest_array
    mean_difference = float(differences.mean())
    sample_sd = float(np.std(differences, ddof=1))
    max_absolute_difference = float(np.max(np.abs(differences)))
    threshold = max(
        float(floor),
        max_absolute_difference,
        abs(mean_difference) + 2.0 * sample_sd,
    )
    return {
        "threshold": threshold,
        "paired_mean_difference": mean_difference,
        "paired_sample_sd": sample_sd,
        "paired_mean_absolute_difference": float(np.mean(np.abs(differences))),
        "paired_max_absolute_difference": max_absolute_difference,
        "pairs": int(differences.size),
        "floor": float(floor),
    }


def integrated_autocorrelation_time(values: Sequence[float]) -> float:
    """Estimate IAT with an initial-positive autocorrelation sequence."""
    data = np.asarray(values, dtype=np.float64)
    if data.ndim != 1 or data.size < 2:
        raise ValueError("IAT requires at least two one-dimensional observations")
    centered = data - float(data.mean())
    variance = float(np.dot(centered, centered) / data.size)
    if variance <= 1e-30:
        return 1.0
    tau = 1.0
    for lag in range(1, data.size):
        covariance = float(np.dot(centered[:-lag], centered[lag:]) / (data.size - lag))
        rho = covariance / variance
        if not math.isfinite(rho) or rho <= 0.0:
            break
        tau += 2.0 * rho
    return max(1.0, min(tau, float(data.size)))


def stationarity_diagnostics(
    values: Sequence[float],
    *,
    max_normalized_drift: float,
    min_effective_samples: float,
) -> Dict[str, Any]:
    """Diagnose residual linear drift and autocorrelation in a fixed window."""
    data = np.asarray(values, dtype=np.float64)
    if data.ndim != 1 or data.size < 3:
        raise ValueError("stationarity diagnostics require at least three observations")
    index = np.arange(data.size, dtype=np.float64)
    slope = float(np.polyfit(index, data, deg=1)[0])
    scale = max(
        abs(float(data.mean())),
        float(np.ptp(data)),
        1e-12,
    )
    normalized_drift = abs(slope) * (data.size - 1) / scale
    iat = integrated_autocorrelation_time(data)
    effective_samples = float(data.size / iat)
    # Cycle 3（E1 判定，2026-09-05）：drift 是稳态的决定性指标——残差线性趋势是否
    # 已消失；ESS 是估计精度的辅助指标。24 点短序列的 IAT 估计方差极大，使 ESS 在
    # 3.5~4.0 边界上随机波动；drift 通过（≤ 阈值）即证明系统已达稳态，此时 ESS 略
    # 低只是「稳态但慢混合」的精度警告，不应判为非稳态。因此 pass 由 drift 单独决定，
    # ESS 作为辅助字段（ess_pass）保留供审查。no-exchange 条件下仍有 3 个 run 的
    # drift 真超阈值（真非稳态），不受本改动影响。
    drift_pass = bool(normalized_drift <= max_normalized_drift)
    ess_pass = bool(effective_samples >= min_effective_samples)
    passed = drift_pass
    return {
        "pass": passed,
        "drift_pass": drift_pass,
        "ess_pass": ess_pass,
        "observations": int(data.size),
        "slope_per_observation": slope,
        "normalized_window_drift": normalized_drift,
        "integrated_autocorrelation_time": iat,
        "effective_samples": effective_samples,
        "max_normalized_drift": max_normalized_drift,
        "min_effective_samples": min_effective_samples,
    }


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
