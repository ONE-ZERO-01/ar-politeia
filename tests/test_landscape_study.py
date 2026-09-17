from __future__ import annotations

import importlib.util
import math
from pathlib import Path

import numpy as np
import pytest


MODULE_PATH = (
    Path(__file__).parents[1]
    / "research"
    / "src"
    / "experiments"
    / "landscape_study.py"
)
SPEC = importlib.util.spec_from_file_location("landscape_study", MODULE_PATH)
assert SPEC and SPEC.loader
landscape_study = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(landscape_study)


def test_matched_landscapes_preserve_exact_histogram_and_total():
    fields = landscape_study.make_matched_landscapes((24, 32), 123)
    audit = landscape_study.audit_matched_landscapes(
        fields["clustered"], fields["shuffled"]
    )
    assert audit["pass"] is True
    assert audit["accessible_area_match"] is True
    assert audit["accessible_cells_clustered"] == audit["accessible_cells_shuffled"]
    assert audit["positive_resource_support_match"] is True
    assert np.array_equal(
        np.sort(fields["clustered"], axis=None),
        np.sort(fields["shuffled"], axis=None),
    )
    assert fields["clustered"].mean() == pytest.approx(1.0)
    assert fields["flat"].sum() == pytest.approx(fields["clustered"].sum())
    assert not np.array_equal(fields["clustered"], fields["shuffled"])


def test_correlated_random_holdout_is_deterministic_and_matched():
    first = landscape_study.make_matched_landscapes(
        (32, 40), 456, family="correlated_random_field"
    )
    second = landscape_study.make_matched_landscapes(
        (32, 40), 456, family="correlated_random_field"
    )
    assert np.array_equal(first["clustered"], second["clustered"])
    assert landscape_study.audit_matched_landscapes(
        first["clustered"], first["shuffled"]
    )["pass"] is True
    assert first["clustered"].mean() == pytest.approx(1.0)
    gaussian = landscape_study.make_matched_landscapes((32, 40), 456)
    assert not np.array_equal(first["clustered"], gaussian["clustered"])


def test_smooth_resource_is_positive_nonflat_and_normalized():
    field = landscape_study.generate_smooth_resource((24, 32))
    assert np.all(np.isfinite(field))
    assert float(field.min()) > 0.0
    assert float(field.std()) > 0.0
    assert float(field.mean()) == pytest.approx(1.0)


def test_resource_to_elevation_reconstructs_resource_contrast():
    resource = np.array([[0.0, 1.0], [2.0, 4.0]])
    elevation = landscape_study.resource_to_elevation(resource)
    # Cycle 3: elevation = -resource, so the absolute abundance is -elevation.
    reconstructed = -elevation
    assert np.array_equal(reconstructed, resource)
    assert np.array_equal(elevation, np.array([[0.0, -1.0], [-2.0, -4.0]]))


def test_parameter_lock_audit_detects_missing_and_changed_values():
    lock = {
        "lock_id": "cycle1",
        "parameters": {"dt": 0.01, "temperature": 0.5},
    }
    passed = landscape_study.audit_parameter_lock(
        {"dt": 0.01, "temperature": 0.5}, lock
    )
    assert passed["pass"] is True
    failed = landscape_study.audit_parameter_lock(
        {"dt": 0.02}, lock
    )
    assert failed["pass"] is False
    assert failed["missing_parameters"] == ["temperature"]
    assert failed["mismatches"] == {
        "dt": {"locked": 0.01, "configured": 0.02}
    }


def test_write_esri_ascii_and_initial_conditions(tmp_path):
    resource = np.array([[0.0, 1.0], [2.0, 4.0]])
    grid_path = tmp_path / "grid.asc"
    grid_digest = landscape_study.write_esri_ascii(grid_path, resource)
    lines = grid_path.read_text(encoding="utf-8").splitlines()
    assert lines[:2] == ["ncols 2", "nrows 2"]
    assert len(grid_digest) == 64

    # ESRI ASCII 第一数据行是最北（最大 y），而 resource 第 0 行是最南。
    # elevation = -resource = [[0, -1], [-2, -4]]，所以翻转后第一数据行
    # 应为 [-2, -4]（resource 最北行 [2, 4] 的负值）。这保证 C++ load_ascii
    # 不会在 y 方向镜像，且绝对丰度（-elevation == resource）被保留。
    assert lines[6].split() == ["-2", "-4"]
    assert lines[7].split() == ["0", "-1"]

    ic_path = tmp_path / "initial.csv"
    ic_digest = landscape_study.write_initial_conditions(
        ic_path, 100, 321, bounds=(0.0, 10.0, 0.0, 10.0)
    )
    table = np.genfromtxt(ic_path, delimiter=",", names=True)
    assert table.size == 100
    assert float(np.mean(table["w"])) == pytest.approx(5.0)
    assert float(np.std(table["w"])) > 0.0
    assert len(ic_digest) == 64


