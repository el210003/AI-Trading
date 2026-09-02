---
status: complete
phase: 03-backtesting-labeling
source: [03-VERIFICATION.md]
started: 2026-09-02T15:40:00Z
updated: 2026-09-02T16:05:00Z
---

## Current Test

[testing complete]

## Tests

### 1. A1 cost-asymmetry convention confirmation
expected: Bid-side bars: LONG crosses spread at ENTRY, SHORT at EXIT; net round-trip = spread_px + 2*slip both directions (pinned by test_long_short_cost_symmetry). Confirm this matches your intended convention.
result: pass

### 2. D-10 SL-first intrabar tie convention confirmation
expected: Read src/ai_trading/backtest/barriers.py module docstring + tests/unit/test_barriers.py::test_tie_sl_first_including_entry_bar. Confirm SL-first on every bar (entry bar included) is the intended conservative labeling rule (intrabar path unknowable from OHLC; no tie heuristic that flatters win rates).
result: pass

### 3. Real-data demo run with history-depth decision
expected: Stored M15 history is ~9 days, below D-21's 30-day gate. Decide ONE of: (1) deepen stored history via Phase 1 purge+backfill, (2) run with --min-history-days override + shorter --range, or (3) demo on H4-range depth. Then run: uv run python -m ai_trading.backtest --config config.toml --range last-ND --write. Expected: gate refusal (exit 1, actionable remedy, no artifacts) below the gate without override; successful run (exit 0) writes data/labels/{SYMBOL}_M15.parquet, canonical_stats.json, run_manifest.json, data/reports/walkforward.parquet, walkforward_manifest.json; zero candidates is a valid exit-0 outcome with schema-correct empty artifacts.
result: pass
reason: "User accepted synthetic-only evidence; real-data demo deferred (history-depth decision postponed to a later data task)"

## Summary

total: 3
passed: 3
issues: 0
pending: 0
skipped: 0
blocked: 0

## Gaps
