"""``record-e2`` must promote the verdict, never author it.

The confirmatory payload decides the claim. The recorder's only authority is to
refuse: it re-derives the composition of that payload's own five gates, checks
that a failed P4 comparability gate was carried through as ``inconclusive``
rather than flattened into a null, counts the battery from the run's own markers,
and then copies the artifacts into git byte for byte. These tests mutate each of
those structural claims in turn and require a refusal, then check that the
promotion itself is a copy.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import shutil
import sys

import pytest

from conftest import assert_manifest_is_auditable


REPO_ROOT = Path(__file__).parents[1]
MODULE_PATH = REPO_ROOT / "research" / "src" / "experiments" / "prepare_cycle4_confirmation.py"
sys.path.insert(0, str(MODULE_PATH.parent))
SPEC = importlib.util.spec_from_file_location("prepare_cycle4_confirmation", MODULE_PATH)
assert SPEC and SPEC.loader
recorder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(recorder)

STUDY_PATH = REPO_ROOT / "research" / "src" / "experiments" / "run_landscape_study.py"
STUDY_SPEC = importlib.util.spec_from_file_location("run_landscape_study", STUDY_PATH)
assert STUDY_SPEC and STUDY_SPEC.loader
study = importlib.util.module_from_spec(STUDY_SPEC)
STUDY_SPEC.loader.exec_module(study)

E2_ID = "E2-CHANNEL-ABLATION-C4"
CONFIG = json.loads(
    (REPO_ROOT / "research" / "jobs" / E2_ID / "config.json").read_text(encoding="utf-8")
)
UNITS = list(study.E2_C4_UNIT_NAMES)
SEEDS = [int(seed) for seed in CONFIG["seeds"]]
RUNS = len(UNITS) * len(SEEDS)
SOURCE_COMMIT = "b6d24b76a50529965469332644e7bed251c49eb1"


def _root(tmp_path: Path) -> Path:
    """A project root holding only what ``record_e2`` binds against.

    The lock, the calibration and the config's real SESOI derivation are copied
    because the recorder re-checks the authorization rather than trusting that the
    run must have been authorized to exist.
    """
    root = tmp_path / "root"
    (root / "research" / "jobs").mkdir(parents=True)
    shutil.copyfile(
        REPO_ROOT / "research" / "parameter_lock.e2.json",
        root / "research" / "parameter_lock.e2.json",
    )
    calibration = root / CONFIG["numerical_calibration"]
    calibration.parent.mkdir(parents=True)
    shutil.copyfile(REPO_ROOT / CONFIG["numerical_calibration"], calibration)
    return root


def _payload(
    *,
    gate_pass: bool = True,
    comparability: bool = True,
    eligible=("wealth_gini", "wealth_variance"),
) -> dict:
    gates = {
        "v1f_numerical_calibration": True,
        "three_condition_inputs": True,
        "isolation_identity": True,
        "comparability": comparability,
        "steady_estimand": gate_pass,
    }
    composed = all(gates.values()) if gate_pass else False
    reasons = {
        metric: ["missing_numerical_resolution_limit", "missing_scientific_sesoi"]
        for metric in ("zero_wealth_fraction", "mean_wealth")
        if metric not in eligible
    }
    return {
        "experiment": E2_ID,
        "analysis_gate_pass": composed,
        "claim_supported": bool(composed and eligible),
        "inconclusive": not comparability,
        "gates": gates,
        "P1_isolation_identity": {
            "pass": True,
            "checked_comparisons": 2 * len(SEEDS),
            "violations": [],
        },
        "P4_comparability": {"pass": comparability, "frozen_policy": {}, "units": {}},
        "threshold_provenance": {
            "claim_eligible_metrics": sorted(eligible),
            "descriptive_only_metrics": sorted(
                {"zero_wealth_fraction", "mean_wealth"} - set(eligible)
            ),
            "ineligibility_reasons": reasons,
        },
    }


def _job(
    tmp_path: Path,
    *,
    payload=None,
    workspace_result=None,
    config=None,
    exit_code=0,
    timed_out=False,
    runs_finished=RUNS,
):
    root = _root(tmp_path)
    config = dict(CONFIG if config is None else config)
    job_dir = root / "research" / "jobs" / E2_ID
    workspace = job_dir / "workspace"
    (workspace / "runs").mkdir(parents=True)
    (job_dir / "config.json").write_text(
        json.dumps(config, indent=2) + "\n", encoding="utf-8"
    )
    (job_dir / "seeds.txt").write_text(
        "".join(f"{seed}\n" for seed in SEEDS), encoding="utf-8"
    )
    (job_dir / "commit.txt").write_text(f"{SOURCE_COMMIT}\n", encoding="utf-8")
    (job_dir / "env.txt").write_text("host=umi\nomp_threads=1\n", encoding="utf-8")
    for index in range(runs_finished):
        run_dir = workspace / "runs" / f"run-{index:03d}"
        run_dir.mkdir()
        (run_dir / "completion.json").write_text(
            json.dumps({"status": "completed"}), encoding="utf-8"
        )
    (workspace / "channel_separation.json").write_text(
        json.dumps(_payload() if payload is None else payload, indent=2) + "\n",
        encoding="utf-8",
    )
    for name in (
        "steady_estimand_report.json",
        "isolation_identity_report.json",
        "stationarity_report.json",
        "matched_input_audit.json",
    ):
        (workspace / name).write_text(json.dumps({"pass": True}) + "\n", encoding="utf-8")
    header = "condition,seed,wealth_gini,wealth_variance\n"
    rows = "".join(
        f"{unit},{seed},0.5,0.6\n" for unit in UNITS for seed in SEEDS
    )
    (workspace / "replicate_metrics.csv").write_text(header + rows, encoding="utf-8")
    raw = {
        "experiment": E2_ID,
        "status": "completed",
        "runs_completed": RUNS,
        "runs_executed_this_invocation": RUNS,
        "runs_reused_from_completion_markers": 0,
        "artifacts": sorted(
            f"research/jobs/{E2_ID}/workspace/{name}"
            for name in (*recorder.E2_REQUIRED_ARTIFACTS, "result.json", "run_specs.json")
        ),
        "config_sha256": recorder._sha256(job_dir / "config.json"),
        "parameter_lock_sha256": recorder._sha256(
            root / "research" / "parameter_lock.e2.json"
        ),
        "omp_threads": 1,
        "elapsed_seconds_executed_this_invocation": 1.0,
    }
    raw.update(workspace_result or {})
    (workspace / "result.json").write_text(
        json.dumps(raw, indent=2) + "\n", encoding="utf-8"
    )
    jobctl = root / ".autoresearcher" / "jobs" / E2_ID
    jobctl.mkdir(parents=True)
    (jobctl / "result.json").write_text(
        json.dumps(
            {"exit_code": exit_code, "timed_out": timed_out, "wall_seconds": 3600.0}
        ),
        encoding="utf-8",
    )
    return root, job_dir, jobctl


def _rewrite(path: Path, mutate) -> None:
    payload = json.loads(path.read_text(encoding="utf-8"))
    mutate(payload)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def test_record_e2_promotes_every_artifact_verbatim(tmp_path):
    root, job_dir, jobctl = _job(tmp_path)
    before = {
        name: (job_dir / "workspace" / name).read_bytes()
        for name in recorder.E2_REQUIRED_ARTIFACTS
    }

    outcome = recorder.record_e2(root, job_dir, jobctl)

    assert outcome["analysis_gate_pass"] is True
    assert outcome["claim_supported"] is True
    assert outcome["inconclusive"] is False
    assert outcome["run_count"] == RUNS
    assert outcome["claim_eligible_metrics"] == ["wealth_gini", "wealth_variance"]
    for name, content in before.items():
        assert (job_dir / name).read_bytes() == content, name
    result = json.loads((job_dir / "result.json").read_text(encoding="utf-8"))
    assert result["workspace_result_sha256"] == recorder._sha256(
        job_dir / "workspace" / "result.json"
    )
    assert result["status"] == "completed"
    assert result["non_evidentiary"] is False
    assert result["runs_planned"] == result["runs_completed"] == RUNS
    assert result["replicates_per_unit"] == len(SEEDS)
    assert result["gates"] == dict.fromkeys(recorder.E2_GATE_KEYS, True)
    for name, entry in result["artifacts"].items():
        assert entry["sha256"] == recorder._sha256(job_dir / entry["path"]), name

    assert result["execution_host"] == "umi"
    assert result["source_commit"] == SOURCE_COMMIT
    assert result["binary_sha256"] == CONFIG["binary_sha256"]
    assert set(result["artifacts"]) == set(recorder.E2_REQUIRED_ARTIFACTS)

    manifest = json.loads((job_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["jobctl_reconcile"] == "completed"
    assert {entry["path"] for entry in manifest["artifacts"]} == {
        f"jobs/{E2_ID}/{name}"
        for name in (*recorder.E2_REQUIRED_ARTIFACTS, "result.json")
    }
    assert_manifest_is_auditable(manifest, root)


@pytest.mark.parametrize("exit_code,timed_out", [(1, False), (0, True)])
def test_record_e2_refuses_a_failed_or_timed_out_job(tmp_path, exit_code, timed_out):
    root, job_dir, jobctl = _job(tmp_path, exit_code=exit_code, timed_out=timed_out)
    with pytest.raises(RuntimeError, match="refusing to record"):
        recorder.record_e2(root, job_dir, jobctl)


def test_record_e2_refuses_a_gate_that_does_not_match_its_own_composition(tmp_path):
    """A payload whose verdict is not the conjunction of its gates is incoherent."""
    root, job_dir, jobctl = _job(tmp_path)
    _rewrite(
        job_dir / "workspace" / "channel_separation.json",
        lambda payload: payload.__setitem__("analysis_gate_pass", True),
    )
    _rewrite(
        job_dir / "workspace" / "channel_separation.json",
        lambda payload: payload["gates"].__setitem__("steady_estimand", False),
    )
    with pytest.raises(RuntimeError, match="not the conjunction of its own gates"):
        recorder.record_e2(root, job_dir, jobctl)


def test_record_e2_refuses_a_p4_failure_that_was_not_marked_inconclusive(tmp_path):
    """This is the direction that would manufacture a null out of an artifact."""
    root, job_dir, jobctl = _job(tmp_path)
    _rewrite(
        job_dir / "workspace" / "channel_separation.json",
        lambda payload: (
            payload["gates"].__setitem__("comparability", False),
            payload.__setitem__("analysis_gate_pass", False),
            payload["P4_comparability"].__setitem__("pass", False),
            payload.__setitem__("claim_supported", False),
        ),
    )
    with pytest.raises(RuntimeError, match="not marked inconclusive"):
        recorder.record_e2(root, job_dir, jobctl)


def test_record_e2_accepts_a_p4_failure_that_is_marked_inconclusive(tmp_path):
    """The pre-registered outcome: not-inconclusive is refused, inconclusive is fine.

    A contrast the P4 gate cannot attribute must be reported as inconclusive
    rather than as a null, so the shape is accepted -- and recorded as such.
    """
    root, job_dir, jobctl = _job(tmp_path, payload=_payload(gate_pass=False, comparability=False))
    outcome = recorder.record_e2(root, job_dir, jobctl)
    assert outcome["analysis_gate_pass"] is False
    assert outcome["claim_supported"] is False
    assert outcome["inconclusive"] is True
    assert outcome["gates"]["comparability"] is False
    result = json.loads((job_dir / "result.json").read_text(encoding="utf-8"))
    assert result["P4_comparability"]["pass"] is False
    assert result["status"] == "completed"


def test_record_e2_refuses_a_claim_supported_without_the_gate(tmp_path):
    root, job_dir, jobctl = _job(tmp_path, payload=_payload(gate_pass=False))
    _rewrite(
        job_dir / "workspace" / "channel_separation.json",
        lambda payload: payload.__setitem__("claim_supported", True),
    )
    with pytest.raises(RuntimeError, match="claims support from a failed analysis gate"):
        recorder.record_e2(root, job_dir, jobctl)


def test_record_e2_refuses_an_unregistered_claim_eligible_metric(tmp_path):
    root, job_dir, jobctl = _job(
        tmp_path, payload=_payload(eligible=("wealth_gini", "zero_wealth_fraction"))
    )
    with pytest.raises(RuntimeError, match="did not register as estimands"):
        recorder.record_e2(root, job_dir, jobctl)


def test_record_e2_refuses_an_unstated_demotion(tmp_path):
    payload = _payload(eligible=("wealth_gini",))
    payload["threshold_provenance"]["ineligibility_reasons"] = {}
    root, job_dir, jobctl = _job(tmp_path, payload=payload)
    with pytest.raises(RuntimeError, match="neither claim-eligible nor given an ineligibility"):
        recorder.record_e2(root, job_dir, jobctl)


def test_record_e2_refuses_an_identity_violation(tmp_path):
    root, job_dir, jobctl = _job(tmp_path)
    _rewrite(
        job_dir / "workspace" / "channel_separation.json",
        lambda payload: (
            payload["P1_isolation_identity"].__setitem__("violations", ["occupancy_entropy"]),
            payload["gates"].__setitem__("isolation_identity", False),
            payload.__setitem__("analysis_gate_pass", False),
            payload.__setitem__("claim_supported", False),
        ),
    )
    with pytest.raises(RuntimeError, match="reported violations"):
        recorder.record_e2(root, job_dir, jobctl)


def test_record_e2_counts_the_battery_from_the_run_markers(tmp_path):
    """A summary that claims 80 runs is not the same as 80 finished runs."""
    root, job_dir, jobctl = _job(tmp_path, runs_finished=RUNS - 1)
    with pytest.raises(RuntimeError, match="completed marker"):
        recorder.record_e2(root, job_dir, jobctl)


def test_record_e2_refuses_a_result_that_does_not_list_an_artifact(tmp_path):
    """The run's own manifest must mention every artifact it is supposed to have."""
    hidden = "matched_input_audit.json"
    workspace_result = {
        "artifacts": sorted(
            f"research/jobs/{E2_ID}/workspace/{name}"
            for name in (*recorder.E2_REQUIRED_ARTIFACTS, "result.json")
            if name != hidden
        )
    }
    root, job_dir, jobctl = _job(tmp_path, workspace_result=workspace_result)
    with pytest.raises(RuntimeError, match=f"does not list {hidden}"):
        recorder.record_e2(root, job_dir, jobctl)


