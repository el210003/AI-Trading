---
phase: 03-backtesting-labeling
plan: 01
subsystem: backtest
tags: [backtest, replay, lookahead-safety, cost-model, smc, pandas, prefix-equivalence]

# Dependency graph
requires:
  - phase: 02-smc-detection-engine
    provides: detector chain exports (detect_swings, build_zigzag, detect_pools, derive_zones, htf_context) with tier-3 repaint guarantees and pinned schemas
  - phase: 01-data-foundation
    provides: COLUMNS/TIMEFRAME_MINUTES bar frames, frozen Config + fail-fast validation, bar_store.merge_and_write
provides:
  - src/ai_trading/backtest/ package core: asof (STAMP_CLOSE/STAMP_BAR visible_mask), chain (run_chain), costs (pip/point conversion + direction-aware fills), candidates (D-01..D-13 pure entry rules), replay (forward-pass state machine + LABEL_COLUMNS schema)
  - 12 frozen Config backtest knobs with fail-fast validation + committed config.toml section
  - tests/unit/_backtest_fixtures.py (set_spreads, bt_cfg, write_bars_parquet)
  - anti-lookahead suite: per-tier as-of tests + replay-level 1-by-1/chunked prefix equivalence (check_exact=True)
affects: [03-02 (barriers consume costs + resolver seam), 03-03 (runner wires chain+replay+gate), phase-4-ml (label schema), phase-6-setups (imports candidate functions per D-03)]

# Tech tracking
tech-stack:
  added: []  # zero new dependencies (locked stack: pandas 3.x, pyarrow)
  patterns: [single-pass chain runner + column-aware as-of slicer, validate-then-compute pure fns, sequential event-sparse replay loop (deliberately not vectorized), schema-pinned empty frames, per-symbol validators]

key-files:
  created:
    - src/ai_trading/backtest/__init__.py
    - src/ai_trading/backtest/asof.py
    - src/ai_trading/backtest/chain.py
    - src/ai_trading/backtest/costs.py
    - src/ai_trading/backtest/candidates.py
    - src/ai_trading/backtest/replay.py
    - tests/unit/_backtest_fixtures.py
    - tests/unit/test_backtest_config.py
    - tests/unit/test_asof.py
    - tests/unit/test_costs.py
    - tests/unit/test_candidates.py
    - tests/unit/test_replay.py
    - tests/unit/test_replay_repaint.py
  modified:
    - src/ai_trading/config.py
    - config.toml
    - tests/unit/test_normalize_and_config.py
    - tests/unit/test_detector_integration.py

key-decisions:
  - "BT-01 chain runner promotes the verified Phase 2 integration composition verbatim; zero backtest-side detection logic (vendor-purity assertion extended over backtest/*.py)"
  - "run_chain also derives zones15 (M15 zones) — the D-01 zone tap consumes them; plan's pinned 11-key dict was internally inconsistent with the replay spec"
  - "Cost convention A1 pinned: bar prices are bid-side, long crosses the spread at entry, short at exit; spread is POINTS (pip/10), slippage in pips on both fills"
  - "D-09 TP liveness convention (D-09 silent): opposite pools resolved at/before the decision bar are excluded from TP candidates; ties resolve to the pool"
  - "D-05 slot-release timing: label appended at fill from ONE resolver call; slot held until the loop advances past the resolver's exit_idx"
  - "Label schema LABEL_COLUMNS (20 cols) with pinned dtypes (StringDtype / datetime64[us] / int64 / float64) for check_exact=True repaint stability"

patterns-established:
  - "Per-tier visibility anchors: close-time stamps (confirmed_at/created_at/activated_at) anchor at close_t; bar-time stamps (pierced_at/resolved_at/mitigated_at/invalidated_at) anchor at bar_t; MTF payload rows consumed as-is"
  - "Candidate functions own their anchor re-filtering so Phase 6 can pass unfiltered frames and get identical results (D-03)"
  - "Prefix-equivalence contract: replay(bars[:k]) labels == full labels with entry_time < prefix_close_time(bars, k), STRICT inequality, check_exact=True"

requirements-completed: [BT-01, BT-02]

