---
phase: 04-ml-scoring
verified: 2026-09-04T00:00:00Z
status: passed
score: 9/9 must-haves verified
behavior_unverified: 0
overrides_applied: 0
human_verification:

  - test: "Run a real-data ML training/eval run (`uv run python -m ai_trading.ml --config config.toml --train --write`) against the actual MT5 label store, after deepening stored history."
    expected: "The label-count gate passes on a real store (decided >= ml_min_train_labels with both classes), the feature audit writes data/reports/feature_audit.json, the walk-forward eval emits the three report parquets, and a versioned bundle is saved under data/models/pooled/v1/ + LATEST.json."
    why_human: "Requires the user's running, logged-in MT5 terminal to execute the Phase 1 collector deep-history backfill (DATA-04 path, M15/H1/H4) — a documented prerequisite data task (D-05 / Phase 3 UAT deferral). Automation cannot open an MT5 terminal; the label-count gate deliberately refuses thin/synthetic data. The pipeline itself is proven end-to-end on synthetic stores by tests."
---

# Phase 4: ML Scoring Verification Report

**Phase Goal:** Calibrated setup-probability scoring with leak-free features and walk-forward evidence
**Verified:** 2026-09-04T00:00:00Z
**Status:** human_needed
**Re-verification:** No — initial verification

## Goal Achievement

All four roadmap Success Criteria (SC1–SC4) and all four requirement IDs (AI-01…AI-04) are implemented, wired, and exercised by passing behavioral tests. The phase delivers a complete, tested ML-scoring pipeline. The single residual item is operational, not a code defect: training an actual production model on real data requires the user's MT5 terminal (deep-history backfill), which automation cannot perform and the label-count gate deliberately refuses until the data exists.

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | SC1: Features assembled point-in-time from SMC state; a feature audit confirms nothing uses post-decision-bar info | ✓ VERIFIED | `ml/features.py` builds all 18 features via `asof.visible_mask` anchors + `run_chain` tiers; `ml/audit.py` L1 prefix-equivalence (check_exact), L2 spec-coverage hash, L3 AST forbidden-column+purity guard; `test_ml_features.py` (9) + `test_ml_feature_audit.py` (11) pass, incl. `test_l1_detects_runtime_leak_mutation` (L1 falsifiable) |
| 2 | SC2: LightGBM scorer outputs calibrated probabilities; reliability recorded via CalibratedClassifierCV | ✓ VERIFIED | `ml/train.py::fit_calibrated` (CalibratedClassifierCV, sigmoid default from `ml_calibration_method`), `reliability_curve` (quantile), `reliability_summary` carried in bundle; `test_ml_train.py` (11) pass |
| 3 | SC3: Training/eval uses the Phase 3 walk-forward harness — no shuffled splits anywhere | ✓ VERIFIED | `ml/folds.py::calibration_folds` derives EXCLUSIVELY from `backtest.walkforward.build_windows`; `ml/evaluate.py` uses `build_windows` + `label_window_assignment`; `fit_calibrated` takes `folds` required-positional, `cv=folds, ensemble=True`; AST test `test_no_default_cv_call_sites` proves no default-cv site |
| 4 | SC4: Model artifacts (model + calibrator + feature metadata) versioned and loadable by the scorer | ✓ VERIFIED | `ml/artifact.py` (`ARTIFACT_SCHEMA_VERSION=1`, `build_bundle`, `save_artifact` → `data/models/pooled/v{N}/` model.joblib+manifest+LATEST.json, atomic), `load_artifact` 3-layer validation; `ml/scorer.py` `load_scorer`/`Scorer.score|contributors`; 13 artifact+scorer tests pass |
| 5 | AI-01: decision-close R:R + session-gap-robust decision-bar location pinned | ✓ VERIFIED | `features_at_decision` recomputes `compute_rr` at decision close; `build_feature_frame` locates decision bar via `searchsorted(entry_time, side='left')-1`; `test_rr_feature_uses_decision_close_not_fill_open`, `test_decision_bar_located_across_session_gap` pass |
| 6 | AI-02/AI-03 (D-01/D-02): decided-only training; TIMEOUT score-and-flag; reliability retained | ✓ VERIFIED | `train.py::decided_mask`/`preflight_reason`; `evaluate.py` decided-only headline (auc/log_loss/brier), TIMEOUT `excluded=True` with scores kept; `artifact.reliability_summary`; `test_decided_only_headline_metrics`, `test_timeout_rows_scored_and_flagged_excluded` pass |
| 7 | AI-04 (OQ5 purge): boundary purge + embargo + harness-derived calibration folds | ✓ VERIFIED | `ml/purge.py::purged_train_mask` (both boundary sides), `ml/folds.py` from `build_windows`; `test_ml_purge.py` (5), `test_ml_folds.py` (5) pass incl. `test_purge_drops_exit_at_test_start`/`test_purge_keeps_exit_closing_at_test_start`/`test_prge_embargo_extends_boundary` |
| 8 | Every labeled row scored with provenance; starved/skipped windows covered by flagged deterministic heuristic | ✓ VERIFIED | `ml/heuristic.py` (WEIGHTS keyed to FEATURE_SPEC, `heuristic_score` vectorized, missing→0, [0,1]); `evaluate.py` `score_source`/`provenance` per row; `test_ml_heuristic.py` (6), `test_ml_evaluate.py` (9) pass incl. `test_starved_window_skipped_and_recorded`, `test_skipped_window_span_heuristic_scored`, `test_every_label_row_scored_exactly_once` |
| 9 | Retrain CLI: label-count gate (actionable refusal), {2,1,0} exit-code contract, atomic report writes | ✓ VERIFIED | `ml/runner.py` (`--config/--train/--eval/--write`, `_label_gate`, `_output_dirs` resolve-under-guard, `_atomic_parquet`), `ml/__main__.py`; `test_ml_runner.py` (8 pass, 1 env-skip on symlink-less Windows) incl. `test_gate_refusal_exit_1_names_counts_and_threshold`, `test_full_train_run_exit_0_writes_artifacts` |

