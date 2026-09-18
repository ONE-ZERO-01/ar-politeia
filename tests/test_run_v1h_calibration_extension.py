"""V1H: the calibration extension must be a re-derivation, not a restatement.

The tests below need no simulator and no retained V1F data: they build a table with
the same shape as ``replicate_metrics.csv`` and a frozen calibration derived from
it, then check that V1H refuses to publish anything except a bit-for-bit
reproduction, and that the Cycle 4 loader only accepts an extension bound to its
source.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import pytest


EXPERIMENTS = Path(__file__).parents[1] / "research" / "src" / "experiments"
sys.path.insert(0, str(EXPERIMENTS))


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, EXPERIMENTS / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


run_v1h = _load("run_v1h_calibration_extension")
run_landscape_study = _load("run_landscape_study")

TIMESTEPS = (0.02, 0.01, 0.005)
METRICS = list(run_v1h.CALIBRATION_METRICS)
EXTENSION = "wealth_variance"
SCALE = {**{metric: index + 1 for index, metric in enumerate(METRICS)}, EXTENSION: 3.0}


def _value(metric: str, landscape: str, seed: int, dt: float, *, divergent: bool) -> float:
    """A deterministic stand-in for one run's tail-window metric value.

    The ``dt`` term makes the frozen limits non-zero and convergent: a linear dt
    dependence gives an exactly constant paired difference, so its sd is 0 and the
    bound is the mean difference itself. ``divergent`` instead makes the metric grow
    like 1/dt^2, which no refinement keeps up with -- exactly what the ceiling-free
    trend criterion exists to catch.
    """
    base = {"smooth": 0.10, "clustered": 0.30, "shuffled": 0.20}[landscape]
    scale = SCALE[metric]
    shared = base * scale + seed * 0.001 * scale
    if divergent:
        return shared + 1000.0 * scale / (dt * dt)
    return shared + 5.0 * scale * dt


def _rows(*, seeds: int = 6, divergent_metric: str | None = None):
    tracked = [*METRICS, EXTENSION]
    rows = []
    for landscape in ("smooth", "clustered", "shuffled"):
        for dt in TIMESTEPS:
            for seed in range(seeds):
                row = {
                    "calibration_component": "timestep",
                    "landscape": landscape,
                    "dt": dt,
                    "seed": seed,
                    "storage_order": "",
                    "condition": f"{landscape}-dt-{dt}",
                    "run_id": f"seed-{seed}--{landscape}-dt-{dt}",
                }
                for metric in tracked:
                    row[metric] = _value(
                        metric, landscape, seed, dt, divergent=metric == divergent_metric
                    )
                rows.append(row)
    # One storage-order pair at every timestep, in a single landscape.
    for dt in TIMESTEPS:
        for seed in range(seeds):
            for order in ("canonical", "permuted"):
                row = {
                    "calibration_component": "order",
                    "landscape": "clustered",
                    "dt": dt,
                    "seed": seed,
                    "storage_order": order,
                    "condition": f"order-{order}-dt-{dt}",
                    "run_id": f"seed-{seed}--order-{order}-dt-{dt}",
                }
                for metric in tracked:
                    row[metric] = _value(metric, "clustered", seed, dt, divergent=False)
                if order == "permuted":
                    # The offset grows as dt coarsens, so "the finest timestep's
                    # bound" and "the largest bound across timesteps" disagree --
                    # which is what pins V1F's rule in the test below.
                    row[EXTENSION] += 0.25 + (dt - TIMESTEPS[-1])
                rows.append(row)
    return rows


def _frozen(rows):
    """A frozen calibration shaped like V1F's, derived from the same table."""
    computed = run_v1h.recompute_layer_bounds(
        rows, timesteps=TIMESTEPS, metrics=[*METRICS, EXTENSION]
    )
    limits = run_v1h.derived_limits(computed, metrics=[*METRICS, EXTENSION])
    return {
        "experiment": run_v1h.SOURCE_EXPERIMENT,
        "pass": True,
        "discretization": computed["discretization"],
        "storage_order_sensitivity": {
            metric: {"by_dt": by_dt}
            for metric, by_dt in computed["storage_order"].items()
            if metric in METRICS
        },
        "numerical_resolution_limits": {metric: limits[metric] for metric in METRICS},
    }


