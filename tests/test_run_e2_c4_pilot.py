"""E2-C4 pilot readiness: read spread and levels, never a direction.

The pilot's whole value is that it is *non-evidentiary*: it sizes the
confirmatory replicate count from this experiment's own variance without ever
reading an effect. That property cannot be checked after the fact, so this module
checks it where it is decided:

1. the probe cannot leave the reference protocol, the frozen seed window or the
   frozen battery -- all three are cross-checked against the tracked reference
   config, the seeds ledger and a duplicated unit table, and every guard fails
   fast;
2. the report cannot contain difference vocabulary -- checked structurally over an
   assembled report, not by reading one;
3. the replicate requirement really is the frozen rules' own arithmetic -- the
   SESOI term is checked against V1ED's helper and hand arithmetic, and the steady
   terms are checked as fixed points of the shared predicates they were solved
   from, so a bounded R is bounded against the criteria the confirmatory run is
   actually gated on.

Everything here is static or writes only into ``tmp_path``.
"""

from __future__ import annotations

import importlib.util
import json
import math
from pathlib import Path
import sys

import numpy as np
import pytest
from scipy.stats import chi2

REPO_ROOT = Path(__file__).parents[1]
PILOT_CONFIG = "research/jobs/E2-C4-PILOT/config.json"
REFERENCE_CONFIG = "research/jobs/E1-MATCHED-LANDSCAPES-C4/config.json"
PARAMETER_LOCK = "research/parameter_lock.cycle4.json"

EXPERIMENTS_DIR = REPO_ROOT / "research" / "src" / "experiments"
sys.path.insert(0, str(EXPERIMENTS_DIR))
for name in (
    "landscape_study",
    "run_landscape_study",
    "run_v1_calibration",
    "run_v1e_sampling_diagnostic",
    "prepare_cycle4_confirmation",
    "run_e2_c4_pilot",
):
    spec = importlib.util.spec_from_file_location(name, EXPERIMENTS_DIR / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)

pilot = sys.modules["run_e2_c4_pilot"]
study = sys.modules["run_landscape_study"]
v1ed = sys.modules["run_v1e_sampling_diagnostic"]


def _pilot_config() -> dict:
    return json.loads((REPO_ROOT / PILOT_CONFIG).read_text(encoding="utf-8"))


def _lock() -> dict:
    return json.loads((REPO_ROOT / PARAMETER_LOCK).read_text(encoding="utf-8"))


def _spec(seed: int, unit: tuple) -> dict:
    name, landscape, decay, base = unit
    return {
        "run_id": f"seed-{seed}--{name}",
        "seed": seed,
        "condition": name,
        "landscape": landscape,
        "wealth_decay_rate": decay,
        "base_production": base,
    }


def _specs(unit_table=None) -> list[dict]:
    return [
        _spec(seed, unit)
        for unit in (unit_table or study.E2_C4_UNITS)
        for seed in pilot.FROZEN_PILOT_SEEDS
    ]


def _series(mean: float, sample_sd: float, n: int) -> np.ndarray:
    """``n`` values with exactly this mean and sample SD (n-1 denominator)."""
    values = np.arange(n, dtype=np.float64)
    values -= values.mean()
    values /= np.std(values, ddof=1)
    return values * sample_sd + mean


def _rows(specs: list[dict], *, variance: float | None = None) -> list[dict]:
    """Deterministic rows with per-unit structure and no directional reading.

    ``density_morans_i`` and ``occupancy_entropy`` vary with the *seed only*, which
    is what the P1 identity guard asserts: with positions exogenous to every
    wealth-family factor they must be bitwise equal across source patterns.
    """
    rows = []
    for spec in specs:
        unit_index = [u[0] for u in study.E2_C4_UNITS].index(spec["condition"])
        # Seed-only for the position metrics (they must be identical across source
        # patterns), and seed x unit for the wealth metrics, so a contrast between
        # two units is not a constant.
        jitter = (spec["seed"] % 11) / 1000.0
        spread = (spec["seed"] % 11) * (unit_index + 1) / 1000.0
        rows.append(
            {
                "run_id": spec["run_id"],
                "seed": spec["seed"],
                "condition": spec["condition"],
                "stationarity_pass": True,
                "density_morans_i": 0.3 + jitter / 10.0,
                "occupancy_entropy": 4.0 + jitter / 10.0,
                "wealth_gini": 0.5 + unit_index / 100.0 + spread / 100.0,
                "wealth_variance": (
                    (1.0 + unit_index + spread) if variance is None else variance
                ),
                "zero_wealth_fraction": 0.001 * (1 + unit_index) + spread / 1000.0,
                "mean_wealth": 0.5 + unit_index / 1000.0 + spread / 1000.0,
                # Real analyser rows always carry both of these; the P4 gate reads
                # the observed one and falls back to the raw one.
                "minimum_wealth": 0.0,
                "minimum_wealth_observed": 0.0,
            }
        )
    return rows


def _by_seed(rows) -> dict:
    by_seed: dict[int, dict[str, dict]] = {}
    for row in rows:
        by_seed.setdefault(int(row["seed"]), {})[str(row["condition"])] = row
    return by_seed


def _comparability(rows) -> dict:
    return study._e2_c4_comparability(_by_seed(rows), _pilot_config())


# ── 1. protocol, unit battery, binary and seed guards ──


def test_frozen_protocol_matches_the_reference_config():
    reference = pilot.reference_protocol(REPO_ROOT)
    tracked = json.loads((REPO_ROOT / REFERENCE_CONFIG).read_text(encoding="utf-8"))
    # The only frozen key the reference config does not declare is the ability
    # saturation scale, so that is the only one whose cross-check has to come from
    # the config builder instead; if another key ever stops being compared, this
    # fails rather than silently dropping out of the guard.
    assert set(reference) == set(pilot.FROZEN_PROTOCOL) - {"ability_saturation_w"}
    assert reference == {key: tracked[key] for key in reference}
    assert (
        study.common_cpp_config(tracked)["ability_saturation_w"]
        == pilot.FROZEN_PROTOCOL["ability_saturation_w"]
    )
    assert study.common_cpp_config(_pilot_config())["ability_saturation_w"] == 5.0


