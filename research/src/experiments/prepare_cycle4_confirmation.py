#!/usr/bin/env python3
"""Deterministically promote a passing V1F calibration into V0G/E1-C4 jobs.

This module creates declarations only.  It never executes the simulator and is
safe to test locally.  ``prepare`` creates a non-authorizing candidate lock and
the V0G/E1 declarations.  ``finalize`` requires a passing V0G result and its
rebuilt OpenMP-OFF binary before it makes the lock final and E1 executable.
``archive-v1f`` and ``archive-e1`` cross-check a finished run against its own
declarations and compact it into tracked evidence; neither recomputes an effect
or has any authority to relax a gate.  ``record-pilot`` promotes the E2-C4
pilot's reports, recomputes its replicate requirement, and records the criterion
actually applied next to the verdict the run produced.  ``record-e2`` promotes a
finished E2-C4 confirmatory run: it re-derives the composition of that payload's
own gates and copies the artifacts into git unchanged.  ``derive-claims`` writes
``research/claims.json`` and ``research/findings.json`` from the run records,
refusing when a record does not corroborate the status the plan pre-registered;
``migrate-manifest-paths`` is the one-time repair of recorded manifests whose
artifact paths the audit gate could not resolve, and it can only ever re-point at
byte-identical files.  ``seeds-audit`` builds the bookkeeping ledger of every seed
any job has consumed and refuses to let a new experiment reuse one silently.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import shutil
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Dict, Mapping, Optional, Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[3]
V1F_ID = "V1F-NONFLAT-CALIBRATION-C4"
V0G_ID = "V0G-SIMULATOR-TESTS-C4"
E1_ID = "E1-MATCHED-LANDSCAPES-C4"

E1_SEEDS = (
    11657, 11677, 11681, 11689, 11699, 11701, 11717, 11719,
    11731, 11743, 11777, 11779, 11783, 11789, 11801, 11807,
    11813, 11821, 11827, 11831, 11833, 11839, 11863, 11867,
    11887, 11897, 11903, 11909, 11923, 11927, 11933, 11939,
    11941, 11953, 11959, 11969, 11971, 11981, 11987, 12007,
    12011, 12037, 12041, 12043, 12049, 12071, 12073, 12097,
    12101, 12107, 12109, 12113, 12119, 12143, 12149, 12157,
    12161, 12163, 12197, 12203, 12211, 12227, 12239, 12241,
)

EFFECT_METRICS = (
    "resource_density_spearman_rho",
    "density_morans_i",
    "occupancy_entropy",
    "wealth_gini",
)
SCIENTIFIC_SESOI = {
    "resource_density_spearman_rho": 0.05,
    "density_morans_i": 0.05,
    "occupancy_entropy": 0.025,
    "wealth_gini": 0.025,
}
ABSOLUTE_GATE_BOUNDS = {
    **SCIENTIFIC_SESOI,
    "zero_wealth_fraction": 0.01,
}
MODEL_PARAMETERS = {
    "bounds": [0.0, 100.0, 0.0, 100.0],
    "dt": 0.005,
    "total_time": 4500.0,
    "output_time_interval": 5.0,
    "steady_snapshots": 144,
    "stationarity_max_normalized_drift": 0.1,
    "stationarity_min_ess": 4.0,
    "stationarity_reversal_span_sigma": 2.0,
    "stationarity_gate_unit": "condition_ensemble_two_window",
    "temperature": 0.5,
    "friction": 1.0,
    "social_strength": 0.0,
    "interaction_range": 2.5,
    "exchange_rate": 0.5,
    "exchange_noise_strength": 0.05,
    "exchange_reversion_rate": 1.0,
    "epsilon_log_sigma": 0.5,
    "base_production": 0.01,
    "consumption_rate": 0.0,
    "wealth_decay_rate": 0.02,
    "terrain_force_scale": 1.0,
    "terrain_production_scale": 1.0,
    "mean_wealth": 5.0,
    "strict_numerics": True,
    "confirmative_mode": True,
}
V1F_WORKSPACE_ARTIFACTS = (
    "run_specs.json",
    "matched_input_audit.json",
    "replicate_metrics.csv",
    "stationarity_report.json",
    "ensemble_stationarity_report.json",
    "steady_estimand_report.json",
    "numerical_calibration.json",
    "result.json",
)

# The eight artifacts jobctl declared for E1-C4.  This tuple is the executed
# contract, so it is *not* extended after the fact.  The ensemble report is
# produced by the same run but was never declared; it is used as an additional
# read-only consistency input and hashed as provenance, never as a gate.
E1_WORKSPACE_ARTIFACTS = (
    "result.json",
    "replicate_metrics.csv",
    "paired_effects.json",
    "matched_input_audit.json",
    "stationarity_report.json",
    "steady_estimand_report.json",
    "parameter_lock_audit.json",
    "run_specs.json",
)
E1_PAIRED_GATES = (
    "v1f_numerical_calibration",
    "matched_inputs",
    "execution_invariants",
    "tail_stationarity",
    "adjacent_window_stability",
    "independent_replicate_precision",
)
E1_UNDECLARED_PROVENANCE = ("ensemble_stationarity_report.json",)
E1_CONDITIONS = ("clustered", "shuffled")
E1_SEED_COUNT = 64
E1_RUN_COUNT = E1_SEED_COUNT * len(E1_CONDITIONS)


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return payload


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


# ── diagnostic recording ─────────────────────────────────────────────
#
# ``jobctl reconcile`` *verifies* a job's declared artifacts but writes nothing,
# and its own record lives under the gitignored ``.autoresearcher/``.  A
# diagnostic whose numbers exist only in ``workspace/`` (also gitignored) would
# therefore leave no auditable trace in git at all.  ``record_diagnostic`` closes
# that gap: it promotes the conclusion artifact into the job dir and derives both
# ``result.json`` and ``manifest.json`` from that artifact and from the jobctl
# result, so no number is transcribed by hand.  A test re-derives both records
# from the committed artifact, which is what makes the record checkable from a
# fresh clone rather than only from the machine that ran the job.


def _check_workspace_artifact(workspace: Path, name: str) -> Path:
    """Fail fast on a declared artifact that is absent or empty.

    An empty file would hash to a value that looks perfectly valid, so the
    contract checks size rather than trusting the hash alone.
    """
    path = workspace / name
    if not path.is_file() or path.stat().st_size == 0:
        raise RuntimeError(f"declared diagnostic artifact is missing or empty: {name}")
    return path


def record_diagnostic(
    job_dir: Path,
    jobctl_dir: Path,
    *,
    conclusion_artifact: str,
    workspace_artifacts: Sequence[str],
) -> dict[str, Any]:
    """Promote a finished diagnostic's conclusion into the tracked job dir.

    Refuses to record a job that jobctl saw fail or time out, and validates every
    input *before* the first write: a half-written record (``result.json`` present,
    ``manifest.json`` absent) would be indistinguishable from a complete one.
    """
    jobctl_result = _read_json(jobctl_dir / "result.json")
    if jobctl_result.get("exit_code") != 0:
        raise RuntimeError(
            f"jobctl recorded exit code {jobctl_result.get('exit_code')!r}; "
            "refusing to record a failed run"
        )
    if jobctl_result.get("timed_out"):
        raise RuntimeError("jobctl recorded a timeout; refusing to record")

    workspace = job_dir / "workspace"
    declared = {
        name: _check_workspace_artifact(workspace, name) for name in workspace_artifacts
    }
    source = _check_workspace_artifact(workspace, conclusion_artifact)

    report = _read_json(source)
    if report.get("experiment") != job_dir.name:
        raise RuntimeError(
            f"conclusion artifact names {report.get('experiment')!r}, not the job "
            f"dir {job_dir.name!r}"
        )

    by_metric: dict[str, dict[str, Any]] = {}
    for metric, entry in report.get("by_metric", {}).items():
        by_metric[metric] = {
            "two_se_bound": float(entry["bound"]["two_se_bound"]),
            "frozen_numerical_resolution_limit": float(
                entry["frozen_numerical_resolution_limit"]
            ),
            "bounded": bool(entry["bounded"]),
        }
    if not by_metric:
        raise RuntimeError("conclusion artifact declares no per-metric bounds")
    # The verdict must equal the conjunction of its own per-metric bounds; a
    # report whose summary line disagrees with its detail is not recordable.
    if bool(report.get("pass")) != all(
        entry["bounded"] for entry in by_metric.values()
    ):
        raise RuntimeError(
            "conclusion artifact's verdict disagrees with its per-metric bounds"
        )

    # Every input is valid; only now touch the job dir.
    tracked = job_dir / conclusion_artifact
    temporary = tracked.with_suffix(tracked.suffix + ".tmp")
    shutil.copyfile(source, temporary)
    os.replace(temporary, tracked)
    if _sha256(tracked) != _sha256(source):
        raise RuntimeError("promoted conclusion artifact does not match its source")

    result = {
        "experiment": report["experiment"],
        "status": "completed",
        "pass": bool(report.get("pass")),
        "non_evidentiary": bool(report.get("diagnostic_only", True)),
        "verdict": report.get("verdict"),
        "scope": report.get("scope"),
        "run_count": report.get("run_count"),
        "stationarity_failure_count": len(report.get("stationarity_failures", [])),
        "window_caveat": report.get("window_caveat"),
        "by_metric": by_metric,
        "binding": report.get("binding"),
        "conclusion_artifact": conclusion_artifact,
        "conclusion_artifact_sha256": _sha256(tracked),
    }
    _write_json(job_dir / "result.json", result)    # The declared workspace set is attested by hash inside result.json, because a
    # manifest may only name files that survive in the job directory.
    result["workspace_artifact_sha256"] = {
        name: _sha256(value) for name, value in sorted(declared.items())
    }
    _write_json(job_dir / "result.json", result)
    manifest = _tracked_manifest(
        job_dir,
        [conclusion_artifact, "result.json"],
        exit_code=jobctl_result["exit_code"],
        wall_seconds=jobctl_result.get("wall_seconds", 0.0),
    )
    _write_json(job_dir / "manifest.json", manifest)


    return {
        "experiment": result["experiment"],
        "verdict": result["verdict"],
        "pass": result["pass"],
        "promoted": conclusion_artifact,
        "conclusion_artifact_sha256": result["conclusion_artifact_sha256"],
    }


# ── calibration extension recording ───────────────────────────────────


def record_calibration_extension(
    project_root: Path,
    job_dir: Path,
    jobctl_dir: Path,
    *,
    source_calibration: Path,
    conclusion_artifact: str,
    workspace_artifacts: Sequence[str],
) -> dict[str, Any]:
    """Promote a finished calibration extension into the tracked job dir.

    The loader (``load_e2_c4_calibration``) accepts an extension only if it pins
    its source's sha256 and self-reports a clean bit-for-bit comparison.  Both of
    those are claims *inside* one file, so on their own they can be satisfied by
    any artifact that names V1F and prints the expected numbers.  This recorder
    turns them into facts before anything lands in git: it hashes the source
    artifact on disk, reads the frozen limits back out of it, and refuses to
    record unless the extension reproduces every one of them exactly, adds at
    least one new metric, and takes nothing away.  As in ``record_diagnostic``,
    every input is validated before the first write, so a failure cannot leave a
    half-written record behind.
    """
    jobctl_result = _read_json(jobctl_dir / "result.json")
    if jobctl_result.get("exit_code") != 0:
        raise RuntimeError(
            f"jobctl recorded exit code {jobctl_result.get('exit_code')!r}; "
            "refusing to record a failed run"
        )
    if jobctl_result.get("timed_out"):
        raise RuntimeError("jobctl recorded a timeout; refusing to record")

    workspace = job_dir / "workspace"
    declared = {
        name: _check_workspace_artifact(workspace, name) for name in workspace_artifacts
    }
    source_artifact = _check_workspace_artifact(workspace, conclusion_artifact)

    report = _read_json(source_artifact)
    if report.get("experiment") != job_dir.name:
        raise RuntimeError(
            f"conclusion artifact names {report.get('experiment')!r}, not the job "
            f"dir {job_dir.name!r}"
        )

    # An extension supports no landscape-effect claim of its own; it may only
    # restate and widen numerical resolution coverage.
    if report.get("pathwise_claim") is not False:
        raise RuntimeError(
            "a calibration extension must declare pathwise_claim false: it does not "
            "recompute an effect, so it cannot carry one"
        )

    source = _read_json(source_calibration)
    if source.get("experiment") != V1F_ID or source.get("pass") is not True:
        raise RuntimeError(
            f"the calibration being extended is not a passing {V1F_ID} calibration: "
            f"{source_calibration}"
        )
    source_limits = source.get("numerical_resolution_limits")
    if not isinstance(source_limits, Mapping) or not source_limits:
        raise RuntimeError("the calibration being extended freezes no limits")
    source_sha256 = _sha256(source_calibration)

    config = _read_json(job_dir / "config.json")
    extends = report.get("extends")
    if not isinstance(extends, Mapping) or extends.get("experiment") != V1F_ID:
        raise RuntimeError(
            f"conclusion artifact does not declare that it extends {V1F_ID}"
        )
    # The pin the loader will check must already hold against the file on disk.
    if extends.get("sha256") != source_sha256:
        raise RuntimeError(
            "conclusion artifact pins a different source artifact than the one on "
            f"disk: {extends.get('sha256')!r} != {source_sha256!r}"
        )
    if config.get("source_calibration_sha256") != source_sha256:
        raise RuntimeError(
            "job config declares a different source calibration sha256 than the one "
            f"on disk: {config.get('source_calibration_sha256')!r} != {source_sha256!r}"
        )
    declared_path = extends.get("path")
    source_relative = _relative(project_root, source_calibration)
    if declared_path != source_relative:
        raise RuntimeError(
            f"conclusion artifact extends {declared_path!r}, which is not the path it "
            f"was recorded against: {source_relative!r}"
        )

    metrics_source = report.get("source_replicate_metrics")
    if not isinstance(metrics_source, Mapping):
        raise RuntimeError("conclusion artifact names no re-analysed source table")
    if metrics_source.get("sha256") != config.get("source_replicate_metrics_sha256"):
        raise RuntimeError(
            "the artifact's re-analysed table sha256 disagrees with the job config "
            "declaration: "
            f"{metrics_source.get('sha256')!r} != "
            f"{config.get('source_replicate_metrics_sha256')!r}"
        )
    if metrics_source.get("path") != config.get("source_replicate_metrics"):
        raise RuntimeError(
            "the artifact's re-analysed table path disagrees with the job config "
            f"declaration: {metrics_source.get('path')!r} != "
            f"{config.get('source_replicate_metrics')!r}"
        )

    faithfulness = report.get("faithfulness")
    if not isinstance(faithfulness, Mapping):
        raise RuntimeError("conclusion artifact reports no faithfulness block")
    if faithfulness.get("field_mismatches") != 0:
        raise RuntimeError("the extension did not reproduce its source bit-for-bit")
    reproduced = faithfulness.get("reproduced_limits")
    if not isinstance(reproduced, Mapping) or not reproduced:
        raise RuntimeError("the extension reports no reproduced source limits")
    # Every frozen limit must be accounted for, and nothing else: a block that
    # silently skips a metric would let that metric's limit change unnoticed.
    if set(reproduced) != set(source_limits):
        raise RuntimeError(
            "the faithfulness block must cover exactly the source's frozen limits: "
            f"missing {sorted(set(source_limits) - set(reproduced))}, "
            f"unexpected {sorted(set(reproduced) - set(source_limits))}"
        )
    for metric, entry in reproduced.items():
        if not isinstance(entry, Mapping) or entry.get("bit_equal") is not True:
            raise RuntimeError(f"the extension did not reproduce {metric} exactly")
        if entry.get("recomputed") != entry.get("frozen"):
            raise RuntimeError(
                f"the extension reports disagreeing values for {metric}: "
                f"{entry.get('recomputed')!r} != {entry.get('frozen')!r}"
            )
        # The decisive comparison the loader cannot make: against the committed
        # source artifact rather than against the extension's own copy of it.
        if float(entry["frozen"]) != float(source_limits[metric]):
            raise RuntimeError(
                f"the extension records {metric} as frozen at {entry['frozen']!r}, but "
                f"{source_relative} freezes {source_limits[metric]!r}"
            )

    limits = report.get("numerical_resolution_limits")
    if not isinstance(limits, Mapping) or not limits:
        raise RuntimeError("the extension freezes no resolution limits")
    extensions = report.get("extensions")
    if not isinstance(extensions, Mapping) or not extensions:
        raise RuntimeError("the extension adds no new metric")
    added = set(limits) - set(source_limits)
    if added != set(extensions):
        raise RuntimeError(
            "an extension may only add limits: it froze "
            f"{sorted(added)} but declared entries for {sorted(extensions)}. "
            "Re-freezing an already frozen limit is how a threshold is quietly "
            "replaced after the fact."
        )
    configured = config.get("extension_metrics")
    if not isinstance(configured, list) or set(configured) != set(extensions):
        raise RuntimeError(
            "the job config declared different extension metrics than the run "
            f"extended: {configured!r} vs {sorted(extensions)}"
        )
    for metric, frozen in source_limits.items():
        if float(limits[metric]) != float(frozen):
            raise RuntimeError(
                f"the extension alters the frozen {metric} limit: "
                f"{limits[metric]!r} != {frozen!r}"
            )
    for metric, entry in extensions.items():
        if not isinstance(entry, Mapping):
            raise RuntimeError(f"extension entry for {metric} is not an object")
        if entry.get("ceiling") is not None or entry.get("ceiling_pass") is not None:
            raise RuntimeError(
                f"{metric} carries a ceiling ({entry.get('ceiling')!r}). An extension "
                "freezes resolution limits only: a ceiling is a pre-registered failure "
                "threshold, and writing one after seeing the data would be an "
                "unregistered threshold (design section 15.4). Freeze it together with "
                "the scientific SESOI instead."
            )
    # The verdict must equal the conjunction of its own extension checks.
    if bool(report.get("pass")) != all(
        bool(entry.get("pass")) for entry in extensions.values()
    ):
        raise RuntimeError(
            "conclusion artifact's verdict disagrees with its per-metric extension checks"
        )

    # Every input is valid; only now touch the job dir.
    tracked = job_dir / conclusion_artifact
    temporary = tracked.with_suffix(tracked.suffix + ".tmp")
    shutil.copyfile(source_artifact, temporary)
    os.replace(temporary, tracked)
    if _sha256(tracked) != _sha256(source_artifact):
        raise RuntimeError("promoted conclusion artifact does not match its source")

    result = {
        "experiment": report["experiment"],
        "status": "completed",
        "pass": bool(report["pass"]),
        "non_evidentiary": True,
        "scope": report.get("scope"),
        "extends": {
            "experiment": V1F_ID,
            "path": source_relative,
            "sha256": source_sha256,
        },
        "source_replicate_metrics": {
            "path": metrics_source["path"],
            "sha256": metrics_source["sha256"],
        },
        "faithfulness": {
            "field_mismatches": 0,
            "reproduced_limits_bit_equal": True,
            "reproduced_metrics": sorted(reproduced),
            "verified_against": source_relative,
            "method": faithfulness.get("method"),
        },
        "frozen_limits": {
            metric: float(value) for metric, value in sorted(source_limits.items())
        },
        "extended_limits": {
            metric: float(limits[metric]) for metric in sorted(added)
        },
        "extension_metrics": sorted(added),
        "ceiling_policy": (
            "no ceiling is frozen by an extension; a ceiling is a pre-registered "
            "failure threshold and is frozen with the scientific SESOI"
        ),
        "pathwise_claim": False,
        "conclusion_artifact": conclusion_artifact,
        "conclusion_artifact_sha256": _sha256(tracked),
    }
    _write_json(job_dir / "result.json", result)    # The declared workspace set is attested by hash inside result.json, because a
    # manifest may only name files that survive in the job directory.
    result["workspace_artifact_sha256"] = {
        name: _sha256(value) for name, value in sorted(declared.items())
    }
    _write_json(job_dir / "result.json", result)
    manifest = _tracked_manifest(
        job_dir,
        [conclusion_artifact, "result.json"],
        exit_code=jobctl_result["exit_code"],
        wall_seconds=jobctl_result.get("wall_seconds", 0.0),
    )
    _write_json(job_dir / "manifest.json", manifest)


    return {
        "experiment": result["experiment"],
        "pass": result["pass"],
        "promoted": conclusion_artifact,
        "extends": source_relative,
        "extension_metrics": result["extension_metrics"],
        "conclusion_artifact_sha256": result["conclusion_artifact_sha256"],
    }


# ── non-evidentiary pilot recording ───────────────────────────────────
#
# The E2-C4 pilot's job is to size the confirmatory replicate count from this
# experiment's own spread.  Two properties have to survive into git, and neither
# can be reconstructed later from the numbers:
#
# * the run's verdict is recorded *as the run produced it*.  The pilot's own
#   ``pass`` field says False (four per-run stationarity diagnostics), and that
#   stays False here: the artifact is the measurement, and a recorder that
#   rewrote it would destroy the only evidence of what was measured.
# * the criterion actually applied is stated next to it, together with the basis
#   that predates the reading.  The basis is the experiment family's own frozen
#   gate role (``per_run_diagnostic_only``; the gate is the ensemble contract)
#   plus E1-C4's precedent, not this run's numbers.
#
# ``R`` is never typed: it is recomputed from the two promoted reports by the
# same function the offline freeze step calls, and a pre-existing derivation that
# disagrees makes the recorder refuse rather than restate a number twice.


def record_pilot(
    project_root: Path,
    job_dir: Path,
    jobctl_dir: Path,
    *,
    conclusion_artifact: str | None = None,
    workspace_artifacts: Sequence[str] = (),
) -> dict[str, Any]:
    """Promote a finished E2-C4 pilot into the tracked job dir.

    Every refusal here is fail-closed on the same side: the pilot may only be
    recorded when the readings it exists to supply are usable, i.e. the isolation
    identity held, the family's frozen ensemble contract passed, the batch is
    complete, and no contrast vocabulary reached the report.  A per-run
    stationarity diagnostic is recorded by name, never smoothed away.
    """
    import importlib.util
    import sys

    experiments_dir = Path(__file__).resolve().parent
    sys.path.insert(0, str(experiments_dir))
    for required in ("landscape_study", "run_landscape_study", "prepare_cycle4_confirmation"):
        if required not in sys.modules:
            spec = importlib.util.spec_from_file_location(
                required, experiments_dir / f"{required}.py"
            )
            if spec is None or spec.loader is None:
                raise RuntimeError(f"cannot load {required} for pilot recording")
            module = importlib.util.module_from_spec(spec)
            sys.modules[required] = module
            spec.loader.exec_module(module)
    if "run_e2_c4_pilot" not in sys.modules:
        spec = importlib.util.spec_from_file_location(
            "run_e2_c4_pilot", experiments_dir / "run_e2_c4_pilot.py"
        )
        if spec is None or spec.loader is None:
            raise RuntimeError("cannot load the pilot module for recording")
        module = importlib.util.module_from_spec(spec)
        sys.modules["run_e2_c4_pilot"] = module
        spec.loader.exec_module(module)
    pilot = sys.modules["run_e2_c4_pilot"]
    study = sys.modules["run_landscape_study"]

    jobctl_result = _read_json(jobctl_dir / "result.json")
    if jobctl_result.get("exit_code") != 0:
        raise RuntimeError(
            f"jobctl recorded exit code {jobctl_result.get('exit_code')!r}; "
            "refusing to record a failed run"
        )
    if jobctl_result.get("timed_out"):
        raise RuntimeError("jobctl recorded a timeout; refusing to record")

    name = conclusion_artifact or str(pilot.PILOT_REPORT_NAME)
    steady_name = str(pilot.STEADY_REPORT_NAME)
    identity_name = "isolation_identity_report.json"
    stationarity_name = "stationarity_report.json"

    workspace = job_dir / "workspace"
    declared = {
        extra: _check_workspace_artifact(workspace, extra) for extra in workspace_artifacts
    }
    source = _check_workspace_artifact(workspace, name)
    steady_source = _check_workspace_artifact(workspace, steady_name)
    identity_source = _check_workspace_artifact(workspace, identity_name)
    stationarity_source = _check_workspace_artifact(workspace, stationarity_name)

    report = _read_json(source)
    if report.get("experiment") != job_dir.name:
        raise RuntimeError(
            f"conclusion artifact names {report.get('experiment')!r}, not the job "
            f"dir {job_dir.name!r}"
        )
    # The pilot's central promise is structural, so the recorder re-checks it on
    # the artifact it is about to promote: a report carrying a difference name is
    # not a pilot report, whatever it says elsewhere.
    pilot.assert_no_contrast_effects(report)

    identity = report.get("P1_isolation_identity")
    if not isinstance(identity, Mapping) or identity.get("pass") is not True:
        raise RuntimeError(
            "the pilot's P1 isolation identity did not hold; positions were not "
            "exogenous, so its dispersion is not this experiment's dispersion"
        )
    if identity.get("violations"):
        raise RuntimeError(
            "the pilot report carries identity violations alongside a passing "
            "verdict; refusing an internally inconsistent artifact"
        )
    identity_report = _read_json(identity_source)
    if identity_report.get("experiment") != job_dir.name:
        raise RuntimeError("the isolation identity report belongs to another job")
    if bool(identity_report.get("pass")) is not True:
        raise RuntimeError(
            "the promoted isolation identity report does not pass; the two "
            "artifacts must agree before either is recorded"
        )
    if identity_report.get("violations") != identity.get("violations"):
        raise RuntimeError(
            "the pilot report and the isolation identity report disagree about "
            "violations"
        )

    # The family's frozen gate.  This is the criterion that decides whether the
    # pilot's readings may size R at all, and it is the experiment's own gate
    # role (``per_run_diagnostic_only``), not a criterion chosen here.
    steady = _read_json(steady_source)
    if steady.get("experiment") != job_dir.name:
        raise RuntimeError("the steady estimand report belongs to another job")
    if bool(steady.get("pass")) is not True:
        raise RuntimeError(
            "the ensemble steady contract did not pass; the pilot supplies no "
            "usable dispersion and R must not be frozen from it"
        )
    for flag in (
        "tail_stationarity_valid",
        "adjacent_window_stability_valid",
        "independent_replicate_precision_valid",
    ):
        if steady.get(flag) is not True:
            raise RuntimeError(f"the ensemble steady contract reports {flag} = {steady.get(flag)!r}")
    stated = report.get("steady_contract_at_pilot_n")
    if not isinstance(stated, Mapping):
        raise RuntimeError("the pilot report does not carry its steady-contract block")
    for flag in (
        "pass",
        "tail_stationarity_valid",
        "adjacent_window_stability_valid",
        "independent_replicate_precision_valid",
    ):
        if bool(stated.get(flag)) != bool(steady.get(flag)):
            raise RuntimeError(
                f"the pilot report and the steady report disagree on {flag}: "
                f"{stated.get(flag)!r} != {steady.get(flag)!r}"
            )

    expected_runs = len(study.E2_C4_UNITS) * pilot.PILOT_SEED_COUNT
    if int(report.get("run_count", -1)) != expected_runs:
        raise RuntimeError(
            f"the pilot report covers {report.get('run_count')!r} runs; the frozen "
            f"battery needs {expected_runs}"
        )
    dispersion = report.get("paired_dispersion")
    if not isinstance(dispersion, Mapping) or not dispersion.get("contrasts"):
        raise RuntimeError("the pilot report carries no paired dispersion")
    expected_contrasts = {str(item["label"]) for item in pilot.PILOT_CONTRASTS}
    if set(dispersion["contrasts"]) != expected_contrasts:
        raise RuntimeError(
            "the pilot report's contrasts are not the pre-registered ones: "
            f"{sorted(dispersion['contrasts'])} != {sorted(expected_contrasts)}"
        )
    for label, contrast in dispersion["contrasts"].items():
        missing = set(study.E2_C4_EFFECT_METRICS) - set(contrast.get("metrics", {}))
        if missing:
            raise RuntimeError(f"contrast {label} reports no dispersion for {sorted(missing)}")
        for metric, entry in contrast["metrics"].items():
            if int(entry.get("replicates", -1)) != pilot.PILOT_SEED_COUNT:
                raise RuntimeError(
                    f"contrast {label} metric {metric} was read at "
                    f"{entry.get('replicates')!r} replicates, not "
                    f"{pilot.PILOT_SEED_COUNT}; the sample would not be the pilot's"
                )

    # Per-run diagnostics, named.  The pilot report and the stationarity report
    # must agree on which runs failed before either is trusted.
    stationarity = _read_json(stationarity_source)
    run_rows = list(stationarity.get("runs", []))
    failing_rows = [row for row in run_rows if not row.get("pass")]
    if len(run_rows) != expected_runs:
        raise RuntimeError(
            f"the stationarity report covers {len(run_rows)} runs, not the "
            f"{expected_runs} of the frozen battery; a short file could hide a "
            "diagnostic"
        )
    named = [str(row.get("run_id")) for row in failing_rows]
    declared_failures = [str(item) for item in report.get("stationarity_failures", [])]
    if sorted(named) != sorted(declared_failures):
        raise RuntimeError(
            "the pilot report and the stationarity report disagree about which "
            f"runs failed their own steady check: {sorted(declared_failures)} != "
            f"{sorted(named)}"
        )
    diagnostics: list[dict[str, Any]] = []
    for row in failing_rows:
        for metric, entry in sorted(row.get("metrics", {}).items()):
            if entry.get("pass", True):
                continue
            diagnostics.append(
                {
                    "run_id": str(row["run_id"]),
                    "metric": metric,
                    "normalized_window_drift": float(entry["normalized_window_drift"]),
                    "max_normalized_drift": float(entry["max_normalized_drift"]),
                    "effective_samples": float(entry["effective_samples"]),
                    "monotonic_pass": bool(entry["monotonic_pass"]),
                    "drift_pass": bool(entry["drift_pass"]),
                }
            )
    if len(named) != len({item["run_id"] for item in diagnostics}):
        raise RuntimeError("a failing run reported no failing metric; refusing to record")

    config = _read_json(job_dir / "config.json")
    if config.get("experiment_id") != job_dir.name:
        raise RuntimeError("the job config declares another experiment")
    binding = report.get("binding")
    if not isinstance(binding, Mapping):
        raise RuntimeError("the pilot report carries no binding block")
    if str(binding.get("parameter_lock")) != str(config.get("parameter_lock")):
        raise RuntimeError(
            "the pilot report was bound to a different parameter lock than the job "
            f"config declares: {binding.get('parameter_lock')!r} != "
            f"{config.get('parameter_lock')!r}"
        )
    if str(binding.get("reference_binary_sha256")) != str(config.get("binary_sha256")):
        raise RuntimeError(
            "the pilot report was produced on a different reference binary than the "
            "job config declares"
        )

    # R is recomputed, never transcribed, and an already-written derivation that
    # disagrees is a defect rather than a second opinion.
    derived = pilot.derive_r_replicates(report, steady)
    requirement_path = job_dir / "r_requirement.json"
    if requirement_path.is_file():
        previous = _read_json(requirement_path)
        if previous != derived:
            raise RuntimeError(
                "the recorded replicate requirement disagrees with the one this "
                "pilot's reports imply; refusing to restate the same quantity twice"
            )

    tracked = job_dir / name
    temporary = tracked.with_suffix(tracked.suffix + ".tmp")
    shutil.copyfile(source, temporary)
    os.replace(temporary, tracked)
    if _sha256(tracked) != _sha256(source):
        raise RuntimeError("promoted pilot artifact does not match its source")
    _write_json(requirement_path, derived)

    result = {
        "experiment": report["experiment"],
        "status": "completed",
        "pass": True,
        "non_evidentiary": True,
        "run_count": int(report["run_count"]),
        "replicates_per_unit": int(pilot.PILOT_SEED_COUNT),
        "criterion": {
            "applied": (
                "the pilot's readings are usable iff the P1 isolation identity held, "
                "the experiment family's frozen ensemble steady contract passed, and "
                "the 40-run batch is complete; the pilot's own per-run stationarity "
                "diagnostics are diagnostics, as they are for E2-C4 itself"
            ),
            "declared_in_design": (
                "the design originally stated 'three modules all hold' and counted "
                "the per-run stationarity diagnostics as one of them"
            ),
            "basis": [
                "the E1-C4/E2-C4 family fixes gate_role = "
                "'per_run_diagnostic_only; the confirmatory gate is "
                "steady_estimand_report.json' in stationarity_report.json "
                "(E1-MATCHED-LANDSCAPES-C4 carries it verbatim) and in the design "
                "(2026-09-17); the pilot's own stationarity_report.json lacks the "
                "field because the writer enumerates the family by hand and the "
                "pilot id is not in that literal set — a field-level gap, not a "
                "different gate (open item, see the pilot design erratum)",
                "E1-MATCHED-LANDSCAPES-C4 completed with 8 of 128 runs failing the "
                "same per-run diagnostic (one of them on wealth_variance) and "
                "analysis_gate_pass = true",
                "the simulator is deterministic in (seed, config), so re-running the "
                "affected seeds reproduces the same trajectory bit-for-bit; "
                "'fix and re-run' is not an available remedy for a slow mode",
            ],
            "artifact_unchanged": True,
        },
        "report_verdict": {
            "pass": bool(report["pass"]),
            "reason": (
                "the run's own pass field counts per-run stationarity diagnostics as "
                "a blocker and four wealth_variance runs missed it; the artifact is "
                "promoted verbatim rather than rewritten"
            ),
        },
        "per_run_stationarity": {
            "gate_role": str(stationarity.get("gate_role") or ""),
            "gate_role_declared_in_this_artifact": "gate_role" in stationarity,
            "family_gate_role": (
                "per_run_diagnostic_only; the confirmatory gate is "
                "steady_estimand_report.json"
            ),
            "runs": int(len(stationarity.get("runs", []))),
            "failure_count": len(named),
            "diagnostics": diagnostics,
            "ensemble_contract_pass": bool(steady["pass"]),
        },
        "P4_comparability": {
            "pass": bool(report["P4_comparability"]["pass"]),
            "frozen_policy": report["P4_comparability"]["frozen_policy"],
            "units": report["P4_comparability"]["units"],
            "group_level_matching": report["P4_comparability"]["group_level_matching"],
        },
        "replicate_requirement": derived,
        "binding": {
            "config_sha256": _sha256(job_dir / "config.json"),
            "parameter_lock": str(binding["parameter_lock"]),
            "reference_binary_sha256": str(binding["reference_binary_sha256"]),
            "seeds": [int(seed) for seed in report["protocol"]["seeds"]],
            "contract_version": binding.get("config"),
        },
        "artifacts": {
            "conclusion": name,
            "conclusion_sha256": _sha256(tracked),
            "steady_estimand_report": steady_name,
            "steady_estimand_report_sha256": _sha256(steady_source),
            "isolation_identity_report": identity_name,
            "isolation_identity_report_sha256": _sha256(identity_source),
            "stationarity_report": stationarity_name,
            "stationarity_report_sha256": _sha256(stationarity_source),
            "derivation": "r_requirement.json",
            "derivation_sha256": _sha256(requirement_path),
        },
        "reference_report": _relative(project_root, tracked),
    }
    _write_json(job_dir / "result.json", result)

    # Only the pilot report, the derivation and the record are kept; the steady,
    # identity and stationarity reports are attested by hash inside result.json.
    manifest = _tracked_manifest(
        job_dir,
        [name, "r_requirement.json", "result.json"],
        exit_code=jobctl_result["exit_code"],
        wall_seconds=jobctl_result.get("wall_seconds", 0.0),
    )
    _write_json(job_dir / "manifest.json", manifest)


    return {
        "experiment": result["experiment"],
        "pass": result["pass"],
        "report_pass": result["report_verdict"]["pass"],
        "per_run_failures": result["per_run_stationarity"]["failure_count"],
        "r_replicates": derived["r_replicates"],
        "worst_required_replicates": derived["worst_required_replicates"],
        "wealth_variance_reference": derived["wealth_variance_reference"],
        "promoted": name,
        "conclusion_artifact_sha256": result["artifacts"]["conclusion_sha256"],
        "reference_report": result["reference_report"],
    }


# ── E2-C4: recording the confirmatory verdict ─────────────────────────
#
# The confirmatory verdict is produced by the frozen runner and is promoted
# verbatim: this recorder never recomputes an effect, applies a threshold, or has
# any authority to relax a gate.  What it does instead is re-derive the
# *structural* claims the payload makes about itself -- that the five gates
# compose into ``analysis_gate_pass`` exactly as declared, that the P4 gate's
# failure is what marks a contrast inconclusive a priori, that the P1 identity
# the run reports is the one the run wrote, that the batch is the declared 80 --
# and then copies the artifacts into git unchanged.  A recorder that could only
# restate the verdict would add nothing; one that could recompute it would be a
# second, competing analysis.

E2_REQUIRED_ARTIFACTS = (
    "channel_separation.json",
    "steady_estimand_report.json",
    "isolation_identity_report.json",
    "stationarity_report.json",
    "replicate_metrics.csv",
    "matched_input_audit.json",
)
# The five components the payload declares, in the order they compose.  Naming
# them here is what makes the composition check below possible.
E2_GATE_KEYS = (
    "v1f_numerical_calibration",
    "three_condition_inputs",
    "isolation_identity",
    "comparability",
    "steady_estimand",
)


def record_e2(
    project_root: Path,
    job_dir: Path,
    jobctl_dir: Path,
) -> dict[str, Any]:
    """Promote a finished E2-C4 confirmatory run into tracked evidence.

    Every branch either reproduces a number the run already recorded or refuses.
    The two refusals worth spelling out: a payload whose ``analysis_gate_pass``
    does not equal the conjunction of its own five gates is internally
    inconsistent and must not be promoted, and a P4 comparability failure that is
    not carried through as ``inconclusive`` would silently convert a
    pre-registered "cannot attribute this contrast" into an unqualified null.
    """
    import importlib.util
    import sys

    experiments_dir = Path(__file__).resolve().parent
    sys.path.insert(0, str(experiments_dir))
    for required in ("landscape_study", "run_landscape_study", "prepare_cycle4_confirmation"):
        if required not in sys.modules:
            spec = importlib.util.spec_from_file_location(
                required, experiments_dir / f"{required}.py"
            )
            if spec is None or spec.loader is None:
                raise RuntimeError(f"cannot load {required} to record E2-C4")
            module = importlib.util.module_from_spec(spec)
            sys.modules[required] = module
            spec.loader.exec_module(module)
    study = sys.modules["run_landscape_study"]

    jobctl_result = _read_json(jobctl_dir / "result.json")
    if jobctl_result.get("exit_code") != 0:
        raise RuntimeError(
            f"jobctl recorded exit code {jobctl_result.get('exit_code')!r}; "
            "refusing to record a failed run"
        )
    if jobctl_result.get("timed_out"):
        raise RuntimeError("jobctl recorded a timeout; refusing to record")

    config = _read_json(job_dir / "config.json")
    if config.get("experiment_id") != E2_ID or job_dir.name != E2_ID:
        raise RuntimeError("the E2-C4 job config declares another experiment")

    # The authorization, re-checked against the lock that is in git now rather
    # than assumed from the fact that the run happened.
    lock_path = (project_root / E2_LOCK_RELATIVE).resolve()
    _relative(project_root, lock_path)
    lock = _read_json(lock_path)
    if lock.get("status") != "final" or (
        lock.get("confirmatory_execution_authorized") is not True
    ):
        raise RuntimeError("E2-C4 was not authorized by a final parameter lock")
    if E2_ID not in (lock.get("authorized_experiments") or []):
        raise RuntimeError("the E2 lock does not authorize E2-CHANNEL-ABLATION-C4")
    if config.get("parameter_lock_sha256") != _sha256(lock_path):
        raise RuntimeError("the E2-C4 config does not bind the final E2 lock")
    audit = study.audit_parameter_lock(config, lock)
    if not audit["pass"]:
        raise RuntimeError(
            f"the recorded run's parameters do not match its lock: "
            f"missing={audit['missing_parameters']}, mismatches={sorted(audit['mismatches'])}"
        )
    calibration_block = lock.get("numerical_calibration")
    if not isinstance(calibration_block, Mapping):
        raise RuntimeError("the E2 lock has no numerical calibration block")
    if config.get("binary_sha256") != calibration_block.get("reference_binary_sha256"):
        raise RuntimeError("the E2-C4 config does not bind the calibrated reference binary")
    calibration = _read_json(project_root / str(config["numerical_calibration"]))
    study._require_cycle4_calibration_identity(calibration)
    if calibration.get("experiment") != C4_EXTENSION_ID:
        raise RuntimeError(
            "E2-C4 must be calibrated by the V1H extension, not "
            f"{calibration.get('experiment')!r}"
        )
    study.validate_e2_c4_sesoi_derivations(config)

    # The battery is the declared one, counted from the run's own markers rather
    # than from the summary it wrote about itself.
    units = list(study.E2_C4_UNIT_NAMES)
    seeds = [int(seed) for seed in config.get("seeds") or []]
    expected_runs = len(units) * len(seeds)
    design = lock.get("design_contract")
    if not isinstance(design, Mapping):
        raise RuntimeError("the E2 lock has no design contract")
    if design.get("units") != units or int(design.get("run_count", -1)) != expected_runs:
        raise RuntimeError("the recorded run's unit battery is not the locked one")
    declared_seeds = sorted(
        int(token)
        for token in (job_dir / "seeds.txt").read_text(encoding="utf-8").split()
        if token.strip()
    )
    if declared_seeds != sorted(seeds):
        raise RuntimeError("the job's seeds.txt and config disagree about the battery")

    workspace = job_dir / "workspace"
    sources = {
        name: _check_workspace_artifact(workspace, name) for name in E2_REQUIRED_ARTIFACTS
    }
    raw = _read_json(workspace / "result.json")
    if raw.get("experiment") != E2_ID:
        raise RuntimeError("the workspace result belongs to another experiment")
    if raw.get("status") != "completed":
        raise RuntimeError(f"the workspace result status is {raw.get('status')!r}")
    if int(raw.get("runs_completed", -1)) != expected_runs:
        raise RuntimeError(
            f"the run completed {raw.get('runs_completed')!r} runs, not {expected_runs}"
        )
    returns = int(raw.get("runs_executed_this_invocation", 0)) + int(
        raw.get("runs_reused_from_completion_markers", 0)
    )
    if returns != expected_runs:
        raise RuntimeError(
            f"executed + reused = {returns}, which is not the declared {expected_runs}"
        )
    # The runner lists artifacts as project-relative paths, so compare basenames:
    # a run whose own manifest does not mention an artifact it is supposed to have
    # produced has not produced it, whatever the file happens to contain.
    # ``result.json`` cannot list itself: the runner enumerates the output directory
    # and only then writes the summary, so it is excluded from its own manifest.
    listed = {Path(str(entry)).name for entry in (raw.get("artifacts") or [])}
    for name in E2_REQUIRED_ARTIFACTS:
        if name not in listed:
            raise RuntimeError(f"the workspace result does not list {name}")
    if raw.get("parameter_lock_sha256") != _sha256(lock_path):
        raise RuntimeError("the workspace result was produced under another lock")
    if raw.get("config_sha256") != _sha256(job_dir / "config.json"):
        raise RuntimeError("the workspace result was produced under another config")

    marker_root = workspace / "runs"
    markers = sorted(marker_root.glob("*/completion.json"))
    finished = [
        marker
        for marker in markers
        if _read_json(marker).get("status") == "completed"
    ]
    if len(finished) != expected_runs:
        raise RuntimeError(
            f"{len(finished)} of {len(markers)} runs carry a completed marker; the "
            f"frozen battery needs {expected_runs}"
        )

    payload = _read_json(sources["channel_separation.json"])
    if payload.get("experiment") != E2_ID:
        raise RuntimeError("the promoted payload belongs to another experiment")
    gates = payload.get("gates")
    if not isinstance(gates, Mapping) or set(gates) != set(E2_GATE_KEYS):
        raise RuntimeError(
            f"the payload's gates are {sorted(gates or {})}, not {list(E2_GATE_KEYS)}"
        )
    if any(not isinstance(value, bool) for value in gates.values()):
        raise RuntimeError("a gate value is not a boolean; refusing an ambiguous verdict")
    gate_pass = payload.get("analysis_gate_pass")
    composed = all(gates[key] for key in E2_GATE_KEYS)
    if gate_pass is not composed:
        raise RuntimeError(
            "the payload's analysis_gate_pass is not the conjunction of its own "
            f"gates: {gate_pass!r} != {composed!r}"
        )
    if bool(payload.get("claim_supported")) and not gate_pass:
        raise RuntimeError("the payload claims support from a failed analysis gate")

    identity_payload = payload.get("P1_isolation_identity")
    if not isinstance(identity_payload, Mapping):
        raise RuntimeError("the payload carries no P1 isolation identity block")
    if identity_payload.get("violations"):
        raise RuntimeError(
            "the P1 isolation identity reported violations; positions were not "
            "exogenous, so no effect in this payload may be reported"
        )
    if not isinstance(payload.get("P4_comparability"), Mapping):
        raise RuntimeError("the payload carries no P4 comparability block")
    if bool(payload["P4_comparability"].get("pass")) is False:
        if bool(payload.get("inconclusive")) is not True:
            raise RuntimeError(
                "the P4 comparability gate failed but the payload is not marked "
                "inconclusive; a contrast that cannot be attributed must not be "
                "promoted as a null"
            )

    provenance = payload.get("threshold_provenance")
    if not isinstance(provenance, Mapping):
        raise RuntimeError("the payload carries no threshold provenance")
    eligible = provenance.get("claim_eligible_metrics")
    if not isinstance(eligible, list):
        raise RuntimeError("the payload does not list its claim-eligible metrics")
    declared_family = list(design.get("estimand_family") or [])
    unregistered = sorted(set(eligible) - set(declared_family))
    if unregistered:
        raise RuntimeError(
            f"the payload claims eligibility for {unregistered}, which the E2 lock "
            f"did not register as estimands ({declared_family})"
        )
    reasons = provenance.get("ineligibility_reasons") or {}
    for metric in declared_family:
        if metric not in eligible and metric not in reasons:
            raise RuntimeError(
                f"{metric} is neither claim-eligible nor given an ineligibility "
                "reason; an unstated demotion is indistinguishable from a mistake"
            )

    rows = (sources["replicate_metrics.csv"]).read_text(encoding="utf-8").splitlines()
    header = rows[0].split(",") if rows else []
    if "condition" not in header or "seed" not in header:
        raise RuntimeError("replicate_metrics.csv does not carry condition/seed columns")
    condition_at = header.index("condition")
    seed_at = header.index("seed")
    per_unit: dict[str, set[int]] = {}
    for row in rows[1:]:
        if not row.strip():
            continue
        cells = row.split(",")
        per_unit.setdefault(cells[condition_at], set()).add(int(cells[seed_at]))
    if sorted(per_unit) != sorted(units):
        raise RuntimeError(
            f"replicate_metrics.csv covers {sorted(per_unit)}, not the locked units"
        )
    for unit, found in per_unit.items():
        if sorted(found) != sorted(seeds):
            raise RuntimeError(
                f"unit {unit} was read at {len(found)} seeds, not the declared {len(seeds)}"
            )

    # Promotion: the artifacts are copied byte for byte, and every hash recorded
    # in the manifest is computed from the copy that is now in git.
    promoted: dict[str, Path] = {}
    for name, source in sources.items():
        tracked = job_dir / name
        temporary = tracked.with_suffix(tracked.suffix + ".tmp")
        shutil.copyfile(source, temporary)
        os.replace(temporary, tracked)
        if _sha256(tracked) != _sha256(source):
            raise RuntimeError(f"promoted {name} does not match its source")
        promoted[name] = tracked
    # ``result.json`` stays derived rather than copied: it is this cycle's record
    # of the run, and the run's own file is hashed into it so the two remain
    # distinguishable.
    result = {
        "experiment": E2_ID,
        "status": "completed",
        "non_evidentiary": False,
        "analysis_gate_pass": bool(gate_pass),
        "claim_supported": bool(payload.get("claim_supported")),
        "inconclusive": bool(payload.get("inconclusive")),
        "gates": {key: bool(gates[key]) for key in E2_GATE_KEYS},
        "runs_planned": expected_runs,
        "runs_completed": expected_runs,
        "replicates_per_unit": len(seeds),
        "units": units,
        "seeds": seeds,
        "execution_host": _e2_host(job_dir),
        "source_commit": _e2_source_commit(job_dir),
        "binary_sha256": calibration_block.get("reference_binary_sha256"),
        "config_sha256": raw.get("config_sha256"),
        "parameter_lock_sha256": raw.get("parameter_lock_sha256"),
        "workspace_result_sha256": _sha256(workspace / "result.json"),
        "omp_threads": raw.get("omp_threads"),
        "elapsed_seconds_executed": raw.get("elapsed_seconds_executed_this_invocation"),
        "claim_eligible_metrics": sorted(eligible),
        "descriptive_only_metrics": sorted(provenance.get("descriptive_only_metrics") or []),
        "ineligibility_reasons": {
            metric: list(value)
            for metric, value in sorted(reasons.items())
        },
        "scientific_sesoi": dict(design.get("scientific_sesoi") or {}),
        "replicate_requirement": dict(design.get("replicate_requirement") or {}),
        "P4_comparability": {
            "pass": bool(payload["P4_comparability"].get("pass")),
            "frozen_policy": payload["P4_comparability"].get("frozen_policy"),
            "group_level_matching": payload["P4_comparability"].get("group_level_matching"),
        },
        "P1_isolation_identity": {
            "pass": bool(identity_payload.get("pass")),
            "checked_comparisons": identity_payload.get("checked_comparisons"),
            "violations": list(identity_payload.get("violations") or []),
        },
        "artifacts": {
            name: {"path": name, "sha256": _sha256(path)}
            for name, path in sorted(promoted.items())
        },
        "reference_report": _relative(project_root, promoted["channel_separation.json"]),
    }
    _write_json(job_dir / "result.json", result)

    # Every declared artifact is promoted, so the manifest attests the promoted set
    # itself: the same bytes the run produced, now kept in the job directory.
    manifest = _tracked_manifest(
        job_dir,
        [*E2_REQUIRED_ARTIFACTS, "result.json"],
        exit_code=jobctl_result["exit_code"],
        wall_seconds=jobctl_result.get("wall_seconds", 0.0),
    )
    _write_json(job_dir / "manifest.json", manifest)


    return {
        "experiment": E2_ID,
        "analysis_gate_pass": result["analysis_gate_pass"],
        "claim_supported": result["claim_supported"],
        "inconclusive": result["inconclusive"],
        "gates": result["gates"],
        "claim_eligible_metrics": result["claim_eligible_metrics"],
        "run_count": expected_runs,
        "reference_report": result["reference_report"],
    }


# ── E2-C4: the confirmatory lock and declaration set ───────────────────
#
# E2-C4 is authorized by a *second* lock version rather than by extending the
# first. The first lock's ``amendment_policy`` says an outcome-informed change
# needs a new lock version and a new cycle; E2-C4 is not an amendment (it changes
# nothing E1-C4 declared) but it *is* a new authorization whose frozen quantities
# -- R and the two SESOI values -- were unknown when the first lock was finalized.
# Writing them into a second lock keeps "what was frozen, and what was known when"
# legible, which is the whole point of the file.
#
# Every number in the lock is *derived*, never typed: R and the variance SESOI come
# from the tracked ``r_requirement.json`` that ``record-pilot`` recomputed from the
# pilot's two reports, the comparability guards and the steady bounds come from the
# pilot's own declarations (R is only valid against the bounds the derivation was
# computed against), and the seeds come from the ledger. What is typed here is only
# what a human decided.

E2_ID = "E2-CHANNEL-ABLATION-C4"
E2_PILOT_ID = "E2-C4-PILOT"
E2_LOCK_RELATIVE = "research/parameter_lock.e2.json"
C4_EXTENSION_ID = "V1H-CALIBRATION-EXTENSION-C4"
# Frozen when the pilot's window was chosen; the confirmatory battery draws from
# the same primes so that no seed decision is made after the fact.
E2_SEED_WINDOW = (12300, 13000)

# The steady-window bounds and the comparability guards are taken from the pilot's
# declaration rather than restated: ``derive_r_replicates`` solved the frozen steady
# inequalities *of that report*, so a confirmatory config with different bounds would
# carry a replicate count that was never derived for it.
E2_FROM_PILOT_CONFIG = (
    "independent_precision_absolute_half_widths",
    "independent_precision_relative_half_widths",
    "adjacent_window_absolute_bounds",
    "adjacent_window_relative_bounds",
    "binary",
    "binary_sha256",
)
# Parameters this module decides and freezes. Everything here is copied into the
# config verbatim and ``audit_parameter_lock`` refuses if the two ever disagree.
E2_LOCKED_PARAMETERS = (    "population",
    "grid_shape",
    "bounds",
    "dt",
    "total_time",
    "output_time_interval",
    "steady_snapshots",
    "stationarity_max_normalized_drift",
    "stationarity_min_ess",
    "stationarity_reversal_span_sigma",
    "stationarity_gate_unit",
    "independent_precision_absolute_half_widths",
    "independent_precision_relative_half_widths",
    "adjacent_window_absolute_bounds",
    "adjacent_window_relative_bounds",
    "temperature",
    "friction",
    "social_strength",
    "interaction_range",
    "exchange_rate",
    "exchange_noise_strength",
    "exchange_reversion_rate",
    "epsilon_log_sigma",
    "consumption_rate",
    "terrain_force_scale",
    "terrain_production_scale",
    "ability_saturation_w",
    "wealth_log_sigma",
    "strict_numerics",
    "confirmative_mode",
    "mpi_enabled",
    "ranks",
    "omp_threads",
    "parallel",
    "per_run_timeout_seconds",
    "familywise_alpha",
    "bootstrap_samples",
    "analysis_seed",
    "scientific_sesoi",
)


def _write_e2_declarations(
    job_dir: Path,
    *,
    project_root: Path,
    config: Mapping[str, Any],
    lock: Mapping[str, Any],
    lock_path: Path,
    calibration_path: Path,
    pilot: Mapping[str, Any],
    requirement: Mapping[str, Any],
    seeds: Sequence[int],
    runs: int,
) -> None:
    """Write the jobctl-facing declaration files for E2-C4.

    Every checksum here is computed from the file it names, so the declaration
    cannot drift from the artifacts it points at. A pre-existing file with
    different contents is a refusal rather than a silent overwrite: these are
    pre-registrations, and editing one after a reading would erase the only record
    of what was expected.
    """
    design = lock["design_contract"]
    checksums = {
        "external_data": "none",
        "generated_inputs": (
            "unit terrain fields rebuilt from the frozen unit battery; every per-seed "
            "input digest is recorded in run_specs.json before execution"
        ),
        "dependency_calibration": _sha256(calibration_path),
        "parameter_lock": _sha256(lock_path),
        "reference_binary": config["binary_sha256"],
        "reference_protocol_config": _sha256(
            project_root / "research/jobs/E1-MATCHED-LANDSCAPES-C4/config.json"
        ),
    }
    artifacts = (
        "channel_separation.json",
        "steady_estimand_report.json",
        "isolation_identity_report.json",
        "stationarity_report.json",
        "replicate_metrics.csv",
    )
    files: dict[str, str] = {
        "seeds.txt": "".join(f"{seed}\n" for seed in seeds),
        "env.txt": "\n".join(
            [
                "host=umi",
                "execution=CPU_reference",
                f"omp_threads={config['omp_threads']}",
                f"parallel={config['parallel']}",
                "mpi=OFF",
                "gpu_count=0",
                "reference_protocol_experiment=E1-MATCHED-LANDSCAPES-C4",
                "reference_protocol_source_commit=b6d24b76a50529965469332644e7bed251c49eb1",
                "reference_protocol_binding="
                "the unit battery, the steady-window contract and the analysis path are "
                "E2-C4's own; E1-C4 is the protocol reference for population, grid, "
                "timestep, temperature and the CPU-reference execution mode",
                "",
            ]
        ),
        "outputs.txt": "".join(f"{name}\n" for name in artifacts),
        "data_checksums.txt": "".join(
            f"{key}={value}\n" for key, value in checksums.items()
        ),
        "computational_strategy.json": json.dumps(
            {
                "approach": (
                    f"Run {runs} simulations ({len(lock['design_contract']['units'])} "
                    f"frozen units x {len(seeds)} seeds, one replicate per unit and "
                    f"seed) as {config['parallel']} OMP=1 CPU reference processes on the "
                    "calibrated reference binary, then analyse the five units under the "
                    "frozen condition-ensemble two-window steady contract, the P1 "
                    "isolation identity guard, the mandatory P4 comparability gate and "
                    "Holm-corrected paired contrasts."
                ),
                "evidence_role": "confirmatory",
                "evidence_boundary": (
                    "Synthetic generative mechanism only; no historical-state claim. The "
                    "estimands are wealth_gini and wealth_variance on two claim-bearing "
                    "contrasts. zero_wealth_fraction is a P4 non-degeneracy guard and "
                    "mean_wealth a level audit, so neither carries a claim."
                ),
                "reference_method": (
                    "validated OpenMP-OFF C++ simulator binary, sha256-bound to the "
                    "cycle 4 E2 parameter lock"
                ),
                "validation_points": [
                    "the parameter lock is final, authorizes E2-CHANNEL-ABLATION-C4, and "
                    "every locked parameter is compared against the config before any run",
                    "the calibration is the V1H extension, accepted only because it "
                    "reproduced V1F's four limits bit for bit",
                    "the relative wealth_variance SESOI is checked against the "
                    "checksum-bound pilot report it was derived from, including its "
                    "level-drift floor",
                    "the seed battery is the smallest unused primes of the frozen window, "
                    "verified against the seeds ledger",
                ],
                "agreement": {
                    "criterion": (
                        "the frozen analysis gate: the ensemble two-window steady "
                        "contract passes, matched inputs hold, execution invariants "
                        "hold, and the P4 comparability gate passes so no contrast is "
                        "downgraded to inconclusive"
                    )
                },
                "reference_validation_required": True,
                "validation_artifact": "channel_separation.json",
                "supports_core_claim": True,
                "claim_ids": ["C3-CHANNELS-C4"],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        "experiment.json": json.dumps(
            {
                "id": E2_ID,
                "type": "command",
                "mode": "server",
                "priority": "P1",
                "claim_ids": ["C3-CHANNELS-C4"],
                "non_evidentiary": False,
                "depends_on": [E2_PILOT_ID, C4_EXTENSION_ID, "V0G-SIMULATOR-TESTS-C4"],
                "objective": (
                    "Separate spatial organisation from the explicitly named "
                    "production-decay source-sink path under the frozen five-unit "
                    "battery: the P2 source-pattern contrasts at a shared sink rate and "
                    "the P3 sink-rate ladder on the clustered source."
                ),
                "role": (
                    "Confirmatory. The two claim-bearing contrasts are "
                    "clustered-minus-shuffled and d0.04-minus-d0.01; their estimands are "
                    "wealth_gini and wealth_variance at the frozen SESOI. The P4 "
                    "comparability gate runs before any effect and can make a contrast "
                    "inconclusive a priori, never null."
                ),
                "command": [
                    "/usr/bin/env",
                    "PYTHONPATH=src:research/src/experiments",
                    "OMP_NUM_THREADS=1",
                    "python3",
                    "research/src/experiments/run_landscape_study.py",
                    "--experiment",
                    E2_ID,
                    "--config",
                    f"research/jobs/{E2_ID}/config.json",
                    "--output-dir",
                    f"research/jobs/{E2_ID}/workspace",
                ],
                "config": f"research/jobs/{E2_ID}/config.json",
                "config_sha256": _sha256(job_dir / "config.json"),
                "env_snapshot": f"research/jobs/{E2_ID}/env.txt",
                "seeds": [int(seed) for seed in seeds],
                "data_checksums": checksums,
                "artifacts": list(artifacts),
                "timeout_seconds": 86400,
                "gpu_count": 0,
                "design": "research/e2-cycle4-channel-design.md",
                "failure_policy": (
                    "A failed run, an analysis-gate failure or a P1 identity violation is "
                    "an implementation problem, never a result. The P4 comparability gate "
                    "may fail a priori: the affected contrast is then reported as "
                    "pre-registered inconclusive, and no band, unit or delta may be "
                    "adjusted from the outcome."
                ),
                "replicate_requirement": {
                    "source": (
                        f"research/jobs/{E2_PILOT_ID}/r_requirement.json"
                    ),
                    "source_sha256": _sha256(
                        project_root / "research/jobs" / E2_PILOT_ID / "r_requirement.json"
                    ),
                    "r_replicates": int(requirement["r_replicates"]),
                    "worst_required_replicates": int(
                        requirement["worst_required_replicates"]
                    ),
                    "note": (
                        "the full per-contrast, per-unit derivation lives in the cited "
                        "file rather than here, so the same quantity has one home"
                    ),
                },
                "replicate_count": int(lock["design_contract"]["replicates_per_unit"]),
                "run_count": runs,
                "scientific_sesoi": dict(lock["design_contract"]["scientific_sesoi"]),
                "pilot_reference": {
                    "experiment": E2_PILOT_ID,
                    "path": pilot["reference_report"],
                    "sha256": pilot["report_sha256"],
                },
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
    }
    for name, text in files.items():
        path = job_dir / name
        if path.is_file() and path.read_text(encoding="utf-8") != text:
            raise RuntimeError(
                f"a different {name} already exists for {E2_ID}; these are "
                "pre-registrations and must not be rewritten in place"
            )
    for name, text in files.items():
        path = job_dir / name
        if not path.is_file():
            path.write_text(text, encoding="utf-8")


def _e2_pilot_artifacts(project_root: Path) -> dict[str, Any]:
    """Read the recorded pilot, refusing anything that is not a usable reading.

    The recorder already checked all of this; re-checking here is not redundant
    because the *lock* must be derivable from the job directory alone, long after
    the recorder ran. A pilot that was promoted without passing the isolation
    identity, the ensemble contract or the batch-completeness test must not be able
    to size R just because its files are present.
    """
    job_dir = project_root / "research" / "jobs" / E2_PILOT_ID
    result = _read_json(job_dir / "result.json")
    if result.get("non_evidentiary") is not True:
        raise RuntimeError("the E2-C4 pilot result is not marked non-evidentiary")
    if result.get("pass") is not True:
        raise RuntimeError(
            "the E2-C4 pilot was not recorded as usable; its readings may not size R"
        )
    per_run = result.get("per_run_stationarity")
    if not isinstance(per_run, Mapping):
        raise RuntimeError("the recorded pilot has no per-run stationarity block")
    if per_run.get("ensemble_contract_pass") is not True:
        raise RuntimeError(
            "the recorded pilot's ensemble contract did not pass; there is no "
            "dispersion to freeze R from"
        )
    requirement = _read_json(job_dir / "r_requirement.json")
    if result.get("replicate_requirement") != requirement:
        raise RuntimeError(
            "the pilot's recorded result and its derivation disagree; one of them "
            "was edited after recording"
        )
    report_name = "pilot_variance_report.json"
    report = job_dir / report_name
    if not report.is_file() or report.stat().st_size == 0:
        raise RuntimeError(f"the tracked pilot report is missing: {report_name}")
    if _sha256(report) != result["artifacts"]["conclusion_sha256"]:
        raise RuntimeError(
            "the tracked pilot report does not match the sha256 the record bound it to"
        )
    # The identity verdict is read off the promoted report, because that is the
    # artifact the lock cites. A record whose summary and whose artifact disagree
    # is not a reading anyone can act on.
    payload = _read_json(report)
    identity = payload.get("P1_isolation_identity")
    if not isinstance(identity, Mapping) or identity.get("pass") is not True:
        raise RuntimeError("the recorded pilot does not carry a passing P1 identity")
    if int(identity.get("violations") or 0) != 0:
        raise RuntimeError("the recorded pilot carries identity violations")
    return {
        "job_dir": job_dir,
        "result": result,
        "requirement": requirement,
        "report_name": report_name,
        "report_sha256": result["artifacts"]["conclusion_sha256"],
        "reference_report": _relative(project_root, report),
        "source_commit": _e2_source_commit(job_dir),
    }


def _e2_host(job_dir: Path) -> str:
    """The host the declarations pinned, not the host the run reports.

    A run's own account of where it executed is not evidence of where it was
    authorized to execute; the declaration is.
    """
    path = job_dir / "env.txt"
    if not path.is_file():
        raise RuntimeError("the E2-C4 job has no env.txt to read its host from")
    for line in path.read_text(encoding="utf-8").splitlines():
        key, _, value = line.partition("=")
        if key.strip() == "host" and value.strip():
            return value.strip()
    raise RuntimeError("the E2-C4 env.txt does not declare a host")


def _e2_source_commit(job_dir: Path) -> str:
    """The commit the pilot's declaration set was committed as.

    Read rather than restated: the lock must point at the code that produced its
    frozen readings, and the only trustworthy record of that is the one the job
    itself carries.
    """
    path = job_dir / "commit.txt"
    if not path.is_file() or not path.stat().st_size:
        raise RuntimeError("the E2-C4 pilot has no commit.txt to bind the lock to")
    value = path.read_text(encoding="utf-8").strip()
    if len(value) != 40 or any(char not in "0123456789abcdef" for char in value):
        raise RuntimeError(f"the pilot's commit.txt is not a 40-character sha: {value!r}")
    return value


def _e2_seeds(project_root: Path, count: int) -> list[int]:
    """The smallest unused primes in the frozen window, excluding the pilot's.

    Deterministic on purpose: "the smallest unused" needs no judgement, so the
    choice cannot be steered, and a re-run of this function against the same ledger
    reproduces the same battery. The pilot's own eight are excluded because a
    non-evidentiary run must not become a replicate of the confirmatory one.
    """
    report = audit_seeds(project_root / "research" / "jobs", exclude=(E2_ID,))
    used = set(int(seed) for seed in report["used_seeds"])
    pool = [
        value
        for value in range(E2_SEED_WINDOW[0], E2_SEED_WINDOW[1] + 1)
        if _is_prime(value) and value not in used
    ]
    if len(pool) < count:
        raise RuntimeError(
            f"the seed window {E2_SEED_WINDOW} holds {len(pool)} unused primes; "
            f"{count} are needed"
        )
    chosen = pool[:count]
    if len(set(chosen)) != count:
        raise RuntimeError("seed selection produced duplicates")
    # If this job already carries a declaration, it must be exactly this choice:
    # the exclusion above is only sound while the excluded dir and the selection
    # agree, and a re-run is the only way that can drift.
    declared = project_root / "research" / "jobs" / E2_ID / "seeds.txt"
    if declared.is_file():
        existing = [
            int(token)
            for token in declared.read_text(encoding="utf-8").split()
            if token.strip()
        ]
        if existing != chosen:
            raise RuntimeError(
                f"the existing E2-C4 declaration lists {existing} but the ledger "
                f"implies {chosen}; the seed choice must not depend on whether the "
                "job has been prepared before"
            )
    return chosen


def prepare_e2(project_root: Path) -> dict[str, Any]:
    """Write the E2-C4 parameter lock, then the config that binds to it.

    The lock is written first because the config must pin the lock's sha256; both
    files are validated before either is written, so a rejected declaration set
    leaves no partially-written pair behind.
    """
    import importlib.util
    import sys

    experiments_dir = Path(__file__).resolve().parent
    sys.path.insert(0, str(experiments_dir))
    for required in ("landscape_study", "run_landscape_study", "prepare_cycle4_confirmation"):
        if required not in sys.modules:
            spec = importlib.util.spec_from_file_location(
                required, experiments_dir / f"{required}.py"
            )
            if spec is None or spec.loader is None:
                raise RuntimeError(f"cannot load {required} to prepare E2-C4")
            module = importlib.util.module_from_spec(spec)
            sys.modules[required] = module
            spec.loader.exec_module(module)
    study = sys.modules["run_landscape_study"]

    pilot = _e2_pilot_artifacts(project_root)

    # The irreversible precondition is checked before anything else is derived: a
    # lock written over recorded outcomes would be an outcome-informed freeze
    # wearing a pre-registration's clothes.
    outcome_dir = project_root / "research" / "jobs" / E2_ID
    for outcome in ("result.json", "channel_separation.json"):
        if (outcome_dir / outcome).exists():
            raise RuntimeError(
                f"E2-C4 already has {outcome}; refusing to write a lock over "
                "recorded outcomes"
            )
    requirement = pilot["requirement"]
    if requirement.get("delta_wealth_variance_ratio") != 0.50:
        raise RuntimeError(
            f"the pilot's derivation was computed at ratio "
            f"{requirement.get('delta_wealth_variance_ratio')!r}; "
            "the frozen decision is 0.50"
        )
    replicates = int(requirement["r_replicates"])
    if replicates < 1 or replicates & (replicates - 1):
        raise RuntimeError(f"R must be a positive power of two, got {replicates}")
    worst = int(requirement["worst_required_replicates"])
    if replicates < worst:
        raise RuntimeError(
            f"R = {replicates} is below the worst family requirement {worst}; the "
            "frozen battery would not be able to satisfy a contract it was sized for"
        )

    band = None
    pilot_config = _read_json(project_root / "research" / "jobs" / E2_PILOT_ID / "config.json")
    pilot_report = _read_json(pilot["job_dir"] / pilot["report_name"])
    frozen_policy = pilot_report["P4_comparability"]["frozen_policy"]
    band = float(frozen_policy["mean_wealth_relative_band"])
    floor = study.e2_c4_level_drift_variance_floor(band)
    ratio = float(requirement["delta_wealth_variance_ratio"])
    if ratio <= floor:
        raise RuntimeError(
            f"the frozen ratio {ratio} is at or below the level-drift floor {floor}"
        )
    comparability = {
        "comparability_zero_wealth_fraction_max": float(
            frozen_policy["zero_wealth_fraction_max"]
        ),
        "comparability_wealth_variance_min": float(frozen_policy["wealth_variance_min"]),
        "comparability_mean_wealth_relative_band": band,
    }

    calibration_relative = (
        f"research/jobs/{C4_EXTENSION_ID}/numerical_calibration_extended.json"
    )
    calibration_path = project_root / calibration_relative
    calibration = _read_json(calibration_path)
    if calibration.get("experiment") != C4_EXTENSION_ID:
        raise RuntimeError(
            f"E2-C4 must be calibrated by {C4_EXTENSION_ID} (V1F never froze "
            "wealth_variance), got "
            f"{calibration.get('experiment')!r}"
        )
    limits = calibration.get("numerical_resolution_limits", {})
    required_metrics = study.confirmatory_metrics_for_experiment(E2_ID)
    for metric in required_metrics:
        if metric not in limits:
            raise RuntimeError(f"the calibration extension does not cover {metric}")

    delta_gini = float(requirement["delta_wealth_gini"])
    delta_variance = float(requirement["delta_wealth_variance"])
    var_ref = float(requirement["wealth_variance_reference"])
    if delta_variance != ratio * var_ref:
        raise RuntimeError(
            "the recorded variance SESOI is not the recorded rule applied to the "
            "recorded reference level"
        )
    sesoi = {"wealth_gini": delta_gini, "wealth_variance": delta_variance}
    derivations = {
        "wealth_variance": {
            "metric": "wealth_variance",
            "rule": study.E2_C4_RELATIVE_SESOI_RULE,
            "ratio": ratio,
            "reference_field": study.E2_C4_SESOI_REFERENCE_FIELDS["wealth_variance"],
            "reference_report": pilot["reference_report"],
            "reference_report_sha256": pilot["report_sha256"],
            "resolved_value": delta_variance,
        }
    }

    seeds = _e2_seeds(project_root, replicates)
    units = list(study.E2_C4_UNIT_NAMES)
    run_count = len(units) * replicates

    parameters: dict[str, Any] = {
        # The model and analysis parameters are the cycle 4 reference configuration;
        # reading them out of the finalized E1 lock is what makes that a fact rather
        # than a claim, and the two locks agreeing is checked below.
        key: value
        for key, value in _read_json(project_root / "research" / "parameter_lock.cycle4.json")[
            "parameters"
        ].items()
    }
    # E2-C4 does not read base_production / wealth_decay_rate / mean_wealth from the
    # config: the unit battery fixes them per unit. Locking them would force the
    # config to carry values that no E2 run uses, which is how a lock stops
    # describing the experiment it authorizes.
    for per_unit in ("base_production", "wealth_decay_rate", "mean_wealth"):
        parameters.pop(per_unit, None)
    parameters["ability_saturation_w"] = 5.0
    for key in E2_FROM_PILOT_CONFIG:
        if key in ("binary", "binary_sha256"):
            continue
        parameters[key] = pilot_config[key]
    parameters["scientific_sesoi"] = sesoi
    if set(parameters) != set(E2_LOCKED_PARAMETERS):
        raise RuntimeError(
            "the E2-C4 locked parameter set drifted from its declaration: "
            f"extra {sorted(set(parameters) - set(E2_LOCKED_PARAMETERS))}, "
            f"missing {sorted(set(E2_LOCKED_PARAMETERS) - set(parameters))}"
        )
    # A lock that silently widened its input set would make the cross-lock check
    # below meaningless, so the inherited values are compared key by key.
    e1_parameters = _read_json(project_root / "research" / "parameter_lock.cycle4.json")[
        "parameters"
    ]
    for key, value in parameters.items():
        if key in e1_parameters and e1_parameters[key] != value:
            if key in ("scientific_sesoi", "independent_precision_absolute_half_widths",
                       "independent_precision_relative_half_widths",
                       "adjacent_window_absolute_bounds", "adjacent_window_relative_bounds"):
                continue
            raise RuntimeError(
                f"E2-C4 parameter {key!r} differs from the cycle 4 reference lock: "
                f"{value!r} != {e1_parameters[key]!r}"
            )

    lock = {
        "lock_id": "ar-politeia-cycle4-e2-v1",
        "status": "final",
        "confirmatory_execution_authorized": True,
        "locked_before_confirmatory_outcomes": True,
        "promotion_base_commit": pilot["source_commit"],
        "source_commit": pilot["source_commit"],
        "analysis_commit": pilot["source_commit"],
        "authorized_experiments": [E2_ID],
        "numerical_calibration": {
            "experiment": C4_EXTENSION_ID,
            "path": calibration_relative,
            "sha256": _sha256(calibration_path),
            "reference_binary_sha256": pilot_config["binary_sha256"],
            "numerical_resolution_limits": dict(limits),
            "extends": calibration.get("extends"),
            "note": (
                "V1F recorded but never froze wealth_variance, so E2-C4's estimands "
                "require the extension. The extension is accepted only because it "
                "reproduced V1F's four limits bit for bit, which "
                "_require_cycle4_calibration_identity re-checks from the artifact."
            ),
        },
        "parameters": parameters,
        "design_contract": {
            "units": units,
            "source_pattern_group": list(study.E2_C4_PATTERN_UNITS),
            "sink_rate_group": list(study.E2_C4_SINK_UNITS),
            "claim_bearing_contrasts": [
                "clustered-minus-shuffled",
                "d0.04-minus-d0.01",
            ],
            "reference_contrast": "clustered-minus-flat",
            "estimand_family": list(required_metrics),
            "claim_ineligible": {
                "zero_wealth_fraction": "P4 non-degeneracy guard only (design section 15)",
                "mean_wealth": "level audit, never an estimand (design section 15)",
            },
            "run_count": run_count,
            "seed_count": replicates,
            "replicates_per_unit": replicates,
            "full_initial_state_match_required": True,
            "resource_histogram_and_accessible_area_match_required": True,
            "temporal_ess_role": "diagnostic_only",
            "valid_null_policy": (
                "A passed analysis gate without a claim-bearing effect beyond the "
                "effective threshold is retained as valid null/equivalence evidence."
            ),
            "scientific_sesoi": sesoi,
            "replicate_requirement": requirement,
            "pilot": {
                "experiment": E2_PILOT_ID,
                "path": pilot["reference_report"],
                "sha256": pilot["report_sha256"],
                "recorded_failures": int(pilot["result"]["per_run_stationarity"]["failure_count"]),
                "role": (
                    "non-evidentiary; supplied the dispersion and the reference level "
                    "that size R and the variance SESOI. It read no direction: the "
                    "report contains no contrast mean, interval or p-value."
                ),
            },
        },
        "amendment_policy": (
            "After finalization, any outcome-informed change requires a new lock "
            "version and research cycle."
        ),
    }

    config: dict[str, Any] = {
        "experiment_id": E2_ID,
        "summary_result": f"research/jobs/{E2_ID}/result.json",
        "numerical_calibration": calibration_relative,
        "numerical_calibration_sha256": _sha256(calibration_path),
        "parameter_lock": E2_LOCK_RELATIVE,
        "seeds": seeds,
        **parameters,
        **comparability,
        "scientific_sesoi_derivations": derivations,
    }
    for key in E2_FROM_PILOT_CONFIG:
        config[key] = pilot_config[key]

    # Both files are validated against the shared code before either is written:
    # a lock that the runner would reject is not a declaration, it is a trap.
    audit = study.audit_parameter_lock(config, lock)
    if not audit["pass"]:
        raise RuntimeError(
            f"the generated E2-C4 config does not match its lock: missing "
            f"{audit['missing_parameters']}, mismatches {sorted(audit['mismatches'])}"
        )
    study._validate_c4_steady_contract(config, E2_ID)
    study.validate_c4_calibration_coverage(
        calibration, sesoi, required_metrics, allow_extension=True
    )

    lock_path = project_root / E2_LOCK_RELATIVE
    if lock_path.is_file():
        existing = _read_json(lock_path)
        if existing != lock:
            raise RuntimeError(
                "a different E2-C4 lock already exists; archive it or bump the "
                "lock version rather than overwriting frozen quantities"
            )
    config["parameter_lock_sha256"] = "pending"
    config_path = outcome_dir / "config.json"
    if config_path.is_file():
        existing_config = _read_json(config_path)
        if {k: v for k, v in existing_config.items() if k != "parameter_lock_sha256"} != {
            k: v for k, v in config.items() if k != "parameter_lock_sha256"
        }:
            raise RuntimeError(
                "a different E2-C4 config already exists; refusing to overwrite it"
            )

    _write_json(lock_path, lock)
    config["parameter_lock_sha256"] = _sha256(lock_path)
    _write_json(config_path, config)
    _write_e2_declarations(
        outcome_dir,
        project_root=project_root,
        config=config,
        lock=lock,
        lock_path=lock_path,
        calibration_path=calibration_path,
        pilot=pilot,
        requirement=requirement,
        seeds=seeds,
        runs=run_count,
    )

    # The written pair must satisfy the checks the runner performs, including the
    # checksum the config now carries.
    written_lock = _read_json(lock_path)
    written_audit = study.audit_parameter_lock(config, written_lock)
    if not written_audit["pass"]:
        raise RuntimeError("the written E2-C4 lock and config disagree")
    if config["parameter_lock_sha256"] != _sha256(lock_path):
        raise RuntimeError("the written E2-C4 config does not pin the lock's sha256")
    study.validate_e2_c4_sesoi_derivations(config)

    return {
        "lock": _relative(project_root, lock_path),
        "lock_sha256": config["parameter_lock_sha256"],
        "config": _relative(project_root, config_path),
        "r_replicates": replicates,
        "run_count": run_count,
        "seed_count": replicates,
        "seeds": seeds,
        "scientific_sesoi": sesoi,
        "wealth_variance_reference": var_ref,
        "level_drift_floor": floor,
        "level_drift_margin": ratio / floor - 1.0,
    }


def _tracked_evidence(job_dir: Path, name: str) -> dict[str, Any]:
    """One manifest artifact record, in the shape the audit gate accepts.

    Cycle 3's manifests are the only ones that ever satisfied ``audit``, and they
    pin all three fields as load-bearing:

    * ``path`` is resolved by ``audit`` against its own run directory (``research/``),
      hence ``jobs/<id>/<name>``.  Cycle 4 wrote ``workspace/<name>``, which resolves
      to ``research/workspace/<name>`` -- a path that can never exist, because
      ``research/jobs/*/workspace/`` is gitignored and no workspace file is ever
      tracked.
    * ``sha256`` is checked.
    * ``size`` is checked as well, and a missing field compares unequal to the real
      size and is reported as a mismatch.  Cycle 4's recorders omitted it.

    So a manifest can only attest a file the recorder actually *kept* in the job
    directory.  Hashes of workspace files that are deliberately not kept belong in
    the job's ``result.json``, beside the verdict they support, which is where
    several recorders already put them.
    """
    path = job_dir / name
    if not path.is_file() or path.stat().st_size == 0:
        raise RuntimeError(
            f"a manifest cannot attest {name}: it is not kept in the job directory"
        )
    parts = job_dir.resolve().parts
    if "jobs" not in parts:
        raise RuntimeError(f"the job directory {job_dir} is not under a 'jobs' directory")
    index = len(parts) - 1 - parts[::-1].index("jobs")
    return {
        "path": "/".join((*parts[index:], name)),
        "sha256": _sha256(path),
        "size": path.stat().st_size,
    }


def _tracked_manifest(
    job_dir: Path,
    kept: Sequence[str],
    *,
    exit_code: Any,
    wall_seconds: Any,
    **extra: Any,
) -> dict[str, Any]:
    """The manifest of a recorded job: it attests exactly what was kept."""
    return {
        "exit_code": int(exit_code),
        "timed_out": False,
        "wall_seconds": float(wall_seconds),
        "jobctl_reconcile": "completed",
        **extra,
        "artifacts": [_tracked_evidence(job_dir, name) for name in sorted(set(kept))],
    }


MIGRATION_REPORT_RELATIVE = "research/manifest-path-migration.json"


def migrate_manifest_paths(project_root: Path) -> dict[str, Any]:
    """Re-point recorded manifests at the files they can actually attest.

    This repairs a whole cycle of recorded evidence, so it is deliberately the
    narrowest edit that makes the records consistent with the audit gate:

    * an entry whose basename resolves inside its own job directory *and* hashes to
      the recorded value is re-pointed to ``jobs/<id>/<name>`` and given the
      ``size`` the gate compares.  The target is byte-identical by construction,
      because the recorded hash is what selected it;
    * an entry that resolves to nothing, or to a file whose bytes are not the ones
      it records, is moved verbatim into ``unkept_workspace_attestations``: its
      ``path`` and ``sha256`` are not touched, because they are a true statement
      about a workspace file that was deliberately not kept, and rewriting them
      would be inventing evidence.  The 11 of these are all ``workspace/result.json``
      entries whose job kept a deliberately *compacted* record instead;
    * a job whose kept ``result.json`` is attested by nothing gets an entry for it,
      which is what every recorder now writes.

    Nothing is inferred about content: a hash mismatch never silently becomes a
    re-point.  The operation is idempotent, and the report it returns names every
    disposition so the change can be reviewed or reverted in git.
    """
    run_dir = (project_root / "research").resolve()
    jobs_root = run_dir / "jobs"
    if not jobs_root.is_dir():
        raise RuntimeError(f"{jobs_root} is not a directory")

    report: dict[str, Any] = {
        "migration": "manifest artifact paths re-pointed at research-relative kept files",
        "gate": "autoresearcher.foundation.audit resolves paths against its run directory",
        "totals": {
            "repointed": 0,
            "already_correct": 0,
            "unkept": 0,
            "unkept_carried": 0,
            "attested_kept": 0,
            "jobs_changed": 0,
        },
        "jobs": [],
    }

    for manifest_path in sorted(jobs_root.glob("*/manifest.json")):
        job_dir = manifest_path.parent
        job = job_dir.name
        payload = _read_json(manifest_path)
        artifacts = payload.get("artifacts")
        if not isinstance(artifacts, list):
            raise RuntimeError(f"{job}: the manifest has no artifact list to migrate")
        dispositions: list[dict[str, Any]] = []
        kept: list[dict[str, Any]] = []
        # Attestations a previous pass already moved out of ``artifacts`` are read
        # back and carried forward.  Leaving them out would make the second pass
        # *delete* them, which is the one direction this migration must never move:
        # they are the only surviving statement about those workspace files.
        carried = payload.get("unkept_workspace_attestations") or []
        if not isinstance(carried, list):
            raise RuntimeError(
                f"{job}: unkept_workspace_attestations is not a list"
            )
        unkept: list[dict[str, Any]] = [dict(entry) for entry in carried]
        report["totals"]["unkept_carried"] += len(carried)
        for entry in artifacts:
            old = entry.get("path")
            if not isinstance(old, str) or not old:
                raise RuntimeError(f"{job}: an artifact record has no path")
            if old.startswith("jobs/"):
                target = run_dir / old
                if not target.is_file() or target.stat().st_size == 0:
                    raise RuntimeError(
                        f"{job}: {old} is already research-relative but does not resolve"
                    )
                fresh = _tracked_evidence(job_dir, Path(old).name)
                if fresh["sha256"] != entry.get("sha256"):
                    raise RuntimeError(
                        f"{job}: {old} hashes to {fresh['sha256']}, not the recorded "
                        f"{entry.get('sha256')}"
                    )
                kept.append(fresh)
                dispositions.append(
                    {"from": old, "disposition": "already_correct", "to": old}
                )
                report["totals"]["already_correct"] += 1
                continue

            name = Path(old).name
            candidate = job_dir / name
            recorded = entry.get("sha256")
            if (
                candidate.is_file()
                and candidate.stat().st_size > 0
                and recorded
                and _sha256(candidate) == recorded
            ):
                fresh = _tracked_evidence(job_dir, name)
                kept.append(fresh)
                dispositions.append(
                    {"from": old, "disposition": "repointed", "to": fresh["path"]}
                )
                report["totals"]["repointed"] += 1
                continue

            unkept.append(dict(entry))
            dispositions.append(
                {"from": old, "disposition": "unkept", "reason": _unkept_reason(candidate, recorded)}
            )
            report["totals"]["unkept"] += 1

        attested = {entry["path"] for entry in kept}
        kept_result = f"jobs/{job}/result.json"
        if kept_result not in attested:
            if not (job_dir / "result.json").is_file():
                raise RuntimeError(f"{job}: the job kept no result.json to attest")
            kept.append(_tracked_evidence(job_dir, "result.json"))
            dispositions.append(
                {
                    "from": None,
                    "disposition": "attested_kept",
                    "to": kept_result,
                    "reason": "the kept record was attested by nothing",
                }
            )
            report["totals"]["attested_kept"] += 1

        updated = dict(payload)
        # The original order is preserved.  The gate does not read order, so
        # re-sorting would churn records that were already correct and bury the real
        # repair under noise in git blame.
        updated["artifacts"] = kept
        if unkept:
            updated["unkept_workspace_attestations"] = unkept
        else:
            updated.pop("unkept_workspace_attestations", None)
        if updated != payload:
            _write_json(manifest_path, updated)
            report["totals"]["jobs_changed"] += 1
        report["jobs"].append({"job": job, "dispositions": dispositions})

    return report


