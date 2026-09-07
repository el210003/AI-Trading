---
id: SEED-005
status: dormant
planted: 2026-09-07
planted_during: v1.0 milestone close-out (UAT test 2 in progress)
trigger_when: v1.0 milestone closes — candidate headline for milestone v2
scope: large
---

# SEED-005: Autonomous self-improvement loop (replay-gated)

## Why This Matters

v1 ships the loop's parts but never closes it: Phase-3 replay/labeling
produces history, Phase-4 walk-forward training consumes it, Phase-6 live
setups accumulate outcomes — and nothing yet uses those outcomes to trade
better tomorrow. The user's explicit vision (2026-09-07 /gsd-explore): **all
four layers improve with experience, fully autonomously**:

1. **Prediction calibration** — live resolved outcomes fold back into
   walk-forward retraining (machinery already exists; `ml_retrain_enabled=false`).
2. **Setup selection** — detection thresholds / symbol-TF eligibility evolve
   from historical outcomes.
3. **Trade management** — entry/SL/TP placement learns per regime instead of
   fixed 1:2 R:R (replay over stored bars can score management variants
   without new infrastructure).
4. **Evidence trust** — do LLM refute verdicts actually predict losers? Which
   evidence patterns matter? Feed measured predictive value back into
   prioritization/blending.

## Adopted safeguard (decided in exploration)

**Fully autonomous WITH a replay gate + auto-rollback** — no human approval
step, but no ungated swaps either: every candidate (model, threshold,
management rule) must beat the incumbent on walk-forward replay over stored
history before going live; live reliability drift triggers rollback.
Rationale: the **selection-effect trap** — autonomous selection/management
changes alter which setups enter future training data, so a bad change can
poison the evidence needed to detect it. "No gate, fastest loop" was
explicitly rejected; so was human-proposal approval (autonomy preferred).

## When to Surface

**Trigger:** the v1.0 milestone closes. User chose "v2 headline, start now":
surface at the first `/gsd-new-milestone` as the headline candidate; the
replay-gate infrastructure can start immediately using existing backfill
depth.

## Dependencies & fuel

- **SEED-002 (deep backfill) is the fuel tank** — live labels mature at only
  ~1 resolved setup/symbol/day (8-bar trigger + 24h barrier); early iterations
  necessarily relearn from backfilled history.
- `backtest/replay.py` + `barriers.py` — replay engine to host the gate.
- Reliability-drift floor — see research question (minimum live labels for a
  meaningful rollback trigger).
- Cross-reference: `notes/self-improvement-loop-decisions.md` (verbatim
  decisions), `todos/pending/2026-09-07-define-replay-gate-criteria.md`.

## Notes

Explored 2026-09-07 via /gsd-explore. Honesty DNA applies to the loop itself:
model/rule version must be shown per setup (dashboard already carries
source/version), every automatic swap gets an audit trail, and the Health tab
should reveal the loop's state (incumbent vs challenger, gate verdicts,
rollbacks).
