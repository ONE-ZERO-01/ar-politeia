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

## Current status (2026-09-17)

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
- **V1F completed and passed every frozen Gate.** On 2026-09-17 08:09 +08:00 the
  960-run job finished 960/960 runs with zero run failures in 166,076 wall-seconds
  (46.13 h) and 340.95 CPU-hours, zero non-empty stderr files, and one OMP=1
  reference-binary checksum. `archive-v1f` then cross-checked run specs, completion
  markers, health files, the jobctl record, the reference binary and the
  calibration/steady reports, and wrote tracked evidence
  (`research/jobs/V1F-NONFLAT-CALIBRATION-C4/{result,manifest,numerical_calibration}.json`).
- **All six numerical Gate layers pass**: invariants, timestep convergence,
  storage-order sensitivity, tail stationarity, adjacent-window stability, and
  independent-replicate precision. The 9 conditions x 64 replicates fail no cell
  on tail stationarity, adjacent-window stability or independent precision. The
  temporal-ESS diagnostic still flags 8/9 conditions but is a diagnostic layer, not
  a Gate, by the frozen design.
- **Numerical resolution limits**: Spearman 0.0045900, Moran's I 0.0032588,
  occupancy entropy 0.00099482, wealth Gini 0.0014408. All are roughly one order of
  magnitude below the frozen scientific SESOI (0.05/0.05/0.025/0.025), so the
  effective E1-C4 thresholds are the SESOI values.
- **The promotion chain produced the final Cycle 4 parameter lock.** V0G passed on
  umi on a clean checkout (Python suite and OpenMP OFF/ON CTest), and `finalize`
  bound the reference binary and authorized `E1-MATCHED-LANDSCAPES-C4`. The lock is
  `research/parameter_lock.cycle4.json` (`ar-politeia-cycle4-confirmatory-v1`,
  status `final`, `confirmatory_execution_authorized = true`), with
  `source_commit = b6d24b76a50529965469332644e7bed251c49eb1`. E1-C4 is therefore
  unblocked.
- **S14 (new, P0): `finalize` silently bound a binary that was not the calibrated
  one.** V1F's numerical resolution limits were measured by executing the reference
  binary `87eafa4e...ddee3`. But commit `0f4ac29` (2026-09-15 21:35), made after
  V1F was submitted (2026-09-15 10:03) and while it was still running, changed
  `research/src/experiments/politeia/src/io/ic_loader.cpp`; V0G therefore rebuilt
  `1e3f052f...b43b` and `finalize` accepted it, writing a lock whose calibration and
  executable did not correspond. The change is semantically inert (it constructs the
  identical culture column name), so it could not alter simulation behaviour, but it
  did alter the artifact. Two structural gaps allowed it: `validate_build` records
  no SHA of the binary under test, and the candidate lock carried no SHA of the
  calibrated binary, so no gate was in a position to judge the binding.
- **S14 remediation.** `validate_v1f` now reads and validates the calibrated
  `binary_sha256` from the V1F archive; the candidate lock carries it as
  `numerical_calibration.reference_binary_sha256`; and `finalize` refuses unless the
  bound binary lies inside the V0G workspace and its SHA-256 equals that reference.
  The offending source hunk was reverted so the simulator tree is byte-identical to
  the calibrated commit (`git diff 48ad02a -- research/src/experiments/politeia/` is
  empty), and V0G's rebuild empirically reproduced `87eafa4e...ddee3` — so the
  binding is now a verified identity, not an argued equivalence, and no 340
  CPU-hour V1F rerun was needed. The compiler-warning fix is deferred until after
  E1-C4. This is exactly the class of unmeasured equivalence assumption the project
  has been eliminating (compare S01, S09).
