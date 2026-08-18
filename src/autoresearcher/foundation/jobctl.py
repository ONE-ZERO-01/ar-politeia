"""jobctl — idempotent job submission, status queries, and crash recovery.

Usage:
    # Submit (idempotent — same config_hash won't restart)
    python -m autoresearcher.foundation.jobctl submit \\
        --exp-id E1 \\
        --command "python run.py" \\
        --config resources/E1/config.yaml \\
        --commit-id abc1234 \\
        --seeds 11,23,37 \\
        --env resources/E1/env.txt

    # Query status
    python -m autoresearcher.foundation.jobctl status --exp-id E1

    # Reconcile after crash
    python -m autoresearcher.foundation.jobctl reconcile --exp-id E1

Output: JSON on stdout. Exit code 0 = success. Non-zero = error.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shlex
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


DEFAULT_JOBS_DIR = Path(".autoresearcher/jobs")


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _config_hash(params: Dict[str, Any]) -> str:
    stable = json.dumps(
        {k: v for k, v in sorted(params.items())},
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(stable.encode("utf-8")).hexdigest()


def _write_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    # atomic write via temp file + rename
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(str(tmp), str(path))


def _read_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


# ── submit ──────────────────────────────────────────────────────────


def submit(
    jobs_dir: Path,
    exp_id: str,
    command: List[str],
    config_path: str,
    commit_id: str,
    seeds: List[int],
    env_path: str,
    artifacts: Optional[List[str]] = None,
    cwd: Optional[str] = None,
    timeout_seconds: int = 3600,
) -> Dict[str, Any]:
    job_dir = jobs_dir / exp_id
    handle_path = job_dir / "handle.json"
    config_file = Path(config_path).expanduser().resolve()
    env_file = Path(env_path).expanduser().resolve()
    validation_errors = []
    if not command or not all(isinstance(item, str) and item for item in command):
        validation_errors.append("command must be a non-empty argument list")
    if not config_file.is_file() or config_file.stat().st_size == 0:
        validation_errors.append("config file is missing or empty")
    if not env_file.is_file() or env_file.stat().st_size == 0:
        validation_errors.append("environment snapshot is missing or empty")
    if not commit_id or commit_id == "dirty":
        validation_errors.append("commit_id is missing or dirty")
    if not seeds:
        validation_errors.append("at least one seed is required")
    if validation_errors:
        return {
            "status": "blocked",
            "exp_id": exp_id,
            "errors": validation_errors,
        }

    params = {
        "exp_id": exp_id,
        "command": command,
        "config_path": str(config_file),
        "config_sha256": _sha256(config_file),
        "commit_id": commit_id,
        "seeds": seeds,
        "env_path": str(env_file),
        "env_sha256": _sha256(env_file),
        "artifacts": artifacts or [],
        "cwd": cwd or os.getcwd(),
        "timeout_seconds": timeout_seconds,
    }
    ch = _config_hash(params)

    if handle_path.exists():
        handle = _read_json(handle_path)
        existing = handle.get("config_hash")
        if existing == ch:
            return {
                "status": "already_submitted",
                "exp_id": exp_id,
                "config_hash": ch,
                "handle": str(handle_path),
                "job_status": handle.get("status"),
            }
        if existing and existing != ch:
            return {
                "status": "config_changed",
                "exp_id": exp_id,
                "old_hash": existing,
                "new_hash": ch,
                "detail": "Config hash differs from previous submission. "
                          "Archive the old job_dir or use a new exp_id to proceed.",
            }

    job_dir.mkdir(parents=True, exist_ok=True)

    # Write intent record (先落盘后行动)
    intent = {
        "exp_id": exp_id,
        "config_hash": ch,
        "command": command,
        "config_path": params["config_path"],
        "config_sha256": params["config_sha256"],
        "commit_id": commit_id,
        "seeds": seeds,
        "env_path": params["env_path"],
        "env_sha256": params["env_sha256"],
        "artifacts": artifacts or [],
        "cwd": cwd or os.getcwd(),
        "timeout_seconds": timeout_seconds,
        "status": "INTENT",
        "pid": None,
        "submitted_at": _now(),
    }
    _write_json(handle_path, intent)

    spec_path = job_dir / "spec.json"
    _write_json(spec_path, params)

    # Start a durable worker that records the exit code and artifact state.
    stdout_path = job_dir / "stdout.log"
    stderr_path = job_dir / "stderr.log"
    env = os.environ.copy()
    env["COMMIT_ID"] = commit_id
    env["SEEDS"] = ",".join(str(s) for s in seeds)
    with stdout_path.open("ab") as stdout_fp, stderr_path.open("ab") as stderr_fp:
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "autoresearcher.foundation.jobctl",
                "--jobs-dir",
                str(jobs_dir),
                "_worker",
                "--exp-id",
                exp_id,
            ],
            stdout=stdout_fp,
            stderr=stderr_fp,
            env=env,
            start_new_session=True,
        )

    intent["status"] = "RUNNING"
    intent["pid"] = process.pid
    intent["process_marker"] = str(spec_path)
    _write_json(handle_path, intent)
    return {
        "status": "submitted",
        "exp_id": exp_id,
        "config_hash": ch,
        "pid": process.pid,
        "handle": str(handle_path),
    }


# ── status ──────────────────────────────────────────────────────────


def status(jobs_dir: Path, exp_id: str) -> Dict[str, Any]:
    handle_path = jobs_dir / exp_id / "handle.json"
    if not handle_path.exists():
        return {"status": "unknown", "exp_id": exp_id, "detail": "No handle.json found"}
    handle = _read_json(handle_path)
    result_path = handle_path.parent / "result.json"
    if result_path.exists():
        result = _read_json(result_path)
        return {
            "status": "COMPLETED" if result.get("exit_code") == 0 else "FAILED",
            "exp_id": exp_id,
            "exit_code": result.get("exit_code"),
            "handle": str(handle_path),
        }
    pid = handle.get("pid")
    if pid:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return {"status": "LOST", "exp_id": exp_id, "pid": pid, "handle": str(handle_path)}
        except PermissionError:
            return {"status": "RUNNING", "exp_id": exp_id, "pid": pid, "handle": str(handle_path)}
        return {"status": "RUNNING", "exp_id": exp_id, "pid": pid, "handle": str(handle_path)}
    if handle.get("status") == "INTENT":
        return {"status": "INTENT", "exp_id": exp_id, "detail": "Job intent recorded but never started"}
    return {"status": handle.get("status", "unknown"), "exp_id": exp_id, "handle": str(handle_path)}


# ── reconcile ───────────────────────────────────────────────────────


def reconcile(jobs_dir: Path, exp_id: str) -> Dict[str, Any]:
    handle_path = jobs_dir / exp_id / "handle.json"
    if not handle_path.exists():
        return {
            "action": "no_handle",
            "exp_id": exp_id,
            "detail": "No handle.json; job may have never been submitted.",
        }

    handle = _read_json(handle_path)
    result_path = handle_path.parent / "result.json"
    pid = handle.get("pid")

    # Case 1: the worker wrote an atomic result record.
    if result_path.exists():
        result = _read_json(result_path)
        if result.get("exit_code") != 0:
            return {
                "action": "failed",
                "exp_id": exp_id,
                "exit_code": result.get("exit_code"),
            }
        invalid = [
            item for item in result.get("artifacts", []) if not item.get("valid")
        ]
        if invalid:
            return {
                "action": "failed",
                "exp_id": exp_id,
                "detail": "One or more declared artifacts are missing or empty.",
            }
        return {
            "action": "completed",
            "exp_id": exp_id,
            "detail": "Worker exit code and declared artifacts are valid.",
        }

    # Case 2: process is still alive
    if pid:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            pass
        except PermissionError:
            return {
                "action": "continue_waiting",
                "exp_id": exp_id,
                "pid": pid,
                "detail": "Process is alive but no artifacts yet.",
            }
        else:
            return {
                "action": "continue_waiting",
                "exp_id": exp_id,
                "pid": pid,
                "detail": "Process is alive but no artifacts yet.",
            }

    # Case 3: process is dead, no artifacts — job was lost
    return {
        "action": "lost",
        "exp_id": exp_id,
        "pid": pid,
        "detail": "Process is dead and no artifacts are present. "
                  "The job can be resubmitted with the same config_hash.",
    }


def _run_worker(jobs_dir: Path, exp_id: str) -> Dict[str, Any]:
    job_dir = jobs_dir / exp_id
    spec = _read_json(job_dir / "spec.json")
    started = time.monotonic()
    timed_out = False
    with (job_dir / "command.stdout.log").open("wb") as stdout_handle, (
        job_dir / "command.stderr.log"
    ).open("wb") as stderr_handle:
        try:
            completed = subprocess.run(
                spec["command"],
                cwd=spec.get("cwd") or None,
                stdout=stdout_handle,
                stderr=stderr_handle,
                timeout=int(spec.get("timeout_seconds", 3600)),
                check=False,
            )
            exit_code = completed.returncode
        except subprocess.TimeoutExpired:
            exit_code = 124
            timed_out = True
            stderr_handle.write(b"\nJob exceeded its wall-clock timeout.\n")
    artifact_records = []
    base = Path(spec.get("cwd") or os.getcwd()).resolve()
    for relative in spec.get("artifacts", []):
        path = (base / relative).resolve()
        contained = base == path or base in path.parents
        artifact_records.append(
            {
                "path": relative,
                "valid": contained and path.is_file() and path.stat().st_size > 0,
            }
        )
    result = {
        "exit_code": exit_code,
        "timed_out": timed_out,
        "wall_seconds": time.monotonic() - started,
        "artifacts": artifact_records,
    }
    _write_json(job_dir / "result.json", result)
    return result


# ── CLI ─────────────────────────────────────────────────────────────


def main(argv: Optional[List[str]] = None) -> None:
    parser = argparse.ArgumentParser(description="Job control for reproducible experiments")
    parser.add_argument("--jobs-dir", default=str(DEFAULT_JOBS_DIR), help="Job records root")
    subparsers = parser.add_subparsers(dest="action", required=True)

    # submit
    p_sub = subparsers.add_parser("submit")
    p_sub.add_argument("--exp-id", required=True)
    p_sub.add_argument(
        "--command",
        dest="launch_command",
        required=True,
        help="Command line to parse without invoking a shell",
    )
    p_sub.add_argument("--config", required=True, help="Path to config file")
    p_sub.add_argument("--commit-id", default="")
    p_sub.add_argument("--seeds", default="", help="Comma-separated seed list")
    p_sub.add_argument("--env", default="", help="Path to environment snapshot")
    p_sub.add_argument("--artifact", action="append", default=[])
    p_sub.add_argument("--cwd", default=os.getcwd())
    p_sub.add_argument("--timeout-seconds", type=int, default=3600)

    # status
    p_st = subparsers.add_parser("status")
    p_st.add_argument("--exp-id", required=True)

    # reconcile
    p_rec = subparsers.add_parser("reconcile")
    p_rec.add_argument("--exp-id", required=True)
    p_worker = subparsers.add_parser("_worker", help=argparse.SUPPRESS)
    p_worker.add_argument("--exp-id", required=True)

    args = parser.parse_args(argv)
    jobs_dir = Path(args.jobs_dir).resolve()

    if args.action == "submit":
        command = shlex.split(args.launch_command)
        seeds = [int(s.strip()) for s in args.seeds.split(",") if s.strip()] if args.seeds else []
        result = submit(
            jobs_dir, args.exp_id, command,
            args.config, args.commit_id, seeds, args.env,
            artifacts=args.artifact,
            cwd=args.cwd,
            timeout_seconds=args.timeout_seconds,
        )
    elif args.action == "status":
        result = status(jobs_dir, args.exp_id)
    elif args.action == "reconcile":
        result = reconcile(jobs_dir, args.exp_id)
    elif args.action == "_worker":
        result = _run_worker(jobs_dir, args.exp_id)
    else:
        result = {"error": f"Unknown action: {args.action}"}

    print(json.dumps(result, ensure_ascii=False, indent=2))
    if (
        "error" in result
        or result.get("status") in ("blocked", "config_changed", "error", "FAILED")
        or result.get("action") == "failed"
    ):
        sys.exit(1)


if __name__ == "__main__":
    main()
