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


def test_resource_to_elevation_reconstructs_resource_contrast():
    resource = np.array([[0.0, 1.0], [2.0, 4.0]])
    elevation = landscape_study.resource_to_elevation(resource)
    reconstructed = elevation.max() - elevation
    assert np.array_equal(reconstructed, resource)


def test_write_esri_ascii_and_initial_conditions(tmp_path):
    resource = np.array([[0.0, 1.0], [2.0, 4.0]])
    grid_path = tmp_path / "grid.asc"
    grid_digest = landscape_study.write_esri_ascii(grid_path, resource)
    lines = grid_path.read_text(encoding="utf-8").splitlines()
    assert lines[:2] == ["ncols 2", "nrows 2"]
    assert len(grid_digest) == 64

    ic_path = tmp_path / "initial.csv"
    ic_digest = landscape_study.write_initial_conditions(
        ic_path, 100, 321, bounds=(0.0, 10.0, 0.0, 10.0)
    )
    table = np.genfromtxt(ic_path, delimiter=",", names=True)
    assert table.size == 100
    assert float(np.mean(table["w"])) == pytest.approx(5.0)
    assert float(np.std(table["w"])) > 0.0
    assert len(ic_digest) == 64


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
