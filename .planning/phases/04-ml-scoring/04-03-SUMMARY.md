---
phase: 04-ml-scoring
plan: 03
subsystem: ml
tags: [walk-forward, heuristic, evaluated, retrain-cli, label-gate, artifact, wave-3]

requires:
  - phase: 04-ml-scoring plan 01
    provides: FEATURE_SPEC/FEATURE_NAMES + frozen Config ml_* knobs + ml.features.build_feature_frame + ml.audit (run/write_feature_audit)
  - phase: 04-ml-scoring plan 02
    provides: ml.purge.purged_train_mask + ml.folds.calibration_folds + ml.train (decided_mask/preflight_reason/fit_calibrated/reliability_curve) + ml.artifact (build_bundle/save_artifact) + ml.scorer
provides:
  - ml/heuristic.py WEIGHTS + HEURISTIC_VERSION + normalize + heuristic_score (Pattern 6 flagged non-ML bootstrap)
  - ml/evaluate.py EvalResult + run_walkforward_eval (per-window train-or-skip, decided-only headline, flagged TIMEOUT, provenance)
  - ml/runner.py run_ml_pipeline + main (python -m ai_trading.ml; label-count gate; {2,1,0} exit contract; --train/--eval/--write)
  - ml/__main__.py module entry mirroring backtest/__main__.py
  - on-disk layout: data/reports/ml_{walkforward,reliability,scores}.parquet + feature_audit.json; data/models/pooled/v{N}/ + LATEST.json on --train
affects: [Phase 5 LLM (P(WIN) + contributors + score_source/provenance), Phase 6 dashboard/setup (loadable artifact + heuristic-flagged rows)]

tech-stack:
  added: []   # no new deps; lightgbm/scikit-learn/joblib inherited from Wave 0
  patterns:
    - "Pattern 6 heuristic bootstrap: deterministic logistic of weighted normalized-goodness over the FEATURE_SPEC vector; smaller-is-better terms inverted; missing->0; never enters ML headline metrics"
    - "Pattern 5 skip contract: a starved/single-class window records status=skipped + stable reason (never raises, never fabricates) and its span is heuristic-scored"
    - "D-01/D-02 score-and-flag: decided-only headline metrics (AUC/log-loss/Brier); TIMEOUT rows scored with excluded=True + score_source/provenance on every row"
    - "Harness-only splitter: windows + window assignment come exclusively from backtest.walkforward (AI-04/SC3) — no new splitter in the ML tier"
    - "Atomic report persistence: tmp + os.replace with deterministic filenames (ml_walkforward/ml_reliability/ml_scores.parquet + feature_audit.json); run metadata only in the summary/log layer"
    - "Data-root resolve-under guard on labels/reports/models dirs (T-04-06); label store unpickled-free (parquet only), schema-validated before concat"

key-files:
  created:
    - src/ai_trading/ml/heuristic.py
    - src/ai_trading/ml/evaluate.py
    - src/ai_trading/ml/runner.py
    - src/ai_trading/ml/__main__.py
    - tests/unit/test_ml_heuristic.py
    - tests/unit/test_ml_evaluate.py
    - tests/unit/test_ml_runner.py
  modified: []

key-decisions:
  - "WEIGHTS uses all-positive magnitudes on normalized goodness (recency/risk/regime inverted to 'smaller better'); inversion encodes the sign, so monotonicity in rr_at_decision is structurally pinned"
  - "heuristic.logistic of the weighted sum is computed vectorized (no per-row Python loop); HEURISTIC_VERSION moves with ml_feature_list_version"
  - "run_walkforward_eval returns a singular EvalResult (report/reliability/scores); the scores artifact is exactly one row per label row with score_source + provenance + excluded — a score without provenance is treated as a bug"
  - "run_ml_pipeline gates the artifact save on --write as well as --train: without --write the run is a dry-run that persists nothing (matches the plan's dry-run test)"
  - "Feature audit (SC1) runs on every training run and is aggregated per-symbol into one payload (max_abs_diff=max, n_labels_checked=sum); feature_spec_hash/spec_table are spec-global"
  - "The traversal guard mirrors backtest._output_dirs (resolve-under-root); its only natural trigger is a directory reparse point, so the named test skips on platforms without symlink support"