def test_frozen_unit_table_matches_the_shared_table():
    # The duplicated freezer must stay a copy of the battery, or the guard below
    # would enforce a battery nobody declared.
    assert pilot.FROZEN_UNIT_TABLE == study.E2_C4_UNITS
    assert tuple(pilot.FROZEN_UNIT_TABLE) == tuple(pilot.E2_C4_UNITS)


def test_pilot_config_is_accepted():
    config = _pilot_config()
    assert config["experiment_id"] == pilot.EXPERIMENT_ID == "E2-C4-PILOT"
    pilot.require_protocol_match(config, pilot.reference_protocol(REPO_ROOT))
    pilot.require_locked_binary(config, _lock())
    assert config["seeds"] == list(pilot.FROZEN_PILOT_SEEDS)
    # The steady contract must cover exactly E2-C4's metric set: a stray bound
    # would be rejected by the shared validator at run time.
    study._validate_c4_steady_contract(config, pilot.EXPERIMENT_ID)
    # The pilot's config must prepare the frozen battery, not a fallback one.
    assert [
        condition["name"]
        for condition in study.default_conditions(pilot.EXPERIMENT_ID, config)
    ] == [name for name, *_rest in pilot.FROZEN_UNIT_TABLE]


@pytest.mark.parametrize(
    "mutate, message",
    [
        (lambda c: c.update(temperature=0.0), "frozen protocol"),
        (lambda c: c.update(dt=0.01), "frozen protocol"),
        (lambda c: c.update(total_time=1500.0), "frozen protocol"),
        (lambda c: c.update(steady_snapshots=48), "frozen protocol"),
        (lambda c: c.update(population=2000), "frozen protocol"),
        (lambda c: c.update(grid_shape=[128, 128]), "frozen protocol"),
        (lambda c: c.update(social_strength=0.5), "frozen protocol"),
        (lambda c: c.update(exchange_rate=0.25), "frozen protocol"),
        (lambda c: c.pop("friction"), "must pin friction"),
    ],
)
def test_protocol_drift_in_the_config_is_refused(mutate, message):
    config = _pilot_config()
    mutate(config)
    with pytest.raises(ValueError, match=message):
        pilot.require_protocol_match(config, pilot.reference_protocol(REPO_ROOT))


def test_protocol_drift_in_the_reference_is_refused():
    reference = pilot.reference_protocol(REPO_ROOT)
    reference["temperature"] = 1.0
    with pytest.raises(ValueError, match="protocol drift"):
        pilot.require_protocol_match(_pilot_config(), reference)


def test_binary_binding_is_refused_when_the_lock_or_binary_moves():
    lock = _lock()
    lock["numerical_calibration"]["reference_binary_sha256"] = "0" * 64
    with pytest.raises(RuntimeError, match="calibrated reference binary"):
        pilot.require_locked_binary(_pilot_config(), lock)

    other = _pilot_config()
    other["parameter_lock"] = "research/parameter_lock.json"
    with pytest.raises(RuntimeError, match="must bind"):
        pilot.require_locked_binary(other, _lock())


def test_frozen_seeds_are_accepted():
    pilot.require_frozen_seeds(pilot.FROZEN_PILOT_SEEDS, consumed_by_others=[1, 2, 3])


@pytest.mark.parametrize(
    "mutate, message",
    [
        (lambda s: s[:-1] + [99991], "frozen at"),
        (lambda s: s[:-1] + [s[0]], "frozen at"),
        (lambda s: s[:-1] + [12279], "frozen at"),
        (lambda s: s[:-1] + [12307], "frozen at"),
    ],
)
def test_seed_guard_refuses_anything_but_the_frozen_eight(mutate, message):
    seeds = mutate(list(pilot.FROZEN_PILOT_SEEDS))
    assert seeds != list(pilot.FROZEN_PILOT_SEEDS)
    with pytest.raises(ValueError, match=message):
        pilot.require_frozen_seeds(seeds, consumed_by_others=[])


def test_seed_guard_refuses_seeds_another_job_already_consumed():
    with pytest.raises(ValueError, match="already consumed"):
        pilot.require_frozen_seeds(pilot.FROZEN_PILOT_SEEDS, consumed_by_others=[12347])


def test_seed_guard_refuses_a_composite_or_out_of_window_frozen_seed(monkeypatch):
    # A mutation of the frozen tuple itself: 12307 is inside the window but
    # composite, so the prime check is exercised rather than assumed.
    monkeypatch.setattr(
        pilot, "FROZEN_PILOT_SEEDS", (12307, *pilot.FROZEN_PILOT_SEEDS[1:])
    )
    with pytest.raises(ValueError, match="not prime"):
        pilot.require_frozen_seeds(pilot.FROZEN_PILOT_SEEDS, consumed_by_others=[])


def test_frozen_seeds_are_the_smallest_unused_primes_in_the_window():
    """The design's derivation, recomputed from the ledger rather than trusted.

    The pilot's own declaration is excluded by ``ledger_seed_partition`` (a job
    cannot reuse its own seeds), so this stays true after the job dir exists.
    """
    partition = pilot.ledger_seed_partition(REPO_ROOT)
    available = pilot.window_pool(partition["others"])
    assert available[: pilot.PILOT_SEED_COUNT] == list(pilot.FROZEN_PILOT_SEEDS)
    # The window must cover the pilot plus the whole confirmatory battery, and both
    # must have been drawn as the *smallest* free primes: the pilot took the first
    # eight, so the confirmatory declaration must be the next sixteen. That used to
    # be written as a flat 64 because R was expected to be E1-C4's; R was then
    # derived from this pilot's own dispersion and frozen at 16 (pilot design
    # section 4 erratum), so the requirement is read from the recorded derivation
    # instead of guessed.
    requirement = json.loads(
        (
            REPO_ROOT / "research" / "jobs" / pilot.EXPERIMENT_ID / "r_requirement.json"
        ).read_text(encoding="utf-8")
    )
    assert len(available) >= requirement["r_replicates"]
    declared = REPO_ROOT / "research" / "jobs" / "E2-CHANNEL-ABLATION-C4" / "seeds.txt"
    if declared.is_file():
        confirmatory = [
            int(token) for token in declared.read_text(encoding="utf-8").split() if token
        ]
        assert len(confirmatory) == requirement["r_replicates"]
        window_primes = pilot.window_pool(())
        assert sorted(list(pilot.FROZEN_PILOT_SEEDS) + confirmatory) == window_primes[
            : pilot.PILOT_SEED_COUNT + len(confirmatory)
        ]


