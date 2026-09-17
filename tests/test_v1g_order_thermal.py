"""V1G readiness: the storage-order probe at the reference temperature.

V1F's order layer is forced to ``temperature = 0.0``, so the frozen numerical
ceiling was measured with the only index-keyed random source switched off (S18).
V1G re-runs that layer at the temperature the reference configuration actually
uses. This module checks the three things that make the probe trustworthy
*before* it is submitted, because none of them can be checked afterwards:

1. its thresholds really are the frozen ones -- read through the parameter lock,
   which is re-hashed and cross-checked against the tracked calibration (and the
   lock's two binary bindings must agree, the S14 defect);
2. its protocol cannot drift from the reference experiment's -- every structural
   guard fails fast, including the tempting wrong setting (``T = 0``, which would
   silently reproduce V1F and answer nothing);
3. its inputs really are the same physical state in two row orders -- otherwise
   the paired difference would conflate row order with different initial data.

Everything here is static or writes only into ``tmp_path``.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import shutil
import sys

import pytest

REPO_ROOT = Path(__file__).parents[1]
V1G_CONFIG = "research/jobs/V1G-ORDER-THERMAL-C4/config.json"
PARAMETER_LOCK = "research/parameter_lock.cycle4.json"
CALIBRATION = "research/jobs/V1F-NONFLAT-CALIBRATION-C4/numerical_calibration.json"
REFERENCE_CONFIG = "research/jobs/E1-MATCHED-LANDSCAPES-C4/config.json"
SEEDS = "research/jobs/V1F-NONFLAT-CALIBRATION-C4/seeds.txt"

EXPERIMENTS_DIR = REPO_ROOT / "research" / "src" / "experiments"
sys.path.insert(0, str(EXPERIMENTS_DIR))
for name in ("landscape_study", "run_landscape_study", "run_v1_calibration", "run_v1g_order_thermal"):
    spec = importlib.util.spec_from_file_location(name, EXPERIMENTS_DIR / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)

v1g = sys.modules["run_v1g_order_thermal"]


def _v1g_config() -> dict:
    return json.loads((REPO_ROOT / V1G_CONFIG).read_text(encoding="utf-8"))


def _reference() -> dict:
    return v1g.reference_protocol(REPO_ROOT)


def _seeds() -> list[int]:
    return v1g.frozen_v1f_seeds(REPO_ROOT)


def test_thresholds_are_the_frozen_ones_read_through_the_lock():
    frozen = v1g.load_frozen_bound(REPO_ROOT)
    lock = json.loads((REPO_ROOT / PARAMETER_LOCK).read_text(encoding="utf-8"))

    assert frozen["limits"] == {
        metric: float(lock["numerical_calibration"]["numerical_resolution_limits"][metric])
        for metric in v1g.CALIBRATION_METRICS
    }
    # The probe must be pinned to the calibrated binary, not merely to "a" binary
    # that happens to run: this is the binding S14 showed can silently break.
    assert frozen["binary_sha256"] == lock["simulator_validation"]["binary_sha256"]
    assert frozen["binary_sha256"] == lock["numerical_calibration"]["reference_binary_sha256"]
    assert frozen["calibration_sha256"] == lock["numerical_calibration"]["sha256"]
    # The comparison against T=0 only exists if the frozen order layer is present.
    assert set(frozen["t0_order_layer"]) == set(v1g.CALIBRATION_METRICS)


def test_tampered_calibration_is_refused(tmp_path):
    (tmp_path / "research" / "jobs" / "V1F-NONFLAT-CALIBRATION-C4").mkdir(parents=True)
    shutil.copyfile(REPO_ROOT / PARAMETER_LOCK, tmp_path / PARAMETER_LOCK)
    target = tmp_path / "research" / "jobs" / "V1F-NONFLAT-CALIBRATION-C4" / "numerical_calibration.json"
    shutil.copyfile(REPO_ROOT / CALIBRATION, target)

    assert v1g.load_frozen_bound(tmp_path)["limits"]

    document = json.loads(target.read_text(encoding="utf-8"))
    document["numerical_resolution_limits"]["wealth_gini"] *= 4.0
    target.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(RuntimeError, match="no longer matches the lock"):
        v1g.load_frozen_bound(tmp_path)


def test_validator_accepts_the_declared_probe_config():
    conditions = v1g.validate_v1g_config(
        _v1g_config(), reference=_reference(), expected_seeds=_seeds()
    )
    assert sorted(item["storage_order"] for item in conditions) == ["canonical", "permuted"]
    assert all(item["explicit_phase_state"] is True for item in conditions)


@pytest.mark.parametrize(
    "mutate, message",
    [
        (lambda c: c.update(experiment_id="something-else"), "unexpected experiment_id"),
        # The tempting wrong setting: T=0 would reproduce V1F and answer nothing.
        (lambda c: c.update(temperature=0.0), "reference protocol"),
        (lambda c: c.update(dt=0.01), "reference protocol"),
        (lambda c: c.update(total_time=1500.0), "reference protocol"),
        (lambda c: c.update(steady_snapshots=48), "reference protocol"),
        (lambda c: c.update(seeds=c["seeds"][:8]), "frozen V1F seeds"),
        (lambda c: c["conditions"][0].update(temperature=0.0), "reference temperature"),
        (lambda c: c["conditions"][0].update(landscape="smooth"), "holds the landscape fixed"),
        (lambda c: c["conditions"][0].update(dt=0.01), "holds dt fixed"),
        (lambda c: c["conditions"][0].update(explicit_phase_state=False), "explicit_phase_state"),
        (lambda c: c["conditions"][0].update(storage_order="permuted"), "canonical and one permuted"),
        (lambda c: c["conditions"].pop(), "canonical and one permuted"),
    ],
)
def test_validator_rejects_protocol_drift(mutate, message):
    config = _v1g_config()
    mutate(config)
    with pytest.raises(ValueError, match=message):
        v1g.validate_v1g_config(config, reference=_reference(), expected_seeds=_seeds())


def _row(seed: int, order: str, run_id: str, **metrics) -> dict:
    row = {"run_id": run_id, "seed": seed, "storage_order": order, "stationarity_pass": True}
    row.update(metrics)
    return row


def _spec(seed: int, order: str) -> dict:
    return {"run_id": f"seed-{seed}--order-{order}", "seed": seed, "storage_order": order}


def test_paired_bound_matches_the_frozen_ceiling_rule():
    limits = {metric: 0.01 for metric in v1g.CALIBRATION_METRICS}
    seeds = [1, 2, 3, 4]
    specs = [_spec(seed, order) for order in ("canonical", "permuted") for seed in seeds]

    identical = [
        _row(seed, order, f"seed-{seed}--{order}", **{m: 0.25 for m in v1g.CALIBRATION_METRICS})
        for order in ("canonical", "permuted")
        for seed in seeds
    ]
    result = v1g.paired_order_bound(identical, specs, limits=limits)
    assert result["pass"] is True
    assert all(
        entry["bound"]["two_se_bound"] == 0.0 for entry in result["by_metric"].values()
    )

    shifted = []
    for index, (row, spec) in enumerate(zip(identical, specs)):
        row = dict(row)
        row["wealth_gini"] = 0.25 + (0.5 if spec["storage_order"] == "permuted" else 0.0)
        shifted.append(row)
    result = v1g.paired_order_bound(shifted, specs, limits=limits)
    assert result["pass"] is False
    assert result["by_metric"]["wealth_gini"]["bounded"] is False
    # The other three metrics did not move, so the verdict is per metric, not global.
    assert result["by_metric"]["occupancy_entropy"]["bounded"] is True


def test_paired_bound_requires_matched_seed_sets():
    limits = {metric: 0.01 for metric in v1g.CALIBRATION_METRICS}
    canonical = [_spec(seed, "canonical") for seed in (1, 2, 3)]
    permuted = [_spec(seed, "permuted") for seed in (1, 2, 4)]
    specs = canonical + permuted
    rows = [
        _row(spec["seed"], spec["storage_order"], spec["run_id"], **{m: 0.1 for m in v1g.CALIBRATION_METRICS})
        for spec in specs
    ]
    with pytest.raises(ValueError, match="same seed set"):
        v1g.paired_order_bound(rows, specs, limits=limits)

    duplicate = canonical + [_spec(1, "canonical")] + permuted
    rows = [
        _row(spec["seed"], spec["storage_order"], spec["run_id"] + f"-{index}", **{m: 0.1 for m in v1g.CALIBRATION_METRICS})
        for index, spec in enumerate(duplicate)
    ]
    with pytest.raises(ValueError, match="duplicate canonical replicate"):
        v1g.paired_order_bound(rows, duplicate, limits=limits)


def test_probe_inputs_are_one_physical_state_in_two_row_orders(tmp_path, monkeypatch):
    """The comparison is only meaningful if both orders share the same state."""
    monkeypatch.setattr(sys.modules["run_landscape_study"], "PROJECT_ROOT", tmp_path)
    config = _v1g_config()
    specs = sys.modules["run_landscape_study"].prepare_inputs(v1g.EXPERIMENT_ID, config, tmp_path)

    assert len(specs) == 2 * len(_seeds())
    by_key = {(int(spec["seed"]), str(spec["storage_order"])): spec for spec in specs}
    assert len(by_key) == len(specs)
    for seed in _seeds():
        canonical = by_key[(seed, "canonical")]
        permuted = by_key[(seed, "permuted")]
        assert canonical["initial_conditions"] != permuted["initial_conditions"]
        assert canonical["initial_conditions_sha256"] != permuted["initial_conditions_sha256"]

        canonical_rows = (
            sys.modules["run_landscape_study"]
            .project_path(canonical["initial_conditions"])
            .read_text(encoding="utf-8")
            .splitlines()
        )
        permuted_rows = (
            sys.modules["run_landscape_study"]
            .project_path(permuted["initial_conditions"])
            .read_text(encoding="utf-8")
            .splitlines()
        )
        # Same physical state: identical header and identical row multiset...
        assert canonical_rows[0] == permuted_rows[0]
        assert sorted(canonical_rows[1:]) == sorted(permuted_rows[1:])
        # ...and the permutation is real, so the probe is not vacuous. Permuting
        # rows alone can leave a 64-row-independent ordering fixed by chance, but
        # not for every one of the 64 seeds.
        if canonical_rows[1:] != permuted_rows[1:]:
            break
    else:  # pragma: no cover - would mean the permuted ICs are canonical
        raise AssertionError("no seed produced a different row order")

    cfg = (
        sys.modules["run_landscape_study"]
        .project_path(by_key[(_seeds()[0], "canonical")]["cpp_config"])
        .read_text(encoding="utf-8")
    )
    assert "temperature = 0.5" in cfg
    assert "confirmative_mode = true" in cfg
    assert "exchange_enabled = true" in cfg
