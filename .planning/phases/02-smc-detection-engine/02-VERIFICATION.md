---
phase: 02-smc-detection-engine
verified: 2026-08-31T18:10:44Z
status: passed
score: 30/30 must-haves verified (8+8+7+7 truths across plans 02-01..02-04)
behavior_unverified: 0
overrides_applied: 0
re_verification: none
gaps: []
deferred:
  - truth: "Live broker-offset DST re-validation against the real MT5 terminal (synthetic +3→+2 continuity is unit-tested; live-terminal confirmation is not possible in unit tests)"
    addressed_in: "Phase 3"
    evidence: "02-CONTEXT.md line 98: 'DST caveat from Phase 1 carries forward: broker offset is +3 during US summer time, +2 after it ends — the H4 anchor shifts with it' — recorded carried-forward obligation, not a Phase 2 gap"
---

# Phase 2: SMC Detection Engine — Verification Report

**Phase Goal:** Pure, point-in-time SMC detectors producing liquidity pools, sweep events, and premium/discount zones with lifecycle state across MTF context
**Verified:** 2026-08-31T18:10:44Z
**Status:** passed
**Re-verification:** No — initial verification

All evidence below was **independently re-run in this verifier's own process** — SUMMARY.md claims were not trusted; every command result and every source-level claim was re-derived from the codebase.

## Goal Achievement

### Command Evidence (re-run by verifier)

| # | Check | Command | Result | Expected | Status |
|---|-------|---------|--------|----------|--------|
| 1 | Full suite | `uv run pytest -q` | **174 passed, 3 deselected** (9.00s) | 174 passed, 3 deselected | ✓ PASS |
| 2 | Full suite incl. MT5-marked | `uv run pytest -q -m "unit or mt5"` | **177 passed** (9.62s) | 177 passed | ✓ PASS |
| 3 | Lint | `uv run ruff check .` | All checks passed! | clean | ✓ PASS |
| 4 | Vendor purity (imports) | grep `import MetaTrader5` / `from MetaTrader5` / `floor_to_timeframe` under `src/ai_trading/detectors/` | 0 matches (only 2 docstring mentions of "MetaTrader5" in prose) | 0 matches | ✓ PASS |
| 5 | Shared fixtures untouched | `git diff --exit-code tests/conftest.py tests/unit/_detector_fixtures.py` | clean | no diff | ✓ PASS |
| 6 | Fixture commit history | `git log -- tests/conftest.py tests/unit/_detector_fixtures.py` | conftest.py: only Phase-1 commits (f685cd6, d6d4e7c); _detector_fixtures.py: only a90aabd (02-01 creation) | untouched by 02-02..02-04 | ✓ PASS |
| 7 | Committed-state greenness | full suite in throwaway `git worktree` at HEAD 96a943a | **174 passed, 3 deselected** | green at HEAD, not only in dirty working tree | ✓ PASS |

The 3 deselected tests are the `mt5`-marked integration tests (pyproject `addopts = '-m "not mt5"'`) — expected by design.

### Behavioral Spot-Checks (named tests, run individually by verifier)

| Behavior | Command | Result | Status |
| -------- | ------- | ------ | ------ |
| SC1 / T1 — appending bars never alters confirmed swings | `pytest tests/unit/test_repaint.py::test_repaint_t1_appending_bars_never_alters_confirmed_swings` | PASSED | ✓ PASS |
| SC1 / T2 — zigzag rows before tail immutable | `pytest tests/unit/test_repaint.py::test_repaint_t2_zigzag_rows_before_tail_immutable` | PASSED | ✓ PASS |
| SC4 / D-15 — HTF confirmation at exactly T excluded | `pytest tests/unit/test_mtf_join.py::test_htf_confirmation_at_exact_bar_time_excluded` | PASSED | ✓ PASS |
| SC4 — full-frame strictly-before invariant | `pytest tests/unit/test_mtf_join.py::test_joined_rows_strictly_before_invariant` | PASSED | ✓ PASS |
| SC5 — vendor purity asserted over detector sources | `pytest tests/unit/test_detector_integration.py::test_no_vendor_imports_in_detector_sources` | PASSED | ✓ PASS |
| SC5 — chain deterministic on rerun | `pytest tests/unit/test_detector_integration.py::test_chain_deterministic_on_rerun` | PASSED | ✓ PASS |

