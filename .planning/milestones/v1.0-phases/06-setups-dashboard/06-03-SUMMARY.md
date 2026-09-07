---
phase: 06-setups-dashboard
plan: 03
subsystem: ui
tags: streamlit, plotly, dashboard, history, performance, health, stats, equity-curve, mt5-free

# Dependency graph
requires:
  - phase: 06-setups-dashboard (plan 06-02)
    provides: dashboard package (theme/data_layer/charts/app shell) + locked 06-UI-SPEC.md contract; the Setups tab surface; the History/Performance/Health stubs this plan replaces
  - phase: 06-setups-dashboard (plan 06-01)
    provides: persisted Parquet setup store (SETUP_COLUMNS / read_setups) with resolved lifecycle statuses + r_gross/r_net/r_raw
  - phase: 03-backtesting-labeling
    provides: backtest.stats.canonical_stats / stats_by_symbol_timeframe (reused verbatim for the Performance panel)
  - phase: 01-data-foundation
    provides: bar_store.read_bars / bar_path (last-bar time source) + meta_store collection_state / bar_gaps (heartbeat freshness + recent-errors)
provides:
  - ai_trading.dashboard History tab (DASH-04): lifecycle-outcome table over closed setups, newest-first, with an outcome filter
  - ai_trading.dashboard Performance tab (DASH-05): Win Rate / Profit Factor / Expectancy (R) KPI cards + trade-count caption + per-symbol breakdown + cumulative-R equity curve (aggregate + per-symbol toggle)
  - ai_trading.dashboard Health strip + tab (DASH-06): per-feed last-bar time, MT5/collector status (heartbeat freshness), recent-errors count, honoring the UI-SPEC copy
  - data_layer.history_frame / performance_stats / cumulative_r_curve / health_status (+ collection_state_heartbeats / recent_bar_gaps meta readers)
  - charts.equity_curve (cumulative-R running line, 360px)
affects: verify-work (UAT over the History/Performance/Health surface), the next milestone (order execution), future phases reusing the stats/health aggregation

# Tech tracking
tech-stack:
  added: (none new; streamlit/plotly consumed from 06-01)
  patterns: single palette/binding source in theme; resolve-under-root guard + defensive empty-state reads (T-06-03) threaded through history/performance/health; reused backtest.stats (no recomputed stat math); single-purpose meta readers for health; native Streamlit widgets only (no unsafe_allow_html, T-06-02); MT5-free dashboard (last-persisted state only, OQ4)
key-files:
  created:
    - tests/unit/test_dashboard_history.py
    - tests/unit/test_dashboard_perf.py
    - tests/unit/test_dashboard_health.py
  modified:
    - src/ai_trading/dashboard/data_layer.py
    - src/ai_trading/dashboard/charts.py
    - src/ai_trading/dashboard/views_history.py
    - src/ai_trading/dashboard/views_performance.py
    - src/ai_trading/dashboard/views_health.py

key-decisions:
  - "Performance R basis (A4): the panel uses the structural r_gross from each resolved setup; data_layer maps tp_hit->WIN / sl_hit->LOSS / expired->TIMEOUT and sets r_raw == r_net == r_gross so it reuses stats_by_symbol_timeframe unchanged; the live-vs-backtest comparability caveat (D-01/D-04) is surfaced as a panel caption."
  - "Health status semantics (OQ4): last-persisted state only — per-feed last-bar time from the bar store + the meta collection_state.last_success_at heartbeat; 'MT5 disconnected'/stale renders the UI-SPEC copy when the heartbeat is old; no live MT5 probe."
  - "Recent-errors is derived from the meta store's existing bar_gaps records (data-quality gaps detected in the last N days) via the new single-purpose helpers collection_state_heartbeats / recent_bar_gaps; no new errors table."
  - "The History tab keeps the invalidated structural break as its own status (no WIN/LOSS badge) per DASH-04 / DASH-06 status semantics."

patterns-established:
  - "Data-layer single source of truth for the Stats + Health aggregation: no stat math in the views; all numbers come from data_layer helpers that reuse backtest.stats."
  - "Defensive store reads (T-06-03) everywhere: history_frame/performance_stats/cumulative_r_curve/health_status all return schema-correct empty values on a missing/empty store, so each view renders the Empty/copy state and suppresses only itself."

requirements-completed: [DASH-04, DASH-05, DASH-06]

