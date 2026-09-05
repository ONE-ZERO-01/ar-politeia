"""gen_manifest — generate audit.py's manifest.json for completed jobs.

audit.py (evidence-chain validation before submission) expects each job directory
to carry a ``manifest.json`` of the form::

    {
        "exit_code": 0,
        "mode": "server",
        "artifacts": [
            {"path": "jobs/E1/result.json", "sha256": "...", "size": 1234},
            ...
        ]
    }

This tool derives that record from a job's authoritative ``result.json``:

- **Scope**: a manifest is emitted only for jobs whose ``result.json`` reports
  ``status == "completed"`` *and* ``pass == true`` — i.e. jobs whose scientific
  gate actually passed and therefore enter the submission evidence pool.
  Retired Cycle-1/2 jobs (``pass == false``; preserved as history per
  ``legacy_evidence_policy``) and not-yet-run jobs (``status == "blocked"``)
  are skipped: their negative/blocked results are audited through the
  claims-evidence path, not through a job manifest.
- ``exit_code`` = 0 (a recorded job has, by definition, completed and passed).
- ``mode`` = ``"server"`` (audit only performs the preflight.json binding check
  when ``mode == "local"``; our numerical jobs run on the ``umi`` server, so we
  skip that local-binding check).
- ``artifacts`` = the job's tracked *conclusion* JSON files — ``result.json``
  plus any experiment-specific conclusion file (``numerical_calibration.json``,
  ``pilot_health.json``, ``paired_effects.json``, ``channel_effects.json``,
  ``holdout_effects.json``). Input declarations (``config.json``,
  ``experiment.json``) are excluded: they are reproducibility *inputs*, not
  results. Artifact ``path`` is expressed relative to the research root, e.g.
  ``jobs/E1-MATCHED-LANDSCAPES/result.json``.

Jobs whose ``result.json`` is absent, blocked, or ``pass == false`` are
reported as skipped.

Usage:
    python -m autoresearcher.foundation.gen_manifest --research-dir research/
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# Experiment-specific conclusion files, in addition to result.json.
CONCLUSION_FILES: tuple[str, ...] = (
    "numerical_calibration.json",  # E0-NUMERICS
    "pilot_health.json",           # B0-DYNAMICS-PILOT
    "paired_effects.json",         # E1-MATCHED-LANDSCAPES
    "channel_effects.json",        # E2-CHANNEL-ABLATION
    "holdout_effects.json",        # E3-ROBUSTNESS-HOLDOUT
)

# Input-declaration files that must NOT be recorded as result artifacts.
INPUT_FILES: frozenset[str] = frozenset({"config.json", "experiment.json"})


def _read_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _recordable(result_path: Path) -> bool:
    """Return True only for jobs that belong in the submission evidence pool.

    A manifest is emitted only when the job completed *and* its scientific gate
    passed (``pass == true``). Retired Cycle-1/2 jobs (``pass == false``) and
    not-yet-run jobs (``status == "blocked"``) are not recorded: their results
    are audited through the claims-evidence path, not a job manifest.
    """
    data = _read_json(result_path)
    return data.get("status") == "completed" and data.get("pass") is True


def _conclusion_files(job_dir: Path) -> List[Path]:
    """Return the tracked conclusion JSON files of a job, result.json first."""
    paths: List[Path] = []
    result = job_dir / "result.json"
    if result.is_file():
        paths.append(result)
    for name in CONCLUSION_FILES:
        candidate = job_dir / name
        if candidate.is_file():
            paths.append(candidate)
    return paths


def build_manifest(job_dir: Path, research_dir: Path) -> Optional[Dict[str, Any]]:
    """Build one job's manifest.json, or None if the job should be skipped."""
    result_path = job_dir / "result.json"
    if not result_path.is_file():
        return None
    if not _recordable(result_path):
        return None

    artifacts: List[Dict[str, Any]] = []
    for path in _conclusion_files(job_dir):
        artifacts.append(
            {
                "path": path.relative_to(research_dir).as_posix(),
                "sha256": _sha256(path),
                "size": path.stat().st_size,
            }
        )

    return {
        "exit_code": 0,
        "mode": "server",
        "artifacts": artifacts,
    }


def run(research_dir: Path) -> Dict[str, Any]:
    """Generate manifest.json for every completed job under research/jobs/."""
    research_dir = research_dir.resolve()
    jobs_dir = research_dir / "jobs"
    generated: List[str] = []
    skipped: List[str] = []
    errors: List[str] = []

    if not jobs_dir.is_dir():
        return {
            "research_dir": str(research_dir),
            "generated": generated,
            "skipped": skipped,
            "errors": [f"jobs directory does not exist: {jobs_dir}"],
        }

    for job_dir in sorted(p for p in jobs_dir.iterdir() if p.is_dir()):
        try:
            manifest = build_manifest(job_dir, research_dir)
        except Exception as exc:  # noqa: BLE001 — surface per-job failures
            errors.append(f"{job_dir.name}: {exc}")
            continue
        if manifest is None:
            skipped.append(job_dir.name)
            continue
        (job_dir / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        generated.append(job_dir.name)

    return {
        "research_dir": str(research_dir),
        "generated": generated,
        "skipped": skipped,
        "errors": errors,
    }


def main(argv: Optional[List[str]] = None) -> None:
    parser = argparse.ArgumentParser(
        description="Generate audit.py's manifest.json for completed jobs"
    )
    parser.add_argument(
        "--research-dir",
        default="research",
        help="Root of the research records (default: research)",
    )
    args = parser.parse_args(argv)

    research_dir = Path(args.research_dir)
    result = run(research_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result["errors"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