# ── 2. the battery ──


def test_units_match_the_frozen_table():
    pilot.require_frozen_units(_specs())


@pytest.mark.parametrize(
    "mutate, message",
    [
        (
            lambda specs: [
                s.update(base_production=0.02)
                for s in specs
                if s["condition"] == "clustered-d0.02"
            ],
            "frozen battery pins",
        ),
        (
            lambda specs: [
                s.update(wealth_decay_rate=0.05)
                for s in specs
                if s["condition"] == "clustered-d0.04"
            ],
            "frozen battery pins",
        ),
        (
            lambda specs: [
                s.update(landscape="flat") for s in specs if s["condition"] == "shuffled-d0.02"
            ],
            "frozen battery pins",
        ),
        (
            lambda specs: specs.__setitem__(
                slice(None), [s for s in specs if s["condition"] != "shuffled-d0.02"]
            ),
            "frozen units",
        ),
        (lambda specs: specs.pop(), "distinct seeds"),
    ],
)
def test_unit_mutations_are_refused(mutate, message):
    specs = _specs()
    mutate(specs)
    with pytest.raises(ValueError, match=message):
        pilot.require_frozen_units(specs)


def test_a_unit_carrying_two_different_batteries_is_refused():
    # A per-seed inconsistency inside one unit: prepared inputs must not describe
    # one unit two ways, or the sample SD would mix two batteries.
    specs = _specs()
    specs[0]["base_production"] = 0.02
    with pytest.raises(ValueError, match="two different"):
        pilot.require_frozen_units(specs)


def test_a_truncated_unit_is_refused_even_when_the_names_survive():
    specs = [
        spec
        for spec in _specs()
        if not (spec["condition"] == "flat-d0.02" and spec["seed"] == 12379)
    ]
    with pytest.raises(ValueError, match="distinct seeds"):
        pilot.require_frozen_units(specs)


def test_a_mutated_unit_table_is_refused_by_the_prepared_inputs(tmp_path, monkeypatch):
    """Change a unit in the shared table and the pilot must stop before running.

    The unit table is code, not config, so this is the only mutation that can move
    the battery without moving the config -- and it must be caught by comparing the
    prepared specs, not by trusting that both sides read the same table.
    """
    monkeypatch.setattr(study, "PROJECT_ROOT", tmp_path)
    config = _pilot_config()
    specs = study.prepare_inputs(pilot.EXPERIMENT_ID, config, tmp_path)
    assert len(specs) == len(pilot.FROZEN_UNIT_TABLE) * pilot.PILOT_SEED_COUNT
    pilot.require_frozen_units(specs)

    drifted_table = tuple(
        (name, landscape, decay, base * 2.0)
        for name, landscape, decay, base in study.E2_C4_UNITS
    )
    monkeypatch.setattr(study, "E2_C4_UNITS", drifted_table)
    drifted_specs = study.prepare_inputs(pilot.EXPERIMENT_ID, config, tmp_path)
    with pytest.raises(ValueError, match="frozen battery pins"):
        pilot.require_frozen_units(drifted_specs)


# ── 3. dispersion ──


def test_paired_dispersion_matches_hand_calculation():
    entry = pilot.paired_dispersion(
        {1: 2.0, 2: 3.5, 3: 4.0, 4: 8.0}, {1: 1.0, 2: 1.5, 3: 1.0, 4: 2.0}
    )
    differences = np.array([1.0, 2.0, 3.0, 6.0])
    expected_sd = float(np.std(differences, ddof=1))
    assert entry["paired_sample_sd"] == pytest.approx(expected_sd)
    # The n-1 denominator is the point: the n denominator would shrink the SD and
    # under-size every replicate requirement derived from it.
    assert entry["paired_sample_sd"] != pytest.approx(float(np.std(differences, ddof=0)))
    factor = math.sqrt(3.0 / float(chi2.ppf(pilot.UPPER_SD_ALPHA, 3)))
    assert factor > 1.0
    assert entry["upper_sample_sd"] == pytest.approx(expected_sd * factor)
    # No contrast mean is reported anywhere in the entry.
    assert not any("mean" in key for key in entry)


def test_paired_dispersion_refuses_unpaired_short_or_degenerate_inputs():
    with pytest.raises(ValueError, match="same seed set"):
        pilot.paired_dispersion({1: 1.0, 2: 2.0, 3: 3.0}, {1: 1.0, 2: 2.0, 4: 3.0})
    with pytest.raises(ValueError, match="three paired replicates"):
        pilot.paired_dispersion({1: 1.0, 2: 2.0}, {1: 1.0, 2: 2.0})
    with pytest.raises(ValueError, match="non-finite"):
        pilot.paired_dispersion(
            {1: 1.0, 2: float("nan"), 3: 3.0}, {1: 1.0, 2: 2.0, 3: 3.0}
        )


def test_pilot_dispersion_covers_every_frozen_contrast_and_metric():
    specs = _specs()
    rows = _rows(specs)
    dispersion = pilot.pilot_dispersion(rows, specs)
    assert set(dispersion["contrasts"]) == {
        contrast["label"] for contrast in pilot.PILOT_CONTRASTS
    }
    assert {c["claim_bearing"] for c in dispersion["contrasts"].values()} == {
        True,
        False,
    }
    for contrast in dispersion["contrasts"].values():
        assert set(contrast["metrics"]) == set(study.E2_C4_EFFECT_METRICS)
        for entry in contrast["metrics"].values():
            assert entry["replicates"] == pilot.PILOT_SEED_COUNT
            assert entry["paired_sample_sd"] > 0.0
    # A duplicated run would silently shrink the sample; it is refused.
    with pytest.raises(RuntimeError, match="duplicate run"):
        pilot.pilot_dispersion([*rows, rows[0]], specs)


