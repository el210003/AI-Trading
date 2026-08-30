---
phase: 01-data-foundation
plan: 03
subsystem: infra
tags: [mt5, backfill, idempotency, history-report, timezone, dst, sqlite, parquet, checkpoint]

requires:
  - phase: 01-data-foundation plan 01
    provides: "load_config/Config, normalize pure time functions, bar_store.merge_and_write/read_bars/bar_path, meta_store checkpoint/bounds/gaps helpers"
  - phase: 01-data-foundation plan 02
    provides: "mt5_client adapter + error taxonomy, collector connect_and_verify/fetch_closed_bars/validate_offset/offset_drift_detected, FakeMT5Client recording + per-(symbol,timeframe) deques, live-validated UTC+3 offset"
provides:
  - "collector.fetch_range_until_stable — officially sanctioned retry-until-stable range fetch (two consecutive equal counts; None+(-4) retried, other codes raise)"
  - "collector.backfill_range/backfill_symbol_timeframe/backfill_all/run_startup — checkpoint-driven idempotent gap backfill with defensive forming-bar trim and write-then-checkpoint ordering"
  - "collector.to_server_wall — live-probed CopyRates range-time conversion (aware-UTC server-wall bounds; naive datetimes are machine-local)"
  - "history_report.discover_history_bounds/compute_gaps/classify_gap/generate_report/get_report/print_report/main — persisted, terminal-queryable history-availability report (DATA-05)"
  - "normalize.rederive_time_utc — raw-preserving offset re-derivation primitive (A1 mitigation, T-1-11)"
  - "tests/unit/test_backfill.py (13), test_history_report.py (14), test_timezone_dst.py (6); tests/integration/test_live_collect.py (3 mt5-marked live tests, auto-skipped by default addopts)"
  - "Live evidence: Friday-tail backfill (+8 rows) then idempotent zero-row rerun; 9-combo report with discovered depth + maxbars provenance in SQLite; fail-loud demo"
affects: [phase-2-smc, phase-3-backtester, verify-work, gsd-transition]

tech-stack:
  added: []
  patterns:
    - "Retry-until-stable range fetch: identical request per round, stability = two consecutive equal counts; None+NO_HISTORY(-4) is a retry signal, never a crash"
    - "CopyRates range bounds as aware-UTC server-wall datetimes (naive datetime args convert via the MACHINE-LOCAL zone — live-probed trap)"
    - "Checkpoint-driven restart: SQLite checkpoint is the only restart state; overlap refetches re-advance the checkpoint (crash-between-write-and-checkpoint convergence)"
    - "Discovery walk-back in narrow 1-year windows with a zero-new-rows boundary signal (pre-history requests clamp to the first bar; spans wider than maxbars fail with -2)"
    - "Gap grid anchored at the observed minimum bar open (broker lattices need not be midnight-UTC anchored)"
    - "Upsert-and-replace gap snapshots per generation (no stale rows for closed gaps); available depth never clobbered by store bounds"

key-files:
  created:
    - src/ai_trading/history_report.py
    - tests/unit/test_backfill.py
    - tests/unit/test_history_report.py
    - tests/unit/test_timezone_dst.py
    - tests/integration/__init__.py
    - tests/integration/test_live_collect.py
  modified:
    - src/ai_trading/collector.py
    - src/ai_trading/normalize.py
    - .planning/REQUIREMENTS.md  # DATA-05 -> complete (via requirements.mark-complete)

