---
phase: 01-data-foundation
verified: 2026-08-30T15:25:00Z
status: passed
score: 18/18 must-haves verified
behavior_unverified: 0
overrides_applied: 0
human_verification:
  - test: "Phase-gate approval (01-03 Task 4, checkpoint:human-verify gate=blocking — explicitly AWAITING HUMAN APPROVAL per 01-03-SUMMARY): review the 9-combo history report (stored vs available depth, terminal_maxbars=250000 provenance, weekend gap classifications), the live demonstrations (102-test suite green with terminal up, +8-then-0 idempotent restarts, fail-loud demos re-confirmed by the verifier on 2026-08-30), against ROADMAP Phase 1 success criteria 1-4, and reply 'approved' or describe issues."
    expected: "Human explicitly approves the phase gate; Phase 1 closes and Phase 2 may start."
    why_human: "The plan's blocking gate requires explicit human sign-off; report plausibility (broker depth, gap classifications) and gate approval are trust decisions that cannot be verified programmatically. Approval is recorded as pending in the plan's own SUMMARY."
    result: "RESOLVED 2026-08-30 — user replied 'approved — close Phase 1' via the orchestrator checkpoint flow (recorded in 01-03-SUMMARY.md Phase Gate Status)."
  - test: "Stored-history depth decision (flagged in 01-03-SUMMARY phase-gate pending items): decide whether 501 stored bars/combo suffice for Phase 2/3 or whether to deepen to the 90-day initial window via a human-approved purge of data/ + restart backfill under the confirmed +3 offset."
    expected: "A recorded human decision; either accept 501 bars/combo (terminal-available depth of 250k/172k/43k per combo is persisted for later) or perform the sanctioned purge-and-refetch."
    why_human: "Discretionary product decision about data depth vs backfill cost, explicitly deferred to the human at the phase gate; no automated check can make it."
    result: "RESOLVED 2026-08-30 — user accepted 501 bars/combo as-is ('approved — close Phase 1 (Recommended)'); terminal-available depth remains persisted in history_bounds; deepening can be sanctioned later via purge + restart backfill."
---

# Phase 1: Data Foundation — Verification Report

**Phase Goal:** A reliable, UTC-normalized OHLC store fed from the local MT5 terminal for all 9 symbol/timeframe combinations, with health checks and known history bounds
**Verified:** 2026-08-30T15:25:00Z
**Status:** passed (all 18 must-haves verified; both human items RESOLVED 2026-08-30 via the orchestrator checkpoint flow — see human_verification results and 01-03-SUMMARY.md "Phase Gate Status: APPROVED")
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

