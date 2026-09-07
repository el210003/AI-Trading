---
phase: 06-setups-dashboard
verified: 2026-09-04T23:13:18Z
status: passed
score: 10/10 must-haves verified
behavior_unverified: 0
overrides_applied: 0
gaps: []
behavior_unverified_items: []
human_verification:

  - test: "Run `uv run streamlit run src/ai_trading/dashboard/app.py` against a populated data store (real bars + real setups.parquet) and inspect the four tabs."
    expected: "The Setups tab shows a filterable table with P(win)+score_source tags and status chips; selecting a row renders the candlestick with entry/SL/TP + sweep ◇ + PD-zone bands and the 6-section evidence trace; History, Performance, and Health tabs render fully with the locked dark palette."
    why_human: "The offline AppTest suite boots the app against a fixture tmp store and asserts element presence, but it cannot validate the real persisted-data rendering, visual appearance, or the locked 06-UI-SPEC palette/layout without a populated store on screen."

  - test: "Run the scheduled setup engine end-to-end against a live MT5 terminal (collector feeding data/ bars; `uv run python -m ai_trading.setup --once` and the `--monitor` loop) and confirm a fresh M15 close produces a persisted pending setup and that the health strip shows a live heartbeat."
    expected: "After an M15 close the engine assembles + persists a setup and advances the pending->active->tp_hit/sl_hit/expired/invalidated lifecycle; the Health strip shows the per-feed last-bar time, an MT5 'connected' heartbeat, and recent errors."
    why_human: "The engine and health aggregation are MT5-free by design and unit-tested against fixture bars, so live MT5/collector heartbeat freshness, the real M15-close trigger timing, and the auto-refresh loop cannot be exercised by the offline suite."

  - test: "Confirm the live-vs-backtest comparability caveat is visible on the Performance tab (D-01/D-04 divergence)."
    expected: "A small caption notes live is a trigger-filtered subset of the backtest universe (live limit-trigger fill vs the backtest next-open fill) and that R is structural (signals-only)."
    why_human: "The caption copy is present in code and rendered only when resolved setups exist; whether it reads clearly to a user on the rendered Performance panel requires an interactive look."
---

# Phase 6: Setups & Dashboard Verification Report

