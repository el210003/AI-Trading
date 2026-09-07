---
phase: 04-ml-scoring
plan: 01
subsystem: ml
tags: [lightgbm, scikit-learn, point-in-time, features, feature-audit, wave-0]

requires:
  - phase: 03-backtesting-labeling
    provides: run_chain tiers, LABEL_COLUMNS label frame, visible_mask as-of anchors
  - phase: 02-smc-detection-engine
    provides: MTF payload, detector tiers (swings/zones/pools/events)
provides:
  - Wave-0 ML stack: lightgbm 4.7.0 + scikit-learn 1.9.0 (joblib 1.6.x transitive) installed & version-verified
  - Frozen-Config ml_* knob extension (13 keys, fail-fast validation, dataclass defaults preserving direct construction)
  - ml/ package with point-in-time feature builder (FEATURE_SPEC + features_at_decision + build_feature_frame)
  - Three-layer point-in-time feature audit + persisted feature_audit.json writer
  - Phase-4 test fixture module (_ml_fixtures)
affects: [04-ml-scoring plan 02 (train/scorer), 04-ml-scoring plan 03 (runner/heuristic), Phase 6 scorer]

tech-stack:
  added: [lightgbm 4.7.0, scikit-learn 1.9.0, joblib 1.6.x (transitive)]
  patterns:
    - "PURE feature builder: FEATURE_SPEC ordered spec + features_at_decision(CandidateState) + build_feature_frame, MT5-free, no I/O, inputs never mutated"
    - "Decision-close R:R rule: compute_rr(direction, decision_close, sl, tp) recomputed at the decision bar — never the label's fill-based rr"
    - "Session-gap-robust decision-bar location via searchsorted(entry_time, side=left) minus one (never entry_time - TF minutes)"
    - "Three-layer audit: L1 prefix-equivalence (check_exact=True), L2 spec-coverage provenance hash, L3 AST forbidden-column + vendor-purity"
    - "Atomic artifact write: local tmp + os.replace (reports discipline) for feature_audit.json"

key-files:
  created:
    - src/ai_trading/ml/__init__.py
    - src/ai_trading/ml/features.py
    - src/ai_trading/ml/audit.py
    - tests/unit/_ml_fixtures.py
    - tests/unit/test_ml_features.py
    - tests/unit/test_ml_feature_audit.py
  modified:
    - pyproject.toml
    - uv.lock
    - config.toml
    - src/ai_trading/config.py
    - tests/unit/test_backtest_config.py
    - tests/unit/test_normalize_and_config.py

key-decisions:
  - "FEATURE_SPEC is the ordered source of truth for ml_feature_list_version: 18 features (5 categorical identity/bias + 13 numeric), each carrying name/dtype/source_tier/source_columns/stamp_kind"
  - "Feature frame is 20 columns: the 18 FEATURE_SPEC names (symbol/timeframe double as alignment identity) + entry_time + decision_close_time"
  - "for feature assignment in build_feature_frame, sl_price/tp_price come from label structural columns (decision-time detector outputs), never the fill-based rr"
  - "L1 audit uses a NON-STRICT visibility horizon (decision_close_time <= prefix_close) because features need only bars up to and including the decision bar S (differs from the replay-repaint strict horizon which needs the S+1 fill bar)"
  - "audit_spec_coverage defaults to FEATURE_SPEC and raises naming missing/extra columns, dtype mismatch, or illegal stamp_kind — falsifiable manifest"

requirements-completed: [AI-01]

coverage:
  - id: D1
    description: "Wave-0 ML foundation — lightgbm 4.7.0 + scikit-learn 1.9.0 installed and version-verified (joblib 1.6.x transitive); frozen Config validates thirteen ml_* keys fail-fast; config.toml documents them; bare ml package marker + Phase-4 fixture module"
    requirement: AI-01
    verification:
      - kind: unit
        ref: "uv run python -c 'import lightgbm,sklearn,joblib; print(...)' -> 4.7.0 1.9.0 1.6.0"
        status: pass
      - kind: unit
        ref: "uv run pytest tests/unit/test_backtest_config.py -q -> 31 passed"
        status: pass
    human_judgment: false
  - id: D2
    description: "Point-in-time feature builder — FEATURE_SPEC + features_at_decision + build_feature_frame (decision-close R:R, session-gap-robust decision location, payload-as-is NA, ATR warmup NA, zone/sweep recency, 20-col schema & alignment)"
    requirement: AI-01
    verification:
      - kind: unit
        ref: "uv run pytest tests/unit/test_ml_features.py -q -> 9 passed"
        status: pass
    human_judgment: false
  - id: D3
    description: "Three-layer point-in-time audit + persisted feature_audit.json writer — L1 prefix-equivalence (falsifiable), L2 spec-coverage hash, L3 AST forbidden-column + vendor-purity guard"
    requirement: AI-01
    verification:
      - kind: unit
        ref: "uv run pytest tests/unit/test_ml_feature_audit.py -q -> 11 passed"
        status: pass
      - kind: unit
        ref: "uv run pytest tests/unit -q -> 392 passed"
        status: pass
    human_judgment: false