Merged must-haves: 4 ROADMAP success criteria (contract) + plan-level truths from all three PLAN frontmatters (deduplicated; plan truths that restate an SC keep the ROADMAP wording).

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | **SC1 (DATA-01):** Collector connects to the running MT5 terminal, verifies all three symbols selectable, fails loudly with an actionable message when the terminal is closed/logged out | ✓ VERIFIED | `connect_and_verify` implements the full 6-step sequence (collector.py:52-117); `test_health_check.py` failure matrix incl. both-servers-on-mismatch + credential scrub all pass; live `test_connect_and_verify_live` passed in the verifier's 102/102 run; fail-loud re-demonstrated live by the verifier: nonexistent path → exit 2 `terminal_path does not exist`, existing non-terminal path → exit 1 `MT5 initialize failed [-10003: IPC initialize failed...]` naming the path + remedy |
| 2 | **SC2 (DATA-02/03):** Closed M15/H1/H4 bars for EURUSD, GBPUSD, USDJPY stored in Parquet with UTC-normalized timestamps and raw server time preserved | ✓ VERIFIED | 9 Parquet files on disk, 4509 rows total; verifier inspected every file: `time − time_utc == 03:00:00` uniformly on EVERY row, COLUMNS order correct, 0 forming-bar violations; `test_offset_three_maps_server_wall_to_true_utc` + `test_fetch_uses_start_pos_1_exactly` pass (start_pos literally 1, collector.py:134-136) |
| 3 | **SC3 (DATA-04):** Restarting the collector backfills gaps idempotently (no duplicate bars, no silent gaps) | ✓ VERIFIED | Named tests exist and passed in the verifier's full run: `test_checkpoint_restart_backfills_exactly_missing_tail`, `test_backfill_range_restores_injected_mid_history_gap`, `test_crash_between_write_and_checkpoint_converges`, `test_second_consecutive_backfill_adds_zero_rows`; verifier ran `collector --once` live just now: 9 combos backfill added 0 rows, poll cycle 0 new bars, exit 0; stored data: 0 duplicate bar-open times, all files sorted, checkpoint == file max time_utc for all 9 combos |
| 4 | **SC4 (DATA-05):** A history-availability report per symbol/timeframe is persisted and queryable | ✓ VERIFIED | SQLite `history_bounds`: 9 rows (one per combo) with discovered available depth (M15: 250,000 bars back to 2016; H1: ~172k to 1996-09-08; H4: ~43.7k to 1996-09-08) + `terminal_maxbars=250000` provenance + `fetched_at`; 63 `bar_gaps` rows; `test_generate_report_persists_and_get_report_reads_without_client` passes; verifier ran `uv run python -m ai_trading.history_report` (no `--discover`) → exit 0, prints all 9 combos with stored AND available depth + weekend classifications |
| 5 | Unit suite green with NO terminal (addopts excludes mt5 by default) | ✓ VERIFIED | pyproject.toml:21 `addopts = '-m "not mt5"'`; default collection: 99 collected / 3 deselected; suite green |
| 6 | Wave-0 smoke: `import MetaTrader5, pandas, pyarrow` on cp312 | ✓ VERIFIED | Verifier ran it live: `smoke-ok 5.0.6147` |
| 7 | Idempotent merge keyed on raw bar-open time; overlap refetch keep='last' wins; atomic tmp+os.replace, no .tmp residue | ✓ VERIFIED | bar_store.py:36-76 (dedup on `time` keep='last', sort, tmp + os.replace, tmp cleanup on failure); `test_writing_identical_frame_twice_is_idempotent`, `test_overlap_refetch_with_revised_bar_wins_keep_last`, `test_no_tmp_file_remains_after_successful_merge` pass; 0 `.tmp` files in data/bars |
| 8 | Forming-bar guard raises ValueError; backfill_range defensively trims inclusive-range forming bars before merge | ✓ VERIFIED | normalize.py:82-98 guard; collector.py:369-375 trim; `test_forming_bar_guard_raises_value_error` + `test_forming_bar_trimmed_before_merge_not_by_guard` (trim, not the guard, removes the row) pass |
| 9 | None rates → MT5DataError embedding last_error (never silent skip); None+(-4) retried, other codes raise immediately, exhaustion raises stabilization error | ✓ VERIFIED | collector.py:137-143, 300-319; `test_none_with_minus4_is_retried_not_raised`, `test_none_with_other_code_raises_immediately`, `test_rounds_exhausted_raises_stabilization_error` pass |
| 10 | run_poll_cycle stores only rows newer than the SQLite checkpoint, writes Parquet BEFORE the checkpoint, second identical cycle stores 0 | ✓ VERIFIED | collector.py:181-194 (filter on time_utc > checkpoint → merge_and_write at 189 → update_checkpoint at 191); `test_poll_cycle_checkpoint_filter_update_and_idempotency` + `test_poll_cycle_writes_parquet_before_checkpoint` pass |
| 11 | config.local.toml carries the empirically validated offset (broker_offset_hours=3, validated_at=2026-08-30T20:23:34Z); purge-and-refetch condition not triggered (confirmed offset == placeholder); no stale-offset bars on disk | ✓ VERIFIED | Verifier read config.local.toml directly (3 + non-empty validated_at + DST caveat comments); uniform 3h offset on every stored row proves no stale-offset bars; the purge branch was correctly skipped since confirmed == configured |
| 12 | No error message or log ever contains initialize credential values | ✓ VERIFIED | mt5_client.initialize accepts no credential parameters at all; `test_credentials_never_appear_in_raised_messages` + `test_initialize_exposes_no_credential_parameters` pass; no login/password in any config file |
| 13 | discover_history_bounds stops at persistent None/-4 / zero-new-rows / 30y bound and records first_bar_utc, last_bar_utc, bar_count, terminal_maxbars, fetched_at | ✓ VERIFIED | history_report.py:66-136; `test_discovery_stops_at_persistent_none_minus4_and_records_maxbars` + `test_discovery_accumulates_and_dedups_across_windows` pass; live persisted rows carry all five fields incl. maxbars=250000 |
| 14 | generate_report persists DISCOVERED (terminal-available) depth on first generation or --discover, never clobbers existing rows; get_report reads back with NO MT5 client | ✓ VERIFIED | history_report.py:210-341 upsert policy; `test_first_generation_prefers_discovered_depth_over_store_bounds`, `test_plain_run_does_not_rediscover_or_clobber_persisted_row`, `test_discover_flag_forces_rediscovery_and_refreshes_row`, `test_discovery_yielding_nothing_falls_back_to_store_row` pass; persisted available_count (250k/172k/43k) ≠ stored_count (501) proves available depth, not store, is persisted |
| 15 | Gap detection finds aligned-timeframe holes in [first_bar, last_bar]; weekend-sized holes classified, never raised; non-midnight H4 lattice handled | ✓ VERIFIED | compute_gaps anchored at observed min (history_report.py:144-178); `test_compute_gaps_finds_injected_missing_slots_exactly`, `test_weekend_hole_classified_without_raising`, `test_compute_gaps_on_non_midnight_anchored_h4_lattice` pass; live report: 1/4/16 weekend gaps per symbol (M15/H1/H4), 0 "review" noise, never raised |
| 16 | rederive_time_utc changes only time_utc and leaves the raw time column byte-identical | ✓ VERIFIED | normalize.py:66-79 (recomputes from raw, returns copy); `test_rederive_matches_fresh_normalize_and_preserves_raw`, `test_offset_two_vs_three_shifts_utc_by_exactly_one_hour`, `test_dst_transition_flags_misaligned_rows_and_rederivation_fixes_them` pass |
| 17 | Meta store is WAL-mode with transactional checkpoints/bounds/gaps (only restart state) | ✓ VERIFIED | meta_store.py DDL + parameterized UPSERTs; `test_connect_enables_wal_and_creates_tables`, `test_checkpoint_roundtrip_and_single_row_per_key`, `test_upsert_gaps_twice_same_key_no_duplicates` pass |
| 18 | Full suite `uv run pytest -q -m "unit or mt5"` green with the terminal up, including the mt5-marked live tests | ✓ VERIFIED | Verifier ran it in its own process: **102 passed in 2.45s** (99 unit + 3 live integration tests executed, not skipped — 99+3=102 arithmetic confirms live execution) |

