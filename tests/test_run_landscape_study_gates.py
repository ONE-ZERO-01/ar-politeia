from __future__ import annotations

import importlib.util
import re
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
    entropy: float = 0.9,
) -> dict[str, object]:
    return {
        "seed": seed,
        "condition": condition,
        "resource_density_spearman_rho": 0.0,
        "density_morans_i": 0.0,
        "occupancy_entropy": entropy,
        "wealth_gini": gini,
        "wealth_variance": variance,
        "minimum_wealth": 0.0,
        "total_wealth_relative_drift": drift,
        "stationarity_pass": stationary,
    }


def test_stationary_metrics_for_experiment_restores_full_gate_sets():
    # R06: E0 wealth stationarity premise now includes zero_wealth_fraction.
    assert run_landscape_study.stationary_metrics_for_experiment(
        "E0-NUMERICS"
    ) == ("wealth_gini", "wealth_variance", "zero_wealth_fraction")
    # S03 (Cycle 4 remediation): density_morans_i restored to every non-E0
    # steady gate, wealth_variance restored to E2, zero_wealth_fraction added
    # (WP5.1). All non-E0 experiments share the full gate set.
    expected_non_e0 = (
        "resource_density_spearman_rho",
        "density_morans_i",
        "occupancy_entropy",
        "wealth_gini",
        "wealth_variance",
        "zero_wealth_fraction",
    )
    assert run_landscape_study.stationary_metrics_for_experiment(
        "B0-DYNAMICS-PILOT"
    ) == expected_non_e0
    assert run_landscape_study.stationary_metrics_for_experiment(
        "E1-MATCHED-LANDSCAPES"
    ) == expected_non_e0
    assert run_landscape_study.stationary_metrics_for_experiment(
        "E2-CHANNEL-ABLATION"
    ) == expected_non_e0
    assert run_landscape_study.stationary_metrics_for_experiment(
        "E3-ROBUSTNESS-HOLDOUT"
    ) == expected_non_e0


def test_absolute_drift_tolerance_for_metric():
    # 绝对漂移容差 = 指标物理范围的 1%，修复「稳态值趋零 → 相对 drift 退化」。
    # 无物理范围的指标（wealth_variance 量纲依赖财富尺度）返回 None。
    assert run_landscape_study.absolute_drift_tolerance_for_metric(
        "resource_density_spearman_rho"
    ) == 0.02
    assert run_landscape_study.absolute_drift_tolerance_for_metric(
        "density_morans_i"
    ) == 0.02
    assert run_landscape_study.absolute_drift_tolerance_for_metric(
        "occupancy_entropy"
    ) == 0.01
    assert run_landscape_study.absolute_drift_tolerance_for_metric(
        "wealth_gini"
    ) == 0.01
    assert run_landscape_study.absolute_drift_tolerance_for_metric(
        "zero_wealth_fraction"
    ) == 0.01
    assert run_landscape_study.absolute_drift_tolerance_for_metric(
        "wealth_variance"
    ) is None


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


def test_aggregate_b0_includes_moran_in_stationarity_gate(tmp_path):
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
            "zero_wealth_fraction": 0.0,
        }
        for seed in (7103, 7207, 7309)
    ]
    payload = run_landscape_study.aggregate_b0(
        rows, {"population": 500}, tmp_path
    )
    assert payload["pass"] is True
    # S03: density_morans_i restored to the steady-window gate.
    assert "density_morans_i" in payload["stationarity_metrics"]
    assert "zero_wealth_fraction" in payload["stationarity_metrics"]


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


def _fake_binary(tmp_path: Path) -> Path:
    binary = tmp_path / "politeia"
    binary.write_text("#!/bin/sh\nexit 0\n")
    binary.chmod(0o755)
    return binary


def test_execute_runs_serial_merges_per_run_summaries(tmp_path, monkeypatch):
    # execute_runs 串行分支正确合并 executed/skipped/elapsed/completed_run_ids。
    def fake_execute(spec, binary, binary_sha256, *, timeout_seconds, omp_threads):
        run_id = str(spec["run_id"])
        # r0/r1 复用（skip），其余执行
        if run_id in {"r0", "r1"}:
            return {
                "executed": 0,
                "skipped": 1,
                "elapsed_seconds_executed": 0.0,
                "run_id": run_id,
            }
        return {
            "executed": 1,
            "skipped": 0,
            "elapsed_seconds_executed": 2.5,
            "run_id": run_id,
        }

    monkeypatch.setattr(run_landscape_study, "_execute_one_run", fake_execute)
    binary = _fake_binary(tmp_path)
    run_specs = [
        {
            "run_id": f"r{i}",
            "run_dir": str(tmp_path / f"r{i}"),
            "cpp_config": str(tmp_path / f"r{i}.cfg"),
        }
        for i in range(4)
    ]
    summary = run_landscape_study.execute_runs(
        run_specs, binary, timeout_seconds=3600, omp_threads=1, parallel=1
    )
    assert summary["executed"] == 2
    assert summary["skipped_completed"] == 2
    assert summary["elapsed_seconds_executed"] == 5.0
    assert summary["completed_run_ids"] == ["r0", "r1", "r2", "r3"]


def test_execute_runs_parallel_merges_and_speeds_up(tmp_path, monkeypatch):
    # 并行分支：8 个各 0.1s 的「单核子进程」用 4 路并行应 ~0.2s（串行 ~0.8s），
    # 且合并结果与串行等价。桩模拟 subprocess.run 释放 GIL 后的 CPU-bound 行为。
    import time as _time

    def fake_execute(spec, binary, binary_sha256, *, timeout_seconds, omp_threads):
        _time.sleep(0.1)
        return {
            "executed": 1,
            "skipped": 0,
            "elapsed_seconds_executed": 0.1,
            "run_id": str(spec["run_id"]),
        }

    monkeypatch.setattr(run_landscape_study, "_execute_one_run", fake_execute)
    binary = _fake_binary(tmp_path)
    run_specs = [
        {
            "run_id": f"r{i}",
            "run_dir": str(tmp_path / f"r{i}"),
            "cpp_config": str(tmp_path / f"r{i}.cfg"),
        }
        for i in range(8)
    ]
    started = _time.monotonic()
    summary = run_landscape_study.execute_runs(
        run_specs, binary, timeout_seconds=3600, omp_threads=1, parallel=4
    )
    elapsed = _time.monotonic() - started
    assert summary["executed"] == 8
    assert summary["skipped_completed"] == 0
    assert summary["completed_run_ids"] == [f"r{i}" for i in range(8)]
    # 4 路并行 8×0.1s ≈ 0.2s；串行需 0.8s。留裕量，验证确实并行而非串行。
    assert elapsed < 0.6, f"expected parallel speedup, took {elapsed:.2f}s"


