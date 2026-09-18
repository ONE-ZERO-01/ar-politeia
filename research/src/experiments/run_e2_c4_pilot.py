#!/usr/bin/env python3
"""E2-C4 pilot: measure the dispersion the confirmatory run needs, and nothing else.

E2-C4's replicate count cannot be inherited from E1-C4 (design §8: 64 was sized
for the paired *landscape* contrast, not for the wealth-structure contrasts), so
it has to come from this experiment's own variance. This pilot is the single
reading that supplies it, and it is **non-evidentiary**: it produces no effect
direction, size, interval or p-value for any contrast, and must never be cited as
evidence for ``C3-CHANNELS-C4``.

The discipline is "guard quantities report levels, estimands report dispersion
only":

* P4's policy quantities (``mean_wealth``, ``zero_wealth_fraction``,
  ``wealth_variance``) are reported as **per-unit levels**, because the frozen
  comparison criteria are themselves per-unit levels and cannot be evaluated
  otherwise. None of the three carries a claim (design §15, §15.5).
* ``wealth_gini`` and ``wealth_variance``, as estimands, are reported as
  **paired-difference sample SDs only** — no mean, no sign. So the direction of
  both estimands remains unread in this project until the confirmatory run.

Three reporting constraints shape the code:

* ``Var_ref`` (the P2 group's mean ``wealth_variance``, the reference level in
  ``Δ_var := 0.50 × Var_ref``) lives in a self-describing top-level field, because
  the analyser binds this report by sha256 and reads that field by dotted path;
  its shape is therefore a hard contract, not a presentation choice.
* The frozen two-window steady contract is *not* a pilot verdict. Its adjacent and
  precision predicates are functions of the replicate count, which is the quantity
  this pilot exists to determine, so they are recorded at the pilot's ``n`` for the
  record and for the replicate requirement they imply — never as a judgement on
  the pilot. Whether the pilot itself is sound is decided by P1 and by the
  replicate-count-independent per-run stationarity checks.
* Nothing about R is written into this report. ``--derive-r`` re-reads the two
  finished reports and turns them into the replicate requirement; it is pure
  JSON-in/JSON-out, so the freeze step that writes R into the E2 lock can be
  reviewed and re-run off the compute host.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import numpy as np
from scipy.stats import chi2

from landscape_study import sha256_file, write_json
from prepare_cycle4_confirmation import _is_prime, audit_seeds
from run_landscape_study import (
    E2_C4_EFFECT_METRICS,
    E2_C4_PATTERN_UNITS,
    E2_C4_PILOT_EXPERIMENT,
    E2_C4_SINK_UNITS,
    E2_C4_UNITS,
    PROJECT_ROOT,
    _e2_c4_comparability,
    aggregate_e1_c4_steady_estimand,
    analyze_runs,
    e2_c4_identity_report,
    execute_runs,
    load_json,
    prepare_inputs,
    project_path,
    require_umi,
    validate_reference_binary,
)
from run_v1e_sampling_diagnostic import _next_power_of_two, _required_replicates

EXPERIMENT_ID = E2_C4_PILOT_EXPERIMENT
JOB_DIR = f"research/jobs/{EXPERIMENT_ID}"
REFERENCE_EXPERIMENT = "E1-MATCHED-LANDSCAPES-C4"
REFERENCE_CONFIG = f"research/jobs/{REFERENCE_EXPERIMENT}/config.json"
PARAMETER_LOCK = "research/parameter_lock.cycle4.json"
PILOT_REPORT_NAME = "pilot_variance_report.json"
STEADY_REPORT_NAME = "steady_estimand_report.json"

# Frozen seed window and the pilot's eight seeds (design §2). ``[12300, 13000]``
# holds 77 unused primes; the pilot takes the smallest eight, leaving 69 for the
# confirmatory run up to R = 64, and the two subsets cannot intersect.
SEED_WINDOW = (12300, 13000)
FROZEN_PILOT_SEEDS = (12301, 12323, 12329, 12343, 12347, 12373, 12377, 12379)
PILOT_SEED_COUNT = len(FROZEN_PILOT_SEEDS)

# V1ED's one-sided upper SD bound. With ``n = 8`` the sample SD is ~1.6x too
# narrow, and using the point estimate would systematically under-size R.
UPPER_SD_ALPHA = 0.1
MIN_REPLICATES = 3

# The pilot must run *the reference protocol*, otherwise its variance is not the
# confirmatory run's variance. Each value is checked twice: against the frozen
# reference experiment's tracked config, and against this table, so neither a
# config edit nor a reference drift can move the probe silently.
FROZEN_PROTOCOL: dict[str, Any] = {
    "temperature": 0.5,
    "dt": 0.005,
    "total_time": 4500.0,
    "output_time_interval": 5.0,
    "steady_snapshots": 144,
    "population": 1000,
    "grid_shape": [64, 64],
    "bounds": [0.0, 100.0, 0.0, 100.0],
    "friction": 1.0,
    "interaction_range": 2.5,
    "exchange_rate": 0.5,
    "exchange_noise_strength": 0.05,
    "exchange_reversion_rate": 1.0,
    "epsilon_log_sigma": 0.5,
    "wealth_log_sigma": 0.01,
    "consumption_rate": 0.0,
    "terrain_force_scale": 1.0,
    "terrain_production_scale": 1.0,
    "social_strength": 0.0,
    "ability_saturation_w": 5.0,
    "ranks": 1,
    "mpi_enabled": False,
    "omp_threads": 1,
    "confirmative_mode": True,
    "strict_numerics": True,
}

# Δ policy frozen 2026-09-18 (design §4 P2, sesoi-decision §9/§10). Taken as
# arguments by ``derive_r_replicates`` so the freeze step reads them from the
# record that carries them, and matched against these literals so no caller can
# hand R a ratio the pre-registration did not freeze.
FROZEN_GINI_DELTA = 0.025
FROZEN_VARIANCE_RATIO = 0.50

# The battery, duplicated on purpose. ``E2_C4_UNITS`` is code, not config, so an
# edit to it would otherwise silently redefine what the pilot measured: the
# prepared spec and the expectation would drift together. Keeping the freezer
# here means such an edit makes the two disagree and the run stops, and
# ``test_frozen_unit_table_matches_the_shared_table`` keeps the copy honest.
FROZEN_UNIT_TABLE = (
    ("clustered-d0.02", "clustered", 0.02, 0.01),
    ("shuffled-d0.02", "shuffled", 0.02, 0.01),
    ("flat-d0.02", "flat", 0.02, 0.01),
    ("clustered-d0.01", "clustered", 0.01, 0.005),
    ("clustered-d0.04", "clustered", 0.04, 0.02),
)

# The pre-registered contrasts, built from the same shared unit constants
# ``aggregate_e2_c4`` uses so the pilot measures the differences the confirmatory
# analyser will actually test.
PILOT_CONTRASTS = (
    {
        "label": "clustered-minus-shuffled",
        "treatment": E2_C4_PATTERN_UNITS[0],
        "control": E2_C4_PATTERN_UNITS[1],
        "claim_bearing": True,
    },
    {
        "label": "clustered-minus-flat",
        "treatment": E2_C4_PATTERN_UNITS[0],
        "control": E2_C4_PATTERN_UNITS[2],
        "claim_bearing": False,
    },
    {
        "label": "d0.04-minus-d0.01",
        "treatment": E2_C4_SINK_UNITS[2],
        "control": E2_C4_SINK_UNITS[0],
        "claim_bearing": True,
    },
)
# Only these two may become claim thresholds (design §15), so only these two enter
# the SESOI term of the replicate requirement.
PILOT_CLAIM_METRICS = ("wealth_gini", "wealth_variance")

# Contrast vocabulary that must never appear anywhere in the pilot report. These
# are *difference* names, not level names: ``mean_wealth``/``mean_wealth_variance``
# are P4 level readings and are supposed to be there.
FORBIDDEN_EFFECT_KEYS = frozenset(
    {
        "mean_difference",
        "paired_mean_difference",
        "signed_mean_difference",
        "relative_mean_difference",
        "mean_effect",
        "effect",
        "effect_size",
        "direction",
        "ci95_low",
        "ci95_high",
        "p_value",
        "p_values",
        "sign_flip_p_value",
        "claim_threshold_pass",
        "claim_supported",
        "inconclusive",
    }
)


# ── protocol, seeds, units: the three "fail fast, or don't run" guards ──


def reference_protocol(root: Path) -> dict[str, Any]:
    """The frozen keys as the reference experiment actually declares them."""
    config = load_json(root / REFERENCE_CONFIG)
    return {key: config[key] for key in FROZEN_PROTOCOL if key in config}


def require_protocol_match(
    config: Mapping[str, Any], reference: Mapping[str, Any]
) -> None:
    """Refuse to probe a protocol the confirmatory run will not run.

    Two independent directions are checked because each catches a different
    accident: the config must equal the frozen table (a config edit), and every
    frozen key the reference experiment also declares must equal the reference
    value (a reference drift). ``ability_saturation_w`` is absent from the
    reference config; the simulator's config builder defaults it to the same frozen
    value, and ``test_frozen_protocol_matches_the_reference_config`` checks that
    default rather than leaving it assumed here.
    """
    for key, expected in FROZEN_PROTOCOL.items():
        if key not in config:
            raise ValueError(f"E2-C4 pilot config must pin {key}")
        if config[key] != expected:
            raise ValueError(
                f"E2-C4 pilot must run the frozen protocol; {key} is "
                f"{config[key]!r}, the frozen value is {expected!r}"
            )
        if key in reference and reference[key] != config[key]:
            raise ValueError(
                f"protocol drift: {REFERENCE_EXPERIMENT} declares {key} = "
                f"{reference[key]!r} but the pilot's frozen value is "
                f"{config[key]!r}; the pilot's variance would not be the "
                "confirmatory run's variance"
            )


def window_pool(
    consumed: Iterable[int], *, window: tuple[int, int] = SEED_WINDOW
) -> list[int]:
    """Unused primes inside the frozen window, smallest first.

    Mirrors ``seeds-audit --pool-min/--pool-max`` exactly (inclusive ends) so the
    proposal can be recomputed from the ledger without a second convention.
    """
    used = {int(seed) for seed in consumed}
    low, high = window
    return [
        value for value in range(low, high + 1) if _is_prime(value) and value not in used
    ]


def require_frozen_seeds(
    seeds: Sequence[int],
    *,
    consumed_by_others: Iterable[int],
    window: tuple[int, int] = SEED_WINDOW,
) -> None:
    """Refuse to run unless the seeds are the frozen eight and still unseen.

    ``consumed_by_others`` is every seed the ledger attributes to *another* job;
    the pilot's own declaration is excluded by its caller, because a job cannot
    reuse its own seeds.
    """
    values = [int(seed) for seed in seeds]
    if sorted(values) != sorted(FROZEN_PILOT_SEEDS):
        raise ValueError(
            f"the pilot's seeds are frozen at {list(FROZEN_PILOT_SEEDS)}; "
            f"got {sorted(values)}"
        )
    if len(set(values)) != len(values):
        raise ValueError("the pilot's seeds must be distinct")
    low, high = window
    for seed in values:
        if not low <= seed <= high:
            raise ValueError(f"pilot seed {seed} is outside the frozen window {window}")
        if not _is_prime(seed):
            raise ValueError(f"pilot seed {seed} is not prime")
    overlap = sorted(set(values) & {int(seed) for seed in consumed_by_others})
    if overlap:
        raise ValueError(
            f"pilot seeds are already consumed by another job: {overlap}; seed "
            "independence is broken and the pilot's variance would not be the "
            "confirmatory run's"
        )


def ledger_seed_partition(root: Path) -> dict[str, list[int]]:
    """Split the ledger's seeds into "this pilot's" and "everyone else's"."""
    report = audit_seeds(root / "research" / "jobs")
    own = [int(seed) for seed in report["jobs"].get(EXPERIMENT_ID, {}).get("seeds", [])]
    used = {int(seed) for seed in report["used_seeds"]}
    others = sorted(used - set(own))
    return {
        "own": sorted(own),
        "others": others,
        "available_in_window": window_pool(others),
    }


