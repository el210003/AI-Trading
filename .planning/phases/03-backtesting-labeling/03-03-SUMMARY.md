---
phase: 03-backtesting-labeling
plan: 03
subsystem: backtest
tags: [walk-forward, time-series-split, expanding-train, rolling-test, canonical-stats, runner-cli, parquet, determinism, atomic-writes, zero-candidate]

# Dependency graph
requires:
  - phase: 03-backtesting-labeling (plan 01)
    provides: replay_symbol + Position contract + resolver seam, check_history_gate/assert_offset_uniform, run_chain (BT-01), frozen Config backtest knobs, _backtest_fixtures
  - phase: 03-backtesting-labeling (plan 02)
    provides: walk_barriers (BT-03), canonical_stats/stats_by_symbol_timeframe (BT-04), reports writers + config_hash + atomic tmp+os.replace discipline, LABEL_COLUMNS schema with entry_time/exit_time
provides:
  - src/ai_trading/backtest/walkforward.py: Window + build_windows (expanding train / rolling test, D-19/D-20), label_window_assignment (exactly-one-window by ENTRY bar time), window_stats_table + window_aggregate (D-22, raw_/net_ + cost delta)
  - src/ai_trading/backtest/reports.py extension: write_walkforward (byte-deterministic parquet) + write_window_manifest (metadata-only JSON, key-contract enforced)
  - src/ai_trading/backtest/runner.py + __main__.py: `python -m ai_trading.backtest` CLI — gate -> chain -> replay(barriers) -> stats -> walk-forward -> artifacts, exit codes 2/1/0 incl. zero-candidate runs
  - 38 new unit tests (19 walkforward, 6 reports, 13 runner); full suite 358 passed
affects: [phase-4-ml (reuses the SAME window harness per AI-04; labels carry entry_time/exit_time for the AFML ch.7 purge), phase-6-setups (per-window stats artifacts for the dashboard)]

# Tech tracking
tech-stack:
  added: []  # zero new dependencies (locked stack: pandas 3.x, pyarrow)
  patterns: [expanding-train/rolling-test chronological windows with b_k <= end coverage, entry-time window assignment via searchsorted, combined-domain shared windows for cross-symbol aggregates, frozen-Config CLI override via dataclasses.replace, zero-candidate-supported schema-correct empty artifacts, deterministic-filename parquet + metadata-only manifest]

key-files:
  created:
    - src/ai_trading/backtest/walkforward.py
    - src/ai_trading/backtest/runner.py
    - src/ai_trading/backtest/__main__.py
    - tests/unit/test_walkforward.py
    - tests/unit/test_runner.py
  modified:
    - src/ai_trading/backtest/reports.py
    - tests/unit/test_reports.py
    - .planning/phases/03-backtesting-labeling/03-USER-SETUP.md

key-decisions:
  - "Walk-forward windows derive over the COMBINED label domain (all symbols) so window_id boundaries are shared and the D-22 per-window aggregate across symbols is well-defined; identical to per-symbol derivation for single-symbol runs"
  - "build_windows loop bound is b_k <= end (not the plan's `while b_k < end` prose): a boundary-aligned max entry_time must be covered by the half-open window starting there — required by the plan's own exactly-one-window / outside-domain-is-an-error rules; never emits an empty trailing window"
  - "--min-history-days rebuilds the frozen Config via dataclasses.replace (no setattr, no signature threading); override validated > 0 at parse"
  - "Zero-candidate runs are a supported outcome: exit 0 with schema-correct empty artifacts (build_windows -> [], stats/assignment schema-correct empties); the D-21 gate already ran, so no signals is valid, not a refusal"
  - "window_start/window_end in stats frames are the OBSERVED entry-time span per window; authoritative boundaries live on Window objects and in walkforward_manifest.json"

patterns-established:
  - "The walkforward module is THE splitter of record — Phase 4 reuses these exact windows (AI-04, no shuffled splits anywhere)"
  - "Runner error mapping: ValueError/RuntimeError after load_config -> exit 1; config-class errors -> exit 2; success (incl. zero candidates) -> exit 0, never anything outside {0,1,2}"
  - "Label-derived artifacts under data/labels/, window artifacts under data/reports/ — walkforward_manifest.json intentionally lives in data/reports/"