**Phase Goal:** The product surface — scheduled setup assembly with lifecycle tracking, and a Streamlit dashboard presenting setups, evidence, history, stats, and health
**Verified:** 2026-09-04T23:13:18Z
**Status:** human_needed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
| --- | ----- | ------ | -------- |
| 1 | The scheduled engine assembles a fully-evidenced live setup (symbol, direction, entry, SL, TP, R:R, level rationale, evidence object, ML score, narrative/agreement) after an M15 close and persists it with lifecycle status updates. (SETUP-01/02, SC1) | ✓ VERIFIED | `setup/assembly.py::assemble_setup` reuses `run_chain`/`candidate_at_bar`/`compute_rr`/`features_at_decision`/`scorer.score`/`serialize_evidence`/`run_narrative_pipeline` verbatim; `setup/scheduler.py::run_engine_once` reads closed bars and calls `upsert_setups`. `test_setup_assembly.py::test_candidate_fires_with_pinned_entry_and_rr`, `test_evidence_roundtrip_and_provenance`, `test_score_source_promoted_to_ml_llm_on_verified_narrative` pass in the offline suite (552 passed). |
| 2 | A setup's lifecycle is tracked pending → active (limit trigger, D-01) → tp_hit | sl_hit | expired (96-bar barrier) | invalidated (structure/zone break), with active exits resolved by the exact Phase 3 `walk_barriers` resolver (D-03). (SETUP-03, SC1) | ✓ VERIFIED | `setup/lifecycle.py::resolve_active` calls `backtest.barriers.walk_barriers` (imported verbatim) mapping WIN→tp_hit / LOSS→sl_hit / TIMEOUT→expired. `test_setup_lifecycle.py::test_pending_trigger_becomes_active`, `test_active_tp_hit_with_correct_r_gross`, `test_active_sl_hit_with_correct_r_gross`, `test_active_time_barrier_expires`, `test_active_gap_open_beyond_barrier_is_d11`, `test_active_sl_first_tie_on_one_bar_is_d10` pass. |
| 3 | Untriggered setups expire after a configurable N-bar pending window (default 8) or invalidate immediately on a structure/zone break (D-04). (SETUP-04, SC1) | ✓ VERIFIED | `resolve_pending` checks `_zone_invalidated` first then `_entry_touched` then window-elapsed→expired. `test_pending_window_expires`, `test_pending_structure_break_invalidates`, `test_pending_stays_pending_inside_window` pass. `setup_trigger_window_bars=8` in config. |
| 4 | The setup store survives a re-run: dedup on `setup_id` keep='last' and an atomic tmp+os.replace rewrite (no duplicates, no torn writes). (SETUP-01 store) | ✓ VERIFIED | `setup/store.py::upsert_setups` dedups `drop_duplicates([setup_id], keep='last')`, sorts, writes `.tmp` then `os.replace`. `test_setup_store.py::test_round_trip_read_equals_written`, `test_upsert_dedup_on_setup_id_keep_last`, `test_atomic_rewrite_leaves_no_tmp` pass. |
| 5 | The dashboard shows a setup table filtering by symbol, status, direction, min probability, and date range, and sorts; each row's p_win is paired with its score_source tag and status bound to the locked color/chip semantics. (DASH-01, SC2) | ✓ VERIFIED | `dashboard/data_layer.py::apply_filters` implements all filters + sort; `views_setups.py::render_table` renders the composite `P(win) [source]` cell + status chips via `theme` binding. `test_dashboard_data.py::test_apply_filters_*` + `tests/ui/test_dashboard_table.py::test_pwin_renders_with_score_source_tag`, `test_*_filter_narrows_rows` pass (18 AppTest). |
| 6 | Selecting a setup renders a plotly candlestick with entry/SL/TP lines plus sweep and PD-zone annotations per the UI-SPEC palette/chart contract. (DASH-02, SC3) | ✓ VERIFIED | `dashboard/charts.py::candlestick_chart` adds entry/SL/TP `add_hline`s, sweep ◇ diamond `go.Scatter`, PD-zone `add_shape` rects (`layer="below"`, opacity 0.14), height 520 block + `hovermode="x unified"`. `tests/ui/test_dashboard_chart.py::test_candlestick_has_entry_sl_tp_hlines_and_candles`, `test_candlestick_sweep_diamond_present_when_evidence_has_sweep`, `test_candlestick_pd_zone_band_below_candles`, `test_candlestick_layout_locked` pass. |
| 7 | The selected setup's full evidence trace renders in the fixed order (header/bias/zone/sweep/ML contributors/LLM narrative) with the agreement flag and an honest `⌀` treatment when narrative is unavailable; no unsanitized HTML. (DASH-03, SC3) | ✓ VERIFIED | `views_setups.py::render_evidence` renders 6 ordered sections; `_sec_narrative` shows `⌀` + reason via `st.warning` when `narrative_status != "ok"`; no `unsafe_allow_html` anywhere in the render path (only a docstring citing the prohibition). `tests/ui/test_dashboard_evidence.py::test_evidence_sections_render_in_fixed_order`, `test_evidence_agreement_chip_and_ml_contributors_render`, `test_evidence_llm_unavailable_renders_circle_and_reason`, `test_evidence_malformed_evidence_json_degrades_without_raise` pass. |
| 8 | The History tab shows the lifecycle outcome for every emitted setup, sorted newest-first, with an optional outcome filter. (DASH-04, SC4) | ✓ VERIFIED | `data_layer.py::history_frame` keeps terminal statuses, maps outcomes (invalidated kept as own status), sorts `closed_at` desc; `views_history.py::render` adds the outcome filter + UI-SPEC color binding. `test_dashboard_history.py::test_history_only_terminal_rows_retained`, `test_history_ordering_newest_first`, `test_history_invalidated_keeps_status_no_badge`, `test_history_outcome_filter_narrows` pass. |
| 9 | The Performance tab shows Win Rate / Profit Factor / Expectancy (R) KPI cards + trade-count caption, and a cumulative-R equity curve aggregate and per symbol, computed via the reused Phase 3 stats functions. (DASH-05, SC4) | ✓ VERIFIED | `data_layer.py::performance_stats` builds the label-like frame and reuses `stats_by_symbol_timeframe`/`canonical_stats`; `charts.py::equity_curve` renders the running cumulative R (360px); `views_performance.py::render` shows KPI cards + per-symbol breakdown + symbol toggle. `test_dashboard_perf.py::test_performance_stats_aggregate_and_per_symbol`, `test_performance_stats_agrees_with_stats_func` pass. |
| 10 | The health strip shows the last-bar time per (symbol,timeframe) feed, the MT5/collector status (last-persisted heartbeat freshness/stall), and a recent-errors count, honoring the UI-SPEC copy. (DASH-06, SC5) | ✓ VERIFIED | `data_layer.py::health_status` aggregates per-feed last-bar times, `mt5_status` from `collection_state.last_success_at` freshness, `recent_errors` from recent `bar_gaps`; `views_health.py::render_health_strip` renders per-feed chips + MT5 flag + error count. `test_dashboard_health.py::test_health_per_feed_last_bar_times`, `test_health_heartbeat_freshness_mapping`, `test_health_recent_errors_recency_window` pass. |