key-decisions:
  - "CopyRates range bounds are converted to aware-UTC server-wall datetimes via collector.to_server_wall — live probe proved naive datetime args are converted in the machine-LOCAL zone (China UTC+8) and the terminal compares request epochs against server-wall bar stamps, inclusive"
  - "Discovery walk uses narrow non-overlapping 1-year windows stepping backward, stopping on persistent None/-4, zero-new-rows (live probe: pre-history windows clamp to the first bar instead of returning None), or the 30-year safety bound (raised from the plan's example 15y after probing showed H1/H4 depth to the 1999 era; spans wider than maxbars fail with -2 Invalid params)"
  - "compute_gaps anchors the expected grid at min time_utc, not midnight-UTC floor — IC Markets H4 opens on the 21:00-UTC server-midnight lattice, so a midnight-anchored grid misclassified every real H4 bar (caught and fixed during the live --discover run)"
  - "generate_report replaces each combo's gap snapshot per generation and upserts DISCOVERED bounds only when discovery ran; existing rows are never clobbered with store bounds; store-derived fallback only when no row exists and discovery yields nothing"
  - "Boundary-alignment test encodes the UTC grid as the server grid shifted by the validated offset (H4 anchored at the 21:00-UTC daily close corroborated live in 01-02) — the plan's literal minutes-since-midnight mod TF == 0 formula cannot hold for offset-shifted H4"
  - "DST-transition test demonstrates that stale-offset misalignment is flagged by expected-open checks yet invisible to naive grid membership — the documented reason the offset must be re-validated at startup and corrected via rederive_time_utc"
  - "requirements DATA-03/DATA-04/DATA-05 now complete in REQUIREMENTS.md (DATA-05 marked via gsd-tools requirements.mark-complete after live verification)"

requirements-completed: [DATA-03, DATA-04, DATA-05]

