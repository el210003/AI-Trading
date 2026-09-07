---
phase: 02-smc-detection-engine
plan: 01
subsystem: detectors
tags: [smc, swings, zigzag, atr, repaint, point-in-time, pytest]

requires:
  - "Phase 1 bar foundation (normalize.COLUMNS/TIMEFRAME_MINUTES, make_bars fixture, unit/mt5 markers)"
provides:
  - "ai_trading.detectors.atr.wilders_atr — Wilder ATR via ewm(alpha=1/period, adjust=False, min_periods=period), NaN warmup, V5 entry guards"
  - "ai_trading.detectors.swings.detect_swings — strict 2/2 fractal swings, confirmation-shifted confirmed_at stamping (D-01..D-03), A9 dual-swing order, exact 6-column schema"
  - "ai_trading.detectors.zigzag.build_zigzag — alternating canonical structure with tail-only replacement (D-04), per-symbol processing, schema-pinned output"
  - "tests/unit/_detector_fixtures.py — flat_bars/sculpt_high/sculpt_low/swing_spec_bars/prefix_close_time/assert_point_in_time_prefix_equality (consumed read-only by 02-02..02-04)"
  - "tests/unit/test_swings.py — 12-test SMC-01 suite (strictness, confirmation stamping, schema, edge contracts, ATR convention)"
  - "tests/unit/test_repaint.py — 5-test SC1 two-tier repaint suite: T1 swing immutability (1-by-1 + chunked), T2 zigzag tail-only rule + replacement legitimacy, structure-shift label stability"
affects: [02-02-pools-sweeps, 02-03-zones-lifecycle, 02-04-mtf-join, phase-3-backtester]

tech-stack:
  added: []
  patterns:
    - "confirmation-shifted emission: confirmed_at = time_utc.shift(-2) + TF minutes; NaN tail disqualifies last 2 rows"
    - "two-tier repaint contract: raw swings strictly immutable; zigzag tail replaceable only by more-extreme same-side confirmation"
    - "dtype canonicalization on detector output (pandas 3 concat string unification is path-dependent)"
    - "TDD sculptor fixtures: equal-pair sculpts (D-02) used to build no-swing BOS/CHoCH crossings"

key-files:
  created:
    - src/ai_trading/detectors/__init__.py
    - src/ai_trading/detectors/atr.py
    - src/ai_trading/detectors/swings.py
    - src/ai_trading/detectors/zigzag.py
    - tests/unit/_detector_fixtures.py
    - tests/unit/test_swings.py
    - tests/unit/test_repaint.py
  modified: []

key-decisions:
  - "detect_swings emits swing-high and swing-low records separately then concats — supports A9 same-bar dual swings (high then low) that the single-mask research pattern would drop"
  - "swing/zigzag output string columns canonicalized with astype('str') — pandas 3 concat unifies all-string object columns to StringDtype only when both sides contribute, which made prefix vs full-frame dtype paths diverge (repaint T1 caught it)"
  - "zigzag carries symbol/timeframe through from swing records (planner-pinned schema) and processes symbols independently via a tail-symbol guard"
  - "structure-shift labeler lives in test_repaint.py only (BOS when break continues the current leg, CHoCH reserved by scope; labels compared as a leading slice so tail-leg labels may change per the contract)"
  - "labels stability fixture sculpts EQUAL high/low pairs (D-02) to carry BOS closes without creating replacement swings — completed-leg labels stay hand-derivable"

requirements-completed: [SMC-01]

coverage:
  - id: D1
    description: "wilders_atr: Wilder recursion via ewm(alpha=1/period, adjust=False, min_periods=period); warmup NaN; constant-TR hand-computed expectation; V5 guards on missing/non-finite columns (A4, Pitfall 7)"
    requirement: "SMC-01"
    verification:
      - kind: unit
        ref: tests/unit/test_swings.py#test_wilders_atr_warmup_nan_and_hand_computed_values
        status: pass
    human_judgment: false
  - id: D2
    description: "Strict 2/2 fractal swings: equal neighbors disqualify, single peak emits one record, confirmation stamp at 2nd right-bar close, truncation hides unconfirmed swings, last 2 rows never emit (D-01/D-02)"
    requirement: "SMC-01"
    verification:
      - kind: unit
        ref: tests/unit/test_swings.py#test_equal_neighbor_price_disqualifies_swing
        status: pass
      - kind: unit
        ref: tests/unit/test_swings.py#test_swing_confirmed_only_at_second_right_bar_close
        status: pass
      - kind: unit
        ref: tests/unit/test_swings.py#test_truncated_frame_hides_unconfirmed_swing
        status: pass
      - kind: unit
        ref: tests/unit/test_swings.py#test_last_two_bars_never_emit
        status: pass
      - kind: unit
        ref: tests/unit/test_swings.py#test_single_sculpted_peak_emits_one_swing_high
        status: pass
    human_judgment: false
  - id: D3
    description: "Output schema exactly (symbol, timeframe, bar_time, price, side, confirmed_at); empty/short-frame contracts; non-mutation; A9 dual-swing high-then-low (D-03, Pitfall 10, SC5)"
    requirement: "SMC-01"
    verification:
      - kind: unit
        ref: tests/unit/test_swings.py#test_output_schema_exact_columns
        status: pass
      - kind: unit
        ref: tests/unit/test_swings.py#test_empty_frame_returns_full_schema
        status: pass
      - kind: unit
        ref: tests/unit/test_swings.py#test_short_frame_below_fractal_width_no_swings
        status: pass
      - kind: unit
        ref: tests/unit/test_swings.py#test_input_frame_not_mutated
        status: pass
      - kind: unit
        ref: tests/unit/test_swings.py#test_dual_swing_same_bar_high_then_low
        status: pass
    human_judgment: false
  - id: D4
    description: "SC1 repaint T1: appending future bars 1-by-1 and in +5/+17 chunks never alters already-visible swing records (check_exact prefix equality for every prefix)"
    requirement: "SMC-01"
    verification:
      - kind: unit
        ref: tests/unit/test_repaint.py#test_repaint_t1_appending_bars_never_alters_confirmed_swings
        status: pass
      - kind: unit
        ref: tests/unit/test_repaint.py#test_repaint_t1_chunked_appends
        status: pass
    human_judgment: false
  - id: D5
    description: "SC1 repaint T2: zigzag rows before the tail immutable across prefixes; more-extreme same-side confirmation replaces the tail (replacement-legitimacy guard fails if disabled) (D-04)"
    requirement: "SMC-01"
    verification:
      - kind: unit
        ref: tests/unit/test_repaint.py#test_repaint_t2_zigzag_rows_before_tail_immutable
        status: pass
      - kind: unit
        ref: tests/unit/test_repaint.py#test_repaint_t2_tail_replacement_is_legitimate
        status: pass
    human_judgment: false
  - id: D6
    description: "Structure-shift (BOS/CHoCH) labels from completed legs stable across prefixes; helper confined to tests (never a src feature per locked scope)"
    requirement: "SMC-01"
    verification:
      - kind: unit
        ref: tests/unit/test_repaint.py#test_structure_shift_labels_stable_for_completed_legs
        status: pass
      - kind: other
        ref: "rg _structure_shifts src/ai_trading/detectors/ -> 0 matches"
        status: pass
    human_judgment: false

