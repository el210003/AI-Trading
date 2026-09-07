# Phase 4: ML Scoring - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-09-02
**Phase:** 4-ML Scoring
**Areas discussed:** Positive label definition

---

## Positive label definition

| Option | Description | Selected |
|--------|-------------|----------|
| P(WIN), TIMEOUT excluded (Recommended) | Binary WIN-vs-LOSS among decided trades; TIMEOUT excluded from training and eval. Matches the A4 win-rate denominator pinned in Phase 3. | ✓ |
| Conservative: TIMEOUT = LOSS | TIMEOUT counts as LOSS: P(hits TP within the 24h barrier). Simpler story, punishes slow winners. | |
| 3-class outcome | P(WIN)/P(TIMEOUT)/P(LOSS) multi-class. Richer but complicates binary calibration and dashboard display. | |

**User's choice:** P(WIN), TIMEOUT excluded
**Notes:** Dashboard semantics recorded: "probability this setup hits TP before SL" among decided trades.

### Follow-up: TIMEOUT treatment in eval artifacts

| Option | Description | Selected |
|--------|-------------|----------|
| Score-and-flag (Recommended) | Scorer emits probability for every row; TIMEOUT rows flagged `excluded` in reports, out of headline metrics. | ✓ |
| Drop entirely | TIMEOUT rows never appear in any Phase 4 artifact. | |
| You decide | Defer to research/planning discretion. | |

**User's choice:** Score-and-flag

### Follow-up: pooled vs per-symbol model

| Option | Description | Selected |
|--------|-------------|----------|
| One pooled model (Recommended) | One model across symbols/timeframes; symbol + timeframe as categorical features. | ✓ |
| Per-symbol models | 3 artifacts; each sees ~1/3 of an already-tiny dataset. | |
| Pooled now, revisit later | Pooled with a documented revisit trigger post-backfill. | |

**User's choice:** One pooled model
**Notes:** Revisit-after-backfill recorded as a deferred idea anyway.

### Follow-up: expected-R regression head

| Option | Description | Selected |
|--------|-------------|----------|
| Probability only (Recommended) | Exactly AI-02 scope: calibrated P(WIN). No secondary target. | |
| Add expected-R head | Secondary net-R regressor; +1 artifact/calibration surface. | |
| You decide | Agent discretion. | ✓ |

**User's choice:** You decide
**Notes:** Agent resolved: probability only in v1; expected-R logged as deferred (tiny decided-trade set makes regression noise; versioned artifacts allow non-breaking addition later).

---

## the agent's Discretion

- Expected-R scope resolution (probability only) — see D-04
- Training data depth strategy (backfill vs tiny-window training) — surfaced as D-05 but not debated; research must resolve with the collector-backfill option on the table

## Deferred Ideas

- Expected-R regression head (post-backfill candidate)
- Per-symbol model split (revisit after deep history)
- ENH-01 calibration reliability dashboard report (v2)
- Real-data demo + history-depth backfill (Phase 3 UAT deferred item; requires MT5 terminal)
