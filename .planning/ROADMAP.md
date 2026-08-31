# Roadmap: AI Forex SMC Trading System

## Overview

This roadmap builds a signals-only AI forex trading system in dependency order: data foundation first (correct UTC-normalized MT5 ingestion is the root of all correctness), then the point-in-time SMC detection engine, then the backtesting/labeling engine that validates detection and produces ML training labels, followed by the hybrid AI layers (calibrated ML scoring, evidence-grounded LLM narrative), and finally the Streamlit dashboard that presents everything with verifiable evidence traces. Every phase enforces the project's single most important constraint: one shared, look-ahead-safe code path used by both live analysis and backtests.

## Phases

**Phase Numbering:**

- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: Data Foundation** - MT5 ingestion, UTC normalization, Parquet/SQLite stores, health checks, history report (completed 2026-08-30)
- [ ] **Phase 2: SMC Detection Engine** - Look-ahead-safe swings, liquidity pools, sweeps, premium/discount zones with lifecycle state
- [ ] **Phase 3: Backtesting & Labeling** - Shared-code-path replay, spread-modeled costs, triple-barrier labels, canonical + walk-forward stats
- [ ] **Phase 4: ML Scoring** - Point-in-time features, calibrated LightGBM probability, walk-forward evaluation, versioned artifacts
- [ ] **Phase 5: LLM Narrative Layer** - Evidence-grounded confirm/refute reasoning with agreement flag and ML-only fallback
- [ ] **Phase 6: Setups & Dashboard** - Setup assembly/lifecycle, Streamlit dashboard with charts, evidence traces, history, stats, health

## Phase Details

### Phase 1: Data Foundation

**Goal**: A reliable, UTC-normalized OHLC store fed from the local MT5 terminal for all 9 symbol/timeframe combinations, with health checks and known history bounds
**Depends on**: Nothing (first phase)
**Requirements**: DATA-01, DATA-02, DATA-03, DATA-04, DATA-05
**Success Criteria** (what must be TRUE):

  1. Collector connects to the running MT5 terminal, verifies all three symbols are selectable, and fails loudly with an actionable message when the terminal is closed or logged out
  2. Closed M15/H1/H4 bars for EURUSD, GBPUSD, USDJPY are stored in Parquet with UTC-normalized timestamps and raw server time preserved
  3. Restarting the collector backfills any gaps idempotently (no duplicate bars, no silent gaps)
  4. A history-availability report per symbol/timeframe is persisted and queryable

**Plans**: 3/3 plans complete

Plans:

- [x] 01-01-PLAN.md
- [x] 01-02-PLAN.md
- [x] 01-03-PLAN.md

**Wave 1**

- [x] 01-01: Project scaffold (uv, ruff, pytest, config with symbols/timeframes/broker offset) + store access layer (Parquet bars + SQLite meta)

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 01-02: MT5 client + collector service (initialize/shutdown lifecycle, symbol_select checks, incremental closed-bar polling, UTC normalization)

**Wave 3** *(blocked on Wave 2 completion)*

- [x] 01-03: Gap backfill + idempotency + history-availability report + timezone/DST validation tests

### Phase 2: SMC Detection Engine

**Goal**: Pure, point-in-time SMC detectors producing liquidity pools, sweep events, and premium/discount zones with lifecycle state across MTF context
**Depends on**: Phase 1
**Requirements**: SMC-01, SMC-02, SMC-03, SMC-04, SMC-05, SMC-06
**Success Criteria** (what must be TRUE):

  1. Swing detection is confirmation-shifted: repaint unit tests prove no detector output changes when future bars are appended
  2. Equal highs/lows cluster into pools with ATR-relative tolerance, and sweep events (take-out + reclaim) are distinguishable from pure breakouts
  3. Premium/discount zones derive from confirmed swing ranges and carry lifecycle state (unmitigated → mitigated → invalidated) updated bar-by-bar
  4. H1/H4 context joins to each M15 decision bar point-in-time (no "latest H4 row" lookahead)
  5. All detectors are pure DataFrame→DataFrame functions with pytest coverage

**Plans**: 2/4 plans executed

Plans:
**Wave 1**

- [x] 02-01-PLAN.md — Swing-point detection (confirmation-shifted) + repaint test suite

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 02-02-PLAN.md — Liquidity pools (equal highs/lows clustering) + sweep events with reclaim rule
- [ ] 02-03-PLAN.md — Premium/discount zones + zone/pool lifecycle state machine

**Wave 3** *(blocked on Wave 2 completion)*

- [ ] 02-04-PLAN.md — MTF point-in-time context join + detector integration tests

### Phase 3: Backtesting & Labeling

