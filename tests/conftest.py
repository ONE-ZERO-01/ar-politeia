"""Shared test helpers.

The one here exists because of a defect that a whole cycle's worth of green
tests failed to catch: every Cycle 4 recorder wrote manifest artifact paths the
audit gate can never resolve, and the tests agreed with the recorders instead of
with the gate.  Asserting a manifest against the constants we happen to use is
therefore not a check at all, so ``assert_manifest_is_auditable`` runs the
manifest through the real resolver in ``autoresearcher.foundation.audit``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from autoresearcher.foundation import audit


def assert_manifest_is_auditable(
    manifest: Mapping[str, Any],
    root: Path,
    *,
    run_dir: Path | None = None,
) -> None:
    """Require a manifest to survive the audit gate's own checks.

    ``audit`` resolves each recorded path against its run directory (default
    ``<root>/research``), verifies the sha256, and compares the recorded size --
    an absent ``size`` compares unequal and is reported as a mismatch, so all
    three fields have to be right.
    """
    run_dir = (run_dir or (root / "research")).resolve()
    artifacts = manifest.get("artifacts")
    assert artifacts, "a manifest with no artifact records is itself an audit failure"
    for entry in artifacts:
        record = audit._verify_evidence(
            entry["path"], run_dir, recorded_sha=entry.get("sha256")
        )
        assert record.get("valid") is True, (entry.get("path"), record)
        assert entry.get("size") == record["size"], entry.get("path")
        assert "size" in entry, f"{entry.get('path')} has no size field"
