---
phase: 03-backtesting-labeling
verified: 2026-09-02T15:31:15Z
status: passed
score: 16/16 must-haves verified
behavior_unverified: 0
overrides_applied: 0
re_verification:
  previous_status: none
  previous_score: n/a
  gaps_closed: []
  gaps_remaining: []
  regressions: []
human_verification:

  - test: "Confirm the A1 cost-asymmetry convention (plan 03-01 user_setup): read costs.py entry_fill_price/exit_fill_price and test_costs.py::test_long_short_cost_symmetry — confirm bid-side bars mean a LONG crosses the spread at ENTRY and a SHORT at EXIT (net round-trip = spread_px + 2*slip for both directions)."
    expected: "The convention matches your mental model of bid-side OHLC bars. If you model 'spread = cost per side' instead, only costs.py + its tests change (RESEARCH Open Question 2)."
    why_human: "Convention choice, not machine-verifiable — the symmetric cost MATH is unit-proven; whether the convention is the intended one is a human call (plan-declared 10-second eyeball at phase verification)."

  - test: "Confirm the D-10 SL-first intrabar tie convention (plan 03-02 coverage D8, human_judgment): read barriers.py module docstring + test_barriers.py::test_tie_sl_first_including_entry_bar — confirm SL-first on every bar (entry bar included) is the intended conservative labeling rule."
    expected: "The conservative SL-first rule matches intent (intrabar path unknowable from OHLC; no tie heuristic that flatters win rates)."
    why_human: "Convention choice per D-10; the implementation is pinned by a named test, the intent-match is a human judgment."

  - test: "Real-data demo run with the history-depth decision (plan 03-03 user_setup, Phase gate Open Question 1): stored M15 history is ~9 days, below D-21's 30-day gate. Decide ONE of: (1) deepen stored history via Phase 1 purge+backfill, (2) run with --min-history-days override + shorter --range, or (3) demo on H4-range depth. Then run: uv run python -m ai_trading.backtest --config config.toml --range last-ND --write"
    expected: "Gate refusal (exit 1, actionable remedy message, no artifacts) if run below the gate without override; a successful run (exit 0) writes data/labels/{SYMBOL}_M15.parquet, canonical_stats.json, run_manifest.json, data/reports/walkforward.parquet, walkforward_manifest.json; zero candidates is a valid exit-0 outcome with schema-correct empty artifacts."
    why_human: "Requires the running MT5 terminal / stored-data depth decision (real external service + a business call on demo depth); the engine itself is fully synthetic-tested either way."
---

# Phase 3: Backtesting & Labeling Verification Report

**Phase Goal:** A bar-by-bar replay engine that runs the identical detector pipeline over history, models costs, labels outcomes, and reports canonical + walk-forward statistics
**Verified:** 2026-09-02T15:31:15Z
**Status:** human_needed (all 16 must-haves VERIFIED; 3 plan-declared human decisions pending)
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

