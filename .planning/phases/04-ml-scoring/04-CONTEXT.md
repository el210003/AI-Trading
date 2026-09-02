# Phase 4: ML Scoring - Context

**Gathered:** 2026-09-02
**Status:** Ready for planning

<domain>
## Phase Boundary

Calibrated LightGBM setup-probability scoring built on Phase 2 detector state and Phase 3 labels: a point-in-time feature builder from SMC state with an explicit feature audit (AI-01), a LightGBM binary classifier with calibrated probabilities via CalibratedClassifierCV (AI-02/03), versioned model artifacts (model + calibrator + feature metadata) loadable by a scorer API (SC4), walk-forward training/evaluation reusing the Phase 3 harness with no shuffled splits (AI-04), and a heuristic-score bootstrap for unlabeled periods. Scope covers AI-01…AI-04 only: no LLM (Phase 5), no setup assembly or dashboard (Phase 6), no online/continuous retraining (scheduled reviewed retrains only), no live scoring loop (Phase 4 delivers the loadable scorer; Phase 6 calls it).

</domain>

<decisions>
## Implementation Decisions

### Model Target (Positive Label)
- **D-01:** The model predicts **binary P(WIN) among decided trades**: positive class = WIN (TP hit), negative = LOSS (SL hit). TIMEOUT rows are **excluded from training and from headline metrics** — consistent with the Phase 3 A4 win-rate denominator (wins/(wins+losses)). Dashboard semantics: "probability this setup hits TP before SL".
- **D-02:** **Score-and-flag for TIMEOUT**: the scorer emits a probability for every candidate row; in walk-forward eval artifacts TIMEOUT rows appear flagged `excluded` (with their scores) but are kept out of headline metrics (AUC, calibration curve, win-rate). No metric contamination, no information loss.
- **D-03:** **One pooled model** across all symbols and timeframes: symbol and timeframe enter as categorical features. A single versioned artifact; per-symbol model splits are explicitly NOT v1 (dataset too small to split three ways).

### Scope Boundaries
- **D-04:** **Probability only** — no expected-R regression head in v1 (agent discretion, resolved). AI-02 asks for a probability score; a regressor on the current tiny decided-trade set would be noise. Logged as a deferred idea.

### Training Data Reality (surfaced, not debated — research must resolve)
- **D-05:** The M15 store holds ~9 days of history (Phase 3 research reality) — far below robust LightGBM training depth. The user did not lock a strategy in discussion. Research MUST evaluate: (a) deepening stored history via the Phase 1 collector's backfill path (DATA-04; requires the user's MT5 terminal running), vs (b) training tiny with the harness's small-window support (D-20), vs (c) pipeline-first + backfill as a data task. Roadmap plan 04-03's heuristic-score bootstrap for unlabeled periods exists precisely for thin-data periods. The Phase 3 UAT deferred real-data demo (history-depth decision) is a prerequisite data task for any real training run.

