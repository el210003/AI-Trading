---
phase: 06-setups-dashboard
plan: 01
subsystem: backtest-engines
tags: setup-engine, m15-scheduler, smc, ml, llm, parquet, streamlit, plotly, ats

# Dependency graph
requires:
  - phase: 03-backtesting-labeling
    provides: candidate_at_bar / CandidateState / compute_rr / walk_barriers / run_chain (reused verbatim, D-03 / BT-01)
  - phase: 04-ml-scoring
    provides: features_at_decision / load_scorer / Scorer.score / Scorer.contributors
  - phase: 05-llm-narrative-layer
    provides: serialize_evidence / run_narrative_pipeline / NarrativeResult
  - phase: 01-data-foundation
    provides: bar_store.read_bars / collector.seconds_until_next_close (M15-close trigger)
provides:
  - ai_trading.setup package: assembly, lifecycle, store, scheduler, CLI
  - MT5-free setup-engine surface (assemble + persist + lifecycle-resolve per M15 close)
  - dedup-on-setup_id atomic Parquet setup store (SETUP-01/02)
  - config setup_trigger_window_bars / setup_min_p_win knobs
affects: 06-02 (dashboard), 06-03 (dashboard data/health), 05 (narrative reader), 04 (score provenance)

# Tech tracking
tech-stack:
  added: streamlit>=1.39 (1.63.0), plotly>=5.23 (7.0.0)
  patterns: setup record = dataclass-shaped dict matching SETUP_COLUMNS; atomic tmp+os.replace store; point-in-time as-of assembly; verbatim Phase 3/4/5 pure-function reuse (BT-01)

key-files:
  created:
    - src/ai_trading/setup/__init__.py
    - src/ai_trading/setup/store.py
    - src/ai_trading/setup/assembly.py
    - src/ai_trading/setup/lifecycle.py
    - src/ai_trading/setup/scheduler.py
    - src/ai_trading/setup/__main__.py
    - tests/unit/_setup_fixtures.py
    - tests/unit/test_setup_store.py
    - tests/unit/test_setup_assembly.py
    - tests/unit/test_setup_lifecycle.py
    - tests/unit/test_setup_engine.py
  modified:
    - pyproject.toml (streamlit marker + addopts)
    - uv.lock
    - config.toml (setup_* keys)
    - src/ai_trading/config.py (setup_* fields / _REQUIRED_KEYS / _validate)
    - tests/conftest.py (_make_cfg defaults)
    - tests/unit/test_backtest_config.py
    - tests/unit/test_normalize_and_config.py

key-decisions:
  - "Setup entry price = the decision-bar M15 close (pinned A3); D-01 limit trigger on a later bar's high/low crossing it."
  - "score_source promoted to ml_llm only when a verified narrative attaches; otherwise the scorer's ml (UI-SPEC honesty rule)."
  - "run_engine_once accepts an injectable scorer/llm_provider (defaults to load_scorer / OpenAICompatProvider) so offline tests need no trained model or live LLM."
  - "Setup store = dedup-on-setup_id Parquet written atomically (tmp + os.replace) under a resolve-under-data-root guard; bar-position columns stored as float64 to allow a pending setup's null trigger/exit index."

patterns-established:
  - "As-of assembly: per-tier visible_mask anchors (STAMP_BAR events/zones, STAMP_CLOSE pools/swings), payload-row as-is — no future data."
  - "Active-exit resolvers reuse walk_barriers verbatim so live R matches backtest R (D-03)."
  - "Engine suppression: one pending/active setup per symbol at a time (D-05)."

requirements-completed: [SETUP-01, SETUP-02, SETUP-03, SETUP-04]