CLAIMS_RELATIVE = "research/claims.json"
FINDINGS_RELATIVE = "research/findings.json"

# What a claim's plan status must be corroborated by, read off the decisive run's
# own record. A calibration claim is carried by a calibration gate; a scientific
# claim is carried by an analysis gate. Keeping the two apart is what stops a
# passing calibration from being read as a passing experiment.
CLAIM_STANDINGS = {
    "passed_gate_claim_supported": "the analysis gate passed and a contrast cleared its effective threshold",
    "passed_gate_valid_null": "the analysis gate passed and no contrast cleared its threshold",
    "failed_gate": "the analysis gate did not pass",
    "completed": "the run completed and reports a calibration verdict",
    "not_recorded": "no run has recorded a verdict",
}
PLAN_STATUS_REQUIRES = {
    "supported": ("passed_gate_claim_supported", "completed"),
    "refuted": ("passed_gate_valid_null", "failed_gate"),
    "contradicted": ("passed_gate_valid_null", "failed_gate"),
    "deferred": ("not_recorded",),
    "pending": ("not_recorded",),
    "blocked": ("not_recorded",),
}


def _record_standing(result: Mapping[str, Any]) -> str:
    """Read a run's own verdict, in the vocabulary the plan is checked against."""
    if result.get("analysis_gate_pass") is True:
        return (
            "passed_gate_claim_supported"
            if result.get("claim_supported") is True
            else "passed_gate_valid_null"
        )
    if result.get("analysis_gate_pass") is False:
        return "failed_gate"
    if result.get("pass") is True:
        return "completed"
    if result.get("pass") is False:
        return "failed_gate"
    return "not_recorded"