def test_explicit_phase_state_permutation_changes_only_row_order(tmp_path):
    canonical_path = tmp_path / "canonical.csv"
    permuted_path = tmp_path / "permuted.csv"
    kwargs = {
        "count": 50,
        "seed": 321,
        "bounds": (0.0, 10.0, 0.0, 10.0),
        "explicit_phase_state": True,
        "momentum_temperature": 0.5,
    }
    landscape_study.write_initial_conditions(
        canonical_path, row_order="canonical", **kwargs
    )
    landscape_study.write_initial_conditions(
        permuted_path, row_order="permuted", **kwargs
    )
    canonical = np.genfromtxt(canonical_path, delimiter=",", names=True)
    permuted = np.genfromtxt(permuted_path, delimiter=",", names=True)
    assert set(canonical.dtype.names or ()) == {
        "gid", "x", "y", "px", "py", "w", "eps", "age"
    }
    assert not np.array_equal(canonical["gid"], permuted["gid"])
    by_gid_canonical = np.sort(canonical, order="gid")
    by_gid_permuted = np.sort(permuted, order="gid")
    for name in canonical.dtype.names or ():
        assert np.array_equal(by_gid_canonical[name], by_gid_permuted[name])


def test_completion_marker_requires_matching_fingerprint_and_snapshot(tmp_path):
    snapshot = tmp_path / "snap_00000010.csv"
    snapshot.write_text("x,y,w\n0,0,1\n", encoding="utf-8")
    fingerprint = landscape_study.canonical_payload_sha256({"run": "a"})
    marker = {
        "status": "completed",
        "run_fingerprint": fingerprint,
        "snapshot_count": 1,
        "final_snapshot": snapshot.name,
        "final_snapshot_sha256": landscape_study.sha256_file(snapshot),
    }
    assert landscape_study.completion_marker_is_reusable(
        marker, run_dir=tmp_path, expected_fingerprint=fingerprint
    ) is True
    assert landscape_study.completion_marker_is_reusable(
        marker, run_dir=tmp_path, expected_fingerprint="0" * 64
    ) is False
    snapshot.write_text("x,y,w\n0,0,2\n", encoding="utf-8")
    assert landscape_study.completion_marker_is_reusable(
        marker, run_dir=tmp_path, expected_fingerprint=fingerprint
    ) is False


def test_spatial_and_wealth_metrics_have_expected_limits():
    resource = np.array([[0.0, 1.0], [2.0, 3.0]])
    assert landscape_study.spearman_correlation(resource, resource) == pytest.approx(1.0)
    assert landscape_study.spearman_correlation(resource, -resource) == pytest.approx(-1.0)
    # S04: a constant field has no defined Moran's I → NaN, not a fallback 0.
    assert math.isnan(landscape_study.morans_i(np.ones((3, 3))))
    assert landscape_study.occupancy_entropy(np.ones((2, 2))) == pytest.approx(1.0)
    assert landscape_study.occupancy_entropy(np.array([[4.0, 0.0], [0.0, 0.0]])) == 0.0
    assert landscape_study.gini(np.array([1.0, 1.0])) == pytest.approx(0.0)
    assert landscape_study.gini(np.array([0.0, 2.0])) == pytest.approx(0.5)


def test_degenerate_correlation_is_nan_not_zero():
    # S04: constant-vector correlation must be marked undefined (NaN), not a
    # fallback zero that would masquerade as a zero discretization error.
    constant = np.full((4, 4), 2.0)
    assert math.isnan(landscape_study.spearman_correlation(constant, constant))
    density = np.array([[1.0, 1.0], [1.0, 1.0]])
    assert math.isnan(landscape_study.morans_i(density))


