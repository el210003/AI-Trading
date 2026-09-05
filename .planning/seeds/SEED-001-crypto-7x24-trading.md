---
id: SEED-001
status: dormant
planted: 2026-09-05
planted_during: v1.0 milestone, Phase 6 (setups-dashboard) — final UAT check pending
trigger_when: v1.0 milestone closes (first /gsd-new-milestone planning)
scope: large
---

# SEED-001: Crypto 7x24 trading — make BTCUSD setup-eligible

## Why This Matters

Forex closes over the weekend (Fri ~21:00 UTC → Sun ~21:00 UTC), which froze live
verification every weekend and motivated the collect-only BTCUSD data feed (v1).
Making BTCUSD a full setup-eligible symbol extends the hybrid-AI pipeline to a
7x24 instrument: the setup engine, lifecycle resolution, and dashboard stay
permanently live, and the system trades a market where SMC liquidity concepts
behave differently (crypto volatility profile).

Groundwork already in place: a full year of BTCUSD M15/H1/H4 bars is collected
(via the `setup_symbols` collect-only split) and flows continuously under the
detached collector monitor.

## When to Surface

**Trigger:** the v1.0 milestone closes — surface during the first
`/gsd-new-milestone` planning session for the next milestone.

## Scope Estimate

**Large** — milestone-sized. Known work items (identified 2026-09-05):

1. **Cost-model calibration** — `pip_size.BTCUSD` + `default_spread_points_by_symbol`;
   the 20-point forex default ≈ $0.20 on BTC while real BTC spread ≈ $5 (500+
   points). The empirical spread distribution is measurable directly from the
   stored year of BTCUSD bars.
2. **Detector economics under crypto volatility** — whether `min_rr=1.0`, the
   96-bar (24h) time barrier, and zone/sweep lifecycle conventions produce
   sensible labels for BTC; needs backtest evidence before enabling.
3. **ML pooled-model retrain** — `symbol` is a pinned categorical
   (`_CATEGORICAL_CATEGORIES` = the 3 majors); adding BTCUSD labels requires
   updating the pin and retraining, with walk-forward evidence.
4. **Constraint amendment** — PROJECT.md Out of Scope ("non-forex instruments —
   forex majors only for v1") must be consciously amended at the milestone
   boundary.

## Breadcrumbs

- `config.toml` — `symbols` / `setup_symbols` collect-only split (added 2026-09-05)
- `src/ai_trading/config.py` — `engine_symbols` property, pip_size validation scope
- `src/ai_trading/ml/features.py` + `src/ai_trading/ml/train.py` — pinned `_CATEGORICAL_CATEGORIES`
- `src/ai_trading/backtest/runner.py` — engine-universe symbol validation
- `data/bars/BTCUSD_M15.parquet` — 34k+ bars of ready-to-analyze history
- `PROJECT.md` — Out of Scope constraint to amend
- `.planning/todos/completed/2026-09-05-add-btcusd-symbol-for-weekend-data-capture.md` — the analysis that surfaced this seed

## Notes

Planted 2026-09-05 after the collect-only BTCUSD feed went live and the user
proposed 7x24 trading. Decision made to close v1 first (one UAT check remaining),
then plan this as its own milestone with proper research on crypto label
economics — not an ad-hoc `setup_symbols` flip.
