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
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional, Sequence

import numpy as np

from landscape_study import (
    annotate_confirmatory_effect,
    audit_matched_landscapes,
    audit_parameter_lock,
    canonical_payload_sha256,
    completion_marker_is_reusable,
    generate_smooth_resource,
    holm_adjust,
    make_matched_landscapes,
    metric_status,
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
E1_C4_EXPERIMENT = "E1-MATCHED-LANDSCAPES-C4"
C4_CALIBRATION_EXPERIMENT = "V1F-NONFLAT-CALIBRATION-C4"
C4_EFFECT_METRICS = (
    "resource_density_spearman_rho",
    "density_morans_i",
    "occupancy_entropy",
    "wealth_gini",
)


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
    if experiment in {"E0-NUMERICS", "B0-DYNAMICS-PILOT"}:
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
    noise_strength = float(config.get("exchange_noise_strength", 0.0))
    reversion_rate = float(config.get("exchange_reversion_rate", 1.0))
    epsilon_log_sigma = float(config.get("epsilon_log_sigma", 0.0))
    wealth_decay_rate = float(config.get("wealth_decay_rate", 0.0))
    dt = float(config.get("dt", 0.01))
    if experiment == "E0-NUMERICS":
        return [
            {
                "name": "equal-no-exchange",
                "landscape": "flat",
                "terrain_force_enabled": False,
                "terrain_production_enabled": False,
                "exchange_rate": 0.0,
                "exchange_noise_strength": 0.0,
                # R04: "no-exchange" must disable drift, noise AND reversion —
                # otherwise the mean-reversion term dt·k·(1/2−share) still moves
                # wealth. Setting reversion to 0 makes the kernel a strict no-op.
                "exchange_reversion_rate": 0.0,
                "exchange_enabled": False,
                "wealth_log_sigma": 0.0,
                # Uniform ability keeps the equal-state absorption check
                # (w_i=w_j and eps_i=eps_j => D_ij=0 => no exchange) well-defined.
                "epsilon_log_sigma": 0.0,
                "dt": dt,
            },
            {
                "name": "equal-exchange",
                "landscape": "flat",
                "terrain_force_enabled": False,
                "terrain_production_enabled": False,
                "exchange_rate": exchange_rate,
                "exchange_noise_strength": 0.0,
                "wealth_log_sigma": 0.0,
                "epsilon_log_sigma": 0.0,
                "dt": dt,
            },
            *[
                {
                    "name": f"perturbed-dt-{factor:g}",
                    "landscape": "flat",
                    "terrain_force_enabled": False,
                    "terrain_production_enabled": False,
                    # Candidate C is now a continuous-time rate model: k, η_d, η_n
                    # are O(1) rates and the C++ kernel discretizes drift by dt and
                    # fluctuation by sqrt(dt) internally, so the rates are held
                    # fixed across dt — this is what makes dt-convergence hold.
                    "exchange_rate": exchange_rate,
                    "exchange_noise_strength": noise_strength,
                    "exchange_reversion_rate": reversion_rate,
                    "wealth_log_sigma": 0.01,
                    # Heterogeneous ability supplies a persistent wealth-gap
                    # source, giving the exchange kernel a non-trivial steady state.
                    "epsilon_log_sigma": epsilon_log_sigma,
                    "dt": dt * factor,
                }
                for factor in (1.0, 0.5, 0.25)
            ],
        ]
    if experiment == "B0-DYNAMICS-PILOT":
        return [
            {
                "name": "clustered-active-health-only",
                "landscape": "clustered",
                "terrain_force_enabled": True,
                "terrain_production_enabled": True,
                "exchange_rate": exchange_rate,
                "exchange_noise_strength": noise_strength,
                "wealth_log_sigma": 0.01,
                "epsilon_log_sigma": epsilon_log_sigma,
                "dt": dt,
            }
        ]
    if experiment == E1_C4_EXPERIMENT:
        # Cycle 4 isolates the confirmatory landscape contrast. Flat and
        # no-exchange conditions belong to separate diagnostics and must not
        # consume or alter the matched-effect family.
        return [
            {
                "name": landscape,
                "landscape": landscape,
                "terrain_force_enabled": True,
                "terrain_production_enabled": True,
                "exchange_rate": exchange_rate,
                "exchange_noise_strength": noise_strength,
                "wealth_log_sigma": 0.01,
                "epsilon_log_sigma": epsilon_log_sigma,
                "dt": dt,
            }
            for landscape in ("clustered", "shuffled")
        ]
    if experiment == "E1-MATCHED-LANDSCAPES":
        return [
            {
                "name": landscape,
                "landscape": landscape,
                "terrain_force_enabled": True,
                "terrain_production_enabled": True,
                "exchange_rate": exchange_rate,
                "exchange_noise_strength": noise_strength,
                "wealth_log_sigma": 0.01,
                "epsilon_log_sigma": epsilon_log_sigma,
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
                "exchange_noise_strength": 0.0,
                # R04: disable reversion too so the kernel is a strict no-op,
                # not a mean-reversion-only process.
                "exchange_reversion_rate": 0.0,
                "exchange_enabled": False,
                "wealth_log_sigma": 0.01,
                "epsilon_log_sigma": epsilon_log_sigma,
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
                "exchange_noise_strength": noise_strength,
                "wealth_log_sigma": 0.01,
                "epsilon_log_sigma": epsilon_log_sigma,
                # production↔decay 配对（参数锁 v3）：生产通道 = 生产(source) +
                # 衰减(sink) 平衡对。关闭生产时同步关闭衰减，否则 production=0 而
                # decay>0 会把财富指数衰减至坍缩（同 E1 flat bug 的数学根源），
                # 使 2×2 因子分析失效。production=True 时 decay 保持锁定值。
                "wealth_decay_rate": wealth_decay_rate if production else 0.0,
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
        "exchange_noise_strength": float(config.get("exchange_noise_strength", 0.0)),
        "exchange_reversion_rate": float(config.get("exchange_reversion_rate", 1.0)),
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
        "strict_numerics": bool(config.get("strict_numerics", True)),
        "confirmative_mode": bool(config.get("confirmative_mode", False)),
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
    epsilon_log_sigma = float(config.get("epsilon_log_sigma", 0.0))
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
                        / f"seed-{seed}-eps-{epsilon_log_sigma:.6g}.csv"
                    )
                    if not ic_path.exists():
                        initial_sha256 = write_initial_conditions(
                            ic_path,
                            population,
                            seed,
                            bounds=bounds,
                            mean_wealth=float(config.get("mean_wealth", 5.0)),
                            wealth_log_sigma=0.01,
                            epsilon_log_sigma=epsilon_log_sigma,
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
                                "exchange_noise_strength": float(
                                    config.get("exchange_noise_strength", 0.0)
                                ),
                                "exchange_reversion_rate": float(
                                    config.get("exchange_reversion_rate", 1.0)
                                ),
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
        fields = {**fields, "smooth": generate_smooth_resource(shape)}
        audit = audit_matched_landscapes(fields["clustered"], fields["shuffled"])
        audit["seed"] = seed
        matching_audits.append(audit)
        if not audit["pass"]:
            raise RuntimeError(f"matched input audit failed for seed {seed}")

        landscape_paths: Dict[str, Path] = {}
        resource_paths: Dict[str, Path] = {}
        landscape_checksums: Dict[str, str] = {}
        resource_checksums: Dict[str, str] = {}
        initial_checksums_by_condition: Dict[str, str] = {}
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
            storage_order = str(condition.get("storage_order", "canonical"))
            explicit_phase_state = bool(
                condition.get("explicit_phase_state", storage_order != "canonical")
            )
            ic_path = seed_dir / (
                f"initial-sigma-{float(condition.get('wealth_log_sigma', 0.01)):.6g}"
                f"-eps-{float(condition.get('epsilon_log_sigma', 0.0)):.6g}.csv"
                if not explicit_phase_state
                else
                f"initial-explicit-{storage_order}"
                f"-sigma-{float(condition.get('wealth_log_sigma', 0.01)):.6g}"
                f"-eps-{float(condition.get('epsilon_log_sigma', 0.0)):.6g}.csv"
            )
            if not ic_path.exists():
                initial_checksum = write_initial_conditions(
                    ic_path,
                    population,
                    seed,
                    bounds=bounds,
                    mean_wealth=float(config.get("mean_wealth", 5.0)),
                    wealth_log_sigma=float(condition.get("wealth_log_sigma", 0.01)),
                    epsilon_log_sigma=float(condition.get("epsilon_log_sigma", 0.0)),
                    explicit_phase_state=explicit_phase_state,
                    row_order=storage_order,
                    momentum_temperature=float(
                        condition.get(
                            "initial_temperature", config.get("temperature", 0.5)
                        )
                    ),
                )
            else:
                initial_checksum = sha256_file(ic_path)
            initial_checksums_by_condition[condition_name] = initial_checksum

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
                    "temperature": float(
                        condition.get("temperature", config.get("temperature", 0.5))
                    ),
                    "random_seed": seed,
                    "initial_particles": population,
                    "initial_conditions_file": relative_to_project(ic_path),
                    "terrain_file": relative_to_project(landscape_paths[landscape_name]),
                    "terrain_force_enabled": bool(condition["terrain_force_enabled"]),
                    "terrain_production_enabled": bool(
                        condition["terrain_production_enabled"]
                    ),
                    "wealth_decay_rate": float(
                        condition.get(
                            "wealth_decay_rate",
                            config.get("wealth_decay_rate", 0.0),
                        )
                    ),
                    "exchange_rate": float(condition["exchange_rate"]),
                    "exchange_noise_strength": float(
                        condition.get("exchange_noise_strength", 0.0)
                    ),
                    "exchange_reversion_rate": float(
                        condition.get(
                            "exchange_reversion_rate",
                            config.get("exchange_reversion_rate", 1.0),
                        )
                    ),
                    "exchange_enabled": bool(condition.get("exchange_enabled", True)),
                    "base_production": float(
                        condition.get(
                            "base_production", config.get("base_production", 0.01)
                        )
                    ),
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
                    "wealth_decay_rate": float(
                        condition.get(
                            "wealth_decay_rate",
                            config.get("wealth_decay_rate", 0.0),
                        )
                    ),
                    "exchange_rate": float(condition["exchange_rate"]),
                    "exchange_noise_strength": float(
                        condition.get("exchange_noise_strength", 0.0)
                    ),
                    "exchange_reversion_rate": float(
                        condition.get(
                            "exchange_reversion_rate",
                            config.get("exchange_reversion_rate", 1.0),
                        )
                    ),
                    "exchange_enabled": bool(condition.get("exchange_enabled", True)),
                    "epsilon_log_sigma": float(
                        condition.get("epsilon_log_sigma", 0.0)
                    ),
                    "dt": float(condition.get("dt", config.get("dt", 0.01))),
                    "temperature": float(
                        condition.get("temperature", config.get("temperature", 0.5))
                    ),
                    "storage_order": storage_order,
                    "explicit_phase_state": explicit_phase_state,
                    "calibration_component": str(
                        condition.get("calibration_component", "timestep")
                    ),
                    "cpp_config": relative_to_project(cpp_config_path),
                    "run_dir": relative_to_project(run_dir),
                    "resource_npy": relative_to_project(resource_paths[landscape_name]),
                    "initial_conditions": relative_to_project(ic_path),
                    "terrain_sha256": landscape_checksums[landscape_name],
                    "resource_sha256": resource_checksums[landscape_name],
                    "initial_conditions_sha256": initial_checksum,
                }
            )

        if experiment == E1_C4_EXPERIMENT:
            initial_match = bool(
                initial_checksums_by_condition.get("clustered")
                == initial_checksums_by_condition.get("shuffled")
            )
            audit["initial_state_match"] = initial_match
            audit["initial_state_sha256_by_condition"] = {
                condition: initial_checksums_by_condition[condition]
                for condition in ("clustered", "shuffled")
            }
            audit["initial_state_fields"] = [
                "gid",
                "position",
                "momentum",
                "wealth",
                "ability",
                "age",
            ]
            audit["pass"] = bool(audit["pass"] and initial_match)

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


def _execute_one_run(
    spec: Mapping[str, Any],
    binary: Path,
    binary_sha256: str,
    *,
    timeout_seconds: int,
    omp_threads: int,
) -> Dict[str, Any]:
    """Execute (or reuse) a single run; returns a per-run summary dict.

    Extracted from ``execute_runs`` so a run can be executed either serially
    or in a worker thread.  A run is fully self-contained: it reads/cleans/
    executes/writes only within its own ``run_dir``, so concurrent runs do
    not race (each completion marker is per-run).
    """
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
            return {
                "executed": 0,
                "skipped": 1,
                "elapsed_seconds_executed": 0.0,
                "run_id": str(spec["run_id"]),
            }

    for stale_path in list(run_dir.glob("*.csv")) + list(
        run_dir.glob("snap_*.bin")
    ):
        stale_path.unlink()
    environment = os.environ.copy()
    environment["OMP_NUM_THREADS"] = str(omp_threads)
    started_at = time.monotonic()
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
        elapsed_seconds = time.monotonic() - started_at
        write_json(
            marker_path,
            {
                "status": "failed",
                "run_id": spec["run_id"],
                "run_fingerprint": fingerprint,
                "failure": "timeout",
                "timeout_seconds": timeout_seconds,
                "elapsed_seconds": elapsed_seconds,
            },
        )
        raise RuntimeError(
            f"run {spec['run_id']} exceeded {timeout_seconds} seconds"
        ) from exc
    if completed.returncode != 0:
        elapsed_seconds = time.monotonic() - started_at
        write_json(
            marker_path,
            {
                "status": "failed",
                "run_id": spec["run_id"],
                "run_fingerprint": fingerprint,
                "failure": "nonzero_exit",
                "returncode": completed.returncode,
                "elapsed_seconds": elapsed_seconds,
            },
        )
        raise RuntimeError(
            f"run {spec['run_id']} failed with exit code {completed.returncode}; see {log_path}"
        )
    snapshots = sorted(run_dir.glob("snap_*.csv"))
    elapsed_seconds = time.monotonic() - started_at
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
            "elapsed_seconds": elapsed_seconds,
        },
    )
    return {
        "executed": 1,
        "skipped": 0,
        "elapsed_seconds_executed": elapsed_seconds,
        "run_id": str(spec["run_id"]),
    }