**Score:** 18/18 truths verified (0 present, behavior-unverified)

**Behavioral evidence note:** Every behavior-dependent truth above (state transitions: write-then-checkpoint ordering, retry loops, idempotent convergence, discovery termination, offset re-derivation) is exercised by a named pre-existing test. Existence proven by `pytest --collect-only` enumeration; pass status proven by the single sanctioned full-suite run (102/102 — pytest fails the run on any single failure, so all named tests passed), supplemented by four fresh live demonstrations run by the verifier itself (fail-loud ×2, report queryability, zero-row idempotent restart).

### Required Artifacts

| Artifact | Expected | Status | Details |
| -------- | -------- | ------ | ------- |
| `pyproject.toml` | Pinned deps, pytest markers unit/mt5 with mt5-excluding addopts, ruff config | ✓ VERIFIED | metatrader5==5.0.6147, pandas>=3.0,<4, pyarrow; markers + addopts + ruff E/F/I/UP/B present |
| `uv.lock` / `.python-version` / `.gitignore` | Lock committed; data/ + config.local.toml ignored | ✓ VERIFIED | `git ls-files uv.lock` → tracked; config.local.toml & data/ untracked; .gitignore has both entries |
| `config.toml` / `config.local.toml` | Committed defaults w/o secrets; local overrides w/ validated offset | ✓ VERIFIED | No credential fields anywhere; local carries terminal_path, ICMarketsSC-Demo, offset 3, validated_at |
| `src/ai_trading/config.py` | load_config + frozen 15-field Config, fail-fast validation | ✓ VERIFIED | 160 lines; all validation rules with named-field ValueErrors |
| `src/ai_trading/normalize.py` | Pure time math, zero MetaTrader5 import | ✓ VERIFIED | grep: no MT5 import; COLUMNS/TIMEFRAME_MINUTES/rates_to_dataframe/floor_to_timeframe/assert_closed_bars/rederive_time_utc |
| `src/ai_trading/stores/bar_store.py` | Single Parquet write path | ✓ VERIFIED | bar_path/read_bars/merge_and_write (atomic, idempotent, guarded) |
| `src/ai_trading/stores/meta_store.py` | WAL SQLite, 3 tables, UPSERT helpers | ✓ VERIFIED | DDL + connect/update_checkpoint/get_checkpoint/upsert_history_bounds/get_history_bounds/upsert_gaps/get_gaps |
| `src/ai_trading/mt5_client.py` | ONLY MetaTrader5 import site, error taxonomy | ✓ VERIFIED | grep confirms exactly 1 import site in src/; constants −6/−4/−8; MT5ConnectionError/MT5DataError |
| `src/ai_trading/collector.py` | Health check, closed-bar poll, offset validation, retry-until-stable backfill, CLI | ✓ VERIFIED | All symbols present incl. to_server_wall; `--once`/`--config`; exit 2/1 fail-loud paths |
| `src/ai_trading/history_report.py` | Discovery, gaps, classification, persistence, queryability, CLI | ✓ VERIFIED | All symbols present; `--discover`; terminal-free when rows persisted |
| `tests/conftest.py` | make_bars + FakeMT5Client with recording + deques | ✓ VERIFIED | 251 lines; both factories present; untouched by 01-03 as planned |
| `tests/unit/*` (8 modules) + `tests/integration/test_live_collect.py` | Unit coverage + mt5-marked live tests | ✓ VERIFIED | 99 unit + 3 mt5 tests collected; all pass |
| `data/bars/*.parquet` × 9 + `data/meta/meta.sqlite` | Runtime evidence of live collection | ✓ VERIFIED | 4509 bars; 9 checkpoints; 9 history_bounds rows; 63 gap rows |

