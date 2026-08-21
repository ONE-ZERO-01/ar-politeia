#!/usr/bin/env bash
# Pull committed research results (code + important documents) from the umi
# server into the local git-authority working copy.
#
# Data never crosses this boundary because the server-side commit step (and
# `.gitignore`) excludes workspace artifacts, compiled PDFs, and run-state.
set -euo pipefail

cd "$(dirname "$0")/.."

echo "== fetching umi =="
git fetch umi
echo "== merging umi/main =="
git merge --ff-only umi/main || git merge umi/main
echo
echo "synced. local HEAD: $(git rev-parse --short HEAD)"