def test_snapshot_metrics_and_paired_bootstrap():
    resource = np.array([[0.0, 1.0], [2.0, 3.0]])
    snapshot = {
        "x": np.array([0.25, 1.25, 0.25, 1.25, 1.35, 1.45]),
        "y": np.array([0.25, 0.25, 1.25, 1.25, 1.35, 1.45]),
        "w": np.array([1.0, 1.0, 1.0, 2.0, 2.0, 3.0]),
    }
    metrics = landscape_study.snapshot_metrics(
        snapshot, resource, bounds=(0.0, 2.0, 0.0, 2.0)
    )
    assert metrics["particle_count"] == 6.0
    assert metrics["resource_density_spearman_rho"] > 0.0
    assert metrics["minimum_wealth"] == 1.0
    assert metrics["wealth_variance"] > 0.0
    assert metrics["zero_wealth_fraction"] == 0.0
    # S12: the equilibrium level is reported so w/w_ref stays auditable.
    assert metrics["mean_wealth"] == pytest.approx(np.mean([1.0, 1.0, 1.0, 2.0, 2.0, 3.0]))
    interval = landscape_study.paired_bootstrap_mean_difference(
        [2.0, 3.0, 4.0], [1.0, 2.0, 3.0], seed=7, samples=1000
    )
    assert interval["mean_difference"] == pytest.approx(1.0)
    assert interval["ci95_low"] == pytest.approx(1.0)
    assert interval["ci95_high"] == pytest.approx(1.0)
    assert interval["sign_flip_p_value"] == pytest.approx(0.25)


def test_holm_adjust_is_monotone_and_preserves_keys():
    adjusted = landscape_study.holm_adjust(
        {"a": 0.01, "b": 0.03, "c": 0.2}, alpha=0.05
    )
    assert set(adjusted) == {"a", "b", "c"}
    assert adjusted["a"]["holm_adjusted_p_value"] == pytest.approx(0.03)
    assert adjusted["b"]["holm_adjusted_p_value"] == pytest.approx(0.06)
    assert adjusted["c"]["holm_adjusted_p_value"] == pytest.approx(0.2)
    assert adjusted["a"]["holm_reject"] is True
    assert adjusted["b"]["holm_reject"] is False


def test_confirmatory_effect_requires_holm_and_sesoi():
    interval = {
        "mean_difference": 0.4,
        "ci95_low": 0.2,
        "ci95_high": 0.6,
    }
    accepted = landscape_study.annotate_confirmatory_effect(
        interval,
        sesoi=0.1,
        holm_result={"holm_reject": True, "holm_adjusted_p_value": 0.01},
    )
    assert accepted["claim_threshold_pass"] is True
    inside_sesoi = landscape_study.annotate_confirmatory_effect(
        interval,
        sesoi=0.3,
        holm_result={"holm_reject": True, "holm_adjusted_p_value": 0.01},
    )
    assert inside_sesoi["claim_threshold_pass"] is False


def test_paired_discretization_sesoi_uses_paired_error_envelope():
    diagnostic = landscape_study.paired_discretization_sesoi(
        [0.12, 0.21, 0.29, 0.42],
        [0.10, 0.20, 0.30, 0.40],
    )
    assert diagnostic["pairs"] == 4
    assert diagnostic["paired_max_absolute_difference"] == pytest.approx(0.02)
    assert diagnostic["threshold"] >= diagnostic["paired_max_absolute_difference"]
    assert diagnostic["threshold"] >= abs(diagnostic["paired_mean_difference"])


def test_stationarity_diagnostics_distinguish_flat_and_drifting_windows():
    flat = landscape_study.stationarity_diagnostics(
        [2.0] * 12, max_normalized_drift=0.1, min_effective_samples=3.0
    )
    assert flat["pass"] is True
    assert flat["integrated_autocorrelation_time"] == 1.0
    assert flat["effective_samples"] == 12.0

    drifting = landscape_study.stationarity_diagnostics(
        np.arange(12.0), max_normalized_drift=0.1, min_effective_samples=3.0
    )
    assert drifting["pass"] is False
    assert drifting["normalized_window_drift"] > 0.1


def test_stationarity_separates_platform_from_precision():
    # R06: stationarity (drift + non-monotonic shape) and precision (ESS) are
    # independent layers. A level platform with a huge ESS threshold passes
    # stationarity while failing precision.
    diagnostic = landscape_study.stationarity_diagnostics(
        [2.0] * 12, max_normalized_drift=0.1, min_effective_samples=1e9
    )
    assert diagnostic["drift_pass"] is True
    assert diagnostic["stationarity_pass"] is True
    assert diagnostic["precision_pass"] is False  # ESS=12 << 1e9

    # A drifting ramp is not a platform (stationarity fails) regardless of ESS.
    drifting = landscape_study.stationarity_diagnostics(
        np.arange(12.0), max_normalized_drift=0.1, min_effective_samples=1.0
    )
    assert drifting["stationarity_pass"] is False