def _e0_valid_rows() -> list[dict[str, object]]:
    return [
        _e0_row(condition="equal-no-exchange", seed=1),
        _e0_row(condition="equal-exchange", seed=1, variance=0.0),
        _e0_row(condition="perturbed-dt-1", seed=1),
        *[
            _e0_row(condition="perturbed-dt-0.5", seed=seed)
            for seed in (1, 2, 3)
        ],
        *[
            _e0_row(condition="perturbed-dt-0.25", seed=seed)
            for seed in (1, 2, 3)
        ],
    ]


def test_aggregate_e0_rejects_invalid_required_metrics(tmp_path):
    # R02: NaN/Inf in a required metric (wealth_gini / occupancy_entropy) is
    # data corruption and must fail, not be silently excluded.
    for bad in (float("nan"), float("inf")):
        rows = _e0_valid_rows()
        for row in rows:
            if row["condition"] in ("perturbed-dt-0.5", "perturbed-dt-0.25"):
                row["wealth_gini"] = bad
        with pytest.raises(RuntimeError, match="invalid"):
            run_landscape_study.aggregate_e0(rows, tmp_path)

    rows = _e0_valid_rows()
    for row in rows:
        if row["condition"] in ("perturbed-dt-0.5", "perturbed-dt-0.25"):
            row["occupancy_entropy"] = float("inf")
    with pytest.raises(RuntimeError, match="invalid"):
        run_landscape_study.aggregate_e0(rows, tmp_path)


def test_aggregate_e0_tolerates_degenerate_spatial_metrics(tmp_path):
    # R02: constant-field Spearman/Moran NaN are expected degenerate and must
    # be recorded (not raise), while required metrics stay calibrated.
    rows = _e0_valid_rows()
    for row in rows:
        if row["condition"] in ("perturbed-dt-0.5", "perturbed-dt-0.25"):
            row["resource_density_spearman_rho"] = float("nan")
            row["density_morans_i"] = float("nan")
    payload = run_landscape_study.aggregate_e0(rows, tmp_path)
    assert set(payload["undefined_degenerate_metrics"]) == {
        "resource_density_spearman_rho",
        "density_morans_i",
    }
    assert payload["pass"] is True
    assert "gate_layers" in payload
    assert payload["gate_layers"]["numerics_valid"] is True


def test_validate_calibration_coverage(tmp_path):
    required = (
        "resource_density_spearman_rho",
        "density_morans_i",
        "occupancy_entropy",
        "wealth_gini",
    )
    good = {
        "sesoi_frozen_before_confirmatory_analysis": {
            "resource_density_spearman_rho": 0.02,
            "density_morans_i": 0.02,
            "occupancy_entropy": 0.01,
            "wealth_gini": 0.01,
        }
    }
    run_landscape_study.validate_calibration_coverage(good, required)  # no raise

    missing = {
        "sesoi_frozen_before_confirmatory_analysis": {
            "occupancy_entropy": 0.01,
            "wealth_gini": 0.01,
        }
    }
    with pytest.raises(RuntimeError, match="missing SESOI"):
        run_landscape_study.validate_calibration_coverage(missing, required)

    nonfinite = {
        "sesoi_frozen_before_confirmatory_analysis": {
            "resource_density_spearman_rho": float("inf"),
            "density_morans_i": 0.02,
            "occupancy_entropy": 0.01,
            "wealth_gini": 0.01,
        }
    }
    with pytest.raises(RuntimeError, match="non-finite SESOI"):
        run_landscape_study.validate_calibration_coverage(nonfinite, required)


def test_no_exchange_conditions_disable_reversion_and_enabled():
    # R04: no-exchange controls must disable drift, noise AND reversion, and set
    # the exchange_enabled master switch so the kernel is a strict no-op.
    config = {
        "exchange_rate": 0.003,
        "exchange_noise_strength": 0.05,
        "exchange_reversion_rate": 1.0,
        "epsilon_log_sigma": 0.5,
        "wealth_decay_rate": 0.0,
        "dt": 0.01,
    }
    e0 = run_landscape_study.default_conditions("E0-NUMERICS", config)
    e0_ne = next(c for c in e0 if c["name"] == "equal-no-exchange")
    assert e0_ne["exchange_reversion_rate"] == 0.0
    assert e0_ne["exchange_enabled"] is False

    e1 = run_landscape_study.default_conditions("E1-MATCHED-LANDSCAPES", config)
    e1_ne = next(c for c in e1 if c["name"] == "clustered-no-exchange")
    assert e1_ne["exchange_reversion_rate"] == 0.0
    assert e1_ne["exchange_enabled"] is False


def test_e1_c4_conditions_are_only_the_matched_confirmatory_pair():
    conditions = run_landscape_study.default_conditions(
        "E1-MATCHED-LANDSCAPES-C4",
        {
            "exchange_rate": 0.5,
            "exchange_noise_strength": 0.05,
            "epsilon_log_sigma": 0.5,
            "dt": 0.005,
        },
    )
    assert [condition["name"] for condition in conditions] == [
        "clustered",
        "shuffled",
    ]
    assert all(condition["terrain_force_enabled"] for condition in conditions)
    assert all(condition["terrain_production_enabled"] for condition in conditions)


def test_reference_binary_requires_exact_frozen_checksum(tmp_path, monkeypatch):
    binary = tmp_path / "politeia"
    binary.write_bytes(b"validated simulator")
    monkeypatch.setattr(run_landscape_study, "PROJECT_ROOT", tmp_path)
    checksum = run_landscape_study.sha256_file(binary)

    resolved = run_landscape_study.validate_reference_binary(
        {"binary": "politeia", "binary_sha256": checksum}
    )
    assert resolved == binary

    with pytest.raises(RuntimeError, match="reference binary checksum mismatch"):
        run_landscape_study.validate_reference_binary(
            {"binary": "politeia", "binary_sha256": "0" * 64}
        )
    with pytest.raises(RuntimeError, match="requires a frozen"):
        run_landscape_study.validate_reference_binary({"binary": "politeia"})


def test_c4_calibration_keeps_numerical_and_scientific_thresholds_separate():
    calibration = {
        "experiment": "V1F-NONFLAT-CALIBRATION-C4",
        "pass": True,
        "numerical_resolution_limits": {
            "resource_density_spearman_rho": 0.06,
            "density_morans_i": 0.01,
            "occupancy_entropy": 0.002,
            "wealth_gini": 0.003,
        },
    }
    scientific = {
        "resource_density_spearman_rho": 0.05,
        "density_morans_i": 0.05,
        "occupancy_entropy": 0.025,
        "wealth_gini": 0.025,
    }
    thresholds = run_landscape_study.validate_c4_calibration_coverage(
        calibration, scientific
    )
    assert thresholds["resource_density_spearman_rho"] == {
        "numerical_resolution_limit": 0.06,
        "scientific_sesoi": 0.05,
        "effective_claim_threshold": 0.06,
    }
    assert thresholds["occupancy_entropy"]["effective_claim_threshold"] == 0.025

    failed = {**calibration, "pass": False}
    with pytest.raises(RuntimeError, match="did not pass"):
        run_landscape_study.validate_c4_calibration_coverage(failed, scientific)
    with pytest.raises(RuntimeError, match="scientific_sesoi is missing wealth_gini"):
        run_landscape_study.validate_c4_calibration_coverage(
            calibration, {key: value for key, value in scientific.items() if key != "wealth_gini"}
        )


