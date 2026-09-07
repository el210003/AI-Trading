---
phase: 02-smc-detection-engine
plan: 02
subsystem: detectors
tags: [smc, liquidity-pools, sweeps, atr, point-in-time, pytest]

requires:
  - "Plan 02-01: detect_swings output schema, wilders_atr, _detector_fixtures helpers"
provides:
  - "ai_trading.detectors.pools.detect_pools — as-of ATR-relative clustering (D-05), 2-touch activation with frozen mean level (D-06/A3), pinned 2-bar inclusive sweep window (D-07/A8), one-and-done terminal states (D-08)"
  - "Pinned schemas: pools (pool_id, symbol, timeframe, side, level, touch_count, state, first_touch_at, activated_at, resolved_at); events (event_id, pool_id, symbol, timeframe, side, level, pierced_at, resolved_at, event_type)"
  - "Deterministic IDs: pool_id {SYMBOL}-{TF}-P{n:04d} in activation order; event_id {pool_id}-E1"
  - "tests/unit/test_pools.py — 11-test SMC-02 suite incl. tier-3 repaint + standalone-vs-in-frame"
  - "tests/unit/test_sweeps.py — 8-test SMC-03 classification suite"
affects: [02-03-zones-lifecycle, 02-04-mtf-join, phase-3-backtester, phase-4-ml-features]

tech-stack:
  added: []
  patterns:
    - "as-of tolerance: tolerance evaluated at each joining swing's confirmation bar only (causal ewm ATR)"
    - "TR-preserving swing sculpts (high=p, low=open=close=p-TR) keep ATR exactly TR for hand-derivable expectations"
    - "pinned output dtypes (StringDtype + datetime64[us]) — pandas value-dependent inference made repaint comparisons dtype-unstable"
    - "point-in-time pierce semantics: any wick crossing pierces; rising touches supersede forming candidates (A5)"

key-files:
  created:
    - src/ai_trading/detectors/pools.py
    - tests/unit/test_pools.py
    - tests/unit/test_sweeps.py
  modified: []

key-decisions:
  - "Strict point-in-time pierce semantics with NO swing-extreme exemption: a bar whose wick crosses the level pierces — cluster members on the original side of the level never pierce (equal retests), and rising touches supersede forming candidates per A5; fixtures build boundary cases from below to stay pierce-free"
  - "Forming candidates appear in the pools frame with state='forming' and NA pool_id (A5 dead-by-supersession is visible state)"
  - "Frame-end contract: a pool still inside its reclaim window stays active/unresolved (no event) — classification requires the full window"
  - "Output dtype pinning (StringDtype for strings, datetime64[us] for stamps) — pandas infers units from values, which made prefix-vs-full repaint comparisons dtype-unstable (caught by tier-3 tests)"
  - "Boundary test builds the inclusive case one ulp inside the exact as-of tolerance (float-exact equality unrepresentable); the detector's <= semantics documented via the constructed assertion"

requirements-completed: [SMC-02, SMC-03, SMC-05]

coverage:
  - id: D1
    description: "As-of ATR clustering: inclusive tolerance at the joining swing's confirmation bar; boundary inside joins, beyond opens separate candidates; equal highs/lows cluster; mean level frozen at activation; third touch increments count not level (D-05/D-06, A3, Pitfall 3)"
    requirement: "SMC-02"
    verification:
      - kind: unit
        ref: tests/unit/test_pools.py#test_equal_highs_cluster_within_tolerance
        status: pass
      - kind: unit
        ref: tests/unit/test_pools.py#test_tolerance_boundary_inclusive_exclusive
        status: pass
      - kind: unit
        ref: tests/unit/test_pools.py#test_equal_lows_cluster_mirror
        status: pass
      - kind: unit
        ref: tests/unit/test_pools.py#test_two_touch_activation_timing_and_level_mean
        status: pass
      - kind: unit
        ref: tests/unit/test_pools.py#test_third_touch_increments_count_not_level
        status: pass
      - kind: unit
        ref: tests/unit/test_pools.py#test_pools_standalone_match_in_frame
        status: pass
    human_judgment: false
  - id: D2
    description: "Warmup skip (Pitfall 7), A5 forming-candidate supersession, empty-frame contracts, input non-mutation"
    requirement: "SMC-02"
    verification:
      - kind: unit
        ref: tests/unit/test_pools.py#test_atr_warmup_produces_no_pools
        status: pass
      - kind: unit
        ref: tests/unit/test_pools.py#test_pierce_while_forming_supersedes_candidate
        status: pass
      - kind: unit
        ref: tests/unit/test_pools.py#test_empty_frame_contracts
        status: pass
      - kind: unit
        ref: tests/unit/test_pools.py#test_input_frames_not_mutated
        status: pass
    human_judgment: false
  - id: D3
    description: "Pool tier-3 repaint: resolved pools immutable under 1-by-1 and chunked appends; prefix pools equal the visible subset of full-frame resolved pools"
    requirement: "SMC-02"
    verification:
      - kind: unit
        ref: tests/unit/test_pools.py#test_resolved_pools_immutable_under_appended_bars
        status: pass
    human_judgment: false
  - id: D4
    description: "Sweep-vs-breakout classification: immediate/next-bar reclaim sweeps, no-reclaim breakout, identical paths differing only by close-back timing, wick-only reclaim rejected (D-07, A8, SMC-03)"
    requirement: "SMC-03"
    verification:
      - kind: unit
        ref: tests/unit/test_sweeps.py#test_immediate_reclaim_swept_on_pierce_bar
        status: pass
      - kind: unit
        ref: tests/unit/test_sweeps.py#test_next_bar_reclaim_swept
        status: pass
      - kind: unit
        ref: tests/unit/test_sweeps.py#test_no_reclaim_breakout
        status: pass
      - kind: unit
        ref: tests/unit/test_sweeps.py#test_identical_pierce_paths_differ_only_by_close_back_timing
        status: pass
      - kind: unit
        ref: tests/unit/test_sweeps.py#test_wick_reclaim_alone_does_not_count
        status: pass
    human_judgment: false
  - id: D5
    description: "One-and-done terminal lifecycles: swept level spawns fresh pool_id that can itself be swept; payload completeness; single event per resolved pool (D-08, SMC-05 pool half)"
    requirement: "SMC-05"
    verification:
      - kind: unit
        ref: tests/unit/test_sweeps.py#test_spent_level_never_re_swept_new_cluster_new_pool
        status: pass
      - kind: unit
        ref: tests/unit/test_sweeps.py#test_event_payload_completeness_and_single_event_per_pool
        status: pass
      - kind: unit
        ref: tests/unit/test_sweeps.py#test_empty_frame_contract
        status: pass
    human_judgment: false

