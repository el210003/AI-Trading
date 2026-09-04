---
phase: 06-setups-dashboard
plan: 02
subsystem: ui
tags: streamlit, plotly, dashboard, smc, streamlit-apptest, dark-theme, candlestick, evidence-trace

# Dependency graph
requires:
  - phase: 06-setups-dashboard (plan 06-01)
    provides: persisted Parquet setup store (SETUP_COLUMNS / read_setups / upsert_setups), evidence_json + NarrativeResult fields, resolved lifecycle statuses
  - phase: 06-setups-dashboard (spec)
    provides: 06-UI-SPEC.md locked visual contract (palette, typography, spacing, layout, components, copy, honesty rules)
  - phase: 01-data-foundation
    provides: bar_store.read_bars / bar_path for the candlestick feed
provides:
  - ai_trading.dashboard package (theme, data_layer, charts, app shell, views_setups + 3 stubs)
  - DASH-01 filterable/sortable setup table with honest P(win) + score_source tag and status chips
  - DASH-02 locked-palette plotly candlestick with entry/SL/TP hlines, sweep diamond, PD-zone bands
  - DASH-03 fixed-order evidence trace with ⌀ fallback for an unavailable narrative
  - .streamlit/config.toml locked dark theme
  - offline Streamlit AppTest suite (app / table / chart / evidence) + pure data-layer tests
affects: 06-03 (History/Performance/Health views replace the stubs), verify-work (UAT over the Setups surface)

# Tech tracking
tech-stack:
  added: (none new; streamlit 1.63.0 + plotly 7.0.0 installed in 06-01 are consumed)
  patterns: single palette/binding source in theme.py; defensive pure-reader data_layer with resolve-under-root guard; honest p_win+score_source composite cell; st.dataframe on_select single-row drives the chart+evidence anchor; on_click callback for Reset Filters; AppTest via st.secrets["CONFIG_PATH"] for offline boot

key-files:
  created:
    - .streamlit/config.toml
    - src/ai_trading/dashboard/__init__.py
    - src/ai_trading/dashboard/theme.py
    - src/ai_trading/dashboard/data_layer.py
    - src/ai_trading/dashboard/app.py
    - src/ai_trading/dashboard/charts.py
    - src/ai_trading/dashboard/views_setups.py
    - src/ai_trading/dashboard/views_history.py
    - src/ai_trading/dashboard/views_performance.py
    - src/ai_trading/dashboard/views_health.py
    - tests/unit/_dashboard_fixtures.py
    - tests/unit/test_dashboard_data.py
    - tests/ui/test_dashboard_app.py
    - tests/ui/test_dashboard_table.py
    - tests/ui/test_dashboard_chart.py
    - tests/ui/test_dashboard_evidence.py
  modified: []

key-decisions:
  - "The setup table uses st.dataframe on_select single-row; selecting a row renders the candlestick + evidence trace as the single visual anchor (DASH-02/03)."
  - "Reset Filters uses an on_click callback deleting the sidebar widget session_state keys (a widget key cannot be SET after instantiation); the Refresh path has no @st.cache_data (UI-SPEC manual-refresh contract)."
  - "The offline AppTest suites inject a fixture config via st.secrets['CONFIG_PATH'] (and the AITRADING_CONFIG env var), so the dashboard boots and is tested against an isolated tmp store with no live MT5/LLM."

patterns-established:
  - "Data-layer single source of truth: view label/color/pct helpers and palette binding live in theme.py / data_layer; no hardcoded hex or display label in views/charts."
  - "Defensive store reads (T-06-03): missing/empty store returns the schema-correct empty frame; each view renders the Empty/Error state and suppresses only its own tab."

requirements-completed: [DASH-01, DASH-02, DASH-03]