def _falsification_conditions(result: Mapping[str, Any]) -> Dict[str, bool]:
    """The named conditions that had to hold, as the run itself recorded them.

    Read, never judged: whichever set of gates the record carries is the set the
    claim is checked against, so a claim cannot be written against conditions that
    were not actually evaluated.
    """
    for key in ("gates", "gate_layers"):
        value = result.get(key)
        if isinstance(value, Mapping) and value:
            return {str(name): bool(flag) for name, flag in sorted(value.items())}
    if isinstance(result.get("pass"), bool):
        return {"pass": result["pass"]}
    return {}


def derive_claims(project_root: Path) -> dict[str, Any]:
    """Derive the cycle's claim ledger and finding record from the run artifacts.

    Both files are *derived*, never typed. For every claim in ``research/plan.json``
    this reads the records of the experiments the plan names for it, takes the last
    one that recorded a verdict as decisive, and refuses if that verdict does not
    corroborate the plan's status. So the pre-registered status stays the claim's
    status -- the generator's job is to prove the records agree with it, not to
    overrule it -- and a disagreement stops the derivation instead of becoming a
    quiet edit.

    Evidence is the manifest artifact paths of the claim's experiments, which is why
    the manifests have to be migrated first: a path that the audit gate cannot
    resolve cannot be evidence. Experiments whose record is a failed gate are not
    evidence; they are carried as named antecedents with their standing, so the
    record shows they were read and why they do not carry the verdict.
    """
    run_dir = (project_root / "research").resolve()
    plan = _read_json(run_dir / "plan.json")
    jobs_dir = run_dir / "jobs"
    findings: list[dict[str, Any]] = []
    claims: list[dict[str, Any]] = []

    for claim in plan.get("claims", []):
        claim_id = claim.get("id")
        status = claim.get("status")
        if not isinstance(claim_id, str) or not claim_id:
            raise RuntimeError("a planned claim has no id")
        if status not in PLAN_STATUS_REQUIRES:
            raise RuntimeError(
                f"{claim_id} has plan status {status!r}, which has no registered "
                "corroboration rule"
            )

        # The decisive record is the last experiment on the claim's list that
        # recorded a verdict: the plan lists them in investigative order, so the
        # last one is the most downstream. It is only a heuristic, which is why the
        # corroboration check below refuses if its standing disagrees with the plan.
        decisive: dict[str, Any] | None = None
        for experiment in claim.get("experiments", []):
            result_path = jobs_dir / experiment / "result.json"
            if not result_path.is_file():
                continue
            standing = _record_standing(_read_json(result_path))
            if standing == "not_recorded":
                continue
            decisive = {
                "experiment": experiment,
                "standing": standing,
                "result": str(_relative(project_root, result_path)),
            }

        evidence: list[str] = []
        negative_antecedents: list[dict[str, Any]] = []
        for experiment in claim.get("experiments", []):
            result_path = jobs_dir / experiment / "result.json"
            if not result_path.is_file():
                continue
            standing = _record_standing(_read_json(result_path))
            is_decisive = decisive is not None and experiment == decisive["experiment"]
            if not is_decisive and standing == "failed_gate":
                # A negative record on this claim's list is read and named, but it
                # is not evidence *for* the claim -- including it would mean citing
                # a failed gate in support of a supported one.
                negative_antecedents.append(
                    {
                        "experiment": experiment,
                        "standing": standing,
                        "role": (
                            "a negative record on this claim's list; it carries no "
                            "part of this verdict and is cited as no evidence"
                        ),
                    }
                )
                continue
            manifest_path = jobs_dir / experiment / "manifest.json"
            if not manifest_path.is_file():
                if is_decisive:
                    raise RuntimeError(
                        f"{claim_id}: the decisive experiment {experiment} has no "
                        "manifest, so its artifacts cannot be cited as evidence"
                    )
                continue
            for entry in _read_json(manifest_path).get("artifacts") or []:
                relative = entry.get("path")
                target = run_dir / str(relative)
                if not target.is_file() or target.stat().st_size == 0:
                    raise RuntimeError(
                        f"{claim_id}: {relative} is cited as evidence but does not "
                        "resolve under the run directory"
                    )
                if entry.get("sha256") and _sha256(target) != entry["sha256"]:
                    raise RuntimeError(
                        f"{claim_id}: {relative} does not match the hash its manifest "
                        "records; the ledger would cite unattested evidence"
                    )
                if str(relative) not in evidence:
                    evidence.append(str(relative))

        if decisive is None:
            # A claim nothing ran against is not a claim with no evidence; the
            # pre-registration that records it as untested is the evidence.
            evidence = ["plan.json"]

        required = PLAN_STATUS_REQUIRES[status]
        standing = "not_recorded" if decisive is None else decisive["standing"]
        if standing not in required:
            raise RuntimeError(
                f"{claim_id}: the plan records status {status!r}, which requires a "
                f"decisive record with standing {required}, but "
                + (
                    "no experiment recorded a verdict"
                    if decisive is None
                    else f"{decisive['experiment']} records {standing!r}"
                )
            )

        finding: dict[str, Any] = {
            "claim_id": claim_id,
            "verdict": _verdict_for_status(status),
            "claim_text": claim.get("text"),
            "claim_type": claim.get("type"),
            "plan_status": status,
            "interpretation": _interpretation(
                claim_id, status, decisive, negative_antecedents
            ),
            "falsification_check": {
                "criterion": claim.get("falsification"),
                "conditions": (
                    _falsification_conditions(_read_json(jobs_dir / decisive["experiment"] / "result.json"))
                    if decisive is not None
                    else {}
                ),
            },
            "evidence": sorted(evidence),
        }
        if decisive is None:
            finding["blocked_reason"] = claim.get("blocked_by")
        else:
            finding["decisive_record"] = decisive
            if negative_antecedents:
                finding["negative_antecedents"] = negative_antecedents
        findings.append(finding)
        claims.append(
            {
                "claim_id": claim_id,
                "verdict": finding["verdict"],
                "claim_text": claim.get("text"),
                "evidence": sorted(evidence),
            }
        )

    generated_at = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    ledger = {
        "project": plan.get("project_id"),
        "cycle": plan.get("cycle"),
        "generated_at": generated_at,
        "source": "research/plan.json and research/jobs/*/result.json",
        "claims": claims,
    }
    record = {
        "project": plan.get("project_id"),
        "cycle": plan.get("cycle"),
        "generated_at": generated_at,
        "node": "claim_derivation",
        "source": "research/plan.json and research/jobs/*/result.json",
        "reconciliation": {
            finding["claim_id"]: {
                "plan_status": finding["plan_status"],
                "verdict": finding["verdict"],
                "decisive": (finding.get("decisive_record") or {}).get("experiment"),
            }
            for finding in findings
        },
        "claims": claims,
        "findings": findings,
    }
    _write_ledger(run_dir / "claims.json", ledger)
    _write_ledger(run_dir / "findings.json", record)
    return {
        "claims": len(claims),
        "verdicts": {finding["claim_id"]: finding["verdict"] for finding in findings},
        "evidence_files": sum(len(claim["evidence"]) for claim in claims),
        "ledger": CLAIMS_RELATIVE,
        "findings": FINDINGS_RELATIVE,
    }


