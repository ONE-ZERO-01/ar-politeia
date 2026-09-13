# Research state

```
current_stage = EXPERIMENT
cycle = 4
replan_from = cycle-3
```

This file is a human-readable stage summary for the single research plan under
`research/`. Orchestrator truth lives in `.autoresearcher/orchestrator/state.json`
and must not be overwritten from here.

Cycle 4 is a simulator-remediation and revalidation cycle. The implementation
scope and remaining checks are recorded in `research/simulator-improvement-plan.md`,
`research/simulator-review-and-repair-plan-2026-09-08.md`, and
`research/simulator-remediation-status.md`.

## Current status (2026-09-13)

- The Cycle 4 local remediation implementation is present in the working tree.
- Local non-numerical validation passes: 141 pytest tests, per-file C++ syntax
  checks, and `git diff --check`.
- The Cycle 3 plan is archived under `research/versions/cycle-3/`; the new
  Cycle 4 plan limits current execution to implementation validation.
- The next required step is to commit/push the remediation event and run
  OpenMP OFF/ON CMake builds plus CTest on `umi`.
- Non-flat timestep calibration and all new numerical evidence remain pending.
  No Cycle 4 confirmatory claim is currently supported.

## Cycle 3 E3 correction

`E3-ROBUSTNESS-HOLDOUT` is not running. Inspection of its authoritative `umi`
workspace found 240 planned run directories, 71 completion markers, 62 completed
runs, 9 runs that timed out at 10,800 seconds, and 169 runs that were never
attempted. The last marker was written on 2026-09-07. No aggregate robustness
analysis was produced.

The partial runs remain as provenance but must not be resumed or pooled into a
Cycle 4 conclusion: the simulator and analysis contract changed during the
remediation cycle. The tracked E3 result is therefore `incomplete`, not a null
scientific result and not evidence for C4-ROBUSTNESS.

## Evidence status

- Cycle 3 E0/E1/E2 outputs and the archived plan remain versioned historical evidence.
- Their earlier `supported` labels require reinterpretation under the simulator
  review, especially the flat-terrain calibration and E2 channel semantics.
- Cycle 4 uses new experiment IDs and will require a new non-degenerate calibration and a
  new parameter lock before any confirmatory execution.