coverage:
  - id: D1
    description: "Setup persistence store: SETUP_COLUMNS, resolve-under-root guard, read_setups empty-schema contract, dedup-on-setup_id atomic rewrite."
    requirement: SETUP-01
    verification:
      - kind: unit
        ref: tests/unit/test_setup_store.py#test_round_trip_read_equals_written;test_upsert_dedup_on_setup_id_keep_last;test_atomic_rewrite_leaves_no_tmp
        status: pass
    human_judgment: false
  - id: D2
    description: "Setup assembly: fully-evidenced pending record (decision-bar-close entry, rr_at_decision, evidence_json round-trip, p_win/score_source provenance, AI-07 labeled fallback, ml_llm promotion, prefix-stability)."
    requirement: SETUP-02
    verification:
      - kind: unit
        ref: tests/unit/test_setup_assembly.py#test_candidate_fires_with_pinned_entry_and_rr;test_evidence_roundtrip_and_provenance;test_ai07_fallback_labeled_when_llm_disabled;test_score_source_promoted_to_ml_llm_on_verified_narrative
        status: pass
    human_judgment: false
  - id: D3
    description: "Lifecycle state machine: pending -> active (limit trigger) / invalidated (zone break, D-04) / expired (window); active -> tp_hit / sl_hit / expired (96-bar barrier) via walk_barriers, with D-10 SL-first tie and D-11 gap-open fill honored."
    requirement: SETUP-03
    verification:
      - kind: unit
        ref: tests/unit/test_setup_lifecycle.py#test_pending_trigger_becomes_active;test_pending_structure_break_invalidates;test_pending_window_expires;test_active_tp_hit_with_correct_r_gross;test_active_sl_hit_with_correct_r_gross;test_active_time_barrier_expires;test_active_gap_open_beyond_barrier_is_d11;test_active_sl_first_tie_on_one_bar_is_d10
        status: pass
    human_judgment: false
  - id: D4
    description: "Scheduled engine + CLI: run_engine_once assembles/persists per non-suppressed symbol (D-05), terminal setups not re-resolved, MT5-free; CLI --once/--monitor exit-code contract (2/1/0)."
    requirement: SETUP-04
    verification:
      - kind: unit
        ref: tests/unit/test_setup_engine.py#test_run_engine_once_assembles_and_persists;test_run_engine_once_suppresses_second_setup_d05;test_run_engine_once_keeps_terminal_setup;test_setup_package_is_mt5_free
        status: pass
      - kind: manual_procedural
        ref: "python -m ai_trading.setup --once -> exit 0"
        status: pass
    human_judgment: false
  - id: D5
    description: "Config setup_trigger_window_bars / setup_min_p_win end-to-end (dataclass + _REQUIRED_KEYS + _validate + load_config + config.toml + conftest + config test suites) and streamlit/plotly installed + importing with the streamlit pytest marker registered."
    verification:
      - kind: unit
        ref: tests/unit/test_backtest_config.py#test_load_config_carries_backtest_knobs;tests/unit/test_setup_store.py
        status: pass
    human_judgment: false

# Metrics
duration: 52min
completed: 2026-09-04
status: complete
---

# Phase 6 Plan 1: Setup Engine & Store Summary

**MT5-free setup surface: a per-M15-close engine that assembles a fully-evidenced live setup (reusing Phase 3/4/5 pure functions verbatim), persists it via a dedup-on-setup_id atomic Parquet store, and resolves its full lifecycle (pending -> active -> tp_hit/sl_hit/expired/invalidated) using the exact backtest `walk_barriers` resolver.**

## Performance

- **Duration:** 52 min
- **Started:** 2026-09-04 (session start)
- **Completed:** 2026-09-04
- **Tasks:** 4 (Task 1 = approved package-legitimacy checkpoint; Tasks 2-4 implemented)
- **Files modified:** 17

## Accomplishments

