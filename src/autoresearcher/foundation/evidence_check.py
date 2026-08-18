"""evidence_check — deterministic per-cycle evidence existence gate.

Motivation: the full `audit` gate only runs on the final `continue` path.
During replan/revise loops nothing verifies that the evidence paths the
ANALYZE agent writes into cycle-output.json actually exist, so a fabricated
path could steer strategy decisions for several cycles. This gate closes
that hole and must run in every cycle, directly after ANALYZE.

Usage:
    python -m autoresearcher.foundation.evidence_check \\
        --cycle-output research/orchestration/cycle-output.json \\
        --run-dir research \\
        [--output research/orchestration/evidence-check.json]

Checks:
    1. Every path in `evidence_paths` and every `claims[].evidence[]` entry
       is relative, resolves inside --run-dir (or its parent workspace as a
       path-prefix fallback), exists, and is non-empty.
    2. Every claim with verdict `supported` or `contradicted` declares at
       least one evidence path. `inconclusive` claims may have none.

Output: JSON on stdout (and to --output when given).
Exit code 0 = pass, 1 = blocked.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _read_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _verify_path(evidence_path: str, run_dir: Path) -> Dict[str, Any]:
    result: Dict[str, Any] = {"path": evidence_path, "valid": False}
    relative = Path(evidence_path)
    if relative.is_absolute():
        result["error"] = "absolute evidence paths are not portable"
        return result
    # Agents record paths either relative to the run dir (audit convention)
    # or with the run-dir prefix already included; accept both roots but
    # never anything that escapes the workspace.
    workspace = run_dir.parent
    for root in (run_dir, workspace):
        full = (root / relative).resolve()
        if workspace != full and workspace not in full.parents:
            continue
        if full.is_file() and full.stat().st_size > 0:
            result["valid"] = True
            result["resolved"] = str(full)
            return result
        if full.is_dir():
            try:
                next(full.iterdir())
            except StopIteration:
                continue
            result["valid"] = True
            result["resolved"] = str(full)
            return result
    result["error"] = "file missing, empty, or escapes workspace"
    return result


def run_check(cycle_output: Path, run_dir: Path) -> Dict[str, Any]:
    """Validate one cycle-output file. Returns the report dict."""
    report: Dict[str, Any] = {
        "generated_at": _now(),
        "cycle_output": str(cycle_output),
        "run_dir": str(run_dir),
        "problems": [],
        "checked_paths": [],
        "pass": False,
    }
    try:
        data = _read_json(cycle_output)
    except (OSError, json.JSONDecodeError) as exc:
        report["problems"].append(f"cycle output unreadable: {exc}")
        return report

    claims = data.get("claims")
    if not isinstance(claims, list):
        report["problems"].append("claims must be an array")
        claims = []
    for index, claim in enumerate(claims):
        if not isinstance(claim, dict):
            report["problems"].append(f"claims[{index}] must be an object")
            continue
        claim_id = str(claim.get("claim_id", f"claims[{index}]"))
        verdict = claim.get("verdict")
        evidence = claim.get("evidence")
        evidence_list: List[str] = (
            [item for item in evidence if isinstance(item, str)]
            if isinstance(evidence, list)
            else []
        )
        if verdict in {"supported", "contradicted"} and not evidence_list:
            report["problems"].append(
                f"claim {claim_id!r} has verdict {verdict!r} but no evidence"
            )
        for evidence_path in evidence_list:
            checked = _verify_path(evidence_path, run_dir)
            checked["claim_id"] = claim_id
            report["checked_paths"].append(checked)
            if not checked["valid"]:
                report["problems"].append(
                    f"claim {claim_id!r} evidence invalid: "
                    f"{evidence_path} ({checked['error']})"
                )

    evidence_paths = data.get("evidence_paths")
    if isinstance(evidence_paths, list):
        for evidence_path in evidence_paths:
            if not isinstance(evidence_path, str):
                report["problems"].append(
                    f"evidence_paths entry must be a string: {evidence_path!r}"
                )
                continue
            checked = _verify_path(evidence_path, run_dir)
            report["checked_paths"].append(checked)
            if not checked["valid"]:
                report["problems"].append(
                    f"evidence path invalid: {evidence_path} "
                    f"({checked['error']})"
                )

    report["pass"] = not report["problems"]
    return report


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Deterministic per-cycle evidence existence gate"
    )
    parser.add_argument("--cycle-output", required=True)
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--output")
    args = parser.parse_args(argv)

    run_dir = Path(args.run_dir).expanduser().resolve()
    report = run_check(Path(args.cycle_output).expanduser().resolve(), run_dir)
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        output = Path(args.output).expanduser()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