def _verdict_for_status(status: str) -> str:
    """The plan's own status, in the vocabulary a finding is recorded with."""
    return {
        "supported": "supported",
        "refuted": "not_supported",
        "contradicted": "contradicted",
        "deferred": "inconclusive",
        "pending": "inconclusive",
        "blocked": "inconclusive",
    }[status]


def _write_ledger(path: Path, payload: dict[str, Any]) -> None:
    """Write a derived record, keeping the old stamp when nothing else changed.

    The derive step is run by a *check* command, so it must not dirty the working
    tree just because time passed.  ``generated_at`` therefore means "when this
    record last changed", which is also the more useful reading: a stamp that moves
    on every run tells you when someone last looked, not when the content moved.
    """
    if path.is_file():
        try:
            existing = _read_json(path)
        except Exception:
            existing = None
        if isinstance(existing, dict) and "generated_at" in existing:
            candidate = dict(payload)
            candidate["generated_at"] = existing["generated_at"]
            if candidate == existing:
                return
    _write_json(path, payload)


def _relative(root: Path, path: Path) -> str:
    resolved_root = root.resolve()
    resolved_path = path.resolve()
    if resolved_path != resolved_root and resolved_root not in resolved_path.parents:
        raise ValueError(f"path escapes project root: {path}")
    return resolved_path.relative_to(resolved_root).as_posix()