**Goal**: A bar-by-bar replay engine that runs the identical detector pipeline over history, models costs, labels outcomes, and reports canonical + walk-forward statistics
**Depends on**: Phase 2
**Requirements**: BT-01, BT-02, BT-03, BT-04, BT-05
**Success Criteria** (what must be TRUE):

  1. The backtester calls the same SMC/feature functions as live analysis (no separate backtest logic exists)
  2. Outcomes are computed net of spread (recorded bar spread) plus slippage buffer, and the backtester refuses ranges with insufficient stored history
  3. Labels follow the documented triple-barrier spec with the documented intrabar tie rule and are reproducible from raw setup + bar data
  4. Reports include win rate, PF, expectancy, max DD, avg R, trade count per symbol/timeframe, plus per-window walk-forward breakdowns

**Plans**: 3 plans

Plans:

- [ ] 03-01: Replay engine (bar-by-bar, historical-range validation) + cost model (spread + slippage)
- [ ] 03-02: Triple-barrier labeling with intrabar tie rule + canonical stats reports
- [ ] 03-03: Walk-forward harness + per-window reports

### Phase 4: ML Scoring

**Goal**: Calibrated setup-probability scoring with leak-free features and walk-forward evidence
**Depends on**: Phase 3
**Requirements**: AI-01, AI-02, AI-03, AI-04
**Success Criteria** (what must be TRUE):

  1. Features are assembled point-in-time from SMC state; a feature audit confirms nothing uses post-decision-bar information
  2. A LightGBM scorer outputs probabilities that are calibrated (reliability data recorded via CalibratedClassifierCV)
  3. Training/evaluation uses the walk-forward harness from Phase 3 — no shuffled splits anywhere
  4. Model artifacts (model + calibrator + feature metadata) are versioned and loadable by the scorer

**Plans**: 3 plans

Plans:

- [ ] 04-01: Feature builder from SMC state + point-in-time feature audit
- [ ] 04-02: LightGBM training + calibration + artifact versioning
- [ ] 04-03: Walk-forward evaluation reports + heuristic-score bootstrap for unlabeled periods

### Phase 5: LLM Narrative Layer

**Goal**: Evidence-grounded LLM confirm/refute reasoning as a separable, degradable component
**Depends on**: Phase 4
**Requirements**: AI-05, AI-06, AI-07
**Success Criteria** (what must be TRUE):

  1. The LLM receives only the structured evidence object and returns structured narrative + agree/disagree verdict; it never originates levels or probabilities
  2. Setups expose an ML↔LLM agreement flag
  3. With the LLM endpoint disabled or timing out, the pipeline still emits complete ML-only setups (graceful fallback proven by test)

**Plans**: 2 plans

Plans:

- [ ] 05-01: Provider interface (local vLLM via OpenAI SDK; Anthropic optional) + structured-output contract
- [ ] 05-02: Narrative pipeline (evidence serialization, citation check) + agreement flag + timeout fallback

### Phase 6: Setups & Dashboard

**Goal**: The product surface — scheduled setup assembly with lifecycle tracking, and a Streamlit dashboard presenting setups, evidence, history, stats, and health
**Depends on**: Phase 5
**Requirements**: SETUP-01, SETUP-02, SETUP-03, SETUP-04, DASH-01, DASH-02, DASH-03, DASH-04, DASH-05, DASH-06
**Success Criteria** (what must be TRUE):

  1. The scheduled engine assembles setups (direction, entry, SL, TP, RR, level rationale, evidence object) after M15 bar closes and persists them with lifecycle status updates (active → TP/SL/expired/invalidated)
  2. Dashboard setup table filters by symbol, status, direction, min probability, and date; sorting works
  3. Chart view renders candlesticks with entry/SL/TP markers plus sweep and PD-zone annotations; setup detail shows the full evidence trace
  4. History view shows lifecycle outcomes for every emitted setup; performance panel shows WR/PF/expectancy and an R-based equity curve aggregate and per symbol
  5. A health strip shows last-bar time per feed, MT5 connection status, and recent errors

**Plans**: 3 plans

Plans:

- [ ] 06-01: Setup assembly + persistence + lifecycle monitor + scheduled engine wiring (M15 close trigger)
- [ ] 06-02: Streamlit dashboard — setup table, chart with SMC overlays, evidence detail view
- [ ] 06-03: History with outcomes, performance stats panel, data-health strip

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4 → 5 → 6

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Data Foundation | 3/3 | Complete    | 2026-08-30 |
| 2. SMC Detection Engine | 2/4 | In Progress|  |
| 3. Backtesting & Labeling | 0/3 | Not started | - |
| 4. ML Scoring | 0/3 | Not started | - |
| 5. LLM Narrative Layer | 0/2 | Not started | - |
| 6. Setups & Dashboard | 0/3 | Not started | - |