- Installed `streamlit>=1.39` (1.63.0) and `plotly>=5.23` (7.0.0); registered the `streamlit` pytest marker and set the default offline addopts to `-m "not mt5 and not llm and not streamlit"`.
- Extended `Config` with `setup_trigger_window_bars=8` and `setup_min_p_win=0.0` across all four required sites (dataclass, `_REQUIRED_KEYS`, `_validate`, `load_config`) plus `config.toml`, `tests/conftest._make_cfg`, and the two config test harnesses.
- `setup/store.py`: `SETUP_COLUMNS` schema, `setup_store_root`/`setup_store_path` (resolve-under-data-root guard, ASVS V4 / T-06-01), `read_setups` (schema-correct empty-frame contract), `upsert_setups` (dedup on `setup_id` keep="last", deterministic sort, atomic tmp+`os.replace` rewrite, never leaves a `.tmp`).
- `setup/assembly.py`: `assemble_setup` reuses `run_chain`, `candidate_at_bar`, `features_at_decision`, `compute_rr`, `scorer.score`/`contributors`, `serialize_evidence`, and `run_narrative_pipeline` verbatim (BT-01 / D-03); decision-bar-close entry (A3), as-of filers via the exact per-tier `visible_mask` anchors, `score_source` → `ml_llm` only on a verified narrative, AI-07 labeled fallback, JSON-safe evidence serialization, and a `build_setup_record` helper that names every field.
- `setup/lifecycle.py`: `resolve_pending` (D-01 limit trigger on bar high/low crossing entry, D-04 zone-break invalidation and N-bar window expiry), `resolve_active` reusing `walk_barriers` verbatim (WIN→tp_hit, LOSS→sl_hit, TIMEOUT→expired with `r_gross`/`r_raw`/`r_net`), and `apply_lifecycle` (pure, skips terminal statuses, fills trigger/exit fields).
- `setup/scheduler.py` + `setup/__main__.py`: `run_engine_once` (reads closed bars per symbol, assembles one setup per non-suppressed symbol — D-05 one-live-setup-per-symbol — resolves the lifecycle, persists atomically; MT5-free), `should_run_on_m15_close`, a drift-corrected `--monitor` loop via collector `seconds_until_next_close`, and the `--once`/`--monitor` CLI honoring the 2/1/0 exit-code contract.

## Task Commits

Each task was committed atomically:

1. **Task 1: Verify streamlit/plotly package legitimacy** — blocking `checkpoint:human-verify` (approved externally); no code commit.
2. **Task 2: Install streamlit/plotly, extend Config with setup_* knobs, implement the setup store** - `c866e32` (feat)
3. **Task 3: Implement setup assembly (SetupRecord)** - `d79155f` (feat)
4. **Task 4: Implement lifecycle monitor + scheduled M15-close engine CLI** - `10c9238` (feat)

**Plan metadata:** (committed in the final docs commit)

## Files Created/Modified

- `src/ai_trading/setup/store.py` - Parquet setup store: SETUP_COLUMNS, resolve-under-root guard, read/upsert (dedup, atomic)
- `src/ai_trading/setup/assembly.py` - assemble_setup / build_setup_record reusing Phase 3/4/5 pure functions
- `src/ai_trading/setup/lifecycle.py` - resolve_pending / resolve_active / apply_lifecycle
- `src/ai_trading/setup/scheduler.py` - run_engine_once / should_run_on_m15_close / CLI main
- `src/ai_trading/setup/__main__.py` - module entry (`python -m ai_trading.setup`)
- `src/ai_trading/setup/__init__.py` - public re-exports of the setup surface
- `src/ai_trading/config.py`, `config.toml`, `pyproject.toml`, `uv.lock` - setup_* knobs, streamlit marker + addopts, streamlit/plotly deps
- `tests/unit/_setup_fixtures.py`, `test_setup_store.py`, `test_setup_assembly.py`, `test_setup_lifecycle.py`, `test_setup_engine.py` - new test suites
- `tests/conftest.py`, `tests/unit/test_backtest_config.py`, `tests/unit/test_normalize_and_config.py` - config defaults/harness updates

## Decisions Made

- Setup `entry` = decision-bar close (pinned A3), with the D-01 limit trigger firing on a later M15 bar's high/low crossing it.
- `score_source` promoted to `ml_llm` only when a verified narrative attaches (`narrative_status == "ok"`); otherwise the scorer's `"ml"` is kept.
- `run_engine_once` accepts an injectable `scorer`/`llm_provider` (defaulting to `load_scorer` / `OpenAICompatProvider`) so offline tests need no trained model artifact or live LLM.
- Store bar-position columns (`entry_bar_idx`/`trigger_bar_idx`/`exit_idx`) as `float64` so a still-pending setup's null trigger/exit index serializes cleanly.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Store string-typed `status`/`outcome` columns** - Found during: Task 2 | Issue: the `SETUP_COLUMNS` string set omitted `status`/`outcome`, so `_coerce` tried to cast them to float64 and raised `could not convert string to float: 'pending'` on round-trip. | Fix: added `status`/`outcome` to `_STR_COLS`. | Files: `src/ai_trading/setup/store.py`. | Verification: `test_setup_store.py` round-trip green.