def test_pilot_dispersion_refuses_a_seed_set_that_drifted_from_the_spec():
    specs = _specs()
    rows = [row for row in _rows(specs) if row["seed"] != pilot.FROZEN_PILOT_SEEDS[0]]
    with pytest.raises(RuntimeError, match="different seed set"):
        pilot.pilot_dispersion(rows, specs)


# ── 4. the report cannot contain a direction ──


def _report(identity=None) -> dict:
    specs = _specs()
    rows = _rows(specs)
    by_seed = _by_seed(rows)
    return pilot.build_pilot_report(
        config=_pilot_config(),
        config_path=str(REPO_ROOT / PILOT_CONFIG),
        execution={"executed": len(specs)},
        identity=identity or study.e2_c4_identity_report(by_seed),
        comparability=_comparability(rows),
        dispersion=pilot.pilot_dispersion(rows, specs),
        reference_variance=pilot.wealth_variance_reference(by_seed),
        steady_report={
            "pass": False,
            "tail_stationarity_valid": True,
            "adjacent_window_stability_valid": False,
            "independent_replicate_precision_valid": False,
        },
        steady_report_sha256="f" * 64,
        rows=rows,
    )


def test_assembled_report_has_no_contrast_vocabulary():
    report = _report()
    pilot.assert_no_contrast_effects(report)
    assert report["pass"] is True
    # Level readings are present and allowed; the prohibition is on differences.
    pattern_unit = study.E2_C4_PATTERN_UNITS[0]
    assert "mean_wealth" in report["P4_comparability"]["units"][pattern_unit]
    assert report["paired_dispersion"]["contrasts"]
    # The steady block is informational: the pilot's own pass must not depend on
    # predicates that are functions of the replicate count it is sizing.
    assert report["steady_contract_at_pilot_n"]["informational"] is True
    assert report["steady_contract_at_pilot_n"]["pass"] is False


def test_a_contrast_mean_anywhere_in_the_report_is_refused():
    report = _report()
    template = report["paired_dispersion"]["contrasts"]["clustered-minus-shuffled"][
        "metrics"
    ]["wealth_gini"]
    for leaked in (
        {"mean_difference": 0.1},
        {"ci95_low": -1.0},
        {"sign_flip_p_value": 0.5},
        {"direction": "up"},
    ):
        damaged = json.loads(json.dumps(report))
        damaged["paired_dispersion"]["contrasts"]["clustered-minus-shuffled"][
            "metrics"
        ]["wealth_gini"].update(leaked)
        assert set(damaged["paired_dispersion"]["contrasts"]["clustered-minus-shuffled"]["metrics"]["wealth_gini"]) > set(template)
        with pytest.raises(RuntimeError, match="contrast-effect fields"):
            pilot.assert_no_contrast_effects(damaged)


def test_report_is_refused_after_an_identity_violation(tmp_path):
    specs = _specs()
    rows = _rows(specs)
    by_seed = _by_seed(rows)
    # Flip one pure-position metric in one unit: the guard must see it.
    victim = by_seed[pilot.FROZEN_PILOT_SEEDS[0]][study.E2_C4_PATTERN_UNITS[1]]
    victim["occupancy_entropy"] = float(victim["occupancy_entropy"]) + 1.0
    identity = study.e2_c4_identity_report(by_seed)
    assert identity["pass"] is False
    assert identity["violations"][0]["metric"] == "occupancy_entropy"

    with pytest.raises(RuntimeError, match="P1 isolation identity failed"):
        pilot.require_identity_guard(
            identity, output_dir=tmp_path, experiment=pilot.EXPERIMENT_ID
        )
    # The violated comparison is left on disk, and no dispersion table exists.
    written = json.loads(
        (tmp_path / "isolation_identity_report.json").read_text(encoding="utf-8")
    )
    assert written["violations"]
    assert not (tmp_path / pilot.PILOT_REPORT_NAME).exists()

    with pytest.raises(RuntimeError, match="refusing to assemble"):
        _report(identity=identity)


def test_wealth_variance_reference_is_positive_and_resolves_by_dotted_path():
    rows = _rows(_specs())
    field = pilot.wealth_variance_reference(_by_seed(rows))
    value = field["P2_source_pattern"]["mean_wealth_variance"]
    units = field["P2_source_pattern"]["units"]
    assert set(units) == set(study.E2_C4_PATTERN_UNITS)
    assert value == pytest.approx(
        float(np.mean([entry["mean_wealth_variance"] for entry in units.values()]))
    )
    assert value > 0.0
    # The analyser binds this report by sha256 and reads this by dotted path; a
    # shape change here would break the derivation silently, so it is asserted.
    dotted = study.E2_C4_SESOI_REFERENCE_FIELDS["wealth_variance"]
    assert study._dotted_field({"wealth_variance_reference": field}, dotted) == value
    assert "not an effect size" in field["P2_source_pattern"]["role"]


def test_wealth_variance_reference_refuses_a_degenerate_level():
    rows = _rows(_specs(), variance=0.0)
    with pytest.raises(RuntimeError, match="finite positive"):
        pilot.wealth_variance_reference(_by_seed(rows))


# ── 5. the replicate requirement ──


