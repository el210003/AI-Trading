---
status: complete
phase: 06-setups-dashboard
source: [06-VERIFICATION.md]
started: 2026-09-04T11:40:00Z
updated: 2026-09-07T07:30:00Z
---

## Current Test

[testing complete]

## Tests

### 1. Interactive Streamlit dashboard run
expected: Launch the dashboard against a populated setup store; confirm table + filters, candlestick with entry/SL/TP + sweep/PD-zone overlays, evidence detail trace, and the History/Performance/Health tabs render.
result: passed (human visual review 2026-09-05) — 18-row populated store (all statuses), filters + Reset/Refresh, candlestick with Entry/SL/TP/Sweep overlays, 6-section evidence trace, History/Performance/Health tabs render; locked dark palette applied.

### 2. Drive the scheduled engine against live MT5
expected: Run the MT5-free engine directly against the live MT5 terminal; confirm a real setup is assembled after the M15 close and the health strip shows connected + last-bar times. (Live heartbeat/trigger timing — human-only.)
result: passed (human confirmation 2026-09-07) — engine --monitor drove live post-close passes from 23:52Z Mon; collector heartbeat 00:00:03Z with all-12-state freshness; health strip human-confirmed (bars 2026-09-07 00:00 UTC, connected). First live (non-backfill) setups assembled at M15 closes 02:01Z/04:02Z UTC (4 rows: EURUSD×2 long, GBPUSD long, USDJPY short; source=ml_llm, agreement=agree), then pending→expired via the 8-bar trigger window — full assembly→trigger→lifecycle seam proven on live data. Note: no entry filled yet (all expired untriggered); first live tp_hit/sl_hit outcome still accrues naturally post-milestone.

### 3. Performance-caveat readability
expected: The Performance panel's live-vs-backtest comparability caveat renders clearly and is human-readable.
result: passed (human visual review 2026-09-05) — Trades: 2 (resolved WIN rows from the populated store), KPI cards + equity curve render, and the caveat caption is readable verbatim: "Live is a trigger-filtered subset of the backtest universe (live limit-trigger fill vs the backtest next-open fill); R is structural (signals-only, no cost model)."

### 2a. Weekend data feed (BTCUSD collect-only split)
expected: With the collect-only BTCUSD config change (setup_symbols split), the running collector stores fresh BTCUSD bars over the closed forex weekend and the health strip shows connected with fresh BTCUSD last-bar times.
result: passed (observed 2026-09-05) — BTCUSD M15 34755→34758 bars across three live M15 closes under the detached collector monitor; BTCUSD heartbeat ~11 min old (connected), forex feeds correctly frozen at Friday 20:45 UTC last bar.

## Summary

total: 4
passed: 4
issues: 0
pending: 0
skipped: 0
blocked: 0

## Gaps
