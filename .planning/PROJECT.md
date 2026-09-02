# AI Forex SMC Trading System

## What This Is

A Python-based AI trading assistant that ingests OHLC forex data from a local MetaTrader 5 terminal (via the official MetaTrader5 Python library), detects Smart Money Concepts (SMC) — focused on liquidity sweeps and premium/discount zones — and produces high-probability trade setups through hybrid AI analysis: a machine learning model scores setup probability while an LLM adds narrative reasoning and confirmation. Setups are presented in a web dashboard. Version 1 is signals-only.

## Core Value

Produce high-probability SMC-based forex trade setups with transparent, reasoned evidence the user can trust and verify.

## Requirements

### Validated

- [x] Ingest OHLC data from MT5 for EURUSD, GBPUSD, USDJPY on M15/H1/H4 via MetaTrader5 Python lib — Validated in Phase 1: Data Foundation (9/9 combos storing UTC-normalized bars; offset validated UTC+3, DST-dependent)
- [x] Detect SMC liquidity concepts: sweeps of equal highs/lows and premium/discount zones (built on swing-point detection) — Validated in Phase 2: SMC Detection Engine (pure deterministic detector chain swings→zigzag→pools→sweeps→zones→MTF context; point-in-time lookahead-safe; 177-test suite green, verification 30/30 must-haves)
- [x] Backtesting engine validates SMC detection and setup quality on historical MT5 data — Validated in Phase 3: Backtesting & Labeling (MT5-free replay engine calls the identical detector chain; triple-barrier labels with SL-first tie rule; costs = recorded spread + slippage; walk-forward reports; 358-test suite, verification 16/16 must-haves)

### Active

- [ ] ML model scores each setup's probability
- [ ] LLM produces narrative/confirmation reasoning per setup
- [ ] Web dashboard presents setups: direction, entry, SL, TP, probability, rationale

### Out of Scope

- Order execution (semi-auto/full-auto) — planned as the next milestone once v1 signals are trusted
- Order blocks, FVG/imbalance, BOS/CHoCH as first-class labeled features — v1 focuses on liquidity + PD zones; swing structure is built internally as a dependency, not as a user-facing feature
- Non-forex instruments (indices, crypto, metals) — forex majors only for v1
- Mobile app — web dashboard first
- External data vendors — MT5 endpoint is the sole data source for v1

## Context

- User runs Windows with a local MT5 terminal; the official MetaTrader5 Python package requires Windows and a running, logged-in terminal
- SMC methodology focus for v1: liquidity sweeps of equal highs/lows and premium/discount zones derived from swing ranges — PD zone detection depends on swing-point detection as a foundational internal component
- Hybrid AI approach: classic ML (probabilistic scoring over SMC-derived features) + LLM (narrative reasoning and confirmation over annotated market context); the two must remain separable components
- Multi-timeframe confluence: M15 execution bias informed by H1/H4 structure
- Backtesting against historical MT5 data is mandatory before trusting live signals

## Constraints

- **Tech stack**: Python; MetaTrader5 Python lib for market data — requires a running MT5 terminal on this Windows machine
- **Data source**: MT5 OHLC only — no third-party data vendors in v1
- **Instruments**: EURUSD, GBPUSD, USDJPY on M15/H1/H4
- **Scope**: v1 is signals-only — no order placement, no broker order APIs
- **Architecture**: ML scoring and LLM reasoning must be separable, independently testable components

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| v1 is signals-only; execution deferred to next milestone | Build trust in signal quality before automating risk | — Pending |
| Hybrid AI (ML scoring + LLM reasoning) | Combines quantitative probability with interpretable narrative confirmation | — Pending |
| MetaTrader5 Python lib for data feed | Official, reliable OHLC source from the user's local terminal | — Pending |
| Backtesting included in v1 | Validate SMC detection and setup quality on historical data before live use | — Proven in Phase 3 (identical-pipeline replay, walk-forward harness) |
| Backtest labeling conventions: triple-barrier with SL-first intrabar tie; entry candidates = sweep + zone tap | Conservative, reproducible labels (D-01…D-22 in Phase 3 CONTEXT.md) | — Validated in Phase 3 |
| SMC scope: liquidity sweeps + premium/discount zones | User-selected v1 focus; swing detection built as internal dependency | — Pending |
| Web dashboard as delivery interface | Rich presentation of setups, history, and stats | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-09-02 after Phase 3 (Backtesting & Labeling) completion*
