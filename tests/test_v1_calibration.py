from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


EXPERIMENTS = Path(__file__).parents[1] / "research" / "src" / "experiments"
sys.path.insert(0, str(EXPERIMENTS))
MODULE_PATH = EXPERIMENTS / "run_v1_calibration.py"
SPEC = importlib.util.spec_from_file_location("run_v1_calibration", MODULE_PATH)
assert SPEC and SPEC.loader
run_v1 = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(run_v1)

V1CD_MODULE_PATH = EXPERIMENTS / "run_v1c_steady_estimand_diagnostic.py"
V1CD_SPEC = importlib.util.spec_from_file_location(
    "run_v1c_steady_estimand_diagnostic", V1CD_MODULE_PATH
)
assert V1CD_SPEC and V1CD_SPEC.loader
run_v1cd = importlib.util.module_from_spec(V1CD_SPEC)
V1CD_SPEC.loader.exec_module(run_v1cd)


def condition(name, landscape, dt, component, **extra):
    return {
        "name": name,
        "landscape": landscape,
        "dt": dt,
        "calibration_component": component,
        "terrain_force_enabled": True,
        "terrain_production_enabled": True,
        "exchange_rate": 0.5,
        **extra,
    }


def full_conditions():
    conditions = [
        condition(f"{landscape}-dt-{dt}", landscape, dt, "timestep")
        for landscape in ("smooth", "clustered", "shuffled")
        for dt in (0.02, 0.01, 0.005)
    ]
    conditions.extend(
        condition(
            f"order-{storage}-dt-{dt}",
            "clustered",
            dt,
            "order",
            storage_order=storage,
            explicit_phase_state=True,
            temperature=0.0,
        )
        for dt in (0.02, 0.01, 0.005)
        for storage in ("canonical", "permuted")
    )
    return conditions


def test_weak_bound_is_zero_for_identical_replicates():
    bound = run_v1._weak_bound([1.0, 2.0, 3.0], [1.0, 2.0, 3.0])
    assert bound["two_se_bound"] == 0.0
    assert bound["replicates"] == 3


def test_validate_full_matrix_accepts_registered_cross_product():
    run_v1.validate_full_matrix(
        {
            "seeds": [101, 211, 307],
            "timesteps": [0.02, 0.01, 0.005],
            "conditions": full_conditions(),
        }
    )


def test_validate_full_matrix_rejects_missing_order_pair():
    with pytest.raises(ValueError, match="order matrix"):
        run_v1.validate_full_matrix(
            {
                "seeds": [101, 211, 307],
                "timesteps": [0.02, 0.01, 0.005],
                "conditions": full_conditions()[:-1],
            }
        )


def test_validate_full_matrix_rejects_unknown_stationarity_gate_unit():
    with pytest.raises(ValueError, match="stationarity_gate_unit"):
        run_v1.validate_full_matrix(
            {
                "seeds": [101, 211, 307],
                "timesteps": [0.02, 0.01, 0.005],
                "conditions": full_conditions(),
                "stationarity_gate_unit": "individual_majority",
            }
        )


def test_order_condition_requires_noise_isolation_and_explicit_state():
    bad = condition(
        "bad-order",
        "clustered",
        0.01,
        "order",
        storage_order="canonical",
        explicit_phase_state=False,
        temperature=0.5,
    )
    with pytest.raises(ValueError, match="temperature=0"):
        run_v1._validate_conditions([bad])


def test_v1cd_precision_uses_independent_run_window_means():
    specs = {
        ("smooth", 0.01): [
            {"run_id": "a"},
            {"run_id": "b"},
        ]
    }
    series = {
        run_id: {
            metric: values
            for metric in run_v1cd.STATIONARY_METRICS
        }
        for run_id, values in {
            "a": [0.0, 2.0],
            "b": [2.0, 4.0],
        }.items()
    }
    report = run_v1cd._independent_replicate_precision(
        specs,
        series,
        segment=slice(0, 2),
        planning_half_widths={"resource_density_spearman_rho": 2.0},
    )
    metric = report["conditions"]["smooth--dt-0.01"][
        "resource_density_spearman_rho"
    ]
    assert metric["mean_of_run_window_means"] == pytest.approx(2.0)
    assert metric["two_se_half_width"] == pytest.approx(2.0)
    assert metric["planning_width_pass"] is True
    assert metric["estimated_replicates_for_planning_width"] == 3
