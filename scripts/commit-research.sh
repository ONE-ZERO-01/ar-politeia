#!/usr/bin/env bash
# Commit research results produced on the server (zeus/umi shared working copy).
#
# This is the "conclusions back to git" step. It stages only what `.gitignore`
# allows (code + important documents), so data — heavy workspace artifacts,
# compiled PDFs, and orchestrator run-state — is never committed.
#
# Usage (run on the server):
#   scripts/commit-research.sh "cycle(1): strategy=replan"
#
# The message must follow the git-workflow convention: a research event, not
# an agent action.
set -euo pipefail

if [ "$#" -ne 1 ]; then
  echo "usage: scripts/commit-research.sh '<commit message>'" >&2
  exit 2
fi

cd "$(dirname "$0")/.."

git add -A

if git diff --cached --quiet; then
  echo "nothing to commit (working tree clean or only ignored files changed)"
  exit 0
fi

echo "== staged files (data already excluded by .gitignore) =="
git diff --cached --stat | tail -40
echo
git commit -m "$1"
echo
echo "committed. On the local machine run: scripts/sync-research.sh"