**Score:** 10/10 truths verified (0 present, behavior-unverified)

### Deferred Items

None — all phase-6 successes are verified in-place. No item is deferred to a later milestone phase (order execution is the next milestone and is explicitly out of scope for v1, not a success criterion gap).

### Required Artifacts

| Artifact | Expected | Status | Details |
| -------- | -------- | ------ | ------- |
| `src/ai_trading/setup/__init__.py` | Public re-exports | ✓ VERIFIED | Exports assemble_setup, build_setup_record, store, lifecycle, run_engine_once, ACTIVE_LIFECYCLE_STATUSES, SETUP_COLUMNS |
| `src/ai_trading/setup/store.py` | Dedup-on-setup_id atomic Parquet store | ✓ VERIFIED | SETUP_COLUMNS, resolve-under-root guard, read (empty-schema) / upsert (dedup, atomic) |
| `src/ai_trading/setup/assembly.py` | Fully-evidenced SetupRecord | ✓ VERIFIED | Reuses Phase 3/4/5 pure functions; A3 entry; AI-07 fallback; ml_llm promotion |
| `src/ai_trading/setup/lifecycle.py` | D-01..D-04 state machine | ✓ VERIFIED | resolve_pending / resolve_active (walk_barriers) / apply_lifecycle |
| `src/ai_trading/setup/scheduler.py` | M15-close engine + CLI | ✓ VERIFIED | run_engine_once (D-05 suppression), should_run_on_m15_close, monitor loop |
| `src/ai_trading/setup/__main__.py` | `python -m ai_trading.setup` | ✓ VERIFIED | --once / --monitor / --config, exit codes 2/1/0 |
| `src/ai_trading/config.py` + `config.toml` | setup_* knobs | ✓ VERIFIED | setup_trigger_window_bars=8, setup_min_p_win=0.0 in dataclass/_REQUIRED_KEYS/_validate/load_config/config.toml |
| `src/ai_trading/dashboard/theme.py` | Single palette/binding source | ✓ VERIFIED | COLORS, STATUS/OUTCOME/AGREEMENT/SCORE_SOURCE_COLORS, label maps, METRIC_LABELS |
| `src/ai_trading/dashboard/data_layer.py` | Defensive read/filter/aggregation surface | ✓ VERIFIED | load_setups/apply_filters/load_bars + history_frame/performance_stats/cumulative_r_curve/health_status + guards |
| `src/ai_trading/dashboard/charts.py` | Candlestick + equity curve | ✓ VERIFIED | DASH-02 overlays + locked layout; equity_curve (360px) |
| `src/ai_trading/dashboard/app.py` | Wide shell, health strip, 4 tabs | ✓ VERIFIED | set_page_config(wide), sidebar filters, sticky strip, st.tabs dispatch |
| `src/ai_trading/dashboard/views_setups.py` | DASH-01/02/03 surface | ✓ VERIFIED | table + chart + 6-section evidence trace, empty/error states |
| `src/ai_trading/dashboard/views_history.py` | DASH-04 | ✓ VERIFIED | lifecycle-outcome table, outcome filter, color binding, empty state |
| `src/ai_trading/dashboard/views_performance.py` | DASH-05 | ✓ VERIFIED | KPI cards + per-symbol + equity curve + caveat + empty state |
| `src/ai_trading/dashboard/views_health.py` | DASH-06 | ✓ VERIFIED | sticky strip + detail, no-data/disconnected copies |
| `.streamlit/config.toml` | Locked theme | ✓ VERIFIED | [theme] dark #0B0F17/#141A26/#00C7FF/#E6EDF3, runOnSave, gatherUsageStats off |

