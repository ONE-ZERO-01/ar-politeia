"""Functional tests for foundation/gen_manifest.py."""
import hashlib
import json
from pathlib import Path

from autoresearcher.foundation.gen_manifest import build_manifest, run


def _write(path: Path, data) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, ensure_ascii=False, indent=2)
    path.write_text(text, encoding="utf-8")
    return path


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _job(research_dir: Path, exp_id: str, *, status="completed", passed=True) -> Path:
    job_dir = research_dir / "jobs" / exp_id
    _write(job_dir / "result.json", {"status": status, "pass": passed, "x": 1})
    return job_dir


def test_build_manifest_completed_pass_true(tmp_path):
    research_dir = tmp_path / "research"
    job_dir = _job(research_dir, "E1-MATCHED-LANDSCAPES")
    _write(job_dir / "paired_effects.json", {"effect": 0.3})
    # input declaration must NOT be recorded as an artifact
    _write(job_dir / "config.json", {"a": 1})

    manifest = build_manifest(job_dir, research_dir)

    assert manifest["exit_code"] == 0
    assert manifest["mode"] == "server"
    paths = [a["path"] for a in manifest["artifacts"]]
    assert paths == [
        "jobs/E1-MATCHED-LANDSCAPES/result.json",
        "jobs/E1-MATCHED-LANDSCAPES/paired_effects.json",
    ]
    for artifact in manifest["artifacts"]:
        full = research_dir / artifact["path"]
        assert artifact["sha256"] == _sha256(full)
        assert artifact["size"] == full.stat().st_size


def test_build_manifest_pass_false_is_skipped(tmp_path):
    research_dir = tmp_path / "research"
    job_dir = _job(research_dir, "E0-NUMERICS", passed=False)

    assert build_manifest(job_dir, research_dir) is None


def test_build_manifest_blocked_is_skipped(tmp_path):
    research_dir = tmp_path / "research"
    job_dir = _job(research_dir, "E2-CHANNEL-ABLATION", status="blocked", passed=False)

    assert build_manifest(job_dir, research_dir) is None


def test_build_manifest_missing_result_is_skipped(tmp_path):
    research_dir = tmp_path / "research"
    job_dir = research_dir / "jobs" / "E3-ROBUSTNESS-HOLDOUT"
    job_dir.mkdir(parents=True)

    assert build_manifest(job_dir, research_dir) is None


def test_run_generates_and_skips(tmp_path):
    research_dir = tmp_path / "research"
    _job(research_dir, "E0-NUMERICS-C3")
    _job(research_dir, "B0-DYNAMICS-PILOT-C3")
    _job(research_dir, "E0-NUMERICS", passed=False)           # retired C1
    _job(research_dir, "E2-CHANNEL-ABLATION", status="blocked", passed=False)

    result = run(research_dir)

    assert set(result["generated"]) == {"E0-NUMERICS-C3", "B0-DYNAMICS-PILOT-C3"}
    assert result["skipped"] == ["E0-NUMERICS", "E2-CHANNEL-ABLATION"]
    assert result["errors"] == []

    for exp_id in ("E0-NUMERICS-C3", "B0-DYNAMICS-PILOT-C3"):
        manifest_path = research_dir / "jobs" / exp_id / "manifest.json"
        assert manifest_path.is_file()
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert manifest["exit_code"] == 0
        assert manifest["artifacts"][0]["path"] == f"jobs/{exp_id}/result.json"

    # skipped jobs must not receive a manifest
    assert not (research_dir / "jobs" / "E0-NUMERICS" / "manifest.json").exists()
    assert not (research_dir / "jobs" / "E2-CHANNEL-ABLATION" / "manifest.json").exists()


def test_run_missing_jobs_dir(tmp_path):
    result = run(tmp_path / "research")
    assert result["generated"] == []
    assert result["errors"]
