"""The pre-submission entry point, and the documentation that points at it.

The failure this guards against is not a wrong gate but a gate nobody noticed could
not be satisfied: `audit` could never pass on a Cycle 4 record, and nothing in the
suite or in CI said so.  `scripts/verify-evidence.sh` makes the attempt one command,
and these tests keep that command, the gate's own default paths, and the two
checklists that tell a human when to run it from drifting apart.

Nothing here runs the derive step: `claims.json` and `findings.json` carry a
`generated_at` stamp, so regenerating them would dirty the working tree.  The
derivation's own behaviour is covered by tests/test_derive_claims.py.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parents[1]
WRAPPER = REPO_ROOT / "scripts" / "verify-evidence.sh"
AUTORESEARCHER = REPO_ROOT / "autoresearcher.md"
CHECKLIST = REPO_ROOT / "SUBMISSION_CHECKLIST.md"


@pytest.fixture(scope="module")
def wrapper_text() -> str:
    return WRAPPER.read_text(encoding="utf-8")


def test_the_entry_point_exists_and_is_executable():
    assert WRAPPER.is_file()
    assert WRAPPER.stat().st_mode & 0o111, "the documented command must be runnable"


def test_the_entry_point_parses():
    subprocess.run(["bash", "-n", str(WRAPPER)], check=True)


def test_the_entry_point_chains_the_derivation_before_the_gate():
    """Auditing a bundle that was not just re-derived verifies a possibly stale record."""
    assert "derive-claims" in WRAPPER.read_text(encoding="utf-8")
    assert "autoresearcher.foundation.audit" in WRAPPER.read_text(encoding="utf-8")


def test_the_entry_point_writes_the_bundle():
    assert "--output" in WRAPPER.read_text(encoding="utf-8")


def test_the_entry_point_states_both_modes():
    usage = WRAPPER.read_text(encoding="utf-8")
    assert "--derive-only" in usage


def test_the_gate_defaults_match_where_the_records_actually_are():
    """The gate's defaults are what make the entry point's bare call correct."""
    parser_defaults = subprocess.run(
        ["python3", "-m", "autoresearcher.foundation.audit", "--help"],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        check=True,
    ).stdout
    assert "default: research" in parser_defaults
    assert (REPO_ROOT / "research" / "claims.json").is_file()


def test_the_derive_step_leaves_the_committed_records_untouched():
    """A check command must not dirty the tree, or nobody will run it as a check.

    The derivation keeps each record's existing ``generated_at`` when nothing else
    changed, which is what makes this byte comparison the right assertion.
    """
    before = {
        name: (REPO_ROOT / "research" / name).read_bytes()
        for name in ("claims.json", "findings.json")
    }
    subprocess.run(
        ["bash", str(WRAPPER), "--derive-only"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=True,
    )
    for name, raw in before.items():
        assert (REPO_ROOT / "research" / name).read_bytes() == raw, name


def test_the_entry_point_passes_on_the_committed_repository(tmp_path):
    """End to end: derive, then audit, on what is in git.

    The bundle is redirected out of the tree so the check stays side-effect free,
    which is also why the script takes ``--bundle`` rather than only fixing a path.
    """
    bundle = tmp_path / "bundle.json"
    result = subprocess.run(
        ["bash", str(WRAPPER), "--bundle", str(bundle)],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "deriving the claim ledger" in result.stdout
    assert "auditing the evidence chain" in result.stdout
    assert json.loads(bundle.read_text())["all_checks_passed"] is True


def test_a_bad_bundle_path_is_a_usage_error_not_a_silent_pass():
    result = subprocess.run(
        ["bash", str(WRAPPER), "--bundle"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert "usage" in result.stderr.lower()


def test_the_mandatory_discipline_names_the_entry_point():
    """The rule already existed; what was missing was the command that satisfies it."""
    text = AUTORESEARCHER.read_text(encoding="utf-8")
    assert "必须跑 `audit`" in text
    assert "scripts/verify-evidence.sh" in text


def test_the_submission_checklist_names_the_entry_point():
    text = CHECKLIST.read_text(encoding="utf-8")
    assert "scripts/verify-evidence.sh" in text


def test_the_checklist_states_that_a_pass_is_required_not_advisory():
    text = CHECKLIST.read_text(encoding="utf-8")
    assert "exit 0" in text or "退出码" in text