def require_locked_binary(config: Mapping[str, Any], lock: Mapping[str, Any]) -> None:
    """The pilot must probe the binary the calibration froze, not just any binary.

    The file-level check (``validate_reference_binary``) proves the binary matches
    the config; this proves the config matches the lock, which is the binding S14
    showed can silently break. The pilot's question is "what is the variance *on
    this* binary", so a different binary makes the reading void.
    """
    declared_lock = str(config.get("parameter_lock", ""))
    if declared_lock != PARAMETER_LOCK:
        raise RuntimeError(
            f"the pilot must bind {PARAMETER_LOCK}; the config names "
            f"{declared_lock!r}"
        )
    locked = str(lock["numerical_calibration"]["reference_binary_sha256"])
    declared = str(config.get("binary_sha256"))
    if declared != locked:
        raise RuntimeError(
            "the pilot must probe the calibrated reference binary: config declares "
            f"{declared}, the lock freezes {locked}"
        )


def require_frozen_units(specs: Sequence[Mapping[str, Any]]) -> None:
    """Refuse to run units that are not the frozen design matrix.

    Three separate accidents are covered, because each is silent on its own: the
    shared table drifting from ``FROZEN_UNIT_TABLE`` (a code edit *before* the
    prepared specs are read -- the confirmatory config would then describe a
    battery the pilot never ran), the prepared specs carrying a different
    ``(landscape, d, base)`` than the frozen table, and a unit arriving with the
    wrong number of replicates (a partial or over-sized battery changes what the
    sample SD means).
    """
    if tuple(E2_C4_UNITS) != FROZEN_UNIT_TABLE:
        raise ValueError(
            "E2_C4_UNITS no longer matches the battery this pilot was "
            f"pre-registered on: shared {tuple(E2_C4_UNITS)} vs frozen "
            f"{FROZEN_UNIT_TABLE}"
        )
    expected = {
        name: (landscape, float(decay), float(base))
        for name, landscape, decay, base in FROZEN_UNIT_TABLE
    }
    prepared: dict[str, tuple[str, float, float]] = {}
    seeds_by_unit: dict[str, set[int]] = {}
    for spec in specs:
        name = str(spec["condition"])
        values = (
            str(spec["landscape"]),
            float(spec["wealth_decay_rate"]),
            float(spec["base_production"]),
        )
        previous = prepared.setdefault(name, values)
        if previous != values:
            raise ValueError(
                f"prepared inputs give unit {name!r} two different "
                f"(landscape, d, base) tuples: {previous} and {values}"
            )
        seeds_by_unit.setdefault(name, set()).add(int(spec["seed"]))
    if set(prepared) != set(expected):
        raise ValueError(
            "E2-C4 pilot must run exactly the frozen units "
            f"{sorted(expected)}; prepared {sorted(prepared)}"
        )
    for name, values in prepared.items():
        if values != expected[name]:
            raise ValueError(
                f"unit {name} carries (landscape, d, base) = {values} but the "
                f"frozen battery pins {expected[name]}"
            )
    counts = {name: len(seeds) for name, seeds in seeds_by_unit.items()}
    if set(counts.values()) != {PILOT_SEED_COUNT}:
        raise ValueError(
            "every frozen unit must carry exactly "
            f"{PILOT_SEED_COUNT} distinct seeds; prepared {counts}"
        )