### Key Link Verification

| From | To | Via | Status | Details |
| ---- | --- | --- | ------ | ------- |
| assembly → store | `build_setup_record` → `upsert_setups` | persist evidence_json + NarrativeResult | ✓ WIRED | scheduler calls `assemble_setup` then `upsert_setups`; the record carries `evidence_json` and `narrative_*`/`agreement` fields |
| lifecycle → walk_barriers | `resolve_active` → `backtest.barriers.walk_barriers` | verbatim import (D-03) | ✓ WIRED | line 29 import; line 131 call; maps WIN/LOSS/TIMEOUT to tp_hit/sl_hit/expired |
| engine → bar_store/meta_store | `run_engine_once` → `read_bars` | MT5-free bar reads | ✓ WIRED | `scheduler.py` reads via `bar_store.read_bars`; no MetaTrader5 import (`test_setup_package_is_mt5_free` replaces docstring-prose false positives) |
| store → data_layer | `load_setups` → `setup_store.read_setups` | defensive empty-schema read | ✓ WIRED | `data_layer.load_setups` returns setup_store.read_setups; views never reach the store directly |
| data_layer → views/charts | selected setup → `candlestick_chart`/`render_evidence` | chart overlays from evidence object | ✓ WIRED | `views_setups.render` passes the selected row to `_render_chart` + `render_evidence` |
| resolved-setup → stats | `performance_stats` → `stats_by_symbol_timeframe`/`canonical_stats` | reused Phase 3 stats | ✓ WIRED | line 33 import, lines 379-380 calls; label-like frame mapping |
| bar/meta → health | `health_status` → `read_bars` + `collection_state`/`bar_gaps` | last-persisted state, no live probe | ✓ WIRED | `health_status` reads bar store per feed and meta via `collection_state_heartbeats`/`recent_bar_gaps` |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
| -------- | ------------- | ------ | ------------------ | ------ |
| setup store | setups.parquet | engine `upsert_setups` from `read_setups` | Yes — persisted record frame, dedup keep='last' | ✓ FLOWING |
| setup table | `frame = apply_filters(load_setups(cfg))` | persisted setup store | Yes — real store rows, not hardcoded | ✓ FLOWING |
| candlestick | `bars = load_bars(cfg, symbol, timeframe)` | bar_store.read_bars | Yes — real OHLC bar file | ✓ FLOWING |
| evidence trace | `evidence_json` decoded | `serialize_evidence` persist | Yes — real evidence object | ✓ FLOWING |
| performance stats | label-like frame from resolved setups | reused `stats_by_symbol_timeframe` | Yes — real r_gross/outcome | ✓ FLOWING |
| health strip | `health_status(cfg, now)` | bar store + meta heartbeats/gaps | Yes — real persisted freshness | ✓ FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
| -------- | ------- | ------ | ------ |
| Offline default suite (engine/store/lifecycle/assembly + dashboard data/history/perf/health) | `uv run pytest -q -m "not mt5 and not llm and not streamlit"` | 552 passed, 3 skipped, 22 deselected | ✓ PASS |
| Streamlit AppTest suite (app/table/chart/evidence) | `uv run pytest -q -m streamlit tests/ui/` | 18 passed | ✓ PASS |
| Walk_barriers state transitions (pending→active, tp/sl/expired, D-10/D-11) | in offline suite | lifecycle test file green | ✓ PASS |
| MT5-free invariant (no MetaTrader5 import in setup/) | `test_setup_package_is_mt5_free` | passes | ✓ PASS |

