"""Functional tests for foundation/jobctl.py."""
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest

import autoresearcher.foundation.jobctl as jobctl
from autoresearcher.foundation.jobctl import (
    _config_hash,
    recheck,
    reconcile,
    status,
    submit,
)


@pytest.fixture()
def jobs_dir():
    with tempfile.TemporaryDirectory() as td:
        yield Path(td)


def test_config_hash_stable():
    a = {"exp_id": "E1", "command": ["python", "run.py"], "seeds": [11, 23]}
    b = {"command": ["python", "run.py"], "exp_id": "E1", "seeds": [11, 23]}
    assert _config_hash(a) == _config_hash(b)


def test_config_hash_different():
    a = {"exp_id": "E1", "command": ["python", "run.py"], "seeds": [11, 23]}
    b = {"exp_id": "E1", "command": ["python", "run.py"], "seeds": [11, 24]}
    assert _config_hash(a) != _config_hash(b)


def test_config_hash_changes_with_command():
    a = {"exp_id": "E1", "command": ["python", "old.py"], "seeds": [11, 23]}
    b = {"exp_id": "E1", "command": ["python", "new.py"], "seeds": [11, 23]}
    assert _config_hash(a) != _config_hash(b)


def test_submit_creates_handle(jobs_dir, tmp_path):
    config = tmp_path / "config.yaml"
    config.write_text("lr: 0.001", encoding="utf-8")
    env = tmp_path / "env.txt"
    env.write_text("python=3.9\n", encoding="utf-8")

    result = submit(
        jobs_dir, "E1",
        ["python3", "-c", "print('hello')"],
        str(config), "abc1234", [11, 23], str(env),
    )
    assert result["status"] == "submitted"
    assert (jobs_dir / "E1" / "handle.json").exists()

    handle = json.loads((jobs_dir / "E1" / "handle.json").read_text(encoding="utf-8"))
    assert handle["config_hash"] == result["config_hash"]


def test_submit_idempotent(jobs_dir, tmp_path):
    config = tmp_path / "config.yaml"
    config.write_text("lr: 0.001", encoding="utf-8")
    env = tmp_path / "env.txt"
    env.write_text("python=3.9\n", encoding="utf-8")

    r1 = submit(jobs_dir, "E1", ["true"], str(config), "abc1234", [11, 23], str(env))
    r2 = submit(jobs_dir, "E1", ["true"], str(config), "abc1234", [11, 23], str(env))
    assert r2["status"] == "already_submitted"
    assert r2["config_hash"] == r1["config_hash"]


def test_submit_config_changed(jobs_dir, tmp_path):
    config = tmp_path / "config.yaml"
    config.write_text("lr: 0.001", encoding="utf-8")
    env = tmp_path / "env.txt"
    env.write_text("python=3.9\n", encoding="utf-8")

    submit(jobs_dir, "E1", ["true"], str(config), "abc1234", [11], str(env))
    result = submit(jobs_dir, "E1", ["true"], str(config), "abc1234", [23], str(env))
    assert result["status"] == "config_changed"


def test_status_unknown(jobs_dir):
    result = status(jobs_dir, "E99")
    assert result["status"] == "unknown"


def test_status_intent(jobs_dir):
    _write(jobs_dir / "E1" / "handle.json", {"status": "INTENT", "pid": None})
    result = status(jobs_dir, "E1")
    assert result["status"] == "INTENT"


def test_status_running(jobs_dir):
    _write(jobs_dir / "E1" / "handle.json", {"status": "RUNNING", "pid": os.getpid()})
    result = status(jobs_dir, "E1")
    assert result["status"] == "RUNNING"


def test_status_lost(jobs_dir):
    _write(jobs_dir / "E1" / "handle.json", {"status": "RUNNING", "pid": 99999})
    result = status(jobs_dir, "E1")
    assert result["status"] == "LOST"