# ── dispersion: the estimands are read as spread only ──


def upper_sd_factor(replicates: int, alpha: float = UPPER_SD_ALPHA) -> float:
    """Sample-SD -> one-sided upper-bound multiplier (V1ED's rule)."""
    if replicates < 2 or not 0.0 < alpha < 1.0:
        raise ValueError("an upper SD bound needs >= 2 replicates and 0 < alpha < 1")
    return math.sqrt((replicates - 1) / float(chi2.ppf(alpha, replicates - 1)))


def paired_dispersion(
    treatment: Mapping[int, float],
    control: Mapping[int, float],
    *,
    alpha: float = UPPER_SD_ALPHA,
) -> dict[str, Any]:
    """Paired-difference spread.

    The mean difference is deliberately neither returned nor computed: with the
    direction unread, "the pilot only measured spread" is a property of the code
    rather than a promise about how it was used.
    """
    seeds = sorted(treatment)
    if seeds != sorted(control):
        raise ValueError(
            "a paired dispersion requires the same seed set in treatment and control"
        )
    if len(seeds) < MIN_REPLICATES:
        raise ValueError("a paired dispersion requires at least three paired replicates")
    differences = [float(treatment[seed]) - float(control[seed]) for seed in seeds]
    if not all(math.isfinite(value) for value in differences):
        raise ValueError("paired dispersion contains a non-finite difference")
    sample_sd = float(np.std(differences, ddof=1))
    return {
        "replicates": len(seeds),
        "paired_sample_sd": sample_sd,
        "upper_sd_alpha": alpha,
        "upper_sample_sd": sample_sd * upper_sd_factor(len(seeds), alpha),
        "rule": (
            "sample_sd uses an n-1 denominator; the upper bound is "
            "sample_sd*sqrt((n-1)/chi2.ppf(alpha, n-1)) (V1ED). No contrast mean "
            "is computed: R depends on SD alone."
        ),
    }


