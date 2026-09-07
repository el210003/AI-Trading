---
title: USD-pair expansion — dedup layer decisions
date: 2026-09-07
context: /gsd-explore session during v1.0 close-out; produced SEED-006
---

# USD-pair expansion — decisions from exploration

## Motivation (user's priority order)

1. Signal throughput (3 symbols = long waits between setups)
2. Regime coverage (AUD/Asia session, CHF safe-haven flows)
3. Pooled-model training fuel (more label diversity)
4. Portfolio breadth (parallel pairs)

## The correlation problem (named explicitly)

USD majors co-fire: same decision bar, consistent USD direction, up to 5
"setups" from one dollar move. Naive expansion ⇒ fake throughput,
pseudo-replicated ML labels, and implicit 5× risk concentration on one idea.

## Why each dedup layer was judged

- **Display-only dedup — REJECTED**: zero code cost but breaks two project
  pillars: model sees 5 correlated labels as independent (inflated sample
  size, shrunken uncertainty — SEED-005 would learn from 5× weight for one
  idea) and live operationally holds 5 positions on one USD move.
- **Assembly-delete — REJECTED**: honest risk (1 position) but the discarded
  members die unknown — never learn if the representative pick was right;
  plus backtest/live history diverges (rule mirrored in two code paths).
- **Cluster-aware labels only — not chosen alone**: statistically cleanest
  but big-engineering-only, no risk fix by itself.
- **Hybrid "trade 1, shadow 4" — ADOPTED**: engine trades only the cluster
  representative; shadow members are stored (`cluster_id`) and resolved by
  lifecycle regardless → free measurement of representative-selection
  quality (feeds SEED-005 gate evidence); label layer counts
  cluster-as-one-sample later (cross-symbol embargo extension in
  `ml/purge.py`); backtest tags clusters, never deletes rows.

## Cluster definition (decided)

Deterministic: same decision bar + consistent USD direction across pairs.
No rolling-correlation estimation at pilot scale. Representative rule
(best R:R? sweep strength?) deferred to `todos/pending/2026-09-07-spec-usd-cluster-schema.md`.

## Rollout (decided)

Pilot = +AUDUSD +USDCHF (deliberately EURUSD's twin + inverse — the hardest
dedup test). Widen to USDCAD/NZDUSD only after clusters prove themselves;
at that point widening is nearly config-only (pip_size, categorical
categories + `ml_feature_list_version` bump + retrain, backfill).