coverage:
  - id: D1
    description: "Retry-until-stable fetch: grow-then-stable returns only after two equal counts; identical request args every round; None+-4 retried, other codes raise immediately; rounds exhausted raises stabilization error"
    requirement: "DATA-04"
    verification:
      - kind: unit
        ref: "tests/unit/test_backfill.py#test_returns_only_after_two_consecutive_equal_counts"
        status: pass
      - kind: unit
        ref: "tests/unit/test_backfill.py#test_issues_identical_request_arguments_every_round"
        status: pass
      - kind: unit
        ref: "tests/unit/test_backfill.py#test_none_with_minus4_is_retried_not_raised"
        status: pass
      - kind: unit
        ref: "tests/unit/test_backfill.py#test_none_with_other_code_raises_immediately"
        status: pass
      - kind: unit
        ref: "tests/unit/test_backfill.py#test_rounds_exhausted_raises_stabilization_error"
        status: pass
    human_judgment: false
  - id: D2
    description: "Checkpoint-driven idempotent backfill: restart fills exactly the missing tail; injected mid-history gap fully restored; crash-between-write-and-checkpoint converges (checkpoint re-advances on overlap refetch); second run adds zero rows"
    requirement: "DATA-04"
    verification:
      - kind: unit
        ref: "tests/unit/test_backfill.py#test_checkpoint_restart_backfills_exactly_missing_tail"
        status: pass
      - kind: unit
        ref: "tests/unit/test_backfill.py#test_backfill_range_restores_injected_mid_history_gap"
        status: pass
      - kind: unit
        ref: "tests/unit/test_backfill.py#test_crash_between_write_and_checkpoint_converges"
        status: pass
      - kind: unit
        ref: "tests/unit/test_backfill.py#test_second_consecutive_backfill_adds_zero_rows"
        status: pass
      - kind: other
        ref: "live: two consecutive collector --once runs (first +8 Friday-tail rows, second all zeros)"
        status: pass
    human_judgment: false
  - id: D3
    description: "Forming-bar defensive trim: a scripted inclusive-range response containing a bar at the current timeframe floor is trimmed before merge; control proves merge_and_write's guard would have rejected it"
    requirement: "DATA-04"
    verification:
      - kind: unit
        ref: "tests/unit/test_backfill.py#test_forming_bar_trimmed_before_merge_not_by_guard"
        status: pass
    human_judgment: false
  - id: D4
    description: "History discovery: walk-back terminates at persistent None/-4 or zero-new-rows, accumulates deduplicated bounds, records terminal_maxbars provenance; generate_report persists discovered bounds on first generation and --discover, never clobbers existing rows, falls back to store bounds when discovery yields nothing"
    requirement: "DATA-05"
    verification:
      - kind: unit
        ref: "tests/unit/test_history_report.py#test_discovery_stops_at_persistent_none_minus4_and_records_maxbars"
        status: pass
      - kind: unit
        ref: "tests/unit/test_history_report.py#test_discovery_accumulates_and_dedups_across_windows"
        status: pass
      - kind: unit
        ref: "tests/unit/test_history_report.py#test_first_generation_prefers_discovered_depth_over_store_bounds"
        status: pass
      - kind: unit
        ref: "tests/unit/test_history_report.py#test_plain_run_does_not_rediscover_or_clobber_persisted_row"
        status: pass
      - kind: unit
        ref: "tests/unit/test_history_report.py#test_discover_flag_forces_rediscovery_and_refreshes_row"
        status: pass
      - kind: unit
        ref: "tests/unit/test_history_report.py#test_empty_store_handled_and_discovery_still_provides_available"
        status: pass
      - kind: unit
        ref: "tests/unit/test_history_report.py#test_discovery_yielding_nothing_falls_back_to_store_row"
        status: pass
      - kind: other
        ref: "live: uv run python -m ai_trading.history_report --discover -> all 9 combos with stored+available depth and terminal_maxbars=250000 persisted"
        status: pass
    human_judgment: false
  - id: D5
    description: "Gap detection + classification: injected missing slots found with exact aligned boundaries; weekend hole (~48h) classified without raising; non-midnight-anchored H4 lattice regression; persisted gap snapshot replaces per generation; get_report reconstructs with no MT5 client"
    requirement: "DATA-05"
    verification:
      - kind: unit
        ref: "tests/unit/test_history_report.py#test_compute_gaps_finds_injected_missing_slots_exactly"
        status: pass
      - kind: unit
        ref: "tests/unit/test_history_report.py#test_weekend_hole_classified_without_raising"
        status: pass
      - kind: unit
        ref: "tests/unit/test_history_report.py#test_compute_gaps_on_non_midnight_anchored_h4_lattice"
        status: pass
      - kind: unit
        ref: "tests/unit/test_history_report.py#test_generate_report_persists_and_get_report_reads_without_client"
        status: pass
      - kind: other
        ref: "live: uv run python -m ai_trading.history_report (no terminal needed) prints persisted rows; weekend gaps classified, zero 'review' fatigue"
        status: pass
    human_judgment: false
  - id: D6
    description: "Timezone/DST contract locked: offset re-derivation (2 vs 3 differ exactly 1h, raw identical), rederive==fresh normalize with raw byte-identical, boundary alignment per TF on the offset-shifted UTC grid, DST-transition misalignment flagged (and invisible to naive grid checks), weekend gaps reported, drift predicate"
    requirement: "DATA-03"
    verification:
      - kind: unit
        ref: "tests/unit/test_timezone_dst.py#test_offset_two_vs_three_shifts_utc_by_exactly_one_hour"
        status: pass
      - kind: unit
        ref: "tests/unit/test_timezone_dst.py#test_rederive_matches_fresh_normalize_and_preserves_raw"
        status: pass
      - kind: unit
        ref: "tests/unit/test_timezone_dst.py#test_time_utc_lands_on_boundary_grid_for_every_timeframe"
        status: pass
      - kind: unit
        ref: "tests/unit/test_timezone_dst.py#test_dst_transition_flags_misaligned_rows_and_rederivation_fixes_them"
        status: pass
      - kind: unit
        ref: "tests/unit/test_timezone_dst.py#test_weekend_gap_reported_and_classified_not_raised"
        status: pass
      - kind: unit
        ref: "tests/unit/test_timezone_dst.py#test_offset_drift_detected_flags_only_real_drift"
        status: pass
    human_judgment: false
  - id: D7
    description: "Live integration coverage behind the mt5 marker: health check, closed-bar fetch, backfill+report pass against the running terminal; auto-excluded from the default run by addopts; skip-with-actionable-message path demonstrated (bogus config -> 3 skipped, exit 0)"
    requirement: "DATA-01"
    verification:
      - kind: integration
        ref: "tests/integration/test_live_collect.py (3 tests passed with terminal up: uv run pytest -q -m 'unit or mt5' -> 102 passed)"
        status: pass
      - kind: other
        ref: "uv run pytest -q -> 99 passed, 3 deselected (mt5 excluded by default addopts)"
        status: pass
    human_judgment: false
  - id: D8
    description: "Phase gate: full suite green with terminal up, live restart idempotency x2, history report human review of all 9 combos, fail-loud demonstration (config ValueError for nonexistent path; MT5ConnectionError -10003 for existing non-terminal path; config restored and re-verified)"
    requirement: "DATA-05"
    verification:
      - kind: other
        ref: "uv run pytest -q -m 'unit or mt5' -> 102 passed (2026-08-30T14:5xZ, terminal up)"
        status: pass
      - kind: other
        ref: "collector --once x2: +8 rows then 0 rows (idempotent restart live)"
        status: pass
      - kind: other
        ref: "spot-check: all 9 parquet files offset=3h uniform, 0 forming bars, checkpoint==max time_utc"
        status: pass
    human_judgment: true
    rationale: "VALIDATION.md's phase gate requires explicit human review/approval of the report and live demonstrations before Phase 1 closes — the executor gathered and presented all evidence; approval is pending at the checkpoint return."