coverage:
  - id: D1
    description: "BT-01 shared code path: run_chain calls only detector exports (no re-implementation); vendor-purity assertion covers src/ai_trading/backtest/*.py"
    requirement: BT-01
    verification:
      - kind: unit
        ref: "tests/unit/test_detector_integration.py#test_no_vendor_imports_in_detector_sources"
        status: pass
      - kind: unit
        ref: "tests/unit/test_detector_integration.py#test_full_chain_end_to_end_over_multi_tf_frames"
        status: pass
    human_judgment: false
  - id: D2
    description: "Point-in-time as-of slicer with per-tier anchors (close-kind vs bar-kind), NaT exclusion, close_time_of over TIMEFRAME_MINUTES"
    requirement: BT-01
    verification:
      - kind: unit
        ref: "tests/unit/test_asof.py"
        status: pass
    human_judgment: false
  - id: D3
    description: "BT-02 cost model: spread POINTS->price via point_size, D-15 default fallback, D-14 per-symbol slippage, direction-aware entry/exit fills, raw-vs-net delta = 2x slippage"
    requirement: BT-02
    verification:
      - kind: unit
        ref: "tests/unit/test_costs.py"
        status: pass
    human_judgment: false
  - id: D4
    description: "Entry-candidate pure functions (D-01..D-04, D-08..D-13): sweep+tap composition, bias gate, structural SL/nearest-live-TP, compute_rr — Phase 6 imports these exact functions"
    requirement: BT-01
    verification:
      - kind: unit
        ref: "tests/unit/test_candidates.py"
        status: pass
    human_judgment: false
  - id: D5
    description: "Forward-pass replay state machine: D-05 one-at-a-time with slot-release timing, D-07 silent warmup, D-12 fill-time min-R:R discard, D-21 history gate, LABEL_COLUMNS schema with pinned dtypes, resolver seam"
    requirement: BT-01
    verification:
      - kind: unit
        ref: "tests/unit/test_replay.py"
        status: pass
    human_judgment: false
  - id: D6
    description: "Anti-lookahead proof: replay prefix equivalence over the full decision path (1-by-1 + chunked, check_exact=True), boundary TIMEOUT truncation as expected behavior, determinism"
    requirement: BT-01
    verification:
      - kind: unit
        ref: "tests/unit/test_replay_repaint.py"
        status: pass
    human_judgment: false
  - id: D7
    description: "12 frozen Config backtest knobs with fail-fast validation (_REQUIRED_KEYS + _validate rejection matrix) and committed config.toml section"
    requirement: BT-02
    verification:
      - kind: unit
        ref: "tests/unit/test_backtest_config.py"
        status: pass
    human_judgment: false
  - id: D8
    description: "A1 cost-asymmetry convention (long pays spread at entry, short at exit) — 10-second human eyeball at phase verification, pinned by test_long_short_cost_symmetry"
    verification: []
    human_judgment: true
    rationale: "Convention choice is a human decision per plan user_setup (03-VALIDATION manual-only row); the symmetric cost math is unit-proven, the convention itself is not machine-verifiable"

# Metrics
duration: 82min
completed: 2026-09-02
status: complete
---

# Phase 3 Plan 1: Replay Engine Core Summary

**MT5-free replay engine core: BT-01 chain runner + as-of slicer, BT-02 direction-aware cost model, D-01..D-13 entry-candidate pure functions, and the forward-pass replay state machine proven look-ahead-safe by a 1-by-1/chunked prefix-equivalence suite**

## Performance

- **Duration:** 82 min
- **Started:** 2026-09-02T01:47:02Z
- **Completed:** 2026-09-02T03:09:09Z
- **Tasks:** 3
- **Files modified:** 17 (13 created, 4 modified)

## Accomplishments
- BT-01 shared code path is executable: `chain.run_chain` runs the identical Phase 2 detector exports (plus M15 `zones15` for the tap), and the replay consumes tier output only through `asof.visible_mask` with per-tier anchors — zero backtest-side detection logic, enforced by an extended vendor-purity assertion
- BT-02 cost model: spread POINTS→price via point_size (pip/10), D-15 default fallback (the dominant stored-data path), D-14 per-symbol slippage on both fills, direction-aware fills (A1: long crosses the spread at entry, short at exit), raw variant via `apply_slippage=False`
- Entry rules defined once as pure functions (`bias_agrees`, `candidate_at_bar`, `compute_rr`) — Phase 6 setup assembly imports these exact functions (D-03)
- Forward-pass replay with D-05 slot-release timing, D-07 silent warmup (auto 28), D-12 fill-time min-R:R discard, D-21 history gate with actionable refusal, and the interface-first resolver seam for 03-02's walk_barriers
- Anti-lookahead proof green: prefix labels == visible subset of full labels (`check_exact=True`) over 1-by-1 AND chunked appends; boundary-window TIMEOUT truncation asserted as expected behavior; determinism pinned
- 12 frozen Config backtest knobs with fail-fast validation + committed config.toml section; conftest/_detector_fixtures untouched (Phase 1/2 Wave-0 contract)

## Task Commits

Each task was committed atomically:

1. **Task 1: Backtest package scaffold + config knobs + test fixtures** - `7af3685` (feat)
2. **Task 2: As-of slicer + chain runner + cost model (BT-01/BT-02 core)** - `d8982a7` (feat)
3. **Task 3: Entry-candidate pure functions + forward-pass replay + anti-lookahead proof** - `5fbba0c` (feat)

## Files Created/Modified
- `src/ai_trading/backtest/__init__.py` - bare package marker (mirrors detectors/__init__.py)
- `src/ai_trading/backtest/asof.py` - STAMP_CLOSE/STAMP_BAR anchors, visible_mask, close_time_of
- `src/ai_trading/backtest/chain.py` - run_chain: the single-pass BT-01 composition (12-key dict incl. zones15)
- `src/ai_trading/backtest/costs.py` - pip_size/point_size, effective spread/slippage, entry/exit fill prices
- `src/ai_trading/backtest/candidates.py` - Candidate/CandidateState, bias_agrees, candidate_at_bar, compute_rr
- `src/ai_trading/backtest/replay.py` - Position, LABEL_COLUMNS, auto_warmup_bars, check_history_gate, assert_offset_uniform, replay_symbol
- `src/ai_trading/config.py` - +12 frozen Config fields, _REQUIRED_KEYS, _validate rules (suffixed symbols resolve via base name)
- `config.toml` - documented backtest knob section
- `tests/unit/_backtest_fixtures.py` - set_spreads, bt_cfg, write_bars_parquet
- `tests/unit/test_backtest_config.py` - happy path + rejection matrix + direct-construction defaults
- `tests/unit/test_asof.py` - per-tier boundary equality, NaT exclusion, invariants
- `tests/unit/test_costs.py` - literal-float fills, D-15/D-14 branches, symmetry, raw/net delta
- `tests/unit/test_candidates.py` - hand-derivable sculpted worlds (TP union, liveness, ties, vetoes)
- `tests/unit/test_replay.py` - warmup/D-05/D-04/D-12/D-21/schema/resolver seam
- `tests/unit/test_replay_repaint.py` - THE anti-lookahead suite over a real-chain world
- `tests/unit/test_normalize_and_config.py` - _base_values carries the 12 required keys (+ TOML dict fix in _write_config)
- `tests/unit/test_detector_integration.py` - vendor-purity assertion extended over backtest/*.py

## Decisions Made
- **run_chain derives zones15** (Rule 3 fix): the plan's pinned 11-key composition (copied from the Phase 2 integration test) never produced M15 zones, but the replay's D-01 tap consumes `chain["zones15"]` — internally inconsistent. Minimal fix: `derive_zones(zigzag15, m15)` added to the chain runner (same detector export; BT-01 preserved).
- **Close-kind boundary semantics corrected in the test spec** (Task 2): the plan's test bullet "stamp == bar_t (one TF earlier) NOT visible" contradicted the plan's own `stamp <= close_t` formula, RESEARCH Pattern 1, and Phase 2 stamp semantics (a close-time stamp at bar_t is the PREVIOUS bar's confirmation — visible). Test asserts the formula's semantics.
- **Float-literal strategy**: chained sums land 1–2 ulp from decimal literals, so fill-price tests assert exact equality against the implementation-matching decomposition plus `pytest.approx` guards; composite round-trip deltas use `abs=1e-15` guards (documented in test_costs.py docstring).
- **Suffixed broker symbols** (Phase 1 `.broker` suffix contract) resolve pip_size/overrides through their base name in config validation and costs lookups.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] TOML dict serialization in test config writers**
- **Found during:** Task 1
- **Issue:** `_write_config` used `json.dumps` for all values; dict values emitted JSON object syntax (`{"EURUSD": 0.0001}`) which tomllib rejects (inline tables need `{ K = V }`) — 34 existing tests failed
- **Fix:** dict values serialize as TOML inline tables in both test modules' `_write_config`
- **Files modified:** tests/unit/test_normalize_and_config.py, tests/unit/test_backtest_config.py
- **Verification:** full unit suite green
- **Committed in:** 7af3685

**2. [Rule 1 - Bug] Suffixed broker symbols broke pip_size validation**
- **Found during:** Task 1
- **Issue:** literal "every symbol in cfg.symbols must appear as a pip_size key" regressed Phase 1's accepted suffixed symbols (EURUSD.a) — `test_symbol_names_accepted[EURUSD.a]` failed
- **Fix:** pip_size and per-symbol override keys resolve through the base name (`_base_symbol`), mirroring the Phase 1 suffix contract
- **Files modified:** src/ai_trading/config.py
- **Verification:** test_symbol_names_accepted green; rejection matrix still rejects unknown keys
- **Committed in:** 7af3685

**3. [Rule 3 - Blocking] run_chain did not produce M15 zones for the replay tap**
- **Found during:** Task 3
- **Issue:** the pinned chain composition (from test_detector_integration.run_chain) omits M15 zones while the replay spec consumes `chain["zones15"]` — the repaint suite's fixture-sanity assertion caught a silent zero-label world (prefix tests passed trivially on empty == empty)
- **Fix:** `zones15 = derive_zones(zigzag15, m15)` added to run_chain (12th key); same detector export, BT-01 preserved
- **Files modified:** src/ai_trading/backtest/chain.py
- **Verification:** test_replay_repaint world now yields the hand-derived label; prefix-equivalence non-trivially green
- **Committed in:** 5fbba0c

---

**Total deviations:** 3 auto-fixed (1 bug, 2 blocking) + 1 plan-spec test correction (documented under Decisions Made)
**Impact on plan:** All fixes required for correctness of the plan's own spec; no scope creep. The zones15 fix slightly extends the chain dict (12 keys vs the pinned 11) — downstream plans 03-02/03-03 should read `chain["zones15"]` for M15 zones.

## Issues Encountered
- The repaint suite initially passed trivially (zero labels in both prefix and full runs) — caught by adding a fixture-sanity assertion (`test_world_produces_exactly_one_expected_label`) that pins the hand-derived label; this is what surfaced the zones15 gap. Lesson recorded: anti-lookahead suites need a positive-control assertion.
- pandas NA comparisons (`pd.NA == pd.NA`) raise "boolean value of NA is ambiguous" — prefix-stability assertions skip NA-NA pairs explicitly.

## Known Stubs
- None in src. `replay_symbol`'s `resolver` parameter is an intentional interface-first seam (documented in the module docstring): plan 03-02 implements `walk_barriers` against it; plan 03-03's runner wires it. `barrier_stub` in test_replay_repaint.py is a test-local stand-in for 03-02's end-of-data lens, documented as such.

## User Setup Required

**One human decision at phase verification.** See [03-USER-SETUP.md](./03-USER-SETUP.md):
- Confirm the A1 cost-asymmetry convention (long pays spread at entry, short at exit) — pinned by `test_long_short_cost_symmetry`; 10-second eyeball, non-blocking for implementation.

## Next Phase Readiness
- The resolver seam (`Callable[[Position, DataFrame, Config], dict] -> {outcome, exit_time, exit_price, exit_idx, r_gross, r_raw, r_net}`) and LABEL_COLUMNS are ready for 03-02's triple-barrier implementation; the R-unit cost expression per convention (a) is specified there
- 03-03's runner wires: D-21 gate (implemented here), `assert_offset_uniform` (implemented here), `write_bars_parquet` fixture path for integration tests, and `chain["zones15"]` is available for the replay input
- Full suite: 261 passed (174 pre-existing + 87 new), 3 mt5-deselected; ruff clean
- Note: M15 stored history (~9 days) still sits below the D-21 default gate — runner-level override decision belongs to 03-03/phase verification per RESEARCH Open Question 1

---
*Phase: 03-backtesting-labeling*
*Completed: 2026-09-02*

## Self-Check: PASSED

All 13 created files verified on disk; all 4 commits (7af3685, d8982a7, 5fbba0c, f259af6) verified in git log. Full suite 261 passed / 3 mt5-deselected; ruff clean; conftest and _detector_fixtures byte-identical (Wave-0 gate).