def test_stationarity_rejects_nonmonotonic_ushape():
    # R06: a symmetric U-shape has ~zero linear slope but is not a platform.
    ushape = [0.0, 1.0, 2.0, 3.0, 4.0, 3.0, 2.0, 1.0, 0.0]
    diagnostic = landscape_study.stationarity_diagnostics(
        ushape, max_normalized_drift=0.1, min_effective_samples=3.0
    )
    assert diagnostic["drift_pass"] is True  # slope ≈ 0
    assert diagnostic["monotonic_pass"] is False
    assert diagnostic["stationarity_pass"] is False

    # A two-sigma reversal threshold still catches a pronounced U shape while
    # reducing accidental reversal flags in noisy stationary windows.
    stricter = landscape_study.stationarity_diagnostics(
        ushape,
        max_normalized_drift=0.1,
        min_effective_samples=3.0,
        reversal_span_sigma=2.0,
    )
    assert stricter["monotonic_pass"] is False


def test_stationarity_reports_nan_as_undefined_not_slope():
    # R01: a non-finite observation is reported as undefined, never as a slope.
    diagnostic = landscape_study.stationarity_diagnostics(
        [1.0, float("nan"), 1.0], max_normalized_drift=0.1, min_effective_samples=3.0
    )
    assert diagnostic["status"] == "undefined"
    assert diagnostic["stationarity_pass"] is False
    assert "slope_per_observation" not in diagnostic


def test_metric_status_three_states():
    valid = landscape_study.metric_status("wealth_gini", 0.42)
    assert valid["status"] == "valid" and valid["value"] == 0.42

    undefined = landscape_study.metric_status("density_morans_i", float("nan"))
    assert undefined["status"] == "undefined" and undefined["value"] is None
    assert undefined["reason"] == "constant_field"

    corrupt_nan = landscape_study.metric_status("wealth_gini", float("nan"))
    assert corrupt_nan["status"] == "invalid"

    inf = landscape_study.metric_status("wealth_gini", float("inf"))
    assert inf["status"] == "invalid" and inf["reason"] == "infinity"

    missing = landscape_study.metric_status("wealth_gini", None)
    assert missing["status"] == "undefined" and missing["value"] is None


def test_stationarity_absolute_drift_tolerance():
    # Cycle 3（E2 判定，2026-09-07）：指标稳态值趋零时，scale = max(|mean|, ptp)
    # 退化为噪声水平，把可忽略的绝对漂移放大成超阈值（相对 drift 归一化退化）。
    # 绝对漂移容差作为稳态的充分条件：绝对漂移 < 物理范围 1% 即稳态。
    values = np.linspace(-0.004, 0.004, 24)  # 稳态值≈0，绝对漂移 0.008
    without = landscape_study.stationarity_diagnostics(
        values, max_normalized_drift=0.1, min_effective_samples=4.0
    )
    assert without["normalized_window_drift"] > 0.1  # 相对 drift 被放大
    assert without["drift_pass"] is False  # 无容差时误判为非稳态

    with_tol = landscape_study.stationarity_diagnostics(
        values,
        max_normalized_drift=0.1,
        min_effective_samples=4.0,
        absolute_drift_tolerance=0.02,
    )
    assert with_tol["absolute_drift"] < 0.02  # 绝对漂移在容差内
    assert with_tol["drift_pass"] is True  # 绝对漂移判据 → 稳态
    assert with_tol["pass"] is True

    # 真实非稳态（绝对漂移大）不被容差误伤
    real_drift = np.linspace(0.0, 0.2, 24)  # rho 从 0 单调漂到 0.2
    real = landscape_study.stationarity_diagnostics(
        real_drift,
        max_normalized_drift=0.1,
        min_effective_samples=4.0,
        absolute_drift_tolerance=0.02,
    )
    assert real["absolute_drift"] >= 0.02
    assert real["drift_pass"] is False


def test_integrated_autocorrelation_time_is_bounded():
    tau = landscape_study.integrated_autocorrelation_time(
        [0.0, 1.0, 0.5, 1.5, 1.0, 2.0, 1.5, 2.5]
    )
    assert 1.0 <= tau <= 8.0