def test_reconcile_no_handle(jobs_dir):
    result = reconcile(jobs_dir, "E99")
    assert result["action"] == "no_handle"


def test_reconcile_completed(jobs_dir):
    job_dir = jobs_dir / "E1"
    job_dir.mkdir(parents=True)
    _write(job_dir / "result.json", {"exit_code": 0, "artifacts": []})
    _write(job_dir / "handle.json", {"status": "RUNNING", "pid": os.getpid()})
    result = reconcile(jobs_dir, "E1")
    assert result["action"] == "completed"


def test_reconcile_lost(jobs_dir):
    _write(jobs_dir / "E1" / "handle.json", {"status": "RUNNING", "pid": 99999})
    result = reconcile(jobs_dir, "E1")
    assert result["action"] == "lost"


def test_submit_launches_process(jobs_dir, tmp_path):
    """Submit a real short process, verify handle and PID are recorded."""
    config = tmp_path / "config.yaml"
    config.write_text("lr: 0.001", encoding="utf-8")
    env = tmp_path / "env.txt"
    env.write_text("python=3.9\n", encoding="utf-8")

    result = submit(
        jobs_dir, "E2",
        [sys.executable, "-c", "exit(0)"],
        str(config), "abc1234", [11, 23], str(env),
    )
    assert result["status"] == "submitted"
    assert result["pid"] is not None
    handle = json.loads((jobs_dir / "E2" / "handle.json").read_text(encoding="utf-8"))
    assert handle["status"] == "RUNNING"
    assert handle["pid"] == result["pid"]


def test_cli_keeps_subcommand_separate_from_launch_command(
    jobs_dir, tmp_path, monkeypatch, capsys
):
    config = tmp_path / "config.yaml"
    config.write_text("lr: 0.001", encoding="utf-8")
    env = tmp_path / "env.txt"
    env.write_text("python=3.11", encoding="utf-8")
    captured = {}

    def fake_submit(*args, **kwargs):
        captured["command"] = args[2]
        return {"status": "submitted", "exp_id": "E1"}

    monkeypatch.setattr(jobctl, "submit", fake_submit)
    jobctl.main(
        [
            "--jobs-dir",
            str(jobs_dir),
            "submit",
            "--exp-id",
            "E1",
            "--command",
            "python run.py --flag value",
            "--config",
            str(config),
            "--commit-id",
            "abc",
            "--seeds",
            "1,2,3",
            "--env",
            str(env),
        ]
    )
    capsys.readouterr()
    assert captured["command"] == ["python", "run.py", "--flag", "value"]


def _write(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) if isinstance(data, dict) else str(data), encoding="utf-8")


# ── submit 校验的负向测试（防止静默通过）──────────────────────────────

def test_submit_empty_config_blocked(jobs_dir, tmp_path):
    config = tmp_path / "config.yaml"
    config.write_text("", encoding="utf-8")  # 空文件
    env = tmp_path / "env.txt"
    env.write_text("python=3.9\n", encoding="utf-8")
    result = submit(
        jobs_dir, "E1", ["true"], str(config), "abc1234", [11], str(env)
    )
    assert result["status"] == "blocked"
    assert any("config" in e for e in result["errors"])


def test_submit_missing_env_blocked(jobs_dir, tmp_path):
    config = tmp_path / "config.yaml"
    config.write_text("lr: 0.001", encoding="utf-8")
    missing_env = tmp_path / "nope.txt"
    result = submit(
        jobs_dir, "E1", ["true"], str(config), "abc1234", [11], str(missing_env)
    )
    assert result["status"] == "blocked"
    assert any("environment" in e for e in result["errors"])


def test_submit_dirty_commit_blocked(jobs_dir, tmp_path):
    config = tmp_path / "config.yaml"
    config.write_text("lr: 0.001", encoding="utf-8")
    env = tmp_path / "env.txt"
    env.write_text("python=3.9\n", encoding="utf-8")
    result = submit(
        jobs_dir, "E1", ["true"], str(config), "dirty", [11], str(env)
    )
    assert result["status"] == "blocked"
    assert any("commit" in e for e in result["errors"])