duration: ~1h 50m
completed: 2026-09-03
status: complete
---

# Phase 4 Plan 1: Point-in-Time Feature Builder + Three-Layer Audit Summary

**Wave-0 ML foundation plus an 18-feature point-in-time builder from SMC state with a mechanical three-layer leak-free audit (lightgbm 4.7.0 / scikit-learn 1.9.0).**

## Performance

- **Duration:** ~1h 50m
- **Started:** 2026-09-03T13:20Z (approx)
- **Completed:** 2026-09-03T23:05Z
- **Tasks:** 3
- **Files modified:** 12 (6 created, 6 modified)

## Accomplishments

- Wave-0 stack installed and verified: `lightgbm 4.7.0`, `scikit-learn 1.9.0`, `joblib 1.6.0` (transitive) import cleanly; added to `pyproject.toml`/`uv.lock` (joblib never a direct dependency).
- Frozen `Config` extended with thirteen `ml_*` keys carrying dataclass defaults so direct construction (`_make_cfg`/`bt_cfg`) keeps working unchanged; `_validate` fails fast on out-of-domain ml values (calibration method must be in {sigmoid, isotonic}, positive-int / number bounds, bool-as-int rejected via `_is_int`), and `_REQUIRED_KEYS` extension makes a missing ml key refuse load naming it.
- `config.toml` documents every `ml_*` knob (feature-list version, sigmoid default, embargo purge-only, min-train gate, calibration window days, deterministic LightGBM capacity, Phase-6 retrain schedule).
- `ml/features.py` implements the 18-feature `FEATURE_SPEC`, pure `features_at_decision(state, label_row, cfg)`, and `build_feature_frame(labels, chain, bars)`. The decision-time R:R is recomputed at the decision close (`compute_rr`), the decision bar is located via `searchsorted(entry_time, side='left') - 1` (robust across session gaps), and every tier is sliced through `visible_mask` with the exact `replay_symbol` anchors (BT-01 single path).
- `ml/audit.py` implements the three-layer audit: L1 prefix-equivalence (non-strict `decision_close_time <= prefix_close`, `check_exact=True`), L2 spec-coverage with a stable sha256 manifest, L3 `FORBIDDEN_LABEL_COLUMNS` static guard (enforced by an AST test) — plus `run_feature_audit` composition and the atomic `write_feature_audit` writer for `data/reports/feature_audit.json`.
- Phase-4 fixture module `_ml_fixtures.py` provides `ml_cfg`, `make_labels`, `sculpted_label_world` (a deterministic world yielding ≥1 WIN and ≥1 LOSS label with known sl/tp) and `synthetic_feature_frame`.
- Both leak-sensitive guarantees are pinned by named tests: `test_rr_feature_uses_decision_close_not_fill_open` and `test_l1_detects_runtime_leak_mutation` (L1 is a real, falsifiable proof, not a tautology).

## Task Commits

Each task was committed atomically; TDD tasks carry a `test(...)` RED commit before the `feat(...)` GREEN commit:

1. **Task 1: Wave-0 ML foundation** — `cbf0d6e` (feat)
2. **Task 2: ml/features.py (RED→GREEN)** — `cacd050` (test), `8bf742e` (feat)
3. **Task 3: ml/audit.py (RED→GREEN)** — `379e50d` (test), `3ab3fd5` (feat)

**Plan metadata:** the docs commit below.

## Files Created/Modified

- `src/ai_trading/ml/__init__.py` - bare package marker (docstring only)
- `src/ai_trading/ml/features.py` - FEATURE_SPEC, features_at_decision, build_feature_frame
- `src/ai_trading/ml/audit.py` - FORBIDDEN_LABEL_COLUMNS, audit_prefix_equivalence (L1), audit_spec_coverage (L2), run_feature_audit, write_feature_audit
- `tests/unit/_ml_fixtures.py` - ml_cfg, make_labels, sculpted_label_world, synthetic_feature_frame
- `tests/unit/test_ml_features.py` - 9 named feature tests
- `tests/unit/test_ml_feature_audit.py` - 11 named audit/guard tests
- `src/ai_trading/config.py` - 13 ml_* frozen fields + _REQUIRED_KEYS + _validate rules
- `config.toml` - ML knob documentation + values
- `pyproject.toml` / `uv.lock` - lightgbm + scikit-learn deps
- `tests/unit/test_backtest_config.py` - ml config test cases (extended)
- `tests/unit/test_normalize_and_config.py` - ml keys added to base values (required-keys fix)

