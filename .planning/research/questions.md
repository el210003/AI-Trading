# Open Research Questions

## SEED-005 — autonomous self-improvement loop

- **Minimum live label count for reliability-drift detection**: how many
  resolved live setups are needed before a rolling hit-rate-vs-predicted
  (reliability) statistic can distinguish real calibration drift from noise
  at an actionable confidence? This sets the auto-rollback trigger floor —
  too low and a lucky losing streak rolls back a good model; too high and
  drift runs unchecked. (Raised 2026-09-07 /gsd-explore; feeds the replay-gate
  criteria todo.)
- **Selection-effect detectability**: beyond the replay gate, is there a
  leading indicator that an autonomous selection change is poisoning future
  training data (e.g., shadow-scoring the retired rule on the new rule's
  feed)?

## SEED-006 — USD-pair expansion + cluster dedup

- **Symbol-addition mechanics audit**: exact retrain blast radius when
  AUDUSD/USDCHF join — `_CATEGORICAL_CATEGORIES` bump +
  `ml_feature_list_version` + full retrain vs incremental; per-symbol
  backfill wall-time from terminal depth; spread-fallback defaults for
  AUDCHF quotes (default_spread_points=20 validity per symbol).
- **Shadow-cluster sample size**: how many resolved USD-clusters (shadow
  members) are needed before representative-selection quality (did the
  chosen member win as often as the best member would have?) is measurable
  at actionable confidence? Sets the bar for trusting the representative
  rule and for widening to the full 7-major basket.