### Test Inventory (enumerated, matches summary claims exactly)

| Module | Tests | Claimed | Status |
| ------ | ----- | ------- | ------ |
| tests/unit/test_swings.py | 12 | 12 | ✓ |
| tests/unit/test_repaint.py | 5 | 5 | ✓ |
| tests/unit/test_pools.py | 11 | 11 | ✓ |
| tests/unit/test_sweeps.py | 8 | 8 | ✓ |
| tests/unit/test_zones.py | 9 | 9 | ✓ |
| tests/unit/test_lifecycle.py | 9 | 9 | ✓ |
| tests/unit/test_mtf_join.py | 11 | 11 | ✓ |
| tests/unit/test_detector_integration.py | 10 | 10 | ✓ |

75 phase-2 tests + 99 phase-1 tests = 174. Arithmetic consistent with the suite result.

### Observable Truths (must_haves roll-up — 30/30 verified)

Source-level verification was performed by reading every detector module against its plan's must_haves; behavioral backing comes from the green full suite plus the named spot-checks above.

| Plan | Truth (condensed) | Source Evidence | Test Evidence | Status |
|------|-------------------|-----------------|---------------|--------|
| 02-01 | Swing emitted only on close of 2nd right bar; `confirmed_at = time_utc.shift(-2) + TIMEFRAME_MINUTES[tf]`; truncation hides unconfirmed swings | swings.py L87–89, L116–126 | test_swing_confirmed_only_at_second_right_bar_close, test_truncated_frame_hides_unconfirmed_swing, test_last_two_bars_never_emit | ✓ VERIFIED |
| 02-01 | Strict comparisons only (equal neighbors never swing); NaN tail disqualifies last 2 rows | swings.py L116–120 (all four `>`/`<`, no `>=`/`==`), shift(-2) NaN tail | test_equal_neighbor_price_disqualifies_swing | ✓ VERIFIED |
| 02-01 | Exact 6-column swing schema; empty/short input returns schema-correct empty frame | swings.py L30–37, L42–53, L112–113 | test_output_schema_exact_columns, test_empty_frame_returns_full_schema, test_short_frame_below_fractal_width_no_swings | ✓ VERIFIED |
| 02-01 | Zigzag alternates: append on opposite side, tail-replace on more-extreme same side, absorb less-extreme | zigzag.py L99–123 | test_repaint_t2_tail_replacement_is_legitimate, test_repaint_t2_zigzag_rows_before_tail_immutable | ✓ VERIFIED |
| 02-01 | Repaint T1: 1-by-1 + chunked appends, prefix == visible subset (check_exact) | fixtures assert_point_in_time_prefix_equality (L96–109) | test_repaint_t1_appending_bars_never_alters_confirmed_swings, test_repaint_t1_chunked_appends | ✓ VERIFIED |
| 02-01 | Repaint T2: pre-tail zigzag rows immutable | zigzag.py replace-tail-only (L104–111) | test_repaint_t2_zigzag_rows_before_tail_immutable | ✓ VERIFIED |
| 02-01 | Same-bar dual swing emits high then low deterministically | swings.py L126 sort `["bar_time","side"]` | test_dual_swing_same_bar_high_then_low | ✓ VERIFIED |
| 02-01 | wilders_atr = ewm(alpha=1/period, adjust=False, min_periods=period), NaN warmup, guards | atr.py L41–50, L31–40 | test_wilders_atr_warmup_nan_and_hand_computed_values | ✓ VERIFIED |
| 02-02 | As-of tolerance (0.1×ATR at each joining swing's confirmation bar, inclusive), never full-frame stats | pools.py L206–218 (`atr.iloc[i]`, `<= tolerance`) | test_equal_highs_cluster_within_tolerance, test_tolerance_boundary_inclusive_exclusive, test_pools_standalone_match_in_frame | ✓ VERIFIED |
| 02-02 | Level = mean of two activating touches, frozen; later touches increment count only | pools.py L218–228 | test_two_touch_activation_timing_and_level_mean, test_third_touch_increments_count_not_level | ✓ VERIFIED |
| 02-02 | 2 clustered touches activate; pierce-while-forming is dead, never activated (A5) | pools.py L220–227, L277–282 | test_pierce_while_forming_supersedes_candidate | ✓ VERIFIED |
| 02-02 | Sweep rule: wick pierce + close-back in 2-bar inclusive window; expiry → breakout/broken | pools.py L257–275 (pierce-bar close, next-bar close via `pierced_pending`) | test_immediate_reclaim_swept_on_pierce_bar, test_next_bar_reclaim_swept, test_no_reclaim_breakout | ✓ VERIFIED |
| 02-02 | One-and-done terminal states; post-resolution swings start new candidates (fresh pool_ids) | pools.py L252–254 (`open=False`), L229–243 | test_spent_level_never_re_swept_new_cluster_new_pool | ✓ VERIFIED |
| 02-02 | ATR-warmup skip; cluster-confirm ordering before event checks (Pitfall 6/7) | pools.py L206–211 (warmup `continue`), step order 1→2→3 | test_atr_warmup_produces_no_pools | ✓ VERIFIED |
| 02-02 | Pool tier-3 repaint: resolved pools immutable under appends; prefix == visible subset | pools.py dtype-pinned output (L324–339) | test_resolved_pools_immutable_under_appended_bars | ✓ VERIFIED |
| 02-02 | Identical pierce paths differ only by close-back timing | — | test_identical_pierce_paths_differ_only_by_close_back_timing, test_wick_reclaim_alone_does_not_count | ✓ VERIFIED |
| 02-03 | One zone per consecutive zigzag pair at completing swing's confirmation; range/equilibrium/leg_direction per D-09 | zones.py L127–151 | test_up_leg_zone_range_and_equilibrium, test_down_leg_zone_mirror, test_created_at_is_completing_swing_confirmation | ✓ VERIFIED |
| 02-03 | No zone before first completed leg | zones.py L127 (pairs require 2 points) | test_incomplete_leg_yields_no_zone | ✓ VERIFIED |
| 02-03 | Wick-interior mitigation (no close required); committed-close invalidation only; wick pokes don't invalidate | zones.py L166–175 | test_wick_touch_mitigates_without_close, test_wick_poke_beyond_does_not_invalidate, test_close_beyond_invalidates_from_unmitigated | ✓ VERIFIED |
| 02-03 | Monotone lifecycle; mitigation checked before invalidation; first-event timestamps never overwritten | zones.py L166–175 (state-gated writes) | test_same_bar_double_stamp_order, test_lifecycle_monotone_first_event_timestamps, test_zone_frozen_after_invalidation | ✓ VERIFIED |
| 02-03 | All zones tracked concurrently, never deleted | zones.py L137–151, L162 | test_two_legs_two_coexisting_zones | ✓ VERIFIED |
| 02-03 | Advancement starts at bar opening at created_at; creating confirmation bar never advances its own zone | zones.py L163 (`t < created_at` skip) | test_zone_not_advanced_before_creation_bar | ✓ VERIFIED |
| 02-03 | Zone tier-3 repaint: completed-leg zones immutable under appends | zones.py float-dtype-pinned output (L203–212) | test_completed_leg_zones_immutable_under_appended_bars | ✓ VERIFIED |
| 02-04 | Strictly-before join: merge_asof(direction='backward', allow_exact_matches=False, by='symbol') on created_at; exact-T invisible | mtf.py L152–160 | test_htf_confirmation_at_exact_bar_time_excluded, test_joined_rows_strictly_before_invariant | ✓ VERIFIED |
| 02-04 | Every joined row satisfies created_at < time_utc (full-payload invariant) | mtf.py join construction | test_joined_rows_strictly_before_invariant, test_payload_strictly_before_invariant_full_chain | ✓ VERIFIED |
| 02-04 | Bias mapping: close>eq→bearish, close<eq→bullish, exact→neutral; no live range→NA/NaN/empty | mtf.py L167–178, L173–184 | test_bias_premium_discount_neutral_mapping, test_payload_field_completeness_and_pre_confirmation_na | ✓ VERIFIED |
| 02-04 | Lean 14-column payload per HTF (H1 AND H4) incl. signed ATR distance + live containment IDs sorted by (created_at, zone_id); no pool/sweep fields | mtf.py L41–56, L186–200 | test_zone_ids_containment_live_only_sorted, test_distance_to_equilibrium_signed_atr_units, test_output_schemas_pinned_including_empty_frames | ✓ VERIFIED |
| 02-04 | Invalidated-latest → NA/NaN/empty until next leg (liveness: invalidated_at NA or ≥ T) | mtf.py L115–118, L169–170 | test_invalidation_boundary_and_na_payload | ✓ VERIFIED |
| 02-04 | DST continuity: joins key on stored time_utc; no context jump at +3→+2 flip | mtf.py docstring L28–30; no grid re-flooring (grep clean) | test_dst_offset_flip_h4_anchor_continuity | ✓ VERIFIED |
| 02-04 | Full chain swings→zigzag→pools→zones→MTF: consistent payloads, purity, determinism, schema locks | mtf.py + all modules zero I/O / zero vendor imports (grep + integration file-content assertion) | test_full_chain_end_to_end_over_multi_tf_frames, test_chain_deterministic_on_rerun, test_all_inputs_unmutated_through_chain, test_no_vendor_imports_in_detector_sources | ✓ VERIFIED |

**Score:** 30/30 truths verified (0 present-but-behavior-unverified)

## Success Criteria Coverage (ROADMAP SC1–SC5)

| SC | Criterion (condensed) | Evidence | Status |
|----|----------------------|----------|--------|
| SC1 | Swing detection confirmation-shifted; repaint unit tests prove no output changes when future bars are appended | test_repaint.py T1 (1-by-1 + chunked, check_exact prefix equality) + T2 (zigzag tail-only rule) + structure-shift label stability; all pass in verifier's run | ✓ SATISFIED |
| SC2 | Equal highs/lows cluster into pools with ATR-relative tolerance; sweeps (take-out + reclaim) distinguishable from pure breakouts | pools.py as-of 0.1×ATR(14) clustering (D-05/D-06) + sweep-vs-breakout state machine (D-07/A8); 11 pool tests + 8 sweep tests | ✓ SATISFIED |
| SC3 | Premium/discount zones from confirmed swing ranges with lifecycle state (unmitigated→mitigated→invalidated) updated bar-by-bar | zones.py per-leg derivation (D-09) + monotone state machine (D-10/D-11/D-12); 9 zone tests + 9 lifecycle tests | ✓ SATISFIED |
| SC4 | H1/H4 context joins to each M15 decision bar point-in-time (no latest-row lookahead) | mtf.py merge_asof backward + allow_exact_matches=False on confirmation timestamps (D-15); exact-T exclusion test + full-frame strictly-before invariant test | ✓ SATISFIED |
| SC5 | All detectors are pure DataFrame→DataFrame functions with pytest coverage | 6 modules, all `DataFrame/Series → DataFrame/Series`; zero file I/O (grep clean), zero vendor imports (grep + test_no_vendor_imports_in_detector_sources reads every detector file); 75 phase-2 tests green; determinism proven by byte-identical rerun test | ✓ SATISFIED |

## Requirements Coverage (SMC-01..SMC-06)

| Requirement | Source Plan(s) | Description (condensed) | Status | Evidence |
| ----------- | -------------- | ------------------------ | ------ | -------- |
| SMC-01 | 02-01 | Confirmation-shifted swing detection (non-repainting) | ✓ SATISFIED | detect_swings (swings.py) with D-01/D-02/D-03 semantics; 12-test suite + 5-test repaint suite, all green |
| SMC-02 | 02-02 | ATR-relative clustering of equal highs/lows into pools | ✓ SATISFIED | detect_pools as-of 0.1×ATR(14) tolerance (D-05/D-06); 11-test suite incl. boundary + tier-3 repaint, all green |
| SMC-03 | 02-02 | Sweep events (take-out + reclaim) vs pure breakouts | ✓ SATISFIED | Pinned 2-bar inclusive reclaim window (D-07/A8); 8-test classification suite, all green |
| SMC-04 | 02-03 | Premium/discount zones from confirmed swing ranges, configurable range-selection | ✓ SATISFIED | derive_zones per-leg ranges with equilibrium (D-09); 9-test suite, all green |
| SMC-05 | 02-02 + 02-03 | Pool and zone lifecycle state, updated bar-by-bar | ✓ SATISFIED | Pool: forming→active→swept/broken one-and-done (D-08); Zone: monotone unmitigated→mitigated→invalidated w/ first-event stamps; 9-test lifecycle suite + sweep lifecycle tests, all green |
| SMC-06 | 02-04 | H1/H4 context joined point-in-time as of each M15 decision bar | ✓ SATISFIED | htf_context strictly-before as-of join (D-15); 11-test join suite + 10-test integration suite, all green |

**Orphaned requirements:** none — REQUIREMENTS.md maps exactly SMC-01..SMC-06 to Phase 2, and the union of plan `requirements` fields is exactly {SMC-01, SMC-02, SMC-03, SMC-04, SMC-05, SMC-06}.

**Locked decisions:** all 15 (D-01..D-15) verified present in 02-CONTEXT.md and implemented per their semantics in the corresponding modules (docstrings cite the D-decisions; behavior verified against them above).

## Key Link Verification (wiring)

| From | To | Via | Status | Details |
| ---- | -- | --- | ------ | ------- |
| swings.py | normalize.py | `from ai_trading.normalize import TIMEFRAME_MINUTES` (confirmation stamping, no grid re-flooring) | ✓ WIRED | L28; grep confirms no re-flooring anywhere in detectors |
| zigzag.py | swings output | consumes swings sorted by (confirmed_at, bar_time, side) — never raw bars | ✓ WIRED | zigzag.py L81–83 |
| pools.py | atr.py + swings output | `from ai_trading.detectors.atr import wilders_atr`; consumes raw swings (NOT zigzag) | ✓ WIRED | pools.py L47, L189–194; zigzag never imported |
| zones.py | zigzag output | derive_zones(zigzag, bars) keyed on confirmation timestamps | ✓ WIRED | zones.py L180, L122–124 |
| mtf.py | zones output + atr.py | `from ai_trading.detectors.atr import wilders_atr`; `from ai_trading.detectors.zones import ZONE_COLUMNS`; merge_asof on created_at | ✓ WIRED | mtf.py L38–39, L152–160 |
| All detectors | SC5 purity | zero adapter-tier imports, zero file I/O, inputs never mutated | ✓ WIRED | grep clean (imports + I/O patterns); test_input_frames_not_mutated × 4 modules + test_all_inputs_unmutated_through_chain |

## Deviations Review (all 6 documented — all acceptable)

| Plan | Deviation | Verifier Assessment |
| ---- | --------- | ------------------- |
| 02-01 | Swing output string dtype canonicalized (`astype("str")`) — pandas 3 concat unifies all-string object columns to StringDtype only when both sides contribute rows, making prefix-vs-full dtype paths diverge | ✓ Acceptable — bug found by the repaint suite itself; the fix strengthens the T1 guarantee.dtype is now path-independent |
| 02-02 | Output dtype pinning (StringDtype / datetime64[us]) — pandas infers datetime units from values, making tier-3 comparisons dtype-unstable | ✓ Acceptable — same class as above; caught by the tier-3 tests, strengthens determinism |
| 02-02 | Pierce-semantics design pin: plan's "exactly-equal-tolerance swings cluster" boundary bullet is unsatisfiable with a rising second touch (its own extreme bar pierces the forming candidate per A5) | ✓ Acceptable — behavior-block precedence correctly applied; both behaviors locked by named tests (test_tolerance_boundary_inclusive_exclusive builds the boundary from below; test_pierce_while_forming_supersedes_candidate covers supersession) |
| 02-03 | Float-column dtype pinning (empty-frame object-dtype drift) + strict tier-3 visibility horizon (created_at < prefix close, applied to both comparison sides) | ✓ Acceptable — the strict horizon is the faithful point-in-time visibility (at created_at == prefix close the lifecycle stamps are undetermined); symmetric filtering is sound |
| 02-04 | Detector validators moved from global to per-symbol time_utc monotonic+unique checks (swings/pools/zones/mtf) — global checks reject valid combined multi-symbol frames | ✓ Acceptable — single-symbol semantics unchanged; no prior test asserted the global form; verified in source (per-symbol groupby guards in all four validators); enables the multi-symbol integration world and by='symbol' joins |
| 02-04 | Join tests authored after Task 1 implementation (both tasks marked tdd) | ✓ Acceptable — fixture design depended on verified module contracts; corrected fixtures passed first run; no contract was weakened |

## Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
| ---- | ---- | ------- | -------- | ------ |
| src/ai_trading/detectors/zigzag.py | 48–51 | Uncommitted working-tree edit: empty-frame datetime64[ns]→[us] dtype alignment | ℹ️ Info | Cosmetic; no test pins empty-zigzag datetime dtype (schema test asserts columns/length only); committed HEAD verified green via throwaway worktree (174 passed). Should be committed with the phase artifacts |
| src/ai_trading/detectors/zigzag.py | 85–97 | Per-symbol processing uses a tail-symbol guard — correct for symbol-block-concatenated frames (the pinned integration contract) but not for time-interleaved multi-symbol swings | ℹ️ Info | No test covers interleaved input; natural usage (per-symbol frames, Phase-3 per-symbol replay, block-concatenated integration frames) is unaffected. Consider a groupby-symbol refactor if interleaved input ever becomes a supported contract |

No TBD/FIXME/XXX/HACK/PLACEHOLDER/TODO markers anywhere in the detector sources. No file I/O. No stub returns. No hardcoded-empty data flowing to output (empty-frame paths are the pinned Pitfall-10 contracts, exercised by tests).

## Human Verification Required

None. Every must-have is unit-testable and was tested in this verifier's own process. The live broker-offset DST re-validation against a real MT5 terminal cannot be exercised in unit tests and is already a **recorded carried-forward obligation** (02-CONTEXT.md: "DST caveat from Phase 1 carries forward"), deferred to Phase 3+ — listed under Deferred Items, not a Phase 2 gap.

## Deferred Items

| # | Item | Addressed In | Evidence |
|---|------|-------------|----------|
| 1 | Live broker-offset DST re-validation on the real terminal (synthetic +3→+2 continuity is unit-locked; live confirmation is out of unit-test scope) | Phase 3 | 02-CONTEXT.md line 98: "DST caveat from Phase 1 carries forward: broker offset is +3 during US summer time, +2 after it ends — the H4 anchor shifts with it" |

## Gaps Summary

No gaps. All six requirements (SMC-01..SMC-06), all five success criteria (SC1–SC5), and all 30 plan must-have truths are verified with concrete, independently re-run evidence: the full suite is green in this process (174 passed / 3 deselected; 177 with mt5-marked), ruff is clean, vendor purity and fixture immutability are grep/commit-history confirmed, the committed HEAD state is itself green, and the phase's two security-grade properties — SC1 repaint immutability and SC4/D-15 strictly-before MTF joins — are behaviorally proven by named tests that were re-run individually. Documented deviations (dtype pinning ×3, pierce-semantics pin, strict repaint horizon, per-symbol validators) were each reviewed against source and tests and all strengthen rather than weaken the contracts. Two info-level housekeeping notes (an uncommitted cosmetic dtype edit in zigzag.py's empty-frame path; interleaved multi-symbol input unsupported by the tail-symbol guard) require no action for this phase and do not affect the goal.

---

_Verified: 2026-08-31T18:10:44Z_
_Verifier: the agent (gsd-verifier)_
