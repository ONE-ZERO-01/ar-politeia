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

## Current status (2026-09-14)

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
- V1 completed all 75 runs on umi with no execution failure. Invariants,
  timestep convergence, and storage-order sensitivity passed, but stationarity
  failed in 19/45 timestep runs and precision failed in 7/45; the overall V1
  verdict is failed and E1 remains blocked.
- V1D completed on umi and jobctl reconcile passed. Its 24/1-sigma baseline
  reproduced V1 exactly. A 2-sigma reversal rule removed almost all shape flags,
  but longer windows exposed genuine earlier drift and autocorrelation: the
  96/2-sigma timestep layer still failed stationarity in 28/45 runs and precision
  in 26/45. V1B is now frozen with independent seeds, total_time=2500, and the
  last-96-snapshot/2-sigma contract; its 75-run preflight passes.
- V1B completed 75/75 runs on umi with no execution failure and jobctl reconcile
  passed. It consumed 14.49 CPU-hours / 2.27 wall-hours. Invariants and the
  storage-order bound passed, but the overall Gate remained negative: the smooth
  Spearman fine-vs-finest bound was 0.02795 against a 0.02 ceiling; timestep
  stationarity failed in 8/45 runs and precision failed in 9/45.
- Extending the horizon reduced the 96/2-sigma stationarity failures from V1D's
  28/45 to 8/45 and precision failures from 26/45 to 9/45. Remaining failures
  are mostly isolated stochastic trajectories, including ESS values just below
  four, while requiring every metric in every replicate to pass creates a
  family-wise conjunction whose failure probability rises with sample size.
- V1BD completed on umi and jobctl reconcile passed. It exactly reproduced the
  V1B run-wise failures. All 9 condition ensembles passed stationarity in the
  final 96-snapshot window, whereas 6/9 remained below temporal ESS=4. The
  limiting smooth-Spearman timestep cell needs an estimated 14 independent
  replicates if its observed mean and variance persist.
- V1C completed 225/225 runs on umi without execution failure and jobctl
  reconcile passed. It consumed 45.38 CPU-hours / 6.24 wall-hours. Invariants,
  all non-flat timestep bounds, and all storage-order bounds passed; numerical
  resolution limits are 0.00673 (Spearman), 0.00997 (Moran), 0.00252 (entropy),
  and 0.00214 (Gini).
- V1C is nevertheless a valid negative calibration. The smooth, dt=0.02
  Spearman ensemble failed drift and ESS, so stationarity failed in 1/9
  conditions. Six of nine conditions failed the frozen temporal ESS precision
  requirement, with all precision failures caused by ESS below four. E1 remains
  blocked while V1CD diagnoses equilibration drift versus temporal and
  between-replicate precision on the fixed V1C outputs.
- V1CD completed and reconciled on umi. It reproduced the V1C tail verdict
  exactly. The previous-to-tail comparison improved from 3/9 to 1/9
  stationarity failures, and all 36 paired window-shift bounds were within the
  pre-existing planning widths. Independent-seed precision passed 30/36 cells;
  the six clustered Moran/entropy cells imply at most 20 seeds.
- V1E is now design-frozen before new data: 20 unseen seeds, total_time=4500,
  two adjacent 144-snapshot windows, temporal dynamics separated from
  independent-seed precision, and the unchanged timestep/storage-order bounds.
  The runner is implemented and V0E passed on umi: Python 152/152 and OpenMP
  OFF/ON CTest 7/7. Jobctl reconcile completed, so V1E is ready to execute; E1
  stays blocked until its result passes every Gate.
- V1E preflight passed 8/8, its V0E reference binary checksum was verified, and
  the 300-run job was submitted on umi under jobctl pid 1914738 with eight
  single-thread processes and a 36-hour overall timeout.
- V1E completed 300/300 runs on umi with no execution failure and reconciled
  successfully. It consumed 103.51 CPU-hours / 14.64 wall-hours. Invariants,
  timestep convergence, storage-order sensitivity, all 9 tail-stationarity
  cells, and all 9 adjacent-window cells passed.
- V1E remains a valid negative calibration: independent-seed precision failed
  in 6/9 conditions and 12 metric cells (clustered Moran/entropy/wealth
  variance and shuffled wealth variance). The limiting observed cell requires
  38 replicates if its moments persist. V1ED must quantify sampling uncertainty
  before a new independent design; E1 remains blocked.
- V1ED completed and reconciled on umi, reproducing the V1E Gate exactly. The
  maximum point requirement is 38 seeds; a one-sided 90% upper-SD calculation
  gives 61, so the frozen next-power-of-two policy selects 64. V1F is now
  design-frozen with 64 unseen seeds and the unchanged V1E process.
- V0D then passed on umi: Python 148/148 and OpenMP OFF/ON CTest 7/7; the
  rebuilt reference binary exactly matches V0C by SHA-256. V1C preflight passes
  8/8 and all execution prerequisites are now satisfied.
- The numerical error bounds are now empirically resolved, but the steady-state
  premise remains unvalidated. No Cycle 4 confirmatory claim is currently
  supported.

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
