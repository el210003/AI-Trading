---
title: Define replay-gate acceptance criteria + rollback triggers
date: 2026-09-07
priority: medium
---

# Define replay-gate acceptance criteria + rollback triggers

Design work for SEED-005 that can happen BEFORE milestone-v2 opens — it is
spec work, not code.

## Questions to answer

1. **Beat metric** — what must a challenger win on vs the incumbent, over
   walk-forward replay of stored history? Candidates: walk-forward AUC,
   calibration (Brier / reliability slope), expectancy in R of setups the
   candidate would have traded, or a composite. Must handle: fewer-but-better
   selection changes (candidate trades half as many setups — which metric
   normalizes for that?).
2. **Margin & window** — how decisive must the win be (bootstrap/PSM over
   folds?) and over how many replay folds? Guard against promoting a
   challenger that wins on one lucky regime.
3. **Management-rule scoring** — replay currently applies fixed barriers;
   what gate-equivalent exists for SL/TP management variants (replay with
   variant barriers = same engine, different parameters — verify no leakage
   through the variant's own path).
4. **Rollback trigger** — live reliability drift bound that auto-reverts:
   which statistic (reliability slope? hit-rate vs predicted over rolling
   resolved window?) and threshold — depends on the label-count floor (see
   research question).
5. **Audit surface** — what the Health tab must show per swap: incumbent,
   challenger, gate verdict numbers, timestamp (honesty DNA: loop state
   visible, not just happy path).

## Inputs to read first

- `.planning/notes/self-improvement-loop-decisions.md`
- `.planning/seeds/SEED-005-autonomous-self-improvement-loop.md`
- `src/ai_trading/backtest/replay.py`, `barriers.py`, `ml/walkforward.py`,
  `ml/evaluate.py`
- Setup store live-outcome schema (`setup/store.py`)