**2. [Rule 1 - Bug] Non-JSON-serializable evidence object** - Found during: Task 3 | Issue: the `serialize_evidence` object carries nullable `bias_h1`/`bias_h4` (`pd.NA`), so `json.dumps(evidence)` raised `TypeError`. | Fix: added a `_json_default` encoder that renders `pd.NA`/`NaT`/`NaN` as `null` and collapses numpy/pandas scalars. | Files: `src/ai_trading/setup/assembly.py`. | Verification: `test_evidence_roundtrip_and_provenance` green.

**3. [Rule 3 - Blocking] New `_REQUIRED_KEYS` broke the config test harnesses** - Found during: Task 2 | Issue: adding `setup_*` to `_REQUIRED_KEYS` made `load_config` reject the hand-built configs in `test_normalize_and_config.py` (17 failures). | Fix: added the `setup_*` keys to that harness's `_base_values`. | Files: `tests/unit/test_normalize_and_config.py`. | Verification: full offline suite green (523 passed).

**4. [Rule 1 - Bug] Engine fake-scorer retry consumed the timeout** - Found during: Task 3 | Issue: with `llm_max_retries=1` the narrative pipeline retries once (2 attempts), so a single scripted `TimeoutError` was consumed and the retry hit "no scripted response" (`reason="error"` instead of `"timeout"`). | Fix: scripted two `TimeoutError`s in the AI-07 fallback test. | Files: `tests/unit/test_setup_assembly.py`. | Verification: `test_ai07_fallback_labeled_on_timeout` green.

**5. [Rule 1 - Bug] MT5-free check tripped on docstring prose** - Found during: Task 4 | Issue: the invariant test asserted `"MetaTrader5" not in source`, but module docstrings legitimately reference it. | Fix: scoped the check to actual import statements (`import metatrader5` / `from metatrader5` / `mt5_client`). | Files: `tests/unit/test_setup_engine.py`. | Verification: `test_setup_package_is_mt5_free` green.

---

**Total deviations:** 5 auto-fixed (4 Rule 1 bugs, 1 Rule 3 blocking).
**Impact on plan:** All fixes were necessary for correctness/robustness. No scope creep; plan contracts honored.

## Issues Encountered

- Windows environment cannot create directory symlinks (`OSError` 1314), so the store traversal-guard test (and the pre-existing Phase 4 analogue) uses the established `pytest.skip("directory symlinks unavailable on this platform")` convention — 1 skip in the suite.

## User Setup Required

None - no external service configuration required for this plan (streamlit/plotly install + config keys are self-contained; `llm_api_key` remains a gitignored `config.local.toml` secret handled elsewhere).

## Next Phase Readiness

- The `ai_trading.setup` surface is complete and exported (`assemble_setup`, `build_setup_record`, `resolve_pending`, `resolve_active`, `apply_lifecycle`, `run_engine_once`, store read/upsert/path APIs, `SETUP_COLUMNS`).
- Ready for 06-02 / 06-03 (Streamlit dashboard reading the setup store, bars, and reports). The dashboard becomes a pure reader of `read_setups` + the `evidence_json`/`NarrativeResult` fields.
- Note: live active-setup `r_gross` is structural (v1 signals-only, A4); the walk-forward comparability caveat is documented in the Performance panel (a 06-03/06-02 concern).

---
*Phase: 06-setups-dashboard*
*Completed: 2026-09-04*

## Self-Check: PASSED

Verified on disk: all 6 `ai_trading.setup` package files + 5 test files + the SUMMARY file exist; commits `c866e32`, `d79155f`, `10c9238` confirmed in `git log`.