def _series_by_unit(
    rows: Sequence[Mapping[str, Any]],
) -> dict[str, dict[int, Mapping[str, Any]]]:
    by_unit: dict[str, dict[int, Mapping[str, Any]]] = {}
    for row in rows:
        unit = str(row["condition"])
        seed = int(row["seed"])
        if seed in by_unit.setdefault(unit, {}):
            raise RuntimeError(f"duplicate run for unit {unit!r} seed {seed}")
        by_unit[unit][seed] = row
    return by_unit


def pilot_dispersion(
    rows: Sequence[Mapping[str, Any]],
    specs: Sequence[Mapping[str, Any]],
    *,
    alpha: float = UPPER_SD_ALPHA,
) -> dict[str, Any]:
    """Paired-difference spread for every pre-registered contrast and metric."""
    by_unit = _series_by_unit(rows)
    for unit, unit_rows in by_unit.items():
        prepared = sorted(
            int(spec["seed"]) for spec in specs if str(spec["condition"]) == unit
        )
        if sorted(unit_rows) != prepared:
            raise RuntimeError(
                f"unit {unit!r} analysed a different seed set than it was prepared with"
            )
    contrasts: dict[str, Any] = {}
    for contrast in PILOT_CONTRASTS:
        label = str(contrast["label"])
        treatment = str(contrast["treatment"])
        control = str(contrast["control"])
        for unit in (treatment, control):
            if unit not in by_unit:
                raise RuntimeError(f"contrast {label} needs unit {unit!r}")
        metrics = {
            metric: paired_dispersion(
                {seed: float(row[metric]) for seed, row in by_unit[treatment].items()},
                {seed: float(row[metric]) for seed, row in by_unit[control].items()},
                alpha=alpha,
            )
            for metric in E2_C4_EFFECT_METRICS
        }
        contrasts[label] = {
            "claim_bearing": bool(contrast["claim_bearing"]),
            "treatment": treatment,
            "control": control,
            "metrics": metrics,
        }
    return {"contrasts": contrasts}


def wealth_variance_reference(
    by_seed: Mapping[int, Mapping[str, Mapping[str, Any]]],
) -> dict[str, Any]:
    """The ``Var_ref`` reading in the shape the analyser reads by dotted path.

    ``wealth_variance_reference.P2_source_pattern.mean_wealth_variance`` is a hard
    contract (``run_landscape_study.E2_C4_SESOI_REFERENCE_FIELDS``): the E2
    analyser binds this report by sha256 and resolves that path. The field says
    what it is, so a later reader cannot mistake a guard-type level reading for an
    effect size.
    """
    units = {
        unit: {
            "mean_wealth_variance": float(
                np.mean(
                    [
                        float(by_seed[seed][unit]["wealth_variance"])
                        for seed in sorted(by_seed)
                    ]
                )
            )
        }
        for unit in E2_C4_PATTERN_UNITS
    }
    mean_variance = float(
        np.mean([item["mean_wealth_variance"] for item in units.values()])
    )
    if not math.isfinite(mean_variance) or mean_variance <= 0.0:
        raise RuntimeError(
            "the P2 reference variance must be a finite positive number; the "
            "analyser refuses to derive Δ_var from anything else"
        )
    return {
        "P2_source_pattern": {
            "mean_wealth_variance": mean_variance,
            "units": units,
            "role": (
                "P4 guard-type level reading; the reference level of the frozen "
                "rule Δ_var := 0.50 × Var_ref; not an effect size and not for "
                "inference"
            ),
        }
    }