coverage:
  - id: D1
    description: "Dashboard package + locked dark theme (.streamlit/config.toml) + defensive data layer (load_setups/apply_filters/load_bars/healthy_config/setup_dir_guarded + UI-SPEC label/color/pct helpers) + the DASH-01 filterable setup table with honest P(win)/score_source composite and status chips."
    requirement: DASH-01
    verification:
      - kind: unit
        ref: tests/unit/test_dashboard_data.py#test_apply_filters_symbol_status_direction;test_apply_filters_min_prob;test_apply_filters_date_range_inclusive;test_apply_filters_sort_newest_first;test_load_setups_missing_store_returns_schema_frame;test_status_and_outcome_label_mappings;test_score_source_tag_and_color_honesty;test_pct_whole_percent_formatter
        status: pass
      - kind: automated_ui
        ref: tests/ui/test_dashboard_app.py#test_app_runs_with_four_tabs_and_health_strip
        status: pass
      - kind: automated_ui
        ref: tests/ui/test_dashboard_table.py#test_default_filters_list_all_fixture_setups;test_pwin_renders_with_score_source_tag;test_symbol_filter_narrows_rows;test_status_filter_narrows_rows;test_min_prob_filter_narrows_rows;test_reset_filters_restores_defaults
        status: pass
    human_judgment: false
  - id: D2
    description: "DASH-02 plotly candlestick with entry/SL/TP hlines (accent/bear/bull), sweep ◇ diamond marker from the evidence object, PD-zone add_shape bands (layer=below, ~14% opacity), and the locked 520px/margin/hovermode layout."
    requirement: DASH-02
    verification:
      - kind: automated_ui
        ref: tests/ui/test_dashboard_chart.py#test_candlestick_has_entry_sl_tp_hlines_and_candles;test_candlestick_sweep_diamond_present_when_evidence_has_sweep;test_candlestick_pd_zone_band_below_candles;test_candlestick_layout_locked;test_candlestick_empty_bars_returns_empty_figure;test_render_chart_path_renders_plotly
        status: pass
    human_judgment: false
  - id: D3
    description: "DASH-03 fixed-order evidence trace (setup header / bias / zone / sweep / ML contributors / LLM narrative) with agreement chip, honest score_source, and the ⌀ + reason fallback for an unavailable narrative; native widgets only (no unsafe_allow_html)."
    requirement: DASH-03
    verification:
      - kind: automated_ui
        ref: tests/ui/test_dashboard_evidence.py#test_evidence_sections_render_in_fixed_order;test_evidence_agreement_chip_and_ml_contributors_render;test_evidence_llm_unavailable_renders_circle_and_reason;test_evidence_malformed_evidence_json_degrades_without_raise
        status: pass
    human_judgment: false

# Metrics
duration: 41min
completed: 2026-09-04
status: complete
---

# Phase 6 Plan 2: Streamlit Setups Dashboard Summary

**Streamlit dashboard surface for the Setups experience: the locked dark theme, a defensive pure-reader data layer, a filterable/sortable setup table with the honest `P(win) [score_source]` composite and status chips (DASH-01), a locked-palette plotly candlestick with entry/SL/TP + sweep-diamond + PD-zone overlays (DASH-02), and the fixed-order evidence trace with an honest `⌀` fallback for an unavailable narrative (DASH-03).**

## Performance

- **Duration:** 41 min
- **Started:** 2026-09-04T13:51:37Z
- **Completed:** 2026-09-04T14:32:16Z
- **Tasks:** 3
- **Files created:** 16

## Accomplishments

- **`.streamlit/config.toml`** applies the locked `[theme]` (dark, `#00C7FF` primary, `#0B0F17`/`#141A26` backgrounds, `#E6EDF3` text) + `runOnSave=true` + `gatherUsageStats=false`.
- **`dashboard/theme.py`** is the single palette + binding source: `COLORS`, `STATUS_COLORS`, `OUTCOME_COLORS`, `AGREEMENT_COLORS`, `DIRECTION_COLORS`, `SCORE_SOURCE_COLORS` (heuristic → warning hue), the enum→human label maps, status glyphs, and metric labels — no hardcoded hex/labels elsewhere.
- **`dashboard/data_layer.py`** is the defensive pure-reader surface: `load_setups`/`load_bars` (never raise on a missing/empty store → schema-correct empty frame), `apply_filters` (symbol/status/direction/min-prob/date-range/sort), `load_cfg`/`config_path`/`get_config`, `data_root_guarded`/`healthy_config`/`setup_dir_guarded` (resolve-under-root guard, T-06-01), and the UI-SPEC label/color/`pct` honesty helpers.
- **`dashboard/charts.py`** builds the DASH-02 figure: `go.Candlestick` (bull `#26A69A`/bear `#EF5350`), entry/SL/TP `add_hline`s (accent/bear/bull), sweep `◇` diamond markers from the evidence object, PD-zone `add_shape` rects (`layer="below"`, ~14% opacity), and the locked layout (height 520, margin `l=8 r=8 t=24 b=8`, `hovermode="x unified"`); plus an `equity_curve` stub for plan 06-03.
- **`dashboard/app.py`** shell: `st.set_page_config(layout="wide")`, sticky health strip, four `st.tabs` (Setups/History/Performance/Health) dispatching per-view; `views_history`/`views_performance`/`views_health` are empty-state stubs (plan 06-03 fills them).
- **`dashboard/views_setups.py`**: `sidebar_filters` (symbol/status/direction/min-prob/date + Reset Filters via `on_click` callback + Refresh via `st.rerun()`, no `@st.cache_data` on the refresh path), `render_table` (sortable `st.dataframe`, `column_config`, status chips + `P(win) [source]` composite via pandas Styler honoring the binding, `on_select` single-row), `render` (drives the chart + evidence trace on selection), and `render_evidence` (DASH-03).
- **Offline AppTest suite** (`tests/ui/`) + pure data-layer tests (`tests/unit/test_dashboard_data.py`) — 18 Streamlit AppTest cases + 11 pure data-layer cases, all green.