coverage:
  - id: D1
    description: "DASH-04 History tab: data_layer.history_frame (terminal-only retention, newest-first closed_at ordering, WIN/LOSS/TIMEOUT badge mapping with invalidated kept as its own status, optional outcome filter, schema-correct empty frame) + views_history.render over it with the outcome filter and UI-SPEC status/outcome color binding."
    requirement: DASH-04
    verification:
      - kind: unit
        ref: tests/unit/test_dashboard_history.py#test_history_only_terminal_rows_retained;test_history_ordering_newest_first;test_history_invalidated_keeps_status_no_badge;test_history_empty_store_schema_frame;test_history_outcome_filter_narrows;test_history_columns_schema
        status: pass
      - kind: automated_ui
        ref: tests/ui/test_dashboard_app.py#test_app_runs_with_four_tabs_and_health_strip
        status: pass
    human_judgment: false
  - id: D2
    description: "DASH-05 Performance tab: data_layer.performance_stats (label-like frame mapped from resolved setups reusing stats_by_symbol_timeframe + canonical_stats aggregate), cumulative_r_curve, charts.equity_curve (cumulative-R line, 360px, bull hue), and views_performance.render (KPI cards + trade-count caption + per-symbol breakdown + equity-curve symbol toggle + empty state + live-vs-backtest caveat)."
    requirement: DASH-05
    verification:
      - kind: unit
        ref: tests/unit/test_dashboard_perf.py#test_performance_stats_aggregate_and_per_symbol;test_performance_stats_agrees_with_stats_func;test_performance_stats_excludes_non_resolved;test_performance_stats_all_expired_non_crashing;test_cumulative_r_curve_ordering_and_filter;test_cumulative_r_curve_empty_schema;test_performance_stats_empty_schema
        status: pass
      - kind: automated_ui
        ref: tests/ui/test_dashboard_app.py#test_app_runs_with_four_tabs_and_health_strip
        status: pass
    human_judgment: false
  - id: D3
    description: "DASH-06 Health strip + tab: data_layer.health_status (per-feed last-bar times, MT5 heartbeat freshness -> healthy/stale/disconnected, recent-errors recency count) + the single-purpose meta readers collection_state_heartbeats/recent_bar_gaps, and views_health.render_health_strip (sticky per-feed chips + MT5 status + errors) / render_detail (per-feed table + status + issues) with the UI-SPEC copy and no-data/disconnected empty states."
    requirement: DASH-06
    verification:
      - kind: unit
        ref: tests/unit/test_dashboard_health.py#test_health_per_feed_last_bar_times;test_health_heartbeat_freshness_mapping;test_health_recent_errors_recency_window;test_health_empty_store_degrades_no_data;test_recent_bar_gaps_direct
        status: pass
      - kind: automated_ui
        ref: tests/ui/test_dashboard_app.py#test_app_runs_with_four_tabs_and_health_strip
        status: pass
    human_judgment: false

# Metrics
duration: 15min
completed: 2026-09-04
status: complete
---

# Phase 6 Plan 3: History / Performance / Health Dashboard Views Summary

**The Phase-6 dashboard surface is complete: the DASH-04 History lifecycle-outcome table (newest-first with an outcome filter), the DASH-05 Performance panel (Win Rate / Profit Factor / Expectancy (R) KPI cards + per-symbol breakdown + cumulative-R equity curve with a symbol toggle, all from the reused Phase-3 `stats` functions), and the DASH-06 Health strip + tab (per-feed last-bar time, MT5/collector heartbeat freshness, recent-errors count) — all MT5-free over the persisted stores with honest empty/copy states.**

## Performance

- **Duration:** 15 min
- **Started:** 2026-09-04T22:45:30Z
- **Completed:** 2026-09-04T23:00:51Z
- **Tasks:** 3
- **Files modified:** 8 (5 source, 3 test created)

## Accomplishments

- **History (DASH-04)** replaces the plan 06-02 stub: `data_layer.history_frame` filters to the terminal statuses (`tp_hit`/`sl_hit`/`expired` and the `invalidated` structural break), derives the outcome badge (`WIN`/`LOSS`/`TIMEOUT`, with `invalidated` kept as its own status — never a WIN/LOSS badge), sorts `closed_at` newest-first, and returns a schema-correct `HISTORY_COLUMNS` frame. `views_history.render` applies the global filters + an optional Outcome selectbox and renders the table with the UI-SPEC status/outcome color binding.
- **Performance (DASH-05)** replaces the stub: `data_layer.performance_stats` builds a label-like frame (`symbol`/`timeframe`/`outcome`/`r_raw`/`r_net`) from the resolved setups with `r_raw == r_net == r_gross` (structural A4 R basis) and maps `tp_hit->WIN`/`sl_hit->LOSS`/`expired->TIMEOUT`, then reuses `stats_by_symbol_timeframe` (per-symbol) + `canonical_stats` (aggregate) — no recomputed stat math. `data_layer.cumulative_r_curve` returns the `closed_at`-sorted cumulative `r_gross`; `charts.equity_curve` renders it as the bull-hue cumulative-R line (360px). `views_performance.render` shows the KPI cards + trade-count caption + per-symbol breakdown + equity curve with a symbol toggle, plus the live-vs-backtest caveat caption and the empty state.
- **Health (DASH-06)** replaces the stub: `data_layer.health_status` aggregates per-feed last-bar times from the bar store, the MT5/collector status from the meta `collection_state.last_success_at` heartbeat freshness (healthy/stale/disconnected), and the recent-errors count from recent `bar_gaps` — via the new single-purpose meta readers `collection_state_heartbeats` / `recent_bar_gaps`. `views_health.render_health_strip` renders the sticky per-feed chips + MT5 status + error count; `render_detail` renders the full per-feed table + status + issues. Every path degrades to the no-data/copy state, never a traceback.
- **Honest empty/copy states** (T-06-03): all three data-layer helpers return schema-correct empty frames / no-data dicts on a missing/empty store, so each view renders the UI-SPEC copy and suppresses only itself.