def assert_no_contrast_effects(payload: Mapping[str, Any]) -> None:
    """Structural prohibition: no difference vocabulary anywhere in the report.

    The pilot must not report a contrast mean, direction, interval or p-value, and
    "must not" has to hold by construction rather than by review. Level names
    (``mean_wealth``, ``mean_wealth_variance``, ``unit_mean_wealth``) are P4
    readings and are not in the forbidden set.
    """
    violations: list[str] = []

    def walk(node: Any, path: str) -> None:
        if isinstance(node, Mapping):
            for key, value in node.items():
                if str(key) in FORBIDDEN_EFFECT_KEYS:
                    violations.append(f"{path}.{key}")
                walk(value, f"{path}.{key}")
        elif isinstance(node, (list, tuple)):
            for index, value in enumerate(node):
                walk(value, f"{path}[{index}]")

    walk(payload, "")
    if violations:
        raise RuntimeError(
            "the pilot report contains contrast-effect fields "
            f"{sorted(set(violations))}; the pilot must not read a direction"
        )


# ── the replicate requirement: what the frozen thresholds imply, never R itself ──


def _adjacent_window_scale(block: Mapping[str, Any]) -> float:
    """Recover the scale ``_adjacent_window_summary`` divides by.

    The shared predicate compares ``|mean| + 2*SE`` against
    ``bound * max(|previous mean|, |tail mean|)`` and reports only the ratio, so
    the scale has to be recovered from quantities it does report: the tail
    replicate mean (``independent_replicate_precision.mean``) and the paired window
    difference, whose mean is the *difference* of the two window means. This is the
    same arithmetic the shared function performed, not a re-definition of the
    criterion.
    """
    difference = float(block["adjacent_window_stability"]["signed_mean_difference"])
    tail_mean = float(block["independent_replicate_precision"]["mean"])
    return max(abs(tail_mean), abs(tail_mean - difference), 1e-12)


def steady_replicate_requirements(
    steady_report: Mapping[str, Any],
    *,
    alpha: float = UPPER_SD_ALPHA,
) -> list[dict[str, Any]]:
    """Replicates each frozen steady bound implies, per unit and metric.

    Both predicates are functions of the replicate count, so a frozen R can be too
    small to pass the very contract the confirmatory analysis is gated on. Solving
    each frozen inequality for ``n`` is arithmetic on the report the shared contract
    already emitted — no threshold is chosen here. The adjacent-window predicate is
    ``|mean| + 2*SE <= bound`` rather than ``2*SE <= bound``, so its bound is
    reduced by the measured drift before V1ED's rule is applied to the remainder.
    """
    requirements: list[dict[str, Any]] = []
    conditions = steady_report.get("conditions")
    if not isinstance(conditions, Mapping) or not conditions:
        raise ValueError("steady report contains no conditions")
    for unit, condition in sorted(conditions.items()):
        metrics = condition.get("metrics")
        if not isinstance(metrics, Mapping) or not metrics:
            raise ValueError(f"steady report condition {unit!r} contains no metrics")
        for metric, block in sorted(metrics.items()):
            precision = block["independent_replicate_precision"]
            requirements.append(
                {
                    "constraint": "independent_replicate_precision",
                    "unit": unit,
                    "metric": metric,
                    "bound_kind": precision["bound_kind"],
                    "threshold": float(precision["threshold"]),
                    "measured_at_replicates": int(precision["replicates"]),
                    "required_replicates": int(
                        _required_replicates(
                            sample_sd=float(precision["sample_sd"]),
                            threshold=float(precision["threshold"]),
                            mean=float(precision["mean"]),
                            bound_kind=str(precision["bound_kind"]),
                            current_replicates=int(precision["replicates"]),
                            upper_sd_alpha=alpha,
                        )["conservative_estimate"]
                    ),
                }
            )
            adjacent = block["adjacent_window_stability"]
            scale = _adjacent_window_scale(block)
            bound = float(adjacent["threshold"]) * (
                scale if adjacent["bound_kind"] != "absolute" else 1.0
            )
            drift = abs(float(adjacent["signed_mean_difference"]))
            entry: dict[str, Any] = {
                "constraint": "adjacent_window_stability",
                "unit": unit,
                "metric": metric,
                "bound_kind": adjacent["bound_kind"],
                "threshold": float(adjacent["threshold"]),
                "measured_at_replicates": int(adjacent["replicates"]),
                "resolved_bound": bound,
                "window_drift": drift,
            }
            if bound <= drift:
                # |mean| does not shrink with n, so no replicate count fixes this.
                entry["required_replicates"] = None
                entry["infeasible"] = (
                    "the measured window drift already exceeds the frozen bound; "
                    "replicates cannot reduce |mean|, so the frozen steady contract "
                    "is out of reach for this unit and metric"
                )
            else:
                entry["required_replicates"] = int(
                    _required_replicates(
                        sample_sd=float(adjacent["paired_sample_sd"]),
                        threshold=bound - drift,
                        mean=None,
                        bound_kind="absolute",
                        current_replicates=int(adjacent["replicates"]),
                        upper_sd_alpha=alpha,
                    )["conservative_estimate"]
                )
            requirements.append(entry)
    return requirements