duration: 25 min
completed: 2026-08-31
---

# Phase 2 Plan 01: Swing Foundation + Repaint Suite Summary

Strict 2/2 fractal swings with confirmation-shifted stamping, alternating zigzag, and Wilder ATR — plus the SC1 two-tier repaint suite that locks point-in-time safety as the executable specification for plans 02-02..02-04.

**Duration:** ~25 min · **Tasks:** 3/3 · **Files:** 7 created · **Commits:** 308a498, a90aabd, 638da41

## Accomplishments

- Detector package `src/ai_trading/detectors/` (atr/swings/zigzag) implementing RESEARCH Patterns 1–3 with locked D-01..D-04 semantics, fail-fast V5 guards, empty/short-frame contracts, and copy-at-entry non-mutation — zero MetaTrader5 imports, zero file I/O, no `floor_to_timeframe` anywhere (Pitfall 8)
- 12-test SMC-01 unit suite locking strictness, confirmation stamping, schema, edge contracts, dual-swing order (A9), and the pinned ATR ewm convention (A4)
- 5-test SC1 repaint suite: T1 swing immutability (1-by-1 + chunked appends, check_exact prefix equality), T2 zigzag tail-only rule with a replacement-legitimacy guard, and completed-leg structure-shift label stability
- Shared sculptor fixtures (`_detector_fixtures.py`) for downstream plans — root conftest.py untouched (git-diff guarded)

## Tasks

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Detector package — Wilder ATR, strict 2/2 swings, alternating zigzag | 308a498 | src/ai_trading/detectors/{__init__,atr,swings,zigzag}.py |
| 2 | SMC-01 unit suite + sculptor fixture helpers | a90aabd | tests/unit/{_detector_fixtures,test_swings}.py |
| 3 | SC1 repaint suite — two-tier contract as executable spec | 638da41 | tests/unit/test_repaint.py (+ swings.py dtype fix) |

## Verification Results

- `uv run pytest tests/unit/test_swings.py -q` → 12 passed
- `uv run pytest tests/unit/test_repaint.py -q` → 5 passed
- `uv run pytest -q` → **116 passed, 3 deselected** (99 Phase 1 + 17 new, MT5-free)
- `uv run ruff check .` → clean
- `git diff --exit-code tests/conftest.py` → clean (root conftest untouched)
- Vendor-import grep in detectors → 0 matches; `_structure_shifts` in src → 0 matches

## Deviations from Plan

**[Rule 1 - Bug] Swing output dtype was path-dependent under pandas 3** — Found during: Task 3 (repaint T1) | Issue: pandas 3 `concat` unifies all-string object columns to StringDtype only when both side-frames contribute rows, so a prefix with swings on one side only produced `object` dtype where the full frame produced StringDtype — check_exact repaint comparisons failed on dtype, not values | Fix: canonicalize output string columns (`symbol`, `timeframe`, `side`) with `astype("str")` in `detect_swings` | Files modified: src/ai_trading/detectors/swings.py | Verification: repaint T1/T2 green for every prefix | Commit: 638da41

**Total deviations:** 1 auto-fixed. **Impact:** none on contract — the fix strengthens the repaint guarantee (output dtype is now path-independent).

## Decisions

See `key-decisions` frontmatter: dual-side record emission for A9 dual swings; output dtype canonicalization; zigzag symbol/timeframe pass-through; test-only structure-shift labeler; equal-pair BOS fixture sculpting.

## Issues Encountered

None — Task 2/3 TDD surfaced the dtype defect above, fixed immediately.

## Self-Check: PASSED
