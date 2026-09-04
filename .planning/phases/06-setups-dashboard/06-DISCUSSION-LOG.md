# Phase 6: Setups & Dashboard - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-09-04
**Phase:** 6-Setups & Dashboard
**Areas discussed:** Setup emit vs fill model
**Note:** Visual/layout decisions were locked separately in `06-UI-SPEC.md` (approved); this discussion covers the implementation/lifecycle semantics only.

---

## Setup emit vs fill model

### Q1: When a D-01 candidate fires at the M15 close, the setup's initial state and fill semantics?

| Option | Description | Selected |
|--------|-------------|----------|
| Signal → limit-trigger (Recommended) | Candidate = live SIGNAL (entry/SL/TP shown); stays `pending` until price trades through entry (limit) on a later M15 bar → `active`; else expires. Fits signals-only v1. | ✓ |
| Assume-filled next open | Mirror backtest D-04 — position filled at next open, immediately `active`. Simpler but auto-assumes the trade. | |
| Signal + separate fill record | Always emit signal; separately detect a fillable entry and attach a trade sub-record. Most faithful, doubles the state machine. | |

**User's choice:** Signal → limit-trigger
**Notes:** Diverges from the backtest's next-open fill (D-04) by design — v1 is signals-only.

### Q2: How does an entry-triggered (active) setup resolve?

| Option | Description | Selected |
|--------|-------------|----------|
| Active monitors TP/SL + time expiry (Recommended) | TP→`tp_hit`, SL→`sl_hit`, else 96-bar (24h) barrier → `expired` (closed at that bar); invalidated if structure/zone breaks first. Mirrors Phase 3 triple-barrier, bounded lifecycle. | ✓ |
| Active resolves on TP/SL only | No active-phase timeout, unbounded open trades. | |
| Fully configurable barriers | Everything configurable, most knobs. | |

**User's choice:** Active monitors TP/SL + time expiry

### Q3: Live active-phase exit rules — mirror backtest (comparable stats)?

| Option | Description | Selected |
|--------|-------------|----------|
| Mirror backtest D-10/D-11/D-17 (Recommended) | SL-first tie on every bar incl. trigger bar; gapped-open fills at open; 96-bar inclusive barrier. One shared exit rule set; live R comparable to backtest stats. | ✓ |
| Simplified live-only rules | Sequential/close-first; live won't match backtest stats, causing apparent discrepancies. | |
| Configurable live rules | Independent of backtest, most flexibility, less comparability. | |

**User's choice:** Mirror backtest D-10/D-11/D-17

### Q4: Pending (untriggered) phase — trigger window + pre-trigger invalidation?

| Option | Description | Selected |
|--------|-------------|----------|
| N-bar trigger window + zone-invalidation (Recommended) | Configurable trigger window (e.g. 8 M15 bars); if the tapped zone/pool invalidates before the trigger → `invalidated` (no entry); else `expired` at window end. Bounded, avoids stale signals. | ✓ |
| No time expiry, invalidate only | Pending waits indefinitely for a trigger; only structure/zone invalidation ends it (stale signals can linger). | |
| Configurable pending window | Pending expiry + pre-trigger invalidation separately configurable. | |

**User's choice:** N-bar trigger window + zone-invalidation

---

## the agent's Discretion (not discussed)

- Scheduled engine trigger (poll M15 close / on-demand CLI; run schedule)
- Setup qualification + LLM timing (min P(WIN) filter; eager vs on-demand narrative)
- Dashboard refresh + health semantics (manual + auto-refresh; live MT5 vs persisted health)
- Trigger-window default bar count; exact trigger-condition check (high/low touch vs close); per-symbol vs global window
- Setup store location/schema (SQLite/Parquet under data/)

## Deferred Ideas

- Order execution / auto-fill (next milestone; v1 signals-only)
- ENH-01..06 (calibration/agreement reporting, alerts, MTF badge) — v2 tracked
- Live-vs-backtest label divergence documented in the Performance panel