requirements-completed: [AI-04, AI-02]

coverage:
  - id: D1
    description: "Deterministic flagged non-ML heuristic bootstrap (WEIGHTS + normalize + heuristic_score) — [0,1], missing-safe, spec-keyed, versioned, never in ML headline metrics"
    requirement: AI-02
    verification:
      - kind: unit
        ref: "tests/unit/test_ml_heuristic.py (6 named): determinism, unit range, missing->zero, rr monotone, spec-keyed weights, pure/no-io"
        status: pass
    human_judgment: false
  - id: D2
    description: "Walk-forward eval (EvalResult + run_walkforward_eval) — decided-only headline metrics, TIMEOUT scored+excluded (D-01/D-02), skip-and-record starvation with heuristic span coverage, provenance on every row, harness-only splitter"
    requirement: AI-04
    verification:
      - kind: unit
        ref: "tests/unit/test_ml_evaluate.py (9 named): decided-only headline, TIMEOUT flag, single-class nan, starved skip, heuristic span, every label scored, reliability per-window+pooled, input purity+sorted, no shuffled splits"
        status: pass
    human_judgment: false
  - id: D3
    description: "Retrain CLI (run_ml_pipeline + main / python -m ai_trading.ml) — label-count gate with actionable refusal, {2,1,0} exit contract, --train versioned bundle + LATEST, atomic report + audit writes, dry-run"
    requirement: AI-04
    verification:
      - kind: unit
        ref: "tests/unit/test_ml_runner.py (8 passing): missing labels dir, gate refusal counts+threshold, missing mode, config error, full train artifacts, eval mode, dry run, all-windows-skipped"
        status: pass
    human_judgment: false

# Metrics
duration: ~40 min
completed: 2026-09-04
status: complete
---

# Phase 4 Plan 3: Walk-Forward Eval Reports + Heuristic Bootstrap + Retrain CLI Summary

**Deterministic flagged non-ML heuristic bootstrap, decided-only walk-forward eval with score-and-flagged TIMEOUTs, and a label-gate-guarded retrain CLI (`python -m ai_trading.ml`) that writes the SC1 audit artifact, the SC4 versioned bundle, and three atomic report parquets — all over the Phase 3 harness windows.**

## Performance

- **Duration:** ~40 min
- **Started:** 2026-09-04T00:00:00Z (session start)
- **Completed:** 2026-09-04T00:38:38Z
- **Tasks:** 3 (all `type="auto"`, tasks 1-2 `tdd="true"`)
- **Files created:** 7 (4 source, 3 tests)

## Accomplishments

- **Pattern 6 heuristic bootstrap (`ml/heuristic.py`).** `WEIGHTS` (all-positive magnitudes on a normalized "goodness" — recency/risk/regime terms inverted so smaller-is-better maps closer to 1) keyed by six FEATURE_SPEC numeric names with an inline rationale each; `normalize(value, feature_name)` maps a scalar to [0,1] goodness (missing→0); `heuristic_score` returns the logistic of the weighted goodness sum, clipped to [0,1], vectorized (no per-row loop). Missing numeric features contribute exactly zero (score = logistic(0) = 0.5); `HEURISTIC_VERSION` ties to `ml_feature_list_version`.
- **D-01/D-02 walk-forward eval (`ml/evaluate.py`).** `run_walkforward_eval(labels, features, windows, cfg) -> EvalResult(report, reliability, scores)` validates the feature↔label row alignment invariant, assigns every label to exactly one harness window, and per window either trains (`fit_calibrated` on the purged-decided train slice with harness-derived calibration folds) or records `status="skipped"` + stable reason and covers the span heuristically. Headline metrics (AUC/log-loss/Brier) are computed on decided rows only with nan guards (single-class test slice); TIMEOUT rows are scored-and-flagged `excluded=True` (D-02) and never contaminate metrics. Every score row carries `score_source` + `provenance` + `artifact_version`; the reliability artifact carries per-window + pooled (`window_id=-1`) rows.
- **Pattern 5 skip contract.** A starved/single-class window never raises and never fabricates a model — it records `status="skipped"` (reason from `preflight_reason`) and its test span is heuristic-scored (`score_source="heuristic"`), keeping every candidate row scoreable on thin data.
- **Label-count gate + retrain CLI (`ml/runner.py`, `ml/__main__.py`).** `python -m ai_trading.ml --config --train|--eval [--write]` loads the label store (schema-validated, never a second Parquet writer), refuses starvation data with an actionable message naming the observed decided/wins/losses counts, `cfg.ml_min_train_labels`, and the Phase-3-backtest + Phase-1-backfill remedy (D-05/D-21-style), builds pooled features point-in-time per symbol, runs the SC1 feature audit + `feature_audit.json`, and either saves the versioned SC4 bundle + `LATEST.json` (`--train --write`) or emits the three report parquets. Exit codes are exactly {2 config, 1 runtime, 0 success incl. all-skipped}.