def _config(**overrides):
    config = {
        "extension_metrics": [EXTENSION],
        "timesteps": list(TIMESTEPS),
        # Recorded by build_extension, verified only by main(); the tests exercise
        # the derivation, so plausible bindings are enough here.
        "source_calibration_sha256": "b" * 64,
        "source_replicate_metrics_sha256": "c" * 64,
        "source_calibration": f"research/jobs/{run_v1h.SOURCE_EXPERIMENT}/numerical_calibration.json",
        "source_replicate_metrics": (
            f"research/jobs/{run_v1h.SOURCE_EXPERIMENT}/workspace/replicate_metrics.csv"
        ),
    }
    config.update(overrides)
    return config


def test_v1h_reproduces_every_frozen_limit_and_extends_the_retained_metric():
    rows = _rows()
    frozen = _frozen(rows)
    payload = run_v1h.build_extension(_config(), rows, frozen)

    assert payload["pass"] is True
    assert payload["faithfulness"]["field_mismatches"] == 0
    assert set(payload["faithfulness"]["reproduced_limits"]) == set(METRICS)
    for entry in payload["faithfulness"]["reproduced_limits"].values():
        assert entry["bit_equal"] is True
        assert entry["recomputed"] == entry["frozen"]
    # The extension must be a strict superset: the old limits are carried, and the
    # new metric's limit is the same rule applied to the same table.
    assert payload["numerical_resolution_limits"]["wealth_gini"] == (
        frozen["numerical_resolution_limits"]["wealth_gini"]
    )
    assert payload["numerical_resolution_limits"]["wealth_variance"] == (
        run_v1h.derived_limits(
            run_v1h.recompute_layer_bounds(
                rows, timesteps=TIMESTEPS, metrics=[*METRICS, "wealth_variance"]
            ),
            metrics=[*METRICS, "wealth_variance"],
        )["wealth_variance"]
    )


def test_v1h_takes_the_order_leg_at_the_finest_timestep_only():
    """V1F's limit uses the finest bound; a max across timesteps is a different number."""
    computed = run_v1h.recompute_layer_bounds(
        _rows(), timesteps=TIMESTEPS, metrics=[*METRICS, EXTENSION]
    )
    by_dt = computed["storage_order"][EXTENSION]
    coarse = by_dt[f"{TIMESTEPS[0]:.17g}"]["two_se_bound"]
    finest = by_dt[f"{TIMESTEPS[-1]:.17g}"]["two_se_bound"]
    assert coarse > finest, "the fixture must make the two rules disagree"

    limits = run_v1h.derived_limits(computed, metrics=[*METRICS, EXTENSION])
    assert limits[EXTENSION] == finest
    assert limits[EXTENSION] != coarse


def test_v1h_refuses_a_single_field_that_does_not_reproduce():
    """Mutation: one flipped float anywhere in the frozen record must fail the run."""
    rows = _rows()
    frozen = _frozen(rows)
    frozen["discretization"]["clustered"]["wealth_gini"]["fine_vs_finest"][
        "two_se_bound"
    ] = 0.123
    with pytest.raises(RuntimeError, match="does not reproduce"):
        run_v1h.build_extension(_config(), rows, frozen)


def test_v1h_refuses_a_frozen_limit_that_differs_from_the_recomputed_one():
    """A limit can agree field-by-field and still be overwritten in the summary."""
    rows = _rows()
    frozen = _frozen(rows)
    frozen["numerical_resolution_limits"]["density_morans_i"] = 0.999
    with pytest.raises(RuntimeError, match="!= frozen"):
        run_v1h.build_extension(_config(), rows, frozen)


def test_v1h_refuses_a_metric_the_retained_table_does_not_carry():
    """Requesting an absent column must fail loudly, not silently drop the metric."""
    with pytest.raises(RuntimeError, match="no column for \\['mean_wealth'\\]"):
        run_v1h.build_extension(
            _config(extension_metrics=["mean_wealth"]), _rows(), _frozen(_rows())
        )


def test_v1h_refuses_to_re_freeze_an_already_frozen_metric():
    with pytest.raises(ValueError, match="already frozen"):
        run_v1h.build_extension(
            _config(extension_metrics=["wealth_gini"]), _rows(), _frozen(_rows())
        )


def test_v1h_does_not_invent_a_ceiling_for_the_extended_metric():
    payload = run_v1h.build_extension(_config(), _rows(), _frozen(_rows()))
    extension = payload["extensions"]["wealth_variance"]
    assert extension["ceiling"] is None
    # Not merely absent: it must also not read as a pass. A null that renders as
    # True is a threshold nobody registered.
    assert extension["ceiling_pass"] is None
    assert "pre-registered" in extension["ceiling_policy"]
    assert payload["extension_metrics"] == ["wealth_variance"]