def test_submit_empty_seeds_blocked(jobs_dir, tmp_path):
    config = tmp_path / "config.yaml"
    config.write_text("lr: 0.001", encoding="utf-8")
    env = tmp_path / "env.txt"
    env.write_text("python=3.9\n", encoding="utf-8")
    result = submit(
        jobs_dir, "E1", ["true"], str(config), "abc1234", [], str(env)
    )
    assert result["status"] == "blocked"
    assert any("seed" in e for e in result["errors"])


# ── reconcile / status 的失败分支（防止把失败误判为通过）────────────────

def test_reconcile_failed_exit_code(jobs_dir):
    job_dir = jobs_dir / "E1"
    job_dir.mkdir(parents=True)
    _write(job_dir / "result.json", {"exit_code": 1, "artifacts": []})
    _write(job_dir / "handle.json", {"status": "RUNNING", "pid": os.getpid()})
    result = reconcile(jobs_dir, "E1")
    assert result["action"] == "failed"
    assert result["exit_code"] == 1


def test_reconcile_invalid_artifact(jobs_dir):
    job_dir = jobs_dir / "E1"
    job_dir.mkdir(parents=True)
    _write(
        job_dir / "result.json",
        {"exit_code": 0, "artifacts": [{"valid": False}]},
    )
    _write(job_dir / "handle.json", {"status": "RUNNING", "pid": os.getpid()})
    result = reconcile(jobs_dir, "E1")
    assert result["action"] == "failed"


def test_status_failed(jobs_dir):
    job_dir = jobs_dir / "E1"
    job_dir.mkdir(parents=True)
    _write(job_dir / "result.json", {"exit_code": 2, "artifacts": []})
    _write(job_dir / "handle.json", {"status": "RUNNING", "pid": os.getpid()})
    result = status(jobs_dir, "E1")
    assert result["status"] == "FAILED"


# ── 声明契约：提交期拦截与完成后 recheck ─────────────────────────────


def _submit_fixtures(tmp_path):
    config = tmp_path / "config.yaml"
    config.write_text("lr: 0.001", encoding="utf-8")
    env = tmp_path / "env.txt"
    env.write_text("python=3.9\n", encoding="utf-8")
    return config, env


def test_submit_blocks_artifact_escaping_cwd(jobs_dir, tmp_path):
    config, env = _submit_fixtures(tmp_path)
    result = submit(
        jobs_dir, "E1", ["true"], str(config), "abc1234", [11], str(env),
        artifacts=["../outside.json"], cwd=str(tmp_path),
    )
    assert result["status"] == "blocked"
    assert any("escapes" in e for e in result["errors"])
    assert not (jobs_dir / "E1" / "handle.json").exists()


def test_submit_blocks_duplicate_artifact(jobs_dir, tmp_path):
    config, env = _submit_fixtures(tmp_path)
    result = submit(
        jobs_dir, "E1", ["true"], str(config), "abc1234", [11], str(env),
        artifacts=["out/result.json", "out/result.json"], cwd=str(tmp_path),
    )
    assert result["status"] == "blocked"
    assert any("duplicate" in e for e in result["errors"])


def test_submit_records_resolved_artifact_path(jobs_dir, tmp_path):
    config, env = _submit_fixtures(tmp_path)
    result = submit(
        jobs_dir, "E1", ["true"], str(config), "abc1234", [11], str(env),
        artifacts=["out/result.json"], cwd=str(tmp_path),
    )
    assert result["status"] == "submitted"
    spec = json.loads((jobs_dir / "E1" / "spec.json").read_text(encoding="utf-8"))
    assert spec["artifacts"] == ["out/result.json"]


