from __future__ import annotations

import importlib.util
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
    assert landscape_study.morans_i(np.ones((3, 3))) == 0.0
    assert landscape_study.occupancy_entropy(np.ones((2, 2))) == pytest.approx(1.0)
    assert landscape_study.occupancy_entropy(np.array([[4.0, 0.0], [0.0, 0.0]])) == 0.0
    assert landscape_study.gini(np.array([1.0, 1.0])) == pytest.approx(0.0)
    assert landscape_study.gini(np.array([0.0, 2.0])) == pytest.approx(0.5)


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


def test_integrated_autocorrelation_time_is_bounded():
    tau = landscape_study.integrated_autocorrelation_time(
        [0.0, 1.0, 0.5, 1.5, 1.0, 2.0, 1.5, 2.5]
    )
    assert 1.0 <= tau <= 8.0
