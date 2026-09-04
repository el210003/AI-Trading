---
status: resolved
trigger: Zone lifecycle generates zero real-data candidates on MT5 forex data — ~99.9% of SMC zones invalidate (D-11) before reaching the mitigated (D-10) state, so the Phase 3 D-01 entry-candidate rule (sweep + same-bar zone tap) never fires, producing an empty label store and blocking real-data ML training.
created: 2026-09-04T07:10:00Z
updated: 2026-09-04T09:40:00Z
root_cause: |
  Zero candidates was the symptom, not the cause — the detectors fire fine (thousands of sweeps/zones on real data). Four stacked point-in-time/real-data issues surfaced only when the pipeline was first run on real MT5 data:
  1. candidates.py:205 tested the FINAL `state=="mitigated"` from derive_zones (99.9% `invalidated` on real data) instead of the as-of state; ~4706 zones ARE mitigated (`mitigated_at==created_at`), but a zone mitigated on bar S then invalidated later read as `invalidated` at S. Fixed by reconstructing as-of: mitigated_at==bar_t AND (invalidated_at is NaT OR invalidated_at>bar_t).
  2. candidates.compute_rr: real data can produce zero structural risk (next-bar open == SL level) → ZeroDivisionError. Guarded risk<=0 → 0.0 (D-12 min_rr then discards).
  3. ML feature audit / LightGBM categoricals: `.astype("category")` auto-derived categories that drifted (['long'] vs ['long','short'], per-fold symbol sets), failing the L1 prefix-equivalence exact check AND LightGBM "categorical_feature do not match". Fixed by pinning canonical category sets (_CATEGORICAL_CATEGORIES) in features.py + train.py.
  4. ml/audit.py: (a) audit re-ran run_chain (~65s/full year) for range(28,n,15) => ~1655 prefixes on real data = O(n^2) hang; bounded to ~6 sampled prefixes. (b) `labels[bool_series]` misaligned when labels had a non-zero index; switched to positional .iloc.
fix: |
  candidates.py (as-of tap state reconstruction + zero-risk RR guard); features.py + train.py (pinned _CATEGORICAL_CATEGORIES => stable categorical dtypes across splits); audit.py (bounded prefix sampling + positional mask).
verification: |
  Full-year backtest now produces EURUSD 520 / GBPUSD 526 / USDJPY 504 trades (thousands of labels). ML retrain succeeds on real data: 1540 decided labels, 11 walk-forward windows trained (AUC ~0.52-0.70), versioned artifact v1 saved. Full suite 449 passed, no regressions.
files_changed:
  - src/ai_trading/backtest/candidates.py
  - src/ai_trading/ml/features.py
  - src/ai_trading/ml/train.py
  - src/ai_trading/ml/audit.py
---

## Symptoms

