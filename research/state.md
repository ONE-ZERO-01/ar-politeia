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

## Current status (2026-09-16)

- The Cycle 4 remediation and V1 validation infrastructure are committed.
- Current non-numerical validation passes locally and through the umi validation
  runner: 164 pytest tests, OpenMP OFF/ON CTest 7/7, and `git diff --check`.
  The umi runner self-test used a clean checkout and its own recorded
  `PYTHONPATH`, without relying on a prior editable install.
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
- V0D then passed on umi: Python 148/148 and OpenMP OFF/ON CTest 7/7; the
  rebuilt reference binary exactly matches V0C by SHA-256. V1C preflight passed
  8/8 before V1C execution.
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
- V0F passed on umi: Python 153/153 and OpenMP OFF/ON CTest 7/7. The rebuilt
  CPU reference retained SHA-256 `87eafa4e...ddee3`, clearing V1F's
  implementation block.
- V1F preflight passed 8/8 with no warning, and its V0F CPU reference checksum
  was verified. The 960-run job was submitted on umi at 2026-09-15 10:01:13
  +08:00 under jobctl pid 2647912. All run directories were created, eight
  single-thread simulator processes entered execution, and the startup check
  found zero non-empty stderr files. The overall timeout is 72 hours.
- The Cycle 4 promotion path is now deterministic and outcome-guarded.
  `prepare_cycle4_confirmation.py prepare` accepts only a hash-bound passing
  960-run V1F result and emits a non-authorizing candidate lock plus V0G/E1-C4
  declarations. `finalize` requires a clean umi V0G run with Python and OpenMP
  OFF/ON CTest passing, then binds the rebuilt reference binary SHA-256 and
  authorizes E1. The E1-C4 runner now rejects a missing or mismatched binary
  checksum before numerical execution. V0G also binds `PYTHONPATH` to the clean
  checkout's `src/` and records it in `environment.json`, so validation no
  longer depends on an earlier editable install; the full local suite is
  164/164.
- V1F post-run archival is now deterministic. Promotion command `archive-v1f`
  requires an exact 960-way match across run specs, completion markers and
  health files, a clean jobctl result, one OMP=1 reference-binary checksum,
  passing input audit, and mutually consistent calibration/steady reports
  before writing tracked calibration, result and manifest evidence. The full
  local suite is now 165/165.
- The numerical error bounds are now empirically resolved, but the steady-state
  premise remains unvalidated. No Cycle 4 confirmatory claim is currently
  supported.
- WP0's model-specification deliverable is written:
  `research/model-specification-c4.md` records the actual implemented process
  (per-step stage order, BBK integration and reflection boundaries, the
  Berendsen thermostat with its two correction regimes, the exchange formula and
  its boundary policy, deterministic per-pair random signs keyed by stable GIDs,
  serial in-place update order, and the production-decay bundle), the causal
  graph including the **absent** `w -> (x, p)` edge, the support matrix, and the
  disposition table for older evidence. This closes the documentation part of
  S01 and S09. Source-level facts confirmed while writing it: `exchange_halos`
  has no call site in `main.cpp`; `ability_saturation_w` defaults to 5.0,
  exactly the configured mean wealth; the V1F `order` layer runs at
  `temperature = 0.0` while the `timestep` layer runs at 0.5.
- E1-C4's frozen seed-disjointness claim was re-verified by bookkeeping across
  every tracked `seeds.txt` and job config: the 64 frozen E1-C4 seeds have zero
  intersection with all Cycle 1-3 jobs and with V1/V1B/V1C/V1E/V1F/V1P.
- V1F is still running on umi under jobctl pid 2647912. At 2026-09-16 23:14
  +08:00 it had completed 875/960 runs with zero non-empty stderr files and zero
  thermostat triggers; at 13:17 it was at 640/960 and at 19:16 at 789/960,
  consistent with the 41.4 wall-hour estimate. E1 stays blocked until it passes,
  is archived by `archive-v1f`, and the promotion `prepare`/`finalize` chain
  produces the final Cycle 4 lock.
- S09's identifiability defect is now located and the E2-C4 design is frozen in
  `research/e2-cycle4-channel-design.md`. A structural audit of Cycle 3's 160
  archived E2 runs showed: the `production` factor switched both
  `terrain_production_enabled` and `wealth_decay_rate`; the production-off cell
  is a degenerate state (zero-sum exchange, mean wealth exactly 5.0) while the
  production-on cell is drained to `min wealth ≈ 1e-07`, putting `w/w_ref` at
  about 0.05 and 0.19 and therefore a different exchange-regime operating point;
  the three spatial metrics are **string-identical** across the production factor
  on every one of the 40 (seed, force) pairs, so the reported spatial null is a
  structural identity rather than a finding; and all four cells passed the old
  stationarity Gate, which cannot detect cross-cell non-comparability. The design
  replaces the impossible source x sink on/off factorial (two of its four cells
  have no stationary distribution) with a source-pattern ablation and a sink-rate
  response along a constant `s/d` line.
- **S12 (new, P0): the reference process runs deep in the sub-saturation regime
  and the movement channel leaks into the wealth scale.** Measuring mean wealth
  on the final snapshot of completed V1F runs (59 paired seeds, `dt = 0.005`):
  clustered 1.9838, shuffled 1.3810, smooth 0.5918, i.e. `w/w_ref` = 0.397,
  0.276, 0.118, with a paired clustered-minus-shuffled difference of **+43.6%**
  (2SE half-width 4.5%; `dt = 0.02` gives +44.3%). So the design intent
  (`initial_wealth = mean_wealth = 5.0 = w_ref`, the half-saturation point) is not
  where the process actually sits: `A = eps*w/(w + w_ref)` is nearly linear in
  `w` there, weakening the channel by which ability heterogeneity becomes
  exchange advantage. `min wealth` reaches 1e-05 to 1e-13, so the `[0,1]` share
  clamp is active at confirmatory scale. And because force on concentrates
  particles in resource wells, raising `sum(prod)`, the equilibrium level differs
  by ~3.4x between force on and off, so any wealth outcome mixes spatial
  organisation with a shift in the wealth scale.
- Consequences of S12. On the E1-C4 side the primary family is position-based and
  therefore unaffected, so its Gate and thresholds are unchanged, but the
  wealth-Gini secondary family is now pre-registered in `e1-cycle4-readiness.md`
  as a composite of spatial organisation and equilibrium wealth-scale shift, and
  `mean_wealth` plus `wealth_scale_ratio` must be reported alongside
  `result.json`. That only narrows interpretation and relaxes no threshold, so it
  does not invalidate the V1F calibration. On the E2-C4 side all cells now run
  with terrain force off, which makes positions exogenous and bit-shared across
  cells (an identity already confirmed bitwise on E2's 40 (seed, force) pairs),
  turning the spatial metrics from outcomes into identity guards; the uniform
  source comes from the `flat` landscape (constant exactly at the mean), so no
  C++ change is needed and the reference binary SHA is untouched.
- Reading mean wealth during the V1F run is disclosed as a protocol deviation in
  both `e1-cycle4-readiness.md` and `e2-cycle4-channel-design.md` section 5. The
  quantity read is a non-primary structural one, the purpose was to check a design
  premise (the original comparability target of `w_ref = 5` turned out
  unreachable), and the resulting action narrows rather than widens any claim.
  V1F's `numerical_calibration.json` has not been read.

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
