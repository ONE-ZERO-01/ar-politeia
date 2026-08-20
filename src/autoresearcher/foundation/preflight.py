"""preflight — reproducibility checks before submitting an experiment.

Usage:
    python -m autoresearcher.foundation.preflight \\
        --exp-dir results/E1/ \\
        --priority P0

Checks (all must pass for P0; P1/P2 allow seed_waiver):
    1. commit_id is present and not "dirty".
    2. env_snapshot file exists and is non-empty.
    3. Config file (any .yaml/.json in exp_dir) exists.
    4. seeds are declared; P0 requires >= 3 unless seed_waiver is recorded.
    5. Output artifact paths are declared.
    6. Data checksums are recorded (optional warning).

Output: JSON on stdout. Exit code 0 = pass, 1 = blocked.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple


def _read_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _resolve_source_file(source_root: Path, relative: str) -> Tuple[Path, str]:
    path = (source_root / relative).resolve()
    if source_root != path and source_root not in path.parents:
        return path, "path escapes source root"
    if not path.is_file():
        return path, "file is missing"
    if path.stat().st_size == 0:
        return path, "file is empty"
    return path, ""


def _check_computational_strategy(
    experiment: Dict[str, Any],
) -> Tuple[bool, str]:
    strategy = experiment.get("computational_strategy")
    if strategy is None:
        return True, ""
    if not isinstance(strategy, dict):
        return False, "computational_strategy must be an object"

    errors: List[str] = []
    approach = strategy.get("approach")
    if not isinstance(approach, str) or not approach.strip():
        errors.append("approach is required")

    evidence_role = strategy.get("evidence_role")
    if not isinstance(evidence_role, str) or not evidence_role.strip():
        errors.append("evidence_role is required")

    boundary = strategy.get("evidence_boundary")
    if not isinstance(boundary, str) or not boundary.strip():
        errors.append("evidence_boundary is required")

    supports_core = strategy.get("supports_core_claim", False)
    if not isinstance(supports_core, bool):
        errors.append("supports_core_claim must be boolean")
        supports_core = False

    screening_roles = {
        "screening",
        "approximate",
        "surrogate",
        "candidate_selection_only",
    }
    needs_validation = supports_core and str(evidence_role).lower() in screening_roles
    if strategy.get("reference_validation_required") is True:
        needs_validation = True

    if needs_validation:
        if not isinstance(strategy.get("reference_method"), str) or not strategy[
            "reference_method"
        ].strip():
            errors.append("reference_method is required for core-claim validation")
        validation_points = strategy.get("validation_points")
        if not isinstance(validation_points, list) or not validation_points or not all(
            isinstance(item, str) and item.strip() for item in validation_points
        ):
            errors.append("validation_points are required for core-claim validation")
        agreement = strategy.get("agreement")
        if not isinstance(agreement, dict) or not agreement:
            errors.append("agreement is required for core-claim validation")
        validation_artifact = strategy.get("validation_artifact")
        artifacts = experiment.get("artifacts", [])
        if not isinstance(validation_artifact, str) or not validation_artifact.strip():
            errors.append("validation_artifact is required for core-claim validation")
        elif validation_artifact not in artifacts:
            errors.append("validation_artifact must also appear in artifacts")

    return not errors, "; ".join(errors)


def check_experiment(
    experiment: Dict[str, Any],
    source_root: Path,
    source_commit: str = "",
) -> Dict[str, Any]:
    """Validate one local experiment and bind its reproducibility inputs."""
    source_root = source_root.resolve()
    failed: List[str] = []
    details: List[Dict[str, Any]] = []
    bindings: Dict[str, Any] = {}

    def record(name: str, passed: bool, detail: str = "") -> None:
        item: Dict[str, Any] = {"check": name, "passed": passed}
        if detail:
            item["detail"] = detail
        details.append(item)
        if not passed:
            failed.append(name)

    command = experiment.get("command")
    record(
        "command",
        isinstance(command, list)
        and bool(command)
        and all(isinstance(item, str) and item for item in command),
        "command must be a non-empty JSON string array",
    )

    commit_id = str(experiment.get("commit_id", "")).strip()
    commit_ok = bool(commit_id) and commit_id != "dirty"
    commit_detail = "commit_id is missing or dirty"
    if commit_ok and source_commit and commit_id != source_commit:
        commit_ok = False
        commit_detail = (
            f"commit_id {commit_id!r} does not match source HEAD {source_commit!r}"
        )
    record("commit_id", commit_ok, "" if commit_ok else commit_detail)

    for field, sha_field in (
        ("config", "config_sha256"),
        ("env_snapshot", "env_sha256"),
    ):
        relative = experiment.get(field)
        if not isinstance(relative, str) or not relative:
            record(field, False, f"{field} must name a source file")
            continue
        path, error = _resolve_source_file(source_root, relative)
        if error:
            record(field, False, f"{relative}: {error}")
            continue
        actual_sha = _sha256(path)
        declared_sha = experiment.get(sha_field)
        if declared_sha and declared_sha != actual_sha:
            record(field, False, f"{sha_field} does not match {relative}")
            continue
        bindings[sha_field] = actual_sha
        bindings[f"{field}_path"] = relative
        record(field, True)

    seeds = experiment.get("seeds")
    seeds_ok = isinstance(seeds, list) and bool(seeds)
    if (
        seeds_ok
        and experiment.get("priority") == "P0"
        and len(seeds) < 3
        and not experiment.get("seed_waiver")
    ):
        seeds_ok = False
    record(
        "seeds",
        seeds_ok,
        "seeds are required; P0 requires at least three seeds or a seed_waiver",
    )

    checksums = experiment.get("data_checksums")
    checksums_ok = isinstance(checksums, dict) and bool(checksums)
    if checksums_ok:
        checksums_ok = all(
            isinstance(key, str)
            and bool(key)
            and isinstance(value, str)
            and bool(value.strip())
            for key, value in checksums.items()
        )
    record(
        "data_checksums",
        checksums_ok,
        "data_checksums must be a non-empty mapping",
    )

    artifacts = experiment.get("artifacts")
    artifacts_ok = isinstance(artifacts, list) and bool(artifacts)
    if artifacts_ok:
        for relative in artifacts:
            if not isinstance(relative, str) or not relative:
                artifacts_ok = False
                break
            path = (Path("workspace") / relative).resolve()
            workspace = Path("workspace").resolve()
            if workspace != path and workspace not in path.parents:
                artifacts_ok = False
                break
    record(
        "artifacts",
        artifacts_ok,
        "artifacts must be non-empty paths contained in the job workspace",
    )

    timeout = experiment.get("timeout_seconds", 3600)
    record(
        "timeout_seconds",
        isinstance(timeout, (int, float)) and 0 < timeout <= 7 * 24 * 3600,
        "timeout_seconds must be between 1 second and 7 days",
    )

    if "computational_strategy" in experiment:
        strategy_ok, strategy_detail = _check_computational_strategy(experiment)
        record(
            "computational_strategy",
            strategy_ok,
            strategy_detail,
        )

    return {
        "status": "ok" if not failed else "blocked",
        "experiment_id": experiment.get("id"),
        "failed": failed,
        "details": details,
        "bindings": bindings,
    }


def _check_commit(exp_dir: Path) -> Tuple[bool, str]:
    """Read commit_id from a commit.txt in exp_dir, or try git."""
    commit_file = exp_dir / "commit.txt"
    if commit_file.is_file():
        commit_id = commit_file.read_text(encoding="utf-8").strip()
    else:
        commit_id = ""
    if not commit_id:
        return False, "commit_id is missing (write commit.txt or use --commit-id)"
    if commit_id == "dirty":
        return False, "commit_id cannot be 'dirty'"
    return True, ""


def _check_env(exp_dir: Path) -> Tuple[bool, str]:
    candidates = sorted(exp_dir.glob("env.*"))
    for path in candidates:
        if path.stat().st_size > 0:
            return True, ""
    if candidates:
        return False, "env_snapshot file exists but is empty"
    return False, "env_snapshot file is missing (expected env.txt or env.lock)"


def _check_config(exp_dir: Path) -> Tuple[bool, str]:
    for suffix in (".yaml", ".yml", ".json"):
        if any(exp_dir.glob(f"*{suffix}")):
            return True, ""
    return False, "config file is missing (expected *.yaml/*.json in exp_dir)"


def _check_seeds(exp_dir: Path, priority: str) -> Tuple[bool, str]:
    seeds_file = exp_dir / "seeds.txt"
    waiver = exp_dir / "seed_waiver.txt"
    if not seeds_file.is_file():
        if waiver.is_file() and waiver.stat().st_size > 0:
            return True, ""
        return False, "seeds.txt is missing"
    seed_text = seeds_file.read_text(encoding="utf-8").strip()
    seeds = [s.strip() for s in seed_text.replace(",", " ").split() if s.strip()]
    if not seeds:
        return False, "seeds.txt is empty"
    if priority == "P0" and len(seeds) < 3:
        if waiver.is_file() and waiver.stat().st_size > 0:
            return True, ""
        return False, f"P0 requires at least 3 seeds (found {len(seeds)}); add seed_waiver.txt to bypass"
    return True, ""


def _check_artifacts(exp_dir: Path) -> Tuple[bool, str]:
    manifest = exp_dir / "outputs.txt"
    if manifest.is_file() and manifest.stat().st_size > 0:
        return True, ""
    return False, "outputs.txt is missing or empty (expected list of artifact paths)"


def _check_data_checksums(exp_dir: Path) -> Tuple[bool, str]:
    checksum_file = exp_dir / "data_checksums.txt"
    if checksum_file.is_file() and checksum_file.stat().st_size > 0:
        return True, ""
    return False, "data_checksums.txt is missing or empty"


def _check_computational_strategy_file(exp_dir: Path) -> Tuple[bool, str]:
    path = exp_dir / "computational_strategy.json"
    if not path.exists():
        return True, ""
    try:
        strategy = _read_json(path)
    except Exception as exc:
        return False, f"invalid computational_strategy.json: {exc}"
    outputs_path = exp_dir / "outputs.txt"
    artifacts = []
    if outputs_path.exists():
        artifacts = [
            line.strip()
            for line in outputs_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    return _check_computational_strategy(
        {
            "computational_strategy": strategy,
            "artifacts": artifacts,
        }
    )


def _check_finite(path: Path) -> Tuple[bool, str]:
    """Verify JSON files in exp_dir don't contain NaN/Inf."""
    for json_file in sorted(path.glob("*.json")):
        try:
            data = _read_json(json_file)
        except Exception as exc:
            return False, f"invalid JSON in {json_file.name}: {exc}"
        if not _is_finite(data):
            return False, f"{json_file.name} contains NaN or Inf"
    return True, ""