- **Expected behavior:** Over a year of real M15 data (EURUSD/GBPUSD/USDJPY, ~24k bars/symbol after a 1-year MT5 backfill), the SMC detector chain should produce a meaningful number of mitigated zones and sweep-tap entry candidates, yielding dozens-to-hundreds of decided-trade labels for ML training.
- **Actual behavior:** `run_chain` produces thousands of swings (6364), pools (5889), zones (5072), and a year's worth of data; BUT the zone lifecycle distribution is `invalidated=5069, mitigated=2, unmitigated=1` for EURUSD. The Phase 3 backtest runner reports **0 candidates for all 3 symbols** over `last-360` (and a 30-day recent slice), so the label store is empty and the ML `ml_min_train_labels` gate refuses training.
- **Error messages:** None — silent zero. Backtest runner logs "0 candidates for EURUSD in last-360: schema-correct backtest summary ... trades: 0 (no candidates in range)". ML runner would report the label-count gate refusal (starvation data).
- **Timeline:** First surfaced when running the deep-history backtest then ML training after a 1-year MT5 backfill (2026-09-04). The Phase 3 real-data demo had been deferred (approved as `pass`), so real data had never exercised the detectors before. Phase 2/3 were validated only on synthetic fixtures (make_bars) that were crafted to produce mitigated zones.
- **Reproduction:** Load real M15/H1/H4 parquet from `data/bars/`, call `run_chain(m15, h1, h4)`, inspect `chain['zones15']['state'].value_counts()` → invalidated dominates. Then `replay_symbol(m15, chain, cfg, walk_barriers)` → 0 labels. `candidate_at_bar` requires a zone with `state=='mitigated'` AND `mitigated_at==bar_t` on the exact same decision bar a visible `event_type=='sweep'` event resolves (D-01). Count of bars with both a zone mitigated at bar_t AND a sweep resolved at bar_t over the year = **0**. Mitigation (D-10: wick touch into the zone) almost never registers before invalidation (D-11: close beyond the zone's far boundary).

## Eliminated

- (none yet)

## Evidence

- timestamp: 2026-09-04T07:20:00Z — EURUSD real M15 (24,855 bars, 2025-09-03→2026-09-03): `derive_zones` produces 5072 zones; `state` value_counts = **invalidated=5069, mitigated=2, unmitigated=1**. Zone lifecycle is *not* the blocker per se: **4706/5072 zones DO set `mitigated_at`** (99.87% of those === `created_at`, i.e. born-tapped on the first bar that advances them). So mitigation is happening; the final `state` column is what says `invalidated`.
- timestamp: 2026-09-04T07:21:00Z — **Root cause localized:** `candidate_at_bar` (src/ai_trading/backtest/candidates.py:205) filters the tap with `zones[(zones["state"]=="mitigated") & (zones["mitigated_at"]==bar_t)]`. The `state` column in the zones frame from `derive_zones` is the **FINAL** lifecycle state (≈99.9% `invalidated`), but the replay (src/ai_trading/backtest/replay.py:256) slices zones only by the `mitigated_at` timestamp via `visible_mask` and never reconstructs the point-in-time state. So a zone legitimately mitigated on the decision bar (`mitigated_at==bar_t`) but invalidated at any later bar reads as `state=="invalidated"` at bar_t → excluded.
- timestamp: 2026-09-04T07:22:00Z — **Quantified:** over EURUSD, tap bars where a zone has `mitigated_at==bar_t` AND is not yet invalidated (`invalidated_at` NaT or `>bar_t`) AND a sweep is visible = **3926**. Of these, `stored state=="mitigated"` = **2** (the two zones that never invalidate). So the stored-final-state filter gates out ~3924 candidate opportunities.
- timestamp: 2026-09-04T07:23:00Z — **Fix produces meaningful output:** with the as-of state reconstructed, EURUSD flows tap=3926 → after D-01 direction=1978 → after D-02 bias=1087 → after D-12 min-RR(>=1)=833. So hundreds of labels would be produced, not zero.
- timestamp: 2026-09-04T07:24:00Z — **Why tests missed it:** tests/unit/test_candidates.py hand-builds zones with `state="mitigated"` and `invalidated_at=NaT` (a point-in-time view), and test_lifecycle.py validates the zone lifecycle only on narrow synthetic fixtures. Neither exercises the mismatch between the real final-state zones frame and the point-in-time state the D-01 rule expects. Synthetic fixtures mask the bug entirely.

## Current Focus

hypothesis: CONFIRMED — the zero-candidate symptom is not caused by zones failing to mitigate (4706 zones do mitigate; ~99.9% born-tapped at created_at) nor by D-01 being "too narrow." The cause is a *state-vs-as-of* mismatch: `candidate_at_bar` requires `zones["state"]=="mitigated"`, but `derive_zones` stores the final lifecycle state (≈99.9% `invalidated`). The replay slices by the `mitigated_at` timestamp but does not reconstruct the point-in-time `state`, so a zone mitigated on the decision bar but invalidated later is excluded. The D-01 same-bar coincidence exists (3926 tap bars this year) but is masked by the wrong state predicate.
next_action: Apply fix — in `candidate_at_bar` (and the replay's zone slice) reconstruct the as-of zone state instead of testing the stored final `state`; a zone is a valid tap on decision bar S iff `mitigated_at==bar_t` AND (`invalidated_at` is NaT OR `invalidated_at > bar_t`). Keep the strict same-bar D-01 semantics validated by fixtures (test_sweep_only_no_mitigated_tap_is_none); do not change derive_zones or any locked decision.
