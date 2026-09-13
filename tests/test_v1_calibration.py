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