## Task Commits

Each task was committed atomically:

1. **Task 1: History view — lifecycle outcomes for closed setups (DASH-04)** - `72b160e` (feat)
2. **Task 2: Performance view — KPI cards, per-symbol breakdown, cumulative-R equity curve (DASH-05)** - `4941e89` (feat)
3. **Task 3: Health view + health strip — last-bar time, MT5/collector status, recent errors (DASH-06)** - `b946faf` (feat)

**Plan metadata:** (final docs commit)

## Files Created/Modified

- `src/ai_trading/dashboard/data_layer.py` - added `history_frame`, `performance_stats`, `cumulative_r_curve`, `health_status`, `collection_state_heartbeats`, `recent_bar_gaps` (+ schema/status constants) — the single source of the History/Performance/Health aggregation over the reused stats functions and stores
- `src/ai_trading/dashboard/charts.py` - `equity_curve` rewritten to render the DASH-05 cumulative-R running line (bull hue, 360px, x-unified hover) from the `{time_utc, cum_r}` frame
- `src/ai_trading/dashboard/views_history.py` - DASH-04 lifecycle-outcome table with outcome filter + UI-SPEC color binding + empty state
- `src/ai_trading/dashboard/views_performance.py` - DASH-05 KPI cards + trade-count caption + per-symbol breakdown + equity curve (symbol toggle) + live-vs-backtest caveat + empty state
- `src/ai_trading/dashboard/views_health.py` - DASH-06 sticky health strip (per-feed chips + MT5 status + errors) + detailed Health tab (feed table + status + issues), MT5-free with no-data/disconnected copies
- `tests/unit/test_dashboard_history.py` / `test_dashboard_perf.py` / `test_dashboard_health.py` - 18 pure unit tests over the new data-layer helpers

## Decisions Made

- Performance R is the structural `r_gross` (signals-only A4); the data layer sets `r_raw == r_net == r_gross` and reuses `stats_by_symbol_timeframe` unchanged, with the live-vs-backtest caveat surfaced in the panel.
- The Health strip reflects last-persisted state only (bar-store last-bar times + meta heartbeat `last_success_at`), never a live MT5 probe (OQ4).
- Recent-errors is derived from the persisted `bar_gaps` records via single-purpose meta readers — no new errors table.
- `invalidated` structural breaks render as their own status in the History table — never a WIN/LOSS/TIMEOUT badge — per the DASH-04/D-06 status semantics.

## Deviations from Plan

None - plan executed exactly as written. The 06-02 health-strip call signature (`render_health_strip()`) was left unchanged because it resolves the config internally; the plan's "update app.py if needed" clause was not triggered (the Strip/Detail call both go through `health_status(cfg, now)` on every run — no cache on the refresh path).

---

**Total deviations:** 0 auto-fixed.
**Impact on plan:** None; the plan contracts were honored as specified.

## Issues Encountered

- Windows cannot create directory symlinks (OSError 1314), so the re-used data-layer traversal-guard tests remain skipped via the established `pytest.skip("directory symlinks unavailable on this platform")` convention (3 skips in the offline suite) — unchanged from prior phases.

## User Setup Required

None - no external service configuration required for this plan (the dashboard reads only persisted stores over the existing config; `llm_api_key` remains a gitignored `config.local.toml` secret. An interactive `streamlit run` needs a populated `config.local.toml` with `terminal_path`, as in prior phases.)

## Next Phase Readiness

- The Phase-6 dashboard is now feature-complete: Setups (DASH-01/02/03) + History (DASH-04) + Performance (DASH-05) + Health (DASH-06) all render over the persisted stores and are MT5-free with honest empty/copy states.
- Offline default suite green (552 passed, 3 skipped, 22 deselected); Streamlit AppTest suite green (18 passed).
- Ready for verify-work (UAT over the full dashboard surface) and the next milestone (order execution, deferred per PROJECT.md).

---
*Phase: 06-setups-dashboard*
*Completed: 2026-09-04*

## Self-Check: PASSED
