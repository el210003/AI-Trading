---
title: Self-improvement loop — exploration decisions
date: 2026-09-07
context: /gsd-explore session during v1.0 close-out; produced SEED-005
---

# Self-improvement loop — decisions from exploration

Design decisions locked in the 2026-09-07 explore conversation (verbatim
intent for milestone-v2 planning):

## 1. Scope: ALL four improvement layers

- Better **predictions** (P(win) calibration/accuracy from flowing outcomes)
- Better **setup selection** (which situations to trade; thresholds,
  symbol-TF selection evolve)
- Better **trade management** (learned entry/SL/TP per regime vs fixed 1:2)
- Better **evidence trust** (measured predictive value of LLM verdicts and
  evidence patterns feeds back into prioritization)

## 2. Autonomy: fully autonomous

No human-approval step for learned changes ("Propose & approve" rejected).
Dashboard reports changes after the fact (model version per setup, audit
trail) — honesty is in *visibility*, not *veto*.

## 3. Safeguard: replay gate + auto-rollback (decided)

- **Gate:** candidate must beat incumbent on walk-forward replay over stored
  history before going live. Machine-judged adoption criteria — autonomous,
  not human-gated.
- **Rollback:** live reliability drift past a bound reverts to incumbent.
- **Rejected:** ungated fastest loop.
- **Central risk named:** selection-effect feedback trap — autonomous changes
  to selection/management determine which data future learning sees; a bad
  change erases the evidence that would reveal it. Replay gate exists for
  exactly this.

## 4. Reality check: fuel

Live labels mature ~1/symbol/day (8-bar trigger + 24h barrier); store is
~365d deep. Early loop generations learn mostly from backfilled history →
SEED-002 (deep backfill) is a functional dependency, not a nice-to-have.

## 5. Sequencing

Milestone-v2 headline; "start now" — replay-gate infrastructure planned
immediately at v2 open, before live label volume matters.

## Existing machinery this reuses

- `backtest/replay.py`, `backtest/barriers.py` — gate = replay candidate vs
  incumbent, compare verdicts (no new replay infra needed)
- `ml/walkforward.py`, `ml/train.py` + `ml_retrain_enabled` knob — scoring layer
- Setup store — live outcome accumulation (labels-for-training already flow
  through the same schema as backtest labels)