requirements-completed: [BT-05]

coverage:
  - id: D1
    description: "BT-05 windowing: chronological expanding-train/rolling-test windows, zero overlap, no shuffles (D-19), day-configurable down to 1-2 days (D-20), zero-label contract (empty -> [] / schema-correct empties)"
    requirement: BT-05
    verification:
      - kind: unit
        ref: "tests/unit/test_walkforward.py#test_windows_chronological_zero_overlap"
        status: pass
      - kind: unit
        ref: "tests/unit/test_walkforward.py#test_expanding_train_strictly_before_test"
        status: pass
      - kind: unit
        ref: "tests/unit/test_walkforward.py#test_label_at_test_start_is_test_not_train"
        status: pass
      - kind: unit
        ref: "tests/unit/test_walkforward.py#test_small_windows_one_day_tests"
        status: pass
      - kind: unit
        ref: "tests/unit/test_walkforward.py#test_build_windows_empty_entry_times_returns_empty_list"
        status: pass
    human_judgment: false
  - id: D2
    description: "Exactly-one-window assignment by ENTRY bar time (searchsorted O(n log n)); outside-domain/NaT labels raise naming the entry_time; duplicate entry times both assign"
    requirement: BT-05
    verification:
      - kind: unit
        ref: "tests/unit/test_walkforward.py#test_every_label_assigned_exactly_one_window"
        status: pass
      - kind: unit
        ref: "tests/unit/test_walkforward.py#test_outside_domain_label_raises_naming_entry_time"
        status: pass
      - kind: unit
        ref: "tests/unit/test_walkforward.py#test_duplicate_entry_times_both_assign"
        status: pass
    human_judgment: false
  - id: D3
    description: "Per-window canonical stats per (window_id, symbol, timeframe) + cross-symbol pooled aggregate per window (D-22), raw_/net_ variants + cost_delta_expectancy (D-16), matching stats.canonical_stats per subset"
    requirement: BT-05
    verification:
      - kind: unit
        ref: "tests/unit/test_walkforward.py#test_window_stats_table_matches_canonical_per_group"
        status: pass
      - kind: unit
        ref: "tests/unit/test_walkforward.py#test_window_aggregate_pools_across_symbols"
        status: pass
    human_judgment: false
  - id: D4
    description: "Deterministic walk-forward artifacts: byte-identical parquet across re-runs (sort-insensitive writer, deterministic filename), separate manifest carrying boundaries + config_hash that never perturbs data bytes"
    requirement: BT-05
    verification:
      - kind: unit
        ref: "tests/unit/test_reports.py#test_walkforward_write_is_byte_deterministic_and_sort_insensitive"
        status: pass
      - kind: unit
        ref: "tests/unit/test_reports.py#test_window_manifest_roundtrip_and_separation"
        status: pass
    human_judgment: false
  - id: D5
    description: "Runner CLI exit-code contract: 2 config / 1 runtime refusal (D-21 gate with symbol+timeframe+day counts+remedy, mixed offsets, invalid range) / 0 success incl. zero-candidate runs with schema-correct empty artifacts; no artifacts written on refusal paths"
    requirement: BT-05
    verification:
      - kind: unit
        ref: "tests/unit/test_runner.py#test_gate_refusal_exit_1_with_actionable_message"
        status: pass
      - kind: unit
        ref: "tests/unit/test_runner.py#test_gate_override_allows_short_store"
        status: pass
      - kind: unit
        ref: "tests/unit/test_runner.py#test_mixed_offset_bars_refused"
        status: pass
      - kind: unit
        ref: "tests/unit/test_runner.py#test_invalid_range_returns_1_with_accepted_formats"
        status: pass
      - kind: unit
        ref: "tests/unit/test_runner.py#test_zero_candidate_run_exits_0_with_empty_artifacts"
        status: pass
    human_judgment: false
  - id: D6
    description: "Full pipeline wiring on synthetic parquet: gate -> offset guard -> range -> HTF lead-in (A8) -> BT-01 chain -> replay with the REAL walk_barriers (resolver seam closed) -> stats -> walk-forward -> all five artifacts with matching config_hash; label-derived under data/labels/ only"
    requirement: BT-05
    verification:
      - kind: unit
        ref: "tests/unit/test_runner.py#test_full_happy_path_end_to_end"
        status: pass
      - kind: unit
        ref: "tests/unit/test_runner.py#test_run_backtest_produces_labels_via_walk_barriers"
        status: pass
    human_judgment: false
  - id: D7
    description: "Phase-gate demo on real stored data with the human history-depth decision (M15 store ~9 days < D-21 30-day gate) — engine fully synthetic-tested either way; decision recorded in 03-USER-SETUP.md"
    verification: []
    human_judgment: true
    rationale: "Real-data demo requires the running terminal and a human call on history depth vs --min-history-days override (plan user_setup / RESEARCH Open Question 1); out of unit-test scope by design"