def test_c4_coverage_admits_the_extension_only_when_asked(tmp_path, monkeypatch):
    """E2-C4 needs a limit V1F never froze, but the default must stay strict.

    V1F recorded ``wealth_variance`` and did not freeze it, so a coverage check
    that only accepted the pristine artifact would make the V1H extension pointless
    and E2-C4 unrunnable. The opt-in keeps E1-C4's accepted input set unchanged and
    still refuses an extension that is not bound to the artifact it re-derived.
    """
    scientific = {"wealth_gini": 0.025, "wealth_variance": 0.048}
    extension = {
        "experiment": "V1H-CALIBRATION-EXTENSION-C4",
        "pass": True,
        "pathwise_claim": False,
        "extends": {
            "experiment": "V1F-NONFLAT-CALIBRATION-C4",
            "sha256": "a" * 64,
            "path": "research/jobs/V1F-NONFLAT-CALIBRATION-C4/numerical_calibration.json",
        },
        "faithfulness": {
            "field_mismatches": 0,
            "reproduced_limits": {
                "wealth_gini": {"recomputed": 0.0014, "frozen": 0.0014, "bit_equal": True}
            },
        },
        "numerical_resolution_limits": {"wealth_gini": 0.0014, "wealth_variance": 0.0568},
    }
    metrics = ("wealth_gini", "wealth_variance")

    # Without the opt-in the extension is not the pristine artifact.
    with pytest.raises(RuntimeError, match="requires V1F-NONFLAT-CALIBRATION-C4"):
        run_landscape_study.validate_c4_calibration_coverage(
            extension, scientific, metrics
        )

    thresholds = run_landscape_study.validate_c4_calibration_coverage(
        extension, scientific, metrics, allow_extension=True
    )
    assert thresholds["wealth_variance"] == {
        "numerical_resolution_limit": 0.0568,
        "scientific_sesoi": 0.048,
        "effective_claim_threshold": 0.0568,
    }

    # The opt-in relaxes *which artifact*, never *whether it is bound*: an
    # extension that did not reproduce its source is rejected even here.
    unfaithful = {
        **extension,
        "faithfulness": {**extension["faithfulness"], "field_mismatches": 2},
    }
    with pytest.raises(RuntimeError, match="bit-for-bit"):
        run_landscape_study.validate_c4_calibration_coverage(
            unfaithful, scientific, metrics, allow_extension=True
        )
    unbound = {**extension, "extends": {"experiment": "V1F-NONFLAT-CALIBRATION-C4"}}
    with pytest.raises(RuntimeError, match="must pin its source's 64-character sha256"):
        run_landscape_study.validate_c4_calibration_coverage(
            unbound, scientific, metrics, allow_extension=True
        )


def test_e1_c4_steady_contract_requires_complete_disjoint_bounds():
    metrics = run_landscape_study.stationary_metrics_for_experiment(
        "E1-MATCHED-LANDSCAPES-C4"
    )
    config = {
        "stationarity_gate_unit": "condition_ensemble_two_window",
        "steady_snapshots": 144,
        "output_time_interval": 5.0,
        "total_time": 4500.0,
        "independent_precision_absolute_half_widths": {
            metric: 0.05 for metric in metrics if metric != "wealth_variance"
        },
        "independent_precision_relative_half_widths": {"wealth_variance": 0.2},
        "adjacent_window_absolute_bounds": {
            metric: 0.05 for metric in metrics if metric != "wealth_variance"
        },
        "adjacent_window_relative_bounds": {"wealth_variance": 0.1},
    }
    run_landscape_study._validate_c4_steady_contract(config)
    config["adjacent_window_absolute_bounds"].pop("wealth_gini")
    with pytest.raises(ValueError, match="must cover every steady metric"):
        run_landscape_study._validate_c4_steady_contract(config)


def test_aggregate_e1_c4_uses_effective_threshold_and_valid_null_policy(
    tmp_path, monkeypatch
):
    calibration = {
        "experiment": "V1F-NONFLAT-CALIBRATION-C4",
        "pass": True,
        "numerical_resolution_limits": {
            "resource_density_spearman_rho": 0.06,
            "density_morans_i": 0.01,
            "occupancy_entropy": 0.002,
            "wealth_gini": 0.003,
        },
    }
    monkeypatch.setattr(
        run_landscape_study, "load_c4_calibration", lambda _config: calibration
    )
    run_landscape_study.write_json(
        tmp_path / "matched_input_audit.json", {"pass": True}
    )
    rows = []
    for seed in range(1, 9):
        for condition, offset in (("clustered", 0.2), ("shuffled", 0.0)):
            rows.append(
                {
                    "seed": seed,
                    "condition": condition,
                    "resource_density_spearman_rho": offset,
                    "density_morans_i": offset,
                    "occupancy_entropy": 0.5 + offset,
                    "wealth_gini": 0.3 + offset,
                    "minimum_wealth": 0.0,
                    "minimum_wealth_observed": 0.0,
                    "particle_count": 1000.0,
                    "total_wealth_relative_drift": -0.5,
                    # S12: clustered sits at a higher equilibrium level than
                    # shuffled even though both landscapes have the same
                    # resource total, so the Gini effect is a composite.
                    "mean_wealth": 2.0 if condition == "clustered" else 1.25,
                }
            )
    config = {
        "seeds": list(range(1, 9)),
        "population": 1000,
        "familywise_alpha": 0.05,
        "bootstrap_samples": 1000,
        "scientific_sesoi": {
            "resource_density_spearman_rho": 0.05,
            "density_morans_i": 0.05,
            "occupancy_entropy": 0.025,
            "wealth_gini": 0.025,
        },
    }
    steady = {
        "pass": True,
        "tail_stationarity_valid": True,
        "adjacent_window_stability_valid": True,
        "independent_replicate_precision_valid": True,
        "temporal_ess_diagnostic_valid": False,
    }
    payload = run_landscape_study.aggregate_e1_c4(
        rows, config, tmp_path, steady
    )
    assert payload["analysis_gate_pass"] is True
    assert payload["claim_supported"] is True
    assert payload["valid_null_or_equivalence"] is False
    assert payload["temporal_ess_diagnostic_pass"] is False
    spearman = payload["confirmatory_spatial_family"][
        "resource_density_spearman_rho"
    ]
    assert spearman["sesoi"] == 0.06
    assert spearman["threshold_components"]["scientific_sesoi"] == 0.05
    # S12: the wealth-scale composite must be reported so the Gini secondary
    # family can be read as a composite rather than a single-channel effect.
    scale = payload["wealth_scale_diagnostics"]
    assert scale["per_condition"]["clustered"]["mean_wealth"] == pytest.approx(2.0)
    assert scale["per_condition"]["shuffled"]["mean_wealth"] == pytest.approx(1.25)
    assert scale["per_condition"]["clustered"][
        "mean_wealth_scale_ratio"
    ] == pytest.approx(2.0 / 5.0)
    assert scale["paired_mean_wealth_difference"]["mean_difference"] == pytest.approx(
        0.75
    )
    assert scale["relative_mean_wealth_difference"] == pytest.approx(0.75 / 1.25)
    assert scale["gate_role"] == "diagnostic only; never enters a gate"


