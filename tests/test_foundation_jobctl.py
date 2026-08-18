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