def _pilot_report_for_derivation(
    *, paired_sd: float = 0.02, var_ref: float = 0.25
) -> dict:
    contrasts = {}
    for contrast in pilot.PILOT_CONTRASTS:
        contrasts[str(contrast["label"])] = {
            "claim_bearing": bool(contrast["claim_bearing"]),
            "treatment": contrast["treatment"],
            "control": contrast["control"],
            "metrics": {
                metric: {
                    "replicates": pilot.PILOT_SEED_COUNT,
                    "paired_sample_sd": paired_sd,
                    "upper_sd_alpha": pilot.UPPER_SD_ALPHA,
                    "upper_sample_sd": paired_sd
                    * pilot.upper_sd_factor(pilot.PILOT_SEED_COUNT),
                }
                for metric in study.E2_C4_EFFECT_METRICS
            },
        }
    return {
        "paired_dispersion": {"contrasts": contrasts},
        "wealth_variance_reference": {
            "P2_source_pattern": {"mean_wealth_variance": var_ref}
        },
    }


def _steady_report_for_derivation(
    *,
    tail_mean: float = 1.0,
    tail_sd: float = 0.05,
    difference_mean: float = 0.0,
    difference_sd: float = 0.005,
    relative_precision: float = 0.2,
    relative_adjacent: float = 0.1,
    n: int = pilot.PILOT_SEED_COUNT,
) -> dict:
    """A steady report built by the shared predicates themselves.

    Building it through ``_independent_precision_summary`` and
    ``_adjacent_window_summary`` means the derivation is exercised against the real
    report shape instead of a hand-written stand-in that could drift from it.
    """
    tail = _series(tail_mean, tail_sd, n)
    differences = _series(difference_mean, difference_sd, n)
    previous = tail - differences
    return {
        "conditions": {
            unit: {
                "condition": unit,
                "replicates": n,
                "metrics": {
                    metric: {
                        "independent_replicate_precision": study._independent_precision_summary(
                            tail, relative_half_width=relative_precision
                        ),
                        "adjacent_window_stability": study._adjacent_window_summary(
                            previous, tail, relative_bound=relative_adjacent
                        ),
                    }
                    for metric in study.stationary_metrics_for_experiment(
                        pilot.EXPERIMENT_ID
                    )
                },
            }
            for unit in study.E2_C4_UNIT_NAMES
        }
    }


def test_sesoi_requirement_is_v1ed_rule_arithmetic():
    report = _pilot_report_for_derivation(paired_sd=0.02, var_ref=0.25)
    requirements, delta_variance = pilot.sesoi_replicate_requirements(
        report,
        gini_delta=pilot.FROZEN_GINI_DELTA,
        variance_ratio=pilot.FROZEN_VARIANCE_RATIO,
    )
    assert delta_variance == pytest.approx(pilot.FROZEN_VARIANCE_RATIO * 0.25)
    # Two claim-bearing contrasts x two claim metrics; the reference contrast
    # carries no claim and contributes no requirement.
    assert {entry["contrast"] for entry in requirements} == {
        "clustered-minus-shuffled",
        "d0.04-minus-d0.01",
    }
    assert len(requirements) == 4
    for entry in requirements:
        expected = v1ed._required_replicates(
            sample_sd=0.02,
            threshold=entry["delta"],
            mean=None,
            bound_kind="absolute",
            current_replicates=pilot.PILOT_SEED_COUNT,
            upper_sd_alpha=pilot.UPPER_SD_ALPHA,
        )
        assert entry["required_replicates"] == expected["conservative_estimate"]
        upper_sd = 0.02 * pilot.upper_sd_factor(pilot.PILOT_SEED_COUNT)
        assert entry["required_replicates"] == max(
            pilot.MIN_REPLICATES, math.ceil((2.0 * upper_sd / entry["delta"]) ** 2)
        )


def _steady_requirement(steady: dict, unit: str, metric: str, constraint: str) -> dict:
    return next(
        item
        for item in pilot.steady_replicate_requirements(steady)
        if item["unit"] == unit
        and item["metric"] == metric
        and item["constraint"] == constraint
    )


def test_precision_requirement_is_a_fixed_point_of_the_shared_predicate():
    steady = _steady_report_for_derivation(tail_sd=0.12)
    unit, metric = study.E2_C4_UNIT_NAMES[0], "wealth_gini"
    entry = _steady_requirement(
        steady, unit, metric, "independent_replicate_precision"
    )
    block = steady["conditions"][unit]["metrics"][metric][
        "independent_replicate_precision"
    ]
    upper_sd = float(block["sample_sd"]) * pilot.upper_sd_factor(
        int(block["replicates"])
    )
    required = entry["required_replicates"]
    assert required > pilot.MIN_REPLICATES  # otherwise the n-1 check is vacuous

    def predicate(n: int) -> bool:
        return study._independent_precision_summary(
            _series(float(block["mean"]), upper_sd, n),
            relative_half_width=float(block["threshold"]),
        )["pass"]

    assert predicate(required) is True
    assert predicate(required - 1) is False


def test_adjacent_requirement_is_a_fixed_point_of_the_shared_predicate():
    steady = _steady_report_for_derivation(difference_mean=0.01, difference_sd=0.06)
    unit, metric = study.E2_C4_UNIT_NAMES[0], "wealth_gini"
    entry = _steady_requirement(steady, unit, metric, "adjacent_window_stability")
    block = steady["conditions"][unit]["metrics"][metric]["adjacent_window_stability"]
    tail_mean = float(steady["conditions"][unit]["metrics"][metric][
        "independent_replicate_precision"
    ]["mean"])
    drift = float(block["signed_mean_difference"])
    scale = max(abs(tail_mean), abs(tail_mean - drift))
    assert entry["resolved_bound"] == pytest.approx(
        float(block["threshold"]) * scale
    )
    assert entry["window_drift"] == pytest.approx(abs(drift))
    upper_sd = float(block["paired_sample_sd"]) * pilot.upper_sd_factor(
        int(block["replicates"])
    )
    required = entry["required_replicates"]
    assert required > pilot.MIN_REPLICATES

    def predicate(n: int) -> bool:
        tail = _series(tail_mean, upper_sd, n)
        return study._adjacent_window_summary(
            tail - _series(drift, upper_sd, n),
            tail,
            relative_bound=float(block["threshold"]),
        )["pass"]

    assert predicate(required) is True
    assert predicate(required - 1) is False


