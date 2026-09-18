"""E2-C4's relative variance SESOI: the rule, its floor, and its false claims.

``wealth_variance`` is scale sensitive, so its SESOI is pre-registered as the rule
``delta := ratio * Var_ref`` rather than as a number: the same relative precision
means the same thing whichever level the force-off regime turns out to have.
``Var_ref`` is a *reading* from the non-evidentiary pilot, which means the rule can
only be trusted if three separate statements of the same quantity are forced to
agree -- the rule evaluated against the checksum-bound report, the absolute value
the config declares, and the value the derivation record itself states.

Two things here are easy to get wrong and are therefore tested against their own
definitions rather than against a remembered constant:

1. **the level-drift floor.** P4 constrains each unit's mean wealth relative to the
   *group mean*, so two contrasted units can sit at opposite edges of the band and
   the drift contribution to a variance *contrast* is larger than the drift
   contribution of a single unit. The floor is defined as a maximum over
   admissible three-unit configurations and is recomputed here by brute force, so
   the closed form cannot quietly drift towards a more convenient value.
2. **the refusal to degrade.** A config that declares a variance threshold without
   a derivation must fail rather than fall back to a hand-written absolute; a
   config that declares no threshold at all must still be analysable, with the
   metric explicitly claim-ineligible.

Everything writes only into ``tmp_path``.
"""

from __future__ import annotations

import importlib.util
import itertools
import json
from pathlib import Path
import sys

import pytest

MODULE_PATH = (
    Path(__file__).parents[1] / "research" / "src" / "experiments" / "run_landscape_study.py"
)
sys.path.insert(0, str(MODULE_PATH.parent))
SPEC = importlib.util.spec_from_file_location("run_landscape_study", MODULE_PATH)
assert SPEC and SPEC.loader
run_landscape_study = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(run_landscape_study)

METRIC = "wealth_variance"
REFERENCE_FIELD = run_landscape_study.E2_C4_SESOI_REFERENCE_FIELDS[METRIC]
FROZEN_BAND = 0.10
DECIDED_RATIO = 0.50
# The value the closed form gives for the frozen +/-10% band. Quoted so that a
# change to the band or to the formula has to be an explicit edit here as well.
FROZEN_BAND_FLOOR = 0.3973509933774835


def _brute_force_floor(band: float, steps: int = 4001) -> float:
    """Maximum relative variance span over admissible three-unit level vectors.

    Levels are normalised so the group mean is 1, each unit is within ``band`` of
    it, and the third member is pinned by the mean constraint. This is the
    definition the closed form must reproduce, computed with no algebra.
    """
    best = 0.0
    for low, high in itertools.product(
        (1.0 - band, 1.0 + band), repeat=2
    ):
        third = 3.0 - low - high
        if not (1.0 - band - 1e-12 <= third <= 1.0 + band + 1e-12):
            continue
        levels = (low, high, third)
        mean_square = sum(level * level for level in levels) / 3.0
        for first, second in itertools.permutations(range(3), 2):
            span = abs(levels[first] ** 2 - levels[second] ** 2) / mean_square
            best = max(best, span)
    return best


@pytest.mark.parametrize("band", [0.10, 0.05, 0.25])
def test_floor_is_the_maximum_over_admissible_level_configurations(band):
    closed_form = run_landscape_study.e2_c4_level_drift_variance_floor(band)
    assert closed_form == pytest.approx(_brute_force_floor(band), rel=1e-12)
    # The brief that first proposed a floor used a single unit's deviation from
    # the group mean -- "(1+band)^2 - 1". That understates the contrast span,
    # because both contrasted units may drift in opposite directions, so the two
    # formulas must not be interchangeable.
    one_sided = (1.0 + band) ** 2 - 1.0
    assert closed_form > one_sided


def test_frozen_band_floor_is_the_decided_ratio_boundary():
    floor = run_landscape_study.e2_c4_level_drift_variance_floor(FROZEN_BAND)
    assert floor == pytest.approx(FROZEN_BAND_FLOOR, rel=1e-15)
    assert DECIDED_RATIO > floor
    # The ratio that was decided before the floor was recomputed sits below it,
    # which is the whole reason this module exists.
    assert 0.25 <= floor


def test_floor_is_undefined_outside_the_open_unit_interval():
    for band in (0.0, -0.1, 1.0, 1.5, float("nan"), float("inf")):
        with pytest.raises(ValueError):
            run_landscape_study.e2_c4_level_drift_variance_floor(band)


def _write_pilot_report(root: Path, var_ref: float) -> tuple[Path, str]:
    report = root / "pilot_variance_report.json"
    run_landscape_study.write_json(
        report,
        {
            "experiment": "E2-C4-PILOT",
            "wealth_variance_reference": {
                "P2_source_pattern": {"mean_wealth_variance": var_ref}
            },
        },
    )
    return report, run_landscape_study.sha256_file(report)


