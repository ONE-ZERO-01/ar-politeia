"""E2-C4's frozen declaration set is checked against the code that will run it.

The E2 lock and config are the last artifacts written before an 80-run
confirmatory battery, and every number in them is supposed to be *derived* from
the recorded pilot rather than chosen. A test that only restated the numbers
would be worthless, so each assertion here re-derives the value from the artifact
it claims to come from: R from the pilot's two reports, the variance SESOI from
the rule applied to the reference report's own field, the steady bounds from the
pilot's declaration (whose inequalities R was solved against), and the seeds from
the ledger.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import shutil
import sys

import pytest


REPO_ROOT = Path(__file__).parents[1]
MODULE_PATH = REPO_ROOT / "research" / "src" / "experiments" / "prepare_cycle4_confirmation.py"
sys.path.insert(0, str(MODULE_PATH.parent))
SPEC = importlib.util.spec_from_file_location("prepare_cycle4_confirmation", MODULE_PATH)
assert SPEC and SPEC.loader
prepare = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(prepare)

PILOT_MODULE_PATH = (
    REPO_ROOT / "research" / "src" / "experiments" / "run_e2_c4_pilot.py"
)
PILOT_SPEC = importlib.util.spec_from_file_location(
    "run_e2_c4_pilot", PILOT_MODULE_PATH
)
assert PILOT_SPEC and PILOT_SPEC.loader
pilot_module = importlib.util.module_from_spec(PILOT_SPEC)
PILOT_SPEC.loader.exec_module(pilot_module)

STUDY_PATH = REPO_ROOT / "research" / "src" / "experiments" / "run_landscape_study.py"
STUDY_SPEC = importlib.util.spec_from_file_location("run_landscape_study", STUDY_PATH)
assert STUDY_SPEC and STUDY_SPEC.loader
study = importlib.util.module_from_spec(STUDY_SPEC)
STUDY_SPEC.loader.exec_module(study)

E2_ID = "E2-CHANNEL-ABLATION-C4"
PILOT_ID = "E2-C4-PILOT"
LOCK_RELATIVE = "research/parameter_lock.e2.json"
CALIBRATION_RELATIVE = (
    "research/jobs/V1H-CALIBRATION-EXTENSION-C4/numerical_calibration_extended.json"
)


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _lock() -> dict:
    return _read_json(REPO_ROOT / LOCK_RELATIVE)


def _config() -> dict:
    return _read_json(REPO_ROOT / "research" / "jobs" / E2_ID / "config.json")


def _pilot_result() -> dict:
    return _read_json(REPO_ROOT / "research" / "jobs" / PILOT_ID / "result.json")


def _pilot_report() -> dict:
    return _read_json(REPO_ROOT / "research" / "jobs" / PILOT_ID / "pilot_variance_report.json")


def _pilot_config() -> dict:
    return _read_json(REPO_ROOT / "research" / "jobs" / PILOT_ID / "config.json")


# ── the lock authorizes exactly this experiment, on derived values ──


def test_e2_lock_authorizes_the_confirmatory_run_and_pins_its_own_config():
    lock = _lock()
    config = _config()
    assert lock["status"] == "final"
    assert lock["confirmatory_execution_authorized"] is True
    assert lock["locked_before_confirmatory_outcomes"] is True
    assert lock["authorized_experiments"] == [E2_ID]
    assert config["experiment_id"] == E2_ID
    assert config["parameter_lock"] == LOCK_RELATIVE
    assert config["parameter_lock_sha256"] == prepare._sha256(REPO_ROOT / LOCK_RELATIVE)

    audit = study.audit_parameter_lock(config, lock)
    assert audit["pass"] is True
    assert audit["missing_parameters"] == []
    assert audit["mismatches"] == {}


def test_e2_lock_is_bound_to_the_recorded_pilot_not_to_a_restatement():
    lock = _lock()
    requirement = _read_json(
        REPO_ROOT / "research" / "jobs" / PILOT_ID / "r_requirement.json"
    )
    assert lock["design_contract"]["replicate_requirement"] == requirement
    assert lock["source_commit"] == prepare._e2_source_commit(
        REPO_ROOT / "research" / "jobs" / PILOT_ID
    )

    pilot = lock["design_contract"]["pilot"]
    report_path = REPO_ROOT / pilot["path"]
    assert pilot["path"] == f"research/jobs/{PILOT_ID}/pilot_variance_report.json"
    assert pilot["sha256"] == prepare._sha256(report_path)
    assert pilot["sha256"] == _pilot_result()["artifacts"]["conclusion_sha256"]
    assert pilot["recorded_failures"] == _pilot_result()["per_run_stationarity"][
        "failure_count"
    ]


def test_e2_r_is_the_maximum_family_requirement_rounded_up():
    requirement = _read_json(
        REPO_ROOT / "research" / "jobs" / PILOT_ID / "r_requirement.json"
    )
    required = [
        int(entry["required_replicates"])
        for family in requirement["requirements"].values()
        for entry in family
    ]
    worst = max(required)
    assert worst == requirement["worst_required_replicates"]
    assert requirement["r_replicates"] == pilot_module._next_power_of_two(worst)
    assert int(_lock()["design_contract"]["replicates_per_unit"]) == requirement[
        "r_replicates"
    ]


def test_e2_variance_sesoi_is_the_rule_applied_to_the_pilots_reference_level():
    config = _config()
    derivation = config["scientific_sesoi_derivations"]["wealth_variance"]
    report = _pilot_report()
    reference = report["wealth_variance_reference"]["P2_source_pattern"][
        "mean_wealth_variance"
    ]
    assert set(derivation) == set(study.E2_C4_SESOI_DERIVATION_KEYS)
    assert derivation["reference_field"] == (
        study.E2_C4_SESOI_REFERENCE_FIELDS["wealth_variance"]
    )
    assert derivation["resolved_value"] == pytest.approx(
        derivation["ratio"] * reference, rel=0, abs=0
    )
    assert config["scientific_sesoi"]["wealth_variance"] == derivation["resolved_value"]
    # The whole rule, including its hard floor and the report it reads, is
    # re-checked by the code the confirmatory run itself calls.
    study.validate_e2_c4_sesoi_derivations(config)


def test_e2_variance_sesoi_stays_above_the_level_drift_floor():
    config = _config()
    ratio = config["scientific_sesoi_derivations"]["wealth_variance"]["ratio"]
    band = config["comparability_mean_wealth_relative_band"]
    floor = study.e2_c4_level_drift_variance_floor(band)
    assert floor == pytest.approx(4 * band / (1 + (2 / 3) * band**2), abs=0)
    assert ratio > floor
    assert ratio / floor - 1.0 > 0.20  # the margin the decision was taken with
    # The band is the pilot's frozen policy, not a number chosen for the lock.
    assert band == _pilot_report()["P4_comparability"]["frozen_policy"][
        "mean_wealth_relative_band"
    ]


def test_e2_steady_bounds_are_the_ones_r_was_derived_against():
    """R was solved from the pilot's report, so the config must not re-bound it.

    ``derive_r_replicates`` evaluates the frozen steady inequalities using the
    bounds carried by the pilot's steady report. A confirmatory config with
    different bounds would carry a replicate count nobody derived for it.
    """
    config = _config()
    pilot_config = _pilot_config()
    for key in (
        "independent_precision_absolute_half_widths",
        "independent_precision_relative_half_widths",
        "adjacent_window_absolute_bounds",
        "adjacent_window_relative_bounds",
        "binary",
        "binary_sha256",
    ):
        assert config[key] == pilot_config[key], key
    study._validate_c4_steady_contract(config, E2_ID)


def test_e2_calibration_is_the_extension_and_the_coverage_check_accepts_it():
    config = _config()
    calibration = _read_json(REPO_ROOT / config["numerical_calibration"])
    assert config["numerical_calibration"] == CALIBRATION_RELATIVE
    assert config["numerical_calibration_sha256"] == prepare._sha256(
        REPO_ROOT / CALIBRATION_RELATIVE
    )
    assert calibration["experiment"] == "V1H-CALIBRATION-EXTENSION-C4"
    # V1F recorded but never froze wealth_variance; the lock must say so rather
    # than pretend the pristine artifact would have done.
    assert "wealth_variance" not in _read_json(
        REPO_ROOT / "research/jobs/V1F-NONFLAT-CALIBRATION-C4/numerical_calibration.json"
    )["numerical_resolution_limits"]
    thresholds = study.validate_c4_calibration_coverage(
        calibration,
        config["scientific_sesoi"],
        study.confirmatory_metrics_for_experiment(E2_ID),
        allow_extension=True,
    )
    assert set(thresholds) == {"wealth_gini", "wealth_variance"}
    assert thresholds["wealth_variance"]["effective_claim_threshold"] == pytest.approx(
        max(
            calibration["numerical_resolution_limits"]["wealth_variance"],
            config["scientific_sesoi"]["wealth_variance"],
        )
    )


# ── the seed battery ──


def test_e2_battery_is_five_units_times_r_fresh_seeds_disjoint_from_the_pilot():
    config = _config()
    lock = _lock()
    units = list(study.E2_C4_UNIT_NAMES)
    seeds = [int(seed) for seed in config["seeds"]]
    assert lock["design_contract"]["units"] == units
    assert len(units) == 5
    assert len(seeds) == lock["design_contract"]["replicates_per_unit"]
    assert lock["design_contract"]["run_count"] == len(units) * len(seeds) == 80
    assert lock["design_contract"]["seed_count"] == len(seeds)

    pilot_seeds = {int(seed) for seed in _pilot_config()["seeds"]}
    assert pilot_seeds.isdisjoint(seeds)
    assert all(prepare._is_prime(seed) for seed in seeds)
    assert all(prepare.E2_SEED_WINDOW[0] <= seed <= prepare.E2_SEED_WINDOW[1] for seed in seeds)


def test_e2_seeds_are_the_smallest_unused_primes_and_the_declaration_agrees():
    text = (REPO_ROOT / "research" / "jobs" / E2_ID / "seeds.txt").read_text(
        encoding="utf-8"
    )
    assert [int(line) for line in text.split()] == _config()["seeds"]

    # Re-deriving the choice from the ledger only works while the job's own
    # declaration is excluded from its own input set; the function refuses if a
    # re-run would pick differently.
    assert prepare._e2_seeds(REPO_ROOT, len(_config()["seeds"])) == _config()["seeds"]


def test_e2_declaration_set_is_consistent_with_its_config_and_lock():
    job_dir = REPO_ROOT / "research" / "jobs" / E2_ID
    experiment = _read_json(job_dir / "experiment.json")
    parsed = dict(
        line.split("=", 1)
        for line in (job_dir / "data_checksums.txt").read_text(encoding="utf-8").splitlines()
        if line.strip()
    )
    assert experiment["id"] == E2_ID
    assert experiment["non_evidentiary"] is False
    assert experiment["claim_ids"] == ["C3-CHANNELS-C4"]
    assert experiment["data_checksums"] == parsed
    assert parsed["parameter_lock"] == prepare._sha256(REPO_ROOT / LOCK_RELATIVE)
    assert parsed["dependency_calibration"] == prepare._sha256(
        REPO_ROOT / CALIBRATION_RELATIVE
    )
    assert parsed["reference_binary"] == _config()["binary_sha256"]
    assert experiment["config_sha256"] == prepare._sha256(job_dir / "config.json")
    assert experiment["seeds"] == _config()["seeds"]
    assert experiment["run_count"] == _lock()["design_contract"]["run_count"]
    assert experiment["replicate_count"] == _lock()["design_contract"][
        "replicates_per_unit"
    ]
    assert set(experiment["artifacts"]) == set(
        line
        for line in (job_dir / "outputs.txt").read_text(encoding="utf-8").splitlines()
        if line.strip()
    )
    assert experiment["replicate_requirement"]["r_replicates"] == _lock()[
        "design_contract"
    ]["replicate_requirement"]["r_replicates"]


def test_prepare_e2_is_idempotent_against_the_committed_declaration_set():
    """A second run must reproduce the files byte for byte.

    Anything else means the generator is not a function of the recorded inputs,
    which is the property that makes the declaration auditable at all.
    """
    lock_path = REPO_ROOT / LOCK_RELATIVE
    config_path = REPO_ROOT / "research" / "jobs" / E2_ID / "config.json"
    experiment_path = REPO_ROOT / "research" / "jobs" / E2_ID / "experiment.json"
    before = {
        path: path.read_bytes()
        for path in (
            lock_path,
            config_path,
            experiment_path,
            REPO_ROOT / "research" / "jobs" / E2_ID / "seeds.txt",
            REPO_ROOT / "research" / "jobs" / E2_ID / "data_checksums.txt",
            REPO_ROOT / "research" / "jobs" / E2_ID / "env.txt",
            REPO_ROOT / "research" / "jobs" / E2_ID / "outputs.txt",
            REPO_ROOT / "research" / "jobs" / E2_ID / "computational_strategy.json",
        )
    }
    prepare.prepare_e2(REPO_ROOT)
    for path, content in before.items():
        assert path.read_bytes() == content, path


# ── refusals ──


def _pilot_in(tmp_path: Path) -> Path:
    job_dir = tmp_path / "research" / "jobs" / PILOT_ID
    job_dir.parent.mkdir(parents=True)
    shutil.copytree(REPO_ROOT / "research" / "jobs" / PILOT_ID, job_dir)
    return job_dir


def test_e2_pilot_reader_refuses_a_pilot_recorded_as_unusable(tmp_path):
    job_dir = _pilot_in(tmp_path)
    result = _read_json(job_dir / "result.json")
    result["pass"] = False
    (job_dir / "result.json").write_text(json.dumps(result), encoding="utf-8")
    with pytest.raises(RuntimeError, match="not recorded as usable"):
        prepare._e2_pilot_artifacts(tmp_path)


def test_e2_pilot_reader_refuses_an_identity_that_did_not_hold(tmp_path):
    """An edited report is re-derived from, not trusted: the verdict is re-read.

    The mutation is accompanied by a matching checksum so that the sha gate does
    not answer the question for us -- the identity check has to catch it on its
    own merits.
    """
    job_dir = _pilot_in(tmp_path)
    report = _read_json(job_dir / "pilot_variance_report.json")
    report["P1_isolation_identity"]["pass"] = False
    report["P1_isolation_identity"]["violations"] = ["occupancy_entropy"]
    (job_dir / "pilot_variance_report.json").write_text(
        json.dumps(report), encoding="utf-8"
    )
    result = _read_json(job_dir / "result.json")
    result["artifacts"]["conclusion_sha256"] = prepare._sha256(
        job_dir / "pilot_variance_report.json"
    )
    (job_dir / "result.json").write_text(json.dumps(result), encoding="utf-8")
    with pytest.raises(RuntimeError, match="does not carry a passing P1 identity"):
        prepare._e2_pilot_artifacts(tmp_path)


def test_e2_pilot_reader_refuses_an_edited_report(tmp_path):
    job_dir = _pilot_in(tmp_path)
    report = _read_json(job_dir / "pilot_variance_report.json")
    report["wealth_variance_reference"]["P2_source_pattern"]["mean_wealth_variance"] = 1.0
    (job_dir / "pilot_variance_report.json").write_text(
        json.dumps(report), encoding="utf-8"
    )
    with pytest.raises(RuntimeError, match="does not match the sha256"):
        prepare._e2_pilot_artifacts(tmp_path)


def test_e2_pilot_reader_refuses_a_result_that_disagrees_with_its_derivation(tmp_path):
    job_dir = _pilot_in(tmp_path)
    requirement = _read_json(job_dir / "r_requirement.json")
    requirement["r_replicates"] = 4
    (job_dir / "r_requirement.json").write_text(
        json.dumps(requirement), encoding="utf-8"
    )
    with pytest.raises(RuntimeError, match="disagree"):
        prepare._e2_pilot_artifacts(tmp_path)


def test_e2_pilot_reader_refuses_an_ensemble_contract_that_did_not_pass(tmp_path):
    job_dir = _pilot_in(tmp_path)
    result = _read_json(job_dir / "result.json")
    result["per_run_stationarity"]["ensemble_contract_pass"] = False
    (job_dir / "result.json").write_text(json.dumps(result), encoding="utf-8")
    with pytest.raises(RuntimeError, match="ensemble contract did not pass"):
        prepare._e2_pilot_artifacts(tmp_path)
