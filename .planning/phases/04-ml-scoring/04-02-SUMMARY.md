---
phase: 04-ml-scoring
plan: 02
subsystem: ml
tags: [lightgbm, scikit-learn, calibration, walk-forward, purge, artifact, scorer, wave-2]

requires:
  - phase: 04-ml-scoring plan 01
    provides: FEATURE_SPEC + FEATURE_NAMES + categorical_specs, frozen Config ml_* knobs, _ml_fixtures (make_labels/ml_cfg/synthetic_feature_frame), lightgbm 4.7.0 + scikit-learn 1.9.0
provides:
  - ml/purge.py purged_train_mask (OQ5 boundary purge + embargo)
  - ml/folds.py calibration_folds (SC3 harness-derived chronological fold pairs)
  - ml/train.py decided_mask / preflight_reason / lgbm_params / fit_lightgbm / fit_calibrated / reliability_curve (D-01, AI-02/03)
  - ml/artifact.py ARTIFACT_SCHEMA_VERSION / build_bundle / save_artifact / load_artifact (SC4, T-04-01)
  - ml/scorer.py load_scorer + Scorer.score/contributors (Phase-6 seam, MT5-free)
affects: [04-ml-scoring plan 03 (runner/evaluate/heuristic, walks forward on these folds + scores), Phase 5 LLM (P(WIN) + contributors), Phase 6 dashboard/scorer load]

tech-stack:
  added: []   # no new deps; lightgbm 4.7.0 + scikit-learn 1.9.0 inherited from Wave 0
  patterns:
    - "PURE training tier: train.py is pure given frames — no I/O, no MetaTrader5, inputs never mutated until the runner tier"
    - "SC3 structural no-shuffle: fit_calibrated takes folds as a REQUIRED positional arg (no default) and passes cv=folds + ensemble=True — enforced by an AST source-assertion test and inspect.signature"
    - "Deterministic LGBM: deterministic=True + force_row_wise=True + num_threads=1 + fixed seed + boosting=gbdt → byte-identical predict_proba across refits; imbalance reweighting flags structurally absent"
    - "OQ5 purge keep-condition: exit strictly before test_start - embargo*bars; exit_time = exit bar's OPEN time makes both boundary sides exact"
    - "Atomic versioned artifact: tmp+os.replace discipline (reports.py copy) for model.joblib/manifest.json/LATEST.json; the LATEST pointer is written only after the version dir completes"
    - "Three-layer loader validation: schema version, feature-list version, library majors (refuse) / minor (warn) — the pickle trust gate (T-04-01)"

key-files:
  created:
    - src/ai_trading/ml/purge.py
    - src/ai_trading/ml/folds.py
    - src/ai_trading/ml/train.py
    - src/ai_trading/ml/artifact.py
    - src/ai_trading/ml/scorer.py
    - tests/unit/test_ml_purge.py
    - tests/unit/test_ml_folds.py
    - tests/unit/test_ml_train.py
    - tests/unit/test_ml_artifact.py
    - tests/unit/test_ml_scorer.py
  modified:
    - src/ai_trading/ml/features.py   # added FEATURE_LIST_VERSION constant for loader validation

key-decisions:
  - "Embargo default 0 (purge-only): the 96-bar barrier already removes every overlapping label; embargo only guards regime continuity and costs train depth on the tiny store — revisit after deep backfill"
  - "fit_calibrated refuses <2 explicit folds with a skip reason — a single viable fold cannot calibrate, never a silent uncalibrated fallback (SC2)"
  - "reliability_summary is a dict (empty when uncomputable) so the artifact 'retains reliability data' (SC2) alongside the per-window/pooled parquet rows plan 03 persists"
  - "FEATURE_LIST_VERSION=1 added to features.py as the loader's current-FEATURE_SPEC source of truth; artifact bundles are NOT byte-deterministic (pickle framing) — determinism pinned at the probability and manifest levels"
  - "contributors come from the raw booster's pred_contrib (uncalibrated logit space) paired with the calibrated p_win headline (A6)"

requirements-completed: [AI-02, AI-03]

