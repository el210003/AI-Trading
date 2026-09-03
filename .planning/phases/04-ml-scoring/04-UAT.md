---
status: testing
phase: 04-ml-scoring
source: [04-VERIFICATION.md]
started: 2026-09-02T16:40:00Z
updated: 2026-09-02T16:40:00Z
---

## Current Test

number: 1
name: Real-data ML training run (deep-history backfill)
expected: |
  Deepen stored M15/H1/H4 history via the Phase 1 collector backfill path (DATA-04 — requires the user's running, logged-in MT5 terminal), then run the retrain CLI: uv run python -m ai_trading.ml --config config.toml. Expected to clear the label-count gate and train + calibrate against real decided-trade labels, producing a versioned bundle under data/models/pooled/v{N}, per-window eval parquets, and reliability data.
awaiting: user response

## Tests

### 1. Real-data ML training run (deep-history backfill)
expected: After MT5 backfill, run the retrain CLI (python -m ai_trading.ml) — clears the label-count gate, trains+calibrates on real decided-trade labels, writes a versioned bundle + eval artifacts. The pipeline is already proven end-to-end on synthetic stores; this is the documented D-05 prerequisite data task.
result: [pending]

## Summary

total: 1
passed: 0
issues: 0
pending: 1
skipped: 0
blocked: 0

## Gaps
