"""audit — evidence-chain validation before submission.

Usage:
    python -m autoresearcher.foundation.audit \\
        --run-dir results/ \\
        --claims-file paper/claims.json \\
        --output reproducibility-bundle.json

Checks:
    1. Every claim in the claims file has verifiable evidence paths.
    2. Each evidence file exists on disk and is non-zero.
    3. SHA-256 of each evidence file matches the record (if recorded).
    4. JSON evidence files contain no NaN or Inf.
    5. Claim coverage is complete (no unanalyzed claims).
    6. No dangling paper claims (every paper claim maps to a finding).

Output: a reproducibility-bundle.json suitable as supplementary material
         during submission. Exit code 0 = all checks pass, 1 = issues found.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _read_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


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


def _verify_evidence(evidence_path: str, run_dir: Path, recorded_sha: Optional[str] = None) -> Dict[str, Any]:
    relative = Path(evidence_path)
    if relative.is_absolute():
        return {
            "path": evidence_path,
            "valid": False,
            "error": "absolute evidence paths are not portable",
        }
    full = (run_dir / relative).resolve()
    result: Dict[str, Any] = {"path": evidence_path, "valid": False}
    if run_dir != full and run_dir not in full.parents:
        result["error"] = "evidence path escapes run directory"
        return result
    if not full.exists():
        result["error"] = "file missing"
        return result
    if full.stat().st_size == 0:
        result["error"] = "file is empty"
        return result
    result["sha256"] = _sha256(full)
    result["size"] = full.stat().st_size
    if recorded_sha and result["sha256"] != recorded_sha:
        result["error"] = "checksum mismatch"
        return result
    if full.suffix == ".json":
        try:
            data = _read_json(full)
        except Exception as exc:
            result["error"] = f"invalid JSON: {exc}"
            return result
        if not _is_finite(data):
            result["error"] = "contains NaN or Inf"
            return result
    result["valid"] = True
    return result


def run(run_dir: Path, claims_file: Optional[Path] = None) -> Dict[str, Any]:
    run_dir = run_dir.resolve()
    issues: List[str] = []
    claims_audit: List[Dict[str, Any]] = []
    paper_claim_ids: List[str] = []

    if claims_file and claims_file.exists():
        claims_data = _read_json(claims_file)
        paper_claims = claims_data.get("claims", [])
        for claim in paper_claims:
            claim_id = claim.get("claim_id")
            if not claim_id:
                issues.append("paper claim is missing claim_id")
            else:
                paper_claim_ids.append(claim_id)
            evidence_records: List[Dict[str, Any]] = []
            claim_sha = claim.get("sha256")
            evidence_items = claim.get("evidence", [])
            if not evidence_items:
                issues.append(f"claim {claim_id or '?'} has no evidence")
            for ev_item in evidence_items:
                if isinstance(ev_item, dict):
                    ev_path = ev_item.get("path", "")
                    ev_sha = ev_item.get("sha256", claim_sha)
                else:
                    ev_path = ev_item
                    ev_sha = claim_sha
                if not isinstance(ev_path, str) or not ev_path:
                    issues.append(f"claim {claim_id or '?'} has an invalid evidence path")
                    continue
                rec = _verify_evidence(ev_path, run_dir, recorded_sha=ev_sha)
                evidence_records.append(rec)
                if not rec.get("valid"):
                    issues.append(f"claim {claim.get('claim_id', '?')}: bad evidence {ev_path} — {rec.get('error', 'unknown')}")
            claims_audit.append({
                "claim_id": claim_id,
                "claim_text": claim.get("text", ""),
                "evidence": evidence_records,
            })
    else:
        issues.append("claims file is missing or not provided")
    if len(paper_claim_ids) != len(set(paper_claim_ids)):
        issues.append("paper claim ids must be unique")

    findings_path = run_dir / "findings.json"
    finding_ids: List[str] = []
    if findings_path.exists():
        try:
            findings = _read_json(findings_path).get("findings", [])
        except Exception as exc:
            issues.append(f"invalid findings.json: {exc}")
            findings = []
        finding_ids = [item.get("claim_id") for item in findings if item.get("claim_id")]
        dangling = set(paper_claim_ids) - set(finding_ids)
        if dangling:
            issues.append(f"paper claims have no finding: {sorted(dangling)}")

    plan_path = run_dir / "plan.json"
    if plan_path.exists():
        try:
            plan_claim_ids = {
                item.get("id")
                for item in _read_json(plan_path).get("claims", [])
                if item.get("id")
            }
        except Exception as exc:
            issues.append(f"invalid plan.json: {exc}")
            plan_claim_ids = set()
        if findings_path.exists():
            missing_findings = plan_claim_ids - set(finding_ids)
            unknown_findings = set(finding_ids) - plan_claim_ids
            if missing_findings:
                issues.append(
                    f"planned claims have no finding: {sorted(missing_findings)}"
                )
            if unknown_findings:
                issues.append(
                    f"findings reference unknown claims: {sorted(unknown_findings)}"
                )

    # check for manifest.json files in job dirs
    jobs_dir = run_dir / "jobs"
    if jobs_dir.is_dir():
        manifest_paths = sorted(jobs_dir.glob("*/manifest.json"))
        if not manifest_paths:
            issues.append(
                "no manifest.json found under jobs/*/ — job-level exit-code, "
                "artifact SHA, and preflight-binding checks were skipped"
            )
        for manifest_path in manifest_paths:
            try:
                manifest = _read_json(manifest_path)
            except Exception as exc:
                issues.append(f"invalid manifest {manifest_path.relative_to(run_dir)}: {exc}")
                continue
            exit_code = manifest.get("exit_code")
            if exit_code != 0:
                issues.append(f"{manifest_path.relative_to(run_dir)}: exit_code={exit_code}")
            if manifest.get("mode") == "local":
                preflight_path = manifest_path.parent / "preflight.json"
                if not preflight_path.exists():
                    issues.append(
                        f"{manifest_path.relative_to(run_dir)}: preflight.json missing"
                    )
                else:
                    try:
                        preflight = _read_json(preflight_path)
                    except Exception as exc:
                        issues.append(
                            f"invalid {preflight_path.relative_to(run_dir)}: {exc}"
                        )
                        preflight = {}
                    if preflight.get("status") != "ok":
                        issues.append(
                            f"{preflight_path.relative_to(run_dir)} did not pass"
                        )
                    bindings = preflight.get("bindings", {})
                    for path_key, sha_key in (
                        ("config_path", "config_sha256"),
                        ("env_snapshot_path", "env_sha256"),
                    ):
                        relative = bindings.get(path_key)
                        expected_sha = bindings.get(sha_key)
                        if not relative or not expected_sha:
                            issues.append(
                                f"{preflight_path.relative_to(run_dir)}: "
                                f"missing {sha_key}"
                            )
                            continue
                        workspace_relative = str(
                            manifest_path.parent.relative_to(run_dir)
                            / "workspace"
                            / relative
                        )
                        record = _verify_evidence(
                            workspace_relative,
                            run_dir,
                            recorded_sha=expected_sha,
                        )
                        if not record.get("valid"):
                            issues.append(
                                f"{preflight_path.relative_to(run_dir)}: "
                                f"{relative} - {record.get('error', 'invalid')}"
                            )
            artifacts = manifest.get("artifacts")
            if not isinstance(artifacts, list) or not artifacts:
                issues.append(
                    f"{manifest_path.relative_to(run_dir)}: no artifact records"
                )
                continue
            for artifact in artifacts:
                artifact_path = artifact.get("path", "")
                record = _verify_evidence(
                    artifact_path,
                    run_dir,
                    recorded_sha=artifact.get("sha256"),
                )
                if not record.get("valid"):
                    issues.append(
                        f"{manifest_path.relative_to(run_dir)}: bad artifact "
                        f"{artifact_path} - {record.get('error', 'unknown')}"
                    )
                elif artifact.get("size") != record.get("size"):
                    issues.append(
                        f"{manifest_path.relative_to(run_dir)}: size mismatch "
                        f"for {artifact_path}"
                    )

    # check NaN in result files
    for result_path in sorted(jobs_dir.glob("*/result.json")):
        try:
            data = _read_json(result_path)
        except Exception as exc:
            issues.append(
                f"invalid result {result_path.relative_to(run_dir)}: {exc}"
            )
            continue
        if not _is_finite(data):
            issues.append(f"{result_path.relative_to(run_dir)} contains NaN/Inf")

    all_checks_passed = len(issues) == 0

    return {
        "timestamp": _now(),
        "all_checks_passed": all_checks_passed,
        "claims": claims_audit,
        "failed_checks": issues,
        "total_claims": len(claims_audit),
        "total_evidence_files": sum(len(c.get("evidence", [])) for c in claims_audit),
    }


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description="Evidence-chain audit before submission")
    parser.add_argument("--run-dir", required=True, help="Root of experiment results")
    parser.add_argument("--claims-file", help="Path to paper claims.json")
    parser.add_argument("--output", help="Write reproducibility bundle to file")
    args = parser.parse_args(argv)

    run_dir = Path(args.run_dir).resolve()
    claims_file = Path(args.claims_file).resolve() if args.claims_file else None

    if not run_dir.is_dir():
        result = {"error": f"run_dir does not exist: {run_dir}"}
        print(json.dumps(result, ensure_ascii=False, indent=2))
        sys.exit(1)

    bundle = run(run_dir, claims_file)
    payload = json.dumps(bundle, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(payload + "\n", encoding="utf-8")
    print(payload)
    if not bundle["all_checks_passed"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
