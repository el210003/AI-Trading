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
