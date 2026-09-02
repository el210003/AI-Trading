---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
current_phase: 03
current_phase_name: backtesting-labeling
status: executing
stopped_at: Completed 03-02-PLAN.md (barrier walk, canonical stats, artifact writers; 320 tests green)
last_updated: "2026-09-02T04:56:38.951Z"
last_activity: 2026-09-02
last_activity_desc: Phase 03 execution started
progress:
  total_phases: 6
  completed_phases: 2
  total_plans: 10
  completed_plans: 8
  percent: 33
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-08-29)

**Core value:** Produce high-probability SMC-based forex trade setups with transparent, reasoned evidence the user can trust and verify
**Current focus:** Phase 03 — backtesting-labeling

## Current Position

Phase: 03 (backtesting-labeling) — EXECUTING
Plan: 3 of 3
Status: Ready to execute
Last activity: 2026-09-02 — Phase 03 execution started

Progress: [███████░░░] 67%

## Performance Metrics

**Velocity:**

- Total plans completed: 7
- Average duration: —
- Total execution time: —

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 1 | 3 | - | - |
| 2 | 4 | - | - |

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

### Pending Todos

None yet.

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

Last session: 2026-09-02T04:56:38.942Z
Stopped at: Completed 03-02-PLAN.md (barrier walk, canonical stats, artifact writers; 320 tests green)
Resume file: None
