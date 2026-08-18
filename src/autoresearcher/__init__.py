"""AutoResearcher — multi-agent research orchestration with reproducibility gates.

The orchestration package executes isolated agent and deterministic gate nodes
as a crash-resumable DAG. Foundation tools remain independently callable.

Tools:
- preflight: reproducibility checks before submitting an experiment.
- jobctl:   idempotent job submission, status queries, and crash recovery.
- audit:    evidence-chain validation before submission.
- autoresearcher-graph: multi-agent DAG validation, execution, and recovery.
"""

__version__ = "0.4.0"