## Task Commits

Each task was committed atomically; TDD tasks carry a `test(...)` RED commit before the `feat(...)` GREEN commit:

1. **Task 1: ml/heuristic.py** — `77b6f49` (test), `c2619b9` (feat)
2. **Task 2: ml/evaluate.py** — `44649c8` (test), `ef68dcb` (feat)
3. **Task 3: ml/runner.py + __main__.py** — `76a67b2` (test), `fffa6d3` (feat)

**Plan metadata:** the docs commit below (04-03 SUMMARY + STATE/ROADMAP/REQUIREMENTS).

## Files Created/Modified

- `src/ai_trading/ml/heuristic.py` - WEIGHTS, HEURISTIC_VERSION, normalize, heuristic_score
- `src/ai_trading/ml/evaluate.py` - EvalResult, run_walkforward_eval (report/reliability/scores assembly, decide-only headline, skip contract)
- `src/ai_trading/ml/runner.py` - run_ml_pipeline, main, label-count gate, _output_dirs guard, atomic report writes
- `src/ai_trading/ml/__main__.py` - module entry for `python -m ai_trading.ml`
- `tests/unit/test_ml_heuristic.py` - 6 named tests
- `tests/unit/test_ml_evaluate.py` - 9 named tests
- `tests/unit/test_ml_runner.py` - 9 named tests (8 pass, 1 enum-skip on symlink-less platforms)

## Decisions Made