def test_analyze_runs_records_wealth_scale_ratio(tmp_path, monkeypatch):
    """S12: every metrics row must carry the exchange kernel's operating point."""
    import numpy as np

    monkeypatch.setattr(
        run_landscape_study,
        "project_path",
        lambda value, must_exist=False: Path(value),
    )
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    np.save(tmp_path / "resource.npy", np.ones((2, 2)), allow_pickle=False)
    (tmp_path / "initial.csv").write_text(
        "x,y,w\n1.0,1.0,4.0\n", encoding="utf-8"
    )
    for index in range(1, 7):
        (run_dir / f"snap_{index}.csv").write_text(
            "x,y,w\n1.0,1.0,2.0\n", encoding="utf-8"
        )
    # Stationarity diagnostics need a non-degenerate window, so vary the metrics
    # slightly across the three snapshots instead of returning a constant.
    call_count = {"value": 0}

    def fake_snapshot_metrics(_snapshot, _resource, _bounds):
        call_count["value"] += 1
        step = 0.01 * call_count["value"]
        return {
            "resource_density_spearman_rho": 0.2 + step,
            "density_morans_i": 0.3 + step,
            "occupancy_entropy": 0.7 + step,
            "wealth_gini": 0.4 + step,
            "wealth_variance": 1.5 + step,
            "zero_wealth_fraction": 0.0,
            "minimum_wealth": 0.1,
            "mean_wealth": 2.0,
            "particle_count": 1000.0,
        }

    monkeypatch.setattr(run_landscape_study, "snapshot_metrics", fake_snapshot_metrics)
    # The E2 aggregator needs four experiment cells; this test only checks that
    # analyze_runs writes the wealth-scale columns, so stub the dispatch out.
    monkeypatch.setattr(run_landscape_study, "aggregate_e2", lambda *args, **kwargs: None)
    spec = {
        "run_id": "run",
        "seed": 5,
        "condition": "clustered",
        "run_dir": str(run_dir),
        "resource_npy": str(tmp_path / "resource.npy"),
        "initial_conditions": str(tmp_path / "initial.csv"),
    }
    rows = run_landscape_study.analyze_runs(
        "E2-CHANNEL-ABLATION",
        {"ability_saturation_w": 4.0, "steady_snapshots": 6},
        tmp_path,
        [spec],
    )
    assert rows[0]["mean_wealth"] == pytest.approx(2.0)
    assert rows[0]["wealth_scale_ratio"] == pytest.approx(0.5)
    header = (tmp_path / "replicate_metrics.csv").read_text(encoding="utf-8").splitlines()[0]
    assert "mean_wealth" in header
    assert "wealth_scale_ratio" in header


def test_e1_c4_two_window_gate_uses_condition_ensembles(tmp_path, monkeypatch):
    monkeypatch.setattr(
        run_landscape_study,
        "project_path",
        lambda value, must_exist=False: Path(value),
    )
    monkeypatch.setattr(run_landscape_study, "read_snapshot_csv", lambda _path: {})
    monkeypatch.setattr(
        run_landscape_study,
        "snapshot_metrics",
        lambda _snapshot, _resource, _bounds: {
            "resource_density_spearman_rho": 0.2,
            "density_morans_i": 0.3,
            "occupancy_entropy": 0.7,
            "wealth_gini": 0.4,
            "wealth_variance": 1.5,
            "zero_wealth_fraction": 0.0,
            "minimum_wealth": 0.1,
            "mean_wealth": 2.0,
            "particle_count": 1000.0,
        },
    )
    resource = tmp_path / "resource.npy"
    import numpy as np

    np.save(resource, np.ones((2, 2)), allow_pickle=False)
    specs = []
    for condition in ("clustered", "shuffled"):
        for seed in (1, 2, 3):
            run_dir = tmp_path / f"{condition}-{seed}"
            run_dir.mkdir()
            for index in range(6):
                (run_dir / f"snap_{index:08d}.csv").write_text("stub\n")
            specs.append(
                {
                    "run_id": f"{condition}-{seed}",
                    "condition": condition,
                    "seed": seed,
                    "run_dir": str(run_dir),
                    "resource_npy": str(resource),
                }
            )
    bounded = {
        "resource_density_spearman_rho": 0.05,
        "density_morans_i": 0.05,
        "occupancy_entropy": 0.025,
        "wealth_gini": 0.025,
        "zero_wealth_fraction": 0.01,
    }
    config = {
        "seeds": [1, 2, 3],
        "bounds": [0.0, 1.0, 0.0, 1.0],
        "stationarity_gate_unit": "condition_ensemble_two_window",
        "steady_snapshots": 3,
        "output_time_interval": 5.0,
        "total_time": 30.0,
        "stationarity_max_normalized_drift": 0.1,
        "stationarity_min_ess": 3.0,
        "stationarity_reversal_span_sigma": 2.0,
        "independent_precision_absolute_half_widths": bounded,
        "independent_precision_relative_half_widths": {"wealth_variance": 0.2},
        "adjacent_window_absolute_bounds": bounded,
        "adjacent_window_relative_bounds": {"wealth_variance": 0.1},
    }
    payload = run_landscape_study.aggregate_e1_c4_steady_estimand(
        specs, config, tmp_path
    )
    assert payload["pass"] is True
    assert payload["replicates_per_condition"] == 3
    assert set(payload["conditions"]) == {"clustered", "shuffled"}
    assert (tmp_path / "steady_estimand_report.json").is_file()
    assert (tmp_path / "ensemble_stationarity_report.json").is_file()


# ─── E2-C4 channel separation (S09) ──────────────────────────────────────────

