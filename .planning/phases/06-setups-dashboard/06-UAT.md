---
status: testing
phase: 06-setups-dashboard
source: [06-VERIFICATION.md]
started: 2026-09-04T11:40:00Z
updated: 2026-09-04T11:40:00Z
---

## Current Test

number: 1
name: Interactive Streamlit dashboard run
expected: |
  Launch the dashboard against a populated setup store. Confirm the Setups tab renders the table with filters, the candlestick chart shows entry/SL/TP lines + sweep and PD-zone overlays, and the evidence detail (DASH-01/02/03) renders the ordered trace (bias/zone/sweep/ML contributors/narrative + agreement chip). History/Performance/Health tabs render their content.
awaiting: user response

## Tests

### 1. Interactive Streamlit dashboard run
expected: Launch the dashboard against a populated setup store; confirm table + filters, candlestick with entry/SL/TP + sweep/PD-zone overlays, evidence detail trace, and the History/Performance/Health tabs render.
result: [pending]

### 2. Drive the scheduled engine against live MT5
expected: Run the MT5-free engine directly against the live MT5 terminal; confirm a real setup is assembled after the M15 close and the health strip shows connected + last-bar times. (Live heartbeat/trigger timing — human-only.)
result: [pending]

### 3. Performance-caveat readability
expected: The Performance panel's live-vs-backtest comparability caveat renders clearly and is human-readable.
result: [pending]

## Summary

total: 3
passed: 0
issues: 0
pending: 3
skipped: 0
blocked: 0

## Gaps
