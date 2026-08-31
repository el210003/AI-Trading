---
phase: 02-smc-detection-engine
plan: 03
subsystem: detectors
tags: [smc, premium-discount-zones, lifecycle, state-machine, point-in-time, pytest]

requires:
  - "Plan 02-01: build_zigzag output (symbol/timeframe carried through, confirmed_at per point)"
provides:
  - "ai_trading.detectors.zones.derive_zones — one zone per consecutive zigzag pair (D-09), wick-interior mitigation (D-10/A7), committed-close invalidation (D-11), concurrent full-history tracking (D-12)"
  - "Pinned zones schema: (zone_id, symbol, timeframe, leg_direction, range_high, range_low, equilibrium, state, created_at, mitigated_at, invalidated_at); deterministic IDs {SYMBOL}-{TF}-Z{n:04d} in creation order"
  - "created_at = completing swing's confirmed_at — the confirmation-time axis plan 02-04's MTF join keys on"
  - "tests/unit/test_zones.py — 9-test SMC-04 suite incl. zone tier-3 repaint"
  - "tests/unit/test_lifecycle.py — 9-test SMC-05 zone lifecycle suite"
affects: [02-04-mtf-join, phase-3-backtester, phase-4-ml-features, phase-6-evidence-traces]

tech-stack:
  added: []
  patterns:
    - "per-bar per-zone advancement: mitigation check first, then invalidation (Pitfall 6 same-bar double-stamp order)"
    - "lifecycle advancement gate: bars with time_utc >= created_at only — zones never born mitigated"
    - "float-column dtype pinning (empty-frame object-dtype drift caught by tier-3 repaint comparisons)"
    - "equal-high pair sculpting to keep engineered bars zigzag-stable (D-02: equal prices never form swings)"

key-files:
  created:
    - src/ai_trading/detectors/zones.py
    - tests/unit/test_zones.py
    - tests/unit/test_lifecycle.py
  modified: []

key-decisions:
  - "Zones derive from EVERY consecutive zigzag pair (including the current tail pair) at p2's confirmation — per the plan action verbatim; the tail pair's range may extend with same-side replacements (two-tier logic: completed-leg zones are strictly immutable, the tail leg's zone is legitimately extensible)"
  - "Tier-3 repaint visibility horizon is created_at STRICTLY before the prefix's last close: at created_at == prefix close the first advancing bar lies beyond the prefix, so lifecycle stamps are not yet determined — both comparison sides filtered with the same strict horizon"
  - "Mitigation operationalized as wick-interior intersection (bar low < range_high AND bar high > range_low) — symmetric for both approach directions (A7)"
  - "Engineered lifecycle bars use equal-high pairs (D-02) so no test path replaces Z0001's completing zigzag point; low sculpts may append new legs (new zones) — assertions target Z0001 by id"

requirements-completed: [SMC-04, SMC-05]

coverage:
  - id: D1
    description: "Per-leg zone derivation: up/down leg ranges at sculpted extremes, exact-midpoint equilibrium, created_at = completing swing's confirmation, sequential IDs, sorted output (D-09, SMC-04)"
    requirement: "SMC-04"
    verification:
      - kind: unit
        ref: tests/unit/test_zones.py#test_up_leg_zone_range_and_equilibrium
        status: pass
      - kind: unit
        ref: tests/unit/test_zones.py#test_down_leg_zone_mirror
        status: pass
      - kind: unit
        ref: tests/unit/test_zones.py#test_created_at_is_completing_swing_confirmation
        status: pass
      - kind: unit
        ref: tests/unit/test_zones.py#test_zone_ids_sequential_and_sorted
        status: pass
    human_judgment: false
  - id: D2
    description: "Leg-completion gate, concurrent full history, empty contracts, input non-mutation (D-09/D-12, Pitfall 10, SC5)"
    requirement: "SMC-04"
    verification:
      - kind: unit
        ref: tests/unit/test_zones.py#test_incomplete_leg_yields_no_zone
        status: pass
      - kind: unit
        ref: tests/unit/test_zones.py#test_two_legs_two_coexisting_zones
        status: pass
      - kind: unit
        ref: tests/unit/test_zones.py#test_empty_frame_contracts
        status: pass
      - kind: unit
        ref: tests/unit/test_zones.py#test_input_frames_not_mutated
        status: pass
    human_judgment: false
  - id: D3
    description: "Zone tier-3 repaint: completed-leg zones immutable under 1-by-1 and chunked appends (strict visibility horizon)"
    requirement: "SMC-04"
    verification:
      - kind: unit
        ref: tests/unit/test_zones.py#test_completed_leg_zones_immutable_under_appended_bars
        status: pass
    human_judgment: false
  - id: D4
    description: "Mitigation semantics: wick touch without close; wick-poke-beyond mitigates but never invalidates (D-10, A7, D-11)"
    requirement: "SMC-05"
    verification:
      - kind: unit
        ref: tests/unit/test_lifecycle.py#test_wick_touch_mitigates_without_close
        status: pass
      - kind: unit
        ref: tests/unit/test_lifecycle.py#test_wick_poke_beyond_does_not_invalidate
        status: pass
    human_judgment: false
  - id: D5
    description: "Invalidation semantics: committed close from unmitigated (direct) and from mitigated (preserving mitigated_at); same-bar double-stamp order mitigation-then-invalidation (D-11, Pitfall 6)"
    requirement: "SMC-05"
    verification:
      - kind: unit
        ref: tests/unit/test_lifecycle.py#test_close_beyond_invalidates_from_unmitigated
        status: pass
      - kind: unit
        ref: tests/unit/test_lifecycle.py#test_close_beyond_invalidates_from_mitigated
        status: pass
      - kind: unit
        ref: tests/unit/test_lifecycle.py#test_same_bar_double_stamp_order
        status: pass
    human_judgment: false
  - id: D6
    description: "Monotone first-event timestamps, creation-bar exclusion pin, post-invalidation freeze, empty contracts (D-12, planner pin, Pitfall 10)"
    requirement: "SMC-05"
    verification:
      - kind: unit
        ref: tests/unit/test_lifecycle.py#test_lifecycle_monotone_first_event_timestamps
        status: pass
      - kind: unit
        ref: tests/unit/test_lifecycle.py#test_zone_not_advanced_before_creation_bar
        status: pass
      - kind: unit
        ref: tests/unit/test_lifecycle.py#test_zone_frozen_after_invalidation
        status: pass
      - kind: unit
        ref: tests/unit/test_lifecycle.py#test_empty_frame_contract
        status: pass
    human_judgment: false

