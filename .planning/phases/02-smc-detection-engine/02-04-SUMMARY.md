---
phase: 02-smc-detection-engine
plan: 04
subsystem: detectors
tags: [smc, mtf-context, point-in-time, merge-asof, lookahead-bias, integration-tests, pytest]

requires:
  - "Plan 02-01: wilders_atr (M15 distance units) + swings/zigzag confirmation timestamps"
  - "Plan 02-03: derive_zones output frames (created_at/invalidated_at/range/equilibrium/zone_id) — the join's right side"
provides:
  - "ai_trading.detectors.mtf.htf_context(m15, htf_zones_h1, htf_zones_h4) — confirmation-time as-of join: merge_asof(direction='backward', allow_exact_matches=False, by='symbol') over zone created_at (D-15 — the #1 lookahead trap, now a tested invariant)"
  - "Pinned 14-column wide payload: (symbol, time_utc, bias_h1, htf_range_high_h1, htf_range_low_h1, htf_equilibrium_h1, htf_dist_to_eq_atr_h1, htf_zone_ids_h1, + H4 mirror); bias in {bullish, bearish, neutral}|NA; zone_ids object lists sorted by (created_at, zone_id)"
  - "Lean payload semantics (D-13/D-14): bias from M15 close vs latest live HTF equilibrium (above=bearish/premium, below=bullish/discount, exact=neutral), signed distance-to-equilibrium in M15 ATR(14) units, live-zone containment IDs; invalidated-latest -> NA/NaN/empty until the next leg"
  - "tests/unit/test_mtf_join.py — 11-test SMC-06 join suite (exact-T exclusion, invalidation boundary, DST anchor continuity, point-in-time stability)"
  - "tests/unit/test_detector_integration.py — 10-test SC5 suite: full-chain composition, determinism, purity (no vendor imports / no mutation), schema+sortedness locks, per-symbol join isolation"
  - "Multi-symbol input support across the whole detector chain: all validators enforce time_utc monotonic+unique PER SYMBOL (combined frames legitimately repeat timestamps across symbols)"
affects: [phase-3-backtester, phase-4-ml-features, phase-6-evidence-traces]

tech-stack:
  added: []
  patterns:
    - "confirmation-time as-of join: merge_asof backward + allow_exact_matches=False on zone created_at, never bar-open time, never latest-row lookup (Pitfall 1)"
    - "join-key dtype normalization at the merge boundary (make_bars emits datetime64[ns]/object; zone frames pin datetime64[us]/StringDtype)"
    - "per-symbol time-monotonicity guards — global checks cannot express combined multi-symbol frames"
    - "liveness predicate: zone live as of T iff invalidated_at is NA or >= T (an invalidation stamped at exactly T is not yet visible)"
    - "end-to-end chain tests run on combined multi-symbol frames with detectors receiving caller frames un-copied, proving non-mutation for real"

key-files:
  created:
    - src/ai_trading/detectors/mtf.py
    - tests/unit/test_mtf_join.py
    - tests/unit/test_detector_integration.py
  modified:
    - src/ai_trading/detectors/swings.py
    - src/ai_trading/detectors/pools.py
    - src/ai_trading/detectors/zones.py

key-decisions:
  - "Strictly-before visibility implemented literally per D-15: allow_exact_matches=False means an HTF zone confirmed at exactly T is invisible to the M15 bar at T and visible from the next bar — locked by test at the exact-match boundary"
  - "Planner pin kept: when the latest strictly-before zone is invalidated as of T, payload fields go NA/NaN/empty (no stale bias from a broken range); liveness uses invalidated_at >= T so an invalidation at exactly T remains visible"
  - "Integration-gap fix per the plan's implementations-move clause: swings/pools/zones/mtf validators now check time_utc strictly-increasing+unique per symbol instead of globally — global checks made by='symbol' joins on combined frames impossible; single-symbol semantics unchanged"
  - "HTF zone fixtures run the REAL chain (detect_swings -> build_zigzag -> derive_zones) on sculpted H1/H4 frames rather than hand-built stand-ins, so created_at/invalidated_at semantics in join tests are genuine"
  - "detect_pools returns (pools, events) — the integration suite locks both frames' schemas in populated and empty tiers"

requirements-completed: [SMC-06]

coverage:
  - "11 join tests: exact-T exclusion, full-frame strictly-before invariant (re-derived), premium/discount/neutral mapping incl. exact eq, payload completeness + pre-confirmation NA, live-only sorted containment, invalidation boundary (visible AT stamp, excluded after, NA gap until next leg), signed ATR distance, DST +3->+2 anchor continuity, appended-bars/zones stability, empty contracts, input non-mutation"
  - "10 integration tests: full-chain composition over 2-symbol 3-TF frames, no zone before leg completion, no payload before first HTF confirmation, full-chain strictly-before invariant, chain determinism (byte-identical rerun), all-inputs unmutated, schema pins incl. empty frames, sortedness invariants, vendor-import file-content assertion, per-symbol join isolation"
  - "Suite: 177 passed (174 unit + 3 mt5 deselected by default), 0 failed; ruff check . clean"