- **All-positive WEIGHTS on normalized goodness.** Inversion (not a negative weight) encodes the "smaller-is-better" sign for recency / risk / regime terms, so monotonicity in `rr_at_decision` is structurally guaranteed (pinned by a named test) and the heuristic stays within [0,1].
- **`EvalResult` as the singular eval surface.** `run_walkforward_eval` returns one dataclass carrying the three report shapes; the scores artifact is exactly one row per label row (label order preserved) with `score_source`, `provenance`, `excluded` — a score without provenance is a bug (research anti-pattern).
- **Artifact save gated on `--write` as well as `--train`.** Without `--write` the run is a dry-run that persists nothing (matches the plan's dry-run test).
- **Per-symbol audit aggregation in the runner.** `run_feature_audit` is invoked per symbol; the single persisted payload takes the max `max_abs_diff` and summed `n_labels_checked` (the spec hash/table are spec-global), keeping the SC1 artifact valid for a pooled multi-symbol run.
- **Heuristic quality deferred (Open Question 3).** Only determinism / [0,1] / missing-safety / spec-keying are pinned now; quality criteria are left to Phase 5/6 feedback with `score_source` recorded everywhere so impact is auditable.

## Deviations from Plan

None affecting the plan's intent; the plan executed as written.

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Final-model calibration-fold geometry needed a multi-day synthetic store**
- **Found during:** Task 3 (`test_full_train_run_exit_0_writes_artifacts`, `test_all_windows_skipped_exit_0`)
- **Issue:** the runner's `--train` refuses when the whole-store decided set yields fewer than two viable calibration folds. The initial 200-bar (~2-day) synthetic store produced only one viable fold (`insufficient_calibration_folds`), and the all-skipped store's global decided count fell below the gate threshold it was paired with.
- **Fix:** widened the full-train store to 400 M15 bars (~4 days) so expanding/sequential calibration folds over the decided set yield ≥2 viable folds; adjusted the all-skipped store to concentrate decided rows on the final day with a gate threshold between the per-window train count (0) and the global decided count so every window starves while the gate passes.
- **Files modified:** `tests/unit/test_ml_runner.py`
- **Verification:** both tests pass; full suite green.
- **Committed in:** `76a67b2`

**2. [Rule 3 - Blocking] `--train` without `--write` still saved an artifact**
- **Found during:** Task 3 (`test_dry_run_writes_nothing`)
- **Issue:** `run_ml_pipeline` computed and saved the versioned bundle whenever `mode=="train"`, so a dry-run (`--train` without `--write`) persisted artifacts, contradicting the plan's dry-run semantics.
- **Fix:** gated the artifact save on `write and mode=="train"`, so a dry-run persists nothing while still printing the summary.
- **Files modified:** `src/ai_trading/ml/runner.py`
- **Verification:** `test_dry_run_writes_nothing` passes (no LATEST/pooled/reports created, summary printed via stdout).
- **Committed in:** `fffa6d3`

**3. [Rule 3 - Blocking] Summary block printed to stdout (not the log)**
- **Found during:** Task 3 (`test_dry_run_writes_nothing`)
- **Issue:** the runner's summary block goes through `print()` (mirroring the backtest runner), so `caplog` did not capture it and the "summary still printed" assertion failed.
- **Fix:** switched the dry-run test to assert on `capsys` stdout.
- **Files modified:** `tests/unit/test_ml_runner.py`
- **Verification:** test passes.
- **Committed in:** `76a67b2`

---

**Total deviations:** 3 auto-fixed (all Rule 3 blocking issues; none Rule 1/2/4 — no scope creep, no architectural change).
**Impact on plan:** all three fixes were needed to keep the runner's exit-code contract, dry-run semantics, and test assertions coherent; the plan's features were implemented exactly as specified.

## Issues Encountered

- **`test_output_dir_traversal_refused` is environment-skipped.** The data-root traversal guard (T-04-06, mirroring `backtest._output_dirs`) is a resolve-under-root check whose only natural trigger is a directory reparse point (symlink). This Windows runner does not permit directory symlinks (no Developer Mode), so the test asserts `pytest.skip` when `os.symlink(...)` raises. The guard code and test exist and will run where symlinks are enabled; the 8 other runner tests all pass. Documented as a known environment limitation, not a plan deviation.
- Synthetic-store geometry: the expanding-train first-fold-empty condition is inherent to deriving folds from a data span at the minimum entry — fixtures needed to span enough days to expose ≥2 viable folds (see Auto-fixed #1).

## User Setup Required

None - no external service configuration required. (Real-data training is gated behind the label-count gate; deep-history backfill via the Phase 1 collector remains the documented human data task.)

## Next Phase Readiness

- AI-02/AI-04 satisfied at the unit level: every labeled candidate row is scored with `score_source` + `provenance`; decided-only headline metrics (D-01); TIMEOUT scored-and-flagged (D-02); starved windows skip-and-record with heuristic coverage (Pattern 5/6); windows derive exclusively from the Phase 3 harness (AI-04/SC3).
- The retrain CLI is runnable end-to-end and proves the whole chain on synthetic stores: labels → gate → features → audit artifact → windows → per-window eval → final calibrated model → versioned bundle + LATEST + three atomic reports, with the {2,1,0} exit-code discipline.
- Phase 5 (LLM) consumes `P(WIN)` + `score_source`/`provenance`; Phase 6 (setups/dashboard) loads the versioned artifact via `ml.scorer` and distinguishes flagged heuristic rows from ML-scored rows.
- No blockers. Suite now 449 passed (+1 env-skipped), up from 426 at plan start; ruff clean; vendor-purity (no MetaTrader5 under `src/ai_trading/ml/`) continues to pass.

---
*Phase: 04-ml-scoring*
*Completed: 2026-09-04*

## Self-Check: PASSED

All 7 deliverable files (4 source + 3 tests) exist on disk; all 6 task commits
(77b6f49, c2619b9, 44649c8, ef68dcb, 76a67b2, fffa6d3) are present in git
history; full unit suite green (449 passed, +1 env-skips); `uv run ruff check .`
clean; the plan-01 vendor-purity static test passes over the new ml/ modules.
