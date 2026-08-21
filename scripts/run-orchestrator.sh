#!/usr/bin/env bash
# Launch the AutoResearcher orchestrator on the zeus control plane.
#
# The orchestrator and its Codex CLI agent adapters run on `zeus`, which has
# full internet access for the LLM provider (DeepSeek). Numerical experiments
# still run on `umi` and are routed there by the experiment worker.
#
# Usage:
#   scripts/run-orchestrator.sh [graph-path] [extra orchestrator args...]
#
# Defaults to orchestration/research-graph.json. Ensures node/codex are on PATH
# and loads the DeepSeek key from ~/.codex/deepseek.env (chmod 600, outside git).

set -euo pipefail

if [ -d "$HOME/.local/node/bin" ]; then
  export PATH="$HOME/.local/node/bin:$PATH"
fi

if [ -f "$HOME/.codex/deepseek.env" ]; then
  # shellcheck disable=SC1091
  source "$HOME/.codex/deepseek.env"
fi

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
export PYTHONPATH="${ROOT_DIR}/src${PYTHONPATH:+:${PYTHONPATH}}"

GRAPH="${1:-orchestration/research-graph.json}"
shift || true

exec python3 -m autoresearcher.orchestration run "$GRAPH" "$@"