def test_recheck_repairs_bare_basename_declaration(jobs_dir, tmp_path):
    """A bare basename resolves to cwd root; recheck must expose the real path."""
    job_dir = jobs_dir / "E1"
    job_dir.mkdir(parents=True)
    workspace = tmp_path / "jobs" / "E1" / "workspace"
    workspace.mkdir(parents=True)
    (workspace / "result.json").write_text('{"pass": true}\n', encoding="utf-8")
    _write(
        job_dir / "spec.json",
        {
            "exp_id": "E1",
            "cwd": str(tmp_path),
            "artifacts": ["jobs/E1/workspace/result.json"],
        },
    )
    # The worker recorded a verdict against the malformed declaration.
    _write(
        job_dir / "result.json",
        {
            "exit_code": 0,
            "timed_out": False,
            "wall_seconds": 12.5,
            "artifacts": [
                {"path": "result.json", "valid": False},
            ],
        },
    )
    result = recheck(jobs_dir, "E1", reason="declaration used bare basenames")
    assert result["action"] == "rechecked"
    assert result["artifacts_valid"] is True
    repaired = json.loads((job_dir / "result.json").read_text(encoding="utf-8"))
    # Execution facts are preserved verbatim; only the contract is recomputed.
    assert repaired["exit_code"] == 0
    assert repaired["timed_out"] is False
    assert repaired["wall_seconds"] == 12.5
    assert repaired["artifacts"][0]["valid"] is True
    assert repaired["artifacts"][0]["resolved"] == str(workspace / "result.json")
    assert repaired["artifact_recheck"]["declaration_evaluated"] == [
        "jobs/E1/workspace/result.json"
    ]
    assert repaired["artifact_recheck"]["previous_artifacts"] == [
        {"path": "result.json", "valid": False}
    ]
    assert repaired["artifact_recheck"]["still_invalid"] == []
    _write(job_dir / "handle.json", {"status": "RUNNING", "pid": os.getpid()})
    assert reconcile(jobs_dir, "E1")["action"] == "completed"


def test_recheck_reports_still_invalid_artifact(jobs_dir, tmp_path):
    job_dir = jobs_dir / "E1"
    job_dir.mkdir(parents=True)
    _write(job_dir / "spec.json", {"exp_id": "E1", "cwd": str(tmp_path), "artifacts": ["a.json"]})
    _write(
        job_dir / "result.json",
        {"exit_code": 0, "timed_out": False, "wall_seconds": 1.0, "artifacts": []},
    )
    result = recheck(jobs_dir, "E1", reason="re-verify")
    assert result["action"] == "rechecked"
    assert result["artifacts_valid"] is False
    assert result["invalid"] == ["a.json"]
    _write(job_dir / "handle.json", {"status": "RUNNING", "pid": os.getpid()})
    assert reconcile(jobs_dir, "E1")["action"] == "failed"


def test_recheck_requires_reason(jobs_dir, tmp_path):
    job_dir = jobs_dir / "E1"
    job_dir.mkdir(parents=True)
    _write(job_dir / "spec.json", {"exp_id": "E1", "cwd": str(tmp_path), "artifacts": []})
    _write(job_dir / "result.json", {"exit_code": 0, "artifacts": []})
    result = recheck(jobs_dir, "E1", reason="   ")
    assert result["action"] == "blocked"


def test_reconcile_surfaces_resolved_path_on_invalid(jobs_dir, tmp_path):
    job_dir = jobs_dir / "E1"
    job_dir.mkdir(parents=True)
    _write(
        job_dir / "result.json",
        {
            "exit_code": 0,
            "artifacts": [
                {
                    "path": "result.json",
                    "resolved": str(tmp_path / "result.json"),
                    "valid": False,
                }
            ],
        },
    )
    _write(job_dir / "handle.json", {"status": "RUNNING", "pid": os.getpid()})
    result = reconcile(jobs_dir, "E1")
    assert result["action"] == "failed"
    assert result["invalid_artifacts"] == [
        {"path": "result.json", "resolved": str(tmp_path / "result.json")}
    ]