## Decisions Made

- FEATURE_SPEC is the ordered source of truth for `ml_feature_list_version`; all 18 entries declare dtype/source_tier/source_columns/stamp_kind (covered by a named test that also asserts the produced 20-column frame's schema and alignment).
- `features_at_decision` reads sl/tp from label structural columns but never the fill-based `rr`/`entry_price`/`exit_*`/`r_*`/`outcome` (documented in the module docstring and enforced by the L3 AST test).
- The L1 audit uses a non-strict horizon because a feature needs only bars up to and including the decision bar S (explicitly documented as differing from the replay-repaint suite, whose fill needs bar S+1).

## Deviations from Plan

None affecting the plan's intent; the plan executed as written (see the two deviation-rules fixes below, which were in-scope correctness fixes needed to keep the existing suite green).

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Phase-1 config test module required the new ml_* keys**
- **Found during:** Task 1 (config extension)
- **Issue:** adding the 13 ml keys to `_REQUIRED_KEYS` made `tests/unit/test_normalize_and_config.py` fail (its `_base_values` predated the ml keys).
- **Fix:** extended that module's `_base_values` with the ml defaults, matching the Phase-3 precedent where backtest keys were added to the same module.
- **Files modified:** `tests/unit/test_normalize_and_config.py`
- **Verification:** `uv run pytest tests/unit -q` green (372 → 392).
- **Committed in:** `cbf0d6e` (Task 1)

**2. [Rule 1 - Bug] make_labels crashed on unprovided numeric label columns**
- **Found during:** Task 2 (fixture used by the session-gap test)
- **Issue:** `make_labels` filled unprovided LABEL_COLUMNS with `pd.NA`, which broke the `astype("float64")` dtype pinning on numeric columns.
- **Fix:** made `make_labels` use type-aware missing placeholders (pd.NA for strings, NaT for timestamps, 0 for int, NaN for floats).
- **Files modified:** `tests/unit/_ml_fixtures.py`
- **Verification:** session-gap test passes; full suite green.
- **Committed in:** `8bf742e` (Task 2)

---

**Total deviations:** 2 auto-fixed (1 blocking, 1 bug).
**Impact on plan:** both were in-scope correctness fixes required to keep the existing 358-test baseline green; no scope creep, no architectural change.

## Issues Encountered

- The `_ml_fixtures` sculpted world needed to produce at least one WIN and one LOSS label through `run_chain` + `replay_symbol`; the detector's swing/pool/zone confirmation was sensitive to the price path. Resolved by keeping a single flat base level and placing the second long tap at a lower pool level (1.09) so the loss trades to SL — verified to yield exactly 1 WIN + 1 LOSS.
- The L1 falsifiability mutation test required a real slice leak (reading one bar past the decision index); a deterministic/constant future-bar leak is prefix-invariant so L1 could not catch it. The leak mutation was implemented as a re-implementation that slices `[:decision_idx+2]`, which makes boundary labels differ between prefix and full runs — proving L1 can fail.

## User Setup Required

None - no external service configuration required.

## Self-Check: PASSED

All 6 deliverable files and the SUMMARY exist on disk; all 5 task commits present in git history; full unit suite green (392 passed); ruff clean; import version check 4.7.0 / 1.9.0 / 1.6.0.

## Next Phase Readiness

- AI-01 is satisfied at the unit level: features assembled point-in-time with the decision-close R:R rule and session-gap robustness pinned by named tests, and the three-layer audit passes on the synthetic world (`max_abs_diff 0.0`, `n_labels_checked > 0`).
- SC1 evidence now exists as a checkable, persisted-artifact writer (`write_feature_audit` → `data/reports/feature_audit.json`), ready for plan 04-02/04-03's runner.
- Wave-0 gaps closed: lightgbm/scikit-learn installed and verified; `ml_*` config keys documented; `_ml_fixtures` module in place.
- No blockers for the next plan (04-02: train/folds/scorer). Note for later plans: plan 02 introduces the train/scorer tests consuming `synthetic_feature_frame` and the existing `sculpted_label_world`.

---
*Phase: 04-ml-scoring*
*Completed: 2026-09-03*