duration: 68min
completed: 2026-08-30
status: complete
---

# Phase 1 Plan 03: Gap Backfill + History Report + Timezone/DST Validation Summary

**Retry-until-stable checkpoint-driven backfill (DATA-04), a persisted/queryable terminal-available history report across all 9 combos (DATA-05), and the timezone/DST test suite locking the raw-time/re-derivation contract (DATA-03) — finished with a live phase-gate run: 102 tests green, +8-then-0 idempotent backfill, discovered depth to 2016 (M15)/1996 (H1/H4) with maxbars provenance, fail-loud demo, all awaiting only the human gate approval.**

## Performance

- **Duration:** 68 min
- **Started:** 2026-08-30T13:48Z
- **Completed:** 2026-08-30T14:56Z
- **Tasks:** 4 (Tasks 1–3 executed and committed; Task 4 = phase-gate checkpoint, all executor pre-work completed, human approval pending)
- **Files modified:** 9 source/test files + REQUIREMENTS.md metadata

## Accomplishments

- **DATA-04 (Task 1, `9d35811`):** `fetch_range_until_stable` implements the officially sanctioned retry-until-stable loop (identical request each round — fake-recorded args prove zero variation; two consecutive equal counts = complete; None+`-4` retried, any other code raises; exhaustion raises a stabilization error). `backfill_range` adds the checker-mandated defensive forming-bar trim (rows at/after the current timeframe floor dropped before merge — the test proves the trim, not `merge_and_write`'s guard, removed the row) and write-then-checkpoint ordering where an overlap refetch re-advances the checkpoint — the exact mechanism that converges a crash-between-write-and-checkpoint. `backfill_symbol_timeframe`/`backfill_all`/`run_startup` complete the restart path; `main()` now runs `run_startup` for both `--once` and continuous mode.
- **DATA-05 (Task 2, `14157bf`):** `history_report.py` — `discover_history_bounds` walks back in narrow 1-year windows, `compute_gaps` finds aligned-TF holes (contiguous slots merged), `classify_gap` labels weekend-vs-review without ever raising, `generate_report` persists discovered (terminal-available) bounds + gap snapshots to SQLite with the store-never-clobbers-available policy, `get_report` reconstructs everything with no MT5 client, and `main()` provides the `--config`/`--discover` CLI (terminal-free when rows are persisted).
- **DATA-03 (Task 3, `5a0273e`):** `normalize.rederive_time_utc` re-derives `time_utc` from the preserved raw server-wall column (raw byte-identical, A1 mitigation for T-1-11). `test_timezone_dst.py` locks the full contract including the DST-transition demonstration: stale-offset misalignment IS flagged by expected-open checks and is INVISIBLE to naive grid membership — why startup re-validation + re-derivation exist. Three mt5-marked live integration tests pass against the running IC Markets terminal and are auto-excluded from default runs.
- **Live phase-gate evidence (Task 4 pre-work):** full suite `uv run pytest -q -m "unit or mt5"` → **102 passed** (3 live tests executed, not skipped); two consecutive `collector --once` runs → **+8 rows** (the exact Friday-close tail across 8 combos) then **all zeros**; `history_report --discover` → all 9 combos with stored AND discovered depth, `terminal_maxbars=250000` provenance in SQLite; weekend gaps classified (0 "review" noise); fail-loud demo (nonexistent path → actionable config ValueError exit 2; existing non-terminal path → `MT5ConnectionError [-10003]` exit 1; config restored, `Test-Path` True, healthy re-run 0-new-bars); spot-checks → uniform 3h offset on every row, 0 forming bars, checkpoint==file max for all 9 combos.

## Task Commits

Each task was committed atomically:

1. **Task 1: Retry-until-stable fetch + checkpoint-driven idempotent backfill (DATA-04)** — `9d35811` (feat)
2. **Task 2: History-availability report — discovery, gaps, persistence, CLI (DATA-05)** — `14157bf` (feat)
3. **Task 3: Timezone/DST validation tests + mt5-marked live integration tests (DATA-03)** — `5a0273e` (feat)
4. **Task 4: Phase gate — full suite green + live integration run + history report review** — checkpoint task, no commit; all executor pre-work completed (evidence above); **human approval pending**
5. **Verification fix found during the live gate run** — `a16aa4a` (fix)

**Plan metadata:** (this docs commit + REQUIREMENTS.md DATA-05 completion)

## Files Created/Modified

- `src/ai_trading/collector.py` — fetch_range_until_stable, to_server_wall, backfill_range (defensive trim + write-then-checkpoint), backfill_symbol_timeframe, backfill_all, run_startup; main() rewired
- `src/ai_trading/history_report.py` — discover_history_bounds, compute_gaps, classify_gap, generate_report, get_report, print_report, main() CLI
- `src/ai_trading/normalize.py` — rederive_time_utc (pure, raw-preserving)
- `tests/unit/test_backfill.py` (13 tests), `tests/unit/test_history_report.py` (14), `tests/unit/test_timezone_dst.py` (6)
- `tests/integration/__init__.py`, `tests/integration/test_live_collect.py` (3 mt5-marked live tests)
- `.planning/REQUIREMENTS.md` — DATA-05 marked complete
- `tests/conftest.py` — NOT modified: FakeMT5Client's recording + per-(symbol,timeframe) deque hooks from 01-02 sufficed exactly as built

## Decisions Made

- **CopyRates range-time conversion (`to_server_wall`):** live probes (clean bar-aligned windows inside Friday) proved the terminal compares request epochs against server-wall bar stamps and the package converts naive datetimes in the machine-LOCAL zone (China UTC+8 here). All range bounds are therefore passed as aware-UTC datetimes carrying the server-wall value (true UTC + validated offset) — machine-independent and exact.
- **Discovery walk shape:** narrow non-overlapping 1-year windows instead of the plan's ever-widening [chunk_start → now] ranges, because (a) spans wider than maxbars fail with error **-2 Invalid params** (8y M15 > 250k cap, live-probed) and (b) pre-history windows do not return None/-4 — they clamp to the very first available bar. The zero-new-rows stop signal (added to persistent None/-4) handles the clamp and the cap; the bound was raised 15y → 30y after probes showed H1/H4 depth reaching the 1999 era.
- **Gap grid anchoring:** anchored at the observed minimum bar open rather than midnight-UTC floor — the first live `--discover` run exposed that IC Markets H4 opens sit on the 21:00-UTC server-midnight lattice, so a midnight-anchored grid misclassified every real H4 bar into one giant fake "weekend" gap. Fixed + regression-tested + re-verified live (16 properly weekend-sized H4 holes per combo).
- **Gap snapshot semantics:** each generation REPLACES the combo's persisted gap rows before upserting, so closed gaps never linger as stale false positives for Phase 3's range validation.
- **Boundary-alignment test formula:** encodes the UTC grid as the server grid shifted by the validated offset (`m ≡ (−offset·60) mod TF`), matching the live-corroborated 21:00-UTC H4 anchor; the plan's literal `mod TF == 0` formula cannot hold for offset-shifted H4 bars.
- **Fail-loud demo interpretation:** a *nonexistent* terminal_path is rejected earlier by design (config validation, exit 2, actionable message); the MT5ConnectionError path was demonstrated with an existing-but-not-a-terminal file (`-10003 IPC initialize failed`, exit 1). Both shown; config restored and re-verified.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] compute_gaps midnight-anchored grid misclassified all H4 bars**
- **Found during:** Task 4 (live `--discover` run — H4 rows showed one ~115-day fake "weekend" gap)
- **Issue:** expected grid was built from `floor(min time_utc, tf)` to midnight UTC; IC Markets H4 bars open on the 21:00-UTC server-midnight lattice, so every grid slot was "missing"
- **Fix:** anchor the expected grid at the observed minimum bar open (bars are TF-aligned by construction); added the H4-lattice regression test
- **Files modified:** src/ai_trading/history_report.py, tests/unit/test_history_report.py
- **Verification:** live re-run — 16 properly weekend-sized H4 holes per combo; unit tests green
- **Committed in:** a16aa4a