def execute_runs(
    run_specs: Sequence[Mapping[str, Any]],
    binary: Path,
    *,
    timeout_seconds: int,
    omp_threads: int,
    parallel: int = 1,
) -> Dict[str, Any]:
    if not binary.is_file() or not os.access(binary, os.X_OK):
        raise FileNotFoundError(f"Politeia binary is missing or not executable: {binary}")
    binary_sha256 = sha256_file(binary)

    def _merge(per_run_results: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
        summary: Dict[str, Any] = {
            "executed": 0,
            "skipped_completed": 0,
            "binary_sha256": binary_sha256,
            "completed_run_ids": [],
            "elapsed_seconds_executed": 0.0,
        }
        for result in per_run_results:
            summary["executed"] += int(result["executed"])
            summary["skipped_completed"] += int(result["skipped"])
            summary["elapsed_seconds_executed"] += float(
                result["elapsed_seconds_executed"]
            )
            summary["completed_run_ids"].append(str(result["run_id"]))
        summary["completed_run_ids"].sort()
        return summary

    if parallel <= 1:
        results = (
            _execute_one_run(
                spec,
                binary,
                binary_sha256,
                timeout_seconds=timeout_seconds,
                omp_threads=omp_threads,
            )
            for spec in run_specs
        )
        return _merge(results)

    # 并行：每个 politeia 子进程是单核 CPU-bound（OMP=1），subprocess.run 等待时
    # 释放 GIL，因此线程池可同时驱动多个 politeia 子进程并行执行。线程共享内存，
    # 无需 pickle；每个 run 只写自己的 run_dir，无竞争。
    from concurrent.futures import ThreadPoolExecutor
    from functools import partial

    worker = partial(
        _execute_one_run,
        binary=binary,
        binary_sha256=binary_sha256,
        timeout_seconds=timeout_seconds,
        omp_threads=omp_threads,
    )
    with ThreadPoolExecutor(max_workers=parallel) as pool:
        results = list(pool.map(worker, run_specs))
    return _merge(results)


def precision_valid_for_rows(rows: Sequence[Mapping[str, Any]]) -> bool:
    """R12: every defined stationarity diagnostic must have ``precision_pass``.

    Metrics with an ``undefined``/``invalid`` status carry no precision verdict
    and are handled by ``stationarity_valid`` (they block stationarity), so they
    are skipped here. ``precision_valid`` is the effective-sample-size layer.
    """
    for row in rows:
        for diagnostic in row.get("stationarity_diagnostics", {}).values():
            if "precision_pass" in diagnostic and not bool(diagnostic["precision_pass"]):
                return False
    return True


def _stationarity_for_metric(
    metric: str,
    series: Sequence[float],
    status: Mapping[str, Any],
    *,
    max_normalized_drift: float,
    min_effective_samples: float,
    reversal_span_sigma: float = 1.0,
) -> Dict[str, Any]:
    """Route a metric's snapshot series to a stationarity verdict (R01/R06).

    Undefined metrics (constant-field correlation → NaN) and invalid metrics
    (data corruption) cannot support a stationarity claim: they return a
    structured ``{pass: False, status: ...}`` result instead of a fabricated
    slope. Finite series are delegated to ``stationarity_diagnostics``.
    """
    if status.get("status") == "undefined":
        return {
            "pass": False,
            "status": "undefined",
            "reason": status.get("reason"),
            "observations": len(series),
        }
    if status.get("status") == "invalid":
        return {
            "pass": False,
            "status": "invalid",
            "reason": status.get("reason"),
            "observations": len(series),
        }
    return stationarity_diagnostics(
        series,
        max_normalized_drift=max_normalized_drift,
        min_effective_samples=min_effective_samples,
        absolute_drift_tolerance=absolute_drift_tolerance_for_metric(metric),
        reversal_span_sigma=reversal_span_sigma,
    )


def mean_metrics_for_run(
    spec: Mapping[str, Any],
    *,
    bounds: Sequence[float],
    steady_snapshots: int,
    stationarity_max_drift: float,
    stationarity_min_ess: float,
    stationary_metrics: Sequence[str],
    stationarity_reversal_span_sigma: float = 1.0,
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
    metric_statuses = {
        name: metric_status(name, float(np.mean([row[name] for row in rows])))
        for name in metric_names
    }
    # R01: carry the metric value as null when it is undefined/invalid so no
    # raw NaN/Inf leaks into JSON or CSV; keep the finite float otherwise.
    means = {
        name: status["value"] for name, status in metric_statuses.items()
    }
    means["minimum_wealth"] = min(float(row["minimum_wealth"]) for row in rows)
    health_path = run_dir / "health.json"
    if health_path.is_file():
        health = load_json(health_path)
        means["minimum_wealth_observed"] = float(
            health.get("min_wealth_observed", means["minimum_wealth"])
        )
    else:
        means["minimum_wealth_observed"] = means["minimum_wealth"]
    diagnostics = {
        metric: _stationarity_for_metric(
            metric,
            [row[metric] for row in rows],
            metric_statuses.get(metric, {"status": "valid"}),
            max_normalized_drift=stationarity_max_drift,
            min_effective_samples=stationarity_min_ess,
            reversal_span_sigma=stationarity_reversal_span_sigma,
        )
        for metric in stationary_metrics
    }
    # R01/R06: stationarity requires every required metric to be a steady
    # platform AND to be numerically valid; undefined (constant-field) or
    # invalid metrics block rather than silently passing.
    means["stationarity_pass"] = all(
        bool(item["pass"]) for item in diagnostics.values()
    )
    for metric, diagnostic in diagnostics.items():
        if "normalized_window_drift" in diagnostic:
            means[f"{metric}__normalized_drift"] = float(
                diagnostic["normalized_window_drift"]
            )
        if "integrated_autocorrelation_time" in diagnostic:
            means[f"{metric}__iat"] = float(
                diagnostic["integrated_autocorrelation_time"]
            )
        if "effective_samples" in diagnostic:
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
        "metric_statuses": metric_statuses,
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


def validate_c4_calibration_coverage(
    calibration: Mapping[str, Any],
    scientific_sesoi: Mapping[str, Any],
    required_metrics: Sequence[str] = C4_EFFECT_METRICS,
) -> Dict[str, Dict[str, float]]:
    """Keep numerical resolution and scientific relevance thresholds separate."""
    if calibration.get("experiment") != C4_CALIBRATION_EXPERIMENT:
        raise RuntimeError(
            f"Cycle 4 requires {C4_CALIBRATION_EXPERIMENT} calibration"
        )
    if calibration.get("pass") is not True:
        raise RuntimeError("Cycle 4 numerical calibration did not pass")
    numerical = calibration.get("numerical_resolution_limits")
    if not isinstance(numerical, Mapping):
        raise RuntimeError("Cycle 4 calibration has no numerical resolution limits")
    if not isinstance(scientific_sesoi, Mapping):
        raise RuntimeError("Cycle 4 config has no scientific_sesoi")

    thresholds: Dict[str, Dict[str, float]] = {}
    for metric in required_metrics:
        if metric not in numerical:
            raise RuntimeError(f"Cycle 4 calibration is missing {metric}")
        if metric not in scientific_sesoi:
            raise RuntimeError(f"Cycle 4 scientific_sesoi is missing {metric}")
        numerical_value = float(numerical[metric])
        scientific_value = float(scientific_sesoi[metric])
        if not math.isfinite(numerical_value) or numerical_value < 0.0:
            raise RuntimeError(f"Cycle 4 numerical limit for {metric} is invalid")
        if not math.isfinite(scientific_value) or scientific_value < 0.0:
            raise RuntimeError(f"Cycle 4 scientific SESOI for {metric} is invalid")
        thresholds[metric] = {
            "numerical_resolution_limit": numerical_value,
            "scientific_sesoi": scientific_value,
            "effective_claim_threshold": max(numerical_value, scientific_value),
        }
    return thresholds


def load_c4_calibration(config: Mapping[str, Any]) -> Dict[str, Any]:
    relative = config.get("numerical_calibration")
    if not isinstance(relative, str) or not relative:
        raise ValueError("Cycle 4 confirmatory analysis requires numerical_calibration")
    calibration_path = project_path(relative, must_exist=True)
    declared_sha256 = config.get("numerical_calibration_sha256")
    if not isinstance(declared_sha256, str) or len(declared_sha256) != 64:
        raise RuntimeError(
            "Cycle 4 confirmatory analysis requires a frozen 64-character "
            "numerical_calibration_sha256"
        )
    actual_sha256 = sha256_file(calibration_path)
    if actual_sha256 != declared_sha256:
        raise RuntimeError(
            f"Cycle 4 calibration checksum mismatch: expected {declared_sha256}, "
            f"got {actual_sha256}"
        )
    calibration = load_json(calibration_path)
    validate_c4_calibration_coverage(
        calibration,
        config.get("scientific_sesoi", {}),
    )
    return calibration


def load_confirmatory_calibration(
    experiment: str, config: Mapping[str, Any]
) -> Dict[str, Any]:
    if experiment == E1_C4_EXPERIMENT:
        return load_c4_calibration(config)
    return load_e0_calibration(config)


def confirmatory_metrics_for_experiment(experiment: str) -> tuple[str, ...]:
    """Metrics a confirmatory analysis indexes against the frozen SESOI (R03).

    These must each have a finite SESOI threshold in the loaded calibration;
    otherwise the analysis would KeyError after expensive runs complete.
    """
    if experiment in {"E1-MATCHED-LANDSCAPES", E1_C4_EXPERIMENT,
                      "E2-CHANNEL-ABLATION",
                      "E3-ROBUSTNESS-HOLDOUT"}:
        return (
            "resource_density_spearman_rho",
            "density_morans_i",
            "occupancy_entropy",
            "wealth_gini",
        )
    return ()


def validate_calibration_coverage(
    calibration: Mapping[str, Any],
    required_metrics: Sequence[str],
) -> None:
    """Fail fast if the calibration cannot cover a confirmatory analysis (R03).

    Checks every required metric has a finite SESOI threshold and that the
    calibration declares a scope. A flat-terrain numerics calibration does not
    carry spatial-correlation thresholds (they are degenerate), so confirmatory
    experiments that need them must be blocked until a non-flat calibration
    exists (phase C, umi) — never silently substitute an old 1e-6 threshold.
    """
    sesoi = calibration.get("sesoi_frozen_before_confirmatory_analysis")
    if not isinstance(sesoi, dict):
        raise RuntimeError("calibration has no frozen SESOI values")
    missing: List[str] = []
    non_finite: List[str] = []
    for metric in required_metrics:
        if metric not in sesoi:
            missing.append(metric)
        else:
            value = sesoi[metric]
            if not isinstance(value, (int, float)) or not math.isfinite(float(value)):
                non_finite.append(metric)
    if not missing and not non_finite:
        return
    detail: List[str] = []
    if missing:
        detail.append(f"missing SESOI: {sorted(missing)}")
    if non_finite:
        detail.append(f"non-finite SESOI: {sorted(non_finite)}")
    raise RuntimeError(
        "calibration does not cover the confirmatory analysis's required metrics; "
        "a non-flat-terrain calibration (phase C, umi) is required before running "
        "this experiment. " + "; ".join(detail)
    )


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


def _independent_precision_summary(
    values: Sequence[float],
    *,
    absolute_half_width: float | None = None,
    relative_half_width: float | None = None,
) -> Dict[str, Any]:
    data = np.asarray(values, dtype=np.float64)
    if data.ndim != 1 or data.size < 3 or not np.all(np.isfinite(data)):
        raise ValueError("independent precision requires >=3 finite replicate values")
    if (absolute_half_width is None) == (relative_half_width is None):
        raise ValueError("independent precision requires exactly one bound type")
    mean = float(np.mean(data))
    sample_sd = float(np.std(data, ddof=1))
    standard_error = sample_sd / math.sqrt(float(data.size))
    two_se_half_width = 2.0 * standard_error
    if absolute_half_width is not None:
        observed = two_se_half_width
        threshold = float(absolute_half_width)
        kind = "absolute"
    else:
        observed = two_se_half_width / max(abs(mean), 1e-12)
        threshold = float(relative_half_width)
        kind = "relative_to_absolute_mean"
    return {
        "replicates": int(data.size),
        "mean": mean,
        "sample_sd": sample_sd,
        "standard_error": standard_error,
        "two_se_half_width": two_se_half_width,
        "bound_kind": kind,
        "observed_bound": observed,
        "threshold": threshold,
        "pass": bool(observed <= threshold),
    }


def _adjacent_window_summary(
    previous: Sequence[float],
    tail: Sequence[float],
    *,
    absolute_bound: float | None = None,
    relative_bound: float | None = None,
) -> Dict[str, Any]:
    if (absolute_bound is None) == (relative_bound is None):
        raise ValueError("adjacent-window stability requires exactly one bound type")
    earlier = np.asarray(previous, dtype=np.float64)
    later = np.asarray(tail, dtype=np.float64)
    if earlier.shape != later.shape or earlier.ndim != 1 or earlier.size < 3:
        raise ValueError("adjacent-window stability requires >=3 paired replicates")
    if not np.all(np.isfinite(earlier)) or not np.all(np.isfinite(later)):
        raise ValueError("adjacent-window stability contains a non-finite metric")
    differences = later - earlier
    mean_difference = float(np.mean(differences))
    sample_sd = float(np.std(differences, ddof=1))
    standard_error = sample_sd / math.sqrt(float(differences.size))
    two_se_bound = abs(mean_difference) + 2.0 * standard_error
    if absolute_bound is not None:
        observed = two_se_bound
        threshold = float(absolute_bound)
        kind = "absolute"
    else:
        scale = max(abs(float(np.mean(earlier))), abs(float(np.mean(later))), 1e-12)
        observed = two_se_bound / scale
        threshold = float(relative_bound)
        kind = "relative_to_larger_window_mean"
    return {
        "replicates": int(differences.size),
        "signed_mean_difference": mean_difference,
        "absolute_mean_difference": abs(mean_difference),
        "paired_sample_sd": sample_sd,
        "standard_error": standard_error,
        "two_se_bound": two_se_bound,
        "bound_kind": kind,
        "observed_bound": observed,
        "threshold": threshold,
        "pass": bool(observed <= threshold),
    }


def _validate_c4_steady_contract(config: Mapping[str, Any]) -> None:
    if config.get("stationarity_gate_unit") != "condition_ensemble_two_window":
        raise ValueError("E1-C4 requires condition_ensemble_two_window stationarity")
    window = int(config.get("steady_snapshots", 0))
    output_interval = float(config.get("output_time_interval", 0.0))
    total_time = float(config.get("total_time", 0.0))
    if window < 3 or output_interval <= 0.0 or total_time / output_interval < 2 * window:
        raise ValueError("E1-C4 requires two complete adjacent steady windows")
    metrics = set(stationary_metrics_for_experiment(E1_C4_EXPERIMENT))
    precision_absolute = config.get("independent_precision_absolute_half_widths")
    precision_relative = config.get("independent_precision_relative_half_widths")
    adjacent_absolute = config.get("adjacent_window_absolute_bounds")
    adjacent_relative = config.get("adjacent_window_relative_bounds")
    for name, value in (
        ("independent_precision_absolute_half_widths", precision_absolute),
        ("independent_precision_relative_half_widths", precision_relative),
        ("adjacent_window_absolute_bounds", adjacent_absolute),
        ("adjacent_window_relative_bounds", adjacent_relative),
    ):
        if not isinstance(value, Mapping):
            raise ValueError(f"E1-C4 {name} must be an object")
        for metric, threshold in value.items():
            if metric not in metrics:
                raise ValueError(f"E1-C4 {name} contains unsupported metric {metric}")
            if not math.isfinite(float(threshold)) or float(threshold) <= 0.0:
                raise ValueError(f"E1-C4 {name}.{metric} must be finite and positive")
    if set(precision_absolute) & set(precision_relative):
        raise ValueError("E1-C4 precision bounds overlap")
    if set(adjacent_absolute) & set(adjacent_relative):
        raise ValueError("E1-C4 adjacent-window bounds overlap")
    if set(precision_absolute) | set(precision_relative) != metrics:
        raise ValueError("E1-C4 precision bounds must cover every steady metric")
    if set(adjacent_absolute) | set(adjacent_relative) != metrics:
        raise ValueError("E1-C4 adjacent-window bounds must cover every steady metric")


def aggregate_e1_c4_steady_estimand(
    specs: Sequence[Mapping[str, Any]],
    config: Mapping[str, Any],
    output_dir: Path,
) -> Dict[str, Any]:
    """Gate E1-C4 dynamics and seed precision on the matched two-condition ensemble."""
    _validate_c4_steady_contract(config)
    expected_seeds = {int(seed) for seed in config.get("seeds", [])}
    if len(expected_seeds) < 3:
        raise ValueError("E1-C4 requires at least three distinct seeds")
    grouped: Dict[str, List[Mapping[str, Any]]] = defaultdict(list)
    for spec in specs:
        grouped[str(spec["condition"])].append(spec)
    if set(grouped) != {"clustered", "shuffled"}:
        raise RuntimeError("E1-C4 steady gate requires only clustered and shuffled")
    for condition, condition_specs in grouped.items():
        seeds = [int(spec["seed"]) for spec in condition_specs]
        if len(seeds) != len(set(seeds)) or set(seeds) != expected_seeds:
            raise RuntimeError(f"E1-C4 {condition} does not contain the exact seed set")

    window = int(config["steady_snapshots"])
    bounds = tuple(float(value) for value in config["bounds"])
    metrics = stationary_metrics_for_experiment(E1_C4_EXPERIMENT)
    precision_absolute = config["independent_precision_absolute_half_widths"]
    precision_relative = config["independent_precision_relative_half_widths"]
    adjacent_absolute = config["adjacent_window_absolute_bounds"]
    adjacent_relative = config["adjacent_window_relative_bounds"]
    conditions: Dict[str, Any] = {}

    for condition, condition_specs in sorted(grouped.items()):
        replicate_series: Dict[str, List[List[float]]] = {
            metric: [] for metric in metrics
        }
        for spec in sorted(condition_specs, key=lambda item: int(item["seed"])):
            run_dir = project_path(spec["run_dir"], must_exist=True)
            snapshots = sorted(run_dir.glob("snap_*.csv"))
            if len(snapshots) < 2 * window:
                raise RuntimeError(f"{spec['run_id']} has fewer than {2 * window} snapshots")
            resource = np.load(
                project_path(spec["resource_npy"], must_exist=True), allow_pickle=False
            )
            metric_rows = [
                snapshot_metrics(read_snapshot_csv(path), resource, bounds)
                for path in snapshots[-2 * window :]
            ]
            for metric in metrics:
                replicate_series[metric].append(
                    [float(row[metric]) for row in metric_rows]
                )

        reports: Dict[str, Any] = {}
        for metric, raw_series in replicate_series.items():
            arrays = np.asarray(raw_series, dtype=np.float64)
            previous = arrays[:, :window]
            tail = arrays[:, window:]
            previous_means = previous.mean(axis=1)
            tail_means = tail.mean(axis=1)
            tail_ensemble = tail.mean(axis=0)
            temporal = _stationarity_for_metric(
                metric,
                tail_ensemble,
                metric_status(metric, float(np.mean(tail_ensemble))),
                max_normalized_drift=float(config["stationarity_max_normalized_drift"]),
                min_effective_samples=float(config["stationarity_min_ess"]),
                reversal_span_sigma=float(
                    config.get("stationarity_reversal_span_sigma", 1.0)
                ),
            )
            reports[metric] = {
                "tail_temporal_diagnostic": temporal,
                "adjacent_window_stability": _adjacent_window_summary(
                    previous_means,
                    tail_means,
                    absolute_bound=(
                        float(adjacent_absolute[metric])
                        if metric in adjacent_absolute
                        else None
                    ),
                    relative_bound=(
                        float(adjacent_relative[metric])
                        if metric in adjacent_relative
                        else None
                    ),
                ),
                "independent_replicate_precision": _independent_precision_summary(
                    tail_means,
                    absolute_half_width=(
                        float(precision_absolute[metric])
                        if metric in precision_absolute
                        else None
                    ),
                    relative_half_width=(
                        float(precision_relative[metric])
                        if metric in precision_relative
                        else None
                    ),
                ),
            }
        conditions[condition] = {
            "condition": condition,
            "replicates": len(condition_specs),
            "tail_stationarity_pass": all(
                bool(report["tail_temporal_diagnostic"].get("stationarity_pass", False))
                for report in reports.values()
            ),
            "adjacent_window_stability_pass": all(
                bool(report["adjacent_window_stability"]["pass"])
                for report in reports.values()
            ),
            "independent_replicate_precision_pass": all(
                bool(report["independent_replicate_precision"]["pass"])
                for report in reports.values()
            ),
            "temporal_ess_diagnostic_pass": all(
                bool(report["tail_temporal_diagnostic"].get("precision_pass", False))
                for report in reports.values()
            ),
            "metrics": reports,
        }

    tail_stationarity = all(
        condition["tail_stationarity_pass"] for condition in conditions.values()
    )
    adjacent = all(
        condition["adjacent_window_stability_pass"] for condition in conditions.values()
    )
    precision = all(
        condition["independent_replicate_precision_pass"]
        for condition in conditions.values()
    )
    temporal_ess = all(
        condition["temporal_ess_diagnostic_pass"] for condition in conditions.values()
    )
    payload = {
        "experiment": E1_C4_EXPERIMENT,
        "gate_unit": "condition_ensemble_two_window",
        "window_snapshots": window,
        "replicates_per_condition": len(expected_seeds),
        "tail_stationarity_valid": tail_stationarity,
        "adjacent_window_stability_valid": adjacent,
        "independent_replicate_precision_valid": precision,
        "temporal_ess_diagnostic_valid": temporal_ess,
        "conditions": conditions,
        "pass": bool(tail_stationarity and adjacent and precision),
        "temporal_ess_policy": (
            "Reported as a dynamical autocorrelation diagnostic; the effect estimand "
            "is gated on independent seed-level window means."
        ),
    }
    write_json(output_dir / "steady_estimand_report.json", payload)
    write_json(
        output_dir / "ensemble_stationarity_report.json",
        {
            "experiment": E1_C4_EXPERIMENT,
            "gate_unit": "condition_ensemble_temporal_diagnostic",
            "window_snapshots": window,
            "replicates_per_condition": len(expected_seeds),
            "stationarity_valid": tail_stationarity,
            "precision_valid": temporal_ess,
            "pass": bool(tail_stationarity and temporal_ess),
            "gate_role": "diagnostic_only_for_condition_ensemble_two_window",
            "conditions": {
                name: {
                    "condition": name,
                    "replicates": item["replicates"],
                    "stationarity_pass": item["tail_stationarity_pass"],
                    "precision_pass": item["temporal_ess_diagnostic_pass"],
                    "metrics": {
                        metric: report["tail_temporal_diagnostic"]
                        for metric, report in item["metrics"].items()
                    },
                }
                for name, item in conditions.items()
            },
        },
    )
    return payload


def stationary_metrics_for_experiment(experiment: str) -> tuple[str, ...]:
    """Return the steady-window metrics checked for each experiment.

    E0 is a flat-terrain pure-exchange numerics test: spatial density metrics
    are degenerate (undefined) there, so only the wealth distribution is
    checked.

    S03 (Cycle 4 remediation): ``density_morans_i`` and ``wealth_variance``
    are restored to the steady-window gate of every non-E0 experiment — a
    steady-state claim on the spatial/wealth structure cannot be inferred from
    the other metrics alone. ``zero_wealth_fraction`` (zero-wealth mass, WP5.1)
    is added to the wealth stationarity premise. Whether these pass must be
    re-verified on umi after the WP1–WP3 core fixes (deferred).
    """
    if experiment == "E0-NUMERICS":
        # R06: zero_wealth_fraction joins the wealth stationarity premise for
        # E0 (boundary-calibration role), alongside Gini and variance.
        return ("wealth_gini", "wealth_variance", "zero_wealth_fraction")
    return (
        "resource_density_spearman_rho",
        "density_morans_i",
        "occupancy_entropy",
        "wealth_gini",
        "wealth_variance",
        "zero_wealth_fraction",
    )


def absolute_drift_tolerance_for_metric(metric: str) -> Optional[float]:
    """Absolute-drift tolerance per metric (physical-range fraction, 1%).

    Fixes the relative-drift normalisation degeneracy for metrics whose steady
    value is physically ~0 (see ``stationarity_diagnostics``).  The tolerance is
    1% of the metric's natural range, so a whole-window drift below it is a
    steady state regardless of the degenerate relative normalisation.

    ``wealth_variance`` returns ``None`` (no absolute tolerance) because its
    physical range depends on the wealth scale and cannot be fixed a priori.
    """
    if metric in ("resource_density_spearman_rho", "density_morans_i"):
        return 0.02  # Spearman/Moran's I ∈ [-1, 1]，范围 2，1% = 0.02
    if metric in ("occupancy_entropy", "wealth_gini", "zero_wealth_fraction"):
        return 0.01  # 归一化熵 / Gini / 零财富比例 ∈ [0, 1]，范围 1，1% = 0.01
    return None


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
    # C2 主效应（clustered−shuffled 配对）的数据质量前提只依赖这两个参与配对的
    # 条件。flat 与 clustered-no-exchange 是诊断对照，不进入配对效应计算；它们的
    # 稳态作为独立发现报告（diagnostic_controls），不阻塞主效应判定。
    # 依据：clustered-no-exchange 是无交换（无噪声）的确定性慢混合系统，ESS 判据
    # （24 snapshot 要求 IAT≤6）对其不适用，其慢弛豫正是「交换核是快速达到稳态的
    # 必要条件」的正面证据（见 exchange-kernel-design.md §13）。
    confirmatory_conditions = {"clustered", "shuffled"}
    diagnostic_conditions = {"flat", "clustered-no-exchange"}

    def stationarity_for(conditions: set[str]) -> bool:
        return all(
            bool(row["stationarity_pass"])
            for row in rows
            if str(row["condition"]) in conditions
        )

    stationarity_pass = stationarity_for(confirmatory_conditions)
    diagnostic_stationarity = {
        condition: stationarity_for({condition})
        for condition in sorted(diagnostic_conditions)
    }
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
        "diagnostic_controls": {
            "flat_stationarity_pass": diagnostic_stationarity["flat"],
            "clustered_no_exchange_stationarity_pass": diagnostic_stationarity[
                "clustered-no-exchange"
            ],
            "note": (
                "flat 与 clustered-no-exchange 是诊断对照，不进入 clustered−shuffled "
                "配对计算，其稳态独立报告、不阻塞主效应判定。clustered-no-exchange "
                "20/20 稳态失败源于无交换的确定性慢混合（高自相关 ESS<4 + 地形聚集慢模态），"
                "作为「交换核为稳态必要条件」的证据记录，真正的通道消融机制判定由 E2 承担。"
            ),
        },
        "confirmatory_spatial_family": primary,
        "secondary_wealth_family": wealth,
        "multiplicity": "Holm family-wise correction",
    }
    write_json(output_dir / "paired_effects.json", payload)
    return payload


def aggregate_e1_c4(
    rows: Sequence[Mapping[str, Any]],
    config: Mapping[str, Any],
    output_dir: Path,
    steady_estimand: Mapping[str, Any],
) -> Dict[str, Any]:
    """Analyze the Cycle 4 matched contrast under its separately frozen gates."""
    expected_seeds = {int(seed) for seed in config.get("seeds", [])}
    if len(expected_seeds) < 3:
        raise ValueError("E1-C4 requires at least three distinct seeds")
    by_seed: Dict[int, Dict[str, Mapping[str, Any]]] = defaultdict(dict)
    for row in rows:
        seed = int(row["seed"])
        condition = str(row["condition"])
        if seed not in expected_seeds:
            raise RuntimeError(f"E1-C4 contains undeclared seed {seed}")
        if condition not in {"clustered", "shuffled"}:
            raise RuntimeError(f"E1-C4 contains undeclared condition {condition}")
        if condition in by_seed[seed]:
            raise RuntimeError(f"E1-C4 duplicates {condition} for seed {seed}")
        by_seed[seed][condition] = row
    if set(by_seed) != expected_seeds:
        raise RuntimeError("E1-C4 rows do not contain the exact declared seed set")
    for seed, condition_rows in by_seed.items():
        if set(condition_rows) != {"clustered", "shuffled"}:
            raise RuntimeError(f"E1-C4 seed {seed} lacks a matched condition")

    calibration = load_c4_calibration(config)
    threshold_components = validate_c4_calibration_coverage(
        calibration,
        config.get("scientific_sesoi", {}),
    )
    raw_intervals: Dict[str, Dict[str, float]] = {}
    for metric in C4_EFFECT_METRICS:
        clustered = [
            float(by_seed[seed]["clustered"][metric]) for seed in sorted(by_seed)
        ]
        shuffled = [
            float(by_seed[seed]["shuffled"][metric]) for seed in sorted(by_seed)
        ]
        if not np.all(np.isfinite(clustered)) or not np.all(np.isfinite(shuffled)):
            raise RuntimeError(f"E1-C4 {metric} contains a non-finite value")
        raw_intervals[metric] = paired_bootstrap_mean_difference(
            clustered,
            shuffled,
            seed=int(config.get("analysis_seed", 9173)),
            samples=int(config.get("bootstrap_samples", 10_000)),
        )

    effective_thresholds = {
        metric: values["effective_claim_threshold"]
        for metric, values in threshold_components.items()
    }
    primary_metrics = C4_EFFECT_METRICS[:3]
    primary = apply_holm_and_sesoi(
        {metric: raw_intervals[metric] for metric in primary_metrics},
        effective_thresholds,
        alpha=float(config.get("familywise_alpha", 0.05)),
        metric_for_key={metric: metric for metric in primary_metrics},
    )
    secondary = apply_holm_and_sesoi(
        {"wealth_gini": raw_intervals["wealth_gini"]},
        effective_thresholds,
        alpha=float(config.get("familywise_alpha", 0.05)),
        metric_for_key={"wealth_gini": "wealth_gini"},
    )
    for metric, result in {**primary, **secondary}.items():
        result["threshold_components"] = threshold_components[metric]

    matched_input_pass = bool(
        load_json(output_dir / "matched_input_audit.json").get("pass", False)
    )
    population = int(config.get("population", 0))
    execution_invariants = {
        "wealth_nonnegative": all(
            float(row.get("minimum_wealth_observed", row["minimum_wealth"])) >= -1e-12
            for row in rows
        ),
        "population_preserved": population > 0
        and all(float(row["particle_count"]) == float(population) for row in rows),
        "total_wealth_change_finite": all(
            math.isfinite(float(row["total_wealth_relative_drift"])) for row in rows
        ),
    }
    gate_pass = bool(
        steady_estimand.get("pass", False)
        and matched_input_pass
        and all(execution_invariants.values())
    )
    payload: Dict[str, Any] = {
        "experiment": E1_C4_EXPERIMENT,
        "comparison": "clustered-minus-shuffled",
        "analysis_gate_pass": gate_pass,
        "claim_supported": bool(
            gate_pass
            and any(result["claim_threshold_pass"] for result in primary.values())
        ),
        "valid_null_or_equivalence": bool(
            gate_pass
            and not any(result["claim_threshold_pass"] for result in primary.values())
        ),
        "gates": {
            "v1f_numerical_calibration": True,
            "matched_inputs": matched_input_pass,
            "execution_invariants": all(execution_invariants.values()),
            "tail_stationarity": bool(
                steady_estimand.get("tail_stationarity_valid", False)
            ),
            "adjacent_window_stability": bool(
                steady_estimand.get("adjacent_window_stability_valid", False)
            ),
            "independent_replicate_precision": bool(
                steady_estimand.get("independent_replicate_precision_valid", False)
            ),
        },
        "temporal_ess_diagnostic_pass": bool(
            steady_estimand.get("temporal_ess_diagnostic_valid", False)
        ),
        "execution_invariant_checks": execution_invariants,
        "confirmatory_spatial_family": primary,
        "secondary_wealth_family": secondary,
        "threshold_policy": (
            "Each claim uses max(V1F numerical resolution limit, independently "
            "frozen scientific SESOI)."
        ),
        "multiplicity": (
            "Holm FWER 0.05 across the three primary spatial metrics; wealth Gini "
            "is a separate secondary family."
        ),
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
    # R02: E0 declares which metrics are required (must be finite and produce a
    # dt-convergence bound) versus which are expected to be degenerate on flat
    # terrain (constant-field correlation → undefined). Inf/NaN data corruption
    # is neither and must fail. An empty convergence set must not pass.
    required_metrics = ("occupancy_entropy", "wealth_gini")
    expected_degenerate_metrics = (
        "resource_density_spearman_rho",
        "density_morans_i",
    )
    bounded_metrics = required_metrics + expected_degenerate_metrics
    convergence: Dict[str, float] = {}
    sesoi_diagnostics: Dict[str, Dict[str, float]] = {}
    undefined_degenerate: List[str] = []
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
        if len(half_seeds) != len(set(half_seeds)):
            raise RuntimeError(f"E0 {metric} dt/2 condition has duplicate seeds")
        dt_half = [row.get(metric) for row in half_rows]
        dt_quarter = [row.get(metric) for row in quarter_rows]

        # R02: classify every observed value. Undefined is only tolerated for
        # expected-degenerate metrics; invalid (Inf/NaN corruption) always fails.
        statuses = [metric_status(metric, value) for value in dt_half + dt_quarter]
        if any(status["status"] == "invalid" for status in statuses):
            raise RuntimeError(
                f"E0 metric {metric} contains invalid (non-finite) values"
            )
        if any(status["status"] == "undefined" for status in statuses):
            if metric in expected_degenerate_metrics:
                undefined_degenerate.append(metric)
                continue
            raise RuntimeError(
                f"E0 required metric {metric} is undefined and cannot be calibrated"
            )
        numeric_half = [float(value) for value in dt_half]
        numeric_quarter = [float(value) for value in dt_quarter]
        paired_absolute_differences = np.abs(
            np.asarray(numeric_half, dtype=np.float64)
            - np.asarray(numeric_quarter, dtype=np.float64)
        )
        convergence[metric] = float(np.mean(paired_absolute_differences))
        sesoi_diagnostics[metric] = paired_discretization_sesoi(
            numeric_half,
            numeric_quarter,
            floor=1e-6,
        )

    missing_convergence = sorted(set(required_metrics) - set(convergence))
    if missing_convergence:
        raise RuntimeError(
            f"E0 dt-convergence is missing required metrics: {missing_convergence}"
        )
    if not convergence:
        raise RuntimeError("E0 dt-convergence produced an empty metric set")

    sesoi = {
        metric: diagnostic["threshold"]
        for metric, diagnostic in sesoi_diagnostics.items()
    }
    equal_exchange_variance = max(
        float(row["wealth_variance"]) for row in by_condition["equal-exchange"]
    )
    core_checks = {
        "wealth_conservation": max_abs_drift <= 1e-8,
        "wealth_nonnegative": minimum_wealth >= -1e-12,
        "dt_convergence": all(value <= 0.02 for value in convergence.values()),
        "equal_state_is_absorbing": equal_exchange_variance <= 1e-20,
    }
    stationarity_pass = all(bool(row["stationarity_pass"]) for row in rows)
    precision_pass = precision_valid_for_rows(rows)
    numerics_valid = all(core_checks.values())
    payload = {
        "experiment": "E0-NUMERICS",
        "scope": "flat-terrain-numerics",
        "pass": numerics_valid,
        "core_checks": core_checks,
        "stationarity_pass": stationarity_pass,
        "stationarity_pending": not stationarity_pass,
        # R12: split the gate verdict into explicit, independently-checkable
        # layers instead of a single opaque `pass`.
        "gate_layers": {
            "execution_completed": True,
            "numerics_valid": numerics_valid,
            "stationarity_valid": stationarity_pass,
            "precision_valid": precision_pass,
            "claim_supported": numerics_valid and stationarity_pass and precision_pass,
        },
        "gate_policy": (
            "Cycle 3 E0 gate is passed when the four deterministic numerical "
            "checks (conservation, non-negativity, dt-convergence, equal-state "
            "absorption) all pass. Steady-window stationarity is reported "
            "separately and, in Cycle 3, does not block the E0 calibration gate."
        ),
        "max_absolute_wealth_drift": max_abs_drift,
        "minimum_wealth": minimum_wealth,
        "dt_half_vs_quarter_mean_absolute_change": convergence,
        "equal_exchange_max_wealth_variance": equal_exchange_variance,
        "sesoi_frozen_before_confirmatory_analysis": sesoi,
        "sesoi_diagnostics": sesoi_diagnostics,
        "undefined_degenerate_metrics": undefined_degenerate,
        "required_metrics": list(required_metrics),
        "expected_degenerate_metrics": list(expected_degenerate_metrics),
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


def aggregate_b0(
    rows: Sequence[Mapping[str, Any]],
    config: Mapping[str, Any],
    output_dir: Path,
) -> Dict[str, Any]:
    expected_population = int(config["population"])
    checks = {
        "all_runs_stationary": all(bool(row["stationarity_pass"]) for row in rows),
        "wealth_nonnegative": min(float(row["minimum_wealth"]) for row in rows)
        >= -1e-12,
        "population_constant": all(
            int(round(float(row["particle_count"]))) == expected_population
            for row in rows
        ),
        "metrics_finite": all(
            math.isfinite(float(row[metric]))
            for row in rows
            for metric in (
                "resource_density_spearman_rho",
                "density_morans_i",
                "occupancy_entropy",
                "wealth_gini",
                "wealth_variance",
            )
        ),
    }
    payload = {
        "experiment": "B0-DYNAMICS-PILOT",
        "pass": all(checks.values()),
        "checks": checks,
        "stationarity_metrics": list(
            stationary_metrics_for_experiment("B0-DYNAMICS-PILOT")
        ),
        "runs": len(rows),
        "evidence_role": "runtime and outcome-blind dynamics health only",
        "prohibited_use": (
            "This pilot has no shuffled comparison and cannot support C2-C4 or "
            "estimate a landscape effect."
        ),
    }
    write_json(output_dir / "pilot_health.json", payload)
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
    stationary_metrics = stationary_metrics_for_experiment(experiment)
    rows = [
        mean_metrics_for_run(
            spec,
            bounds=config.get("bounds", [0.0, 100.0, 0.0, 100.0]),
            steady_snapshots=int(config.get("steady_snapshots", 5)),
            stationarity_max_drift=float(
                config.get("stationarity_max_normalized_drift", 0.1)
            ),
            stationarity_min_ess=float(config.get("stationarity_min_ess", 3.0)),
            stationary_metrics=stationary_metrics,
            stationarity_reversal_span_sigma=float(
                config.get("stationarity_reversal_span_sigma", 1.0)
            ),
        )
        for spec in run_specs
    ]
    write_metrics_csv(output_dir / "replicate_metrics.csv", rows)
    # R01: stationarity report carries per-metric status/reason so undefined
    # (constant-field) and invalid (corruption) metrics are distinguishable
    # from genuine drift, and no raw NaN/Inf reaches JSON.
    stationarity_valid = all(bool(row["stationarity_pass"]) for row in rows)
    precision_valid = precision_valid_for_rows(rows)
    stationarity_payload = {
        "experiment": experiment,
        "pass": stationarity_valid,
        "stationarity_valid": stationarity_valid,
        "precision_valid": precision_valid,
        "runs": [
            {
                "run_id": row["run_id"],
                "pass": row["stationarity_pass"],
                "metrics": row["stationarity_diagnostics"],
                "metric_statuses": {
                    name: {
                        "value": status["value"],
                        "status": status["status"],
                        "reason": status["reason"],
                    }
                    for name, status in row["metric_statuses"].items()
                },
            }
            for row in rows
        ],
    }
    if experiment == E1_C4_EXPERIMENT:
        stationarity_payload["gate_role"] = (
            "per_run_diagnostic_only; the confirmatory gate is steady_estimand_report.json"
        )
    write_json(output_dir / "stationarity_report.json", stationarity_payload)
    if experiment == "E0-NUMERICS":
        calibration = aggregate_e0(rows, output_dir)
        tracked_calibration = config.get("calibration_result")
        if not isinstance(tracked_calibration, str) or not tracked_calibration:
            raise ValueError("E0 requires calibration_result for tracked provenance")
        write_json(project_path(tracked_calibration), calibration)
    elif experiment == "B0-DYNAMICS-PILOT":
        aggregate_b0(rows, config, output_dir)
    elif experiment == "E1-MATCHED-LANDSCAPES":
        aggregate_e1(rows, config, output_dir)
    elif experiment == E1_C4_EXPERIMENT:
        steady_estimand = aggregate_e1_c4_steady_estimand(
            run_specs, config, output_dir
        )
        aggregate_e1_c4(rows, config, output_dir, steady_estimand)
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

    if args.experiment not in {"E0-NUMERICS", "B0-DYNAMICS-PILOT"}:
        calibration = load_confirmatory_calibration(args.experiment, config)
        # R03: block before any expensive run if the calibration cannot cover
        # this experiment's confirmatory metrics (e.g. flat-terrain calibration
        # lacks spatial-correlation SESOI).
        if args.experiment == E1_C4_EXPERIMENT:
            validate_c4_calibration_coverage(
                calibration,
                config.get("scientific_sesoi", {}),
                confirmatory_metrics_for_experiment(args.experiment),
            )
        else:
            validate_calibration_coverage(
                calibration,
                confirmatory_metrics_for_experiment(args.experiment),
            )

    execution_summary: Dict[str, Any] = {
        "executed": 0,
        "skipped_completed": 0,
        "completed_run_ids": [],
        "elapsed_seconds_executed": 0.0,
    }
    if not args.analyze_only:
        binary = project_path(config["binary"], must_exist=True)
        execution_summary = execute_runs(
            run_specs,
            binary,
            timeout_seconds=int(config.get("per_run_timeout_seconds", 3600)),
            omp_threads=int(config.get("omp_threads", 8)),
            parallel=int(config.get("parallel", 1)),
        )
    else:
        # --analyze-only 重分析：从已有的 summary result 保留上次执行统计
        # （executed / reused / elapsed），避免重分析时丢失 execute provenance。
        prior_summary = config.get("summary_result")
        if prior_summary:
            prior_path = project_path(str(prior_summary))
            if prior_path.is_file():
                prior = load_json(prior_path)
                execution_summary["executed"] = int(
                    prior.get("runs_executed_this_invocation", 0)
                )
                execution_summary["skipped_completed"] = int(
                    prior.get("runs_reused_from_completion_markers", 0)
                )
                execution_summary["elapsed_seconds_executed"] = float(
                    prior.get("elapsed_seconds_executed_this_invocation", 0.0)
                )

    rows = analyze_runs(args.experiment, config, output_dir, run_specs)
    job_pass = True
    if args.experiment == "E0-NUMERICS":
        job_pass = bool(load_json(output_dir / "numerical_calibration.json")["pass"])
    elif args.experiment == "B0-DYNAMICS-PILOT":
        job_pass = bool(load_json(output_dir / "pilot_health.json")["pass"])
    elif args.experiment == "E1-MATCHED-LANDSCAPES":
        job_pass = bool(load_json(output_dir / "paired_effects.json")["analysis_gate_pass"])
    elif args.experiment == E1_C4_EXPERIMENT:
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
        "elapsed_seconds_executed_this_invocation": execution_summary[
            "elapsed_seconds_executed"
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