def sesoi_replicate_requirements(
    pilot_report: Mapping[str, Any],
    *,
    gini_delta: float,
    variance_ratio: float,
    alpha: float = UPPER_SD_ALPHA,
) -> tuple[list[dict[str, Any]], float]:
    """Replicates the two frozen Δ values imply, per claim-bearing contrast."""
    variance_reference = float(
        pilot_report["wealth_variance_reference"]["P2_source_pattern"][
            "mean_wealth_variance"
        ]
    )
    delta_variance = float(variance_ratio) * variance_reference
    deltas = {"wealth_gini": float(gini_delta), "wealth_variance": delta_variance}
    requirements: list[dict[str, Any]] = []
    for label, contrast in sorted(pilot_report["paired_dispersion"]["contrasts"].items()):
        if not contrast["claim_bearing"]:
            continue
        for metric in PILOT_CLAIM_METRICS:
            dispersion = contrast["metrics"][metric]
            requirements.append(
                {
                    "constraint": "sesoi",
                    "contrast": label,
                    "metric": metric,
                    "delta": deltas[metric],
                    "measured_at_replicates": int(dispersion["replicates"]),
                    "required_replicates": int(
                        _required_replicates(
                            sample_sd=float(dispersion["paired_sample_sd"]),
                            threshold=deltas[metric],
                            mean=None,
                            bound_kind="absolute",
                            current_replicates=int(dispersion["replicates"]),
                            upper_sd_alpha=alpha,
                        )["conservative_estimate"]
                    ),
                }
            )
    return requirements, delta_variance


def derive_r_replicates(
    pilot_report: Mapping[str, Any],
    steady_report: Mapping[str, Any],
    *,
    gini_delta: float | None = None,
    variance_ratio: float | None = None,
    alpha: float = UPPER_SD_ALPHA,
) -> dict[str, Any]:
    """Turn a finished pilot into the replicate requirement the E2 lock freezes.

    ``R`` is the maximum over three requirement families — the SESOI power rule,
    the frozen independent-replicate precision widths and the frozen adjacent
    window bounds — rounded up to a power of two (V1ED's policy). The steady
    families belong here because ``analysis_gate_pass`` is gated on them: an R that
    ignored them could be too small to pass a contract already frozen before any
    effect was seen. The frozen Δ policy is an argument so the caller must supply
    the recorded values, and it is checked against the pre-registered literals so no
    invocation can quietly re-scale it.
    """
    resolved_gini = FROZEN_GINI_DELTA if gini_delta is None else float(gini_delta)
    resolved_ratio = (
        FROZEN_VARIANCE_RATIO if variance_ratio is None else float(variance_ratio)
    )
    if resolved_gini != FROZEN_GINI_DELTA:
        raise ValueError(
            f"wealth_gini's Δ is frozen at {FROZEN_GINI_DELTA}; got {resolved_gini}"
        )
    if resolved_ratio != FROZEN_VARIANCE_RATIO:
        raise ValueError(
            "the wealth_variance Δ ratio is frozen at "
            f"{FROZEN_VARIANCE_RATIO} (it must also exceed the P4 level-drift "
            f"floor); got {resolved_ratio}"
        )
    sesoi, delta_variance = sesoi_replicate_requirements(
        pilot_report,
        gini_delta=resolved_gini,
        variance_ratio=resolved_ratio,
        alpha=alpha,
    )
    steady = steady_replicate_requirements(steady_report, alpha=alpha)
    precision = [
        item for item in steady if item["constraint"] == "independent_replicate_precision"
    ]
    adjacent = [
        item for item in steady if item["constraint"] == "adjacent_window_stability"
    ]
    infeasible = [item for item in adjacent if item.get("required_replicates") is None]
    if infeasible:
        raise RuntimeError(
            "the frozen adjacent-window bound is out of reach for "
            f"{[(item['unit'], item['metric']) for item in infeasible]}: the "
            "measured window drift already exceeds it, and replicates cannot reduce "
            "|mean|. The steady contract must be re-examined before R is frozen, "
            "not worked around."
        )
    counts = [
        int(item["required_replicates"]) for item in (*sesoi, *precision, *adjacent)
    ]
    if not counts:
        raise ValueError("no replicate requirement could be derived")
    worst = max(counts)
    return {
        "policy": (
            "R = next_power_of_two(max(SESOI power, frozen precision width, frozen "
            "adjacent-window bound)); V1ED's rule throughout, one-sided upper SD at "
            f"alpha={alpha} and a floor of {MIN_REPLICATES} replicates"
        ),
        "delta_wealth_gini": resolved_gini,
        "delta_wealth_variance": delta_variance,
        "delta_wealth_variance_ratio": resolved_ratio,
        "wealth_variance_reference": float(
            pilot_report["wealth_variance_reference"]["P2_source_pattern"][
                "mean_wealth_variance"
            ]
        ),
        "worst_required_replicates": worst,
        "r_replicates": int(_next_power_of_two(worst)),
        "requirements": {
            "sesoi": sesoi,
            "independent_replicate_precision": precision,
            "adjacent_window_stability": adjacent,
        },
    }