# Metrics
duration: 66min
completed: 2026-09-02
status: complete
---

# Phase 3 Plan 3: Walk-Forward Harness + Runner CLI Summary

**BT-05 walk-forward harness (expanding train / rolling test, entry-time assignment, per-window canonical stats + cross-symbol aggregate) and the `python -m ai_trading.backtest` runner CLI wiring gate -> chain -> replay(barriers) -> stats -> walk-forward -> deterministic artifacts with exit codes 2/1/0**

## Performance

- **Duration:** 66 min
- **Started:** 2026-09-02T13:38:13Z
- **Completed:** 2026-09-02T14:44:41Z
- **Tasks:** 3
- **Files modified:** 8 (5 created, 2 source/test modified, 1 planning doc)

## Accomplishments
- BT-05 executable: `build_windows` derives strictly chronological expanding-train / rolling fixed-length-test windows (next test_start == previous test_end, zero overlap, no shuffles — D-19/AI-04), day-configurable down to 1–2 days so the ~90-day store is usable today (D-20); `train_days` retained as documented Phase 4 metadata
- `label_window_assignment` gives every label EXACTLY ONE window by its ENTRY bar time (searchsorted, O(n log n)); outside-domain or NaT labels raise naming the entry_time — never dropped silently (Pitfall 7 pin); Phase 4 purge contract honored (split on entry TIME, exit-time overlap purge is Phase 4's AFML ch.7 obligation, documented in-module)
- Per-window reports: `window_stats_table` (full canonical stats per window_id × symbol × timeframe) + `window_aggregate` (pooled across symbols per window, D-22), both with raw_/net_ variants and visible cost_delta_expectancy (D-16), reusing `stats.canonical_stats`; zero-label paths return schema-correct empty frames — a no-candidate range never crashes the harness
- Deterministic persistence: `write_walkforward` (byte-identical parquet, sort-insensitive, deterministic filename) + `write_window_manifest` (boundaries/config-hash/range/created_at metadata ONLY, key contract enforced, regeneration never perturbs data bytes)
- Runner CLI closes the 03-01 resolver seam: `run_backtest` runs the D-21 history gate (actionable refusal message, nothing written on refusal), `assert_offset_uniform` on M15/H1/H4 (Pitfall 10), range resolution (inclusive date span clamped to store / last-ND / full), HTF warmup lead-in (A8), BT-01 `run_chain`, replay with the REAL `walk_barriers`, combined-domain walk-forward, and — with `--write` — all five artifacts in the 03-02-aligned layout (label-derived under data/labels/, window artifacts under data/reports/)
- Exit-code contract pinned end-to-end: 2 (config), 1 (gate/offset/range/replay refusals), 0 (success INCLUDING zero-candidate runs with schema-correct empty artifacts); `--min-history-days` overrides the frozen Config via `dataclasses.replace`
- Full suite 358 passed (320 pre-existing + 38 new), 3 mt5-deselected; `uv run ruff check .` clean; zero new dependencies; MT5-free vendor-purity assertion covers the new modules

## Task Commits

Each task was committed atomically:

1. **Task 1: Walk-forward window derivation + per-window stats (BT-05, D-19/D-20)** - `c19bab9` (feat)
2. **Task 2: Walk-forward artifact writer (deterministic, atomic) + reports extension** - `7ad6559` (feat)
3. **Task 3: Runner CLI — full pipeline wiring, history gate, offset uniformity, exit codes** - `8ab5b48` (feat)

## Files Created/Modified
- `src/ai_trading/backtest/walkforward.py` - Window dataclass, build_windows, label_window_assignment, window_stats_table, window_aggregate (THE splitter of record for Phase 4)
- `src/ai_trading/backtest/reports.py` - +write_walkforward, +write_window_manifest, WINDOW_MANIFEST_KEYS contract
- `src/ai_trading/backtest/runner.py` - main(argv)->int, run_backtest, resolve_range, _output_dirs path guard
- `src/ai_trading/backtest/__main__.py` - `python -m ai_trading.backtest` entry (declared CLI surface)
- `tests/unit/test_walkforward.py` - 19 tests: overlap/chronology/boundary/no-shuffle/small-windows/assignment/outside-domain/stats-aggregate/zero-label pins
- `tests/unit/test_reports.py` - +6 tests: atomicity, byte determinism + sort insensitivity, manifest separation, key contract, schema validation, empty round-trip
- `tests/unit/test_runner.py` - 13 tests: exit-code matrix, gate refusal/override, mixed-offset, range validation + clamping, happy path over the repaint-sculpted world with the real walk_barriers, zero-candidate contract
- `.planning/phases/03-backtesting-labeling/03-USER-SETUP.md` - added the plan 03-03 human decision (real-data demo history depth, Phase gate Open Question 1)

## Decisions Made
- **Combined-domain walk-forward windows**: the plan's per-symbol step-8 loop would give each symbol its own boundaries, making the D-22 "aggregate across symbols per window" ill-defined when stores differ. `run_backtest` derives windows once over the combined label domain (identical for single-symbol runs) so boundaries are shared and the pooled aggregate is exact.
- **build_windows loop bound `b_k <= end`** (plan-spec correction): the plan's own `while b_k < end` prose strands a boundary-aligned max entry_time outside every window, contradicting its exactly-one-window / outside-domain-is-an-error rules. `<=` covers `[b_0, end]` with half-open windows, never emits an empty trailing window, and keeps the plan's 5-window example byte-identical.
- **window_start/window_end in stats frames** are the observed entry-time span of each window's labels; authoritative boundaries live on `Window` objects and in `walkforward_manifest.json`.
- **Zero-candidate contract honored literally**: empty label sets exit 0 with schema-correct empty artifacts (INFO log "0 candidates for {symbol} in {range}") — an empty set after a passing gate is a valid outcome, not a refusal.
- **`--min-history-days` via `dataclasses.replace`** on the frozen Config (validated > 0 at parse) — no setattr, no extra parameters through `run_backtest`/`check_history_gate`.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Added backtest/__main__.py module entry**
- **Found during:** Task 3
- **Issue:** the plan's done criterion and Artifacts section declare `python -m ai_trading.backtest` as the CLI surface, but `files_modified` omitted the `__main__.py` entry file a package needs for `-m` execution
- **Fix:** 6-line `backtest/__main__.py` delegating to `runner.main` (keeps `__init__.py` a bare marker per the 03-01 contract); vendor-purity scan covers it automatically
- **Files modified:** src/ai_trading/backtest/__main__.py (created)
- **Verification:** `python -m ai_trading.backtest --help` exits 0; `--config missing.toml` exits 2 (live smoke)
- **Committed in:** 8ab5b48 (Task 3 commit)

**2. [Rule 1 - Bug] build_windows boundary-aligned domain coverage (plan-spec inconsistency)**
- **Found during:** Task 1
- **Issue:** the plan's `while b_k < end` prose leaves a label whose entry_time lands exactly on the last window boundary outside every window — which the plan's own assignment rule then (correctly) refuses, breaking legitimate stores (e.g. daily labels Aug 20–24 with test_days=1)
- **Fix:** loop bound `b_k <= end` (half-open windows cover `[b_0, end]`; no empty trailing windows; the plan's 5-window example unchanged); documented in the build_windows docstring
- **Files modified:** src/ai_trading/backtest/walkforward.py
- **Verification:** test_boundary_aligned_domain_fully_assigned + the full walkforward suite green
- **Committed in:** c19bab9 (Task 1 commit)

**3. [Rule 1 - Bug] Test fixture: local `_write_config` shadowed the imported helper (infinite recursion -> MemoryError)**
- **Found during:** Task 3
- **Issue:** the runner test's local config helper was named identically to the imported `test_backtest_config._write_config` and called itself, recursing until MemoryError (127 s hang/failure)
- **Fix:** imported the TOML writer under an alias (`_write_toml`); local helper delegates
- **Files modified:** tests/unit/test_runner.py
- **Verification:** 13/13 runner tests green in ~2 s
- **Committed in:** 8ab5b48 (Task 3 commit)

**4. [Rule 1 - Bug] Mixed-offset fixture silently normalized by the bar store's dedup contract**
- **Found during:** Task 3
- **Issue:** shifting the server-wall `time` column +2h for a few rows collided with neighbouring bar-open times, so `merge_and_write`'s documented `drop_duplicates("time", keep="last")` removed the shifted rows — the store round-tripped uniform and the offset guard never fired
- **Fix:** fixture now shifts `time_utc` for a few rows instead (same raw server time re-derived under a different broker offset — the faithful DST-flip simulation); `time` stays unique so nothing is deduped
- **Files modified:** tests/unit/test_runner.py
- **Verification:** test_mixed_offset_bars_refused exits 1 naming the symbol
- **Committed in:** 8ab5b48 (Task 3 commit)

---

**Total deviations:** 4 auto-fixed (1 blocking module entry, 3 bugs — one plan-spec inconsistency, two test-side). **Impact on plan:** all fixes required by the plan's own contract or fixtures; no scope creep. The `__main__.py` addition fulfills (not extends) the declared CLI surface.

## Issues Encountered
- The full runner test module initially hit a 5-minute timeout caused by the recursion bug above (fix 3) — after the fix the whole runner suite runs in ~2 s. No other issues; pandas 3.x groupby/StringDtype/searchsorted behavior behaved as pinned in the 03-01/03-02 patterns.

## Known Stubs
- None. All modules are complete implementations; no placeholder branches, no TODO/FIXME markers.

## User Setup Required

**One human decision added at phase verification.** See [03-USER-SETUP.md](./03-USER-SETUP.md):
- Real-data demo run (Phase gate, Open Question 1): M15 stored history is ~9 days (below D-21's 30-day gate). Decide at verification: deepen stored history via Phase 1 purge+backfill, run with `--min-history-days` override, or demo on H4-range depth. The engine is fully synthetic-tested either way. (Joins plan 03-01's A1 convention eyeball.)

## Next Phase Readiness
- Phase 3 scope (BT-01…BT-05) fully executable: `python -m ai_trading.backtest --config config.toml --range last-ND --write` runs the identical detector pipeline over stored history with actionable refusals
- Phase 4 (ML) reuse contract satisfied: `backtest.walkforward` is THE splitter (AI-04) — `Window` objects carry test boundaries + train/test masks; labels carry `entry_time`/`exit_time` for the AFML ch.7 purge (documented obligation); `config_hash` ready for content-versioned caching; walk-forward artifacts byte-deterministic for cache keys
- Phase 6 (dashboard) consumers ready: `data/reports/walkforward.parquet` + `walkforward_manifest.json` join the 03-02 canonical stats artifacts
- Full suite 358 passed / 3 mt5-deselected; ruff clean; zero new dependencies
- Carried obligations: DST live re-validation of the broker offset stays a human-assisted, mt5-marked check (02-VERIFICATION deferred item); Phase-gate demo history-depth decision recorded in 03-USER-SETUP.md

---
*Phase: 03-backtesting-labeling*
*Completed: 2026-09-02*

## Self-Check: PASSED

All 5 created files verified on disk; all 3 task commits (c19bab9, 7ad6559, 8ab5b48) verified in git log. Full suite 358 passed / 3 mt5-deselected; `uv run ruff check .` clean. Named integrity gates green: test_windows_chronological_zero_overlap, test_label_at_test_start_is_test_not_train, test_outside_domain_label_raises_naming_entry_time, test_window_aggregate_pools_across_symbols, test_walkforward_write_is_byte_deterministic_and_sort_insensitive, test_gate_refusal_exit_1_with_actionable_message, test_mixed_offset_bars_refused, test_zero_candidate_run_exits_0_with_empty_artifacts, test_full_happy_path_end_to_end. Live CLI smoke: `python -m ai_trading.backtest --help` exit 0, missing-config exit 2. ROADMAP updated: phase 03 3/3 plans Complete.