duration: "60 min"
completed: 2026-08-31
---

# Plan 02-04 Execution Summary: Multi-Timeframe Point-in-Time Context Join

## Accomplishments

- Implemented `src/ai_trading/detectors/mtf.py` — `htf_context(m15, htf_zones_h1, htf_zones_h4)` joins H1+H4 zone state onto every M15 decision bar with strictly-before confirmation visibility (D-15), bias from the close's position inside the latest live HTF range (D-13), and the lean per-HTF payload with ATR-scaled distance and live-zone containment IDs (D-14).
- Made the project's #1 lookahead trap a build-breaking invariant: `merge_asof(direction="backward", allow_exact_matches=False, by="symbol")` on confirmation timestamps, with the strictly-before rule re-derived row-by-row in tests over full frames.
- Delivered the end-to-end integration proof (ROADMAP SC5): the complete chain swings -> zigzag -> pools -> zones -> MTF is pure, deterministic (byte-identical reruns), schema-locked (populated and empty tiers), sorted, and lookahead-safe over synthetic multi-TF multi-symbol frames — the exact functions Phase 3's backtester replays (BT-01).
- Closed SMC-06 and thereby all six Phase 2 requirements (SMC-01..06).

## Tasks

### Task 1: mtf.py — confirmation-time as-of join + lean MTF payload (commit 10db9b5)
- `htf_context` with guards (required columns, per-symbol monotonic/unique time_utc, finite OHLC, zone-schema check), pinned 14-column payload, deterministic NA/NaN/empty contracts, input non-mutation.
- Join-key dtype normalization on merge-asof copies: `datetime64[us]` + StringDtype both sides (make_bars vs derive_zones dtype conventions differ).
- Containment cross-join filtered to live zones with `range_low <= close <= range_high`, IDs sorted by (created_at, zone_id).

### Task 2: test_mtf_join.py — 11-test SMC-06 join suite (commit e16d168)
- Zone fixtures through the real chain on sculpted H1 frames (TWO_LEG 1.08/1.12, THREE_LEG adds 1.07 leg); committed-close invalidation sculpt (D-11: close 1.07 < range low) which also completes a down leg (asserted: 2 zones).
- Boundary semantics: zone visible AT its invalidation timestamp, excluded strictly after, NA/NaN/empty gap until the next zone confirms.
- DST fixture mirrors test_timezone_dst's server-wall offset arrays (+3 -> +2 flip at wall 40h) with the zone confirming BEFORE the flip; no bias gap and monotonic time_utc across it.

### Task 3: test_detector_integration.py — 10-test SC5 suite (commit e33e2ca)
- Combined 2-symbol (EURUSD sculpted / GBPUSD flat 1.32) 3-TF world; chain passes caller frames through un-copied and all snapshots stay bit-identical.
- Known-good sweep sculpt from test_sweeps (equal-high pool at 1.115, pierce pair 30/31, immediate reclaim) keeps the events tier non-empty.
- Vendor purity asserted by reading every file under src/ai_trading/detectors/ (no `import MetaTrader5` / `from MetaTrader5` / `floor_to_timeframe`).

## Verification Results

- `uv run pytest tests/unit/test_mtf_join.py -q` — 11 passed
- `uv run pytest tests/unit/test_detector_integration.py -q` — 10 passed
- `uv run pytest -q` — 174 passed, 3 deselected
- `uv run pytest -q -m "unit or mt5"` — 177 passed
- `uv run ruff check .` — clean
- Vendor-import grep over src/ai_trading/detectors/ — no matches
- `git diff --exit-code tests/conftest.py tests/unit/_detector_fixtures.py` — shared fixtures untouched

## Deviations

- **Detector validators moved to per-symbol time checks (swings.py, pools.py, zones.py, mtf.py).** The integration suite's combined multi-symbol frames repeat timestamps across symbols and concatenate symbol blocks, so global `is_monotonic_increasing`/`is_unique` guards rejected valid input. Per the plan's "implementations move, not tests" clause, guards now enforce strictly-increasing+unique time_utc within each symbol. Single-symbol behavior is unchanged; no prior test asserted the global form.
- **Join tests authored after Task 1 implementation** (plan marked both tasks tdd): fixture design depended on verified module contracts (detect_pools returns (pools, events); D-11 invalidation is close beyond EITHER boundary; zigzag tail replacement), so source was read first; the corrected fixtures passed on first run.

## Decisions

- Liveness predicate pinned as `invalidated_at is NA or >= T` — an invalidation stamped at exactly T is a confirmation at T and remains visible; strictly-after T the zone is dead. Matches the plan's boundary wording verbatim.
- No HTF pool/sweep payload in v1 (D-14): payload columns contain no pool/sweep fields (asserted).
- Bias mapping exact-equilibrium case returns "neutral" (A9), not NaN.

## Issues

- None open. The two failing first-run integration assertions were test-side (bias sculpts make bars 54/55 non-bearish); fixed by spot-checking sculpt rows and asserting uniform bearish only outside the sculpt window.

## Self-Check: PASSED