def _is_finite(value: Any) -> bool:
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return True
    if isinstance(value, (int, float)):
        return math.isfinite(value)
    if isinstance(value, list):
        return all(_is_finite(item) for item in value)
    if isinstance(value, dict):
        return all(_is_finite(item) for item in value.values())
    return True


def run(exp_dir: Path, priority: str) -> Dict[str, Any]:
    if not exp_dir.is_dir():
        return {"status": "blocked", "checks": 0, "passed": 0, "failed": ["exp_dir"], "warnings": ["directory does not exist"], "details": []}

    checks: List[Dict[str, Any]] = []
    failed: List[str] = []
    warnings: List[str] = []

    for name, msg, func, *args in [
        ("commit_id",   "commit_id is present and not dirty",   _check_commit,       exp_dir),
        ("env_snapshot","env_snapshot file exists and non-empty", _check_env,         exp_dir),
        ("config",      "config file exists",                    _check_config,       exp_dir),
        ("seeds",       "seeds declared (P0≥3 or waiver)",       _check_seeds,        exp_dir, priority),
        ("artifacts",   "output artifact paths declared",        _check_artifacts,    exp_dir),
        ("finite_json", "JSON configs contain no NaN/Inf",       _check_finite,       exp_dir),
    ]:
        passed, detail = func(*args)
        result = {"check": name, "description": msg, "passed": passed}
        if not passed:
            result["detail"] = detail
            failed.append(name)
        checks.append(result)

    dc_passed, dc_detail = _check_data_checksums(exp_dir)
    checks.append({
        "check": "data_checksums",
        "description": "data checksums recorded",
        "passed": dc_passed,
        **({"detail": dc_detail} if dc_detail else {}),
    })
    if not dc_passed:
        failed.append("data_checksums")

    strategy_path = exp_dir / "computational_strategy.json"
    if strategy_path.exists():
        strategy_passed, strategy_detail = _check_computational_strategy_file(
            exp_dir
        )
        checks.append({
            "check": "computational_strategy",
            "description": "performance or screening strategy preserves reference validation",
            "passed": strategy_passed,
            **({"detail": strategy_detail} if strategy_detail else {}),
        })
        if not strategy_passed:
            failed.append("computational_strategy")

    blocked = bool(failed)
    return {
        "status": "blocked" if blocked else "ok",
        "checks": len(checks),
        "passed": len(checks) - len(failed),
        "failed": failed,
        "warnings": warnings,
        "details": checks,
    }


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description="Reproducibility preflight check")
    parser.add_argument("--exp-dir", required=True, help="Experiment record directory")
    parser.add_argument("--priority", default="P0", choices=["P0", "P1", "P2"])
    parser.add_argument("--output", help="Write result to file instead of stdout")
    args = parser.parse_args(argv)
    exp_dir = Path(args.exp_dir).resolve()
    if not exp_dir.is_dir():
        result = {"status": "blocked", "failed": ["exp_dir"], "details": [], "warnings": [], "checks": 0}
    else:
        result = run(exp_dir, args.priority)
    payload = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(payload + "\n", encoding="utf-8")
    else:
        print(payload)
    if result["status"] == "blocked":
        sys.exit(1)


if __name__ == "__main__":
    main()