Merged from ROADMAP SC1–SC4 (contract) + all three PLAN must_haves frontmatter blocks (deduplicated; roadmap wording kept where plans restate).

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | SC1/BT-01: The backtester imports and calls the exact Phase 2 detector functions (detect_swings, build_zigzag, detect_pools, derive_zones, htf_context) — no separate backtest detection logic exists | ✓ VERIFIED | chain.py L20-24 imports the 5 detector exports directly; run_chain composes them (L42-52); zero detection logic in backtest/ (grep clean); vendor-purity test extended over `src/ai_trading/backtest/*.py` (test_detector_integration.py L381-391) — green in suite run |
| 2 | BT-01: Point-in-time visibility uses per-tier stamp semantics (close-time anchors for confirmed_at/created_at/activated_at; bar-time anchors for resolved_at/pierced_at/mitigated_at/invalidated_at); MTF payload consumed as-is | ✓ VERIFIED | asof.py STAMP_CLOSE/STAMP_BAR + visible_mask (L49-71); replay.py L251-271 slices every tier through visible_mask with the correct anchor; test_asof.py (12 tests) covers both anchors at boundary equality, NaT exclusion, invariants |
| 3 | BT-01/SC1: Decision-path prefix stability — replay(bars[:k]) labels equal the visible subset of replay(full) by entry_time < prefix_close_time, STRICT, check_exact=True, 1-by-1 AND chunked | ✓ VERIFIED (behavioral) | test_replay_repaint.py::test_prefix_equivalence_one_by_one + test_prefix_equivalence_chunked_appends + test_world_produces_exactly_one_expected_label (positive control) — all green in the 358-pass suite run |
| 4 | BT-02/SC2: Cost model converts spread POINTS→price via point_size (pip/10), falls back to per-symbol default when recorded spread is 0/absent (D-15), applies fixed slippage pips on BOTH fills (D-14), direction-aware (A1: long crosses spread at entry, short at exit) | ✓ VERIFIED | costs.py L74-134 (all six functions with pinned formulas); test_costs.py: D-15 fallback ×4, D-14, literal fills, test_long_short_cost_symmetry, test_raw_vs_net_delta_is_exactly_twice_slippage — green |
| 5 | BT-01: Entry candidate = sweep + mitigated PD-zone tap on M15 only (D-01/D-06), HTF bias agreement (D-02), one-at-a-time suppression (D-05), silent warmup (D-07), structural raw SL/TP (D-08/D-09/D-13), min-R:R discard at fill (D-12) | ✓ VERIFIED | candidates.py (Candidate, bias_agrees, candidate_at_bar, compute_rr — D-01..D-13 semantics implemented incl. D-09 liveness convention); replay.py D-05 held_until (L240-241), D-07 warmup (L238-239), D-12 (L287-288); test_candidates.py (19 tests), test_replay.py D-05/D-07/D-12 tests — green |
| 6 | BT-02: 12 new config knobs validate fail-fast in the frozen Config; backtest package is MT5-free | ✓ VERIFIED | config.py _REQUIRED_KEYS L47-58 (all 12), Config fields L81-94, _validate rules; config.toml backtest section L33-54; test_backtest_config.py rejection matrix; vendor-purity assertion green (no MetaTrader5 import in backtest/ — docstring prose only, which the test permits) |
| 7 | BT-03/SC3: Triple-barrier walk evaluates exactly bars [E, E+time_barrier_bars) inclusive of entry bar, checks SL before TP on EVERY bar including the entry bar (D-10), fills gap crossings at the bar's open (D-11, both directions) | ✓ VERIFIED (behavioral) | barriers.py L119-148 (gap check before high/low on every bar, SL-first branch order, no tie heuristic); named tests test_tie_sl_first_including_entry_bar, test_sl_hit_on_entry_bar, 4 gap tests both directions, test_timeout_after_exactly_96_bars (exit_idx - E + 1 == 96) — green |
| 8 | BT-03/SC3: Outcomes are exactly WIN/LOSS/TIMEOUT; TIMEOUT exits at the final window bar's close (end-of-data lens included) | ✓ VERIFIED (behavioral) | barriers.py L150-153 (window_end-1 close, last available bar when frame ends inside window); OUTCOME_* constants; test_timeout_after_exactly_96_bars + test_timeout_near_end_of_data — green |
| 9 | BT-03: Every label carries entry_time, exit_time, outcome, R_raw, R_net; all three R variants normalize by the SAME structural risk \|entry_open − sl_price\| (convention (a)); with costs > 0 a net LOSS is strictly below −1.0; per-trade delta r_net − r_raw = −2·slip_px/risk | ✓ VERIFIED (behavioral) | barriers.py L101-186 (single denominator, three variants); test_r_literals_loss pins r_raw = −1.20 / r_net = −1.30 exactly (spread 20 pt, slip 0.5 pip, risk 0.001); test_stats.py::test_cost_delta_expectancy_from_real_walk_barriers pins −0.10 exact — green |
| 10 | BT-04/SC4: Canonical stats (win rate w/ TIMEOUT excluded from denominator, PF inf/nan guards, expectancy/avg_r over ALL trades, max DD from cumulative R curve, trade count) per (symbol, timeframe) in BOTH raw and net variants with visible cost delta | ✓ VERIFIED | stats.py canonical_stats + stats_by_symbol_timeframe (groupby (symbol, timeframe) only, never global); test_stats.py: hand-computed series, guard parametrization, test_win_rate_denominator_ignores_timeouts, test_stats_by_symbol_timeframe_groups_without_leakage — green |
| 11 | BT-03/BT-04: Label/canonical artifacts written atomically (tmp + os.replace, zstd Parquet), keyed by (symbol, entry_time), byte-identical on re-runs, run metadata in a SEPARATE JSON manifest | ✓ VERIFIED | reports.py _atomic_json/_atomic_parquet (L65-91, bar_store discipline), write_labels dedup keep="last" (L125), MANIFEST_KEYS hard contract (L161-171); test_reports.py: no-.tmp-residue (success+failure), byte determinism, idempotent overwrite, manifest separation, config_hash stability — green |
| 12 | BT-05: Walk-forward windows strictly chronological: expanding train (entry_time strictly before test_start), fixed-length rolling test sliding by exactly test length, zero overlap, no shuffles | ✓ VERIFIED (behavioral) | walkforward.py build_windows (b_{k+1} = b_k + test_days, while b <= end); test_walkforward.py::test_windows_chronological_zero_overlap, test_expanding_train_strictly_before_test, test_label_at_test_start_is_test_not_train, test_no_shuffle_input_order_preserved — green |
| 13 | BT-05/D-20: Window sizes configurable in days (defaults 180/30) AND functional with small day-windows (1-2 days) | ✓ VERIFIED | test_small_windows_one_day_tests + test_small_windows_two_day_tests (10 labels / 5 days → 5 windows) — green; test_invalid_window_sizes_raise pins positivity |
| 14 | BT-05: Every label assigned exactly ONE window by entry bar time; per-window reports contain full canonical stats per (symbol, timeframe) AND an aggregate across symbols per window | ✓ VERIFIED | label_window_assignment (searchsorted, outside-domain raises naming entry_time); window_stats_table (per window_id × symbol × timeframe) + window_aggregate (groupby window_id only); test_every_label_assigned_exactly_one_window, test_window_aggregate_pools_across_symbols — green |
| 15 | BT-05/SC2: Runner CLI wires gate → load (HTF lead-in) → chain → replay → barriers → stats → walk-forward → reports; exit codes 2 (config) / 1 (runtime refusal incl. D-21 gate, mixed offsets) / 0 (success incl. zero-candidate runs) | ✓ VERIFIED (behavioral) | runner.py main/run_backtest (gate L207, offset guard L208/216-217, walk_barriers wired as resolver L225, dataclasses.replace override L356); test_runner.py 13 tests: gate refusal exit 1 with actionable message, gate override, mixed-offset refusal, invalid range, zero-candidate exit 0 with schema-correct empty artifacts, full happy path — green; live CLI smoke `python -m ai_trading.backtest --help` exit 0 |
| 16 | BT-05: Walk-forward artifacts deterministic and atomic: walkforward.parquet byte-identical across re-runs, boundaries/config hash in a separate JSON manifest | ✓ VERIFIED | reports.py write_walkforward (deterministic filename, internal sort) + write_window_manifest (WINDOW_MANIFEST_KEYS contract); test_walkforward_write_is_byte_deterministic_and_sort_insensitive, test_window_manifest_roundtrip_and_separation — green |