- **S13 (new, P1): the V1F job declaration was malformed.** Its `jobctl` spec
  declared eight artifacts as bare basenames, which the worker resolves against
  `spec.cwd` (the project root) rather than the job workspace, so all eight were
  recorded `valid: false` 46 hours later. Peer jobs V1E/V0E/V0F used full
  project-root-relative paths, so this was a declaration error, not lost output;
  `archive-v1f` independently validated the workspace and passed. `jobctl` now
  fails fast when a declared artifact escapes the submission cwd or is duplicated,
  records the resolved absolute path for each artifact (so a misdeclaration is
  visible instead of appearing as a missing file), and gained a `recheck` action
  that recomputes a completed job's artifact contract from the stored declaration
  while preserving every execution fact and recording the previous verdict as
  provenance. V1F's declaration was corrected and now reconciles as `completed`
  (execution facts unchanged: exit 0, 46.13 h).
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
- The E2-C4 authorisation prerequisite for fresh, mutually exclusive seeds is now
  met by a new `seeds-audit` subcommand
  (`research/src/experiments/prepare_cycle4_confirmation.py`). It replaces a gap:
  preflight only checked that `seeds.txt` exists and is non-empty, and the E1-C4
  helper guarded only E1's own 64 seeds through `config.json` alone. The audit
  reads three channels per job: a top-level `seeds`/`seed` field, a `seeds.txt`
  list, and `seed-<n>` tokens inside run identifiers. Top-level fields and
  `seeds.txt` are declarations of what a job drew, so they count as consumption; a
  nested declaration such as V1P's `target_design.seeds` names a design the job
  points at, so it is recorded as a reference. Run-identifier tokens count as
  consumption by default, with an explicit register for jobs whose tokens label
  upstream runs instead. That default fails closed on purpose: over-counting can
  only raise a spurious overlap that forces a declaration, whereas under-counting
  would hide a real reuse. The ledger now holds 211 distinct seeds across 28 jobs
  and 91 overlap groups in three components; unregistered reuse fails the audit,
  and E2-C4 is deliberately absent from the register so it cannot silently reuse
  one. A job that records no seed provenance at all must hold a `seed_waiver.txt`,
  and the 10 such waived jobs are listed explicitly so the ledger's coverage is
  visible rather than implied. Two historical accounting defects are recorded
  without rewriting them: seed `1103` is shared by `E0-NUMERICS` and
  `E1-MATCHED-LANDSCAPES`, and `6407`, `6503` (V1) and `9071` (V1C) are not prime.
  Each authorisation now carries a machine-verified basis instead of prose: a
  same-`experiment_id` re-execution, a citation to a tracked document that must
  still contain the declaring text, or disjointness from the evidence-bearing seed
  set. That last property is the one that actually makes the historical collisions
  tolerable, and it is re-derived on every run: the 24 grandfathered seeds (all
  <= 5519) are disjoint from the 174 evidence seeds (minimum 6007). Two earlier
  component justifications did not survive this re-check and were rewritten: the
  B0 jobs are one experiment recorded three times rather than a deliberate seed
  freeze, and the E0/E1/E2 collision was never written down as a decision at all.
  Primality was checked against the code rather than assumed: `random_seed` only
  initialises `mt19937_64` streams and serves as the base of `rank`-derived
  offsets, so nothing depends on the base being prime; the primes in the codebase
  are offsets, and the convention was carried over to base selection with no
  recorded rationale. Uniqueness is the only requirement that can be demonstrated.
  The available-pool window is left unset on purpose
  (`--pool-min/--pool-max` have no defaults) because that boundary must be frozen
  explicitly alongside R.
- Reading mean wealth during the V1F run is disclosed as a protocol deviation in
  both `e1-cycle4-readiness.md` and `e2-cycle4-channel-design.md` section 5. The
  quantity read is a non-primary structural one, the purpose was to check a design
  premise (the original comparability target of `w_ref = 5` turned out
  unreachable), and the resulting action narrows rather than widens any claim.
  V1F's `numerical_calibration.json` has not been read.
- E1-C4, the Cycle 4 confirmatory matched-landscape run, completed on umi:
  128/128 runs, 0 failures, 34.97 CPU-hours over 18,512 s wall, and a longest
  single run of 3,655 s. All six analysis gates passed, and the paired
  clustered-minus-shuffled effects exceed the frozen SESOI on all three required
  spatial metrics: `resource_density_spearman_rho` +0.2297, `density_morans_i`
  +0.5525, `occupancy_entropy` -0.0818, each Holm-significant at p=3.0e-5. None
  of C2-LANDSCAPE-C4's pre-registered falsification conditions hold, so the claim
  is supported at the calibrated reference configuration. The secondary
  `wealth_gini` effect is +0.00303 with an interval containing zero, consistent
  with the registered S12 synthetic-effect caveat. System-size, density,
  grid-discretization and holdout-landscape generalisation remain with
  C4-ROBUSTNESS-C4 (deferred). The `temporal_ess` diagnostic is false, which the
  frozen policy registers but does not gate on.
- E1-C4's verdicts are now archived in git. The promotion module shipped without
  an E1 archival path, so the only complete copy of the result lived in the
  git-ignored umi workspace; a new `archive-e1` command closes that exposure. It
  is a validation-and-compaction step only: it recomputes no effect, applies no
  threshold, copies the verdict byte-for-byte, and can only refuse. Beyond the
  V1F checks it binds every completion marker to its final-snapshot digest and
  requires `analysis_gate_pass` to equal the conjunction of its six gates. The
  contract was authored after the run finished; that deviation is recorded in
  `simulator-remediation-status.md` section 4.9, and because it changes no model,
  threshold, required metric or analysis it does not trigger the `change_control`
  clause and requires no new lock.