## Task Commits

Each task was committed atomically:

1. **Task 1: Dashboard package, locked theme, defensive data layer** - `0ceb988` (feat)
2. **Task 2: App shell + Setups tab (table + filters) + candlestick with SMC overlays** - `33c3ee4` (feat)
3. **Task 3: Evidence trace view (DASH-03)** - `c52b8da` (feat)

**Plan metadata:** `(separate docs commit)`

## Files Created

- `.streamlit/config.toml` - locked dark theme + server/browser settings
- `src/ai_trading/dashboard/__init__.py` - package marker + convenience re-exports
- `src/ai_trading/dashboard/theme.py` - palette + color binding + label maps (single source)
- `src/ai_trading/dashboard/data_layer.py` - defensive reads + filters + guard + label helpers
- `src/ai_trading/dashboard/app.py` - wide app shell with health strip + 4 tabs
- `src/ai_trading/dashboard/charts.py` - candlestick + overlays + equity stub
- `src/ai_trading/dashboard/views_setups.py` - filters + table + selected chart + evidence trace
- `src/ai_trading/dashboard/views_history.py` / `views_performance.py` / `views_health.py` - empty-state stubs (DASH-04/05/06 deferred to 06-03)
- `tests/unit/_dashboard_fixtures.py` - dashboard fixture helpers (store/config/evidence builders)
- `tests/unit/test_dashboard_data.py` - pure data-layer tests
- `tests/ui/test_dashboard_app.py` / `test_dashboard_table.py` / `test_dashboard_chart.py` / `test_dashboard_evidence.py` - offline AppTest suites

## Decisions Made

- Table selection via `st.dataframe(on_select="rerun", selection_mode="single-row")`; the selected setup becomes the single visual anchor (chart + evidence).
- Reset Filters is an `on_click` callback that deletes the sidebar widget `session_state` keys (a widget key cannot be set after it is instantiated in the same run); Refresh just `st.rerun()` with no cache on the refresh path (UI-SPEC manual-refresh contract).
- The offline AppTest suites inject a fixture `config.toml` via `st.secrets["CONFIG_PATH"]` (or the `AITRADING_CONFIG` env var), booting the dashboard against an isolated tmp store with no live MT5/LLM.
- The dashboard is a pure reader of the persisted setup store + bars; it re-builds no setup statistics or levels.

## Deviations from Plan

None - plan executed exactly as written. (The Windows platform still cannot create directory symlinks, so the data-layer resolve-under-root traversal test uses the established `pytest.skip("directory symlinks unavailable on this platform")` convention — 1 skip, mirroring the Phase-6 store guard test.)

---

**Total deviations:** 0 auto-fixed.
**Impact on plan:** None; the plan contracts were honored as specified.

## Issues Encountered

- Streamlit `behavior` flags: `st.dataframe` / `st.plotly_chart` / `st.button` `use_container_width` is deprecated and slated for removal after 2025-12-31; switched to the supported `width="stretch"` API (applies today, given the current date).
- The sync `tests/ui/conftest.py` was initially created to add `tests/unit` to `sys.path` but shadowed the root `conftest` module (breaking `from conftest import`), so the ui tests use a per-file `sys.path` bootstrap with `# noqa: E402` instead.
- As in Phase 6 plan 1: Windows cannot create directory symlinks (`OSError` 1314), so the data-layer traversal-guard test skips (1 skip in the suite).

## User Setup Required

None - no external service configuration required for this plan (the dashboard reads only persisted stores; `llm_api_key` remains a gitignored `config.local.toml` secret. An interactive `streamlit run` needs a populated `config.local.toml` with `terminal_path`, as in prior phases.)

## Next Phase Readiness

- The Setups tab is the complete DASH-01/02/03 surface; the dashboard boots offline and the AppTest suites are green.
- Ready for 06-03: replace the `views_history` (`st.dataframe` over closed setups, newest-first), `views_performance` (KPI cards + cumulative-R equity curve + per-symbol breakdown via the `stats` functions), and `views_health` (per-feed freshness + MT5 status + error count) stubs with the full DASH-04/05/06 implementations.

---
*Phase: 06-setups-dashboard*
*Completed: 2026-09-04*

## Self-Check: PASSED

Verified on disk: `.streamlit/config.toml`, all 6 dashboard package modules
(theme/data_layer/app/charts/views_setups/views_history), and the 4 UI + 1 unit
test files exist; the individual task commits `0ceb988`, `33c3ee4`, `c52b8da`
are confirmed in `git log`; the offline suite (534 passed) and the Streamlit
AppTest suite (18 passed) are both green.
