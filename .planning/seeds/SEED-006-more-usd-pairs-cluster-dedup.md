---
id: SEED-006
status: dormant
planted: 2026-09-07
planted_during: v1.0 milestone close-out (UAT test 2 in progress)
trigger_when: v2 milestone planning (/gsd-new-milestone) — pairs with SEED-005 and SEED-002
scope: medium
---

# SEED-006: More USD majors + USD-cluster dedup ("trade 1, shadow 4")

## Why This Matters

With 3 setup symbols, qualifying candidates are sparse (2026-09-07: zero live
setups all Asian session). Four motivations, in the user's stated priority
order: **signal throughput → regime coverage → pooled-model training fuel →
portfolio breadth**. But USD majors are not independent: a USD-wide move
produces same-instant setups across EURUSD/AUDUSD/USDCHF/USDCAD — naive
expansion multiplies rows without multiplying information, pseudo-replicates
ML labels, and would silently 5× the risk on one dollar idea.

## Adopted design (decided 2026-09-07 /gsd-explore)

**Hybrid dedup: trade the representative, shadow the cluster.**
- Cluster definition (deterministic, no correlation estimation): setups
  sharing the same decision bar + consistent USD direction across pairs.
- Engine *trades* only the representative (one live position per USD-cluster —
  honest 1× risk); representative rule to be specced (best R:R vs sweep
  strength — see todo).
- *Members are still stored* with `cluster_id` and resolved by lifecycle
  anyway → shadow outcomes answer "was the representative the right pick?"
  for free; feeds SEED-005's replay-gate loop with representative-quality
  evidence.
- ML label layer later counts a cluster as ONE effective sample (extend
  `ml/purge.py` embargo logic cross-symbol) — full history kept, no
  pseudo-replication.
- Backtest mirror: tag clusters, never delete rows (keeps live/backtest
  comparability and one rule in one place).
- **Rejected:** display-only dedup (pseudo-replication + hidden 5× risk),
  assembly-delete (blind spot on discarded members, dual code paths).

## Pair strategy: pilot first

**+AUDUSD and USDCHF as setup-eligible (5 total)** — deliberately chosen as
EURUSD's correlated twin and inverse: the pairs most likely to expose cluster
bugs. Widening to USDCAD/NZDUSD (+full 7 majors) is then nearly config-only,
once clusters prove themselves.

## Mechanical checklist (known, cheap)

- `config.toml`: add to `symbols` + `setup_symbols`; `pip_size` entries
  (AUDUSD/USDCHF = 0.0001)
- `ml/train.py` `_CATEGORICAL_CATEGORIES` pins symbol categories → bump
  `ml_feature_list_version` + full retrain (stale artifacts refuse to load —
  by design)
- Collector/backfill per new symbol (`initial_backfill_days = 90`; terminal
  holds ~10y — see SEED-002)
- Broker offset shared (same server) ✓; D-05 per-symbol suppression already
  exists ✓; dashboard symbol filters already generic ✓

## Cross-references

- `notes/usd-pair-expansion-decisions.md` (dedup-layer analysis, verbatim)
- `todos/pending/2026-09-07-spec-usd-cluster-schema.md` (design surface)
- SEED-005 (cluster labels + shadow outcomes are loop fuel),
  SEED-002 (deep backfill covers new symbols' history depth)