**2. [Rule 2 - Missing Critical] Discovery walk robustness (narrow windows, zero-new-rows stop, 30y bound)**
- **Found during:** Task 2 implementation + live probes (pre-implementation probes against the running terminal)
- **Issue:** the plan's [chunk_start → now] widening ranges fail with -2 Invalid params once a span exceeds maxbars (live-probed at ~8y M15), and pre-history windows clamp to the first bar instead of returning None/-4, so a None-only stop signal would never fire; the 15y example bound truncated H1/H4 discovery at 2011 despite 1999-era depth
- **Fix:** narrow 1-year non-overlapping windows; zero-new-rows boundary signal; `_MAX_WALK_YEARS = 30`
- **Files modified:** src/ai_trading/history_report.py, tests/unit/test_history_report.py
- **Verification:** unit tests for both stop signals; live discovery reached 2016 (M15, ≈maxbars cap) and 1996 (H1/H4, 30y walk bound)
- **Committed in:** 14157bf (windows/stop signals), a16aa4a (30y bound)

**3. [Rule 2 - Missing Critical] CopyRates range-bound conversion helper (to_server_wall)**
- **Found during:** Task 1 (pre-implementation live probes of range-time semantics)
- **Issue:** the plan's sketches pass datetimes to copy_rates_range without specifying representation; live probes proved naive datetimes convert in the machine-LOCAL zone (UTC+8 here) and the terminal filters on server-wall epochs — naive true-UTC bounds would silently shift every request window
- **Fix:** `collector.to_server_wall` converts true-UTC bounds to aware-UTC server-wall datetimes; used by backfill_range and discover_history_bounds; semantics documented in the docstring
- **Files modified:** src/ai_trading/collector.py
- **Verification:** probe table (7 datetime forms) reconciled exactly; live backfill picked up precisely the expected Friday-tail bars
- **Committed in:** 9d35811