**Score:** 9/9 truths verified (0 present, behavior-unverified)

### Required Artifacts

| Artifact | Expected | Status | Details |
| -------- | -------- | ------ | ------- |
| `src/ai_trading/ml/features.py` | FEATURE_SPEC + features_at_decision + build_feature_frame (pure, MT5-free) | ✓ VERIFIED | 18-feature spec; 20-col frame; visible_mask/run_chain wiring |
| `src/ai_trading/ml/audit.py` | FORBIDDEN_LABEL_COLUMNS + L1/L2/L3 + run/write_feature_audit | ✓ VERIFIED | atomic feature_audit.json writer; falsifiable L1 |
| `src/ai_trading/ml/purge.py` | purged_train_mask (OQ5 + embargo) | ✓ VERIFIED | both boundary sides exact |
| `src/ai_trading/ml/folds.py` | calibration_folds from build_windows | ✓ VERIFIED | no second splitter |
| `src/ai_trading/ml/train.py` | decided_mask/preflight/lgbm_params/fit_lightgbm/fit_calibrated/reliability_curve | ✓ VERIFIED | deterministic, no imbalance flags, ensemble=True explicit folds |
| `src/ai_trading/ml/artifact.py` | build_bundle/save_artifact/load_artifact | ✓ VERIFIED | v{N} + manifest + LATEST; 3-layer validation |
| `src/ai_trading/ml/scorer.py` | load_scorer + Scorer.score/contributors | ✓ VERIFIED | category restoration; MT5-free |
| `src/ai_trading/ml/heuristic.py` | WEIGHTS + heuristic_score | ✓ VERIFIED | deterministic, [0,1], spec-keyed |
| `src/ai_trading/ml/evaluate.py` | run_walkforward_eval → EvalResult | ✓ VERIFIED | decided-only, TIMEOUT flagged, provenance |
| `src/ai_trading/ml/runner.py` + `__main__.py` | run_ml_pipeline + main CLI | ✓ VERIFIED | gate, exit codes, atomic writes |
| `src/ai_trading/config.py` + `config.toml` | 13 ml_* keys, fail-fast | ✓ VERIFIED | all present, validated |
| `tests/unit/_ml_fixtures.py` + 9 `test_ml_*.py` | Phase 4 fixtures + tests | ✓ VERIFIED | all present |

### Key Link Verification

