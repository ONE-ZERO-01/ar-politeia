#!/usr/bin/env python3
"""Deterministically promote a passing V1F calibration into V0G/E1-C4 jobs.

This module creates declarations only.  It never executes the simulator and is
safe to test locally.  ``prepare`` creates a non-authorizing candidate lock and
the V0G/E1 declarations.  ``finalize`` requires a passing V0G result and its
rebuilt OpenMP-OFF binary before it makes the lock final and E1 executable.
``archive-v1f`` and ``archive-e1`` cross-check a finished run against its own
declarations and compact it into tracked evidence; neither recomputes an effect
or has any authority to relax a gate.  ``seeds-audit`` builds the bookkeeping
ledger of every seed any job has consumed and refuses to let a new experiment
reuse one silently.
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
from typing import Any, Mapping, Sequence


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
    _write_json(job_dir / "result.json", result)

    manifest = {
        "exit_code": int(jobctl_result["exit_code"]),
        "timed_out": False,
        "wall_seconds": float(jobctl_result.get("wall_seconds", 0.0)),
        "jobctl_reconcile": "completed",
        "artifacts": [
            {
                "path": f"workspace/{name}",
                "sha256": _sha256(path),
                "valid": True,
            }
            for name, path in declared.items()
        ],
    }
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
    _write_json(job_dir / "result.json", result)

    manifest = {
        "exit_code": int(jobctl_result["exit_code"]),
        "timed_out": False,
        "wall_seconds": float(jobctl_result.get("wall_seconds", 0.0)),
        "jobctl_reconcile": "completed",
        "artifacts": [
            {
                "path": f"workspace/{name}",
                "sha256": _sha256(path),
                "valid": True,
            }
            for name, path in declared.items()
        ],
    }
    _write_json(job_dir / "manifest.json", manifest)

    return {
        "experiment": result["experiment"],
        "pass": result["pass"],
        "promoted": conclusion_artifact,
        "extends": source_relative,
        "extension_metrics": result["extension_metrics"],
        "conclusion_artifact_sha256": result["conclusion_artifact_sha256"],
    }


def _relative(root: Path, path: Path) -> str:
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
    manifest = {
        "exit_code": 0,
        "timed_out": False,
        "wall_seconds": jobctl_result.get("wall_seconds"),
        "jobctl_reconcile": "completed",
        "artifacts": [
            {
                "path": f"workspace/{name}",
                "sha256": artifact_hashes[name],
                "valid": True,
            }
            for name in V1F_WORKSPACE_ARTIFACTS
        ],
    }
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

    manifest = {
        "exit_code": 0,
        "timed_out": False,
        "wall_seconds": jobctl_result.get("wall_seconds"),
        "jobctl_reconcile": "completed",
        "archived_after_run": True,
        "artifacts": [
            {
                "path": f"workspace/{name}",
                "sha256": artifact_hashes[name],
                "valid": True,
            }
            for name in E1_WORKSPACE_ARTIFACTS
        ],
        "undeclared_provenance_sha256": {
            name: artifact_hashes[name] for name in E1_UNDECLARED_PROVENANCE
        },
    }
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
            consumed.extend(_seed_values(payload.get("seeds")))
            consumed.extend(_seed_values(payload.get("seed")))
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
) -> dict[str, Any]:
    """Build the bookkeeping ledger of every seed consumed by every job.

    Raises RuntimeError when the ledger is internally inconsistent, meaning a
    job repeats a seed inside one channel, or declares its seeds two different
    ways, or shares a seed with another job without a registered reason.
    """
    jobs = {
        job_dir.name: _harvest_job_seeds(job_dir)
        for job_dir in sorted(path for path in jobs_dir.iterdir() if path.is_dir())
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
    else:
        finalize(
            PROJECT_ROOT,
            (PROJECT_ROOT / args.v0g_result).resolve(),
            (PROJECT_ROOT / args.binary).resolve(),
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
