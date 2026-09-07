---
title: Spec the USD-cluster schema (trade 1, shadow 4)
date: 2026-09-07
priority: medium
---

# Spec the USD-cluster schema (trade 1, shadow 4)

Design work for SEED-006 before any pair is added — the schema decides what
the store, lifecycle, ML, and dashboard must each support.

## Surface to specify

1. **`cluster_id` schema** — deterministic id from (decision-bar time UTC,
   USD direction); where it lives in the setup-store schema (new column on
   all rows; backfill-tag historical EURUSD/GBPUSD/USDJPY rows retroactively?)
2. **Representative rule** — best R:R? highest sweep strength? highest P(win)?
   Must be computable at assembly time from data already in hand (no
   look-ahead). Record *why* each member lost representative status
   (auditability).
3. **Shadow lifecycle semantics** — `is_shadow` flag: shadows resolve
   tp_hit/sl_hit/expired normally but (a) never occupy the D-05 live slot,
   (b) are filtered from live KPI/Performance (they'd inflate win-rate
   evidence), (c) appear on the dashboard greyed/grouped under the
   representative.
4. **Cluster detection at assembly** — same decision bar + consistent USD
   direction across `setup_symbols` (e.g. EURUSD long ≡ USDCHF short ≡
   USDCAD long = "sell USD"); reuse detector outputs, no new correlation
   statistics.
5. **Backtest mirror** — `backtest/candidates.py` tags clusters the same way
   (shared helper, ONE implementation for both live and replay — rule-drift
   is the failure mode).
6. **ML consumption** — v1: shadows excluded from training (flag filter, no
   schema surgery). v2: cluster-as-one-sample via cross-symbol embargo
   extension in `ml/purge.py` + cluster-robust eval variance.
7. **Dashboard** — cluster cards: representative expanded, shadows collapsed;
   Health/Performance unaffected.

## Inputs to read first

- `.planning/seeds/SEED-006-more-usd-pairs-cluster-dedup.md`
- `.planning/notes/usd-pair-expansion-decisions.md`
- `src/ai_trading/setup/assembly.py`, `lifecycle.py`, `store.py`
- `src/ai_trading/backtest/candidates.py`, `ml/purge.py`