**4. [Rule 1 - Test design] Boundary-alignment formula corrected for the broker offset**
- **Found during:** Task 3 (test failed against the plan's literal formula)
- **Issue:** `minutes-since-midnight mod TF == 0` cannot hold for H4 time_utc under a +3 offset — the broker's H4 grid anchors at 21:00 UTC (01-02's live {1,5,9,13,17,21}-hour evidence)
- **Fix:** assert `m ≡ (−offset·60) (mod TF)` with the derivation documented in the test docstring
- **Files modified:** tests/unit/test_timezone_dst.py
- **Verification:** all 6 timezone/DST tests green
- **Committed in:** 5a0273e

---

**Total deviations:** 4 auto-fixed (2 live-verified correctness bugs/robustness gaps in new code, 1 correctness-critical helper, 1 test-design correction). **Impact on plan:** all fixes were forced by live-terminal evidence or the project's own 01-02 live data; the plan's specified behaviors (retry-until-stable, checkpoint restart, discovery persistence, gap reporting, DST re-derivation) are all implemented as specified. No scope creep.

## Authentication Gates

None — the MT5 terminal was already running and logged in (IC MarketsSC-Demo) from plan 01-02; no credential handling occurred.

## Issues Encountered

- **Weekend execution window:** markets closed all session, so the live runs could not demonstrate new closed bars from ticks; compensated by (a) the Friday-tail backfill (+8 rows) proving gap-fill against real terminal data and (b) the zero-row second run proving restart idempotency. The weekend `validate_offset` sample was poison (−39, ~39h-old Friday tick) — flagged by the drift advisory and correctly NOT persisted (documented weekend rule from 01-02).
- **H1/H4 `available_first` is walk-bound-limited at 1996-09-08** (the 30-year safety bound), not a terminal boundary — the broker serves at least 30 years of H1/H4. Noted for Phase 3: practical backtest depth is bounded by `terminal_maxbars` (250,000) per single fetch anyway.
- **Terminal `maxbars` reads 250,000** (not "Unlimited") — M15 available depth ≈ 250k bars ≈ 10 years, which the cap enforces. Above `min_maxbars` (100k) so no health warning fires; surfaced here for the human's phase-gate review.
- **Em-dash mojibake** in Windows console log output (known cosmetic issue from 01-02; message content unaffected).
- Untracked `.planning/research/.cache/*.json` files predate this plan (planning-session residue) — left untouched.