def _interpretation(
    claim_id: str,
    status: str,
    decisive: Optional[Mapping[str, Any]],
    negative_antecedents: Sequence[Mapping[str, Any]],
) -> str:
    if decisive is None:
        return (
            f"The plan records {claim_id} as {status} and no experiment on its list "
            "has recorded a verdict, so there is nothing to support and nothing to "
            "contradict."
        )
    text = (
        f"The plan records {claim_id} as {status}. Its decisive record is "
        f"{decisive['experiment']}, whose own verdict reads "
        f"'{CLAIM_STANDINGS[decisive['standing']]}' ({decisive['standing']}), which "
        "is what the plan's status requires."
    )
    if negative_antecedents:
        named = ", ".join(item["experiment"] for item in negative_antecedents)
        text += (
            f" The claim's list also names {named}, whose own records are negative; "
            "they are read as antecedents and carry no part of this verdict."
        )
    return text



    resolved_root = root.resolve()
    resolved_path = path.resolve()
    if resolved_path != resolved_root and resolved_root not in resolved_path.parents:
        raise ValueError(f"path escapes project root: {path}")
    return resolved_path.relative_to(resolved_root).as_posix()


def _unkept_reason(candidate: Path, recorded: Any) -> str:
    if not candidate.is_file():
        return "no file of that name is kept in the job directory"
    if candidate.stat().st_size == 0:
        return "the file of that name is empty"
    return "the kept file of that name has different bytes than the entry records"



    resolved_root = root.resolve()
    resolved_path = path.resolve()
    if resolved_path != resolved_root and resolved_root not in resolved_path.parents:
        raise ValueError(f"path escapes project root: {path}")
    return resolved_path.relative_to(resolved_root).as_posix()


def validate_v1f(
    calibration_path: Path, result_path: Path, config_path: Path
) -> dict[str, Any]:
    calibration = _read_json(calibration_path)
    result = _read_json(result_path)
    config = _read_json(config_path)
    if calibration.get("experiment") != V1F_ID or calibration.get("pass") is not True:
        raise RuntimeError("V1F calibration is missing or did not pass")
    if result.get("experiment") != V1F_ID or result.get("pass") is not True:
        raise RuntimeError("V1F result is missing or did not pass")
    if result.get("status") not in {
        "completed",
        "completed_passed_gate",
        "executed_passed",
    }:
        raise RuntimeError("V1F result is not complete")
    if result.get("execution_completed") is not True:
        raise RuntimeError("V1F execution completion is not certified")
    if config.get("experiment_id") != V1F_ID:
        raise RuntimeError("V1F config has the wrong experiment_id")
    seeds = config.get("seeds", [])
    conditions = config.get("conditions", [])
    if not all(isinstance(item, Mapping) for item in conditions) or (
        len(seeds) != 64
        or len(set(seeds)) != 64
        or len(conditions) != 15
        or len({item.get("name") for item in conditions}) != 15
    ):
        raise RuntimeError("V1F must bind exactly 64 seeds and 15 conditions")
    if result.get("runs_completed") != 960 or result.get("run_failures") != 0:
        raise RuntimeError("V1F does not contain a clean 960-run completion")

    required_layers = {
        "invariants",
        "timestep_convergence",
        "storage_order_sensitivity",
        "stationarity",
        "precision",
        "adjacent_window_stability",
    }
    layers = calibration.get("gate_layers")
    if not isinstance(layers, Mapping) or any(layers.get(key) is not True for key in required_layers):
        raise RuntimeError("V1F did not pass every numerical and steady-estimand gate")
    numerical = calibration.get("numerical_resolution_limits")
    if not isinstance(numerical, Mapping):
        raise RuntimeError("V1F has no numerical_resolution_limits")
    for metric in EFFECT_METRICS:
        value = numerical.get(metric)
        if not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
            raise RuntimeError(f"V1F numerical limit is invalid for {metric}")

    expected_calibration_sha = result.get("calibration_sha256")
    actual_calibration_sha = _sha256(calibration_path)
    if not isinstance(expected_calibration_sha, str) or len(expected_calibration_sha) != 64:
        raise RuntimeError("V1F result does not contain a calibration SHA-256")
    if expected_calibration_sha != actual_calibration_sha:
        raise RuntimeError("V1F result does not bind the supplied calibration")
    expected_config_sha = result.get("config_sha256")
    if not isinstance(expected_config_sha, str) or len(expected_config_sha) != 64:
        raise RuntimeError("V1F result does not contain a config SHA-256")
    if expected_config_sha != _sha256(config_path):
        raise RuntimeError("V1F result does not bind the supplied config")

    frozen_from_v1f = {
        "population": 1000,
        "grid_shape": [64, 64],
        "total_time": 4500.0,
        "output_time_interval": 5.0,
        "steady_snapshots": 144,
        "omp_threads": 1,
        "parallel": 8,
        "per_run_timeout_seconds": 10800,
    }
    for key, expected in frozen_from_v1f.items():
        if config.get(key) != expected:
            raise RuntimeError(f"V1F config changed frozen field {key}")
    for key, expected in MODEL_PARAMETERS.items():
        if key == "dt":
            continue
        if config.get(key) != expected:
            raise RuntimeError(f"V1F config changed frozen model field {key}")
    expected_gate_fields = {
        "independent_precision_absolute_half_widths": ABSOLUTE_GATE_BOUNDS,
        "independent_precision_relative_half_widths": {"wealth_variance": 0.2},
        "adjacent_window_absolute_bounds": ABSOLUTE_GATE_BOUNDS,
        "adjacent_window_relative_bounds": {"wealth_variance": 0.1},
    }
    for key, expected in expected_gate_fields.items():
        if config.get(key) != expected:
            raise RuntimeError(f"V1F config changed frozen gate field {key}")
    if sorted(float(value) for value in config.get("timesteps", [])) != [0.005, 0.01, 0.02]:
        raise RuntimeError("V1F does not contain the frozen three timesteps")
    expected_condition_names = {
        f"{landscape}-dt-{dt}"
        for landscape in ("smooth", "clustered", "shuffled")
        for dt in ("0.02", "0.01", "0.005")
    } | {
        f"order-{order}-dt-{dt}"
        for order in ("canonical", "permuted")
        for dt in ("0.02", "0.01", "0.005")
    }
    if {str(item["name"]) for item in conditions} != expected_condition_names:
        raise RuntimeError("V1F condition matrix differs from the frozen 15-cell design")
    if set(E1_SEEDS) & set(seeds):
        raise RuntimeError("E1 seeds overlap V1F calibration seeds")
    calibrated_binary_sha256 = result.get("binary_sha256")
    if (
        not isinstance(calibrated_binary_sha256, str)
        or len(calibrated_binary_sha256) != 64
        or any(character not in "0123456789abcdef" for character in calibrated_binary_sha256)
    ):
        raise RuntimeError("V1F archive does not bind the calibrated reference binary")
    return {
        "calibration": calibration,
        "calibration_sha256": actual_calibration_sha,
        "result_sha256": _sha256(result_path),
        "config_sha256": _sha256(config_path),
        "binary_sha256": calibrated_binary_sha256,
    }


def _failed_v1f_cells(
    calibration: Mapping[str, Any], steady: Mapping[str, Any]
) -> tuple[list[str], list[str], dict[str, int]]:
    timestep: list[str] = []
    for landscape, metrics in calibration.get("discretization", {}).items():
        if not isinstance(metrics, Mapping):
            continue
        for metric, values in metrics.items():
            if isinstance(values, Mapping) and values.get("pass") is not True:
                timestep.append(f"{landscape}/{metric}")
    storage = [
        str(metric)
        for metric, values in calibration.get("storage_order_sensitivity", {}).items()
        if isinstance(values, Mapping) and values.get("pass") is not True
    ]
    failed_precision_metrics: dict[str, int] = {}
    for condition in steady.get("conditions", {}).values():
        if not isinstance(condition, Mapping):
            continue
        for metric, values in condition.get("metrics", {}).items():
            if not isinstance(values, Mapping):
                continue
            precision = values.get("independent_replicate_precision")
            if isinstance(precision, Mapping) and precision.get("pass") is not True:
                failed_precision_metrics[str(metric)] = (
                    failed_precision_metrics.get(str(metric), 0) + 1
                )
    return sorted(timestep), sorted(storage), failed_precision_metrics


def archive_v1f(root: Path, job_dir: Path, jobctl_dir: Path) -> dict[str, Any]:
    """Validate and compact a completed V1F workspace into tracked evidence."""
    root = root.resolve()
    job_dir = job_dir.resolve()
    jobctl_dir = jobctl_dir.resolve()
    _relative(root, job_dir)
    _relative(root, jobctl_dir)
    if job_dir.name != V1F_ID or jobctl_dir.name != V1F_ID:
        raise ValueError("archive-v1f requires the V1F job and jobctl directories")

    config_path = job_dir / "config.json"
    workspace = job_dir / "workspace"
    config = _read_json(config_path)
    calibration_path = workspace / "numerical_calibration.json"
    calibration = _read_json(calibration_path)
    raw_result_path = workspace / "result.json"
    raw_result = _read_json(raw_result_path)
    steady_path = workspace / "steady_estimand_report.json"
    steady = _read_json(steady_path)
    matched_audit = _read_json(workspace / "matched_input_audit.json")
    jobctl_result = _read_json(jobctl_dir / "result.json")
    jobctl_spec = _read_json(jobctl_dir / "spec.json")

    if config.get("experiment_id") != V1F_ID:
        raise RuntimeError("V1F config has the wrong experiment_id")
    if raw_result.get("experiment") != V1F_ID or raw_result.get("status") != "completed":
        raise RuntimeError("V1F workspace result is not complete")
    if calibration.get("experiment") != V1F_ID:
        raise RuntimeError("V1F workspace calibration has the wrong experiment")
    if not isinstance(calibration.get("pass"), bool):
        raise RuntimeError("V1F calibration has no boolean verdict")
    if raw_result.get("pass") is not calibration.get("pass"):
        raise RuntimeError("V1F result and calibration verdicts disagree")
    if raw_result.get("calibration_sha256") != _sha256(calibration_path):
        raise RuntimeError("V1F workspace result does not bind its calibration")
    if raw_result.get("config_sha256") != _sha256(config_path):
        raise RuntimeError("V1F workspace result does not bind its config")
    if jobctl_spec.get("config_sha256") != _sha256(config_path):
        raise RuntimeError("jobctl spec does not bind the V1F config")
    jobctl_artifacts = jobctl_result.get("artifacts", [])
    if (
        jobctl_result.get("exit_code") != 0
        or jobctl_result.get("timed_out") is not False
        or not isinstance(jobctl_artifacts, list)
        or any(item.get("valid") is not True for item in jobctl_artifacts)
    ):
        raise RuntimeError("jobctl did not record a clean V1F execution")
    recorded_artifacts = {
        Path(str(item.get("path", ""))).name for item in jobctl_artifacts
    }
    if recorded_artifacts != set(V1F_WORKSPACE_ARTIFACTS):
        raise RuntimeError("jobctl artifact declaration differs from V1F outputs")
    if matched_audit.get("pass") is not True:
        raise RuntimeError("V1F matched-input audit did not pass")

    run_specs_payload = _read_json(workspace / "run_specs.json")
    run_specs = run_specs_payload.get("runs")
    if not isinstance(run_specs, list):
        raise RuntimeError("V1F run_specs.json has no runs list")
    expected_run_count = len(config.get("seeds", [])) * len(config.get("conditions", []))
    if expected_run_count != 960 or len(run_specs) != expected_run_count:
        raise RuntimeError("V1F must contain exactly 960 run specs")
    expected_run_ids = {str(spec.get("run_id")) for spec in run_specs}
    if len(expected_run_ids) != expected_run_count or "None" in expected_run_ids:
        raise RuntimeError("V1F run IDs are missing or duplicated")

    marker_paths = sorted((workspace / "runs").glob("*/completion.json"))
    if len(marker_paths) != expected_run_count:
        raise RuntimeError(
            f"V1F completion markers are incomplete: {len(marker_paths)}/{expected_run_count}"
        )
    markers = [_read_json(path) for path in marker_paths]
    marker_run_ids = {str(marker.get("run_id")) for marker in markers}
    if marker_run_ids != expected_run_ids:
        raise RuntimeError("V1F completion markers do not match run specs")
    if any(marker.get("status") != "completed" for marker in markers):
        raise RuntimeError("V1F contains a non-completed marker")
    health_paths = [path.parent / "health.json" for path in marker_paths]
    if any(not path.is_file() for path in health_paths):
        raise RuntimeError("V1F has a completed run without health.json")
    if any(not isinstance(_read_json(path), Mapping) for path in health_paths):
        raise RuntimeError("V1F contains an invalid health.json payload")
    binary_hashes = {marker.get("binary_sha256") for marker in markers}
    if len(binary_hashes) != 1 or not all(
        isinstance(value, str) and len(value) == 64 for value in binary_hashes
    ):
        raise RuntimeError("V1F completion markers do not bind one reference binary")
    binary_path = (root / str(config.get("binary", ""))).resolve()
    _relative(root, binary_path)
    if not binary_path.is_file() or _sha256(binary_path) not in binary_hashes:
        raise RuntimeError("V1F completion markers do not match the reference binary")
    if {marker.get("omp_threads") for marker in markers} != {1}:
        raise RuntimeError("V1F completion markers do not all use OMP=1")

    for name in V1F_WORKSPACE_ARTIFACTS:
        path = workspace / name
        if not path.is_file() or path.stat().st_size == 0:
            raise RuntimeError(f"V1F workspace artifact is missing or empty: {name}")
    artifact_hashes = {
        name: _sha256(workspace / name) for name in V1F_WORKSPACE_ARTIFACTS
    }
    failed_timestep, failed_storage, failed_precision = _failed_v1f_cells(
        calibration, steady
    )
    conditions = steady.get("conditions", {})
    if not isinstance(conditions, Mapping) or len(conditions) != 9:
        raise RuntimeError("V1F steady report must contain nine timestep conditions")
    if steady.get("replicates_per_condition") != 64:
        raise RuntimeError("V1F steady report must contain 64 replicates per condition")
    gate_layers = calibration.get("gate_layers", {})
    required_gate_layers = {
        "invariants",
        "timestep_convergence",
        "storage_order_sensitivity",
        "stationarity",
        "precision",
        "adjacent_window_stability",
    }
    if not isinstance(gate_layers, Mapping) or any(
        not isinstance(gate_layers.get(key), bool) for key in required_gate_layers
    ):
        raise RuntimeError("V1F calibration gate layers are incomplete")
    expected_steady_flags = {
        "stationarity": "tail_stationarity_valid",
        "adjacent_window_stability": "adjacent_window_stability_valid",
        "precision": "independent_replicate_precision_valid",
    }
    for calibration_key, steady_key in expected_steady_flags.items():
        if gate_layers.get(calibration_key) is not steady.get(steady_key):
            raise RuntimeError(
                f"V1F calibration and steady report disagree on {calibration_key}"
            )

    source_commit = jobctl_spec.get("commit_id")
    if (
        not isinstance(source_commit, str)
        or len(source_commit) != 40
        or any(character not in "0123456789abcdef" for character in source_commit)
    ):
        raise RuntimeError("jobctl spec does not contain a full lowercase source commit")
    elapsed_seconds = [float(marker.get("elapsed_seconds", 0.0)) for marker in markers]
    if any(not math.isfinite(value) or value < 0.0 for value in elapsed_seconds):
        raise RuntimeError("V1F completion markers contain invalid elapsed time")
    jobctl_wall_seconds = float(jobctl_result.get("wall_seconds", 0.0))
    if not math.isfinite(jobctl_wall_seconds) or jobctl_wall_seconds < 0.0:
        raise RuntimeError("jobctl result contains invalid wall time")

    tracked_calibration_path = job_dir / "numerical_calibration.json"
    tracked_calibration_temp = tracked_calibration_path.with_suffix(".json.tmp")
    shutil.copyfile(calibration_path, tracked_calibration_temp)
    os.replace(tracked_calibration_temp, tracked_calibration_path)
    compact_result = {
        "experiment": V1F_ID,
        "status": (
            "completed_passed_gate"
            if calibration.get("pass") is True
            else "completed_failed_gate"
        ),
        "pass": bool(calibration.get("pass")),
        "execution_completed": True,
        "runs_planned": expected_run_count,
        "runs_completed": len(markers),
        "run_failures": 0,
        "execution_host": "umi",
        "source_commit": source_commit,
        "binary_sha256": next(iter(binary_hashes)),
        "config_sha256": _sha256(config_path),
        "calibration_sha256": _sha256(tracked_calibration_path),
        "elapsed_cpu_hours": sum(elapsed_seconds) / 3600.0,
        "maximum_single_run_seconds": max(elapsed_seconds),
        "jobctl_wall_seconds": jobctl_wall_seconds,
        "gate_layers": {
            "invariants": gate_layers.get("invariants") is True,
            "timestep_convergence": gate_layers.get("timestep_convergence") is True,
            "storage_order_sensitivity": gate_layers.get("storage_order_sensitivity") is True,
            "tail_stationarity": gate_layers.get("stationarity") is True,
            "adjacent_window_stability": gate_layers.get("adjacent_window_stability") is True,
            "independent_replicate_precision": gate_layers.get("precision") is True,
        },
        "temporal_ess_diagnostic_valid": bool(
            steady.get("temporal_ess_diagnostic_valid")
        ),
        "steady_estimand_layer": {
            "conditions": len(conditions),
            "replicates_per_condition": steady.get("replicates_per_condition"),
            "tail_stationarity_failed_conditions": sum(
                item.get("tail_stationarity_pass") is not True
                for item in conditions.values()
            ),
            "adjacent_window_failed_conditions": sum(
                item.get("adjacent_window_stability_pass") is not True
                for item in conditions.values()
            ),
            "independent_precision_failed_conditions": sum(
                item.get("independent_replicate_precision_pass") is not True
                for item in conditions.values()
            ),
            "temporal_ess_diagnostic_failed_conditions": sum(
                item.get("temporal_ess_diagnostic_pass") is not True
                for item in conditions.values()
            ),
            "independent_precision_failed_metric_cells": sum(
                failed_precision.values()
            ),
            "failed_precision_metrics": failed_precision,
        },
        "numerical_resolution_limits": calibration.get(
            "numerical_resolution_limits", {}
        ),
        "failed_timestep_cells": failed_timestep,
        "failed_storage_order_metrics": failed_storage,
        "workspace_artifact_sha256": artifact_hashes,
        "conclusion": (
            "V1F completed 960/960 runs and passed every frozen calibration gate."
            if calibration.get("pass") is True
            else "V1F completed 960/960 runs but failed one or more frozen calibration gates."
        ),
        "next_action": (
            "Run Cycle 4 promotion prepare; E1 remains blocked until V0G and finalization pass."
            if calibration.get("pass") is True
            else "Archive the independent negative calibration and keep E1 blocked."
        ),
        "evidence_boundary": (
            "Independent numerical calibration only; no Cycle 4 landscape-effect claim is supported."
        ),
    }
    compact_result_path = job_dir / "result.json"
    _write_json(compact_result_path, compact_result)
    manifest = _tracked_manifest(
        job_dir,
        ["numerical_calibration.json", "result.json"],
        exit_code=0,
        wall_seconds=jobctl_result.get("wall_seconds"),
    )
    _write_json(job_dir / "manifest.json", manifest)

    if compact_result["pass"] is True:
        validate_v1f(tracked_calibration_path, compact_result_path, config_path)
    return compact_result


