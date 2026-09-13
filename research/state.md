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

- The Cycle 4 remediation and V1 validation infrastructure are committed.
- Local non-numerical validation passes: 147 pytest tests, per-file C++ syntax
  checks, and `git diff --check`.
- The Cycle 3 plan is archived under `research/versions/cycle-3/`; the new
  Cycle 4 plan limits current execution to implementation validation.
- V0B implementation validation passed on umi: Python 141/141 and CTest 7/7
  with OpenMP disabled and enabled; jobctl reconcile completed.
- V1 now has a registered two-layer design: non-flat weak timestep convergence
  plus a deterministic, full-phase-state storage-order diagnostic. The next Gate
  V0C passed on umi (Python 147/147 and both CTest builds 7/7). The next Gate
  V1P then completed three capped runtime profiles in 2.80 seconds. The frozen
  75-run target is estimated at 3.47 CPU-hours, or 0.43 wall-hours at eight-way
  parallelism with a 1.5 safety factor.
- Full V1 is frozen and preflight passes 8/8. On 2026-09-13 the user authorized
  unrestricted project compute, including multi-process CPU and GPU resources.
  V1 will use the validated CPU reference with eight single-thread processes;
  its point estimate is 3.47 CPU-hours / 0.43 wall-hours.
- Non-flat timestep calibration and all new scientific evidence remain pending.
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