coverage:
  - id: D1
    description: "OQ5 boundary purge + embargo over label exit stamps (purged_train_mask) — both boundary sides exact, NaT excluded, inputs never mutated"
    requirement: AI-04
    verification:
      - kind: unit
        ref: "tests/unit/test_ml_purge.py#test_purge_drops_exit_at_test_start / test_purge_keeps_exit_closing_at_test_start / test_purge_embargo_extends_boundary / test_purge_preserves_mask_alignment_and_inputs / test_purge_nat_exit_excluded"
        status: pass
    human_judgment: false
  - id: D2
    description: "Harness-derived calibration fold pairs (calibration_folds) — exclusively from walkforward.build_windows, expanding/sequential, purge at every boundary, zero-label + invalid-days contracts"
    requirement: AI-04
    verification:
      - kind: unit
        ref: "tests/unit/test_ml_folds.py#test_folds_derived_from_build_windows_expanding / test_folds_purge_applied_at_every_boundary / test_folds_embargo_applied / test_folds_empty_entry_times_returns_empty_list / test_folds_reject_harness_invalid_days"
        status: pass
    human_judgment: false
  - id: D3
    description: "Training core (decided_mask, preflight_reason, lgbm_params, fit_lightgbm, fit_calibrated, reliability_curve) — decided-only, deterministic, chronologically calibrated with a structural no-default-cv guard"
    requirement: AI-02
    verification:
      - kind: unit
        ref: "tests/unit/test_ml_train.py (11 named): deterministic predict_proba, no imbalance flags, required positional folds + AST no-default-cv, end-to-end sigmoid [0,1], reliability schema/counts/empty-guard"
        status: pass
    human_judgment: false
  - id: D4
    description: "Versioned artifact bundle (ARTIFACT_SCHEMA_VERSION, build_bundle, save_artifact, load_artifact) — v{N} increment, stamped artifact_version, atomic writes, pickled-free manifest, LATEST pointer, three-layer loader validation"
    requirement: AI-03
    verification:
      - kind: unit
        ref: "tests/unit/test_ml_artifact.py (7 named): version increment + LATEST, required SC4 keys, pickled-free manifest, no-tmp atomic writes, schema/feature-list/major refusals + minor warn"
        status: pass
    human_judgment: false
  - id: D5
    description: "Loadable MT5-free scorer (load_scorer + Scorer.score/contributors) — feature reindex, categorical restoration (Pitfall 7), unseen→missing, output schema, contributors shape/bias/determinism"
    requirement: AI-02
    verification:
      - kind: unit
        ref: "tests/unit/test_ml_scorer.py (6 named): pointer+dir equivalence, single-row == training row, missing-column refusal, unseen-category warning, output schema, contributors shape/bias"
        status: pass
    human_judgment: false

duration: ~40m
completed: 2026-09-03
status: complete
---

# Phase 4 Plan 2: LightGBM P(WIN) Training Core, Chronological-Fold Calibration, Versioned Artifact & Scorer Summary

**The OQ5 boundary purge, harness-derived calibration folds, deterministic decided-only LightGBM training with sigmoid calibration, and a versioned/validated artifact bundle + MT5-free scorer (lightgbm 4.7.0 / scikit-learn 1.9.0).**

## Performance

- **Duration:** ~40m
- **Started:** 2026-09-03T15:10Z (approx)
- **Completed:** 2026-09-03T15:48Z
- **Tasks:** 3
- **Files modified:** 11 (10 created, 1 modified)

## Accomplishments

