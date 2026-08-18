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
import os
import socket
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Sequence

import numpy as np

from landscape_study import (
    audit_matched_landscapes,
    make_matched_landscapes,
    paired_bootstrap_mean_difference,
    read_snapshot_csv,
    sha256_file,
    snapshot_metrics,
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


def prepare_inputs(
    experiment: str, config: Mapping[str, Any], output_dir: Path
) -> List[Dict[str, Any]]:
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
        cellsize = (bounds[1] - bounds[0]) / shape[1]
        for name, field in fields.items():
            grid_path = seed_dir / f"{name}.asc"
            write_esri_ascii(
                grid_path,
                field,
                xllcorner=bounds[0],
                yllcorner=bounds[2],
                cellsize=cellsize,
            )
            resource_path = seed_dir / f"{name}-resource.npy"
            np.save(resource_path, field, allow_pickle=False)
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
                write_initial_conditions(
                    ic_path,
                    population,
                    seed,
                    bounds=bounds,
                    mean_wealth=float(config.get("mean_wealth", 5.0)),
                    wealth_log_sigma=float(condition.get("wealth_log_sigma", 0.01)),
                )

            cpp_values = common_cpp_config(config)
            dt = float(condition.get("dt", config.get("dt", 0.01)))
            if "total_time" in config:
                total_steps = int(round(float(config["total_time"]) / dt))
                if total_steps < 1:
                    raise ValueError("total_time/dt must yield at least one step")
                cpp_values["total_steps"] = total_steps
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
                }
            )

    audit_payload = {
        "experiment": experiment,
        "pass": all(item["pass"] for item in matching_audits),
        "audits": matching_audits,
    }
    write_json(output_dir / "matched_input_audit.json", audit_payload)
    write_json(output_dir / "run_specs.json", {"runs": run_specs})
    return run_specs


def execute_runs(
    run_specs: Sequence[Mapping[str, Any]],
    binary: Path,
    *,
    timeout_seconds: int,
) -> None:
    if not binary.is_file() or not os.access(binary, os.X_OK):
        raise FileNotFoundError(f"Politeia binary is missing or not executable: {binary}")
    for spec in run_specs:
        run_dir = project_path(spec["run_dir"])
        log_path = run_dir / "run.log"
        config_path = project_path(spec["cpp_config"], must_exist=True)
        with log_path.open("w", encoding="utf-8") as log:
            completed = subprocess.run(
                [str(binary), str(config_path)],
                cwd=PROJECT_ROOT,
                stdout=log,
                stderr=subprocess.STDOUT,
                timeout=timeout_seconds,
                check=False,
                text=True,
            )
        if completed.returncode != 0:
            raise RuntimeError(
                f"run {spec['run_id']} failed with exit code {completed.returncode}; see {log_path}"
            )