def test_v1h_records_why_mean_wealth_was_left_out():
    payload = run_v1h.build_extension(_config(), _rows(), _frozen(_rows()))
    reason = payload["out_of_scope"]["mean_wealth"]
    assert "replicate_metrics.csv" in reason
    assert "audit" in reason


def test_v1h_extension_verdict_follows_the_metric_not_the_extension_set():
    """Mutation: the same table, one divergent metric -- the verdict must flip."""
    passing = run_v1h.build_extension(_config(), _rows(), _frozen(_rows()))
    assert passing["extensions"]["wealth_variance"]["discretization_trend_pass"] is True

    rows = _rows(divergent_metric="wealth_variance")
    failing = run_v1h.build_extension(_config(), rows, _frozen(rows))
    assert failing["extensions"]["wealth_variance"]["discretization_trend_pass"] is False
    assert failing["extensions"]["wealth_variance"]["pass"] is False
    assert failing["pass"] is False
    # The frozen limits still reproduce: only the extension's verdict moved.
    assert failing["faithfulness"]["field_mismatches"] == 0


def test_v1h_refuses_a_table_whose_order_layer_spans_two_landscapes():
    rows = _rows()
    for row in rows:
        if row["calibration_component"] == "order" and row["seed"] == 0:
            row["landscape"] = "smooth"
    with pytest.raises(RuntimeError, match="spans landscapes"):
        run_v1h.recompute_layer_bounds(
            rows, timesteps=TIMESTEPS, metrics=[*METRICS, "wealth_variance"]
        )


# ── the loader only accepts an extension bound to its source ───────────


def _extension_payload(*, clean: bool = True):
    payload = run_v1h.build_extension(_config(), _rows(), _frozen(_rows()))
    payload["extends"] = {
        "experiment": run_v1h.SOURCE_EXPERIMENT,
        "sha256": "a" * 64,
        "path": "research/jobs/V1F-NONFLAT-CALIBRATION-C4/numerical_calibration.json",
    }
    if not clean:
        payload["faithfulness"]["field_mismatches"] = 1
    return payload


def test_loader_accepts_v1f_itself():
    run_landscape_study._require_cycle4_calibration_identity(
        {"experiment": run_v1h.SOURCE_EXPERIMENT}
    )


def test_loader_accepts_a_faithful_extension():
    run_landscape_study._require_cycle4_calibration_identity(_extension_payload())


def test_loader_rejects_an_unrelated_experiment():
    with pytest.raises(RuntimeError, match="requires V1F-NONFLAT-CALIBRATION-C4"):
        run_landscape_study._require_cycle4_calibration_identity(
            {"experiment": "V1E-NONFLAT-CALIBRATION-C4"}
        )


def test_loader_rejects_an_extension_that_names_no_source():
    payload = _extension_payload()
    del payload["extends"]
    with pytest.raises(RuntimeError, match="does not declare the artifact it extends"):
        run_landscape_study._require_cycle4_calibration_identity(payload)


def test_loader_rejects_an_extension_without_a_source_hash():
    payload = _extension_payload()
    payload["extends"]["sha256"] = "not-a-hash"
    with pytest.raises(RuntimeError, match="64-character sha256"):
        run_landscape_study._require_cycle4_calibration_identity(payload)


def test_loader_rejects_an_extension_that_admits_a_mismatch():
    with pytest.raises(RuntimeError, match="did not reproduce its source"):
        run_landscape_study._require_cycle4_calibration_identity(_extension_payload(clean=False))


def test_loader_rejects_an_extension_whose_limits_contradict_its_own_faithfulness_block():
    payload = _extension_payload()
    payload["numerical_resolution_limits"]["wealth_gini"] = 0.5
    with pytest.raises(RuntimeError, match="disagrees with its own faithfulness block"):
        run_landscape_study._require_cycle4_calibration_identity(payload)


def test_loader_rejects_an_extension_that_did_not_reproduce_a_metric_exactly():
    payload = _extension_payload()
    payload["faithfulness"]["reproduced_limits"]["density_morans_i"]["bit_equal"] = False
    with pytest.raises(RuntimeError, match="did not reproduce density_morans_i"):
        run_landscape_study._require_cycle4_calibration_identity(payload)