- **OQ5 closed.** `purged_train_mask` implements the single keep-condition (exit strictly before `test_start − embargo_bars × bar_minutes`). With embargo 0 it is the mandatory purge — a label whose `exit_time` is at/after `test_start` (outcome resolves inside the test window) is dropped, while an `exit_time` one bar before `test_start` (the exit bar's OPEN 15m earlier, closing exactly at the window start) is kept. Both boundary sides pinned by their own named tests; the embargo knob moves the boundary by whole bars. NaT exits conservatively excluded; inputs never mutated.
- **SC3 no-shuffle folds.** `calibration_folds` derives expanding/sequential `(train, test)` positional pairs EXCLUSIVELY from `walkforward.build_windows` (the splitter of record), with the purge applied at every fold boundary and zero-`cv`-default enforced. Empty-train/empty-test windows are skipped (zero-label contract); invalid day values propagate the harness's own `ValueError` — no second splitter exists.
- **Deterministic decided-only training (D-01, T-04-05).** `train.py` confines fitting to WIN/LOSS via `decided_mask`, gates starvation/single-class windows through `preflight_reason` (stable prefixes), and fits with a deterministic LightGBM parameter set (`gbdt`, fixed seed, `num_threads=1`) that reproduces byte-identical `predict_proba` across refits. The imbalance reweighting flags are structurally absent (documented probability distortion).
- **SC2 reliability.** `reliability_curve` wraps `calibration_curve(strategy='quantile')` into a schema-stable `bin/prob_pred/prob_true/count` DataFrame (empty schema frame for single-class / <2 distinct values, never raises).
- **SC4 artifact + scorer.** `artifact.py` writes `data/models/pooled/v{N}/model.joblib` + `manifest.json` + `data/models/LATEST.json` atomically (tmp+`os.replace`), stamps `artifact_version`, and validates schema version, feature-list version, and sklearn/lightgbm majors on load (minor mismatch warns). `scorer.py` returns a MT5-free `Scorer` whose `score` produces `p_win/score_source/artifact_version` and whose `contributors` emits `pred_contrib` attributions (feature_names + bias). Category restoration makes unseen categories missing (Pitfall 7) without the deprecated pandas path.

## Task Commits

Each task was committed atomically; TDD tasks carry a `test(...)` RED commit before the `feat(...)` GREEN commit:

1. **Task 1: Boundary purge (OQ5) + harness-derived calibration folds** — `72a9523` (test), `5cd0671` (feat)
2. **Task 2: ml/train.py training core** — `e7f4950` (test), `7b59f42` (feat)
3. **Task 3: ml/artifact.py + ml/scorer.py** — `d040261` (test), `25e58e2` (feat)

**Plan metadata:** the docs commit below (04-02 SUMMARY + STATE/ROADMAP/REQUIREMENTS).

## Files Created/Modified

- `src/ai_trading/ml/purge.py` - `purged_train_mask` (OQ5 purge + embargo keep-condition)
- `src/ai_trading/ml/folds.py` - `calibration_folds` (build_windows-derived chronological fold pairs, purge at every boundary)
- `src/ai_trading/ml/train.py` - `decided_mask`, `preflight_reason`, `lgbm_params`, `fit_lightgbm`, `fit_calibrated`, `reliability_curve`
- `src/ai_trading/ml/artifact.py` - `ARTIFACT_SCHEMA_VERSION`, `build_bundle`, `save_artifact`, `load_artifact`
- `src/ai_trading/ml/scorer.py` - `load_scorer`, `Scorer.score`, `Scorer.contributors`
- `src/ai_trading/ml/features.py` - added `FEATURE_LIST_VERSION` (current FEATURE_SPEC version for loader validation)
- `tests/unit/test_ml_purge.py` - 5 named purge tests
- `tests/unit/test_ml_folds.py` - 5 named folds tests
- `tests/unit/test_ml_train.py` - 11 named training tests
- `tests/unit/test_ml_artifact.py` - 7 named artifact tests
- `tests/unit/test_ml_scorer.py` - 6 named scorer tests

## Decisions Made

- **Embargo default 0 (purge-only).** Documented in `purge.py`'s docstring: the 96-bar outcome barrier already removes every overlapping label, so embargo only guards regime continuity and costs train depth on the tiny store — `ml_embargo_bars` knob leaves it reversible after deep backfill.
- **`fit_calibrated` refuses <2 explicit folds.** A single viable fold cannot calibrate; the function raises a skip-defining `ValueError` rather than silently falling back to uncalibrated probabilities (SC2).
- **`reliability_summary` as a dict (empty when uncomputable).** Satisfies SC2's "the artifact retains reliability data" alongside the per-window/pooled parquet rows plan 03 persists.
- **`FEATURE_LIST_VERSION=1` added to features.py.** This is the loader's "current FEATURE_SPEC version" source of truth — a future feature-spec change must bump it and `ml_feature_list_version` together (Pitfall 10).
- **Bundle determinism at probability + manifest level only** (research deviation note): model bundles are not byte-deterministic (pickle framing); determinism is pinned at `predict_proba` and the manifest (config_hash).
- **Contributors in raw-model space.** `contributors` uses the raw booster's `pred_contrib` (uncalibrated logit), paired with the calibrated `p_win` headline (A6); the scale delta is documented, not hidden.

## Deviations from Plan

None affecting the plan's intent; the plan executed as written (see the three in-scope correctness fixes below under Auto-fixed Issues, which were required to keep the suite green and honest).

### Auto-fixed Issues

**1. [Rule 1 - Bug] Test-fixture data geometry under-produced valid calibration folds**
- **Found during:** Task 2 (`test_fit_calibrated_end_to_end_sigmoid`) and Task 3 (both fixtures)
- **Issue:** expanding windows starting at the data's min entry leave the first window's train empty, so a 2-day / 48-row hourly domain yields only ONE valid fold (dropped as empty-train); `fit_calibrated` correctly refuses <2 folds, failing the tests.
- **Fix:** widened the fixture domains to 3 days (72 hourly entries) so two valid chronological folds exist (windows b=01-03 and b=01-05); the scallop of the test's y (alternating) guarantees both classes in every train/test block.
- **Files modified:** `tests/unit/test_ml_train.py`, `tests/unit/test_ml_artifact.py`, `tests/unit/test_ml_scorer.py`
- **Verification:** all affected tests green; the 34-test ML module block green.
- **Committed in:** `7b59f42`, `25e58e2`

**2. [Rule 1 - Bug] Embargo test used hourly entries + 60-minute exits, so no label landed in the 15-minute embargo window**
- **Found during:** Task 1 (`test_folds_embargo_applied`)
- **Issue:** with hourly entries and a 1-hour exit offset, every label was either already purged at the test_start or strictly outside `[test_start − 15m, test_start)` — so embargo 1 did not shrink any fold's train, failing the strict-subset assertion.
- **Fix:** switched the embargo test to 15-minute entries so labels resolve inside the embargo window (exit exactly one bar before `test_start`), making the knob-before-boundary shrink real.
- **Files modified:** `tests/unit/test_ml_folds.py`
- **Verification:** `test_folds_embargo_applied` proceeds and passes.
- **Committed in:** `5cd0671`

**3. [Rule 1 - Bug] pandas-3 deprecation on the scorer's unseen-category path**
- **Found during:** Task 3 (`test_score_unseen_category_becomes_missing_with_warning`)
- **Issue:** restoring `CategoricalDtype` over a column containing off-dtype values emitted `Pandas4Warning` (deprecated, will raise in a future pandas) on the intended unseen→missing path.
- **Fix:** mask unseen values to missing first, then build the Categorical from the cleaned array — records the same unseen-category warning for the caller and never feeds pandas foreign values.
- **Files modified:** `src/ai_trading/ml/scorer.py`
- **Verification:** the unseen-category test passes with zero warnings.
- **Committed in:** `25e58e2`

---

**Total deviations:** 3 auto-fixed (all Rule 1 bugs; none Rule 2/3/4 — no scope creep, no architectural change).
**Impact on plan:** all three were in-scope correctness/cleanliness fixes needed to keep the suite green and the scorer future-proof; the plan's features were implemented exactly as specified.

## Issues Encountered

- The expanding-window first-fold-empty-train geometry is inherent to deriving folds from a data span starting at the minimum entry — the first window's train is always empty and is correctly skipped; fixtures simply had to span enough days to expose ≥2 valid folds (see Auto-fixed #1).
- Adjusted 3 validation-write helper signatures during development to keep ruff's import sorting and the unused-import / unused-variable checks clean (no behavior change).

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- AI-02/AI-03 satisfied at the unit level: deterministic decided-only training with sigmoid-default chronological calibration and recorded reliability helper; SC2/SC3/SC4 delivered (reliability retention, harness-only folds, versioned validated artifact + scorer).
- Plan 03 (runner/evaluate/heuristic) has everything it needs: `calibration_folds` + `fit_calibrated` for walk-forward per-window training, `reliability_curve` for the SC2 reliability rows, and `artifact.save_artifact`/`scorer.load_scorer` for the versioned bundle + loadable scoring path Phase 5/6 consume.
- `FEATURE_LIST_VERSION` bump discipline established (must move with `ml_feature_list_version`); the scorer is MT5-free and importable without runner dependencies (Phase-6 seam proven).
- No blockers. Full suite now 426 (was 392 at plan start).

---
*Phase: 04-ml-scoring*
*Completed: 2026-09-03*

## Self-Check: PASSED

All 10 deliverable files + the SUMMARY exist on disk; all 6 task commits
(72a9523, 5cd0671, e7f4950, 7b59f42, d040261, 25e58e2) present in git history;
full unit suite green (426 passed, up from 392); ruff clean; the plan-01 vendor
purity static test continues to pass over the new ml/ modules.