**Score:** 16/16 truths verified (0 present, behavior-unverified)

**Suite evidence:** `uv run pytest tests/unit -q` → **358 passed** in 61.69s (single full-suite run this verification; 184 of those are this phase's tests across the 11 new/extended modules — 87 from 03-01 + 59 from 03-02 + 38 from 03-03, matching the SUMMARY claims exactly). All behavior-dependent truths above are backed by passing named tests inside that run (enumerated before running; single named tests were not re-run separately).

### Deferred Items

| # | Item | Addressed In | Evidence |
|---|------|-------------|----------|
| 1 | Purge train labels whose [entry_time, exit_time] interval overlaps a test window (AFML ch.7) | Phase 4 (ML) | Documented obligation in walkforward.py module docstring (L23-28) + 03-02/03-03 PLAN verification notes; labels carry entry_time/exit_time exactly for this purpose — Phase 3 scope correctly stops at persisting the stamps |
| 2 | DST live re-validation of the broker offset (+3/+2 flip) | Carried obligation (human-assisted, mt5-marked) | 02-VERIFICATION deferred item; runner's assert_offset_uniform guard (unit-proven) is the in-scope counterpart; live terminal check is out of unit scope by design |

### Required Artifacts

| Artifact | Expected | Status | Details |
| -------- | -------- | ------ | ------- |
| `src/ai_trading/backtest/__init__.py` | bare marker, zero code | ✓ VERIFIED | 228 bytes; docstring-only marker |
| `src/ai_trading/backtest/asof.py` | STAMP_CLOSE/STAMP_BAR, visible_mask, close_time_of | ✓ VERIFIED | substantive; wired into replay.py + candidates.py |
| `src/ai_trading/backtest/chain.py` | run_chain calling detector exports only | ✓ VERIFIED | 12-key dict incl. zones15 (documented deviation); wired by runner L224 |
| `src/ai_trading/backtest/costs.py` | 6 cost functions, POINTS→price, D-15/D-14 | ✓ VERIFIED | wired into replay + barriers + runner |
| `src/ai_trading/backtest/candidates.py` | Candidate/CandidateState, bias_agrees, candidate_at_bar, compute_rr | ✓ VERIFIED | wired into replay L41; Phase 6 import surface documented |
| `src/ai_trading/backtest/replay.py` | Position, LABEL_COLUMNS (20 cols), warmup/gate/offset helpers, replay_symbol | ✓ VERIFIED | resolver seam closed by walk_barriers |
| `src/ai_trading/backtest/barriers.py` | OUTCOME_* + walk_barriers (resolver impl) | ✓ VERIFIED | satisfies the 03-01 seam (test_walk_barriers_satisfies_replay_resolver_seam) |
| `src/ai_trading/backtest/stats.py` | canonical_stats, stats_by_symbol_timeframe | ✓ VERIFIED | raw_/net_ + cost_delta_expectancy; pinned dtypes |
| `src/ai_trading/backtest/reports.py` | 5 writers + config_hash + atomic helpers | ✓ VERIFIED | tmp+os.replace everywhere; manifest key contracts enforced |
| `src/ai_trading/backtest/walkforward.py` | Window, build_windows, assignment, stats_table, aggregate | ✓ VERIFIED | THE Phase 4 splitter of record |
| `src/ai_trading/backtest/runner.py` + `__main__.py` | main→int, run_backtest, resolve_range; CLI entry | ✓ VERIFIED | exit-code contract proven; --help smoke exit 0 |
| `src/ai_trading/config.py` | +12 frozen knobs, _REQUIRED_KEYS, _validate | ✓ VERIFIED | load_config passes all 12 |
| `config.toml` | backtest knobs section | ✓ VERIFIED | all 12 keys with documented defaults |
| 11 test modules + `_backtest_fixtures.py` | per-plan test specs | ✓ VERIFIED | 184 tests collected; named integrity tests all present |

### Key Link Verification

| From | To | Via | Status | Details |
| ---- | --- | --- | ------ | ------- |
| chain.run_chain | detectors.* (swings/zigzag/pools/zones/mtf) | direct submodule imports | ✓ WIRED | chain.py L20-24; vendor-purity assertion extended over backtest/*.py |
| replay.replay_symbol | asof.visible_mask + candidates.candidate_at_bar + costs.entry_fill_price | imports + per-bar calls | ✓ WIRED | replay.py L40-42, L251-285 |
| costs spread/slippage fallback | config knobs | cfg lookups | ✓ WIRED | costs.py L54-55, L84-85; config.py carries the 12 knobs |
| barriers.walk_barriers | replay resolver seam | (Position, bars, cfg) → dict | ✓ WIRED | exact key set {outcome, exit_price, exit_idx, exit_time, r_gross, r_raw, r_net}; lifecycle test green |
| runner | walk_barriers as resolver | replay_symbol(m15, chain, cfg, walk_barriers) | ✓ WIRED | runner.py L225 — the 03-01 interface-first seam closes |
| runner | check_history_gate / assert_offset_uniform / bar_store.read_bars | gate → load wiring | ✓ WIRED | runner.py L198-217; gate refusal test green |
| walkforward | stats.canonical_stats + barrier entry_time/exit_time stamps | reuse per group | ✓ WIRED | walkforward.py L55, L264-265; splits on entry TIME (Phase 4 purge contract) |
| reports writers | bar_store atomic discipline | tmp + os.replace | ✓ WIRED | reports.py L65-91; no second write path |
| runner → artifacts | 5 artifact files under data/labels/ + data/reports/ | --write path | ✓ WIRED | test_full_happy_path_end_to_end green: all five artifacts created with matching config_hash |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
| -------- | ------------- | ------ | ------------------ | ------ |
| runner pipeline | bars | bar_store.read_bars parquet stores | Yes — synthetic parquet written via bar_store.merge_and_write in tests, read back through the single read path | ✓ FLOWING |
| labels frame | chain tier output | run_chain detector exports over sliced bars | Yes — real detector functions, positive-control label test pins a hand-derived label | ✓ FLOWING |
| canonical/walk-forward stats | labels (outcome, r_raw, r_net) | real walk_barriers output | Yes — cost-delta test asserts −0.10 exact from REAL walk output | ✓ FLOWING |

No UI/dashboard artifacts in this phase — no hollow-prop risk surface.

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
| -------- | ------- | ------ | ------ |
| Full unit suite green | `uv run pytest tests/unit -q` | 358 passed in 61.69s | ✓ PASS |
| CLI surface | `uv run python -m ai_trading.backtest --help` | usage text incl. --config/--symbols/--range/--min-history-days/--write; exit 0 | ✓ PASS |
| Phase test enumeration | `pytest --co -q` over the 11 phase modules | 184 collected | ✓ PASS |

### Probe Execution

Step 7c: SKIPPED — no `scripts/*/tests/probe-*.sh` probes declared or conventional for this repo; the pytest suite + live CLI smoke serve as the runnable checks (recorded above).

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
| ----------- | ---------- | ----------- | ------ | -------- |
| BT-01 | 03-01 | Backtester replays the identical pipeline bar-by-bar (one shared code path) | ✓ SATISFIED | Truths 1-3, 5; chain.py imports detector exports; vendor-purity test; prefix-equivalence suite |
| BT-02 | 03-01 | Outcomes model recorded spread + slippage buffer; metrics net of costs | ✓ SATISFIED | Truths 4, 6, 9; costs.py + convention-(a) R variants; config knobs fail-fast |
| BT-03 | 03-02 | Triple-barrier labels with documented SL-first tie rule, reproducible from raw setup + bars | ✓ SATISFIED | Truths 7-9, 11; barriers.py pure walk + named tie/gap/window tests; label parquet deterministic |
| BT-04 | 03-02 | Canonical stats per symbol/timeframe | ✓ SATISFIED | Truths 10, 11; stats.py + guard table + raw/net with cost delta |
| BT-05 | 03-03 | Per-window walk-forward reports to expose regime shifts | ✓ SATISFIED | Truths 12-16; walkforward.py + runner + per-window stats/aggregate + deterministic artifacts |

Orphaned requirements: **none** — REQUIREMENTS.md maps exactly BT-01…BT-05 to Phase 3; plans claim 03-01: [BT-01, BT-02], 03-02: [BT-03, BT-04], 03-03: [BT-05]; full union = BT-01…BT-05 with no gap and no extra.

### Locked-Decisions Honor Check (D-01…D-22)

All 22 locked decisions from 03-CONTEXT.md are traceable to implemented, test-pinned code: D-01/D-02/D-06 (candidates.py + tests), D-03 (module-ownership docstring + signature stability), D-04/D-05/D-07/D-12 (replay.py + named tests), D-08/D-09/D-13 (candidates.py SL/TP incl. documented D-09 liveness convention), D-10/D-11/D-17/D-18 (barriers.py + named tests), D-14/D-15/D-16 (costs.py/stats.py + literal tests), D-19/D-20/D-22 (walkforward.py + named tests), D-21 (replay.check_history_gate + runner gate tests). Two planner conventions where the context was silent (D-09 liveness, PF decided-trade ratio) are documented in-module and in SUMMARY decisions — plan-spec corrections, not violations.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
| ---- | ---- | ------- | -------- | ------ |
| (none) | — | No TBD/FIXME/XXX/TODO/HACK/PLACEHOLDER markers in src/ai_trading/backtest/ | — | — |
| (none) | — | No vendor (MetaTrader5) imports — docstring prose only, permitted by the extended vendor-purity assertion | — | — |
| (none) | — | No empty-return / console-only / placeholder implementations in backtest/ | — | — |

All 9 task commits verified in git log: 7af3685, d8982a7, 5fbba0c, f259af6 (03-01); 2f84b4b, 72ed7ca, 96d5631, 53ec22b (03-02); c19bab9, 7ad6559, 8ab5b48, c32f2ff (03-03).

### Human Verification Required

Three items, all recorded in 03-USER-SETUP.md (Status: Incomplete). None are implementation gaps — the code and tests are complete; these are plan-declared human judgment calls:

1. **A1 cost-asymmetry convention** (plan 03-01 user_setup) — 10-second eyeball of `costs.py` fill formulas + `test_long_short_cost_symmetry`; confirm bid-side-bar semantics match your mental model.
2. **D-10 SL-first tie convention** (plan 03-02, human_judgment coverage row) — eyeball the barriers.py docstring + tie test; confirm the conservative rule matches intent.
3. **Real-data demo run + history-depth decision** (plan 03-03 user_setup, Phase gate Open Question 1) — stored M15 history is ~9 days, below the 30-day gate. Choose: deepen history via Phase 1 purge+backfill, run with `--min-history-days` override / shorter range, or demo on H4 depth; then execute `uv run python -m ai_trading.backtest --config config.toml --range last-ND --write` and inspect the five artifacts.

### Gaps Summary

None. Every must-have truth, artifact, and key link is verified against actual source code and a green 358-test suite run (184 phase tests, matching all SUMMARY claims). The phase goal — a bar-by-bar replay engine running the identical detector pipeline, modeling costs, labeling outcomes, and reporting canonical + walk-forward statistics — is fully achieved in code. The `human_needed` status reflects only the three plan-declared human decisions above (two convention eyeballs + one real-data demo gate decision), all pending in 03-USER-SETUP.md.

---

_Verified: 2026-09-02T15:31:15Z_
_Verifier: the agent (gsd-verifier)_
