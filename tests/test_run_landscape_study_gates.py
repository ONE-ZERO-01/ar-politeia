from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import pytest


MODULE_PATH = (
    Path(__file__).parents[1]
    / "research"
    / "src"
    / "experiments"
    / "run_landscape_study.py"
)
sys.path.insert(0, str(MODULE_PATH.parent))
SPEC = importlib.util.spec_from_file_location("run_landscape_study", MODULE_PATH)
assert SPEC and SPEC.loader
run_landscape_study = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(run_landscape_study)


def _e0_row(
    *,
    condition: str,
    seed: int = 1,
    gini: float = 0.5,
    variance: float = 1.0,
    drift: float = 0.0,
    stationary: bool = True,
) -> dict[str, object]:
    return {
        "seed": seed,
        "condition": condition,
        "resource_density_spearman_rho": 0.0,
        "density_morans_i": 0.0,
        "occupancy_entropy": 0.9,
        "wealth_gini": gini,
        "wealth_variance": variance,
        "minimum_wealth": 0.0,
        "total_wealth_relative_drift": drift,
        "stationarity_pass": stationary,
    }


def test_stationary_metrics_for_experiment_uses_cycle3_gate_sets():
    assert run_landscape_study.stationary_metrics_for_experiment(
        "E0-NUMERICS"
    ) == ("wealth_gini", "wealth_variance")
    assert "density_morans_i" not in (
        run_landscape_study.stationary_metrics_for_experiment("B0-DYNAMICS-PILOT")
    )
    # density_morans_i 已从所有 non-E0 实验的稳态 gate 移出（E1 与 B0 一致），
    # 仅作为确认性效应在配对分析中检验。
    assert "density_morans_i" not in (
        run_landscape_study.stationary_metrics_for_experiment("E1-MATCHED-LANDSCAPES")
    )


def test_aggregate_e0_passes_four_core_checks_with_stationarity_pending(tmp_path):
    rows = [
        _e0_row(condition="equal-no-exchange", seed=1),
        _e0_row(condition="equal-exchange", seed=1, variance=0.0),
        _e0_row(condition="perturbed-dt-1", seed=1),
        *[
            _e0_row(condition="perturbed-dt-0.5", seed=seed)
            for seed in (1, 2, 3)
        ],
        *[
            _e0_row(
                condition="perturbed-dt-0.25",
                seed=seed,
                stationary=(seed != 3),
            )
            for seed in (1, 2, 3)
        ],
    ]
    payload = run_landscape_study.aggregate_e0(rows, tmp_path)
    assert payload["pass"] is True
    assert payload["core_checks"] == {
        "wealth_conservation": True,
        "wealth_nonnegative": True,
        "dt_convergence": True,
        "equal_state_is_absorbing": True,
    }
    assert payload["stationarity_pass"] is False
    assert payload["stationarity_pending"] is True
    assert "stationarity" not in payload["core_checks"]


def test_aggregate_b0_excludes_moran_from_stationarity_gate(tmp_path):
    rows = [
        {
            "seed": seed,
            "condition": "clustered-active-health-only",
            "particle_count": 500.0,
            "minimum_wealth": 0.0,
            "stationarity_pass": True,
            "resource_density_spearman_rho": 0.3,
            "density_morans_i": 0.8,
            "occupancy_entropy": 0.7,
            "wealth_gini": 0.5,
            "wealth_variance": 1.0,
        }
        for seed in (7103, 7207, 7309)
    ]
    payload = run_landscape_study.aggregate_b0(
        rows, {"population": 500}, tmp_path
    )
    assert payload["pass"] is True
    assert "density_morans_i" not in payload["stationarity_metrics"]


def test_e2_default_conditions_pair_decay_with_production():
    # 参数锁 v3：生产通道 = 生产(source) + 衰减(sink) 平衡对。关闭生产时同步关闭
    # 衰减，否则 production=0 而 decay>0 会让财富指数坍缩（E1 flat bug 的数学根源）。
    config = {
        "exchange_rate": 0.5,
        "exchange_noise_strength": 0.05,
        "exchange_reversion_rate": 1.0,
        "epsilon_log_sigma": 0.5,
        "wealth_decay_rate": 0.02,
        "dt": 0.01,
    }
    conditions = run_landscape_study.default_conditions(
        "E2-CHANNEL-ABLATION", config
    )
    assert len(conditions) == 8  # 2 landscapes x 2 force x 2 production
    assert {c["terrain_force_enabled"] for c in conditions} == {False, True}
    assert {c["terrain_production_enabled"] for c in conditions} == {False, True}
    for cond in conditions:
        production = cond["terrain_production_enabled"]
        expected_decay = 0.02 if production else 0.0
        assert cond["wealth_decay_rate"] == expected_decay, cond["name"]
        # 名字约定 f{landscape}-f{int(force)}-p{int(production)} 用于快速定位
        assert cond["name"].endswith(f"-p{int(production)}")