def test_derive_r_takes_the_maximum_and_rounds_up_to_a_power_of_two():
    derived = pilot.derive_r_replicates(
        _pilot_report_for_derivation(paired_sd=0.02, var_ref=0.25),
        _steady_report_for_derivation(tail_sd=0.12, difference_sd=0.06),
    )
    counts = [
        entry["required_replicates"]
        for family in derived["requirements"].values()
        for entry in family
    ]
    # Every family is represented, so a family cannot silently stop contributing.
    assert all(derived["requirements"][family] for family in derived["requirements"])
    assert derived["worst_required_replicates"] == max(counts)
    assert derived["r_replicates"] == v1ed._next_power_of_two(max(counts))
    assert derived["r_replicates"] >= max(counts) >= pilot.MIN_REPLICATES

    # A steady-dominated case: if R were taken over the SESOI family alone, this
    # would come back at the SESOI family's 7 rather than the adjacent family's.
    steady_dominated = pilot.derive_r_replicates(
        _pilot_report_for_derivation(paired_sd=0.02, var_ref=0.25),
        _steady_report_for_derivation(tail_sd=0.12, difference_sd=0.20),
    )
    sesoi_alone = max(
        entry["required_replicates"]
        for entry in steady_dominated["requirements"]["sesoi"]
    )
    assert sesoi_alone == max(
        entry["required_replicates"] for entry in derived["requirements"]["sesoi"]
    )
    assert steady_dominated["worst_required_replicates"] > sesoi_alone
    assert steady_dominated["r_replicates"] == v1ed._next_power_of_two(
        steady_dominated["worst_required_replicates"]
    )


def test_a_tighter_frozen_bound_raises_the_requirement():
    loose = pilot.derive_r_replicates(
        _pilot_report_for_derivation(),
        _steady_report_for_derivation(difference_sd=0.005),
    )
    tight = pilot.derive_r_replicates(
        _pilot_report_for_derivation(),
        _steady_report_for_derivation(difference_sd=0.06),
    )
    loosest = max(
        entry["required_replicates"]
        for entry in loose["requirements"]["adjacent_window_stability"]
    )
    tightest = max(
        entry["required_replicates"]
        for entry in tight["requirements"]["adjacent_window_stability"]
    )
    assert tightest > loosest
    assert tight["r_replicates"] >= loose["r_replicates"]


def test_an_infeasible_adjacent_window_bound_is_refused():
    # The window drift alone exceeds the frozen bound, and replicates cannot reduce
    # |mean|, so no R fixes it: the steady contract must be re-examined.
    steady = _steady_report_for_derivation(difference_mean=0.4, difference_sd=0.001)
    entry = next(
        item
        for item in pilot.steady_replicate_requirements(steady)
        if item["constraint"] == "adjacent_window_stability"
    )
    assert entry["required_replicates"] is None
    with pytest.raises(RuntimeError, match="out of reach"):
        pilot.derive_r_replicates(_pilot_report_for_derivation(), steady)


def test_derive_r_refuses_a_delta_policy_it_did_not_freeze():
    steady = _steady_report_for_derivation()
    with pytest.raises(ValueError, match="wealth_gini's Δ is frozen"):
        pilot.derive_r_replicates(
            _pilot_report_for_derivation(), steady, gini_delta=0.05
        )
    with pytest.raises(ValueError, match="ratio is frozen"):
        pilot.derive_r_replicates(
            _pilot_report_for_derivation(), steady, variance_ratio=0.25
        )
    # The rejected ratio is exactly the one the floor correction retired.
    assert pilot.FROZEN_VARIANCE_RATIO == 0.50


def test_derive_r_mode_is_offline_and_writes_what_it_derived(tmp_path, monkeypatch):
    # ``--derive-r`` must be runnable off the compute host, so the freeze step can
    # be reviewed anywhere; the run mode keeps its host check.
    monkeypatch.setattr(
        pilot, "project_path", lambda value, *, must_exist=False: Path(value)
    )
    pilot_report = _pilot_report_for_derivation(paired_sd=0.02, var_ref=0.25)
    steady_report = _steady_report_for_derivation(tail_sd=0.12, difference_sd=0.06)
    pilot_path = tmp_path / pilot.PILOT_REPORT_NAME
    steady_path = tmp_path / pilot.STEADY_REPORT_NAME
    pilot_path.write_text(json.dumps(pilot_report), encoding="utf-8")
    steady_path.write_text(json.dumps(steady_report), encoding="utf-8")
    out = tmp_path / "r_requirement.json"

    assert (
        pilot.main(
            [
                "--derive-r",
                "--pilot-report",
                str(pilot_path),
                "--steady-report",
                str(steady_path),
                "--out",
                str(out),
            ]
        )
        == 0
    )
    written = json.loads(out.read_text(encoding="utf-8"))
    assert written == pilot.derive_r_replicates(pilot_report, steady_report)
    assert written["delta_wealth_variance"] == pytest.approx(0.125)
    assert written["r_replicates"] >= pilot.MIN_REPLICATES

    with pytest.raises(SystemExit, match="requires --pilot-report"):
        pilot.main(["--derive-r", "--pilot-report", str(pilot_path)])


# ── 8. recording the pilot: promote the measurement, never rewrite it ──

recorder = sys.modules["prepare_cycle4_confirmation"]


def _steady_stub(*, passing: bool = True) -> dict:
    """A steady report with real predicates behind the frozen bounds.

    ``conditions`` is built by the shared summaries, so the replicate requirement
    the recorder derives is arithmetically meaningful rather than a stub constant.
    """
    steady = _steady_report_for_derivation()
    steady.update(
        {
            "experiment": pilot.EXPERIMENT_ID,
            "pass": passing,
            "tail_stationarity_valid": passing,
            "adjacent_window_stability_valid": passing,
            "independent_replicate_precision_valid": passing,
        }
    )
    return steady