def test_record_e2_refuses_a_short_replicate_table(tmp_path):
    root, job_dir, jobctl = _job(tmp_path)
    table = job_dir / "workspace" / "replicate_metrics.csv"
    lines = table.read_text(encoding="utf-8").splitlines()
    table.write_text("\n".join(lines[:-1]) + "\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="was read at"):
        recorder.record_e2(root, job_dir, jobctl)


def test_record_e2_refuses_a_result_recorded_under_another_lock(tmp_path):
    root, job_dir, jobctl = _job(tmp_path, workspace_result={"parameter_lock_sha256": "0" * 64})
    with pytest.raises(RuntimeError, match="produced under another lock"):
        recorder.record_e2(root, job_dir, jobctl)


def test_record_e2_refuses_a_config_that_does_not_bind_the_lock(tmp_path):
    config = dict(CONFIG)
    config["parameter_lock_sha256"] = "0" * 64
    root, job_dir, jobctl = _job(tmp_path, config=config)
    with pytest.raises(RuntimeError, match="does not bind the final E2 lock"):
        recorder.record_e2(root, job_dir, jobctl)


def test_record_e2_refuses_a_seed_list_that_disagrees_with_the_declaration(tmp_path):
    root, job_dir, jobctl = _job(tmp_path)
    (job_dir / "seeds.txt").write_text("12391\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="seeds.txt and config disagree"):
        recorder.record_e2(root, job_dir, jobctl)


def test_record_e2_refuses_a_lock_that_is_not_final(tmp_path):
    root, job_dir, jobctl = _job(tmp_path)
    _rewrite(
        root / "research" / "parameter_lock.e2.json",
        lambda lock: lock.__setitem__("status", "candidate"),
    )
    with pytest.raises(RuntimeError, match="not authorized by a final parameter lock"):
        recorder.record_e2(root, job_dir, jobctl)