### the agent's Discretion
- Feature engineering details: exact features, encodings, transforms — grounded in the point-in-time constraint and the feature audit
- Feature audit implementation (how "nothing post-decision-bar" is proven — e.g., snapshot/recompute comparison tests)
- LightGBM hyperparameters, search policy, early stopping, class-imbalance handling
- Calibration method within CalibratedClassifierCV (isotonic vs Platt/sigmoid) and calibration fold strategy compatible with walk-forward (no shuffled splits)
- Train/test boundary purge mechanics — the obligation deferred from Phase 3 RESEARCH OQ5 (embargo/leakage handling at window boundaries)
- Model artifact format (e.g., joblib bundle) + versioning scheme + loader API shape for the scorer
- Heuristic-score bootstrap design for unlabeled periods (what the heuristic is, how it's flagged as non-ML)
- Retrain CLI design (follows the Phase 3 `backtest` runner CLI pattern) and scheduled-retrain config keys
- Eval report format (reliability data, per-window metrics) and on-disk layout under `data/`

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Locked scope + goals
- `.planning/ROADMAP.md` — Phase 4 goal, success criteria SC1–4, plan breakdown 04-01…04-03
- `.planning/REQUIREMENTS.md` — AI-01…AI-04 definitions; AI-05…AI-07 belong to Phase 5 (do not absorb); Out of Scope table (no online retraining); ENH-01 calibration reliability report is v2
- `.planning/PROJECT.md` — core value (transparent, verifiable evidence), hybrid AI separation (ML owns probability; separable components)

### Phase 3 contracts (what the model consumes)
- `.planning/phases/03-backtesting-labeling/03-CONTEXT.md` — labels D-18 (WIN/LOSS/TIMEOUT), tie/gap rules, walk-forward D-19/D-20 (expanding train/rolling test, small windows), artifact layout (`data/labels/`, `data/reports/`), D-21 history gate
- `.planning/phases/03-backtesting-labeling/03-RESEARCH.md` — data realities (M15 ~9 days, spread stored in POINTS), Open Questions (RESOLVED) incl. OQ5 purge obligation deferred to this phase, Validation Architecture
- `.planning/phases/03-backtesting-labeling/03-VERIFICATION.md` — verified Phase 3 contract (16/16 must-haves; what the harness guarantees)
- `.planning/phases/03-backtesting-labeling/03-01-SUMMARY.md`, `03-02-SUMMARY.md`, `03-03-SUMMARY.md` — what shipped: chain runner, LABEL_COLUMNS 20-col label frame (incl. entry/exit stamps), walkforward windows + per-window stats, runner CLI

### Phase 2 contracts (feature sources)
- `.planning/phases/02-smc-detection-engine/02-CONTEXT.md` — D-12 full zone history retention (kept FOR Phase 4 features), D-14 lean MTF payload (bias, range, dist-to-equilibrium ATR, containing zone IDs), D-15 confirmation-time as-of rule (the lookahead trap features must respect)
- `.planning/phases/02-smc-detection-engine/02-VERIFICATION.md` — verified detector guarantees the feature builder inherits

### Phase 1 foundations
- `.planning/phases/01-data-foundation/01-RESEARCH.md` — MT5 time semantics, closed-bars invariant, pandas 3.x realities
- `.planning/phases/01-data-foundation/01-PATTERNS.md` — pattern-of-record conventions

### Code (integration surface)
- `src/ai_trading/backtest/barriers.py` — LABEL_COLUMNS 20-col label contract incl. entry/exit stamps and r_gross/r_raw/r_net
- `src/ai_trading/backtest/walkforward.py` — the walk-forward window harness Phase 4 MUST reuse (expanding train/rolling test, zero-label contract)
- `src/ai_trading/backtest/candidates.py` — D-01…D-13 entry-candidate pure functions (feature provenance: the candidate's own decision-time state)
- `src/ai_trading/backtest/replay.py` + `asof.py` — point-in-time slicing machinery (STAMP_CLOSE/STAMP_BAR anchors) the feature builder must respect
- `src/ai_trading/backtest/stats.py` — canonical stats conventions (A4 denominator, PF decided-trade ratio) eval reports must stay consistent with
- `src/ai_trading/backtest/runner.py` + `__main__.py` — CLI pattern (exit-code contract, D-21 gate) for the retrain CLI
- `src/ai_trading/detectors/mtf.py` — lean payload builder (D-14) for HTF features
- `src/ai_trading/config.py` — frozen Config + fail-fast validation pattern for new ML config keys
- `tests/unit/_backtest_fixtures.py` + `tests/conftest.py` — synthetic bar/label fixtures for feature-audit and training tests

### Test conventions
- `.planning/phases/01-data-foundation/01-VALIDATION.md` — Nyquist verification map; unit/mt5 marker layering
- `tests/unit/test_replay_repaint.py` — the point-in-time test pattern the feature audit should mirror

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `backtest/walkforward.py` — window derivation, label-window assignment, per-window stats: training/eval folds come from here, not new split logic
- `LABEL_COLUMNS` label frame (Parquet, `data/labels/`) — training-ready records with entry/exit stamps, outcomes, R variants, spread/point context
- `asof.py` visible_mask + STAMP_CLOSE/STAMP_BAR anchors — the exact machinery for point-in-time feature assembly
- `candidates.py` — decision-time candidate state (direction, zone/pool refs, R:R) is the feature seed
- `stats.py` — reliability/win-rate conventions to keep eval reports consistent with dashboard panels
- `make_bars` + `_backtest_fixtures.py` — deterministic synthetic data for unit tests and the feature audit

### Established Patterns
- Pure functions, zero vendor imports outside the adapter tier; ML modules must stay MT5-free and side-effect-free until the runner tier
- Frozen `Config` dataclass extension with fail-fast validation for new knobs (feature list version, calibration method, embargo bars, retrain schedule)
- Atomic tmp+os.replace artifact writers (bar_store/reports discipline) for model artifacts and eval reports
- pytest `unit`/`mt5` markers; ruff line-length 100; zero new dependencies except the locked LightGBM + scikit-learn

### Integration Points
- **Phase 5 LLM**: consumes the evidence object + calibrated P(WIN); ML↔LLM agreement flag (AI-06) needs the score + contributors Phase 4 emits
- **Phase 6 Setups**: setup assembly calls the loadable scorer (model + calibrator + feature metadata artifact, SC4); heuristic bootstrap covers unlabeled periods
- **Dashboard (Phase 6)**: reliability/calibration data recorded in this phase feeds the honesty of displayed probabilities (ENH-01 is v2 display work)

</code_context>

<specifics>
## Specific Ideas

- SC2 wording is binding: "reliability data recorded via CalibratedClassifierCV" — the calibration artifact must retain reliability data, not just the calibrated model
- SC1 wording is binding: a feature audit must CONFIRM point-in-time assembly — plan 04-01 is dedicated to it
- SC3 wording is binding: training/evaluation uses the Phase 3 walk-forward harness — no shuffled splits anywhere, including inside calibration folds
- AI-04's "no shuffled splits" extends to any CV inside hyperparameter search — TimeSeriesSplit-style only
- Pooling decision (D-03) means the training table is the union over symbols/timeframes of decided-trade labels
- The scorer API surface Phase 6 will call should be importable and MT5-free (load artifact → score feature dict/frame → P(WIN) + contributors)

</specifics>

<deferred>
## Deferred Ideas

- **Expected-R regression head** — surfaced in discussion, resolved out of v1 scope (D-04). Natural candidate after deep-history backfill makes decided-trade counts meaningful; versioned artifacts make it a non-breaking addition.
- **Per-symbol model split** — revisit trigger: after deep history exists, evaluate whether per-symbol models beat the pooled model on walk-forward evidence.
- **ENH-01 calibration reliability report in dashboard** — v2 display work; Phase 4 only records the reliability data.
- **Real-data demo run + history-depth backfill** — Phase 3 UAT deferred item; a data task requiring the user's MT5 terminal. Prerequisite for any real (non-synthetic) training run in this phase.

</deferred>

---

*Phase: 4-ML Scoring*
*Context gathered: 2026-09-02*