def _report_from(steady: dict, *, rows=None, identity=None) -> dict:
    specs = _specs()
    rows = _rows(specs) if rows is None else rows
    by_seed = _by_seed(rows)
    return pilot.build_pilot_report(
        config=_pilot_config(),
        config_path=str(REPO_ROOT / PILOT_CONFIG),
        execution={"executed": len(specs)},
        identity=identity or study.e2_c4_identity_report(by_seed),
        comparability=_comparability(rows),
        dispersion=pilot.pilot_dispersion(rows, specs),
        reference_variance=pilot.wealth_variance_reference(by_seed),
        steady_report=steady,
        steady_report_sha256="f" * 64,
        rows=rows,
    )


def _stationarity_stub(report: dict) -> dict:
    failing = {str(name) for name in report.get("stationarity_failures", [])}
    runs = []
    for spec in _specs():
        if spec["run_id"] in failing:
            runs.append(
                {
                    "run_id": spec["run_id"],
                    "pass": False,
                    "metrics": {
                        "wealth_variance": {
                            "pass": False,
                            "drift_pass": False,
                            "monotonic_pass": True,
                            "normalized_window_drift": 0.19,
                            "max_normalized_drift": 0.1,
                            "effective_samples": 9.0,
                        }
                    },
                }
            )
        else:
            runs.append({"run_id": spec["run_id"], "pass": True, "metrics": {}})
    return {
        "experiment": pilot.EXPERIMENT_ID,
        "pass": not failing,
        "stationarity_valid": not failing,
        "precision_valid": True,
        "runs": runs,
    }


def _pilot_job(
    tmp_path,
    *,
    report=None,
    steady=None,
    stationarity=None,
    config=None,
    exit_code=0,
    timed_out=False,
):
    steady = _steady_stub() if steady is None else steady
    report = _report_from(steady) if report is None else report
    stationarity = _stationarity_stub(report) if stationarity is None else stationarity
    job_dir = tmp_path / pilot.EXPERIMENT_ID
    workspace = job_dir / "workspace"
    workspace.mkdir(parents=True)
    (job_dir / "config.json").write_text(
        json.dumps(_pilot_config() if config is None else config), encoding="utf-8"
    )
    payloads = {
        pilot.PILOT_REPORT_NAME: report,
        pilot.STEADY_REPORT_NAME: steady,
        "isolation_identity_report.json": {
            "experiment": pilot.EXPERIMENT_ID,
            "pass": True,
            "violations": [],
        },
        "stationarity_report.json": stationarity,
    }
    for name, payload in payloads.items():
        (workspace / name).write_text(json.dumps(payload), encoding="utf-8")
    jobctl = tmp_path / "jobctl" / pilot.EXPERIMENT_ID
    jobctl.mkdir(parents=True)
    (jobctl / "result.json").write_text(
        json.dumps(
            {"exit_code": exit_code, "timed_out": timed_out, "wall_seconds": 3.0}
        ),
        encoding="utf-8",
    )
    return job_dir, jobctl