def mean_metrics_for_run(
    spec: Mapping[str, Any],
    *,
    bounds: Sequence[float],
    steady_snapshots: int,
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
    return {**dict(spec), **means, "snapshots_used": len(selected)}


def write_metrics_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    if not rows:
        raise ValueError("no metrics to write")
    fieldnames: List[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def aggregate_e1(rows: Sequence[Mapping[str, Any]], output_dir: Path) -> None:
    metrics = (
        "resource_density_spearman_rho",
        "density_morans_i",
        "occupancy_entropy",
        "wealth_gini",
    )
    by_seed = defaultdict(dict)
    for row in rows:
        by_seed[int(row["seed"])][str(row["condition"])] = row
    payload: Dict[str, Any] = {"comparison": "clustered-minus-shuffled", "metrics": {}}
    for metric in metrics:
        clustered = [by_seed[seed]["clustered"][metric] for seed in sorted(by_seed)]
        shuffled = [by_seed[seed]["shuffled"][metric] for seed in sorted(by_seed)]
        payload["metrics"][metric] = paired_bootstrap_mean_difference(
            clustered, shuffled, seed=9173
        )
    write_json(output_dir / "paired_effects.json", payload)


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
    convergence: Dict[str, float] = {}
    for metric in ("wealth_gini", "wealth_variance"):
        dt_half = float(np.mean([row[metric] for row in by_condition["perturbed-dt-0.5"]]))
        dt_quarter = float(
            np.mean([row[metric] for row in by_condition["perturbed-dt-0.25"]])
        )
        convergence[metric] = abs(dt_half - dt_quarter) / max(
            abs(dt_quarter), 1e-12
        )

    calibration_rows = by_condition["perturbed-dt-1"]
    sesoi = {
        metric: max(
            2.0 * float(np.std([row[metric] for row in calibration_rows], ddof=1)),
            1e-6,
        )
        for metric in (
            "resource_density_spearman_rho",
            "density_morans_i",
            "occupancy_entropy",
            "wealth_gini",
        )
    }
    equal_exchange_variance = max(
        float(row["wealth_variance"]) for row in by_condition["equal-exchange"]
    )
    checks = {
        "wealth_conservation": max_abs_drift <= 1e-8,
        "wealth_nonnegative": minimum_wealth >= -1e-12,
        "dt_convergence": max(convergence.values()) <= 0.02,
        "equal_state_is_absorbing": equal_exchange_variance <= 1e-20,
    }
    payload = {
        "experiment": "E0-NUMERICS",
        "pass": all(checks.values()),
        "checks": checks,
        "max_absolute_wealth_drift": max_abs_drift,
        "minimum_wealth": minimum_wealth,
        "dt_half_vs_quarter_relative_change": convergence,
        "equal_exchange_max_wealth_variance": equal_exchange_variance,
        "sesoi_frozen_before_confirmatory_analysis": sesoi,
        "interpretation_boundary": (
            "The equal-state check diagnoses the deterministic exchange kernel's "
            "absorbing state; it is not evidence for a Boltzmann-Gibbs wealth law."
        ),
    }
    write_json(output_dir / "numerical_calibration.json", payload)
    return payload


def aggregate_e2(rows: Sequence[Mapping[str, Any]], output_dir: Path) -> None:
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
    payload: Dict[str, Any] = {"design": "movement-by-production-2x2", "metrics": {}}
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
        payload["metrics"][metric] = {}
        for effect in ("movement", "production", "interaction"):
            estimates = [
                float(np.mean(per_seed[seed][effect])) for seed in sorted(per_seed)
            ]
            payload["metrics"][metric][effect] = paired_bootstrap_mean_difference(
                estimates, np.zeros(len(estimates)), seed=9173
            )
    write_json(output_dir / "channel_effects.json", payload)


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
        )
        for spec in run_specs
    ]
    write_metrics_csv(output_dir / "replicate_metrics.csv", rows)
    if experiment == "E0-NUMERICS":
        aggregate_e0(rows, output_dir)
    elif experiment == "E1-MATCHED-LANDSCAPES":
        aggregate_e1(rows, output_dir)
    elif experiment == "E2-CHANNEL-ABLATION":
        aggregate_e2(rows, output_dir)
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

    specs_path = output_dir / "run_specs.json"
    if args.analyze_only:
        run_specs = load_json(specs_path)["runs"]
    else:
        run_specs = prepare_inputs(args.experiment, config, output_dir)

    if args.prepare_only:
        return 0

    if not args.analyze_only:
        binary = project_path(config["binary"], must_exist=True)
        execute_runs(
            run_specs,
            binary,
            timeout_seconds=int(config.get("per_run_timeout_seconds", 3600)),
        )

    rows = analyze_runs(args.experiment, config, output_dir, run_specs)
    job_pass = True
    if args.experiment == "E0-NUMERICS":
        job_pass = bool(load_json(output_dir / "numerical_calibration.json")["pass"])
    result = {
        "experiment": args.experiment,
        "status": "completed",
        "pass": job_pass,
        "runs_completed": len(rows),
        "config_sha256": sha256_file(config_path),
        "evidence_boundary": "Synthetic generative mechanism only; no historical-state claim.",
        "artifacts": sorted(
            relative_to_project(path)
            for path in output_dir.iterdir()
            if path.is_file()
        ),
    }
    write_json(output_dir / "result.json", result)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise
