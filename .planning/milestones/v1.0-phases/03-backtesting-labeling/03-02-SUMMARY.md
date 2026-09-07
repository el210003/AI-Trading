---
phase: 03-backtesting-labeling
plan: 02
subsystem: backtest
tags: [triple-barrier, labeling, statistics, profit-factor, drawdown, atomic-writes, parquet, determinism]

# Dependency graph
requires:
  - phase: 03-backtesting-labeling (plan 01)
    provides: Position contract + resolver seam (replay.py), LABEL_COLUMNS schema, costs.entry_fill_price/exit_fill_price (raw vs net), effective_spread_points (D-15 fallback), _backtest_fixtures (bt_cfg, make_bars, set_spreads)
provides:
  - src/ai_trading/backtest/barriers.py: OUTCOME_WIN/LOSS/TIMEOUT + walk_barriers (the 03-01 resolver seam, now implemented — BT-03)
  - src/ai_trading/backtest/stats.py: canonical_stats + stats_by_symbol_timeframe with raw_/net_ variants and cost_delta_expectancy (BT-04)
  - src/ai_trading/backtest/reports.py: write_labels / write_canonical_stats / write_run_manifest / config_hash / _atomic_json / _atomic_parquet
  - 59 new unit tests pinning the tie rule, gap fills, off-by-one window, R math, guard table, and artifact atomicity/determinism
affects: [03-03 (runner wires walk_barriers into replay_symbol and calls the writers), phase-4-ml (labels carry entry_time/exit_time for AFML ch.7 purge; config_hash for content versioning), phase-6-setups (canonical stats panel)]

# Tech tracking
tech-stack:
  added: []  # zero new dependencies (locked stack: pandas 3.x, pyarrow)
  patterns: [SL-first conservative tie convention, gap-open fills, inclusive time-barrier window, convention-(a) single-denominator R normalization, decided-trade PF ratio, tmp+os.replace atomic writes, manifest/label separation for byte determinism]

key-files:
  created:
    - src/ai_trading/backtest/barriers.py
    - src/ai_trading/backtest/stats.py
    - src/ai_trading/backtest/reports.py
    - tests/unit/test_barriers.py
    - tests/unit/test_stats.py
    - tests/unit/test_reports.py
  modified: []

key-decisions:
  - "profit_factor pinned as a decided-trade ratio: R-sign sums over WIN/LOSS rows only (TIMEOUT excluded from both sums, A4-consistent) — the plan's hand-pinned series (timeout -0.1, PF == 1.5) is internally inconsistent with an all-rows sum (which yields 1.5/1.1); documented in stats.py docstring"
  - "R normalization follows convention (a) exactly: one structural denominator |entry_open - sl_price| for gross/raw/net; per-trade delta pinned to -2*slip_px/risk (-0.10 exact on the fixture), spread cancels"
  - "write_run_manifest enforces the exact MANIFEST_KEYS set (missing AND unknown keys fail fast) — the hard guarantee that run metadata never leaks into label/canonical bytes"
  - "walk_barriers raises on non-positive structural risk (zero distance pinned by plan; wrong-side SL guarded as an extension so inverted levels can never silently flip R signs)"

patterns-established:
  - "Barrier walk: gap check on the open BEFORE high/low checks on every bar (entry bar included); SL-first branch order everywhere; no TP-first/close-direction heuristic anywhere in the module"
  - "Atomic writers: every artifact goes through _atomic_json/_atomic_parquet (tmp sibling + os.replace + unlink-on-failure), mirroring bar_store.merge_and_write"
  - "Determinism: label parquet and canonical stats JSON are byte-identical across same-input re-runs; created_at/run_id live only in run_manifest.json"

requirements-completed: [BT-03, BT-04]

coverage:
  - id: D1
    description: "BT-03 triple-barrier walk: SL-first tie rule on ALL bars incl. entry bar (D-10), gap-open fills both directions (D-11), inclusive 96-bar window with TIMEOUT at bar E+95 close (D-17), WIN/LOSS/TIMEOUT classes (D-18)"
    requirement: BT-03
    verification:
      - kind: unit
        ref: "tests/unit/test_barriers.py#test_tie_sl_first_including_entry_bar"
        status: pass
      - kind: unit
        ref: "tests/unit/test_barriers.py#test_timeout_after_exactly_96_bars"
        status: pass
      - kind: unit
        ref: "tests/unit/test_barriers.py#test_long_gap_below_sl_fills_at_open"
        status: pass
      - kind: unit
        ref: "tests/unit/test_barriers.py#test_short_gap_below_tp_fills_at_open"
        status: pass
      - kind: unit
        ref: "tests/unit/test_barriers.py#test_sl_hit_on_entry_bar"
        status: pass
      - kind: unit
        ref: "tests/unit/test_barriers.py#test_timeout_near_end_of_data"
        status: pass
    human_judgment: false
  - id: D2
    description: "Convention-(a) R math: gross/raw/net over the SAME structural risk; clean SL hit -> r_raw -1.20 / r_net -1.30 (both < -1.0); per-trade delta -2*slip_px/risk == -0.10 exact"
    requirement: BT-03
    verification:
      - kind: unit
        ref: "tests/unit/test_barriers.py#test_r_literals_loss"
        status: pass
      - kind: unit
        ref: "tests/unit/test_barriers.py#test_r_literals_short_loss_symmetry"
        status: pass
      - kind: unit
        ref: "tests/unit/test_barriers.py#test_r_literals_win"
        status: pass
      - kind: unit
        ref: "tests/unit/test_barriers.py#test_zero_risk_distance_raises"
        status: pass
    human_judgment: false
  - id: D3
    description: "Resolver-seam lifecycle consistency: replay_symbol accepts walk_barriers and lands the returned dict verbatim in the label row"
    requirement: BT-03
    verification:
      - kind: unit
        ref: "tests/unit/test_barriers.py#test_walk_barriers_satisfies_replay_resolver_seam"
        status: pass
    human_judgment: false
  - id: D4
    description: "BT-04 canonical stats: hand-computed literals, A4 win-rate denominator (TIMEOUT excluded, share separate), A5 expectancy over ALL trades, PF inf/nan guards, R-curve max_dd, empty-input safety"
    requirement: BT-04
    verification:
      - kind: unit
        ref: "tests/unit/test_stats.py#test_hand_computed_series"
        status: pass
      - kind: unit
        ref: "tests/unit/test_stats.py#test_profit_factor_guards"
        status: pass
      - kind: unit
        ref: "tests/unit/test_stats.py#test_win_rate_denominator_ignores_timeouts"
        status: pass
      - kind: unit
        ref: "tests/unit/test_stats.py#test_all_timeout_stats"
        status: pass
      - kind: unit
        ref: "tests/unit/test_stats.py#test_empty_labels_yield_nan_stats_and_zero_dd"
        status: pass
    human_judgment: false
  - id: D5
    description: "Per-(symbol, timeframe) grouping only (never global), raw_ + net_ variants with visible cost delta computed over REAL walk_barriers output (cost_delta_expectancy == -0.10 exact)"
    requirement: BT-04
    verification:
      - kind: unit
        ref: "tests/unit/test_stats.py#test_stats_by_symbol_timeframe_groups_without_leakage"
        status: pass
      - kind: unit
        ref: "tests/unit/test_stats.py#test_cost_delta_expectancy_from_real_walk_barriers"
        status: pass
      - kind: unit
        ref: "tests/unit/test_stats.py#test_stats_by_symbol_timeframe_empty_labels"
        status: pass
    human_judgment: false
  - id: D6
    description: "Atomic artifact writers: tmp + os.replace everywhere, no .tmp residue on success or failure, parent dirs created"
    requirement: BT-03
    verification:
      - kind: unit
        ref: "tests/unit/test_reports.py#test_no_tmp_file_remains_after_successful_write"
        status: pass
      - kind: unit
        ref: "tests/unit/test_reports.py#test_failed_parquet_write_leaves_no_tmp_residue_and_reraises"
        status: pass
      - kind: unit
        ref: "tests/unit/test_reports.py#test_failed_json_write_leaves_no_tmp_residue_and_reraises"
        status: pass
    human_judgment: false
  - id: D7
    description: "Determinism + idempotency: byte-identical label parquet across re-runs, byte-identical canonical JSON, (symbol, entry_time) keep=last overwrite, manifest regeneration never touches label bytes, config_hash stable/sensitive"
    requirement: BT-04
    verification:
      - kind: unit
        ref: "tests/unit/test_reports.py#test_labels_write_is_byte_deterministic"
        status: pass
      - kind: unit
        ref: "tests/unit/test_reports.py#test_canonical_stats_json_is_deterministic"
        status: pass
      - kind: unit
        ref: "tests/unit/test_reports.py#test_revised_row_same_key_keeps_last"
        status: pass
      - kind: unit
        ref: "tests/unit/test_reports.py#test_manifest_regeneration_does_not_touch_label_bytes"
        status: pass
      - kind: unit
        ref: "tests/unit/test_reports.py#test_config_hash_changes_when_a_knob_changes"
        status: pass
    human_judgment: false
  - id: D8
    description: "SL-first-as-the-right-conservative-convention (D-10) is a locked human convention — the tie-rule math is unit-proven, the choice itself is not machine-verifiable (per 03-USER-SETUP pattern from plan 01)"
    verification: []
    human_judgment: true
    rationale: "Convention choice per D-10 research grounding (intrabar path unknowable from OHLC); the named test pins the implementation, a human eyeballs that the convention matches intent at phase verification"

# Metrics
duration: 21min
completed: 2026-09-02
status: complete
---

# Phase 3 Plan 2: Barriers, Stats & Reports Summary

**Triple-barrier outcome walk (SL-first, gap=open, 96-bar inclusive window) with convention-(a) R in gross/raw/net, canonical per-symbol/timeframe stats with visible cost delta, and atomic byte-deterministic label/canonical/manifest writers**

## Performance

- **Duration:** 21 min
- **Started:** 2026-09-02T12:35:45Z
- **Completed:** 2026-09-02T12:56:30Z
- **Tasks:** 3
- **Files modified:** 6 (all created)

## Accomplishments
- BT-03 executable: `walk_barriers` implements the 03-01 resolver seam — D-10 SL-first on every bar (entry bar included, named test fails on any TP-first/close-direction heuristic), D-11 gap-open fills in both directions checked before high/low, D-17 inclusive window `[E, E+time_barrier_bars)` with TIMEOUT at the final window bar's close, D-18 WIN/LOSS/TIMEOUT classes
- R math per convention (a): all three variants normalize by the SAME structural risk `|entry_open - sl_price|`; a clean SL hit lands r_raw = -1.20 / r_net = -1.30 exactly on the pinned fixture (spread 20 pt, slip 0.5 pip, risk 0.001), both strictly below -1.0, per-trade delta exactly -2*slip/risk = -0.10
- BT-04 canonical stats as pure functions: win rate (A4 denominator excludes TIMEOUT, share reported separately), expectancy/avg_r over ALL trades (A5), profit factor with inf/nan guards, R-curve max DD, per-(symbol, timeframe) only — raw + net variants with cost_delta_expectancy visible
- Atomic deterministic persistence: labels Parquet keyed (symbol, entry_time), canonical stats JSON, and a separate run manifest carrying config hash — all through tmp + os.replace, byte-identical on re-runs, no .tmp residue even on failure
- Full suite 320 passed (261 pre-existing + 59 new), 3 mt5-deselected; ruff clean repo-wide

## Task Commits

Each task was committed atomically:

1. **Task 1: Triple-barrier walk (BT-03)** - `2f84b4b` (feat)
2. **Task 2: Canonical stats (BT-04)** - `72ed7ca` (feat)
3. **Task 3: Label + canonical-stat artifact writers** - `96d5631` (feat)

## Files Created/Modified
- `src/ai_trading/backtest/barriers.py` - OUTCOME_* constants + walk_barriers (resolver seam implementation; SL-first/gap/inclusive-window conventions documented in-module)
- `src/ai_trading/backtest/stats.py` - canonical_stats, stats_by_symbol_timeframe, STATS_COLUMNS schema with pinned empty-frame dtypes
- `src/ai_trading/backtest/reports.py` - write_labels, write_canonical_stats, write_run_manifest, config_hash, _atomic_json/_atomic_parquet
- `tests/unit/test_barriers.py` - 26 tests: tie/gap/off-by-one/R-literal pins + resolver-seam lifecycle test
- `tests/unit/test_stats.py` - 17 tests: hand-computed literals, guard parametrization, no-leakage grouping, real-walk cost delta
- `tests/unit/test_reports.py` - 16 tests: atomicity, determinism, idempotent overwrite, schema, manifest separation, hash stability

## Decisions Made
- **Profit factor as a decided-trade ratio** (plan-spec correction): the plan's action text says `sum(r > 0) / abs(sum(r < 0))` over the R column, but its own hand-pinned series (wins +1.0/+0.5, loss -1.0, timeout -0.1) demands PF == 1.5 — an all-rows sum yields 1.5/1.1 = 1.3636 because the negative timeout R lands in the denominator. Resolved A4-consistently: TIMEOUT rows are excluded from BOTH PF sums (win_rate already excludes them from its denominator); all-TIMEOUT runs report PF nan, mirroring their nan win_rate. Documented in stats.py docstring; hand-pinned value holds exactly.
- **Wrong-side SL guard extension**: the plan pins the zero-risk guard (`sl == entry_open` -> ValueError); implemented additionally for risk < 0 (SL on the wrong side of entry for the direction) so an inverted level can never silently flip R signs. Same invariant family, fail-fast style.
- **Run-manifest key contract enforced**: write_run_manifest rejects missing AND unknown keys against MANIFEST_KEYS — turns the "run metadata ONLY" separation from a convention into a hard guarantee (test_run_manifest_key_contract).
- **Float-literal strategy** (carried from 03-01): R assertions use pytest.approx(abs=1e-12) around hand-derived decompositions; chained cost sums land 1-2 ulp from decimal literals.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Test-fixture construction errors (3 failures, module logic correct)**
- **Found during:** Task 1
- **Issue:** test helpers indexed sculpted frames before building Positions (`_position(bars)` hit KeyError/IndexError on dropped/out-of-range spread lookups) and one timeout assertion used a wrong index arithmetic (`len(bars) - 105` vs E+95)
- **Fix:** built positions from the full frame before sculpting/dropping; replaced the bogus assertion with the inclusive-count pin `exit_idx - E + 1 == 96`
- **Files modified:** tests/unit/test_barriers.py
- **Verification:** 26/26 barriers tests green
- **Committed in:** 2f84b4b (part of Task 1 commit)

---

**Total deviations:** 1 auto-fixed (test-side bug; no source-module changes needed). The PF decided-trade reading is documented under Decisions Made as a plan-spec correction (plan internally inconsistent: formula text vs hand-pinned literal — the pinned acceptance criterion wins).
**Impact on plan:** No scope creep; all plan acceptance criteria verified green.

## Issues Encountered
- None beyond the fixture bugs above; pandas 3.x StringDtype groupby/astype behavior behaved as pinned in the 03-01 patterns.

## Known Stubs
- None. All three modules are pure complete implementations; no placeholder branches, no TODO/FIXME markers.

## User Setup Required

None - no external service configuration required. (The D-10 SL-first convention choice joins plan 03-01's A1 convention in 03-USER-SETUP.md for the phase-verification eyeball; no new setup steps.)

## Next Phase Readiness
- 03-03 runner can wire directly: `replay_symbol(bars, chain, cfg, walk_barriers)` is proven end-to-end (resolver-seam lifecycle test), and the writers (`write_labels`, `write_canonical_stats`, `write_run_manifest`, `config_hash`) are ready for the runner's artifact step; `data/labels/` is the canonical artifact dir per the plan layout
- Phase 4 purge contract satisfied: labels carry entry_time/exit_time (AFML ch.7 purge inputs) and `config_hash(cfg)` is available for content-versioned caching
- Full suite 320 passed / 3 mt5-deselected; ruff clean; zero new dependencies

---
*Phase: 03-backtesting-labeling*
*Completed: 2026-09-02*

## Self-Check: PASSED

All 6 created files verified on disk; all 3 task commits (2f84b4b, 72ed7ca, 96d5631) verified in git log. Full suite 320 passed / 3 mt5-deselected; `uv run ruff check .` clean. Named integrity gates green: test_tie_sl_first_including_entry_bar, test_timeout_after_exactly_96_bars, test_cost_delta_expectancy_from_real_walk_barriers, test_no_tmp_file_remains_after_successful_write, test_labels_write_is_byte_deterministic.
