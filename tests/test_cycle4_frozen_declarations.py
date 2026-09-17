"""Cycle 4 frozen-declaration integrity.

Cycle 4's authorization is a chain of cross-references between *tracked* files:
a numerical calibration, its archived result, the final parameter lock, and the
experiment declaration that consumes them. Until now nothing in the test suite
pinned those references -- the promotion tests only exercise the generators
against synthetic temporary directories, so a real archive could drift from its
own declaration and every test would still pass.

S14 is the reason this module exists: ``finalize`` once wrote a lock bound to a
binary that had never been calibrated, and the defect survived because no one
mechanically checked the binding. A chain that is only asserted by prose is a
chain that can silently change. Everything here reads tracked files only; it
never touches the simulator, job state, or numeric results.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import sys

import pytest

REPO_ROOT = Path(__file__).parents[1]

CALIBRATION = "research/jobs/V1F-NONFLAT-CALIBRATION-C4/numerical_calibration.json"
CALIBRATION_RESULT = "research/jobs/V1F-NONFLAT-CALIBRATION-C4/result.json"
PARAMETER_LOCK = "research/parameter_lock.cycle4.json"
EXPERIMENT_ID = "E1-MATCHED-LANDSCAPES-C4"
EXPERIMENT_CONFIG = f"research/jobs/{EXPERIMENT_ID}/config.json"
EXPERIMENT_DECLARATION = f"research/jobs/{EXPERIMENT_ID}/experiment.json"
EXPERIMENT_OUTPUTS = f"research/jobs/{EXPERIMENT_ID}/outputs.txt"

C4_EFFECT_METRICS = (
    "resource_density_spearman_rho",
    "density_morans_i",
    "occupancy_entropy",
    "wealth_gini",
)

MODULE_PATH = REPO_ROOT / "research" / "src" / "experiments" / "run_landscape_study.py"
sys.path.insert(0, str(MODULE_PATH.parent))
_SPEC = importlib.util.spec_from_file_location("run_landscape_study", MODULE_PATH)
assert _SPEC and _SPEC.loader
run_landscape_study = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(run_landscape_study)

if not (REPO_ROOT / PARAMETER_LOCK).exists():  # pragma: no cover - branch safety
    pytest.skip(
        "no Cycle 4 parameter lock in this checkout; nothing to guard",
        allow_module_level=True,
    )


def _sha256(relative: str) -> str:
    return hashlib.sha256((REPO_ROOT / relative).read_bytes()).hexdigest()


def _load(relative: str) -> dict:
    return json.loads((REPO_ROOT / relative).read_text())


lock = _load(PARAMETER_LOCK)
calibration = _load(CALIBRATION)
calibration_result = _load(CALIBRATION_RESULT)
config = _load(EXPERIMENT_CONFIG)
declaration = _load(EXPERIMENT_DECLARATION)


def test_lock_calibration_result_hash_matches_the_tracked_bytes():
    # Every layer records the SHA-256 of the layer beneath it; a mismatch means
    # the archived object is not the object that was authorized.
    assert _sha256(CALIBRATION) == lock["numerical_calibration"]["sha256"]
    assert _sha256(CALIBRATION_RESULT) == lock["numerical_calibration"]["result_sha256"]
    assert _sha256(PARAMETER_LOCK) == config["parameter_lock_sha256"]
    assert _sha256(EXPERIMENT_CONFIG) == declaration["config_sha256"]
    assert lock["numerical_calibration"]["path"] == CALIBRATION


def test_calibration_result_is_a_pass_for_the_declared_experiment():
    assert calibration["experiment"] == lock["numerical_calibration"]["experiment"]
    assert calibration["pass"] is True
    assert calibration_result["pass"] is True
    assert calibration_result["experiment"] == calibration["experiment"]
    # The archived result must be the one built from the calibration it names.
    assert calibration_result["calibration_sha256"] == _sha256(CALIBRATION)


def test_one_reference_binary_is_bound_across_every_layer():
    # S14: the lock must bind the calibrated binary *by identity*, and every
    # other layer must name the same artifact.
    calibrated = calibration_result["binary_sha256"]
    assert lock["numerical_calibration"]["reference_binary_sha256"] == calibrated
    assert lock["simulator_validation"]["binary_sha256"] == calibrated
    assert (
        declaration["data_checksums"]["reference_binary"] == calibrated
    ), "the experiment must run the binary the numerical limits were measured on"


def test_lock_is_final_and_authorizes_only_the_declared_experiment():
    assert lock["status"] == "final"
    assert lock["confirmatory_execution_authorized"] is True
    assert lock["authorized_experiments"] == [EXPERIMENT_ID]
    assert lock["locked_before_confirmatory_outcomes"] is True


def test_source_commit_agrees_across_lock_validation_and_declaration():
    assert lock["source_commit"] == lock["simulator_validation"]["validated_commit"]
    assert lock["source_commit"] == declaration["commit_id"]


def test_declared_artifacts_match_the_declaration_lists():
    listed = sorted(
        line for line in (REPO_ROOT / EXPERIMENT_OUTPUTS).read_text().split() if line
    )
    assert sorted(declaration["artifacts"]) == listed


def test_thresholds_are_the_max_of_resolution_limit_and_scientific_sesoi():
    # The calibration bounds numerical error only; the scientific SESOI decides
    # relevance. The two must never be conflated into one number.
    thresholds = run_landscape_study.load_confirmatory_calibration(
        EXPERIMENT_ID, config
    )
    assert thresholds["pass"] is True
    numerical = calibration["numerical_resolution_limits"]
    sesoi = config["scientific_sesoi"]
    for metric in C4_EFFECT_METRICS:
        assert float(numerical[metric]) < float(sesoi[metric]), (
            f"{metric}: the SESOI must dominate the numerical limit, otherwise "
            "the numerical floor would silently become the claim threshold"
        )


def test_shared_code_still_resolves_the_declared_plan_and_gates():
    # Guards the shared analyser against drifting the *authorized* experiment's
    # plan: conditions, steady-gate contract and metric sets are all frozen in
    # the tracked declaration, so any change here fails instead of silently
    # producing a different experiment.
    experiment = EXPERIMENT_ID
    assert [
        condition["name"]
        for condition in run_landscape_study.default_conditions(experiment, config)
    ] == ["clustered", "shuffled"]
    assert run_landscape_study.stationary_metrics_for_experiment(experiment) == (
        "resource_density_spearman_rho",
        "density_morans_i",
        "occupancy_entropy",
        "wealth_gini",
        "wealth_variance",
        "zero_wealth_fraction",
    )
    assert (
        run_landscape_study.confirmatory_metrics_for_experiment(experiment)
        == C4_EFFECT_METRICS
    )
    run_landscape_study._validate_c4_steady_contract(config, experiment)
    assert run_landscape_study.common_cpp_config(config)["base_production"] == pytest.approx(
        0.01
    )