def _config(
    tmp_path: Path,
    *,
    var_ref: float = 2.5,
    ratio: float = DECIDED_RATIO,
    declared: float | None = None,
    band: float = FROZEN_BAND,
    report_path: Path | None = None,
    report_sha256: str | None = None,
    field: str = REFERENCE_FIELD,
    resolved_value: float | None = None,
    extra_derivations: dict | None = None,
) -> dict:
    report, sha = _write_pilot_report(tmp_path, var_ref)
    resolved = ratio * var_ref
    derivation = {
        "metric": METRIC,
        "rule": run_landscape_study.E2_C4_RELATIVE_SESOI_RULE,
        "ratio": ratio,
        "reference_field": field,
        "reference_report": str(report_path if report_path is not None else report),
        "reference_report_sha256": (
            report_sha256 if report_sha256 is not None else sha
        ),
        "resolved_value": resolved if resolved_value is None else resolved_value,
    }
    derivations = {METRIC: derivation}
    if extra_derivations:
        derivations.update(extra_derivations)
    return {
        "comparability_mean_wealth_relative_band": band,
        "scientific_sesoi": {
            "wealth_gini": 0.025,
            METRIC: resolved if declared is None else declared,
        },
        "scientific_sesoi_derivations": derivations,
    }


def test_derivation_is_accepted_and_records_rule_reference_and_margin(tmp_path, monkeypatch):
    monkeypatch.setattr(run_landscape_study, "PROJECT_ROOT", tmp_path)
    config = _config(tmp_path)
    records = run_landscape_study.validate_e2_c4_sesoi_derivations(config)
    record = records[METRIC]
    assert record["rule"] == run_landscape_study.E2_C4_RELATIVE_SESOI_RULE
    assert record["ratio"] == DECIDED_RATIO
    assert record["reference_level"] == 2.5
    assert record["resolved_value"] == pytest.approx(1.25)
    assert record["level_drift_floor"] == pytest.approx(FROZEN_BAND_FLOOR, rel=1e-15)
    assert record["level_drift_margin"] == pytest.approx(DECIDED_RATIO / FROZEN_BAND_FLOOR - 1.0)
    # The report is named relative to the project, so the record can be re-read
    # after the checkout moves.
    assert record["reference_report"] == "pilot_variance_report.json"
    assert record["reference_report_sha256"] == run_landscape_study.sha256_file(
        tmp_path / "pilot_variance_report.json"
    )


def test_metric_without_a_declared_threshold_needs_no_derivation(tmp_path, monkeypatch):
    # The claim-ineligible route stays open: no declared SESOI, no rule to check,
    # and the reason code is what records it.
    monkeypatch.setattr(run_landscape_study, "PROJECT_ROOT", tmp_path)
    config = {
        "comparability_mean_wealth_relative_band": FROZEN_BAND,
        "scientific_sesoi": {"wealth_gini": 0.025},
    }
    assert run_landscape_study.validate_e2_c4_sesoi_derivations(config) == {}


def test_declared_threshold_without_a_derivation_is_refused(tmp_path, monkeypatch):
    # The dangerous shape: a number that looks frozen but whose rule was never
    # landed, so the design's relative SESOI is bypassed invisibly.
    monkeypatch.setattr(run_landscape_study, "PROJECT_ROOT", tmp_path)
    config = _config(tmp_path)
    del config["scientific_sesoi_derivations"]
    with pytest.raises(RuntimeError, match="no derivation"):
        run_landscape_study.validate_e2_c4_sesoi_derivations(config)


def test_declared_number_must_equal_the_rule_applied_to_the_report(tmp_path, monkeypatch):
    monkeypatch.setattr(run_landscape_study, "PROJECT_ROOT", tmp_path)
    config = _config(tmp_path, declared=1.0)
    with pytest.raises(RuntimeError, match="derived, never chosen"):
        run_landscape_study.validate_e2_c4_sesoi_derivations(config)


def test_recorded_resolved_value_must_agree_with_its_own_rule(tmp_path, monkeypatch):
    monkeypatch.setattr(run_landscape_study, "PROJECT_ROOT", tmp_path)
    config = _config(tmp_path, resolved_value=1.0)
    with pytest.raises(RuntimeError, match="twice and disagree"):
        run_landscape_study.validate_e2_c4_sesoi_derivations(config)


def test_ratio_at_or_below_the_level_drift_floor_is_refused(tmp_path, monkeypatch):
    monkeypatch.setattr(run_landscape_study, "PROJECT_ROOT", tmp_path)
    config = _config(tmp_path, ratio=0.25)
    with pytest.raises(RuntimeError, match="level-drift floor"):
        run_landscape_study.validate_e2_c4_sesoi_derivations(config)


