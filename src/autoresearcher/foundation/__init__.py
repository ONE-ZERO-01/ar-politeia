"""Foundation tools for reproducible research.

These tools have standalone CLIs and are also used by the main
AutoResearcher state machine at experiment and submission boundaries.

Tools:
- preflight: reproducibility checks before submitting an experiment.
- jobctl:   idempotent job submission, status queries, and crash recovery.
- audit:    evidence-chain validation before submission.
"""

__version__ = "0.4.0"