duration: 30 min
completed: 2026-08-31
---

# Phase 2 Plan 03: Premium/Discount Zones + Lifecycle Summary

Per-leg premium/discount zones with equilibrium and confirmation-time creation, plus the monotone bar-by-bar lifecycle state machine — the HTF bias source for SMC-06 and the evidence backbone for Phases 4/6.

**Duration:** ~30 min · **Tasks:** 3/3 · **Files:** 3 created · **Commits:** 93ade8d, d8e69c8, 1d19e82, 122c195, f6ffe6f

## Accomplishments

- `derive_zones` implementing D-09..D-12: one zone per consecutive zigzag pair at the completing swing's confirmation, exact-midpoint equilibrium, wick-interior mitigation, committed-close invalidation, monotone first-event timestamps, concurrent full-history tracking, deterministic IDs, V5 guards, empty-frame contracts, dtype-pinned output
- 9-test SMC-04 suite: leg ranges/mirrors, creation timing, leg-completion gate, coexisting history, ID ordering, contracts, tier-3 repaint (1-by-1 + chunked)
- 9-test SMC-05 lifecycle suite: mitigation without close, wick-poke rejection, direct/mitigated-path invalidation, same-bar double-stamp order, monotonicity, creation-bar pin, post-invalidation freeze
- Fixture discipline documented: equal-high pair sculpting keeps engineered bars zigzag-stable

## Tasks

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | zones.py — per-leg derivation + monotone lifecycle machine | 93ade8d, d8e69c8 | src/ai_trading/detectors/zones.py |
| 2 | test_zones.py — ranges, equilibrium, creation timing + tier-3 repaint | 1d19e82, 122c195 | tests/unit/test_zones.py (+ float dtype pinning) |
| 3 | test_lifecycle.py — bar-by-bar monotone state transitions | f6ffe6f | tests/unit/test_lifecycle.py |

## Verification Results

- `uv run pytest tests/unit/test_zones.py tests/unit/test_lifecycle.py -q` → 18 passed
- `uv run pytest -q` → **153 passed, 3 deselected** (full suite incl. plans 02-01/02-02/02-03)
- `uv run ruff check .` → clean
- Vendor-import / floor_to_timeframe grep in detectors → 0 matches
- `git diff --exit-code tests/conftest.py tests/unit/_detector_fixtures.py` → clean

## Deviations from Plan

**[Rule 1 - Bug] Empty-frame float dtype drift** — Found during: Task 2 (tier-3 repaint) | Issue: zero-zone prefix frames left range/equilibrium columns as object dtype (pandas empty-DataFrame inference), breaking check_exact comparisons against non-empty frames | Fix: pin float columns (range_high/range_low/equilibrium → float64) in derive_zones output assembly | Files modified: src/ai_trading/detectors/zones.py | Verification: tier-3 repaint green for every prefix | Commit: 1d19e82

**[Design pin] Tier-3 visibility horizon** — Found during: Task 2 | Issue: the plan's "created_at <= prefix close" filter double-counts the boundary zone whose first advancing bar lies beyond the prefix (lifecycle stamps undetermined at that horizon) | Resolution: strict horizon (created_at < prefix close) applied identically to both comparison sides — the faithful point-in-time visibility; documented in the test docstring | Verification: repaint green for every prefix | Commit: 1d19e82

**Total deviations:** 1 auto-fixed + 1 design pin (behavior-block precedence). **Impact:** none on contract — both strengthen determinism and point-in-time safety.

## Decisions

See `key-decisions` frontmatter: tail-pair zone extensibility (two-tier logic), strict repaint horizon, wick-interior mitigation operationalization, equal-high fixture discipline.

## Issues Encountered

None — test-first surfaced the dtype drift and the horizon semantics, both resolved immediately.

## Self-Check: PASSED