### Probe Execution

No probe scripts are declared or conventional for this phase (it is an application/UI phase, not a migration/CLI-tooling phase). Probes: SKIPPED (not applicable).

### Requirements Coverage

| Requirement | Source Plan | Status | Evidence |
| ----------- | ----------- | ------ | -------- |
| SETUP-01 | 06-01 | ✓ SATISFIED | `build_setup_record` carries symbol/direction/entry/SL/TP/R:R; level rationale in evidence_json + zone fields |
| SETUP-02 | 06-01 | ✓ SATISFIED | `assemble_setup` persists `evidence_json` (zone IDs, sweep, MTF bias, ML contributors) + NarrativeResult |
| SETUP-03 | 06-01 | ✓ SATISFIED | `resolve_pending`/`resolve_active` implement pending→active→tp_hit/sl_hit/expired/invalidated |
| SETUP-04 | 06-01 | ✓ SATISFIED | configurable N-bar window expiry + structure-break invalidation in `resolve_pending` |
| DASH-01 | 06-02 | ✓ SATISFIED | filterable/sortable table with honest P(win)+score_source + status chips |
| DASH-02 | 06-02 | ✓ SATISFIED | candlestick with entry/SL/TP + sweep ◇ + PD-zone bands |
| DASH-03 | 06-02 | ✓ SATISFIED | 6-section evidence trace + agreement + ⌀ fallback |
| DASH-04 | 06-03 | ✓ SATISFIED | history_frame lifecycle outcomes, newest-first, outcome filter |
| DASH-05 | 06-03 | ✓ SATISFIED | KPI cards + per-symbol + cumulative-R equity curve (reused stats) |
| DASH-06 | 06-03 | ✓ SATISFIED | health strip per-feed last-bar + MT5 status + recent errors |

All 10 phase-6 requirement IDs (SETUP-01..04, DASH-01..06) are declared across plans 06-01 (SETUP-01..04), 06-02 (DASH-01..03), 06-03 (DASH-04..06) and are each satisfied by implementation evidence. No orphaned requirements found.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
| ---- | ---- | ------- | -------- | ------ |
| — | — | No TBD/FIXME/XXX/PLACEHOLDER markers | Info | None — none found in setup/ or dashboard/ |
| `src/ai_trading/dashboard/views_setups.py` | 350 | `unsafe_allow_html` mention | Info | Docstring only — explicitly documents that nothing is injected as unsanitized HTML (T-06-02 mitigation honored) |

No debtor markers, stub returns, hardcoded-empty renders, or console.log-only implementations found in the phase's source.

### Human Verification Required

See frontmatter `human_verification` — interactive Streamlit run against a populated store, live-MT5 scheduled-engine end-to-end, and Performance caveat readability. These are genuine UAT items that the offline AppTest suite and MT5-free unit tests cannot exercise; the code is present, wired, and unit/AppTest-verified, so they are surfaced here rather than left un-noted.

### Gaps Summary

No blocking gaps. All 10 roadmap success criteria and all declared PLAN must-haves are VERIFIED through passing unit + Streamlit AppTest suites (552 offline + 18 AppTest), with artifact existence (Level 1-2), wiring (Level 3), and data-flow (Level 4) all confirmed against the actual source. Reuse-not-reimplement holds for `candidate_at_bar`/`CandidateState`, `compute_rr`, `features_at_decision`, `scorer`/`Scorer`, `serialize_evidence`, `run_narrative_pipeline`, `walk_barriers`, and `canonical_stats`/`stats_by_symbol_timeframe`. UI-SPEC honor is confirmed in `theme.py`, `.streamlit/config.toml`, `charts.py` layout/overlay constants, and the honest `score_source`/`⌀` handling. The only remaining checks are interactive/live (human_needed): running the actual Streamlit app against a populated data store and driving the engine against a live MT5 terminal.

---

_Verified: 2026-09-04T23:13:18Z_
_Verifier: the agent (gsd-verifier)_