def archive_e1(root: Path, job_dir: Path, jobctl_dir: Path) -> dict[str, Any]:
    """Validate and compact a completed E1-C4 workspace into tracked evidence.

    This is a validation-and-compaction step, not an analysis step.  The
    confirmatory verdict is produced by the frozen E1-C4 runner and is copied
    verbatim; nothing here recomputes an effect, applies a threshold, or can
    relax a gate.  Every branch either reproduces a number that the run already
    recorded or refuses.

    Unlike ``archive_v1f`` this contract was authored *after* the E1-C4 run had
    already finished, because the promotion module shipped without an E1
    archival path.  That is recorded as a process deviation in the remediation
    ledger.  The direction of the omission is safe: a missing archive could only
    have lost evidence, and adding one can only refuse or copy.
    """
    root = root.resolve()
    job_dir = job_dir.resolve()
    jobctl_dir = jobctl_dir.resolve()
    _relative(root, job_dir)
    _relative(root, jobctl_dir)
    if job_dir.name != E1_ID or jobctl_dir.name != E1_ID:
        raise ValueError("archive-e1 requires the E1-C4 job and jobctl directories")

    config_path = job_dir / "config.json"
    workspace = job_dir / "workspace"
    config = _read_json(config_path)
    if config.get("experiment_id") != E1_ID:
        raise RuntimeError("E1-C4 config has the wrong experiment_id")

    lock_path = (root / "research/parameter_lock.cycle4.json").resolve()
    _relative(root, lock_path)
    lock = _read_json(lock_path)
    if (
        lock.get("status") != "final"
        or lock.get("confirmatory_execution_authorized") is not True
    ):
        raise RuntimeError("E1-C4 was not authorized by a final Cycle 4 parameter lock")
    if E1_ID not in (lock.get("authorized_experiments") or []):
        raise RuntimeError("the final Cycle 4 lock does not authorize E1-C4")
    lock_sha256 = _sha256(lock_path)
    if config.get("parameter_lock_sha256") != lock_sha256:
        raise RuntimeError("E1-C4 config does not bind the final Cycle 4 lock")
    calibration = lock.get("numerical_calibration")
    if not isinstance(calibration, Mapping):
        raise RuntimeError("the final Cycle 4 lock has no numerical calibration block")
    reference_binary_sha256 = calibration.get("reference_binary_sha256")
    if (
        not isinstance(reference_binary_sha256, str)
        or len(reference_binary_sha256) != 64
    ):
        raise RuntimeError("the final Cycle 4 lock does not bind a calibrated binary")
    if config.get("binary_sha256") != reference_binary_sha256:
        raise RuntimeError("E1-C4 config does not bind the calibrated reference binary")

    raw_result = _read_json(workspace / "result.json")
    if raw_result.get("experiment") != E1_ID or raw_result.get("status") != "completed":
        raise RuntimeError("E1-C4 workspace result is not complete")
    if not isinstance(raw_result.get("pass"), bool):
        raise RuntimeError("E1-C4 workspace result has no boolean verdict")
    if raw_result.get("config_sha256") != _sha256(config_path):
        raise RuntimeError("E1-C4 workspace result does not bind its config")
    if raw_result.get("parameter_lock_sha256") != lock_sha256:
        raise RuntimeError("E1-C4 workspace result does not bind the final lock")

    jobctl_result = _read_json(jobctl_dir / "result.json")
    jobctl_spec = _read_json(jobctl_dir / "spec.json")
    if jobctl_spec.get("commit_id") != lock.get("source_commit"):
        raise RuntimeError("jobctl spec does not bind the finalized source commit")
    artifacts = jobctl_result.get("artifacts", [])
    if (
        jobctl_result.get("exit_code") != 0
        or jobctl_result.get("timed_out") is not False
        or not isinstance(artifacts, list)
        or any(item.get("valid") is not True for item in artifacts)
    ):
        raise RuntimeError("jobctl did not record a clean E1-C4 execution")
    recorded_artifacts = {Path(str(item.get("path", ""))).name for item in artifacts}
    if recorded_artifacts != set(E1_WORKSPACE_ARTIFACTS):
        raise RuntimeError("jobctl artifact declaration differs from E1-C4 outputs")
    if any(item.get("contained_in_cwd") is not True for item in artifacts):
        raise RuntimeError("jobctl recorded an E1-C4 artifact outside its workspace")

    for name in E1_WORKSPACE_ARTIFACTS + E1_UNDECLARED_PROVENANCE:
        path = workspace / name
        if not path.is_file() or path.stat().st_size == 0:
            raise RuntimeError(f"E1-C4 workspace artifact is missing or empty: {name}")
    artifact_hashes = {
        name: _sha256(workspace / name)
        for name in E1_WORKSPACE_ARTIFACTS + E1_UNDECLARED_PROVENANCE
    }

    seeds = config.get("seeds", [])
    if len(seeds) != E1_SEED_COUNT or len(set(seeds)) != E1_SEED_COUNT:
        raise RuntimeError(f"E1-C4 must bind exactly {E1_SEED_COUNT} seeds")
    # E1-C4's matched two-condition matrix is imposed by the runner and is not
    # repeated in the job config, so the pre-registered design is read from the
    # final lock and the executed run specs are required to reproduce it exactly.
    design = lock.get("design_contract")
    if not isinstance(design, Mapping):
        raise RuntimeError("the final Cycle 4 lock has no design contract")
    if (
        design.get("conditions") != list(E1_CONDITIONS)
        or design.get("run_count") != E1_RUN_COUNT
        or design.get("seed_count") != E1_SEED_COUNT
    ):
        raise RuntimeError("the final Cycle 4 lock does not freeze the E1-C4 design")

    run_specs_payload = _read_json(workspace / "run_specs.json")
    run_specs = run_specs_payload.get("runs")
    if not isinstance(run_specs, list) or len(run_specs) != E1_RUN_COUNT:
        raise RuntimeError(f"E1-C4 must contain exactly {E1_RUN_COUNT} run specs")
    expected_run_ids = {str(spec.get("run_id")) for spec in run_specs}
    if len(expected_run_ids) != E1_RUN_COUNT or "None" in expected_run_ids:
        raise RuntimeError("E1-C4 run IDs are missing or duplicated")
    declared_design = {
        (int(spec.get("seed")), str(spec.get("condition"))) for spec in run_specs
    }
    if declared_design != {
        (int(seed), name) for seed in seeds for name in E1_CONDITIONS
    }:
        raise RuntimeError("E1-C4 run specs do not cover the frozen seed x condition design")

    marker_paths = sorted((workspace / "runs").glob("*/completion.json"))
    if len(marker_paths) != E1_RUN_COUNT:
        raise RuntimeError(
            f"E1-C4 completion markers are incomplete: {len(marker_paths)}/{E1_RUN_COUNT}"
        )
    markers = [_read_json(path) for path in marker_paths]
    if {str(marker.get("run_id")) for marker in markers} != expected_run_ids:
        raise RuntimeError("E1-C4 completion markers do not match run specs")
    if any(marker.get("status") != "completed" for marker in markers):
        raise RuntimeError("E1-C4 contains a non-completed marker")
    if {marker.get("binary_sha256") for marker in markers} != {
        reference_binary_sha256
    }:
        raise RuntimeError(
            "E1-C4 completion markers do not bind the calibrated reference binary"
        )
    if {marker.get("omp_threads") for marker in markers} != {1}:
        raise RuntimeError("E1-C4 completion markers do not all use OMP=1")

    # Tie every marker to the numerical payload it claims: the recorded final
    # snapshot must be present and hash to the value the marker bound.
    for path, marker in zip(marker_paths, markers):
        health = path.parent / "health.json"
        if not health.is_file() or not isinstance(_read_json(health), Mapping):
            raise RuntimeError("E1-C4 has a completed run without a valid health.json")
        snapshot = path.parent / str(marker.get("final_snapshot", ""))
        if not snapshot.is_file() or _sha256(snapshot) != marker.get(
            "final_snapshot_sha256"
        ):
            raise RuntimeError(
                "E1-C4 final snapshot is missing or does not match its marker"
            )

    binary_path = (root / str(config.get("binary", ""))).resolve()
    _relative(root, binary_path)
    if not binary_path.is_file() or _sha256(binary_path) != reference_binary_sha256:
        raise RuntimeError("E1-C4 config does not point at the calibrated reference binary")

    matched_audit = _read_json(workspace / "matched_input_audit.json")
    if matched_audit.get("pass") is not True:
        raise RuntimeError("E1-C4 matched-input audit did not pass")
    lock_audit = _read_json(workspace / "parameter_lock_audit.json")
    if lock_audit.get("pass") is not True:
        raise RuntimeError("E1-C4 parameter-lock audit did not pass")
    if lock_audit.get("parameter_lock_sha256") != lock_sha256:
        raise RuntimeError("E1-C4 parameter-lock audit does not bind the final lock")
    if lock_audit.get("parameter_lock_status") != "final":
        raise RuntimeError("E1-C4 parameter-lock audit did not run against a final lock")

    paired = _read_json(workspace / "paired_effects.json")
    if paired.get("experiment") != E1_ID:
        raise RuntimeError("E1-C4 paired-effects report has the wrong experiment")
    if paired.get("comparison") != "clustered-minus-shuffled":
        raise RuntimeError("E1-C4 paired-effects report has the wrong comparison")
    if not isinstance(paired.get("analysis_gate_pass"), bool) or not isinstance(
        paired.get("claim_supported"), bool
    ):
        raise RuntimeError("E1-C4 paired-effects report has no boolean verdict")
    gates = paired.get("gates")
    if not isinstance(gates, Mapping) or any(
        not isinstance(gates.get(key), bool) for key in E1_PAIRED_GATES
    ):
        raise RuntimeError("E1-C4 paired-effects gate block is incomplete")
    invariant_checks = paired.get("execution_invariant_checks")
    if not isinstance(invariant_checks, Mapping) or not invariant_checks:
        raise RuntimeError("E1-C4 paired-effects report has no invariant block")
    if gates.get("execution_invariants") is not all(invariant_checks.values()):
        raise RuntimeError("E1-C4 invariant gate disagrees with its own checks")
    if gates.get("matched_inputs") is not matched_audit.get("pass"):
        raise RuntimeError("E1-C4 matched-input gate disagrees with the input audit")
    if paired.get("analysis_gate_pass") is not all(
        gates.get(key) is True for key in E1_PAIRED_GATES
    ):
        raise RuntimeError("E1-C4 analysis gate verdict disagrees with its gate block")
    if paired.get("claim_supported") is True and paired.get("analysis_gate_pass") is not True:
        raise RuntimeError("E1-C4 claims support while failing its analysis gate")

    steady = _read_json(workspace / "steady_estimand_report.json")
    if steady.get("experiment") != E1_ID:
        raise RuntimeError("E1-C4 steady report has the wrong experiment")
    if steady.get("replicates_per_condition") != E1_SEED_COUNT:
        raise RuntimeError("E1-C4 steady report must contain 64 replicates per condition")
    steady_conditions = steady.get("conditions")
    if (
        not isinstance(steady_conditions, Mapping)
        or set(steady_conditions) != set(E1_CONDITIONS)
    ):
        raise RuntimeError("E1-C4 steady report does not cover both conditions")
    for gate_key, steady_key in {
        "tail_stationarity": "tail_stationarity_valid",
        "adjacent_window_stability": "adjacent_window_stability_valid",
        "independent_replicate_precision": "independent_replicate_precision_valid",
    }.items():
        if gates.get(gate_key) is not steady.get(steady_key):
            raise RuntimeError(
                f"E1-C4 paired-effects and steady report disagree on {gate_key}"
            )

    ensemble = _read_json(workspace / "ensemble_stationarity_report.json")
    if ensemble.get("experiment") != E1_ID:
        raise RuntimeError("E1-C4 ensemble report has the wrong experiment")
    if gates.get("tail_stationarity") is not ensemble.get("stationarity_valid"):
        raise RuntimeError(
            "E1-C4 paired-effects and ensemble report disagree on stationarity"
        )

    stationarity = _read_json(workspace / "stationarity_report.json")
    if stationarity.get("experiment") != E1_ID:
        raise RuntimeError("E1-C4 stationarity report has the wrong experiment")
    if not isinstance(stationarity.get("pass"), bool):
        raise RuntimeError("E1-C4 stationarity report has no boolean verdict")

    source_commit = jobctl_spec.get("commit_id")
    if (
        not isinstance(source_commit, str)
        or len(source_commit) != 40
        or any(character not in "0123456789abcdef" for character in source_commit)
    ):
        raise RuntimeError("jobctl spec does not contain a full lowercase source commit")
    elapsed_seconds = [float(marker.get("elapsed_seconds", 0.0)) for marker in markers]
    if any(not math.isfinite(value) or value < 0.0 for value in elapsed_seconds):
        raise RuntimeError("E1-C4 completion markers contain invalid elapsed time")
    jobctl_wall_seconds = float(jobctl_result.get("wall_seconds", 0.0))
    if not math.isfinite(jobctl_wall_seconds) or jobctl_wall_seconds < 0.0:
        raise RuntimeError("jobctl result contains invalid wall time")

    tracked_paired_path = job_dir / "paired_effects.json"
    tracked_paired_temp = tracked_paired_path.with_suffix(".json.tmp")
    shutil.copyfile(workspace / "paired_effects.json", tracked_paired_temp)
    os.replace(tracked_paired_temp, tracked_paired_path)

    gate_pass = paired.get("analysis_gate_pass") is True
    claim_supported = paired.get("claim_supported") is True
    if not gate_pass:
        status = "completed_failed_gate"
    elif claim_supported:
        status = "completed_passed_gate_claim_supported"
    else:
        status = "completed_passed_gate_valid_null"
    compact_result = {
        "experiment": E1_ID,
        "status": status,
        "analysis_gate_pass": gate_pass,
        "claim_supported": claim_supported,
        "valid_null_or_equivalence": bool(paired.get("valid_null_or_equivalence", False)),
        "execution_completed": True,
        "runs_planned": E1_RUN_COUNT,
        "runs_completed": len(markers),
        "run_failures": 0,
        "execution_host": "umi",
        "source_commit": source_commit,
        "binary_sha256": reference_binary_sha256,
        "config_sha256": _sha256(config_path),
        "parameter_lock_sha256": lock_sha256,
        "comparison": paired.get("comparison"),
        "elapsed_cpu_hours": sum(elapsed_seconds) / 3600.0,
        "maximum_single_run_seconds": max(elapsed_seconds),
        "jobctl_wall_seconds": jobctl_wall_seconds,
        "gates": {key: bool(gates.get(key)) for key in E1_PAIRED_GATES},
        "temporal_ess_diagnostic_pass": paired.get("temporal_ess_diagnostic_pass"),
        "paired_effects_sha256": _sha256(tracked_paired_path),
        "workspace_artifact_sha256": artifact_hashes,
        "conclusion": (
            "E1-C4 completed 128/128 runs and supported the frozen matched-landscape claim."
            if claim_supported
            else (
                "E1-C4 completed 128/128 runs and returned a valid null/equivalence result."
                if gate_pass
                else "E1-C4 completed 128/128 runs but failed one or more frozen analysis gates."
            )
        ),
        "evidence_boundary": raw_result.get("evidence_boundary")
        or "Synthetic generative mechanism only; no historical-state claim.",
    }
    compact_result_path = job_dir / "result.json"
    _write_json(compact_result_path, compact_result)

    manifest = _tracked_manifest(
        job_dir,
        ["paired_effects.json", "result.json"],
        exit_code=0,
        wall_seconds=jobctl_result.get("wall_seconds"),
        archived_after_run=True,
        undeclared_provenance_sha256={
            name: artifact_hashes[name] for name in E1_UNDECLARED_PROVENANCE
        },
    )
    _write_json(job_dir / "manifest.json", manifest)


    if _sha256(workspace / "paired_effects.json") != compact_result[
        "paired_effects_sha256"
    ]:
        raise RuntimeError("archived E1-C4 verdict does not match the workspace verdict")
    return compact_result


def _candidate_lock(source_commit: str, v1f: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "lock_id": "ar-politeia-cycle4-confirmatory-v1",
        "status": "candidate",
        "confirmatory_execution_authorized": False,
        "locked_before_confirmatory_outcomes": True,
        "promotion_base_commit": source_commit,
        "source_commit": "pending clean V0G checkout",
        "analysis_commit": "pending clean V0G checkout",
        "authorized_experiments": [],
        "numerical_calibration": {
            "experiment": V1F_ID,
            "path": f"research/jobs/{V1F_ID}/numerical_calibration.json",
            "sha256": v1f["calibration_sha256"],
            "result_sha256": v1f["result_sha256"],
            "config_sha256": v1f["config_sha256"],
            # The numerical resolution limits were measured by executing this exact
            # binary. E1-C4 must execute the same artifact, so the SHA is carried
            # forward and enforced at finalize time.
            "reference_binary_sha256": v1f["binary_sha256"],
            "numerical_resolution_limits": v1f["calibration"]["numerical_resolution_limits"],
        },
        "parameters": {
            "population": 1000,
            "grid_shape": [64, 64],
            **MODEL_PARAMETERS,
            "wealth_log_sigma": 0.01,
            "mpi_enabled": False,
            "ranks": 1,
            "omp_threads": 1,
            "parallel": 8,
            "per_run_timeout_seconds": 10800,
            "familywise_alpha": 0.05,
            "bootstrap_samples": 10000,
            "analysis_seed": 9173,
            "scientific_sesoi": SCIENTIFIC_SESOI,
            "independent_precision_absolute_half_widths": ABSOLUTE_GATE_BOUNDS,
            "independent_precision_relative_half_widths": {"wealth_variance": 0.2},
            "adjacent_window_absolute_bounds": ABSOLUTE_GATE_BOUNDS,
            "adjacent_window_relative_bounds": {"wealth_variance": 0.1},
        },
        "design_contract": {
            "conditions": ["clustered", "shuffled"],
            "paired_difference": "clustered-minus-shuffled",
            "primary_family": list(EFFECT_METRICS[:3]),
            "secondary_family": ["wealth_gini"],
            "run_count": 128,
            "seed_count": 64,
            "full_initial_state_match_required": True,
            "resource_histogram_and_accessible_area_match_required": True,
            "temporal_ess_role": "diagnostic_only",
            "valid_null_policy": "A passed analysis gate without a primary effect beyond the effective threshold is retained as valid null/equivalence evidence.",
        },
        "amendment_policy": "After finalization, any outcome-informed change requires a new lock version and research cycle.",
    }