| From | To | Via | Status | Details |
| ---- | --- | --- | ------ | ------- |
| ml/features.py | backtest/asof.py | visible_mask + STAMP_CLOSE/STAMP_BAR | ✓ WIRED | imported and used in build_feature_frame |
| ml/features.py | backtest/chain.py run_chain | chain tiers into CandidateState | ✓ WIRED | run_chain passed in / used in audit |
| ml/audit.py | data/reports/feature_audit.json | atomic write_feature_audit | ✓ WIRED | tmp+os.replace |
| ml/folds.py | backtest/walkforward.py build_windows | exclusive fold derivation | ✓ WIRED | imported; no other splitter |
| ml/train.py | sklearn.calibration.CalibratedClassifierCV | cv=folds, ensemble=True | ✓ WIRED | AST no-default-cv test |
| ml/artifact.py | data/models/pooled/v{N}/ + LATEST.json | atomic joblib + JSON | ✓ WIRED | save/load round-trip |
| ml/scorer.py | ml/features.py FEATURE_SPEC | feature_names + categorical_specs | ✓ WIRED | reindex + category restore |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
| -------- | ------- | ------ | ------ |
| ML module suite | `uv run pytest tests/unit/test_ml_*.py -q` 2>&1 tail | 77 passed, 1 skipped | ✓ PASS |
| Full unit suite | `uv run pytest tests/unit -q` 2>&1 tail | 448 passed (1 transient Phase-3 Windows file-lock flake in test_reports.py, passes standalone), 1 skipped | ✓ PASS (ML intact) |

*Step 7b note:* the behavior-dependent truths here (decision-close R:R, purge boundary, fold derivation, determinism, no-default-cv, calibrator end-to-end, TIMEOUT flagging, gate refusal, scorer round-trip) are all exercised by their own named passing tests — no truth needed to remain ⚠️ PRESENT_BEHAVIOR_UNVERIFIED on symbol presence alone.

### Probe Execution

No probe scripts (`scripts/*/tests/probe-*.sh`) are declared or conventional for this phase; verification is test-suite-based per 04-VALIDATION.md.

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
| ----------- | ----------- | ----------- | ------ | -------- |
| AI-01 | 04-01 | Features point-in-time (no info after decision bar) | ✓ SATISFIED | features.py + audit.py L1/L2/L3 + named tests |
| AI-02 | 04-02, 04-03 | Each candidate gets an ML probability from gradient-boosted model | ✓ SATISFIED | fit_lightgbm (LGBMClassifier), scorer.score p_win, heuristic fallback |
| AI-03 | 04-02 | Scores calibrated (isotonic/Platt) so probabilities honest | ✓ SATISFIED | CalibratedClassifierCV sigmoid default; reliability_curve; artifact reliability_summary |
| AI-04 | 04-02, 04-03 | Walk-forward protocol, no shuffled splits | ✓ SATISFIED | build_windows-only folds; label_window_assignment; AST no-default-cv |

All four requirement IDs are accounted for by PLAN frontmatter and none is orphaned.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
| ---- | ---- | ------- | -------- | ------ |
| — | — | None (no TBD/FIXME/XXX/HACK/PLACEHOLDER markers; no `import MetaTrader5`; `rg`/AST purity test passes over all ml/ modules) | ℹ️ none | — |

### Human Verification Required

1. **Real-data ML training run (deep-history backfill via MT5 terminal)** — See the `human_verification` frontmatter item. The pipeline is proven end-to-end on synthetic stores by tests; producing an actual production model requires the user's logged-in MT5 terminal to backfill M15/H1/H4 history (DATA-04), after which the label-count gate passes and `python -m ai_trading.ml --train --write` emits the artifact. Documented as the D-05 prerequisite data task (deferred from Phase 3 UAT), not a code gap.

### Gaps Summary

No gaps. All nine must-have truths and all four requirements (AI-01…AI-04) are verified in code and by passing behavioral tests. The 448-pass-1-skipfull suite also confirms no regression was introduced by Phase 4 (the one transient `PermissionError` is a Windows file-lock flake in a Phase 3 `test_reports.py` case that passes in isolation and is unrelated to the ML modules).

The single item routing this to `human_needed` is operational — training the actual model on real data requires the user's MT5 terminal, which automation cannot exercise. This is exactly the documented prerequisite data task, not an unresolved implementation gap.

---

_Verified: 2026-09-04T00:00:00Z_
_Verifier: the agent (gsd-verifier)_
