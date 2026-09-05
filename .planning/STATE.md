---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
current_phase: 6
current_phase_name: Setups & Dashboard
status: verifying
stopped_at: Completed 06-03-PLAN.md
last_updated: "2026-09-04T15:02:11.029Z"
last_activity: 2026-09-04
last_activity_desc: Phase 6 execution started
progress:
  total_phases: 6
  completed_phases: 5
  total_plans: 18
  completed_plans: 17
  percent: 83
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-08-29)

**Core value:** Produce high-probability SMC-based forex trade setups with transparent, reasoned evidence the user can trust and verify
**Current focus:** Phase 6 — Setups & Dashboard

## Current Position

Phase: 6 (Setups & Dashboard) — EXECUTING
Plan: 3 of 3
Status: Phase complete — ready for verification
Last activity: 2026-09-04 — Phase 6 execution started

Progress: [███████░░░] 67%

## Performance Metrics

**Velocity:**

- Total plans completed: 15
- Average duration: —
- Total execution time: —

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 1 | 3 | - | - |
| 2 | 4 | - | - |
| 03 | 3 | - | - |
| 04 | 3 | - | - |
| 05 | 2 | - | - |

**Recent Trend:**

- Last 5 plans: —
- Trend: —

*Updated after each plan completion*
| Phase 01 P01 | 11min | 4 tasks | 16 files |
| Phase 01 P02 | 3min | 4 tasks | 5 files |
| Phase 2 P01 | 25 min | 3 tasks | 7 files |
| Phase 2 P02 | 30 min | 3 tasks | 3 files |
| Phase 2 P03 | 30 min | 3 tasks | 3 files |
| Phase 2 P04 | 60 min | 3 tasks | 7 files |
| Phase 03 P01 | 82min | 3 tasks | 17 files |
| Phase 03 P02 | 20min | 3 tasks | 6 files |
| Phase 03 P03 | 66min | 3 tasks | 7 files |
| Phase 04-ml-scoring P01 | 1h 50m | 3 tasks | 12 files |
| Phase 04-ml-scoring P02 | ~40m | 3 tasks | 11 files |
| Phase 04-ml-scoring P03 | 40 min | 3 tasks | 7 files |
| Phase 05-llm-narrative-layer P01 | 16 min | 3 tasks | 14 files |
| Phase 05-llm-narrative-layer P02 | 16min | 3 tasks | 12 files |
| Phase 06 P01 | 52 min | 4 tasks | 17 files |
| Phase 06-setups-dashboard P02 | 41 min | 3 tasks | 18 files |
| Phase 06 P03 | 15 min | 3 tasks | 8 files |

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- [Init]: v1 is signals-only; order execution is the next milestone
- [Init]: Hybrid AI — calibrated ML owns probability; LLM only narrates/confirm-refutes structured evidence
- [Init]: One shared, look-ahead-safe code path for live analysis AND backtests (non-negotiable)
- [Init]: Stack locked per research: Python 3.12, metatrader5 5.0.6147, pandas, LightGBM+sklearn, SQLite+Parquet, Streamlit v1
- [Phase 01]: Symbol config validation accepts an optional .broker suffix (regex ^[A-Z]{6}(\.[A-Za-z0-9]+)?$) — widens research assumption A5 for plan 01-02 suffixed names
- [Phase 01]: merge_and_write is the single Parquet write path: atomic tmp+os.replace, dedup on raw bar-open time keep=last, .tmp cleaned up even on failed writes
- [Phase 01]: assert_closed_bars strips tz from an aware now_utc before comparing to naive time_utc — broker columns stay naive
- [Phase 01]: metatrader5 5.0.6147 vendor-binary install approved by human legitimacy checkpoint (Task 1) before any uv add ran
- [Phase 01]: Broker offset human-confirmed UTC+3 (2026-08-30) and persisted with validated_at; DST-dependent - expected +2 after US summer time ends (early November); re-validate at DST transitions
- [Phase 01]: Task 4 weekend rule applied - poisoned -36 weekend tick sample flagged by offset_drift_detected and NOT persisted; human confirmation replaced the weekday sample; H4 21:00-UTC grid anchor independently corroborates +3
- [Phase 01]: FakeMT5Client recording + per-(symbol, timeframe) deque hooks fixed in conftest so plan 01-03 tests consume them without extending conftest
- [Phase 03]: run_chain derives zones15 (M15 zones) alongside the Phase 2 composition - the D-01 zone tap consumes chain[zones15] — Plan 03-01 replay spec requires M15 zones for the tap; same derive_zones export keeps BT-01 intact
- [Phase 03]: Cost convention A1 pinned: bid-side bars, long crosses spread at entry, short at exit; slippage adversely on both fills — Locked by test_long_short_cost_symmetry; human eyeball recorded in 03-USER-SETUP.md
- [Phase 03]: D-09 TP liveness convention: opposite pools resolved at/before the decision bar are excluded from TP candidates; ties resolve to the pool — D-09 silent on liveness - planner convention documented in candidates.py docstring
- [Phase 03]: profit_factor pinned as a decided-trade ratio (TIMEOUT rows excluded from both R-sign sums) — the plan hand-pinned PF == 1.5 on a series whose all-rows sum would give 1.5/1.1; A4-consistent reading chosen, documented in stats.py
- [Phase ?]: Phase 03 plan 03: walk-forward windows derive over the COMBINED label domain so window_id boundaries are shared across symbols and the D-22 per-window aggregate is well-defined (identical to per-symbol derivation for single-symbol runs)
- [Phase ?]: Phase 03 plan 03: build_windows loop bound b_k <= end so a boundary-aligned max entry_time is still covered by the half-open window - required by the exactly-one-window contract, never emits empty trailing windows
- [Phase ?]: Phase 03 plan 03: --min-history-days override rebuilds the frozen Config via dataclasses.replace (never setattr, no signature threading); zero-candidate runs exit 0 with schema-correct empty artifacts per the exit-code contract
- [Phase ?]: FEATURE_SPEC is the ordered source of truth for ml_feature_list_version (18 features: 5 categorical + 13 numeric), each declaring dtype/source_tier/source_columns/stamp_kind
- [Phase ?]: build_feature_frame emits a 20-col frame (18 FEATURE_SPEC names + entry_time + decision_close_time); decision-close R:R recomputed (never fill-based rr); decision bar located via searchsorted-minus-one (session-gap robust); L1 audit uses non-strict decision_close_time<=prefix_close horizon
- [Phase 04-ml-scoring]: Embargo default 0 (purge-only) in ml/purge.py: the 96-bar barrier already removes every overlapping label, so embargo only guards regime continuity and costs train depth on the tiny store; ml_embargo_bars knob keeps it reversible after deep backfill — OQ5 purge semantics with the exit-bar OPEN-time boundary; documented in the module docstring (A1 rationale)
- [Phase 04-ml-scoring]: FEATURE_LIST_VERSION=1 added to ml/features.py as the loader's current-FEATURE_SPEC source of truth; model bundles are not byte-deterministic (pickle framing) - determinism pinned at the probability and manifest (config_hash) levels — Pitfall 10 + research determinism deviation note: version gates at the artifact boundary, probability-level reproducibility
- [Phase 04-ml-scoring]: fit_calibrated takes folds as a REQUIRED positional argument (no default) passing cv=folds + ensemble=True; refuses fewer than 2 explicit folds with a skip reason rather than silent uncalibrated fallback — SC3 no-shuffled-splits rule made structural (AST-pinned) and SC2 never-fabricate-a-model
- [Phase ?]: All-positive WEIGHTS on normalized goodness (inversion encodes smaller-is-better); EvalResult as singular eval surface; artifact save gated on --write; per-symbol audit aggregation; heuristic quality deferred to Phase 5/6
- [Phase ?]: citation_check value-match is contradiction-detection on scalar enum fields; numeric fields (p_win/contributors) are existence-checked only (research OQ3)
- [Phase 05-llm-narrative-layer]: run_narrative_pipeline returns a complete NarrativeResult on every path; the ML-only fallback is labeled (narrative_status=llm_unavailable, reason=timeout|error|llm_disabled), never silence (research OQ2)
- [Phase 06]: Setup entry = decision-bar M15 close (pinned A3); limit trigger on later bar high/low crossing entry.
- [Phase 06]: score_source promoted to ml_llm only when a verified narrative attaches; otherwise scorer ml (UI-SPEC honesty rule).
- [Phase 06]: run_engine_once accepts injectable scorer/llm_provider (defaulting to load_scorer/OpenAICompatProvider) so offline tests need no trained model or live LLM.
- [Phase 06]: Setup store = dedup-on-setup_id Parquet, atomic tmp+os.replace, resolve-under-data-root guard; bar-position columns float64 to allow null trigger/exit index.
- [Phase 06-setups-dashboard]: Selection drives the DASH-02/03 anchor: the setup table uses st.dataframe on_select single-row; selecting a row renders the candlestick + full evidence trace as the single visual focal point
- [Phase 06-setups-dashboard]: Reset Filters uses an on_click callback deleting the sidebar widget session_state keys (a widget key cannot be SET after instantiation in the same run); the Refresh path has no @st.cache_data per the UI-SPEC manual-refresh contract
- [Phase 06-setups-dashboard]: The offline AppTest suites inject a fixture config via st.secrets['CONFIG_PATH'] (and the AITRADING_CONFIG env var), so the dashboard boots and is tested against an isolated tmp store with no live MT5/LLM
- [Phase 06]: Performance R basis (A4): the Performance panel uses the structural r_gross from each resolved setup (entry vs SL distance); data_layer maps tp_hit->WIN / sl_hit->LOSS / expired->TIMEOUT and sets both r_raw and r_net to r_gross so it reuses backtest.stats.stats_by_symbol_timeframe unchanged; the live-vs-backtest comparability caveat (D-01/D-04) is surfaced as a panel caption.
- [Phase 06]: Health status semantics (OQ4): the strip shows last-persisted state only - per-feed last-bar time from the bar store and a collector heartbeat from the meta collection_state.last_success_at; 'MT5 disconnected'/stale renders the UI-SPEC copy when the heartbeat is old; there is no live MT5 probe in the dashboard.
- [Phase 06]: Recent errors are derived from the meta store's existing bar_gaps records (data-quality gaps detected in the last N days) surfaced as the health recent-errors count, via the new single-purpose helpers collection_state_heartbeats / recent_bar_gaps; no new errors table.

### Pending Todos

- [2026-09-05] Fix LLM vLLM endpoint 404 (llm)
- [2026-09-05] Add BTCUSD symbol for weekend data capture (config)

### Blockers/Concerns

- [Init]: Subagent (Task tool) spawns aborted repeatedly in this runtime — research completed inline; prefer inline execution if subagent spawns fail again
- [Init - resolved 2026-08-30]: Broker server timezone offset validated empirically (plan 01-02 Task 4): human-confirmed UTC+3, DST-dependent — re-validate at DST transitions (plan 01-03 owns the re-derivation guard)
- [Init]: MT5 terminal must be running and logged in for any collector work

## Deferred Items

Items acknowledged and carried forward from previous milestone close:

| Category | Item | Status | Deferred At |
|----------|------|--------|-------------|
| *(none)* | | | |

## Session Continuity

Last session: 2026-09-05
Stopped at: Session resumed — Phase 6 executed & verified (10/10, human_needed); awaiting human UAT checks
Resume file: None