def _e1_config(root: Path, lock: Mapping[str, Any], *, binary_sha256: str | None) -> dict[str, Any]:
    lock_path = root / "research/parameter_lock.cycle4.json"
    config = {
        "experiment_id": E1_ID,
        "binary": f"research/jobs/{V0G_ID}/workspace/build-off/src/politeia",
        "summary_result": f"research/jobs/{E1_ID}/result.json",
        "numerical_calibration": f"research/jobs/{V1F_ID}/numerical_calibration.json",
        "numerical_calibration_sha256": lock["numerical_calibration"]["sha256"],
        "parameter_lock": "research/parameter_lock.cycle4.json",
        "parameter_lock_sha256": _sha256(lock_path),
        "seeds": list(E1_SEEDS),
        **lock["parameters"],
    }
    if binary_sha256 is not None:
        config["binary_sha256"] = binary_sha256
    return config


def _experiment(config: Mapping[str, Any], source_commit: str) -> dict[str, Any]:
    return {
        "id": E1_ID,
        "type": "command",
        "mode": "server",
        "priority": "P0",
        "claim_ids": ["C2-LANDSCAPE-C4"],
        "depends_on": [V1F_ID, V0G_ID],
        "objective": "Estimate the paired clustered-minus-shuffled Cycle 4 effect under the frozen V1F numerical and two-window steady-estimand contract.",
        "command": [
            "python3", "research/src/experiments/run_landscape_study.py",
            "--experiment", E1_ID,
            "--config", f"research/jobs/{E1_ID}/config.json",
            "--output-dir", f"research/jobs/{E1_ID}/workspace",
        ],
        "config": f"research/jobs/{E1_ID}/config.json",
        "config_sha256": "set after config.json is written",
        "commit_id": source_commit,
        "env_snapshot": f"research/jobs/{E1_ID}/env.txt",
        "seeds": list(E1_SEEDS),
        "data_checksums": {
            "external_data": "none",
            "generated_inputs": "SHA-256 values are written to workspace/matched_input_audit.json before execution",
            "dependency_calibration": config["numerical_calibration_sha256"],
            "parameter_lock": config["parameter_lock_sha256"],
            "reference_binary": config.get("binary_sha256", "pending V0G"),
        },
        "artifacts": [
            "result.json", "replicate_metrics.csv", "paired_effects.json",
            "matched_input_audit.json", "stationarity_report.json",
            "steady_estimand_report.json", "parameter_lock_audit.json", "run_specs.json",
        ],
        "timeout_seconds": 86400,
        "gpu_count": 0,
        "failure_policy": "Missing runs or failed invariant/stationarity/precision gates make the result inconclusive; a valid null is retained as evidence.",
    }


def _write_support_files(root: Path, source_commit: str, config: Mapping[str, Any]) -> None:
    e1_dir = root / f"research/jobs/{E1_ID}"
    e1_dir.mkdir(parents=True, exist_ok=True)
    (e1_dir / "commit.txt").write_text(source_commit + "\n", encoding="utf-8")
    (e1_dir / "env.txt").write_text(
        "host=umi\nexecution=CPU_reference\nomp_threads=1\nparallel=8\nmpi=OFF\n"
        f"gpu_count=0\nsource_commit={source_commit}\n",
        encoding="utf-8",
    )
    (e1_dir / "seeds.txt").write_text(
        "\n".join(str(seed) for seed in E1_SEEDS) + "\n", encoding="utf-8"
    )
    outputs = _experiment(config, source_commit)["artifacts"]
    (e1_dir / "outputs.txt").write_text("\n".join(outputs) + "\n", encoding="utf-8")
    (e1_dir / "data_checksums.txt").write_text(
        "external_data=none\n"
        f"dependency_calibration={config['numerical_calibration_sha256']}\n"
        f"parameter_lock={config['parameter_lock_sha256']}\n"
        f"reference_binary={config.get('binary_sha256', 'pending V0G')}\n",
        encoding="utf-8",
    )
    _write_json(
        e1_dir / "computational_strategy.json",
        {
            "approach": "Run 64 matched seed pairs as eight OMP=1 CPU reference processes.",
            "evidence_role": "confirmatory synthetic-mechanism experiment",
            "evidence_boundary": "Supports only the frozen synthetic landscape-mechanism claim, not a historical-state claim.",
            "supports_core_claim": True,
            "reference_method": "validated OpenMP-OFF C++ simulator binary",
            "validation_points": ["Python contract suite", "OpenMP OFF CTest", "OpenMP ON CTest"],
            "agreement": {"criterion": "all tests pass and the executed binary SHA-256 matches the declaration"},
            "reference_validation_required": True,
            "validation_artifact": "parameter_lock_audit.json",
        },
    )
    experiment = _experiment(config, source_commit)
    experiment["config_sha256"] = _sha256(e1_dir / "config.json")
    _write_json(e1_dir / "experiment.json", experiment)


def _assert_no_e1_outcomes(root: Path) -> None:
    e1_dir = root / f"research/jobs/{E1_ID}"
    forbidden = (
        e1_dir / "result.json",
        e1_dir / "paired_effects.json",
        e1_dir / "workspace/result.json",
        e1_dir / "workspace/paired_effects.json",
        e1_dir / "workspace/replicate_metrics.csv",
    )
    runs_dir = e1_dir / "workspace/runs"
    execution_started = runs_dir.exists() and any(
        runs_dir.rglob("completion.json")
    )
    if any(path.exists() for path in forbidden) or execution_started:
        raise RuntimeError("refusing to change the Cycle 4 lock after E1 outcomes exist")


# ---------------------------------------------------------------------------
# Seeds mutual-exclusion ledger
# ---------------------------------------------------------------------------

# A job that consumes no stochastic seeds writes a sentinel into seeds.txt
# instead of a number. Sentinels are recorded for auditability but are never
# treated as seeds.
SEED_SENTINELS = frozenset({"none", "not-applicable-deterministic-tests"})

# Jobs that are allowed to share seeds, grouped by the reason they may.
#
# Membership in a component is the authorisation. The ``status`` field is purely
# descriptive and neither gates nor relaxes anything: ``intended`` marks a reuse
# chosen when the design was frozen, ``grandfathered`` marks a historical
# collision that is recorded but not rewritten.
#
# ``basis`` names the property the audit must *verify* before the component
# authorises anything, so a component cannot be justified by prose alone:
#
# * ``same_experiment_reexecution`` — every member must carry one identical
#   ``experiment_id``. The shared seeds then come from the same experiment being
#   re-executed in successive cycles, not from one experiment borrowing another's
#   random stream.
# * ``declared_paired_rerun`` — ``citation`` must name a tracked document that
#   exists and actually contains ``marker``. The reuse is a frozen design
#   decision, so the design that declares it must still be in the tree.
# * ``historical_collision`` — the component's shared seeds must be disjoint from
#   ``EVIDENCE_SEED_SETS``. This is the property that matters: these collisions
#   are tolerable *because* they cannot contaminate anything the precision bounds,
#   thresholds or confirmatory claims depend on.
#
# Every seed found anywhere in the repository must have all of its consumers
# inside one single component. A consumer outside every component is a leak: it
# means a job silently reused another job's random stream, which breaks the
# independence assumption behind the pooled precision estimates.
# Post-V1F experiments are deliberately absent from this table, so any overlap
# they introduce fails the audit until it is registered explicitly.
SEED_REUSE_COMPONENTS: tuple[dict[str, Any], ...] = (
    {
        "jobs": (
            "B0-DYNAMICS-PILOT",
            "B0-DYNAMICS-PILOT-C2",
            "B0-DYNAMICS-PILOT-C3",
        ),
        "status": "intended",
        "basis": "same_experiment_reexecution",
        "reason": (
            "three cycle-labelled records of one and the same experiment "
            "(experiment_id is identical in all three), so the shared seeds are a "
            "re-execution artifact rather than a borrowed random stream"
        ),
    },
    {
        "jobs": (
            "E0-NUMERICS",
            "E0-NUMERICS-C2",
            "E0-NUMERICS-C3",
            "E1-MATCHED-LANDSCAPES",
            "E2-CHANNEL-ABLATION",
        ),
        "status": "grandfathered",
        "basis": "historical_collision",
        "reason": (
            "Cycle 1-3 collisions that were never written down as a decision: the "
            "Cycle 3 E2 ablation re-used E1's seeds, and seed 1103 additionally "
            "collides with E0. No document declares any of this, which is exactly "
            "why it is recorded as a defect rather than as intent. It stays harmless "
            "only because every one of these seeds is disjoint from the evidence "
            "sets, which the audit now re-verifies on every run."
        ),
    },
    {
        "jobs": ("V1F-NONFLAT-CALIBRATION-C4", "V1G-ORDER-THERMAL-C4"),
        "status": "intended",
        "basis": "declared_paired_rerun",
        "citation": {
            "path": "research/v1g-order-thermal-design.md",
            "marker": "seeds | **V1F 冻结的 64 个**",
        },
        "reason": (
            "V1G re-runs V1F's exact 64 seeds at the same time points; the seed pairing "
            "is the estimand, since storage order must be the only difference"
        ),
    },
)

# Jobs whose numeric output the calibration bounds, the pre-registered thresholds
# or a confirmatory claim actually rest on. A historical collision is only
# tolerable while it stays clear of these: if a shared seed ever appeared here,
# the independence of the precision estimates would be in question and the
# collision would have to stop being called harmless.
EVIDENCE_BEARING_JOBS: tuple[str, ...] = (
    "V1-NONFLAT-CALIBRATION-C4",
    "V1B-NONFLAT-CALIBRATION-C4",
    "V1C-NONFLAT-CALIBRATION-C4",
    "V1E-NONFLAT-CALIBRATION-C4",
    "V1F-NONFLAT-CALIBRATION-C4",
    "V1G-ORDER-THERMAL-C4",
    "V1P-RUNTIME-PILOT-C4",
    "E1-MATCHED-LANDSCAPES-C4",
)

# Jobs whose ``seed-<n>`` run-identifier tokens name pre-existing source runs
# rather than seeds they drew themselves.
#
# A token such as ``seed-6101--smooth-dt-0.02`` appears in a reanalysis job's
# results as a *label* for which upstream run it read. Counting it as that job's
# own consumption would over-count the ledger and manufacture a seed overlap
# between two jobs that never shared a random stream.
#
# The default is deliberately the opposite: an undeclared run-identifier token is
# counted as consumption. That direction fails closed, because over-counting can
# only raise a spurious overlap (which forces someone to declare the truth),
# whereas under-counting would hide a real reuse silently. Each entry must name
# the ``source_experiment`` its config points at, so the claim is corroborated by
# the job's own declaration instead of being taken on trust.
SEED_REFERENCE_JOBS: dict[str, dict[str, str]] = {
    "V1D-STATIONARITY-DIAGNOSTIC-C4": {
        "source_experiment": "V1-NONFLAT-CALIBRATION-C4",
        "reason": (
            "V1D performs a deterministic reanalysis of V1's completed snapshots and "
            "draws no new random numbers; its run identifiers name the V1 source runs"
        ),
    },
}

_NUMERIC_SEED = re.compile(r"^\d+$")
_RUN_ID_SEED = re.compile(r"seed-(\d+)")


def _is_prime(value: int) -> bool:
    if value < 2:
        return False
    if value % 2 == 0:
        return value == 2
    divisor = 3
    while divisor * divisor <= value:
        if value % divisor == 0:
            return False
        divisor += 2
    return True