E2_C4_TEST_SEEDS = [1, 2, 3, 4, 5, 6, 7, 8]
E2_C4_TEST_PATTERN_UNITS = run_landscape_study.E2_C4_PATTERN_UNITS
E2_C4_TEST_SINK_UNITS = run_landscape_study.E2_C4_SINK_UNITS


def _e2_c4_row(
    seed: int,
    unit: str,
    *,
    gini: float,
    mean_wealth: float,
    moran: float = 0.3,
    entropy: float = 0.7,
) -> dict[str, object]:
    """One synthetic metrics row for an E2-C4 unit."""
    return {
        "seed": seed,
        "condition": unit,
        "occupancy_entropy": entropy,
        "density_morans_i": moran,
        # Undefined on the constant flat source field (S04); must not leak into
        # any contrast.
        "resource_density_spearman_rho": (
            None if unit == E2_C4_TEST_PATTERN_UNITS[2] else 0.2
        ),
        "wealth_gini": gini,
        "wealth_variance": 1.5,
        "zero_wealth_fraction": 0.0,
        "minimum_wealth": 0.1,
        "minimum_wealth_observed": 0.1,
        "mean_wealth": mean_wealth,
        "mean_source_rate": 0.01,
        "total_source_rate": 10.0,
        "mean_resource_at_particles": 1.0,
        "particle_count": 1000.0,
    }


def _e2_c4_rows(*, sink_gini_spread: float = 0.0) -> list[dict[str, object]]:
    """Three source patterns at the reference sink plus the P3 sink ladder."""
    clustered, shuffled, flat = E2_C4_TEST_PATTERN_UNITS
    d_low, d_ref, d_high = E2_C4_TEST_SINK_UNITS
    levels = {clustered: 1.00, shuffled: 0.95, flat: 1.05, d_low: 0.98, d_high: 1.02}
    rows: list[dict[str, object]] = []
    for seed in E2_C4_TEST_SEEDS:
        rows.append(_e2_c4_row(seed, clustered, gini=0.30, mean_wealth=levels[clustered]))
        rows.append(_e2_c4_row(seed, shuffled, gini=0.20, mean_wealth=levels[shuffled]))
        rows.append(_e2_c4_row(seed, flat, gini=0.25, mean_wealth=levels[flat]))
        rows.append(
            _e2_c4_row(
                seed, d_low, gini=0.30 - sink_gini_spread, mean_wealth=levels[d_low]
            )
        )
        rows.append(
            _e2_c4_row(
                seed, d_high, gini=0.30 + sink_gini_spread, mean_wealth=levels[d_high]
            )
        )
    return rows


def _e2_c4_config() -> dict[str, object]:
    return {
        "seeds": E2_C4_TEST_SEEDS,
        "population": 1000,
        "familywise_alpha": 0.05,
        "bootstrap_samples": 1000,
        "ability_saturation_w": 5.0,
        "comparability_zero_wealth_fraction_max": 0.05,
        "comparability_wealth_variance_min": 0.01,
        "comparability_mean_wealth_relative_band": 0.10,
        "scientific_sesoi": {"wealth_gini": 0.025},
    }


def _stub_e2_c4_calibration(monkeypatch) -> None:
    monkeypatch.setattr(
        run_landscape_study,
        "load_e2_c4_calibration",
        lambda _config: {
            "experiment": "V1F-NONFLAT-CALIBRATION-C4",
            "pass": True,
            "numerical_resolution_limits": {"wealth_gini": 0.003},
        },
    )


def test_e2_c4_conditions_are_the_five_unit_channel_separation_matrix():
    config = {
        "exchange_rate": 0.5,
        "exchange_noise_strength": 0.05,
        "epsilon_log_sigma": 0.5,
        "dt": 0.005,
    }
    conditions = run_landscape_study.default_conditions(
        "E2-CHANNEL-ABLATION-C4", config
    )
    # P1/P2's three source patterns plus P3's two extra sink rungs, with the
    # clustered reference unit shared, gives five deduplicated units.
    assert len(conditions) == 5
    assert [c["name"] for c in conditions] == list(run_landscape_study.E2_C4_UNIT_NAMES)
    # Constraint 3: every unit runs with positions exogenous to wealth.
    assert {c["terrain_force_enabled"] for c in conditions} == {False}
    assert {c["landscape"] for c in conditions} == {"clustered", "shuffled", "flat"}
    # Constraint 1: source and sink on in every unit, so a stationary
    # distribution exists at all.
    assert {c["terrain_production_enabled"] for c in conditions} == {True}
    # P3 holds base/d at 0.5 so omega* is matched and only tau = 1/d varies.
    for condition in conditions:
        assert condition["base_production"] / condition["wealth_decay_rate"] == pytest.approx(
            0.5
        )
    assert sorted({c["wealth_decay_rate"] for c in conditions}) == [0.01, 0.02, 0.04]


# The exact ``run_specs.json`` key set E1-C4 was declared and archived under
# (its frozen ``source_commit`` is b6d24b7). ``run_specs.json`` is a declared
# artifact of an authorized confirmatory experiment, so every key is part of a
# contract: adding one silently makes the archived generated inputs
# unreproducible from the commit that produced them. This literal exists to fail
# loudly if a later experiment's needs leak into the shared spec builder.
E1_C4_FROZEN_RUN_SPEC_KEYS = frozenset(
    {
        "calibration_component",
        "condition",
        "cpp_config",
        "dt",
        "epsilon_log_sigma",
        "exchange_enabled",
        "exchange_noise_strength",
        "exchange_rate",
        "exchange_reversion_rate",
        "explicit_phase_state",
        "initial_conditions",
        "initial_conditions_sha256",
        "landscape",
        "resource_npy",
        "resource_sha256",
        "run_dir",
        "run_id",
        "seed",
        "storage_order",
        "temperature",
        "terrain_force_enabled",
        "terrain_production_enabled",
        "terrain_sha256",
        "wealth_decay_rate",
    }
)


def _prepare_inputs_config() -> dict[str, object]:
    return {
        "seeds": [11, 12],
        "population": 16,
        "grid_shape": [16, 16],
        "bounds": [0.0, 100.0, 0.0, 100.0],
        "dt": 0.005,
        "total_time": 1.0,
        "output_time_interval": 0.5,
        "temperature": 0.5,
        "friction": 1.0,
        "social_strength": 0.0,
        "exchange_rate": 0.5,
        "exchange_noise_strength": 0.05,
        "exchange_reversion_rate": 1.0,
        "epsilon_log_sigma": 0.5,
        "wealth_decay_rate": 0.02,
        "base_production": 0.01,
        "mean_wealth": 5.0,
        "terrain_production_scale": 1.0,
        "terrain_force_scale": 1.0,
        "strict_numerics": True,
        "confirmative_mode": True,
    }


