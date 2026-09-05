---
id: SEED-002
status: dormant
planted: 2026-09-05
planted_during: v1.0 milestone, Phase 6 (setups-dashboard) — final UAT check pending
trigger_when: v1.0 milestone closes (first /gsd-new-milestone planning)
scope: large
---

# SEED-002: ML improvement — deep backfill, capacity, calibration

## Why This Matters

The v1 pooled model is deliberately tiny-capacity LightGBM trained on only
~1,540 decided labels (365 days): walk-forward AUC ~0.52–0.70 — modest
discrimination, and calibration folds (ml_cal_train_days=2) are starved.
Signal quality is the core value of the product; P(WIN) honesty improves only
with more labels and more evidence per label.

**Cheapest big lever first:** the MT5 terminal already holds ~10 years of M15
bars (250,000/terminal_maxbars per symbol — see `data/meta` history_bounds),
while the store keeps only 365 days. A deep backfill to terminal depth would
multiply decided labels ~10x with zero new code — config + collector time.

## When to Surface

**Trigger:** the v1.0 milestone closes — surface during the first
`/gsd-new-milestone` planning session (pairs naturally with SEED-001: deep
backfill also deepens BTCUSD history, and crypto adds pooled-model diversity).

## Scope Estimate

**Large** — milestone-sized. Known levers (ranked by expected value):

1. **Deep backfill** — raise `initial_backfill_days` toward the terminal's
   250k-bar depth → ~15k+ decided labels across 10 years of regimes. Watch:
   backfill rounds/pause knobs, label-regeneration runtime, and drift of the
   broker offset over a decade of stored bars (offset is DST-dependent).
2. **Calibration revisit** — `ml_calibration_method = "sigmoid"` was chosen
   because isotonic overfits ≪1000-sample folds; with 10x labels, isotonic
   becomes viable (config comment already flags "revisit after deep backfill").
   Also revisit `ml_cal_train_days`/`ml_cal_test_days` fold sizing.
3. **Capacity revisit** — `ml_n_estimators=200 / ml_num_leaves=7 /
   ml_min_data_in_leaf=5` were tiny-capacity-by-design for 1.5k labels; scale
   with data, re-walk-forward.
4. **Feature expansion** — v1 FEATURE_SPEC is 18 features (5 categorical +
   13 numeric), version-gated. Candidates: session/time-of-day, ATR/volatility
   regime, sweep recency (the heuristic.py scorer already uses it — the ML
   model does not), spread-at-decision, MTF-bias interactions. Bump
   `ml_feature_list_version` so stale artifacts refuse to load.
5. **Model structure** — pooled vs per-symbol vs hierarchical; `ml_embargo_bars`
   (0 = purge-only) revisit once regime history is deep.

## Breadcrumbs

- `config.toml` — all `ml_*` knobs with rationale comments (capacity, calibration, embargo)
- `src/ai_trading/ml/features.py` — FEATURE_SPEC (ordered source of truth, 18 features)
- `src/ai_trading/ml/train.py` — pinned `_CATEGORICAL_CATEGORIES`, train gate
- `src/ai_trading/ml/heuristic.py` — sweep-recency heuristic (feature-candidate precedent)
- `data/meta/meta.sqlite` history_bounds — terminal_maxbars=250000 vs store depth
- `.planning/phases/04-ml-scoring/` — Phase-4 conventions (A1..: purge/embargo, decided-only labels, pooled model)
- `SEED-001` — crypto milestone; deep backfill benefits both

## Notes

Planted 2026-09-05 from the same conversation as SEED-001. Both seeds surface
at the next `/gsd-new-milestone`; they may combine into one milestone
(deep backfill is the shared enabler) or sequence back-to-back.