- `plan.json` now matches the evidence: V1F, V0G, V1G, V1H and E1-C4 are
  `executed_passed`/`completed`, C1-NUM-C4 and C2-LANDSCAPE-C4 are `supported`,
  and C3-CHANNELS-C4 / C4-ROBUSTNESS-C4 remain pending and deferred. S18 is
  **closed**: V1G-ORDER-THERMAL-C4 returned `bounded`, so the frozen
  storage-order bound does cover the thermal-noise/row-order coupling at the
  reference temperature. The verdict carries two pre-registered reservations —
  `occupancy_entropy` uses 88% of its frozen limit (the tightest of the four),
  and 12 of 128 runs fail the per-run steady-window checks, which the design
  excludes from the verdict but which the bound inherits.
- V1H-CALIBRATION-EXTENSION-C4 extends the Cycle 4 numerical limits to
  `wealth_variance` without new simulation. It re-analyses V1F's retained
  `replicate_metrics.csv` with V1F's own bound routine and reproduced all four
  frozen limits bit for bit (0 mismatched fields out of 144), which is what makes
  the new limit a continuation of V1F's measurement rather than a second,
  unrelated one. The added limit is `wealth_variance = 0.0568`, bounded by
  discretization rather than by storage order. No ceiling was frozen: a ceiling is
  a pre-registered failure threshold, so it is left to be frozen with the
  scientific SESOI instead of being written after seeing the data. This is the
  last missing prerequisite for E2-C4's P2 estimands (`wealth_gini` from V1F,
  `wealth_variance` from V1H); what remains before the E2 lock is the seed-pool
  window, the pilot, and R.
- Two bookkeeping gaps closed alongside V1H, both of which had the same shape: a
  number existing only outside git. `record-calibration-extension` promotes a
  calibration extension's artifact into the job dir and derives `result.json` and
  `manifest.json` from it, verifying against the *source artifact on disk* rather
  than trusting the extension's self-report — it refuses a pin that does not match
  the file, a rewritten or silently skipped frozen limit, an extension that adds
  nothing or re-freezes an existing metric, and a post-hoc ceiling. Separately,
  V1H's `seed_waiver.txt` now lists the 64 V1F seeds that its jobctl submission
  declared, with a test binding that list to V1F's own `seeds.txt`: the ledger only
  checks that a waiver exists, so a fabricated provenance list could otherwise sit
  in git unnoticed — a local draft of that list was in fact wrong, and the test is
  what caught it.
- E2-C4's remaining thresholds are decided (2026-09-18), via the criteria brief in
  `e2-cycle4-sesoi-decision.md` whose section 9 records the choices and section 10
  corrects one of them, and the pilot is pre-registered in `e2-cycle4-pilot-design.md`.
  `scientific_sesoi` for `wealth_gini` stays the absolute 0.025 carried over from
  E1-C4. `wealth_variance` takes the *relative* rule `delta := 0.50 * Var_ref`, with
  `Var_ref` read from the P2 arm of the non-evidentiary pilot — a rule rather than a
  number because the metric is scale sensitive, and the pilot is the only thing that
  can fix the reference level without reading an effect. The relative coefficient has
  a floor, and getting that floor right took a correction: the first version used
  `(1.10)^2 - 1 = 0.21`, the drift of a *single* unit within P4's +/-10% band, but P4
  constrains each unit relative to the group mean, so two contrasted units can drift
  to opposite edges and the contrast sees `4*beta / (1 + (2/3)*beta^2)` = 0.3974 at
  beta = 0.10. The initially chosen rho = 0.25 sat *below* that, which would have let
  a P4-passing, purely level-driven contrast cross the threshold on its own — with
  R = 64 the paired CI half-width is about 0.125*Var_ref against a 0.397*Var_ref
  drift, so the whole interval shifts past the threshold and Holm then calls it
  supported. The ratio was therefore raised to 0.50 the same day: +26% margin, which
  is there because the floor assumes drift is a pure rescale. Cheaper too, since
  R scales as 1/rho^2 (64 -> 16 at q = 0.5); what it costs is sensitivity in the
  0.25-0.50 band, whose effects are not attributable under the frozen band anyway.
  P4's guards are `zero_wealth_fraction <= 0.01` and a +/-10% relative band on mean
  wealth, and `wealth_variance`'s level floor is V1H's 0.056828569227561854 — quoted
  as an analogy (a difference bound used as a level bound), not a derivation. No
  ceiling is frozen for the new metrics: the SESOI *is* the failure threshold, so
  giving the same quantity two adjustable definitions is exactly what is avoided.
  Landed as machine-readable policy in `plan.json` (`analysis_policy.sesoi_policy`
  and `.comparability_policy`) and enforced in code by
  `validate_e2_c4_sesoi_derivations`: declaring the metric's threshold without a
  derivation, `ratio <= floor(band)`, an absolute that is not `ratio * Var_ref`, a
  reference report whose sha256 does not match, a re-anchored reference field, or a
  relative rule on the scale-invariant `wealth_gini` are all refusals. The rule,
  the reference reading and its provenance are recorded in `threshold_components`
  so the derivation stays checkable. What remains before the E2 lock is the
  seed-pool window (`12300-13000`), the non-evidentiary pilot, and R.

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
