"""Tests for the manifest path migration and for the repo's records conforming.

The migration exists because the audit gate -- a mandatory pre-submission gate --
could never pass on a Cycle 4 record: every manifest wrote ``workspace/<name>``,
which the gate resolves to ``research/workspace/<name>``, a path that cannot exist
because ``research/jobs/*/workspace/`` is gitignored.  These tests pin both halves:
that the migration can only ever re-point at byte-identical files, and that the
records actually in git satisfy the gate.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from autoresearcher.foundation import audit

REPO_ROOT = Path(__file__).parents[1]
MODULE_PATH = (
    REPO_ROOT / "research" / "src" / "experiments" / "prepare_cycle4_confirmation.py"
)
SPEC = importlib.util.spec_from_file_location("prepare_cycle4_confirmation", MODULE_PATH)
assert SPEC and SPEC.loader
promotion = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(promotion)


def _write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _job(root: Path, name: str, *, result: dict | None = None, extra: dict | None = None):
    job_dir = root / "research" / "jobs" / name
    job_dir.mkdir(parents=True)
    # Records are JSON: the gate refuses evidence it cannot parse, so a fixture
    # holding prose would exercise the migration against files audit rejects anyway.
    _write_json(job_dir / "result.json", {"pass": True} if result is None else result)
    for filename, payload in (extra or {}).items():
        _write_json(job_dir / filename, payload)
    return job_dir


def _sha256(path: Path) -> str:
    return promotion._sha256(path)


def _manifest(job_dir: Path, artifacts: list, **extra) -> Path:
    path = job_dir / "manifest.json"
    _write_json(path, {"exit_code": 0, "artifacts": artifacts, **extra})
    return path


def _auditable(manifest_path: Path, root: Path) -> None:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    run_dir = (root / "research").resolve()
    for entry in manifest["artifacts"]:
        record = audit._verify_evidence(
            entry["path"], run_dir, recorded_sha=entry.get("sha256")
        )
        assert record.get("valid") is True, (entry["path"], record)
        assert entry.get("size") == record["size"], entry["path"]


# ── re-pointing ──


def test_a_resolvable_entry_is_repointed_and_given_a_size(tmp_path):
    job_dir = _job(tmp_path, "E1", extra={"paired_effects.json": {"claim_supported": True}})
    kept_paired = job_dir / "paired_effects.json"
    kept_result = job_dir / "result.json"
    manifest_path = _manifest(
        job_dir,
        [
            {"path": "workspace/paired_effects.json", "sha256": _sha256(kept_paired), "valid": True},
            {"path": "workspace/result.json", "sha256": _sha256(kept_result), "valid": True},
        ],
    )
    report = promotion.migrate_manifest_paths(tmp_path)
    assert report["totals"]["repointed"] == 2
    assert report["totals"]["already_correct"] == 0
    assert report["totals"]["unkept"] == 0
    assert report["totals"]["attested_kept"] == 0
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert [entry["path"] for entry in manifest["artifacts"]] == [
        "jobs/E1/paired_effects.json",
        "jobs/E1/result.json",
    ]
    assert all("size" in entry for entry in manifest["artifacts"])
    _auditable(manifest_path, tmp_path)


def test_a_workspace_entry_the_job_did_not_keep_is_moved_verbatim(tmp_path):
    """The 11 real cases: the job kept a compacted record, not the workspace one."""
    job_dir = _job(tmp_path, "E1", result={"pass": True, "compacted": True})
    manifest_path = _manifest(
        job_dir,
        [
            {
                "path": "workspace/result.json",
                "sha256": "0" * 64,
                "valid": True,
                "source_sha256": "1" * 64,
            },
            {"path": "workspace/replicate_metrics.csv", "sha256": "2" * 64, "valid": True},
        ],
    )
    report = promotion.migrate_manifest_paths(tmp_path)
    assert report["totals"]["unkept"] == 2
    assert report["totals"]["attested_kept"] == 1
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert [entry["path"] for entry in manifest["artifacts"]] == ["jobs/E1/result.json"]
    # The un-kept attestations are carried across untouched: they are a true
    # statement about a workspace file, and rewriting them would invent evidence.
    assert manifest["unkept_workspace_attestations"] == [
        {
            "path": "workspace/result.json",
            "sha256": "0" * 64,
            "valid": True,
            "source_sha256": "1" * 64,
        },
        {"path": "workspace/replicate_metrics.csv", "sha256": "2" * 64, "valid": True},
    ]
    _auditable(manifest_path, tmp_path)


def test_a_kept_record_nothing_attested_gets_an_entry(tmp_path):
    job_dir = _job(tmp_path, "E1")
    manifest_path = _manifest(
        job_dir, [{"path": "workspace/gone.json", "sha256": "0" * 64, "valid": True}]
    )
    report = promotion.migrate_manifest_paths(tmp_path)
    assert report["totals"]["attested_kept"] == 1
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert [entry["path"] for entry in manifest["artifacts"]] == ["jobs/E1/result.json"]
    assert manifest["artifacts"][0]["sha256"] == _sha256(job_dir / "result.json")
    _auditable(manifest_path, tmp_path)


def test_an_already_correct_entry_is_kept_and_given_its_size(tmp_path):
    job_dir = _job(tmp_path, "E1")
    result = job_dir / "result.json"
    manifest_path = _manifest(
        job_dir, [{"path": "jobs/E1/result.json", "sha256": _sha256(result)}]
    )
    report = promotion.migrate_manifest_paths(tmp_path)
    assert report["totals"]["already_correct"] == 1
    assert report["totals"]["repointed"] == 0
    assert report["totals"]["attested_kept"] == 0
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["artifacts"][0]["size"] == result.stat().st_size
    _auditable(manifest_path, tmp_path)


def test_an_already_correct_manifest_is_left_byte_identical(tmp_path):
    """No cosmetic churn on records that were already right.

    The gate does not read artifact order, so re-sorting would rewrite Cycle 3's
    manifests for no reason and bury the real repair under noise in git blame.
    """
    job_dir = _job(tmp_path, "E1", extra={"a.json": {"a": 1}, "z.json": {"z": 1}})
    manifest_path = _manifest(
        job_dir,
        [
            promotion._tracked_evidence(job_dir, "result.json"),
            promotion._tracked_evidence(job_dir, "z.json"),
            promotion._tracked_evidence(job_dir, "a.json"),
        ],
    )
    before = manifest_path.read_bytes()
    report = promotion.migrate_manifest_paths(tmp_path)
    assert report["totals"]["jobs_changed"] == 0
    assert manifest_path.read_bytes() == before


def test_unkept_attestations_survive_a_second_pass(tmp_path):
    """The carry-forward the first draft dropped on the floor.

    Without it a second pass deletes the only surviving statement about a workspace
    file, which is the one direction a repair of recorded evidence must never move.
    """
    job_dir = _job(tmp_path, "E1")
    manifest_path = _manifest(
        job_dir, [{"path": "workspace/result.json", "sha256": "3" * 64, "valid": True}]
    )
    promotion.migrate_manifest_paths(tmp_path)
    first = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert first["unkept_workspace_attestations"] == [
        {"path": "workspace/result.json", "sha256": "3" * 64, "valid": True}
    ]
    report = promotion.migrate_manifest_paths(tmp_path)
    assert report["totals"]["jobs_changed"] == 0
    assert report["totals"]["unkept_carried"] == 1
    assert json.loads(manifest_path.read_text(encoding="utf-8")) == first


def test_the_migration_is_idempotent(tmp_path):
    job_dir = _job(tmp_path, "E1", extra={"paired_effects.json": {"claim_supported": True}})
    manifest_path = _manifest(
        job_dir,
        [
            {
                "path": "workspace/paired_effects.json",
                "sha256": _sha256(job_dir / "paired_effects.json"),
            },
            {"path": "workspace/result.json", "sha256": "0" * 64, "valid": True},
        ],
    )
    promotion.migrate_manifest_paths(tmp_path)
    after = manifest_path.read_bytes()
    second = promotion.migrate_manifest_paths(tmp_path)
    assert manifest_path.read_bytes() == after
    assert second["totals"]["jobs_changed"] == 0
    assert second["totals"]["already_correct"] == 2
    assert second["totals"]["repointed"] == 0
    assert second["totals"]["unkept"] == 0
    assert second["totals"]["attested_kept"] == 0


# ── refusals ──


def test_an_entry_whose_hash_disagrees_is_never_repointed(tmp_path):
    job_dir = _job(tmp_path, "E1", extra={"paired_effects.json": {"claim_supported": False}})
    manifest_path = _manifest(
        job_dir, [{"path": "workspace/paired_effects.json", "sha256": "0" * 64, "valid": True}]
    )
    report = promotion.migrate_manifest_paths(tmp_path)
    # It becomes an un-kept attestation rather than a re-point, and the entry it
    # becomes is the one that was recorded, not a claim about the file on disk.
    assert report["totals"]["repointed"] == 0
    assert report["totals"]["unkept"] == 1
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["unkept_workspace_attestations"][0]["sha256"] == "0" * 64
    assert manifest["artifacts"] == [
        {
            "path": "jobs/E1/result.json",
            "sha256": _sha256(job_dir / "result.json"),
            "size": (job_dir / "result.json").stat().st_size,
        }
    ]


def test_a_research_relative_entry_that_does_not_resolve_is_refused(tmp_path):
    job_dir = _job(tmp_path, "E1")
    _manifest(job_dir, [{"path": "jobs/E1/no-such-file.json", "sha256": "0" * 64}])
    with pytest.raises(RuntimeError, match="already research-relative but does not resolve"):
        promotion.migrate_manifest_paths(tmp_path)


def test_a_research_relative_entry_whose_hash_disagrees_is_refused(tmp_path):
    job_dir = _job(tmp_path, "E1")
    _manifest(job_dir, [{"path": "jobs/E1/result.json", "sha256": "0" * 64}])
    with pytest.raises(RuntimeError, match="not the recorded"):
        promotion.migrate_manifest_paths(tmp_path)


def test_a_manifest_with_no_artifact_list_is_refused(tmp_path):
    job_dir = _job(tmp_path, "E1")
    _write_json(job_dir / "manifest.json", {"exit_code": 0})
    with pytest.raises(RuntimeError, match="no artifact list"):
        promotion.migrate_manifest_paths(tmp_path)


def test_a_job_that_kept_no_record_is_refused(tmp_path):
    job_dir = tmp_path / "research" / "jobs" / "E1"
    job_dir.mkdir(parents=True)
    _manifest(job_dir, [{"path": "workspace/gone.json", "sha256": "0" * 64}])
    with pytest.raises(RuntimeError, match="kept no result.json"):
        promotion.migrate_manifest_paths(tmp_path)


def test_an_unkept_block_that_is_not_a_list_is_refused(tmp_path):
    job_dir = _job(tmp_path, "E1")
    _manifest(
        job_dir,
        [{"path": "jobs/E1/result.json", "sha256": _sha256(job_dir / "result.json")}],
        unkept_workspace_attestations={"workspace/result.json": "0" * 64},
    )
    with pytest.raises(RuntimeError, match="is not a list"):
        promotion.migrate_manifest_paths(tmp_path)


# ── the records actually in git ──


def test_every_manifest_in_the_repository_satisfies_the_audit_gate():
    """The guard whose absence let the convention drift through a whole cycle.

    A test that asserts a manifest against the constants we happen to use proves
    nothing; this one runs each recorded manifest through the gate's own resolver.
    """
    run_dir = (REPO_ROOT / "research").resolve()
    manifests = sorted((run_dir / "jobs").glob("*/manifest.json"))
    assert manifests, "no recorded manifests to check"
    for manifest_path in manifests:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert manifest.get("artifacts"), manifest_path
        for entry in manifest["artifacts"]:
            assert "size" in entry, (manifest_path, entry.get("path"))
            record = audit._verify_evidence(
                entry["path"], run_dir, recorded_sha=entry.get("sha256")
            )
            assert record.get("valid") is True, (manifest_path, entry.get("path"), record)
            assert entry["size"] == record["size"], (manifest_path, entry.get("path"))


def test_running_the_migration_on_the_repository_changes_nothing():
    """Already migrated, so a second pass is a no-op and git stays clean.

    This test writes to the working tree when the migration is *not* a no-op, and
    that is deliberate: it is how the dropped carry-forward above was found.  A
    failure here is a real diff in research/jobs/*/manifest.json, ready to inspect.
    """
    manifests = sorted((REPO_ROOT / "research" / "jobs").glob("*/manifest.json"))
    before = {path: path.read_bytes() for path in manifests}
    unkept_before = sum(
        len(json.loads(raw).get("unkept_workspace_attestations") or [])
        for raw in before.values()
    )
    assert unkept_before, "the records this test protects are missing"

    report = promotion.migrate_manifest_paths(REPO_ROOT)

    assert report["totals"]["jobs_changed"] == 0
    assert report["totals"]["repointed"] == 0
    assert report["totals"]["unkept"] == 0
    assert report["totals"]["attested_kept"] == 0
    assert report["totals"]["unkept_carried"] == unkept_before
    for path, raw in before.items():
        assert path.read_bytes() == raw, path
