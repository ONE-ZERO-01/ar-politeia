#!/usr/bin/env python3
"""Prepare, execute and summarize AR-Politeia Cycle 1 experiments on umi.

The host guard is intentional: project rules prohibit numerical preparation,
smoke tests and execution on local machines.  Pure input/metric functions live
in ``landscape_study.py`` and have deterministic unit tests.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import socket
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Sequence

import numpy as np

from landscape_study import (
    annotate_confirmatory_effect,
    audit_matched_landscapes,
    audit_parameter_lock,
    canonical_payload_sha256,
    completion_marker_is_reusable,
    holm_adjust,
    make_matched_landscapes,
    paired_bootstrap_mean_difference,
    paired_discretization_sesoi,
    read_snapshot_csv,
    sha256_file,
    snapshot_metrics,
    stationarity_diagnostics,
    write_esri_ascii,
    write_initial_conditions,
    write_json,
)


PROJECT_ROOT = Path(__file__).resolve().parents[3]


def require_umi() -> None:
    hostname = socket.gethostname().split(".", 1)[0]
    if hostname != "umi":
        raise RuntimeError(
            f"numerical experiment workflow is server-only: expected host 'umi', got {hostname!r}"
        )


def project_path(value: str | Path, *, must_exist: bool = False) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    path = path.resolve()
    if path != PROJECT_ROOT and PROJECT_ROOT not in path.parents:
        raise ValueError(f"path escapes AR_PROJECT_ROOT: {value}")
    if must_exist and not path.exists():
        raise FileNotFoundError(path)
    return path


def relative_to_project(path: Path) -> str:
    return path.resolve().relative_to(PROJECT_ROOT).as_posix()


def load_json(path: Path) -> Dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"configuration must be an object: {path}")
    return payload


def validate_parameter_lock(
    experiment: str,
    config: Mapping[str, Any],
    output_dir: Path,
    *,
    require_final: bool,
) -> Dict[str, Any] | None:
    if experiment == "E0-NUMERICS":
        return None
    relative = config.get("parameter_lock")
    declared_sha256 = config.get("parameter_lock_sha256")
    if not isinstance(relative, str) or not relative:
        raise ValueError(f"{experiment} requires parameter_lock")
    if not isinstance(declared_sha256, str) or len(declared_sha256) != 64:
        raise ValueError(f"{experiment} requires a SHA-256 parameter_lock_sha256")
    lock_path = project_path(relative, must_exist=True)
    actual_sha256 = sha256_file(lock_path)
    if actual_sha256 != declared_sha256:
        raise RuntimeError(
            f"parameter lock checksum mismatch: expected {declared_sha256}, "
            f"got {actual_sha256}"
        )
    lock = load_json(lock_path)
    lock_status = lock.get("status")
    if require_final and lock_status != "final":
        raise RuntimeError(
            f"{experiment} execution requires a final parameter lock; "
            f"current status is {lock_status!r}"
        )
    authorized = lock.get("authorized_experiments")
    if not isinstance(authorized, list) or experiment not in authorized:
        raise RuntimeError(f"parameter lock does not authorize {experiment}")
    audit = audit_parameter_lock(config, lock)
    audit.update(
        {
            "experiment": experiment,
            "parameter_lock": relative,
            "parameter_lock_sha256": actual_sha256,
            "parameter_lock_status": lock_status,
        }
    )
    write_json(output_dir / "parameter_lock_audit.json", audit)
    if not audit["pass"]:
        raise RuntimeError(
            f"configured parameters do not match lock: "
            f"missing={audit['missing_parameters']}, "
            f"mismatches={sorted(audit['mismatches'])}"
        )
    return audit


def default_conditions(experiment: str, config: Mapping[str, Any]) -> List[Dict[str, Any]]:
    exchange_rate = float(config.get("exchange_rate", 0.003))
    dt = float(config.get("dt", 0.01))
    if experiment == "E0-NUMERICS":
        return [
            {
                "name": "equal-no-exchange",
                "landscape": "flat",
                "terrain_force_enabled": False,
                "terrain_production_enabled": False,
                "exchange_rate": 0.0,
                "wealth_log_sigma": 0.0,
                "dt": dt,
            },
            {
                "name": "equal-exchange",
                "landscape": "flat",
                "terrain_force_enabled": False,
                "terrain_production_enabled": False,
                "exchange_rate": exchange_rate,
                "wealth_log_sigma": 0.0,
                "dt": dt,
            },
            *[
                {
                    "name": f"perturbed-dt-{factor:g}",
                    "landscape": "flat",
                    "terrain_force_enabled": False,
                    "terrain_production_enabled": False,
                    "exchange_rate": exchange_rate,
                    "wealth_log_sigma": 0.01,
                    "dt": dt * factor,
                }
                for factor in (1.0, 0.5, 0.25)
            ],
        ]
    if experiment == "E1-MATCHED-LANDSCAPES":
        return [
            {
                "name": landscape,
                "landscape": landscape,
                "terrain_force_enabled": True,
                "terrain_production_enabled": True,
                "exchange_rate": exchange_rate,
                "wealth_log_sigma": 0.01,
                "dt": dt,
            }
            for landscape in ("clustered", "shuffled", "flat")
        ] + [
            {
                "name": "clustered-no-exchange",
                "landscape": "clustered",
                "terrain_force_enabled": True,
                "terrain_production_enabled": True,
                "exchange_rate": 0.0,
                "wealth_log_sigma": 0.01,
                "dt": dt,
            }
        ]
    if experiment == "E2-CHANNEL-ABLATION":
        return [
            {
                "name": f"{landscape}-f{int(force)}-p{int(production)}",
                "landscape": landscape,
                "terrain_force_enabled": force,
                "terrain_production_enabled": production,
                "exchange_rate": exchange_rate,
                "wealth_log_sigma": 0.01,
                "dt": dt,
            }
            for landscape in ("clustered", "shuffled")
            for force in (False, True)
            for production in (False, True)
        ]
    conditions = config.get("conditions")
    if not isinstance(conditions, list) or not conditions:
        raise ValueError(f"{experiment} requires a non-empty conditions list")
    return [dict(condition) for condition in conditions]


def write_cpp_config(path: Path, values: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines: List[str] = []
    for key, value in values.items():
        if isinstance(value, bool):
            rendered = "true" if value else "false"
        else:
            rendered = str(value)
        lines.append(f"{key} = {rendered}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def common_cpp_config(config: Mapping[str, Any]) -> Dict[str, Any]:
    bounds = [float(value) for value in config.get("bounds", [0.0, 100.0, 0.0, 100.0])]
    if len(bounds) != 4:
        raise ValueError("bounds must have four values")
    return {
        "domain_xmin": bounds[0],
        "domain_xmax": bounds[1],
        "domain_ymin": bounds[2],
        "domain_ymax": bounds[3],
        "total_steps": int(config.get("total_steps", 5000)),
        "output_interval": int(config.get("output_interval", 500)),
        "compact_interval": int(config.get("compact_interval", 500)),
        "temperature": float(config.get("temperature", 0.5)),
        "friction": float(config.get("friction", 1.0)),
        "social_strength": float(config.get("social_strength", 0.0)),
        "social_distance": float(config.get("social_distance", 1.0)),
        "interaction_range": float(config.get("interaction_range", 2.5)),
        "consumption_rate": float(config.get("consumption_rate", 0.0)),
        "wealth_decay_rate": float(config.get("wealth_decay_rate", 0.0)),
        "base_production": float(config.get("base_production", 0.01)),
        "ability_saturation_w": float(config.get("ability_saturation_w", 5.0)),
        "terrain_type": "grid",
        "terrain_format": "ascii",
        "terrain_force_scale": float(config.get("terrain_force_scale", 1.0)),
        "terrain_production_scale": float(config.get("terrain_production_scale", 1.0)),
        "terrain_barrier_enabled": False,
        "culture_enabled": False,
        "technology_enabled": False,
        "loyalty_enabled": False,
        "conquest_enabled": False,
        "plague_enabled": False,
        "carrying_capacity_enabled": False,
        "reproduction_enabled": False,
        "mortality_enabled": False,
        "climate_enabled": False,
        "river_enabled": False,
        "snapshot_binary": False,
        "checkpoint_interval": 0,
    }


def prepare_e3_inputs(
    config: Mapping[str, Any], output_dir: Path
) -> List[Dict[str, Any]]:
    populations = [int(value) for value in config.get("populations", [])]
    raw_shapes = config.get("grid_shapes", [])
    families = [str(value) for value in config.get("landscape_families", [])]
    seeds = [int(seed) for seed in config.get("seeds", [])]
    if not populations or min(populations) < 1:
        raise ValueError("E3 requires positive populations")
    if not isinstance(raw_shapes, list) or not raw_shapes:
        raise ValueError("E3 requires grid_shapes")
    shapes: List[tuple[int, int]] = []
    for value in raw_shapes:
        if not isinstance(value, list) or len(value) != 2:
            raise ValueError("each E3 grid shape must be [rows, cols]")
        shape = (int(value[0]), int(value[1]))
        if min(shape) < 2:
            raise ValueError("E3 grid dimensions must be at least two")
        shapes.append(shape)
    required_families = {"gaussian_mixture", "correlated_random_field"}
    if set(families) != required_families:
        raise ValueError(
            f"E3 landscape_families must be {sorted(required_families)}"
        )
    if not seeds:
        raise ValueError("E3 requires at least one seed")

    bounds_values = config.get("bounds", [0.0, 100.0, 0.0, 100.0])
    bounds = tuple(float(value) for value in bounds_values)
    if len(bounds) != 4:
        raise ValueError("bounds must have four values")
    inputs_dir = output_dir / "inputs"
    runs_dir = output_dir / "runs"
    inputs_dir.mkdir(parents=True, exist_ok=True)
    runs_dir.mkdir(parents=True, exist_ok=True)
    dt = float(config.get("dt", 0.01))
    exchange_rate = float(config.get("exchange_rate", 0.003))
    run_specs: List[Dict[str, Any]] = []
    matching_audits: List[Dict[str, Any]] = []
    input_checksums: List[Dict[str, Any]] = []

    for rows, cols in shapes:
        cellsize_x = (bounds[1] - bounds[0]) / cols
        cellsize_y = (bounds[3] - bounds[2]) / rows
        if not math.isclose(cellsize_x, cellsize_y, rel_tol=1e-12, abs_tol=1e-12):
            raise ValueError("ESRI ASCII E3 grids require equal x/y cell sizes")
        for family in families:
            for seed in seeds:
                design_dir = (
                    inputs_dir / f"grid-{rows}x{cols}" / family / f"seed-{seed}"
                )
                fields = make_matched_landscapes(
                    (rows, cols), seed, family=family
                )
                audit = audit_matched_landscapes(
                    fields["clustered"], fields["shuffled"]
                )
                audit.update(
                    {
                        "seed": seed,
                        "landscape_family": family,
                        "grid_shape": [rows, cols],
                    }
                )
                matching_audits.append(audit)
                if not audit["pass"]:
                    raise RuntimeError(
                        f"E3 matched input audit failed for {family}, "
                        f"grid={rows}x{cols}, seed={seed}"
                    )

                landscape_paths: Dict[str, Path] = {}
                resource_paths: Dict[str, Path] = {}
                terrain_sha256: Dict[str, str] = {}
                resource_sha256: Dict[str, str] = {}
                for landscape in ("clustered", "shuffled"):
                    field = fields[landscape]
                    grid_path = design_dir / f"{landscape}.asc"
                    terrain_sha256[landscape] = write_esri_ascii(
                        grid_path,
                        field,
                        xllcorner=bounds[0],
                        yllcorner=bounds[2],
                        cellsize=cellsize_x,
                    )
                    resource_path = design_dir / f"{landscape}-resource.npy"
                    np.save(resource_path, field, allow_pickle=False)
                    resource_sha256[landscape] = sha256_file(resource_path)
                    landscape_paths[landscape] = grid_path
                    resource_paths[landscape] = resource_path

                for population in populations:
                    ic_path = (
                        inputs_dir
                        / "initial-conditions"
                        / f"population-{population}"
                        / f"seed-{seed}.csv"
                    )
                    if not ic_path.exists():
                        initial_sha256 = write_initial_conditions(
                            ic_path,
                            population,
                            seed,
                            bounds=bounds,
                            mean_wealth=float(config.get("mean_wealth", 5.0)),
                            wealth_log_sigma=0.01,
                        )
                    else:
                        initial_sha256 = sha256_file(ic_path)
                    for landscape in ("clustered", "shuffled"):
                        run_id = (
                            f"population-{population}--grid-{rows}x{cols}--"
                            f"{family}--seed-{seed}--{landscape}"
                        )
                        run_dir = runs_dir / run_id
                        run_dir.mkdir(parents=True, exist_ok=True)
                        cpp_values = common_cpp_config(config)
                        if "total_time" in config:
                            cpp_values["total_steps"] = int(
                                round(float(config["total_time"]) / dt)
                            )
                        if "output_time_interval" in config:
                            cpp_values["output_interval"] = int(
                                round(float(config["output_time_interval"]) / dt)
                            )
                        cpp_values.update(
                            {
                                "dt": dt,
                                "random_seed": seed,
                                "initial_particles": population,
                                "initial_conditions_file": relative_to_project(ic_path),
                                "terrain_file": relative_to_project(
                                    landscape_paths[landscape]
                                ),
                                "terrain_force_enabled": True,
                                "terrain_production_enabled": True,
                                "exchange_rate": exchange_rate,
                                "output_dir": relative_to_project(run_dir),
                            }
                        )
                        cpp_config_path = run_dir / "politeia.cfg"
                        write_cpp_config(cpp_config_path, cpp_values)
                        run_specs.append(
                            {
                                "run_id": run_id,
                                "seed": seed,
                                "condition": landscape,
                                "landscape": landscape,
                                "landscape_family": family,
                                "population": population,
                                "grid_rows": rows,
                                "grid_cols": cols,
                                "terrain_force_enabled": True,
                                "terrain_production_enabled": True,
                                "exchange_rate": exchange_rate,
                                "dt": dt,
                                "cpp_config": relative_to_project(cpp_config_path),
                                "run_dir": relative_to_project(run_dir),
                                "resource_npy": relative_to_project(
                                    resource_paths[landscape]
                                ),
                                "initial_conditions": relative_to_project(ic_path),
                                "terrain_sha256": terrain_sha256[landscape],
                                "resource_sha256": resource_sha256[landscape],
                                "initial_conditions_sha256": initial_sha256,
                            }
                        )
                input_checksums.append(
                    {
                        "seed": seed,
                        "landscape_family": family,
                        "grid_shape": [rows, cols],
                        "terrain": terrain_sha256,
                        "resource_arrays": resource_sha256,
                    }
                )

    write_json(
        output_dir / "matched_input_audit.json",
        {
            "experiment": "E3-ROBUSTNESS-HOLDOUT",
            "pass": all(item["pass"] for item in matching_audits),
            "audits": matching_audits,
            "generated_input_sha256": input_checksums,
        },
    )
    write_json(output_dir / "run_specs.json", {"runs": run_specs})
    return run_specs


def prepare_inputs(
    experiment: str, config: Mapping[str, Any], output_dir: Path
) -> List[Dict[str, Any]]:
    if experiment == "E3-ROBUSTNESS-HOLDOUT":
        return prepare_e3_inputs(config, output_dir)
    shape_values = config.get("grid_shape", [128, 128])
    if not isinstance(shape_values, list) or len(shape_values) != 2:
        raise ValueError("grid_shape must be [rows, cols]")
    shape = (int(shape_values[0]), int(shape_values[1]))
    bounds_values = config.get("bounds", [0.0, 100.0, 0.0, 100.0])
    bounds = tuple(float(value) for value in bounds_values)
    if len(bounds) != 4:
        raise ValueError("bounds must have four values")
    population = int(config.get("population", 2000))
    seeds = [int(seed) for seed in config.get("seeds", [])]
    if len(seeds) < 1:
        raise ValueError("at least one seed is required")
    conditions = default_conditions(experiment, config)
    inputs_dir = output_dir / "inputs"
    runs_dir = output_dir / "runs"
    inputs_dir.mkdir(parents=True, exist_ok=True)
    runs_dir.mkdir(parents=True, exist_ok=True)

    run_specs: List[Dict[str, Any]] = []
    matching_audits: List[Dict[str, Any]] = []
    input_checksums: List[Dict[str, Any]] = []
    for seed in seeds:
        seed_dir = inputs_dir / f"seed-{seed}"
        fields = make_matched_landscapes(shape, seed)
        audit = audit_matched_landscapes(fields["clustered"], fields["shuffled"])
        audit["seed"] = seed
        matching_audits.append(audit)
        if not audit["pass"]:
            raise RuntimeError(f"matched input audit failed for seed {seed}")

        landscape_paths: Dict[str, Path] = {}
        resource_paths: Dict[str, Path] = {}
        landscape_checksums: Dict[str, str] = {}
        resource_checksums: Dict[str, str] = {}
        cellsize = (bounds[1] - bounds[0]) / shape[1]
        for name, field in fields.items():
            grid_path = seed_dir / f"{name}.asc"
            landscape_checksums[name] = write_esri_ascii(
                grid_path,
                field,
                xllcorner=bounds[0],
                yllcorner=bounds[2],
                cellsize=cellsize,
            )
            resource_path = seed_dir / f"{name}-resource.npy"
            np.save(resource_path, field, allow_pickle=False)
            resource_checksums[name] = sha256_file(resource_path)
            landscape_paths[name] = grid_path
            resource_paths[name] = resource_path

        for condition in conditions:
            condition_name = str(condition["name"])
            landscape_name = str(condition["landscape"])
            if landscape_name not in landscape_paths:
                raise ValueError(f"unknown landscape {landscape_name!r}")
            run_id = f"seed-{seed}--{condition_name}"
            run_dir = runs_dir / run_id
            run_dir.mkdir(parents=True, exist_ok=True)
            ic_path = seed_dir / (
                f"initial-sigma-{float(condition.get('wealth_log_sigma', 0.01)):.6g}.csv"
            )
            if not ic_path.exists():
                initial_checksum = write_initial_conditions(
                    ic_path,
                    population,
                    seed,
                    bounds=bounds,
                    mean_wealth=float(config.get("mean_wealth", 5.0)),
                    wealth_log_sigma=float(condition.get("wealth_log_sigma", 0.01)),
                )
            else:
                initial_checksum = sha256_file(ic_path)

            cpp_values = common_cpp_config(config)
            dt = float(condition.get("dt", config.get("dt", 0.01)))
            if "total_time" in config:
                total_steps = int(round(float(config["total_time"]) / dt))
                if total_steps < 1:
                    raise ValueError("total_time/dt must yield at least one step")
                cpp_values["total_steps"] = total_steps
            if "output_time_interval" in config:
                output_interval = int(round(float(config["output_time_interval"]) / dt))
                if output_interval < 1:
                    raise ValueError("output_time_interval/dt must yield at least one step")
                cpp_values["output_interval"] = output_interval
            cpp_values.update(
                {
                    "dt": dt,
                    "random_seed": seed,
                    "initial_particles": population,
                    "initial_conditions_file": relative_to_project(ic_path),
                    "terrain_file": relative_to_project(landscape_paths[landscape_name]),
                    "terrain_force_enabled": bool(condition["terrain_force_enabled"]),
                    "terrain_production_enabled": bool(
                        condition["terrain_production_enabled"]
                    ),
                    "exchange_rate": float(condition["exchange_rate"]),
                    "output_dir": relative_to_project(run_dir),
                }
            )
            cpp_config_path = run_dir / "politeia.cfg"
            write_cpp_config(cpp_config_path, cpp_values)
            run_specs.append(
                {
                    "run_id": run_id,
                    "seed": seed,
                    "condition": condition_name,
                    "landscape": landscape_name,
                    "terrain_force_enabled": bool(condition["terrain_force_enabled"]),
                    "terrain_production_enabled": bool(
                        condition["terrain_production_enabled"]
                    ),
                    "exchange_rate": float(condition["exchange_rate"]),
                    "dt": float(condition.get("dt", config.get("dt", 0.01))),
                    "cpp_config": relative_to_project(cpp_config_path),
                    "run_dir": relative_to_project(run_dir),
                    "resource_npy": relative_to_project(resource_paths[landscape_name]),
                    "initial_conditions": relative_to_project(ic_path),
                    "terrain_sha256": landscape_checksums[landscape_name],
                    "resource_sha256": resource_checksums[landscape_name],
                    "initial_conditions_sha256": initial_checksum,
                }
            )

        input_checksums.append(
            {
                "seed": seed,
                "terrain": landscape_checksums,
                "resource_arrays": resource_checksums,
            }
        )

    audit_payload = {
        "experiment": experiment,
        "pass": all(item["pass"] for item in matching_audits),
        "audits": matching_audits,
        "generated_input_sha256": input_checksums,
    }
    write_json(output_dir / "matched_input_audit.json", audit_payload)
    write_json(output_dir / "run_specs.json", {"runs": run_specs})
    return run_specs


def execute_runs(
    run_specs: Sequence[Mapping[str, Any]],
    binary: Path,
    *,
    timeout_seconds: int,
    omp_threads: int,
) -> Dict[str, Any]:
    if not binary.is_file() or not os.access(binary, os.X_OK):
        raise FileNotFoundError(f"Politeia binary is missing or not executable: {binary}")
    binary_sha256 = sha256_file(binary)
    summary: Dict[str, Any] = {
        "executed": 0,
        "skipped_completed": 0,
        "binary_sha256": binary_sha256,
        "completed_run_ids": [],
    }
    for spec in run_specs:
        run_dir = project_path(spec["run_dir"])
        log_path = run_dir / "run.log"
        config_path = project_path(spec["cpp_config"], must_exist=True)
        marker_path = run_dir / "completion.json"
        fingerprint = canonical_payload_sha256(
            {
                "run_spec": dict(spec),
                "cpp_config_sha256": sha256_file(config_path),
                "binary_sha256": binary_sha256,
                "omp_threads": omp_threads,
            }
        )
        if marker_path.is_file():
            try:
                marker = load_json(marker_path)
            except Exception:
                marker = {}
            if completion_marker_is_reusable(
                marker,
                run_dir=run_dir,
                expected_fingerprint=fingerprint,
            ):
                summary["skipped_completed"] += 1
                summary["completed_run_ids"].append(str(spec["run_id"]))
                continue

        for stale_path in list(run_dir.glob("*.csv")) + list(
            run_dir.glob("snap_*.bin")
        ):
            stale_path.unlink()
        environment = os.environ.copy()
        environment["OMP_NUM_THREADS"] = str(omp_threads)
        try:
            with log_path.open("w", encoding="utf-8") as log:
                completed = subprocess.run(
                    [str(binary), str(config_path)],
                    cwd=PROJECT_ROOT,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    timeout=timeout_seconds,
                    check=False,
                    text=True,
                    env=environment,
                )
        except subprocess.TimeoutExpired as exc:
            write_json(
                marker_path,
                {
                    "status": "failed",
                    "run_id": spec["run_id"],
                    "run_fingerprint": fingerprint,
                    "failure": "timeout",
                    "timeout_seconds": timeout_seconds,
                },
            )
            raise RuntimeError(
                f"run {spec['run_id']} exceeded {timeout_seconds} seconds"
            ) from exc
        if completed.returncode != 0:
            write_json(
                marker_path,
                {
                    "status": "failed",
                    "run_id": spec["run_id"],
                    "run_fingerprint": fingerprint,
                    "failure": "nonzero_exit",
                    "returncode": completed.returncode,
                },
            )
            raise RuntimeError(
                f"run {spec['run_id']} failed with exit code {completed.returncode}; see {log_path}"
            )
        snapshots = sorted(run_dir.glob("snap_*.csv"))
        if not snapshots:
            write_json(
                marker_path,
                {
                    "status": "failed",
                    "run_id": spec["run_id"],
                    "run_fingerprint": fingerprint,
                    "failure": "missing_snapshots",
                },
            )
            raise RuntimeError(f"run {spec['run_id']} produced no CSV snapshots")
        final_snapshot = snapshots[-1]
        write_json(
            marker_path,
            {
                "status": "completed",
                "run_id": spec["run_id"],
                "run_fingerprint": fingerprint,
                "binary_sha256": binary_sha256,
                "omp_threads": omp_threads,
                "snapshot_count": len(snapshots),
                "final_snapshot": final_snapshot.name,
                "final_snapshot_sha256": sha256_file(final_snapshot),
            },
        )
        summary["executed"] += 1
        summary["completed_run_ids"].append(str(spec["run_id"]))
    return summary


def mean_metrics_for_run(
    spec: Mapping[str, Any],
    *,
    bounds: Sequence[float],
    steady_snapshots: int,
    stationarity_max_drift: float,
    stationarity_min_ess: float,
) -> Dict[str, Any]:
    run_dir = project_path(spec["run_dir"], must_exist=True)
    snapshots = sorted(run_dir.glob("snap_*.csv"))
    if len(snapshots) < steady_snapshots:
        raise RuntimeError(
            f"{spec['run_id']} has {len(snapshots)} snapshots, needs {steady_snapshots}"
        )
    selected = snapshots[-steady_snapshots:]
    resource = np.load(project_path(spec["resource_npy"], must_exist=True), allow_pickle=False)
    rows = [
        snapshot_metrics(
            read_snapshot_csv(snapshot),
            resource,
            tuple(float(value) for value in bounds),
        )
        for snapshot in selected
    ]
    metric_names = rows[0].keys()
    means = {name: float(np.mean([row[name] for row in rows])) for name in metric_names}
    means["minimum_wealth"] = min(float(row["minimum_wealth"]) for row in rows)
    stationary_metrics = (
        "resource_density_spearman_rho",
        "density_morans_i",
        "occupancy_entropy",
        "wealth_gini",
        "wealth_variance",
    )
    diagnostics = {
        metric: stationarity_diagnostics(
            [row[metric] for row in rows],
            max_normalized_drift=stationarity_max_drift,
            min_effective_samples=stationarity_min_ess,
        )
        for metric in stationary_metrics
    }
    means["stationarity_pass"] = all(item["pass"] for item in diagnostics.values())
    for metric, diagnostic in diagnostics.items():
        means[f"{metric}__normalized_drift"] = float(
            diagnostic["normalized_window_drift"]
        )
        means[f"{metric}__iat"] = float(
            diagnostic["integrated_autocorrelation_time"]
        )
        means[f"{metric}__ess"] = float(diagnostic["effective_samples"])
    final_snapshot = read_snapshot_csv(selected[-1])
    initial_snapshot = np.genfromtxt(
        project_path(spec["initial_conditions"], must_exist=True),
        delimiter=",",
        names=True,
    )
    initial_wealth = float(np.sum(np.atleast_1d(initial_snapshot)["w"]))
    final_wealth = float(np.sum(final_snapshot["w"]))
    means["total_wealth_relative_drift"] = (
        (final_wealth - initial_wealth) / initial_wealth if initial_wealth else 0.0
    )
    return {
        **dict(spec),
        **means,
        "snapshots_used": len(selected),
        "stationarity_diagnostics": diagnostics,
    }


def write_metrics_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    if not rows:
        raise ValueError("no metrics to write")
    fieldnames: List[str] = []
    for row in rows:
        for key, value in row.items():
            if isinstance(value, (dict, list)):
                continue
            if key not in fieldnames:
                fieldnames.append(key)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(
            {key: value for key, value in row.items() if key in fieldnames}
            for row in rows
        )


def load_e0_calibration(config: Mapping[str, Any]) -> Dict[str, Any]:
    relative = config.get("numerical_calibration")
    if not isinstance(relative, str) or not relative:
        raise ValueError("confirmatory analysis requires numerical_calibration")
    calibration_path = project_path(relative, must_exist=True)
    declared_sha256 = config.get("numerical_calibration_sha256")
    if not isinstance(declared_sha256, str) or len(declared_sha256) != 64:
        raise RuntimeError(
            "confirmatory analysis requires a frozen 64-character "
            "numerical_calibration_sha256"
        )
    actual_sha256 = sha256_file(calibration_path)
    if actual_sha256 != declared_sha256:
        raise RuntimeError(
            f"E0 calibration checksum mismatch: expected {declared_sha256}, "
            f"got {actual_sha256}"
        )
    calibration = load_json(calibration_path)
    if calibration.get("experiment") != "E0-NUMERICS" or not calibration.get("pass"):
        raise RuntimeError("E0 numerical calibration is missing or did not pass")
    sesoi = calibration.get("sesoi_frozen_before_confirmatory_analysis")
    if not isinstance(sesoi, dict) or not sesoi:
        raise RuntimeError("E0 numerical calibration does not contain frozen SESOI values")
    return calibration


def apply_holm_and_sesoi(
    intervals: Mapping[str, Mapping[str, float]],
    sesoi: Mapping[str, float],
    *,
    alpha: float,
    metric_for_key: Mapping[str, str],
) -> Dict[str, Dict[str, Any]]:
    decisions = holm_adjust(
        {key: float(value["sign_flip_p_value"]) for key, value in intervals.items()},
        alpha=alpha,
    )
    return {
        key: annotate_confirmatory_effect(
            interval,
            sesoi=float(sesoi[metric_for_key[key]]),
            holm_result=decisions[key],
        )
        for key, interval in intervals.items()
    }


def aggregate_e1(
    rows: Sequence[Mapping[str, Any]],
    config: Mapping[str, Any],
    output_dir: Path,
) -> Dict[str, Any]:
    metrics = (
        "resource_density_spearman_rho",
        "density_morans_i",
        "occupancy_entropy",
        "wealth_gini",
    )
    by_seed = defaultdict(dict)
    for row in rows:
        by_seed[int(row["seed"])][str(row["condition"])] = row
    required_conditions = {"clustered", "shuffled", "flat", "clustered-no-exchange"}
    for seed, values in by_seed.items():
        missing = sorted(required_conditions - set(values))
        if missing:
            raise RuntimeError(f"E1 seed {seed} is missing conditions: {missing}")
    calibration = load_e0_calibration(config)
    sesoi = calibration["sesoi_frozen_before_confirmatory_analysis"]
    raw_intervals: Dict[str, Dict[str, float]] = {}
    for metric in metrics:
        clustered = [by_seed[seed]["clustered"][metric] for seed in sorted(by_seed)]
        shuffled = [by_seed[seed]["shuffled"][metric] for seed in sorted(by_seed)]
        raw_intervals[metric] = paired_bootstrap_mean_difference(
            clustered, shuffled, seed=9173
        )
    primary_metrics = metrics[:3]
    primary = apply_holm_and_sesoi(
        {metric: raw_intervals[metric] for metric in primary_metrics},
        sesoi,
        alpha=float(config.get("familywise_alpha", 0.05)),
        metric_for_key={metric: metric for metric in primary_metrics},
    )
    wealth = apply_holm_and_sesoi(
        {"wealth_gini": raw_intervals["wealth_gini"]},
        sesoi,
        alpha=float(config.get("familywise_alpha", 0.05)),
        metric_for_key={"wealth_gini": "wealth_gini"},
    )
    stationarity_pass = all(bool(row["stationarity_pass"]) for row in rows)
    matched_input_pass = bool(load_json(output_dir / "matched_input_audit.json")["pass"])
    payload: Dict[str, Any] = {
        "experiment": "E1-MATCHED-LANDSCAPES",
        "comparison": "clustered-minus-shuffled",
        "analysis_gate_pass": bool(stationarity_pass and matched_input_pass),
        "claim_supported": bool(
            stationarity_pass
            and matched_input_pass
            and any(value["claim_threshold_pass"] for value in primary.values())
        ),
        "gates": {
            "e0_calibration": True,
            "stationarity": stationarity_pass,
            "matched_inputs": matched_input_pass,
        },
        "confirmatory_spatial_family": primary,
        "secondary_wealth_family": wealth,
        "multiplicity": "Holm family-wise correction",
    }
    write_json(output_dir / "paired_effects.json", payload)
    return payload


def aggregate_e0(rows: Sequence[Mapping[str, Any]], output_dir: Path) -> Dict[str, Any]:
    by_condition: MutableMapping[str, List[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        by_condition[str(row["condition"])].append(row)

    required = {
        "equal-no-exchange",
        "equal-exchange",
        "perturbed-dt-1",
        "perturbed-dt-0.5",
        "perturbed-dt-0.25",
    }
    missing = sorted(required - set(by_condition))
    if missing:
        raise RuntimeError(f"E0 is missing required conditions: {missing}")

    max_abs_drift = max(
        abs(float(row["total_wealth_relative_drift"])) for row in rows
    )
    minimum_wealth = min(float(row["minimum_wealth"]) for row in rows)
    bounded_metrics = (
        "resource_density_spearman_rho",
        "density_morans_i",
        "occupancy_entropy",
        "wealth_gini",
    )
    convergence: Dict[str, float] = {}
    sesoi_diagnostics: Dict[str, Dict[str, float]] = {}
    for metric in bounded_metrics:
        half_rows = sorted(
            by_condition["perturbed-dt-0.5"], key=lambda item: int(item["seed"])
        )
        quarter_rows = sorted(
            by_condition["perturbed-dt-0.25"], key=lambda item: int(item["seed"])
        )
        half_seeds = [int(row["seed"]) for row in half_rows]
        quarter_seeds = [int(row["seed"]) for row in quarter_rows]
        if half_seeds != quarter_seeds:
            raise RuntimeError("E0 dt/2 and dt/4 conditions do not have paired seeds")
        dt_half = [
            float(row[metric])
            for row in half_rows
        ]
        dt_quarter = [
            float(row[metric])
            for row in quarter_rows
        ]
        paired_absolute_differences = np.abs(
            np.asarray(dt_half, dtype=np.float64)
            - np.asarray(dt_quarter, dtype=np.float64)
        )
        convergence[metric] = float(np.mean(paired_absolute_differences))
        sesoi_diagnostics[metric] = paired_discretization_sesoi(
            dt_half,
            dt_quarter,
            floor=1e-6,
        )
    sesoi = {
        metric: diagnostic["threshold"]
        for metric, diagnostic in sesoi_diagnostics.items()
    }
    equal_exchange_variance = max(
        float(row["wealth_variance"]) for row in by_condition["equal-exchange"]
    )
    checks = {
        "wealth_conservation": max_abs_drift <= 1e-8,
        "wealth_nonnegative": minimum_wealth >= -1e-12,
        "dt_convergence": all(value <= 0.02 for value in convergence.values()),
        "equal_state_is_absorbing": equal_exchange_variance <= 1e-20,
        "stationarity": all(bool(row["stationarity_pass"]) for row in rows),
    }
    payload = {
        "experiment": "E0-NUMERICS",
        "pass": all(checks.values()),
        "checks": checks,
        "max_absolute_wealth_drift": max_abs_drift,
        "minimum_wealth": minimum_wealth,
        "dt_half_vs_quarter_mean_absolute_change": convergence,
        "equal_exchange_max_wealth_variance": equal_exchange_variance,
        "sesoi_frozen_before_confirmatory_analysis": sesoi,
        "sesoi_diagnostics": sesoi_diagnostics,
        "sesoi_basis": (
            "Paired same-seed dt/2 versus dt/4 discretization differences. "
            "Each threshold is the maximum of the observed absolute envelope, "
            "absolute paired bias plus two sample standard deviations, and 1e-6. "
            "It is a conservative simulation-resolution limit, not a substantive "
            "social-science effect size."
        ),
        "interpretation_boundary": (
            "The equal-state check diagnoses the deterministic exchange kernel's "
            "absorbing state; it is not evidence for a Boltzmann-Gibbs wealth law."
        ),
    }
    write_json(output_dir / "numerical_calibration.json", payload)
    return payload


def aggregate_e2(
    rows: Sequence[Mapping[str, Any]],
    config: Mapping[str, Any],
    output_dir: Path,
) -> Dict[str, Any]:
    metrics = (
        "resource_density_spearman_rho",
        "density_morans_i",
        "occupancy_entropy",
        "wealth_gini",
    )
    cells = defaultdict(dict)
    for row in rows:
        key = (int(row["seed"]), str(row["landscape"]))
        cell = (bool(row["terrain_force_enabled"]), bool(row["terrain_production_enabled"]))
        cells[key][cell] = row
    calibration = load_e0_calibration(config)
    sesoi = calibration["sesoi_frozen_before_confirmatory_analysis"]
    raw_intervals: Dict[str, Dict[str, float]] = {}
    metric_for_key: Dict[str, str] = {}
    for metric in metrics:
        per_seed: MutableMapping[int, Dict[str, List[float]]] = defaultdict(
            lambda: defaultdict(list)
        )
        for (seed, _landscape), values in cells.items():
            y00 = float(values[(False, False)][metric])
            y10 = float(values[(True, False)][metric])
            y01 = float(values[(False, True)][metric])
            y11 = float(values[(True, True)][metric])
            per_seed[seed]["movement"].append(0.5 * ((y10 - y00) + (y11 - y01)))
            per_seed[seed]["production"].append(0.5 * ((y01 - y00) + (y11 - y10)))
            per_seed[seed]["interaction"].append(y11 - y10 - y01 + y00)
        for effect in ("movement", "production", "interaction"):
            estimates = [
                float(np.mean(per_seed[seed][effect])) for seed in sorted(per_seed)
            ]
            key = f"{metric}::{effect}"
            raw_intervals[key] = paired_bootstrap_mean_difference(
                estimates, np.zeros(len(estimates)), seed=9173
            )
            metric_for_key[key] = metric
    primary_keys = [key for key in raw_intervals if not key.startswith("wealth_gini::")]
    secondary_keys = [key for key in raw_intervals if key.startswith("wealth_gini::")]
    primary = apply_holm_and_sesoi(
        {key: raw_intervals[key] for key in primary_keys},
        sesoi,
        alpha=float(config.get("familywise_alpha", 0.05)),
        metric_for_key=metric_for_key,
    )
    wealth = apply_holm_and_sesoi(
        {key: raw_intervals[key] for key in secondary_keys},
        sesoi,
        alpha=float(config.get("familywise_alpha", 0.05)),
        metric_for_key=metric_for_key,
    )
    stationarity_pass = all(bool(row["stationarity_pass"]) for row in rows)
    matched_input_pass = bool(load_json(output_dir / "matched_input_audit.json")["pass"])
    identified_channels = [
        effect
        for effect in ("movement", "production")
        if any(
            value["claim_threshold_pass"]
            for key, value in primary.items()
            if key.endswith(f"::{effect}")
        )
    ]
    interaction_identified = any(
        value["claim_threshold_pass"]
        for key, value in primary.items()
        if key.endswith("::interaction")
    )
    payload: Dict[str, Any] = {
        "experiment": "E2-CHANNEL-ABLATION",
        "design": "movement-by-production-2x2",
        "analysis_gate_pass": bool(stationarity_pass and matched_input_pass),
        "claim_supported": bool(
            stationarity_pass
            and matched_input_pass
            and (identified_channels or interaction_identified)
        ),
        "identified_channels": identified_channels,
        "interaction_identified": interaction_identified,
        "mechanism_conclusion": (
            "single-channel attribution available"
            if identified_channels
            else "combined mechanism only"
            if interaction_identified
            else "inconclusive"
        ),
        "gates": {
            "e0_calibration": True,
            "stationarity": stationarity_pass,
            "matched_inputs": matched_input_pass,
        },
        "confirmatory_spatial_family": primary,
        "secondary_wealth_family": wealth,
        "multiplicity": "Holm family-wise correction",
    }
    write_json(output_dir / "channel_effects.json", payload)
    return payload


def aggregate_e3(
    rows: Sequence[Mapping[str, Any]],
    config: Mapping[str, Any],
    output_dir: Path,
) -> Dict[str, Any]:
    metrics = (
        "resource_density_spearman_rho",
        "density_morans_i",
        "occupancy_entropy",
        "wealth_gini",
    )
    grouped: MutableMapping[
        tuple[int, int, int, int, str], Dict[str, Mapping[str, Any]]
    ] = defaultdict(dict)
    for row in rows:
        key = (
            int(row["seed"]),
            int(row["population"]),
            int(row["grid_rows"]),
            int(row["grid_cols"]),
            str(row["landscape_family"]),
        )
        grouped[key][str(row["condition"])] = row
    for key, values in grouped.items():
        missing = sorted({"clustered", "shuffled"} - set(values))
        if missing:
            raise RuntimeError(f"E3 design cell {key} is missing conditions: {missing}")

    differences: Dict[str, Dict[tuple[int, int, int, int, str], float]] = {
        metric: {} for metric in metrics
    }
    for key, values in grouped.items():
        for metric in metrics:
            differences[metric][key] = float(
                values["clustered"][metric] - values["shuffled"][metric]
            )

    calibration = load_e0_calibration(config)
    sesoi = calibration["sesoi_frozen_before_confirmatory_analysis"]
    alpha = float(config.get("familywise_alpha", 0.05))
    populations = sorted({key[1] for key in grouped})
    resolutions = sorted({(key[2], key[3]) for key in grouped})
    families = sorted({key[4] for key in grouped})
    seeds = sorted({key[0] for key in grouped})

    cell_intervals: Dict[str, Dict[str, float]] = {}
    metric_for_cell: Dict[str, str] = {}
    for metric in metrics:
        for population in populations:
            for grid_rows, grid_cols in resolutions:
                for family in families:
                    key_name = (
                        f"{metric}::population-{population}::"
                        f"grid-{grid_rows}x{grid_cols}::{family}"
                    )
                    estimates = [
                        differences[metric][
                            (seed, population, grid_rows, grid_cols, family)
                        ]
                        for seed in seeds
                    ]
                    cell_intervals[key_name] = paired_bootstrap_mean_difference(
                        estimates, np.zeros(len(estimates)), seed=9173
                    )
                    metric_for_cell[key_name] = metric
    primary_cell_keys = [
        key for key in cell_intervals if not key.startswith("wealth_gini::")
    ]
    secondary_cell_keys = [
        key for key in cell_intervals if key.startswith("wealth_gini::")
    ]
    scale_specific_primary = apply_holm_and_sesoi(
        {key: cell_intervals[key] for key in primary_cell_keys},
        sesoi,
        alpha=alpha,
        metric_for_key=metric_for_cell,
    )
    scale_specific_wealth = apply_holm_and_sesoi(
        {key: cell_intervals[key] for key in secondary_cell_keys},
        sesoi,
        alpha=alpha,
        metric_for_key=metric_for_cell,
    )

    holdout_family = "correlated_random_field"
    holdout_raw: Dict[str, Dict[str, float]] = {}
    for metric in metrics[:3]:
        per_seed = [
            float(
                np.mean(
                    [
                        value
                        for key, value in differences[metric].items()
                        if key[0] == seed and key[4] == holdout_family
                    ]
                )
            )
            for seed in seeds
        ]
        holdout_raw[metric] = paired_bootstrap_mean_difference(
            per_seed, np.zeros(len(per_seed)), seed=12011
        )
    holdout_effects = apply_holm_and_sesoi(
        holdout_raw,
        sesoi,
        alpha=alpha,
        metric_for_key={metric: metric for metric in holdout_raw},
    )

    direction_consistency: Dict[str, Any] = {}
    resolution_sensitivity: Dict[str, Any] = {}
    for metric in metrics[:3]:
        overall = float(np.mean(list(differences[metric].values())))
        overall_sign = int(np.sign(overall))
        population_effects = {
            str(population): float(
                np.mean(
                    [
                        value
                        for key, value in differences[metric].items()
                        if key[1] == population
                    ]
                )
            )
            for population in populations
        }
        direction_consistency[metric] = {
            "overall_mean_effect": overall,
            "population_mean_effects": population_effects,
            "pass": bool(
                overall_sign != 0
                and all(
                    int(np.sign(value)) == overall_sign
                    for value in population_effects.values()
                )
            ),
        }
        resolution_effects = {
            f"{grid_rows}x{grid_cols}": float(
                np.mean(
                    [
                        value
                        for key, value in differences[metric].items()
                        if key[2:4] == (grid_rows, grid_cols)
                    ]
                )
            )
            for grid_rows, grid_cols in resolutions
        }
        resolution_values = list(resolution_effects.values())
        if len(resolution_values) != 2:
            raise RuntimeError("E3 resolution sensitivity requires exactly two grids")
        relative_change = abs(resolution_values[1] - resolution_values[0]) / max(
            abs(resolution_values[1]), float(sesoi[metric]), 1e-12
        )
        resolution_sensitivity[metric] = {
            "resolution_mean_effects": resolution_effects,
            "relative_change": relative_change,
            "max_relative_change": 0.2,
            "pass": bool(relative_change <= 0.2),
        }

    stationarity_pass = all(bool(row["stationarity_pass"]) for row in rows)
    matched_input_pass = bool(load_json(output_dir / "matched_input_audit.json")["pass"])
    parameter_lock_pass = bool(load_json(output_dir / "parameter_lock_audit.json")["pass"])
    analysis_gate_pass = bool(
        stationarity_pass and matched_input_pass and parameter_lock_pass
    )
    primary_metric = "resource_density_spearman_rho"
    claim_supported = bool(
        analysis_gate_pass
        and holdout_effects[primary_metric]["claim_threshold_pass"]
        and direction_consistency[primary_metric]["pass"]
        and resolution_sensitivity[primary_metric]["pass"]
    )
    payload: Dict[str, Any] = {
        "experiment": "E3-ROBUSTNESS-HOLDOUT",
        "comparison": "clustered-minus-shuffled",
        "confirmatory_unit": "seed; repeated scales and families averaged within seed",
        "analysis_gate_pass": analysis_gate_pass,
        "claim_supported": claim_supported,
        "gates": {
            "e0_calibration": True,
            "stationarity": stationarity_pass,
            "matched_inputs": matched_input_pass,
            "parameter_lock": parameter_lock_pass,
        },
        "scale_specific_spatial_family": scale_specific_primary,
        "scale_specific_wealth_family": scale_specific_wealth,
        "holdout_family": holdout_family,
        "holdout_pooled_spatial_effects": holdout_effects,
        "population_direction_consistency": direction_consistency,
        "resolution_sensitivity": resolution_sensitivity,
        "multiplicity": "Holm family-wise correction within scale-specific and pooled-holdout spatial families",
    }
    write_json(output_dir / "holdout_effects.json", payload)
    return payload


def analyze_runs(
    experiment: str,
    config: Mapping[str, Any],
    output_dir: Path,
    run_specs: Sequence[Mapping[str, Any]],
) -> List[Dict[str, Any]]:
    rows = [
        mean_metrics_for_run(
            spec,
            bounds=config.get("bounds", [0.0, 100.0, 0.0, 100.0]),
            steady_snapshots=int(config.get("steady_snapshots", 5)),
            stationarity_max_drift=float(
                config.get("stationarity_max_normalized_drift", 0.1)
            ),
            stationarity_min_ess=float(config.get("stationarity_min_ess", 3.0)),
        )
        for spec in run_specs
    ]
    write_metrics_csv(output_dir / "replicate_metrics.csv", rows)
    write_json(
        output_dir / "stationarity_report.json",
        {
            "experiment": experiment,
            "pass": all(bool(row["stationarity_pass"]) for row in rows),
            "runs": [
                {
                    "run_id": row["run_id"],
                    "pass": row["stationarity_pass"],
                    "metrics": row["stationarity_diagnostics"],
                }
                for row in rows
            ],
        },
    )
    if experiment == "E0-NUMERICS":
        calibration = aggregate_e0(rows, output_dir)
        tracked_calibration = config.get("calibration_result")
        if not isinstance(tracked_calibration, str) or not tracked_calibration:
            raise ValueError("E0 requires calibration_result for tracked provenance")
        write_json(project_path(tracked_calibration), calibration)
    elif experiment == "E1-MATCHED-LANDSCAPES":
        aggregate_e1(rows, config, output_dir)
    elif experiment == "E2-CHANNEL-ABLATION":
        aggregate_e2(rows, config, output_dir)
    elif experiment == "E3-ROBUSTNESS-HOLDOUT":
        aggregate_e3(rows, config, output_dir)
    return rows


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment", required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--analyze-only", action="store_true")
    args = parser.parse_args(argv)

    require_umi()
    config_path = project_path(args.config, must_exist=True)
    output_dir = project_path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    config = load_json(config_path)
    if config.get("experiment_id") != args.experiment:
        raise ValueError("experiment_id in config does not match --experiment")
    parameter_lock_audit = validate_parameter_lock(
        args.experiment,
        config,
        output_dir,
        require_final=not args.prepare_only,
    )

    specs_path = output_dir / "run_specs.json"
    if args.analyze_only:
        run_specs = load_json(specs_path)["runs"]
    else:
        run_specs = prepare_inputs(args.experiment, config, output_dir)

    if args.prepare_only:
        return 0

    if args.experiment != "E0-NUMERICS":
        load_e0_calibration(config)

    execution_summary: Dict[str, Any] = {
        "executed": 0,
        "skipped_completed": 0,
        "completed_run_ids": [],
    }
    if not args.analyze_only:
        binary = project_path(config["binary"], must_exist=True)
        execution_summary = execute_runs(
            run_specs,
            binary,
            timeout_seconds=int(config.get("per_run_timeout_seconds", 3600)),
            omp_threads=int(config.get("omp_threads", 8)),
        )

    rows = analyze_runs(args.experiment, config, output_dir, run_specs)
    job_pass = True
    if args.experiment == "E0-NUMERICS":
        job_pass = bool(load_json(output_dir / "numerical_calibration.json")["pass"])
    elif args.experiment == "E1-MATCHED-LANDSCAPES":
        job_pass = bool(load_json(output_dir / "paired_effects.json")["analysis_gate_pass"])
    elif args.experiment == "E2-CHANNEL-ABLATION":
        job_pass = bool(load_json(output_dir / "channel_effects.json")["analysis_gate_pass"])
    elif args.experiment == "E3-ROBUSTNESS-HOLDOUT":
        job_pass = bool(load_json(output_dir / "holdout_effects.json")["analysis_gate_pass"])
    result = {
        "experiment": args.experiment,
        "status": "completed",
        "pass": job_pass,
        "runs_completed": len(rows),
        "runs_executed_this_invocation": execution_summary["executed"],
        "runs_reused_from_completion_markers": execution_summary[
            "skipped_completed"
        ],
        "config_sha256": sha256_file(config_path),
        "omp_threads": int(config.get("omp_threads", 8)),
        "parameter_lock_sha256": (
            parameter_lock_audit["parameter_lock_sha256"]
            if parameter_lock_audit is not None
            else None
        ),
        "evidence_boundary": "Synthetic generative mechanism only; no historical-state claim.",
        "artifacts": sorted(
            relative_to_project(path)
            for path in output_dir.iterdir()
            if path.is_file()
        ),
    }
    if args.experiment == "E0-NUMERICS":
        tracked_calibration = project_path(
            str(config["calibration_result"]), must_exist=True
        )
        result["tracked_calibration_result"] = relative_to_project(
            tracked_calibration
        )
        result["tracked_calibration_sha256"] = sha256_file(tracked_calibration)
    write_json(output_dir / "result.json", result)
    summary_result = config.get("summary_result")
    if summary_result:
        write_json(project_path(str(summary_result)), result)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise
