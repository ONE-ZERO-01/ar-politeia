#!/usr/bin/env bash
# Verify the evidence chain and write the pre-submission bundle.
#
# This is the "声称可以投稿前必须跑 audit" step, in one command.  It exists because the
# gate takes a claim-to-evidence bundle as input, and that bundle is *derived* from
# the run records -- so auditing it without re-deriving it first would verify a
# record that may no longer match the runs it cites.  Chaining the two makes that
# mistake impossible, which is the point: the failure mode this guards against was
# not a wrong gate, it was a gate nobody noticed could not be satisfied.
#
# The gate is foundation code and knows nothing about how the bundle is produced;
# this script is the project-level glue, so that knowledge lives here and not in
# `src/autoresearcher/`.
#
# Usage:
#   scripts/verify-evidence.sh                     # derive, then audit
#   scripts/verify-evidence.sh --derive-only       # refresh the ledger, no audit
#   scripts/verify-evidence.sh --bundle out.json   # write the bundle elsewhere
#
# Exit codes: 0 = the audit passed, 1 = it did not, 2 = usage error.
set -euo pipefail

BUNDLE="research/reproducibility-bundle.json"
DERIVE_ONLY=0

while [ "$#" -gt 0 ]; do
  case "$1" in
    --derive-only) DERIVE_ONLY=1; shift ;;
    --bundle)
      if [ "$#" -lt 2 ]; then
        echo "usage: scripts/verify-evidence.sh [--derive-only] [--bundle <path>]" >&2
        exit 2
      fi
      BUNDLE="$2"; shift 2 ;;
    --bundle=*) BUNDLE="${1#--bundle=}"; shift ;;
    *) echo "usage: scripts/verify-evidence.sh [--derive-only] [--bundle <path>]" >&2; exit 2 ;;
  esac
done

cd "$(dirname "$0")/.."

DERIVER="research/src/experiments/prepare_cycle4_confirmation.py"

echo "== deriving the claim ledger from the run records =="
# The derivation refuses when a record does not corroborate the status the plan
# pre-registered, so a failure here is a real disagreement about what was found --
# not a formatting problem to work around.
python3 "$DERIVER" derive-claims >/dev/null

if [ "$DERIVE_ONLY" -eq 1 ]; then
  echo "refreshed research/claims.json and research/findings.json"
  exit 0
fi

echo "== auditing the evidence chain =="
python3 -m autoresearcher.foundation.audit --output "$BUNDLE"
