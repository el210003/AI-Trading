# Milestones

## v1.0 MVP (Shipped: 2026-09-07)

**Phases completed:** 6 phases, 18 plans, 58 tasks

**Delivered:** A signals-only AI forex SMC trading system — MT5 data foundation, non-repainting SMC detection, shared-code-path backtesting, calibrated ML scoring, evidence-grounded LLM narratives, and a Streamlit dashboard proven on live data.

**Closeout type:** override_closeout — Known verification overrides: 8 (see STATE.md Deferred Items); no pre-close milestone audit run.

**Stats:**

- Git range: `4785ed1` (2026-08-29) → `9d5f25e` (2026-09-07) — 9 days
- 273 files changed, +51,188 insertions
- Python: 135 files, 22,095 LOC
- Requirements: 33/33 v1 requirements complete

**Key accomplishments:**

1. MT5→UTC-normalized data foundation: health-checked collector, idempotent gap backfill, DST-validated broker offset, history depth to 2016 (M15) / 1996 (H1/H4) (Phase 1)
2. Non-repainting SMC detection chain (swings→liquidity pools→sweeps→PD zones) with bar-by-bar lifecycle state and point-in-time MTF context (Phase 2)
3. One shared look-ahead-safe code path: the backtester replays the identical live pipeline with spread+slippage costs, triple-barrier labels, and walk-forward stats (Phase 3)
4. Calibrated LightGBM P(WIN) scorer — leak-audited point-in-time features, versioned artifacts, walk-forward evaluation with no shuffled splits (Phase 4)
5. Evidence-grounded LLM narratives: strict citation check, ML↔LLM agreement flag, graceful ML-only fallback (Phase 5)
6. Live setups + Streamlit dashboard: per-M15-close assembly engine, full lifecycle resolution, charts with evidence traces, history/performance/health panels — first 4 live setups assembled and lifecycle-proven 2026-09-07 (Phase 6)

---