### Key Link Verification

| From | To | Via | Status | Details |
| ---- | --- | --- | ------ | ------- |
| collector.connect_and_verify | mt5_client wrapper functions | injected `client` param (module default / FakeMT5Client) | ✓ WIRED | collector.py:52; fake exercises every path in tests; live path uses real module |
| collector.run_poll_cycle | bar_store.merge_and_write → meta_store.update_checkpoint | write-then-checkpoint ordering | ✓ WIRED | collector.py:189→191; order asserted by test_poll_cycle_writes_parquet_before_checkpoint |
| collector.backfill_range | fetch_range_until_stable → merge_and_write → update_checkpoint | checkpoint-only restart state | ✓ WIRED | collector.py:352-388; convergence tests pass |
| load_config / broker_offset_hours | normalize.rates_to_dataframe | offset as the ONLY UTC-math source | ✓ WIRED | collector.py:144, 367 pass cfg.broker_offset_hours; config is the sole source (normalize has no other offset input) |
| history_report.generate_report | meta_store.upsert_history_bounds / upsert_gaps | persisted report state | ✓ WIRED | history_report.py:255, 268, 284; get_report reads back with no client |
| collector.fetch_closed_bars | copy_rates_from_pos start_pos=1 | forming-bar safety root | ✓ WIRED | collector.py:134-136 literal 1; asserted by test_fetch_uses_start_pos_1_exactly |
| MetaTrader5 package | codebase | single import site | ✓ WIRED | grep: only src/ai_trading/mt5_client.py:23 |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
| -------- | ------------- | ------ | ------------------ | ------ |
| data/bars/*.parquet | OHLC rows | live MT5 terminal via collector | Yes — 4509 real IC Markets bars, uniform 3h offset, H4 anchored on the 21:00-UTC server-midnight lattice | ✓ FLOWING |
| history_bounds rows | available depth | live terminal walk-back discovery | Yes — 250k/172k/43k counts back to 2016/1996, maxbars=250000 | ✓ FLOWING |
| get_report CLI output | persisted rows + Parquet | SQLite + data/bars | Yes — real values printed for all 9 combos | ✓ FLOWING |

No hollow artifacts: nothing renders hardcoded/empty data.

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
| -------- | ------- | ------ | ------ |
| Full suite incl. live tests, terminal up | `uv run pytest -q -m "unit or mt5"` | 102 passed in 2.45s | ✓ PASS |
| Fail-loud: nonexistent terminal path | `collector --once --config <tmp config>` | exit 2, `terminal_path does not exist: 'Z:\nonexistent\terminal64.exe'` | ✓ PASS |
| Fail-loud: existing non-terminal path | `collector --once --config <tmp config>` | exit 1, `MT5 initialize failed [-10003: IPC initialize failed...]` + remedy naming the path | ✓ PASS |
| Report queryable without terminal discovery | `uv run python -m ai_trading.history_report` | exit 0; all 9 combos, stored + available depth, maxbars, weekend classifications | ✓ PASS |
| Live restart idempotency (fresh, verifier-run) | `uv run python -m ai_trading.collector --once` | backfill: 0 rows added on all 9 combos; poll: 0 new bars; exit 0 | ✓ PASS |
| Wave-0 smoke | `uv run python -c "import MetaTrader5, pandas, pyarrow; ..."` | `smoke-ok 5.0.6147` | ✓ PASS |
| Lint gate | `uv run ruff check .` | All checks passed! | ✓ PASS |
| Stored-data invariants (read-only script) | offset uniformity, duplicates, sort order, checkpoint==max, forming-bar check | all clean across 9 files / 4509 rows | ✓ PASS |

### Probe Execution

No conventional `scripts/*/tests/probe-*.sh` probes exist and none are declared in the plans; probe execution N/A. The live integration tests behind the mt5 marker serve as the phase's live probe and were executed by the verifier (see spot-checks).

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
| ----------- | ---------- | ----------- | ------ | -------- |
| DATA-01 | 01-02 | Connects to local MT5 terminal and verifies health at startup | ✓ SATISFIED | Truth 1 |
| DATA-02 | 01-02 | Collects closed-bar OHLC for 3 symbols × M15/H1/H4 | ✓ SATISFIED | Truth 2 (4509 real bars) |
| DATA-03 | 01-01, 01-02, 01-03 | UTC-normalized timestamps; broker offset as validated config | ✓ SATISFIED | Truths 2, 11, 16 (offset 3 validated, persisted, raw time preserved) |
| DATA-04 | 01-01, 01-03 | Incremental updates with gap backfill, idempotent across restarts | ✓ SATISFIED | Truths 3, 7, 9, 10, 17 |
| DATA-05 | 01-03 | Reports available history depth per symbol/timeframe, persisted for backtest range validation | ✓ SATISFIED | Truths 4, 13, 14, 15 |

**Orphaned requirements:** none — REQUIREMENTS.md maps exactly DATA-01..05 to Phase 1, and the union of the three plans' `requirements` frontmatter is exactly {DATA-01, DATA-02, DATA-03, DATA-04, DATA-05}. All five marked Complete in REQUIREMENTS.md, consistent with evidence.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
| ---- | ---- | ------- | -------- | ------ |
| src/ai_trading/history_report.py | 162 | `return []` (empty-DataFrame early return in compute_gaps) | ℹ️ Info | Documented, correct behavior for an empty store — not a stub |
| — | — | No TBD/FIXME/XXX/HACK/PLACEHOLDER markers in any src or test file | — | Clean |
| — | — | No *.tmp residue in data/bars; no debt markers; no console-log-only implementations | — | Clean |

### Human Verification Required

### 1. Phase-gate approval (01-03 Task 4 — blocking checkpoint, pending)

**Test:** Review the history report output for all 9 combos (stored vs available depth, `terminal_maxbars=250000` provenance, weekend gap classifications), the live demonstrations (full suite green with terminal up; idempotent restarts; fail-loud paths — all re-confirmed independently by the verifier on 2026-08-30), against ROADMAP Phase 1 success criteria 1–4. Reply "approved" or describe issues.
**Expected:** Explicit human approval of the phase gate; Phase 1 closes and Phase 2 (SMC Detection) may start.
**Why human:** The plan's `checkpoint:human-verify gate="blocking"` requires explicit sign-off; 01-03-SUMMARY itself records "Phase Gate Status: AWAITING HUMAN APPROVAL". Report plausibility (broker history depth, gap classifications) and gate approval are trust decisions, not programmatically checkable.

### 2. Stored-history depth decision (flagged in 01-03-SUMMARY as pending gate item)

**Test:** Decide whether 501 stored bars per combo suffice for Phase 2/3, or whether to deepen stored history to the 90-day initial window via the sanctioned mechanism (human-approved purge of `data/` + restart backfill under the confirmed +3 offset).
**Expected:** A recorded decision; terminal-available depth (250k/172k/43k per combo) is already persisted either way, so Phase 3 range validation is unblocked in both cases.
**Why human:** Discretionary trade-off between storage depth and backfill cost, explicitly reserved to the human at the gate.

## Gaps Summary

No gaps. Every observable truth, artifact, and key link verified — most with fresh, verifier-executed live evidence rather than SUMMARY claims: the full 102-test suite (including the 3 live MT5 integration tests) was run in the verifier's own process and passed; the fail-loud paths, report queryability, and zero-row idempotent restart were each re-demonstrated live; the 4509 stored bars were inspected row-level (uniform 3h offset, zero duplicates, zero forming-bar violations, checkpoints consistent); and SQLite was queried directly for the 9 history_bounds rows with terminal_maxbars provenance and 63 classified gap rows.

The phase goal — a reliable, UTC-normalized OHLC store for all 9 combinations, with health checks and known history bounds — is **achieved in the codebase**. Status is `human_needed` solely because the plan's own blocking phase-gate checkpoint (history-report review + explicit approval, plus the stored-depth decision) is recorded as pending in 01-03-SUMMARY and is harvested here per `workflow.human_verify_mode = end-of-phase`.

**Carried obligation (not a gap):** re-validate the broker offset at the US-DST transition (early November, +3 → +2 expected); `rederive_time_utc`, the timezone/DST suite, and `run_startup`'s drift advisory are the guard rails, per config.local.toml's documented caveat.

---

_Verified: 2026-08-30T15:25:00Z_
_Verifier: the agent (gsd-verifier)_