duration: 30 min
completed: 2026-08-31
---

# Phase 2 Plan 02: Liquidity Pools + Sweep Classification Summary

Equal-high/low liquidity pools with as-of ATR-relative tolerance and the sweep-vs-breakout state machine — the core SMC signal input, proven lookahead-safe by tier-3 repaint and standalone-vs-in-frame tests.

**Duration:** ~30 min · **Tasks:** 3/3 · **Files:** 3 created · **Commits:** bf5a809, 0caee1f, 86e769f

## Accomplishments

- `detect_pools` implementing D-05..D-08: as-of 0.1×ATR(14) clustering (inclusive), 2-touch activation with frozen mean level, pinned 2-bar inclusive sweep window (pierce bar's close + next bar's close), one-and-done terminals, deterministic IDs, ATR-warmup skip, forming-candidate supersession (A5), V5 guards, empty-frame contracts
- 11-test SMC-02 suite including tier-3 repaint immutability (1-by-1 + chunked) and the standalone-vs-in-frame warning-sign test with an extreme ATR-changing tail (Pitfall 3)
- 8-test SMC-03 suite locking the classification: identical pierce paths differ solely by close-back timing; wick-only reclaim rejected; spent levels spawn fresh pool_ids
- Output dtype pinning (StringDtype / datetime64[us]) — the tier-3 tests caught pandas' value-dependent datetime unit inference

## Tasks

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | pools.py — cluster-then-activate machine + sweep/breakout classification | bf5a809 | src/ai_trading/detectors/pools.py |
| 2 | test_pools.py — clustering, activation, warmup, contracts + tier-3 repaint | 0caee1f | tests/unit/test_pools.py (+ pools.py dtype pinning) |
| 3 | test_sweeps.py — sweep vs breakout per the pinned window | 86e769f | tests/unit/test_sweeps.py |

## Verification Results

- `uv run pytest tests/unit/test_pools.py tests/unit/test_sweeps.py -q` → 19 passed
- `uv run pytest -q` → **135 passed, 3 deselected** (full suite incl. plans 02-01/02-02)
- `uv run ruff check .` → clean
- Vendor-import / floor_to_timeframe grep in detectors → 0 matches
- `git diff --exit-code tests/conftest.py tests/unit/_detector_fixtures.py` → clean (shared fixtures untouched)

## Deviations from Plan

**[Rule 1 - Bug] Output frame dtype instability under pandas 3** — Found during: Task 2 (tier-3 repaint) | Issue: pandas infers datetime unit ([s]/[us]) and string dtype from frame VALUES, so prefix vs full-frame pool frames differed in column dtypes — check_exact comparisons failed on attributes, not values | Fix: pin output dtypes explicitly (StringDtype for string columns, datetime64[us] for stamps) in detect_pools output assembly | Files modified: src/ai_trading/detectors/pools.py | Verification: tier-3 repaint green for every prefix | Commit: 0caee1f

**[Design pin] Pierce semantics vs the plan's boundary example** — Found during: Task 2 | Issue: the plan's boundary bullet ("two swings differing by exactly the tolerance cluster together") is unsatisfiable with a RISING second touch — its own extreme bar pierces the forming candidate and supersedes it (A5, correct per plan behavior bullet 4) | Resolution: strict point-in-time pierce semantics with no exemptions; the boundary fixture builds the second touch BELOW the first (rising-touch supersession covered by its own named test) | Verification: both behaviors proven by named tests | Commit: 0caee1f

**Total deviations:** 1 auto-fixed + 1 design pin (behavior-block precedence). **Impact:** none on contract — both strengthen determinism and point-in-time safety.

## Decisions

See `key-decisions` frontmatter: pierce semantics (no exemptions, A5 supersession), forming-candidate visibility, frame-end window contract, dtype pinning, ulp-inside boundary construction.

## Issues Encountered

None — test-first surfaced the dtype defect and the boundary/pierce interaction, both resolved immediately.

## Self-Check: PASSED