def test_prepare_inputs_keeps_e1_c4_schema_frozen_and_e2_c4_sink_aware(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(run_landscape_study, "PROJECT_ROOT", tmp_path)
    config = _prepare_inputs_config()

    e1_specs = run_landscape_study.prepare_inputs(
        "E1-MATCHED-LANDSCAPES-C4", config, tmp_path / "e1"
    )
    assert len(e1_specs) == 4  # two seeds x (clustered, shuffled)
    for spec in e1_specs:
        assert frozenset(spec) == E1_C4_FROZEN_RUN_SPEC_KEYS
        # E1-C4 has no per-run sink override, but the config-level source rate
        # must still reach the simulator through the generated cfg.
        cfg = run_landscape_study.project_path(spec["cpp_config"]).read_text()
        assert "base_production = 0.01" in cfg

    e2_specs = run_landscape_study.prepare_inputs(
        "E2-CHANNEL-ABLATION-C4", config, tmp_path / "e2"
    )
    assert len(e2_specs) == 10  # two seeds x five deduplicated units
    for spec in e2_specs:
        # E2-C4's realized source rate must be recomputable from the spec, so
        # it carries exactly one extra key -- and only that one.
        assert frozenset(spec) == E1_C4_FROZEN_RUN_SPEC_KEYS | {"base_production"}
        assert spec["base_production"] / spec["wealth_decay_rate"] == pytest.approx(0.5)
        cfg = run_landscape_study.project_path(spec["cpp_config"]).read_text()
        assert f"base_production = {spec['base_production']:g}" in cfg


def test_e2_c4_mean_metrics_requires_spec_source_rate():
    # P2's realized-source accounting scales with base_production; a spec that
    # lacks it would account zero source for every unit and let the
    # matched-source premise "pass" vacuously. The guard fires before any
    # filesystem work, so the bogus paths below are never reached.
    spec = {
        "run_id": "seed-1--clustered-d0.02",
        "run_dir": "does/not/exist",
        "resource_npy": "does/not/exist.npy",
    }
    kwargs = {
        "bounds": (0.0, 100.0, 0.0, 100.0),
        "steady_snapshots": 1,
        "stationarity_max_drift": 0.1,
        "stationarity_min_ess": 4.0,
        "stationary_metrics": ("wealth_gini",),
    }
    with pytest.raises(RuntimeError, match="without base_production"):
        run_landscape_study.mean_metrics_for_run(
            spec, experiment="E2-CHANNEL-ABLATION-C4", **kwargs
        )
    # Scoped: E1-C4 must keep the historical behaviour of reaching its run dir
    # (here the missing path surfaces), never the E2-C4 source-rate contract.
    with pytest.raises(FileNotFoundError):
        run_landscape_study.mean_metrics_for_run(
            spec, experiment="E1-MATCHED-LANDSCAPES-C4", **kwargs
        )


def test_e2_c4_structure_guard_rejects_wealth_dependent_movement():
    config = {"social_strength": 0.0}
    conditions = run_landscape_study.default_conditions(
        "E2-CHANNEL-ABLATION-C4", {"dt": 0.005, "epsilon_log_sigma": 0.5}
    )
    run_landscape_study.validate_e2_c4_structure(conditions, config)

    with pytest.raises(ValueError, match="social_strength = 0"):
        run_landscape_study.validate_e2_c4_structure(
            conditions, {"social_strength": 0.3}
        )
    forced = [dict(condition) for condition in conditions]
    forced[0]["terrain_force_enabled"] = True
    with pytest.raises(ValueError, match="enables terrain force"):
        run_landscape_study.validate_e2_c4_structure(forced, config)
    starved = [dict(condition) for condition in conditions]
    starved[1]["terrain_production_enabled"] = False
    with pytest.raises(ValueError, match="disables production"):
        run_landscape_study.validate_e2_c4_structure(starved, config)


def test_e2_c4_stationary_metrics_exclude_degenerate_spearman():
    metrics = run_landscape_study.stationary_metrics_for_experiment(
        "E2-CHANNEL-ABLATION-C4"
    )
    # Spearman is undefined on the constant flat source field, so it cannot be
    # part of the stationarity premise; the two pure-position metrics must be.
    assert "resource_density_spearman_rho" not in metrics
    for metric in (
        "density_morans_i",
        "occupancy_entropy",
        "wealth_gini",
        "wealth_variance",
        "zero_wealth_fraction",
    ):
        assert metric in metrics


def test_e2_c4_source_rate_matches_simulator_production_term():
    import numpy as np

    # Constant source field: production is base * scale * resource * eps, exactly
    # what apply_resource_dynamics computes from -elevation.
    snapshot = {
        "x": np.array([1.0, 2.0]),
        "y": np.array([1.0, 2.0]),
        "eps": np.array([2.0, 4.0]),
    }
    metrics = run_landscape_study.source_rate_metrics(
        snapshot,
        np.full((4, 4), 3.0),
        (0.0, 4.0, 0.0, 4.0),
        base_production=0.01,
        terrain_production_scale=1.0,
    )
    assert metrics["mean_resource_at_particles"] == pytest.approx(3.0)
    assert metrics["mean_source_rate"] == pytest.approx(0.01 * 3.0 * 3.0)
    assert metrics["total_source_rate"] == pytest.approx(0.01 * 3.0 * 3.0 * 2.0)

    with pytest.raises(ValueError, match="eps snapshot column"):
        run_landscape_study.source_rate_metrics(
            {"x": np.array([1.0]), "y": np.array([1.0])},
            np.ones((2, 2)),
            (0.0, 2.0, 0.0, 2.0),
            base_production=0.01,
            terrain_production_scale=1.0,
        )


def test_aggregate_e2_c4_reports_identity_comparability_and_blocks(
    tmp_path, monkeypatch
):
    _stub_e2_c4_calibration(monkeypatch)
    run_landscape_study.write_json(
        tmp_path / "matched_input_audit.json", {"pass": True}
    )
    steady = {"pass": True, "tail_stationarity_valid": True}
    payload = run_landscape_study.aggregate_e2_c4(
        _e2_c4_rows(), _e2_c4_config(), tmp_path, steady
    )
    assert payload["analysis_gate_pass"] is True
    assert payload["claim_supported"] is True
    # P1 is a guard entry, never an effect entry.
    assert payload["P1_isolation_identity"]["pass"] is True
    assert payload["P1_isolation_identity"]["violations"] == []
    assert payload["P4_comparability"]["pass"] is True
    # The old bundle's single-channel attribution fields must not reappear.
    for legacy in ("identified_channels", "interaction_identified", "mechanism_conclusion"):
        assert legacy not in payload
    assert (tmp_path / "channel_separation.json").is_file()
    assert (tmp_path / "isolation_identity_report.json").is_file()
    # P2's primary contrast is the histogram-matched source-pattern pair.
    primary = payload["P2_source_pattern"]["primary"]
    assert set(primary) == {
        f"{metric}::clustered-minus-shuffled"
        for metric in run_landscape_study.E2_C4_EFFECT_METRICS
    }
    assert primary["wealth_gini::clustered-minus-shuffled"]["claim_threshold_pass"] is True
    # The histogram-changing reference contrast is role-limited by the design and
    # must never carry a claim, even when it separates cleanly.
    reference = payload["P2_source_pattern"]["reference"]
    assert set(reference) == {
        f"{metric}::clustered-minus-flat"
        for metric in run_landscape_study.E2_C4_EFFECT_METRICS
    }
    assert all(
        entry["claim_eligible"] is False
        and entry["claim_threshold_pass"] is False
        and "reference role" in entry["descriptive_only"]
        for entry in reference.values()
    )
    # sink_gini_spread=0 => the ladder shows no detectable scale dependence.
    assert payload["P3_sink_rate"]["scale_invariance_assessment"] == (
        "not_falsified_within_thresholds"
    )
    assert payload["P3_sink_rate"]["matched_equilibrium"] is True
    assert payload["source_total_accounting"]["units"][
        run_landscape_study.E2_C4_PATTERN_UNITS[0]
    ]["total_source_rate"] == pytest.approx(10.0)


def test_aggregate_e2_c4_fails_fast_on_position_divergence(tmp_path, monkeypatch):
    _stub_e2_c4_calibration(monkeypatch)
    run_landscape_study.write_json(
        tmp_path / "matched_input_audit.json", {"pass": True}
    )
    rows = _e2_c4_rows()
    for row in rows:
        if row["condition"] == run_landscape_study.E2_C4_PATTERN_UNITS[1] and row["seed"] == 3:
            row["density_morans_i"] = 0.3000001
    with pytest.raises(RuntimeError, match="P1 isolation identity failed"):
        run_landscape_study.aggregate_e2_c4(
            rows, _e2_c4_config(), tmp_path, {"pass": True}
        )
    # The violation is still written out so the failure is auditable.
    report = run_landscape_study.load_json(
        tmp_path / "isolation_identity_report.json"
    )
    assert report["pass"] is False
    assert report["violations"][0]["seed"] == 3


def test_aggregate_e2_c4_marks_uncalibrated_metrics_claim_ineligible(
    tmp_path, monkeypatch
):
    _stub_e2_c4_calibration(monkeypatch)
    run_landscape_study.write_json(
        tmp_path / "matched_input_audit.json", {"pass": True}
    )
    payload = run_landscape_study.aggregate_e2_c4(
        _e2_c4_rows(), _e2_c4_config(), tmp_path, {"pass": True}
    )
    probe = payload["P2_source_pattern"]["primary"]
    gini = probe["wealth_gini::clustered-minus-shuffled"]
    assert gini["claim_eligible"] is True
    assert gini["threshold_components"]["effective_claim_threshold"] == pytest.approx(
        0.025
    )
    for metric in ("wealth_variance", "zero_wealth_fraction", "mean_wealth"):
        entry = probe[f"{metric}::clustered-minus-shuffled"]
        assert entry["claim_eligible"] is False
        assert entry["claim_threshold_pass"] is False
        assert "descriptive_only" in entry
    assert payload["threshold_provenance"]["claim_eligible_metrics"] == ["wealth_gini"]


def test_aggregate_e2_c4_requires_frozen_comparability_policy(tmp_path, monkeypatch):
    _stub_e2_c4_calibration(monkeypatch)
    run_landscape_study.write_json(
        tmp_path / "matched_input_audit.json", {"pass": True}
    )
    config = _e2_c4_config()
    del config["comparability_mean_wealth_relative_band"]
    with pytest.raises(RuntimeError, match="must be frozen before analysis"):
        run_landscape_study.aggregate_e2_c4(
            _e2_c4_rows(), config, tmp_path, {"pass": True}
        )


def test_aggregate_e2_c4_downgrades_unmatched_levels_to_inconclusive(
    tmp_path, monkeypatch
):
    _stub_e2_c4_calibration(monkeypatch)
    run_landscape_study.write_json(
        tmp_path / "matched_input_audit.json", {"pass": True}
    )
    rows = _e2_c4_rows()
    # A 40% wealth-scale gap between two source patterns cannot be absorbed by
    # the frozen band, and must make the contrast inconclusive rather than null.
    for row in rows:
        if row["condition"] == run_landscape_study.E2_C4_PATTERN_UNITS[1]:
            row["mean_wealth"] = float(row["mean_wealth"]) * 1.4
    payload = run_landscape_study.aggregate_e2_c4(
        rows, _e2_c4_config(), tmp_path, {"pass": True}
    )
    assert payload["P4_comparability"]["pass"] is False
    assert payload["analysis_gate_pass"] is False
    assert payload["inconclusive"] is True
    assert payload["claim_supported"] is False


def test_e2_c4_two_window_gate_runs_on_five_units(tmp_path, monkeypatch):
    import numpy as np

    monkeypatch.setattr(
        run_landscape_study,
        "project_path",
        lambda value, must_exist=False: Path(value),
    )
    monkeypatch.setattr(run_landscape_study, "read_snapshot_csv", lambda _path: {})
    monkeypatch.setattr(
        run_landscape_study,
        "snapshot_metrics",
        lambda _snapshot, _resource, _bounds: {
            "resource_density_spearman_rho": 0.2,
            "density_morans_i": 0.3,
            "occupancy_entropy": 0.7,
            "wealth_gini": 0.4,
            "wealth_variance": 1.5,
            "zero_wealth_fraction": 0.0,
            "minimum_wealth": 0.1,
            "mean_wealth": 2.0,
            "particle_count": 1000.0,
        },
    )
    resource = tmp_path / "resource.npy"
    np.save(resource, np.ones((2, 2)), allow_pickle=False)
    specs = []
    for condition in run_landscape_study.E2_C4_UNIT_NAMES:
        for seed in (1, 2, 3):
            run_dir = tmp_path / f"{condition}-{seed}"
            run_dir.mkdir()
            for index in range(6):
                (run_dir / f"snap_{index:08d}.csv").write_text("stub\n")
            specs.append(
                {
                    "run_id": f"{condition}-{seed}",
                    "condition": condition,
                    "seed": seed,
                    "run_dir": str(run_dir),
                    "resource_npy": str(resource),
                }
            )
    metrics = run_landscape_study.stationary_metrics_for_experiment(
        "E2-CHANNEL-ABLATION-C4"
    )
    bounded = {metric: 0.05 for metric in metrics if metric != "wealth_variance"}
    config = {
        "seeds": [1, 2, 3],
        "bounds": [0.0, 1.0, 0.0, 1.0],
        "stationarity_gate_unit": "condition_ensemble_two_window",
        "steady_snapshots": 3,
        "output_time_interval": 5.0,
        "total_time": 30.0,
        "stationarity_max_normalized_drift": 0.1,
        "stationarity_min_ess": 3.0,
        "stationarity_reversal_span_sigma": 2.0,
        "independent_precision_absolute_half_widths": bounded,
        "independent_precision_relative_half_widths": {"wealth_variance": 0.2},
        "adjacent_window_absolute_bounds": bounded,
        "adjacent_window_relative_bounds": {"wealth_variance": 0.1},
    }
    payload = run_landscape_study.aggregate_e1_c4_steady_estimand(
        specs,
        config,
        tmp_path,
        experiment="E2-CHANNEL-ABLATION-C4",
        expected_conditions=list(run_landscape_study.E2_C4_UNIT_NAMES),
    )
    assert payload["pass"] is True
    assert payload["experiment"] == "E2-CHANNEL-ABLATION-C4"
    assert set(payload["conditions"]) == set(run_landscape_study.E2_C4_UNIT_NAMES)
    assert payload["replicates_per_condition"] == 3


# ── claim eligibility: mechanical, threshold-free reasons ─────────────


def _by_seed(values_by_unit):
    """Build {seed: {unit: {metric: value}}} from {unit: [per-seed values]}."""
    lengths = {len(values) for values in values_by_unit.values()}
    assert len(lengths) == 1, "all units must carry the same seed count"
    count = lengths.pop()
    return {
        seed: {unit: {"m": values[seed]} for unit, values in values_by_unit.items()}
        for seed in range(count)
    }


def _reasons(by_seed, metric="m", limits=None, sesoi=None):
    return run_landscape_study.e2_c4_claim_ineligibility_reasons(
        by_seed,
        metric,
        {"m": 0.003} if limits is None else limits,
        {"m": 0.025} if sesoi is None else sesoi,
    )


def test_claim_eligibility_requires_a_frozen_limit_and_a_sesoi():
    by_seed = _by_seed({"a": [1.0, 2.0, 3.0], "b": [1.5, 2.5, 3.5]})
    assert _reasons(by_seed, limits={}, sesoi={}) == [
        "missing_numerical_resolution_limit",
        "missing_scientific_sesoi",
    ]
    assert _reasons(by_seed) == []


def test_claim_eligibility_refuses_a_zero_resolution_limit():
    """A limit of exactly 0.0 is bitwise invariance, not perfect precision."""
    by_seed = _by_seed({"a": [1.0, 2.0, 3.0], "b": [1.5, 2.5, 3.5]})
    assert _reasons(by_seed, limits={"m": 0.0}) == ["zero_numerical_resolution_limit"]


def test_claim_eligibility_refuses_a_metric_with_no_variance():
    by_seed = _by_seed({"a": [0.0, 0.0, 0.0], "b": [0.0, 0.0, 0.0]})
    assert _reasons(by_seed) == ["degenerate_metric_no_variance"]


def test_claim_eligibility_refuses_the_measured_zero_wealth_fraction_shape():
    """Both reasons at once, exactly as measured on V1F's 960 runs."""
    by_seed = _by_seed({"a": [0.0, 0.0, 0.0], "b": [0.0, 0.0, 0.0]})
    assert _reasons(by_seed, limits={"m": 0.0}) == [
        "zero_numerical_resolution_limit",
        "degenerate_metric_no_variance",
    ]


def test_claim_eligibility_follows_the_data_rather_than_a_fixed_allowlist():
    """Mutation: the same metric flips once its values vary and its limit is real."""
    assert _reasons(_by_seed({"a": [0.0, 0.0, 0.0], "b": [0.0, 0.0, 0.0]}), limits={"m": 0.0}) != []
    varying = _by_seed({"a": [0.0, 0.0, 0.0], "b": [0.0, 1e-5, 2e-5]})
    assert _reasons(varying, limits={"m": 1e-6}) == []


def test_aggregate_e2_c4_reports_why_each_metric_is_ineligible(tmp_path, monkeypatch):
    _stub_e2_c4_calibration(monkeypatch)
    run_landscape_study.write_json(tmp_path / "matched_input_audit.json", {"pass": True})
    payload = run_landscape_study.aggregate_e2_c4(
        _e2_c4_rows(), _e2_c4_config(), tmp_path, {"pass": True}
    )
    reasons = payload["threshold_provenance"]["ineligibility_reasons"]
    # The three uncalibrated metrics must each say why, not merely be excluded.
    assert set(reasons) == {"wealth_variance", "zero_wealth_fraction", "mean_wealth"}
    for metric_reasons in reasons.values():
        assert "missing_numerical_resolution_limit" in metric_reasons
    assert "wealth_gini" not in reasons


# ── design ↔ code consistency (guards the section-14 class of error) ───

DESIGN_PATH = Path(__file__).parents[1] / "research" / "e2-cycle4-channel-design.md"


def _design_section(heading: str, next_heading: str) -> str:
    text = DESIGN_PATH.read_text(encoding="utf-8")
    return text.split(heading, 1)[1].split(next_heading, 1)[0]


def test_design_reason_vocabulary_equals_the_codes_the_function_emits():
    """A reason added in code but absent from the design is an unregistered threshold."""
    section = _design_section("### 15.3", "### 15.4")
    documented = set(re.findall(r"^\|\s*`([a-z_]+)`\s*\|", section, flags=re.MULTILINE))

    source = MODULE_PATH.read_text(encoding="utf-8")
    function = source.split("def e2_c4_claim_ineligibility_reasons", 1)[1].split("\ndef ", 1)[0]
    emitted = set(re.findall(r'reasons\.append\(\s*"([a-z_]+)"\s*\)', function))

    assert documented == emitted
    assert len(documented) == 4


def test_design_p2_accounts_for_every_metric_in_the_code_effect_family():
    """P2's prose must split the code's effect family into estimands and audits.

    A metric that the code computes but the design never mentions is exactly the
    section-14 failure: reach asserted in prose that the code does not grant, or
    granted by the code but never written down.
    """
    bullet = _design_section("### P2 — 源的空间组织消融", "- 关键性质")
    estimand_line = bullet.split("- 估计量：", 1)[1].split("。", 1)[0]
    estimands = set(re.findall(r"`([a-z_]+)`", estimand_line))

    assert estimands == {"wealth_gini", "wealth_variance"}
    # The other two are named, but only to state the role they may not exceed.
    non_estimands = {"zero_wealth_fraction", "mean_wealth"}
    for metric in sorted(non_estimands):
        assert f"`{metric}`：" in bullet
    assert estimands | non_estimands == set(run_landscape_study.E2_C4_EFFECT_METRICS)
    assert run_landscape_study.E2_C4_EFFECT_METRICS == (
        "wealth_gini",
        "wealth_variance",
        "zero_wealth_fraction",
        "mean_wealth",
    )