def test_reference_report_is_checksum_bound(tmp_path, monkeypatch):
    monkeypatch.setattr(run_landscape_study, "PROJECT_ROOT", tmp_path)
    config = _config(tmp_path)
    # Substituting a report with a different reading must not be enough: the
    # binding is to the artifact, not to its path.
    report, _sha = _write_pilot_report(tmp_path, 9.0)
    assert report.is_file()
    with pytest.raises(RuntimeError, match="checksum mismatch"):
        run_landscape_study.validate_e2_c4_sesoi_derivations(config)


def test_reference_field_cannot_be_re_anchored(tmp_path, monkeypatch):
    monkeypatch.setattr(run_landscape_study, "PROJECT_ROOT", tmp_path)
    config = _config(tmp_path, field="wealth_variance_reference.P2_source_pattern.whatever")
    with pytest.raises(RuntimeError, match="pre-registered reference"):
        run_landscape_study.validate_e2_c4_sesoi_derivations(config)


def test_missing_reference_report_is_refused(tmp_path, monkeypatch):
    monkeypatch.setattr(run_landscape_study, "PROJECT_ROOT", tmp_path)
    config = _config(tmp_path, report_path=tmp_path / "not_written.json")
    with pytest.raises(FileNotFoundError):
        run_landscape_study.validate_e2_c4_sesoi_derivations(config)


def test_reference_field_must_be_a_positive_number(tmp_path, monkeypatch):
    monkeypatch.setattr(run_landscape_study, "PROJECT_ROOT", tmp_path)
    config = _config(tmp_path, var_ref=-1.0)
    with pytest.raises(RuntimeError, match="must be finite and positive"):
        run_landscape_study.validate_e2_c4_sesoi_derivations(config)
    assert (tmp_path / "pilot_variance_report.json").is_file()


def test_a_rule_for_a_scale_invariant_metric_is_refused(tmp_path, monkeypatch):
    # ``wealth_gini`` is scale invariant, so a relative rule there would be a new
    # mechanism rather than a re-expression of the same one.
    monkeypatch.setattr(run_landscape_study, "PROJECT_ROOT", tmp_path)
    config = _config(tmp_path)
    config["scientific_sesoi_derivations"]["wealth_gini"] = dict(
        config["scientific_sesoi_derivations"][METRIC]
    ) | {"metric": "wealth_gini"}
    with pytest.raises(RuntimeError, match="scale-invariant"):
        run_landscape_study.validate_e2_c4_sesoi_derivations(config)


def test_unknown_rule_name_is_refused(tmp_path, monkeypatch):
    monkeypatch.setattr(run_landscape_study, "PROJECT_ROOT", tmp_path)
    config = _config(tmp_path)
    config["scientific_sesoi_derivations"][METRIC]["rule"] = "hand_written"
    with pytest.raises(RuntimeError, match="unknown rule"):
        run_landscape_study.validate_e2_c4_sesoi_derivations(config)


def test_derivation_key_set_is_exact(tmp_path, monkeypatch):
    monkeypatch.setattr(run_landscape_study, "PROJECT_ROOT", tmp_path)
    config = _config(tmp_path)
    del config["scientific_sesoi_derivations"][METRIC]["resolved_value"]
    with pytest.raises(RuntimeError, match="must have exactly"):
        run_landscape_study.validate_e2_c4_sesoi_derivations(config)


def test_band_is_required_to_bound_the_ratio(tmp_path, monkeypatch):
    monkeypatch.setattr(run_landscape_study, "PROJECT_ROOT", tmp_path)
    config = _config(tmp_path)
    del config["comparability_mean_wealth_relative_band"]
    with pytest.raises(RuntimeError, match="comparability_mean_wealth_relative_band"):
        run_landscape_study.validate_e2_c4_sesoi_derivations(config)


# --- end-to-end: the derivation reaches the effect payload -------------------


E2_C4_TEST_SEEDS = [1, 2, 3, 4, 5, 6, 7, 8]