def test_resource_sampling_matches_cpp_bilinear_convention():
    # Mirrors politeia::TerrainGrid::elevation: node interpolation with index
    # clamping. If this drifts, E2-C4's source-rate accounting silently stops
    # describing what the simulator actually computes.
    grid = np.arange(16.0).reshape(4, 4)
    bounds = (0.0, 4.0, 0.0, 4.0)

    def sample(fx: float, fy: float) -> float:
        return float(
            landscape_study.resource_at_particles(
                grid, np.array([fx]), np.array([fy]), bounds
            )[0]
        )

    assert sample(1.0, 0.0) == pytest.approx(1.0)
    assert sample(0.5, 0.5) == pytest.approx(2.5)
    # Explicit weights of the four surrounding nodes at (fx, fy) = (0.25, 0.75).
    assert sample(0.25, 0.75) == pytest.approx(
        0.75 * 0.25 * grid[0, 0]
        + 0.25 * 0.25 * grid[0, 1]
        + 0.75 * 0.75 * grid[1, 0]
        + 0.25 * 0.75 * grid[1, 1]
    )
    assert sample(99.0, 99.0) == pytest.approx(15.0)
    assert sample(-5.0, -5.0) == pytest.approx(0.0)
    with pytest.raises(ValueError, match="strictly increasing"):
        landscape_study.resource_at_particles(
            grid, np.array([1.0]), np.array([1.0]), (4.0, 0.0, 0.0, 4.0)
        )


def test_snapshot_reader_exposes_eps_only_when_present(tmp_path):
    with_eps = tmp_path / "with-eps.csv"
    with_eps.write_text("x,y,w,eps\n1.0,2.0,3.0,4.0\n", encoding="utf-8")
    loaded = landscape_study.read_snapshot_csv(with_eps)
    assert set(loaded) == {"w", "x", "y", "eps"}
    assert float(loaded["eps"][0]) == pytest.approx(4.0)

    # Legacy snapshots without ability must still load; source-rate accounting
    # fails fast at the point of use instead of substituting a default.
    without_eps = tmp_path / "without-eps.csv"
    without_eps.write_text("x,y,w\n1.0,2.0,3.0\n", encoding="utf-8")
    assert set(landscape_study.read_snapshot_csv(without_eps)) == {"w", "x", "y"}


def test_three_condition_audit_requires_matched_totals():
    clustered = np.array([[0.0, 2.0], [1.0, 1.0]])
    shuffled = np.array([[1.0, 0.0], [1.0, 2.0]])
    flat = np.full((2, 2), float(clustered.mean()))
    audit = landscape_study.audit_three_condition_landscapes(
        clustered, shuffled, flat
    )
    assert audit["pass"] is True
    assert audit["exact_permutation"] is True
    assert audit["flat_constant"] is True
    assert audit["flat_equals_clustered_mean"] is True
    assert audit["means_match"] is True
    assert audit["positive_resource_support_match"] is True

    # A non-constant "flat" field is not a uniform source.
    assert (
        landscape_study.audit_three_condition_landscapes(
            clustered, shuffled, np.array([[1.0, 1.0], [1.0, 1.5]])
        )["flat_constant"]
        is False
    )
    # Rescaling the shuffled field breaks both permutation and total matching.
    rescaled = landscape_study.audit_three_condition_landscapes(
        clustered, shuffled * 1.5, flat
    )
    assert rescaled["exact_permutation"] is False
    assert rescaled["pass"] is False
    # A flat field whose value is not the clustered mean breaks total matching.
    assert (
        landscape_study.audit_three_condition_landscapes(
            clustered, shuffled, np.full((2, 2), 1.5)
        )["means_match"]
        is False
    )


def test_source_rate_metrics_mirrors_production_term():
    snapshot = {
        "x": np.array([1.0, 2.0]),
        "y": np.array([1.0, 2.0]),
        "eps": np.array([2.0, 4.0]),
    }
    metrics = landscape_study.source_rate_metrics(
        snapshot,
        np.full((4, 4), 3.0),
        (0.0, 4.0, 0.0, 4.0),
        base_production=0.01,
        terrain_production_scale=2.0,
    )
    # production per unit time is base * scale * resource(x_i) * eps_i.
    assert metrics["mean_resource_at_particles"] == pytest.approx(3.0)
    assert metrics["mean_source_rate"] == pytest.approx(0.01 * 2.0 * 3.0 * 3.0)
    assert metrics["total_source_rate"] == pytest.approx(0.01 * 2.0 * 3.0 * 3.0 * 2.0)
    with pytest.raises(ValueError, match="eps snapshot column"):
        landscape_study.source_rate_metrics(
            {"x": np.array([1.0]), "y": np.array([1.0])},
            np.ones((2, 2)),
            (0.0, 2.0, 0.0, 2.0),
            base_production=0.01,
            terrain_production_scale=1.0,
        )