# ── run ──


def require_identity_guard(
    identity: Mapping[str, Any], *, output_dir: Path, experiment: str
) -> None:
    """Write the P1 report and stop the batch on any violation.

    The guard is written *before* the verdict is raised so a failed run leaves the
    violated comparisons behind: "positions were not exogenous" is only actionable
    if the (seed, metric, unit) triple is on disk. Raising here is what keeps the
    pilot from producing a dispersion table at all.
    """
    write_json(
        output_dir / "isolation_identity_report.json",
        {"experiment": experiment, **identity},
    )
    if not identity["pass"]:
        raise RuntimeError(
            f"{experiment} P1 isolation identity failed for "
            f"{len(identity['violations'])} (seed, metric) comparisons; positions are "
            "not exogenous, so nothing may be measured. This is an implementation "
            "failure, not a result."
        )


def build_pilot_report(
    *,
    config: Mapping[str, Any],
    config_path: str,
    execution: Mapping[str, Any],
    identity: Mapping[str, Any],
    comparability: Mapping[str, Any],
    dispersion: Mapping[str, Any],
    reference_variance: Mapping[str, Any],
    steady_report: Mapping[str, Any],
    steady_report_sha256: str,
    rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Assemble the report, refusing to do so if the identity guard failed.

    The refusal is duplicated here on purpose: ``require_identity_guard`` already
    stops the batch, and this second barrier makes "no variance table exists for a
    contaminated batch" a property of the assembler rather than of the caller's
    statement order.
    """
    if not identity["pass"]:
        raise RuntimeError(
            "refusing to assemble a pilot dispersion report after a P1 isolation "
            "identity violation"
        )
    instability = [
        str(row.get("run_id", "?"))
        for row in rows
        if not bool(row.get("stationarity_pass"))
    ]
    report = {
        "experiment": EXPERIMENT_ID,
        "role": (
            "non-evidentiary pilot: supplies the dispersion and comparability "
            "readings that freeze E2-C4's replicate count"
        ),
        "not_evidence": (
            "by construction this report contains no contrast mean, direction, "
            "interval or p-value; it must never be cited as evidence for "
            "C3-CHANNELS-C4"
        ),
        "binding": {
            "config": str(config_path),
            "config_sha256": sha256_file(project_path(config_path, must_exist=True)),
            "parameter_lock": PARAMETER_LOCK,
            "reference_binary": str(config["binary"]),
            "reference_binary_sha256": str(config["binary_sha256"]),
        },
        "protocol": {
            **{key: config[key] for key in FROZEN_PROTOCOL},
            "units": [name for name, *_rest in E2_C4_UNITS],
            "seeds": sorted(int(seed) for seed in config["seeds"]),
            "replicates_per_unit": PILOT_SEED_COUNT,
            "seed_window": list(SEED_WINDOW),
            "upper_sd_alpha": UPPER_SD_ALPHA,
            "steady_contract_reference": REFERENCE_EXPERIMENT,
        },
        "run_count": len(rows),
        "execution": dict(execution),
        "stationarity_failures": instability,
        "P1_isolation_identity": dict(identity),
        "P4_comparability": dict(comparability),
        "paired_dispersion": dict(dispersion),
        "wealth_variance_reference": dict(reference_variance),
        "steady_contract_at_pilot_n": {
            "informational": True,
            "gate_role": (
                "not a pilot verdict: the adjacent and precision predicates are "
                "functions of the replicate count, which is the quantity the pilot "
                "determines. They are recorded at the pilot's n, and the R they "
                "imply is derived by --derive-r."
            ),
            "replicates_per_condition": PILOT_SEED_COUNT,
            "pass": bool(steady_report["pass"]),
            "tail_stationarity_valid": bool(steady_report["tail_stationarity_valid"]),
            "adjacent_window_stability_valid": bool(
                steady_report["adjacent_window_stability_valid"]
            ),
            "independent_replicate_precision_valid": bool(
                steady_report["independent_replicate_precision_valid"]
            ),
            "report": STEADY_REPORT_NAME,
            "report_sha256": str(steady_report_sha256),
        },
        "replicate_requirement_policy": (
            "R is NOT recorded here. It is derived after this pilot by "
            "`run_e2_c4_pilot.py --derive-r` from this report plus "
            f"{STEADY_REPORT_NAME}, as the maximum over the SESOI power rule and the "
            "frozen steady bounds, rounded up to a power of two, and frozen in the "
            "E2-C4 design_contract."
        ),
        "pass": bool(
            identity["pass"]
            and not instability
            and all(
                contrast["metrics"][metric]["replicates"] == PILOT_SEED_COUNT
                for contrast in dispersion["contrasts"].values()
                for metric in E2_C4_EFFECT_METRICS
            )
        ),
    }
    assert_no_contrast_effects(report)
    return report


def _run(config_path: str, output_dir_arg: str) -> int:
    require_umi()
    root = PROJECT_ROOT
    config = load_json(project_path(config_path, must_exist=True))
    output_dir = project_path(output_dir_arg)
    output_dir.mkdir(parents=True, exist_ok=True)

    if str(config.get("experiment_id", "")) != EXPERIMENT_ID:
        raise ValueError(f"unexpected experiment_id: {config.get('experiment_id')!r}")
    require_protocol_match(config, reference_protocol(root))

    partition = ledger_seed_partition(root)
    require_frozen_seeds(config.get("seeds", []), consumed_by_others=partition["others"])

    require_locked_binary(config, load_json(root / PARAMETER_LOCK))
    binary = validate_reference_binary(config)

    specs = prepare_inputs(EXPERIMENT_ID, config, output_dir)
    require_frozen_units(specs)
    expected_runs = len(E2_C4_UNITS) * PILOT_SEED_COUNT
    if len(specs) != expected_runs:
        raise RuntimeError(f"expected {expected_runs} runs, prepared {len(specs)}")
    execution = execute_runs(
        specs,
        binary,
        timeout_seconds=int(config.get("per_run_timeout_seconds", 10800)),
        omp_threads=int(config.get("omp_threads", 1)),
        parallel=int(config.get("parallel", 1)),
    )
    rows = analyze_runs(EXPERIMENT_ID, config, output_dir, specs)
    if len(rows) != len(specs):
        raise RuntimeError("analyze_runs did not return one row per run")

    by_seed: dict[int, dict[str, Mapping[str, Any]]] = {}
    for row in rows:
        by_seed.setdefault(int(row["seed"]), {})[str(row["condition"])] = row

    # P1 runs first and aborts the batch: a violated identity guard means positions
    # are not exogenous, so no dispersion table may be written at all.
    identity = e2_c4_identity_report(by_seed)
    require_identity_guard(identity, output_dir=output_dir, experiment=EXPERIMENT_ID)

    comparability = _e2_c4_comparability(by_seed, config)
    dispersion = pilot_dispersion(rows, specs)
    reference_variance = wealth_variance_reference(by_seed)
    steady_report = aggregate_e1_c4_steady_estimand(
        specs,
        config,
        output_dir,
        experiment=EXPERIMENT_ID,
        expected_conditions=[name for name, *_rest in E2_C4_UNITS],
    )
    report = build_pilot_report(
        config=config,
        config_path=config_path,
        execution=execution,
        identity=identity,
        comparability=comparability,
        dispersion=dispersion,
        reference_variance=reference_variance,
        steady_report=steady_report,
        steady_report_sha256=sha256_file(output_dir / STEADY_REPORT_NAME),
        rows=rows,
    )
    write_json(output_dir / PILOT_REPORT_NAME, report)

    print(
        json.dumps(
            {
                "pass": report["pass"],
                "stationarity_failures": len(report["stationarity_failures"]),
                "P4_comparability_pass": bool(comparability["pass"]),
                "wealth_variance_reference": report["wealth_variance_reference"][
                    "P2_source_pattern"
                ]["mean_wealth_variance"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", help="pilot config (run mode)")
    parser.add_argument("--output-dir", help="pilot workspace (run mode)")
    parser.add_argument(
        "--derive-r",
        action="store_true",
        help=(
            "offline: derive the replicate requirement from a finished pilot's two "
            "reports (no simulator, no host check)"
        ),
    )
    parser.add_argument("--pilot-report", help="finished pilot_variance_report.json")
    parser.add_argument("--steady-report", help="finished steady_estimand_report.json")
    parser.add_argument("--gini-delta", type=float, default=None)
    parser.add_argument("--variance-ratio", type=float, default=None)
    parser.add_argument("--out", default=None, help="write JSON here instead of stdout")
    args = parser.parse_args(argv)

    if args.derive_r:
        if not args.pilot_report or not args.steady_report:
            raise SystemExit("--derive-r requires --pilot-report and --steady-report")
        derived = derive_r_replicates(
            load_json(project_path(args.pilot_report, must_exist=True)),
            load_json(project_path(args.steady_report, must_exist=True)),
            gini_delta=args.gini_delta,
            variance_ratio=args.variance_ratio,
        )
        if args.out:
            write_json(project_path(args.out), derived)
        else:
            print(json.dumps(derived, ensure_ascii=False, indent=2))
        return 0

    if not args.config or not args.output_dir:
        raise SystemExit("run mode requires --config and --output-dir")
    return _run(args.config, args.output_dir)


if __name__ == "__main__":
    raise SystemExit(main())