def _e2_c4_rows() -> list[dict[str, object]]:
    clustered, shuffled, flat = run_landscape_study.E2_C4_PATTERN_UNITS
    d_low, _d_ref, d_high = run_landscape_study.E2_C4_SINK_UNITS
    gini = {clustered: 0.30, shuffled: 0.20, flat: 0.25, d_low: 0.30, d_high: 0.30}
    variance = {clustered: 2.60, shuffled: 2.40, flat: 2.50, d_low: 2.55, d_high: 2.45}
    levels = {clustered: 1.00, shuffled: 0.95, flat: 1.05, d_low: 0.98, d_high: 1.02}
    rows: list[dict[str, object]] = []
    for seed in E2_C4_TEST_SEEDS:
        for unit in run_landscape_study.E2_C4_UNIT_NAMES:
            rows.append(
                {
                    "seed": seed,
                    "condition": unit,
                    "occupancy_entropy": 0.7,
                    "density_morans_i": 0.3,
                    "resource_density_spearman_rho": (
                        None if unit == flat else 0.2
                    ),
                    "wealth_gini": gini[unit],
                    "wealth_variance": variance[unit],
                    "zero_wealth_fraction": 0.0,
                    "minimum_wealth": 0.1,
                    "minimum_wealth_observed": 0.1,
                    "mean_wealth": levels[unit],
                    "mean_source_rate": 0.01,
                    "total_source_rate": 10.0,
                    "mean_resource_at_particles": 1.0,
                    "particle_count": 1000.0,
                }
            )
    return rows


def test_payload_threshold_components_carry_the_rule_and_its_reference(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(run_landscape_study, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(
        run_landscape_study,
        "load_e2_c4_calibration",
        lambda _config: {
            "experiment": "V1F-NONFLAT-CALIBRATION-C4",
            "pass": True,
            "numerical_resolution_limits": {"wealth_gini": 0.0014, METRIC: 0.0568},
        },
    )
    run_landscape_study.write_json(tmp_path / "matched_input_audit.json", {"pass": True})
    config = {
        "seeds": E2_C4_TEST_SEEDS,
        "population": 1000,
        "familywise_alpha": 0.05,
        "bootstrap_samples": 1000,
        "ability_saturation_w": 5.0,
        "comparability_zero_wealth_fraction_max": 0.05,
        "comparability_wealth_variance_min": 0.01,
    } | _config(tmp_path, var_ref=2.5)
    payload = run_landscape_study.aggregate_e2_c4(
        _e2_c4_rows(),
        config,
        tmp_path,
        {"pass": True, "tail_stationarity_valid": True},
    )
    entry = payload["P2_source_pattern"]["primary"][f"{METRIC}::clustered-minus-shuffled"]
    assert entry["claim_eligible"] is True
    components = entry["threshold_components"]
    # The recorded threshold keeps all three statements of the same quantity: the
    # absolute used for the decision, the rule, and the reading it came from.
    assert components["scientific_sesoi"] == pytest.approx(1.25)
    assert components["effective_claim_threshold"] == pytest.approx(1.25)
    assert components["derivation"]["rule"] == (
        run_landscape_study.E2_C4_RELATIVE_SESOI_RULE
    )
    assert components["derivation"]["ratio"] == DECIDED_RATIO
    assert components["derivation"]["reference_level"] == 2.5
    assert components["derivation"]["reference_report_sha256"] == (
        run_landscape_study.sha256_file(tmp_path / "pilot_variance_report.json")
    )
    # ``wealth_gini`` keeps an absolute number, so it must not acquire a rule.
    gini_entry = payload["P2_source_pattern"]["primary"][
        "wealth_gini::clustered-minus-shuffled"
    ]
    assert "derivation" not in gini_entry["threshold_components"]


def test_payload_refuses_when_the_declared_variance_threshold_has_no_rule(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(run_landscape_study, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(
        run_landscape_study,
        "load_e2_c4_calibration",
        lambda _config: {
            "experiment": "V1F-NONFLAT-CALIBRATION-C4",
            "pass": True,
            "numerical_resolution_limits": {"wealth_gini": 0.0014, METRIC: 0.0568},
        },
    )
    run_landscape_study.write_json(tmp_path / "matched_input_audit.json", {"pass": True})
    config = {
        "seeds": E2_C4_TEST_SEEDS,
        "population": 1000,
        "familywise_alpha": 0.05,
        "bootstrap_samples": 1000,
        "ability_saturation_w": 5.0,
        "comparability_zero_wealth_fraction_max": 0.05,
        "comparability_wealth_variance_min": 0.01,
    } | _config(tmp_path, var_ref=2.5)
    del config["scientific_sesoi_derivations"]
    with pytest.raises(RuntimeError, match="no derivation"):
        run_landscape_study.aggregate_e2_c4(
            _e2_c4_rows(),
            config,
            tmp_path,
            {"pass": True, "tail_stationarity_valid": True},
        )


def test_e2_c4_prerun_coverage_demands_the_second_estimand():
    # R03's point: refuse before the runs are paid for, not when the payload is
    # assembled. Both claim-bearing metrics must already carry a threshold.
    assert run_landscape_study.confirmatory_metrics_for_experiment(
        run_landscape_study.E2_C4_EXPERIMENT
    ) == ("wealth_gini", METRIC)
