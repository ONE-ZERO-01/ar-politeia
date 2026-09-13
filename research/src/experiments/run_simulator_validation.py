#!/usr/bin/env python3
"""Build and validate the remediated Politeia simulator on umi.

This is a non-evidentiary implementation validation. It does not execute a
landscape experiment or produce scientific results.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[3]
SIMULATOR_SOURCE = PROJECT_ROOT / "research/src/experiments/politeia"


def project_path(value: str, *, create: bool = False) -> Path:
    path = (PROJECT_ROOT / value).resolve()
    if path != PROJECT_ROOT and PROJECT_ROOT not in path.parents:
        raise ValueError(f"path escapes project root: {value}")
    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path


def run_logged(command: Sequence[str], log_path: Path) -> dict[str, Any]:
    started = time.monotonic()
    with log_path.open("w", encoding="utf-8") as log:
        completed = subprocess.run(
            list(command),
            cwd=PROJECT_ROOT,
            stdout=log,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
        )
    return {
        "command": list(command),
        "returncode": completed.returncode,
        "elapsed_seconds": time.monotonic() - started,
        "log": log_path.name,
    }


def command_output(command: Sequence[str]) -> str:
    return subprocess.check_output(
        list(command), cwd=PROJECT_ROOT, text=True, stderr=subprocess.STDOUT
    ).strip()


def validate_build(
    output_dir: Path, *, openmp: bool, build_jobs: int
) -> dict[str, Any]:
    label = "on" if openmp else "off"
    build_dir = output_dir / f"build-{label}"
    if build_dir.exists():
        shutil.rmtree(build_dir)

    configure = run_logged(
        [
            "cmake",
            "-S",
            str(SIMULATOR_SOURCE),
            "-B",
            str(build_dir),
            "-DCMAKE_BUILD_TYPE=Release",
            "-DPOLITEIA_BUILD_TESTS=ON",
            f"-DPOLITEIA_USE_OPENMP={'ON' if openmp else 'OFF'}",
            "-DPOLITEIA_USE_MPI=OFF",
        ],
        output_dir / f"configure-{label}.log",
    )
    build = {"returncode": None, "log": f"build-{label}.log"}
    ctest = {"returncode": None, "log": f"ctest-{label}.log"}
    if configure["returncode"] == 0:
        build = run_logged(
            ["cmake", "--build", str(build_dir), "--parallel", str(build_jobs)],
            output_dir / f"build-{label}.log",
        )
    if build["returncode"] == 0:
        ctest = run_logged(
            ["ctest", "--test-dir", str(build_dir), "--output-on-failure"],
            output_dir / f"ctest-{label}.log",
        )
    return {
        "openmp": openmp,
        "configure": configure,
        "build": build,
        "ctest": ctest,
        "pass": all(
            stage.get("returncode") == 0 for stage in (configure, build, ctest)
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    config_path = project_path(args.config)
    output_dir = project_path(args.output_dir, create=True)
    config = json.loads(config_path.read_text(encoding="utf-8"))
    experiment_id = str(config.get("experiment_id", ""))
    if experiment_id not in {
        "V0-SIMULATOR-TESTS-C4",
        "V0B-SIMULATOR-TESTS-C4",
        "V0C-SIMULATOR-TESTS-C4",
    }:
        raise ValueError("unexpected experiment_id")
    if platform.node() != "umi":
        raise RuntimeError("simulator validation must run on host umi")

    build_jobs = int(config.get("build_jobs", 4))
    if not 1 <= build_jobs <= 16:
        raise ValueError("build_jobs must be between 1 and 16")

    environment = {
        "host": platform.node(),
        "platform": platform.platform(),
        "python": sys.version.split()[0],
        "cmake": command_output(["cmake", "--version"]).splitlines()[0],
        "compiler": command_output(["g++", "--version"]).splitlines()[0],
        "source_commit": command_output(["git", "rev-parse", "HEAD"]),
        "working_tree_clean": not bool(command_output(["git", "status", "--porcelain"])),
        "cpu_count": os.cpu_count(),
    }
    (output_dir / "environment.json").write_text(
        json.dumps(environment, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    pytest_result = run_logged(
        [sys.executable, "-m", "pytest", "-q"], output_dir / "pytest.log"
    )
    builds = [
        validate_build(output_dir, openmp=False, build_jobs=build_jobs),
        validate_build(output_dir, openmp=True, build_jobs=build_jobs),
    ]
    passed = pytest_result["returncode"] == 0 and all(
        item["pass"] for item in builds
    )
    result = {
        "experiment": experiment_id,
        "status": "completed" if passed else "failed",
        "pass": passed,
        "non_evidentiary": True,
        "evidence_boundary": "Implementation validation only; no scientific claim or numerical calibration.",
        "environment": environment,
        "pytest": pytest_result,
        "builds": builds,
    }
    (output_dir / "result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