## Phase Gate Status: APPROVED (2026-08-30)

Human approved via orchestrator checkpoint flow with two explicit responses:
1. Phase-gate approval: "approved -- close Phase 1" -- 9-combo history report + live demonstrations reviewed against ROADMAP SC 1-4; fail-loud, idempotency, and offset-uniformity evidence accepted.
2. Stored-history depth decision: accept 501 bars/combo as-is (option: "approved -- close Phase 1 (Recommended)"). Terminal-available depth (250k M15 / ~172k H1 / ~43.7k H4 per symbol) is persisted in history_bounds for Phase 3; deepening to the 90-day window declined for now and can be sanctioned later via purge of data/ + restart backfill.

Task 4 is `checkpoint:human-verify` (`gate="blocking"`). All executor pre-work is complete and the evidence is presented in the structured checkpoint return that accompanies this SUMMARY. Pending items for the human:

1. Review the history report output (9 combos, stored vs available depth, maxbars provenance, weekend classifications) — success criteria 1–4 of ROADMAP Phase 1.
2. Optionally decide whether to deepen stored history (currently 501 bars/combo from the poll path + Friday tails) to the full 90-day initial window — the sanctioned mechanism would be a human-approved purge of `data/` followed by a restart backfill under the confirmed +3 offset; the report's discovered depth shows the terminal serves years of history either way.
3. Reply "approved" (or describe issues) — on approval, Phase 1 execution is complete and ready for `/gsd-verify-work`.

## Security Compliance (threat register)

- **T-1-08 (mitigate):** ✅ checkpoint-driven range fetch + idempotent merge; crash-between-write-and-checkpoint and injected-gap tests prove convergence to exactly-one-row-per-open-time.
- **T-1-09 (mitigate):** ✅ terminal_maxbars recorded as mandatory provenance in every history_bounds row and surfaced in every report row; maxbars value surfaced to the human at the gate.
- **T-1-10 (accept/mitigate):** ✅ gaps persisted and classified (weekend/review), never raised; human reviews the first report at the gate.
- **T-1-11 (mitigate):** ✅ rederive_time_utc recomputes from the preserved raw column (raw-invariance unit-proven); drift warning at every startup via run_startup.
- No new network endpoints, auth paths, or trust-boundary surfaces introduced (local IPC + local files only) — no new threat flags.

## User Setup Required

None beyond the existing terminal setup (running/logged in, verified throughout this session).

## Next Phase Readiness

- **Phase 1 is functionally complete** pending the human gate approval: ROADMAP success criteria 1–4 are each backed by live evidence (fail-loud health check from 01-02; stored bars with UTC normalization + raw preservation; restart idempotency demonstrated twice live; persisted/queryable history report across 9 combos).
- **Phase 2 (SMC Detection) can start** against `bar_store.read_bars` and the canonical COLUMNS layout once the gate is approved.
- **Phase 3 consumers:** `get_report(cfg, conn)` (no client) returns per-combo stored/available bounds + classified gaps for backtest range validation.
- **Carried obligation:** re-validate the broker offset at the US-DST transition (early November, +3 → +2 expected); `rederive_time_utc` + the timezone/DST suite are the guard rails, and `run_startup`'s drift advisory will fire once live ticks resume.

## Self-Check: PASSED

- All 9 plan key-files verified present on disk (collector.py, history_report.py, normalize.py, conftest.py untouched-but-verified, 3 unit test modules, 2 integration files).
- Task commits verified in `git log`: `9d35811` (Task 1), `14157bf` (Task 2), `5a0273e` (Task 3), `a16aa4a` (live-verification fix); Task 4 is the pending human-gate checkpoint by design.
- Verification re-run on committed state: `uv run pytest -q` → 99 passed, 3 deselected; `uv run pytest -q -m "unit or mt5"` → **102 passed** (terminal up, live tests executed); `uv run ruff check .` → All checks passed.
- CLI verified: `uv run python -m ai_trading.history_report --help` exits 0 with `--config` and `--discover`.
- REQUIREMENTS.md: DATA-05 marked complete via `gsd-tools requirements.mark-complete` (DATA-01..04 were already complete).

---
*Phase: 01-data-foundation*
*Completed: 2026-08-30*