def _rewrite(job_dir, name, mutate):
    """Apply ``mutate`` to a workspace artifact's JSON and write it back."""
    path = job_dir / "workspace" / name
    payload = json.loads(path.read_text(encoding="utf-8"))
    mutate(payload)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_record_pilot_promotes_the_artifact_verbatim_and_derives_r(tmp_path):
    job_dir, jobctl = _pilot_job(tmp_path)
    before = (job_dir / "workspace" / pilot.PILOT_REPORT_NAME).read_bytes()

    outcome = recorder.record_pilot(tmp_path, job_dir, jobctl)

    promoted = job_dir / pilot.PILOT_REPORT_NAME
    assert promoted.read_bytes() == before  # the measurement is copied, not edited
    assert outcome["pass"] is True
    assert outcome["report_pass"] is True

    result = json.loads((job_dir / "result.json").read_text(encoding="utf-8"))
    assert result["non_evidentiary"] is True
    assert result["per_run_stationarity"]["failure_count"] == 0
    assert result["criterion"]["artifact_unchanged"] is True
    assert result["reference_report"] == recorder._relative(tmp_path, promoted)
    # R is derived here, from the promoted reports, by the same function the freeze
    # step calls: nothing in the record is transcribed.
    derived = json.loads((job_dir / "r_requirement.json").read_text(encoding="utf-8"))
    report = json.loads(promoted.read_text(encoding="utf-8"))
    steady = json.loads(
        (job_dir / "workspace" / pilot.STEADY_REPORT_NAME).read_text(encoding="utf-8")
    )
    assert derived == pilot.derive_r_replicates(report, steady)
    assert result["replicate_requirement"] == derived
    assert result["artifacts"]["derivation_sha256"] == recorder._sha256(
        job_dir / "r_requirement.json"
    )

    manifest = json.loads((job_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["jobctl_reconcile"] == "completed"
    assert {entry["path"] for entry in manifest["artifacts"]} == {
        f"workspace/{name}"
        for name in (
            pilot.PILOT_REPORT_NAME,
            pilot.STEADY_REPORT_NAME,
            "isolation_identity_report.json",
            "stationarity_report.json",
        )
    }
    for entry in manifest["artifacts"]:
        assert entry["valid"] is True
        assert entry["sha256"] == recorder._sha256(job_dir / entry["path"])


def test_record_pilot_names_the_per_run_diagnostics_instead_of_smoothing_them(tmp_path):
    steady = _steady_stub()
    rows = _rows(_specs())
    rows[0]["stationarity_pass"] = False
    report = _report_from(steady, rows=rows)
    assert report["pass"] is False  # the run's own verdict, recorded as such

    job_dir, jobctl = _pilot_job(tmp_path, report=report, steady=steady)
    outcome = recorder.record_pilot(tmp_path, job_dir, jobctl)

    result = json.loads((job_dir / "result.json").read_text(encoding="utf-8"))
    assert result["pass"] is True
    assert result["report_verdict"]["pass"] is False
    block = result["per_run_stationarity"]
    assert block["failure_count"] == 1
    assert block["runs"] == len(_specs())
    assert block["ensemble_contract_pass"] is True
    assert block["gate_role_declared_in_this_artifact"] is False
    assert block["family_gate_role"].startswith("per_run_diagnostic_only")
    diagnostic = block["diagnostics"][0]
    assert diagnostic["run_id"] == report["stationarity_failures"][0]
    assert diagnostic["metric"] == "wealth_variance"
    assert diagnostic["normalized_window_drift"] == pytest.approx(0.19)
    assert any("deterministic" in item for item in result["criterion"]["basis"])
    assert outcome["per_run_failures"] == 1


@pytest.mark.parametrize("exit_code,timed_out", [(1, False), (0, True)])
def test_record_pilot_refuses_a_failed_or_timed_out_job(tmp_path, exit_code, timed_out):
    job_dir, jobctl = _pilot_job(tmp_path, exit_code=exit_code, timed_out=timed_out)
    with pytest.raises(RuntimeError, match="refusing to record"):
        recorder.record_pilot(tmp_path, job_dir, jobctl)


def test_record_pilot_refuses_a_direction_that_reached_the_artifact(tmp_path):
    job_dir, jobctl = _pilot_job(tmp_path)

    def mutate(payload):
        payload["paired_dispersion"]["contrasts"]["clustered-minus-shuffled"][
            "paired_mean_difference"
        ] = 0.5

    _rewrite(job_dir, pilot.PILOT_REPORT_NAME, mutate)
    with pytest.raises(RuntimeError, match="contrast-effect"):
        recorder.record_pilot(tmp_path, job_dir, jobctl)


def test_record_pilot_refuses_when_the_ensemble_contract_failed(tmp_path):
    steady = _steady_stub(passing=False)
    job_dir, jobctl = _pilot_job(tmp_path, steady=steady)
    with pytest.raises(RuntimeError, match="ensemble steady contract did not pass"):
        recorder.record_pilot(tmp_path, job_dir, jobctl)


def test_record_pilot_refuses_when_the_two_steady_blocks_disagree(tmp_path):
    job_dir, jobctl = _pilot_job(tmp_path)
    _rewrite(
        job_dir,
        pilot.PILOT_REPORT_NAME,
        lambda payload: payload["steady_contract_at_pilot_n"].__setitem__(
            "adjacent_window_stability_valid", False
        ),
    )
    with pytest.raises(RuntimeError, match="disagree on adjacent_window_stability_valid"):
        recorder.record_pilot(tmp_path, job_dir, jobctl)


def test_record_pilot_refuses_an_identity_failure(tmp_path):
    job_dir, jobctl = _pilot_job(tmp_path)
    _rewrite(
        job_dir,
        pilot.PILOT_REPORT_NAME,
        lambda payload: payload["P1_isolation_identity"].__setitem__("pass", False),
    )
    with pytest.raises(RuntimeError, match="P1 isolation identity did not hold"):
        recorder.record_pilot(tmp_path, job_dir, jobctl)


def test_record_pilot_refuses_identity_artifacts_that_disagree(tmp_path):
    job_dir, jobctl = _pilot_job(tmp_path)
    _rewrite(
        job_dir,
        "isolation_identity_report.json",
        lambda payload: payload.__setitem__("pass", False),
    )
    with pytest.raises(RuntimeError, match="does not pass"):
        recorder.record_pilot(tmp_path, job_dir, jobctl)


def test_record_pilot_refuses_an_incomplete_batch(tmp_path):
    job_dir, jobctl = _pilot_job(tmp_path)
    _rewrite(
        job_dir,
        pilot.PILOT_REPORT_NAME,
        lambda payload: payload.__setitem__("run_count", payload["run_count"] - 1),
    )
    with pytest.raises(RuntimeError, match="runs; the frozen battery needs"):
        recorder.record_pilot(tmp_path, job_dir, jobctl)


def test_record_pilot_refuses_a_truncated_stationarity_report(tmp_path):
    job_dir, jobctl = _pilot_job(tmp_path)
    _rewrite(
        job_dir,
        "stationarity_report.json",
        lambda payload: payload["runs"].pop(),
    )
    with pytest.raises(RuntimeError, match="a short file could hide"):
        recorder.record_pilot(tmp_path, job_dir, jobctl)


def test_record_pilot_refuses_stationarity_reports_that_disagree(tmp_path):
    job_dir, jobctl = _pilot_job(tmp_path)

    def mutate(payload):
        payload["runs"][0]["pass"] = False
        payload["runs"][0]["metrics"] = {
            "wealth_variance": {
                "pass": False,
                "drift_pass": False,
                "monotonic_pass": True,
                "normalized_window_drift": 0.19,
                "max_normalized_drift": 0.1,
                "effective_samples": 9.0,
            }
        }

    _rewrite(job_dir, "stationarity_report.json", mutate)
    with pytest.raises(RuntimeError, match="disagree about which runs failed"):
        recorder.record_pilot(tmp_path, job_dir, jobctl)


def test_record_pilot_refuses_a_recorded_requirement_that_disagrees(tmp_path):
    job_dir, jobctl = _pilot_job(tmp_path)
    (job_dir / "r_requirement.json").write_text(
        json.dumps({"r_replicates": 4}), encoding="utf-8"
    )
    with pytest.raises(RuntimeError, match="disagrees with the one this pilot's reports imply"):
        recorder.record_pilot(tmp_path, job_dir, jobctl)


def test_record_pilot_refuses_a_config_that_moved_under_the_report(tmp_path):
    config = _pilot_config()
    config["binary_sha256"] = "0" * 64
    job_dir, jobctl = _pilot_job(tmp_path, config=config)
    with pytest.raises(RuntimeError, match="different reference binary"):
        recorder.record_pilot(tmp_path, job_dir, jobctl)


def test_record_pilot_refuses_a_lock_that_moved_under_the_report(tmp_path):
    config = _pilot_config()
    config["parameter_lock"] = "research/parameter_lock.cycle3.json"
    job_dir, jobctl = _pilot_job(tmp_path, config=config)
    with pytest.raises(RuntimeError, match="different parameter lock"):
        recorder.record_pilot(tmp_path, job_dir, jobctl)