def _load_seed_json(path: Path) -> Any:
    """Load a job JSON file tolerantly; job payloads may be objects or arrays."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _seed_values(value: Any) -> list[int]:
    """Normalise a ``seeds``/``seed`` field into a list of integers."""
    if isinstance(value, list):
        return [
            item for item in value if isinstance(item, int) and not isinstance(item, bool)
        ]
    if isinstance(value, int) and not isinstance(value, bool):
        return [value]
    if isinstance(value, str) and _NUMERIC_SEED.match(value):
        return [int(value)]
    return []


def _collect_nested_seeds(node: Any) -> list[int]:
    """Seeds named inside a nested block, such as V1P's ``target_design.seeds``.

    A nested declaration describes a design the job *points at* rather than one
    it ran, so it is recorded as a reference and kept out of the
    mutual-exclusion set. Only the top level of a job file declares consumed
    seeds.
    """
    found: list[int] = []
    if isinstance(node, dict):
        for key, value in node.items():
            if key in ("seeds", "seed"):
                found.extend(_seed_values(value))
            else:
                found.extend(_collect_nested_seeds(value))
    elif isinstance(node, list):
        for item in node:
            found.extend(_collect_nested_seeds(item))
    return found


def _collect_run_id_seeds(node: Any) -> list[int]:
    """Seeds recoverable only from ``seed-<n>`` tokens inside run identifiers."""
    found: list[int] = []
    if isinstance(node, dict):
        for value in node.values():
            found.extend(_collect_run_id_seeds(value))
    elif isinstance(node, list):
        for item in node:
            found.extend(_collect_run_id_seeds(item))
    elif isinstance(node, str):
        found.extend(int(match.group(1)) for match in _RUN_ID_SEED.finditer(node))
    return found


def _harvest_job_seeds(job_dir: Path) -> dict[str, Any]:
    """Collect every seed a job consumed, from every channel it can appear on.

    Seeds reach the record through three independent channels, and a job may use
    only some of them:

    * ``seeds.txt``, the declared list that preflight checks;
    * a top-level ``seeds``/``seed`` field in a job JSON file;
    * ``seed-<n>`` tokens inside run identifiers in ``result.json`` or
      ``manifest.json``.

    ``seeds.txt`` and the top-level fields are declarations of what the job drew,
    so they are taken as consumption. A nested block such as V1P's
    ``target_design.seeds`` names a design the job points at, so it is recorded as
    a reference. Run-identifier tokens are counted as consumption *unless* the job
    is declared in ``SEED_REFERENCE_JOBS``, because a reanalysis job labels its
    inputs with the upstream runs it read.
    """
    sentinels: list[str] = []
    channels: dict[str, list[int]] = {}
    references: dict[str, list[int]] = {}
    counts: dict[str, int] = {}
    experiment_id: str | None = None

    seeds_file = job_dir / "seeds.txt"
    if seeds_file.is_file():
        tokens = [
            token
            for token in re.split(r"[\s,]+", seeds_file.read_text(encoding="utf-8").strip())
            if token
        ]
        from_file = [int(token) for token in tokens if _NUMERIC_SEED.match(token)]
        sentinels = [token for token in tokens if not _NUMERIC_SEED.match(token)]
        if from_file:
            channels["seeds.txt"] = from_file

    reference_declaration = SEED_REFERENCE_JOBS.get(job_dir.name)

    for path in sorted(job_dir.glob("*.json")):
        payload = _load_seed_json(path)
        if payload is None:
            continue
        if isinstance(payload, dict) and experiment_id is None:
            candidate = payload.get("experiment_id")
            if isinstance(candidate, str) and candidate:
                experiment_id = candidate

        consumed: list[int] = []
        referenced: list[int] = []
        if isinstance(payload, dict):
            for key in ("seeds", "seed"):
                value = payload.get(key)
                if isinstance(value, int) and not isinstance(value, bool):
                    # A *scalar* ``seeds`` is a count, not a list of seed values:
                    # E2-C4's isolation-identity report records "seeds": 16 for the
                    # sixteen replicates it compared.  Folding it into the consumed
                    # set invented a seed 16 that no run ever drew, which the ledger
                    # then reported as a disagreement between seeds.txt and the
                    # declarations -- a false alarm that hid the real check.
                    counts[f"{path.name}:{key}"] = value
                else:
                    consumed.extend(_seed_values(value))
            referenced.extend(
                _collect_nested_seeds(
                    {
                        key: value
                        for key, value in payload.items()
                        if key not in ("seeds", "seed")
                    }
                )
            )
        if consumed:
            channels[f"declared:{path.name}"] = consumed
        if referenced:
            references[f"{path.name}:nested"] = sorted(set(referenced))

        # Run identifiers are harvested as a set: one seed legitimately appears
        # once per replicate and once per condition.
        run_ids = sorted(set(_collect_run_id_seeds(payload)))
        if run_ids:
            if reference_declaration:
                references[f"{path.name}:run_ids"] = run_ids
            else:
                channels[f"runids:{path.name}"] = run_ids

    if reference_declaration:
        # Corroborate the declaration against the job's own config rather than
        # trusting the register: a reanalysis job must name its source.
        declared_sources = set()
        for path in sorted(job_dir.glob("*.json")):
            payload = _load_seed_json(path)
            if isinstance(payload, dict):
                source = payload.get("source_experiment")
                if isinstance(source, str):
                    declared_sources.add(source)
        expected = reference_declaration["source_experiment"]
        if expected not in declared_sources:
            raise RuntimeError(
                f"{job_dir.name} is registered as a reanalysis of {expected}, but its "
                f"config names {sorted(declared_sources) or 'no source_experiment'}"
            )

    return {
        "sentinels": sentinels,
        "experiment_id": experiment_id,
        "seeds": sorted({seed for group in channels.values() for seed in group}),
        "channels": {name: list(group) for name, group in channels.items()},
        "references": references,
        "seed_counts": counts,
        "reference_job": bool(reference_declaration),
        "has_seed_waiver": (job_dir / "seed_waiver.txt").is_file(),
        # A seed repeated inside one declaration list is a typo, because it
        # silently shrinks the realised seed count below the registered one.
        # Run-identifier channels are excluded: repeats there are expected.
        "duplicates": {
            name: sorted(seed for seed in set(group) if group.count(seed) > 1)
            for name, group in channels.items()
            if not name.startswith("runids:") and len(set(group)) != len(group)
        },
    }


def _verify_seed_reuse_components(
    jobs: Mapping[str, dict[str, Any]],
    consumers: Mapping[int, set[str]],
    repo_root: Path,
) -> list[str]:
    """Verify that every component's ``basis`` actually holds.

    A component authorises a seed overlap, so it must not rest on prose. Each
    basis is checked against data: the experiment identity, the cited document, or
    the disjointness that makes a historical collision harmless. Returns the
    evidence-bearing seed set so the caller can report it.
    """
    known = {
        "same_experiment_reexecution",
        "declared_paired_rerun",
        "historical_collision",
    }
    for entry in SEED_REUSE_COMPONENTS:
        basis = entry.get("basis")
        if basis not in known:
            raise RuntimeError(
                f"seed reuse component {entry['jobs']} has basis {basis!r}, "
                f"expected one of {sorted(known)}"
            )
        missing = [job for job in entry["jobs"] if job not in jobs]
        if missing:
            raise RuntimeError(
                f"seed reuse component {entry['jobs']} names jobs with no directory: {missing}"
            )

    evidence_jobs = [job for job in EVIDENCE_BEARING_JOBS if job in jobs]
    absent = [job for job in EVIDENCE_BEARING_JOBS if job not in jobs]
    if absent:
        # A typo here would silently shrink the evidence set and make the
        # disjointness check vacuous.
        raise RuntimeError(f"EVIDENCE_BEARING_JOBS names jobs with no directory: {absent}")
    evidence_seeds = {seed for job in evidence_jobs for seed in jobs[job]["seeds"]}

    for entry in SEED_REUSE_COMPONENTS:
        members = list(entry["jobs"])
        basis = entry["basis"]

        if basis == "same_experiment_reexecution":
            identities = {jobs[job]["experiment_id"] for job in members}
            if len(identities) != 1 or None in identities:
                raise RuntimeError(
                    f"component {tuple(members)} claims one experiment re-executed, but "
                    f"its experiment_ids are {sorted(str(i) for i in identities)}"
                )

        elif basis == "declared_paired_rerun":
            citation = entry.get("citation") or {}
            path, marker = citation.get("path"), citation.get("marker")
            if not isinstance(path, str) or not isinstance(marker, str) or not marker:
                raise RuntimeError(
                    f"component {tuple(members)} claims a declared pairing but has no "
                    f"citation path and marker"
                )
            document = repo_root / path
            if not document.is_file():
                raise RuntimeError(
                    f"component {tuple(members)} cites {path}, which is not in the tree"
                )
            if marker not in document.read_text(encoding="utf-8"):
                raise RuntimeError(
                    f"component {tuple(members)} cites {path}, but it no longer contains "
                    f"the declaration {marker!r}"
                )

        elif basis == "historical_collision":
            shared = {
                seed
                for seed, users in consumers.items()
                if len(users) >= 2 and users <= set(members)
            }
            contaminated = sorted(shared & evidence_seeds)
            if contaminated:
                raise RuntimeError(
                    f"component {tuple(members)} is registered as a harmless historical "
                    f"collision, but seeds {contaminated} also appear in evidence-bearing "
                    f"jobs; the collision can no longer be called harmless"
                )

    return sorted(evidence_seeds)


def audit_seeds(
    jobs_dir: Path,
    *,
    pool_min: int | None = None,
    pool_max: int | None = None,
    propose: int | None = None,
    exclude: Sequence[str] = (),
) -> dict[str, Any]:
    """Build the bookkeeping ledger of every seed consumed by every job.

    Raises RuntimeError when the ledger is internally inconsistent, meaning a
    job repeats a seed inside one channel, or declares its seeds two different
    ways, or shares a seed with another job without a registered reason.

    ``exclude`` names job directories to leave out. It exists for one case: a
    declaration set being generated *right now* must not be an input to its own
    seed choice. Without it, the act of writing the job dir would push its seeds
    into the exclusion set -- making the selection depend on whether it had been
    run before -- and would also make the dir fail the "records no seed
    evidence" check while it is still being assembled. The caller is responsible
    for the resulting declaration being exactly the choice it just made;
    ``prepare_e2`` re-checks that.
    """
    excluded = set(exclude)
    jobs = {
        job_dir.name: _harvest_job_seeds(job_dir)
        for job_dir in sorted(path for path in jobs_dir.iterdir() if path.is_dir())
        if job_dir.name not in excluded
    }

    # A seed drawn twice inside one declaration list is not a larger sample, it
    # is a typo, and it would silently shrink the realised seed count.
    for job, record in jobs.items():
        for channel, repeats in record["duplicates"].items():
            raise RuntimeError(f"{job} repeats seeds inside {channel}: {repeats}")

    # A non-numeric token in seeds.txt is either a registered sentinel or a typo;
    # an unrecognised token would otherwise be dropped silently.
    for job, record in jobs.items():
        unknown = [token for token in record["sentinels"] if token not in SEED_SENTINELS]
        if unknown:
            raise RuntimeError(
                f"{job} has non-numeric seeds.txt entries that are not registered "
                f"sentinels: {unknown}"
            )

    # A declared *count* of seeds must equal the declared battery: an artifact that
    # says it compared sixteen replicates while the job declares a different battery
    # is stale, and a stale artifact under a passing verdict is the thing this ledger
    # exists to refuse.
    for job, record in jobs.items():
        for channel, count in record["seed_counts"].items():
            declared_size = len(record["seeds"])
            if declared_size and count != declared_size:
                raise RuntimeError(
                    f"{job} declares {declared_size} seeds but {channel} says {count}; "
                    "one of the two is stale"
                )

    # seeds.txt and the structured declarations must agree; a disagreement means
    # one of the two is stale and the ledger cannot be trusted.
    for job, record in jobs.items():
        channels = record["channels"]
        from_file = set(channels.get("seeds.txt", []))
        declared = {
            seed
            for name, group in channels.items()
            if name.startswith("declared:")
            for seed in group
        }
        if from_file and declared and from_file != declared:
            raise RuntimeError(
                f"{job} declares seeds.txt {sorted(from_file)} but config/experiment "
                f"{sorted(declared)}; one of the two is stale"
            )

    # A job that records no seed provenance at all is invisible to this ledger,
    # so it must at least declare why it needed none. Without this, a job could
    # consume randomness, record nothing, and never appear in the mutual
    # exclusion set.
    for job, record in jobs.items():
        if not record["seeds"] and not record["references"] and not record["has_seed_waiver"]:
            raise RuntimeError(
                f"{job} records no seed evidence and holds no seed_waiver.txt; its seed "
                f"provenance is unverifiable"
            )

    consumers: dict[int, set[str]] = {}
    for job, record in jobs.items():
        for seed in record["seeds"]:
            consumers.setdefault(seed, set()).add(job)

    # Authorisation must be verified, not asserted: each component's basis is
    # checked against the data before it is allowed to explain any overlap.
    repo_root = jobs_dir.resolve().parents[1]
    evidence_seeds = _verify_seed_reuse_components(jobs, consumers, repo_root)

    # Membership in a component authorises the reuse; the entry's ``status`` is a
    # label for readers and never affects this test.
    components = [set(entry["jobs"]) for entry in SEED_REUSE_COMPONENTS]
    overlaps: list[dict[str, Any]] = []
    for seed, users in sorted(consumers.items()):
        if len(users) < 2:
            continue
        owner = next((index for index, c in enumerate(components) if users <= c), None)
        overlaps.append(
            {
                "seed": seed,
                "jobs": sorted(users),
                "reason": SEED_REUSE_COMPONENTS[owner]["reason"] if owner is not None else None,
                "status": (
                    SEED_REUSE_COMPONENTS[owner]["status"] if owner is not None else "leak"
                ),
                "basis": (
                    SEED_REUSE_COMPONENTS[owner]["basis"] if owner is not None else None
                ),
            }
        )

    leaks = [entry for entry in overlaps if entry["reason"] is None]
    if leaks:
        detail = "; ".join(
            f"seed {entry['seed']} shared by {entry['jobs']}" for entry in leaks
        )
        raise RuntimeError(f"unregistered seed reuse breaks run independence: {detail}")

    used = sorted(consumers)
    # Primality is a selection convention, not a requirement the simulator
    # enforces: ``random_seed`` only initialises ``mt19937_64`` streams, so the
    # one property that matters is that distinct jobs draw distinct streams.
    # Three frozen historical seeds are not prime (6407 and 6503 in V1, 9071 in
    # V1C); they are reported rather than rejected so the ledger stays usable as
    # evidence, and primality is only enforced when proposing new seeds.
    non_prime = [seed for seed in used if not _is_prime(seed)]

    report: dict[str, Any] = {
        "job_count": len(jobs),
        "used_seed_count": len(used),
        "used_seeds": used,
        "non_prime_seeds": non_prime,
        "evidence_bearing_jobs": list(EVIDENCE_BEARING_JOBS),
        "evidence_seed_count": len(evidence_seeds),
        "jobs": jobs,
        "overlaps": overlaps,
        "references": {
            job: record["references"]
            for job, record in sorted(jobs.items())
            if record["references"]
        },
        "jobs_without_seed_evidence": sorted(
            job
            for job, record in jobs.items()
            if not record["seeds"] and not record["references"]
        ),
        "grandfathered_overlaps": [
            entry for entry in overlaps if entry["status"] == "grandfathered"
        ],
    }

    if pool_min is None and pool_max is None:
        return report
    if pool_min is None or pool_max is None:
        raise RuntimeError("pool bounds must be given together")
    if pool_max <= pool_min:
        raise RuntimeError("pool_max must exceed pool_min")

    pool = [
        value
        for value in range(pool_min, pool_max + 1)
        if _is_prime(value) and value not in consumers
    ]
    report["pool"] = {
        "min": pool_min,
        "max": pool_max,
        "available_count": len(pool),
        "available_primes": pool,
    }
    if propose is not None:
        if propose < 1:
            raise RuntimeError("propose must request at least one seed")
        if len(pool) < propose:
            raise RuntimeError(
                f"pool [{pool_min}, {pool_max}] holds {len(pool)} unused primes, "
                f"cannot propose {propose}"
            )
        report["proposed_seeds"] = pool[:propose]
    return report


def _assert_e1_seeds_unused(root: Path) -> None:
    """Reject a lock whose E1 seeds are no longer unseen by any other job.

    Every channel is checked rather than just ``config.json``, because a job can
    consume a seed while declaring it only inside a run identifier.
    """
    e1_seed_set = set(E1_SEEDS)
    jobs_dir = root / "research/jobs"
    for job_dir in sorted(path for path in jobs_dir.iterdir() if path.is_dir()):
        if job_dir.name == E1_ID:
            continue
        overlap = e1_seed_set & set(_harvest_job_seeds(job_dir)["seeds"])
        if overlap:
            raise RuntimeError(
                f"E1 seeds are no longer unseen; overlap in {job_dir.name}: {sorted(overlap)}"
            )


def _require_real_commit(root: Path, source_commit: str) -> None:
    """Reject a source commit that is well-formed but does not exist.

    A fabricated or stale SHA would otherwise be written into the V0G
    declaration and the candidate lock, where it is descriptive only and
    therefore never fails loudly: V0G records its own live ``HEAD``, so the
    mismatch would surface only later as an inexplicable record. Fail here.

    The clean-working-tree requirement is deliberately *not* enforced here:
    ``prepare`` itself writes tracked declarations, so its own output makes the
    tree dirty and a second run would then refuse. That requirement belongs to
    V0G, which records ``working_tree_clean`` at run time, and to ``finalize``,
    which rejects a V0G result without it.
    """
    import subprocess

    probe = subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", f"{source_commit}^{{commit}}"],
        cwd=root,
        capture_output=True,
        text=True,
    )
    resolved = probe.stdout.strip()
    if probe.returncode != 0 or resolved != source_commit:
        raise ValueError(
            f"source_commit does not resolve to a commit in this repository: {source_commit}"
        )


def prepare(root: Path, calibration: Path, result: Path, v1f_config: Path, source_commit: str) -> None:
    if len(source_commit) != 40 or any(character not in "0123456789abcdef" for character in source_commit):
        raise ValueError("source_commit must be a full 40-character lowercase Git SHA")
    _require_real_commit(root, source_commit)
    for path in (calibration, result, v1f_config):
        _relative(root, path)
    _assert_no_e1_outcomes(root)
    _assert_e1_seeds_unused(root)
    v1f = validate_v1f(calibration, result, v1f_config)
    lock_path = root / "research/parameter_lock.cycle4.json"
    if lock_path.exists() and _read_json(lock_path).get("status") == "final":
        raise RuntimeError("refusing to replace the final Cycle 4 parameter lock")
    _write_json(lock_path, _candidate_lock(source_commit, v1f))

    v0g_dir = root / f"research/jobs/{V0G_ID}"
    v0g_dir.mkdir(parents=True, exist_ok=True)
    _write_json(
        v0g_dir / "config.json",
        {
            "experiment_id": V0G_ID,
            "source_commit": source_commit,
            "execution_host": "umi",
            "build_jobs": 4,
            "openmp_modes": [False, True],
            "mpi_enabled": False,
            "build_type": "Release",
            "run_pytest": True,
            "test_scope": "Final Cycle 4 lock/calibration/binary binding, matched E1-C4 runner, two-window gates, and all simulator invariants.",
        },
    )
    (v0g_dir / "commit.txt").write_text(source_commit + "\n", encoding="utf-8")
    (v0g_dir / "env.txt").write_text("host=umi\nexecution=python_pytest_and_cmake_ctest\nopenmp=OFF_and_ON\nmpi=OFF\nsimulation=none\n", encoding="utf-8")
    (v0g_dir / "seeds.txt").write_text("none\n", encoding="utf-8")
    (v0g_dir / "seed_waiver.txt").write_text("Implementation validation executes no numerical simulation.\n", encoding="utf-8")
    (v0g_dir / "outputs.txt").write_text("result.json\nenvironment.json\npytest.log\nctest-off.log\nctest-on.log\n", encoding="utf-8")
    (v0g_dir / "data_checksums.txt").write_text(f"source_tree=git_commit_{source_commit}\nexternal_data=none\n", encoding="utf-8")
    _write_json(v0g_dir / "computational_strategy.json", {
        "approach": "Run the full Python suite and rebuild/test the C++ reference with OpenMP OFF and ON on umi.",
        "evidence_role": "implementation validation",
        "evidence_boundary": "V0G validates code and bindings only and produces no scientific evidence.",
        "supports_core_claim": False,
    })

    lock = _read_json(lock_path)
    config = _e1_config(root, lock, binary_sha256=None)
    e1_dir = root / f"research/jobs/{E1_ID}"
    _write_json(e1_dir / "config.json", config)
    _write_support_files(root, source_commit, config)


def validate_v0g(result_path: Path) -> dict[str, Any]:
    result = _read_json(result_path)
    if result.get("experiment") != V0G_ID or result.get("pass") is not True:
        raise RuntimeError("V0G is missing or did not pass")
    if result.get("status") != "completed":
        raise RuntimeError("V0G did not complete")
    environment = result.get("environment")
    if not isinstance(environment, Mapping) or str(environment.get("host", "")).split(".", 1)[0] != "umi":
        raise RuntimeError("V0G was not executed on umi")
    if environment.get("working_tree_clean") is not True:
        raise RuntimeError("V0G did not validate a clean checkout")
    pytest_result = result.get("pytest")
    if not isinstance(pytest_result, Mapping) or pytest_result.get("returncode") != 0:
        raise RuntimeError("V0G Python suite did not pass")
    builds = result.get("builds")
    if not isinstance(builds, list) or len(builds) != 2:
        raise RuntimeError("V0G must contain OpenMP OFF and ON build results")
    modes = {item.get("openmp") for item in builds if isinstance(item, Mapping) and item.get("pass") is True}
    if modes != {False, True}:
        raise RuntimeError("V0G OpenMP OFF/ON CTest did not both pass")
    return result


def finalize(root: Path, v0g_result: Path, binary: Path) -> None:
    _relative(root, v0g_result)
    _relative(root, binary)
    _assert_no_e1_outcomes(root)
    result = validate_v0g(v0g_result)
    if not binary.is_file():
        raise FileNotFoundError(binary)
    lock_path = root / "research/parameter_lock.cycle4.json"
    lock = _read_json(lock_path)
    if lock.get("status") != "candidate" or lock.get("confirmatory_execution_authorized") is not False:
        raise RuntimeError("Cycle 4 lock is not an unexecuted candidate")
    validated_commit = result["environment"].get("source_commit")
    if (
        not isinstance(validated_commit, str)
        or len(validated_commit) != 40
        or any(character not in "0123456789abcdef" for character in validated_commit)
    ):
        raise RuntimeError("V0G did not record a full clean-checkout source commit")
    binary_sha256 = _sha256(binary)
    # The lock binds a SHA-256 of the simulator binary that E1-C4 will execute, so
    # the artifact must be the one the numerical calibration was measured on. Any
    # simulator source change after V1F silently produces a different binary; that
    # must fail loudly here rather than produce a lock whose calibration and
    # executable do not correspond.
    reference_binary_sha256 = (
        lock.get("numerical_calibration", {}).get("reference_binary_sha256")
        if isinstance(lock.get("numerical_calibration"), Mapping)
        else None
    )
    if (
        not isinstance(reference_binary_sha256, str)
        or len(reference_binary_sha256) != 64
    ):
        raise RuntimeError("candidate lock does not bind a calibrated reference binary")
    v0g_dir = (root / f"research/jobs/{V0G_ID}").resolve()
    resolved_binary = binary.resolve()
    if v0g_dir != resolved_binary and v0g_dir not in resolved_binary.parents:
        raise RuntimeError("finalize must bind a binary built inside the V0G workspace")
    if binary_sha256 != reference_binary_sha256:
        raise RuntimeError(
            "the binary bound for E1-C4 is not the calibrated reference binary: "
            f"calibrated {reference_binary_sha256}, rebuilt {binary_sha256}. "
            "The V1F numerical resolution limits were measured on the calibrated "
            "binary, so a simulator source change after calibration breaks the "
            "binding. Revert the simulator change (or recalibrate) before "
            "authorizing E1."
        )
    lock["status"] = "final"
    lock["confirmatory_execution_authorized"] = True
    lock["authorized_experiments"] = [E1_ID]
    lock["source_commit"] = validated_commit
    lock["analysis_commit"] = validated_commit
    lock["simulator_validation"] = {
        "experiment": V0G_ID,
        "result_sha256": _sha256(v0g_result),
        "validated_commit": validated_commit,
        "binary": _relative(root, binary),
        "binary_sha256": binary_sha256,
        "openmp_execution_mode": "OFF reference binary; OMP_NUM_THREADS=1",
    }
    _write_json(lock_path, lock)
    config = _e1_config(root, lock, binary_sha256=binary_sha256)
    e1_dir = root / f"research/jobs/{E1_ID}"
    _write_json(e1_dir / "config.json", config)
    _write_support_files(root, validated_commit, config)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    archive_parser = subparsers.add_parser("archive-v1f")
    archive_parser.add_argument(
        "--job-dir", default=f"research/jobs/{V1F_ID}"
    )
    archive_parser.add_argument(
        "--jobctl-dir", default=f".autoresearcher/jobs/{V1F_ID}"
    )
    archive_e1_parser = subparsers.add_parser("archive-e1")
    archive_e1_parser.add_argument("--job-dir", default=f"research/jobs/{E1_ID}")
    archive_e1_parser.add_argument(
        "--jobctl-dir", default=f".autoresearcher/jobs/{E1_ID}"
    )
    prepare_parser = subparsers.add_parser("prepare")
    prepare_parser.add_argument("--calibration", required=True)
    prepare_parser.add_argument("--result", required=True)
    prepare_parser.add_argument("--v1f-config", required=True)
    prepare_parser.add_argument("--source-commit", required=True)
    finalize_parser = subparsers.add_parser("finalize")
    finalize_parser.add_argument("--v0g-result", required=True)
    finalize_parser.add_argument("--binary", required=True)
    seeds_parser = subparsers.add_parser("seeds-audit")
    seeds_parser.add_argument("--jobs-dir", default="research/jobs")
    seeds_parser.add_argument("--pool-min", type=int, default=None)
    seeds_parser.add_argument("--pool-max", type=int, default=None)
    seeds_parser.add_argument("--propose", type=int, default=None)
    seeds_parser.add_argument("--out", default=None)
    record_parser = subparsers.add_parser("record-diagnostic")
    record_parser.add_argument("--job-dir", required=True)
    record_parser.add_argument("--jobctl-dir", required=True)
    record_parser.add_argument("--conclusion-artifact", required=True)
    record_parser.add_argument("--workspace-artifact", action="append", default=[])
    extension_parser = subparsers.add_parser("record-calibration-extension")
    extension_parser.add_argument("--job-dir", required=True)
    extension_parser.add_argument("--jobctl-dir", required=True)
    extension_parser.add_argument("--source-calibration", required=True)
    extension_parser.add_argument("--conclusion-artifact", required=True)
    extension_parser.add_argument("--workspace-artifact", action="append", default=[])
    pilot_parser = subparsers.add_parser("record-pilot")
    pilot_parser.add_argument("--job-dir", required=True)
    pilot_parser.add_argument("--jobctl-dir", required=True)
    pilot_parser.add_argument("--conclusion-artifact", default=None)
    pilot_parser.add_argument("--workspace-artifact", action="append", default=[])
    subparsers.add_parser("prepare-e2")
    subparsers.add_parser(
        "derive-claims",
        help=(
            "derive research/claims.json and research/findings.json from the run "
            "artifacts; refuses if a record does not corroborate the plan"
        ),
    )
    subparsers.add_parser(
        "migrate-manifest-paths",
        help=(
            "one-time repair of recorded manifests whose artifact paths the audit "
            "gate cannot resolve; writes research/manifest-path-migration.json"
        ),
    )
    record_e2_parser = subparsers.add_parser("record-e2")
    record_e2_parser.add_argument("--job-dir", default=f"research/jobs/{E2_ID}")
    record_e2_parser.add_argument("--jobctl-dir", default=f".autoresearcher/jobs/{E2_ID}")
    args = parser.parse_args(argv)
    if args.command == "archive-v1f":
        archive_v1f(
            PROJECT_ROOT,
            (PROJECT_ROOT / args.job_dir).resolve(),
            (PROJECT_ROOT / args.jobctl_dir).resolve(),
        )
    elif args.command == "archive-e1":
        archive_e1(
            PROJECT_ROOT,
            (PROJECT_ROOT / args.job_dir).resolve(),
            (PROJECT_ROOT / args.jobctl_dir).resolve(),
        )
    elif args.command == "prepare":
        prepare(
            PROJECT_ROOT,
            (PROJECT_ROOT / args.calibration).resolve(),
            (PROJECT_ROOT / args.result).resolve(),
            (PROJECT_ROOT / args.v1f_config).resolve(),
            args.source_commit,
        )
    elif args.command == "seeds-audit":
        report = audit_seeds(
            (PROJECT_ROOT / args.jobs_dir).resolve(),
            pool_min=args.pool_min,
            pool_max=args.pool_max,
            propose=args.propose,
        )
        print(
            f"{report['used_seed_count']} distinct seeds across {report['job_count']} jobs"
        )
        for job, record in sorted(report["jobs"].items()):
            if record["seeds"]:
                print(f"  {job}: {len(record['seeds'])} seeds")
            else:
                sentinel = ", ".join(record["sentinels"]) or "none declared"
                print(f"  {job}: no seeds ({sentinel})")
        print(f"cross-job overlap groups: {len(report['overlaps'])}")
        grouped: dict[tuple[str, ...], list[dict[str, Any]]] = {}
        for entry in report["overlaps"]:
            grouped.setdefault(tuple(entry["jobs"]), []).append(entry)
        for jobs_in_common, entries in sorted(grouped.items()):
            tag = entries[0]["status"]
            print(f"  [{tag}] {len(entries)} seeds shared by {', '.join(jobs_in_common)}")
        if report["non_prime_seeds"]:
            print(f"non-prime seeds (convention violation): {report['non_prime_seeds']}")
        for job, refs in report["references"].items():
            for name, seeds in refs.items():
                print(f"referenced (not consumed): {job} {name} = {seeds}")
        if report["jobs_without_seed_evidence"]:
            print(
                "jobs with no seed evidence (waiver held, nothing to exclude): "
                f"{report['jobs_without_seed_evidence']}"
            )
        if "pool" in report:
            pool = report["pool"]
            print(
                f"pool [{pool['min']}, {pool['max']}]: "
                f"{pool['available_count']} unused primes"
            )
        if "proposed_seeds" in report:
            print(f"proposed seeds: {report['proposed_seeds']}")
        if args.out:
            (PROJECT_ROOT / args.out).write_text(
                json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                encoding="utf-8",
            )
            print(f"wrote {args.out}")
    elif args.command == "record-diagnostic":
        print(
            json.dumps(
                record_diagnostic(
                    (PROJECT_ROOT / args.job_dir).resolve(),
                    (PROJECT_ROOT / args.jobctl_dir).resolve(),
                    conclusion_artifact=args.conclusion_artifact,
                    workspace_artifacts=args.workspace_artifact,
                ),
                ensure_ascii=False,
                indent=2,
            )
        )
    elif args.command == "record-calibration-extension":
        print(
            json.dumps(
                record_calibration_extension(
                    PROJECT_ROOT,
                    (PROJECT_ROOT / args.job_dir).resolve(),
                    (PROJECT_ROOT / args.jobctl_dir).resolve(),
                    source_calibration=(PROJECT_ROOT / args.source_calibration).resolve(),
                    conclusion_artifact=args.conclusion_artifact,
                    workspace_artifacts=args.workspace_artifact,
                ),
                ensure_ascii=False,
                indent=2,
            )
        )
    elif args.command == "derive-claims":
        print(json.dumps(derive_claims(PROJECT_ROOT), ensure_ascii=False, indent=2))
    elif args.command == "migrate-manifest-paths":
        report = migrate_manifest_paths(PROJECT_ROOT)
        report_path = PROJECT_ROOT / MIGRATION_REPORT_RELATIVE
        report["report"] = MIGRATION_REPORT_RELATIVE
        _write_json(report_path, report)
        print(json.dumps(report["totals"], ensure_ascii=False, indent=2))
    elif args.command == "record-e2":
        print(
            json.dumps(
                record_e2(
                    PROJECT_ROOT,
                    (PROJECT_ROOT / args.job_dir),
                    (PROJECT_ROOT / args.jobctl_dir),
                ),
                ensure_ascii=False,
                indent=2,
            )
        )
    elif args.command == "prepare-e2":
        print(json.dumps(prepare_e2(PROJECT_ROOT), ensure_ascii=False, indent=2))
    elif args.command == "record-pilot":
        print(
            json.dumps(
                record_pilot(
                    PROJECT_ROOT,
                    (PROJECT_ROOT / args.job_dir).resolve(),
                    (PROJECT_ROOT / args.jobctl_dir).resolve(),
                    conclusion_artifact=args.conclusion_artifact,
                    workspace_artifacts=args.workspace_artifact,
                ),
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        finalize(
            PROJECT_ROOT,
            (PROJECT_ROOT / args.v0g_result).resolve(),
            (PROJECT_ROOT / args.binary).resolve(),
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
