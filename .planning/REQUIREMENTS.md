# Requirements: AI Forex SMC Trading System

**Defined:** 2026-08-29
**Core Value:** Produce high-probability SMC-based forex trade setups with transparent, reasoned evidence the user can trust and verify

## v1 Requirements

Requirements for initial release. Each maps to roadmap phases.

### Data Ingestion

- [x] **DATA-01**: System connects to the local MT5 terminal and verifies health at startup (initialize success, each symbol selectable via symbol_select)
- [x] **DATA-02**: System collects closed-bar OHLC data for EURUSD, GBPUSD, USDJPY on M15/H1/H4 via the MetaTrader5 Python library
- [x] **DATA-03**: All stored bar timestamps are UTC-normalized, with the broker server offset held as validated configuration
- [x] **DATA-04**: Bar collection performs incremental updates with gap backfill and is idempotent across restarts
- [x] **DATA-05**: System reports available history depth per symbol/timeframe and persists it for backtest range validation

### SMC Detection

- [x] **SMC-01**: System detects swing highs/lows using confirmation-shifted logic (a swing exists only after its confirmation bar — non-repainting)
- [x] **SMC-02**: System clusters equal highs/lows into liquidity pools using ATR-relative tolerance per instrument
- [x] **SMC-03**: System emits sweep events when a pool level is taken out and reclaimed, distinguishing sweeps from pure breakouts
- [x] **SMC-04**: System derives premium/discount zones from confirmed swing ranges with configurable range-selection rules
- [x] **SMC-05**: Every pool and zone carries lifecycle state (unmitigated → mitigated → invalidated) updated bar-by-bar
- [x] **SMC-06**: Higher-timeframe context (H1/H4) is joined point-in-time as of each M15 decision bar's timestamp

### AI Analysis

- [x] **AI-01**: ML features are assembled point-in-time from SMC state (no information after the decision bar)
- [x] **AI-02**: Each candidate setup receives an ML probability score from a gradient-boosted model
- [x] **AI-03**: ML scores are calibrated (isotonic/Platt) so displayed probabilities are honest
- [x] **AI-04**: ML training/evaluation follows a walk-forward protocol with no shuffled splits on time series
- [x] **AI-05**: Each setup receives an LLM narrative that confirms or refutes using only the structured evidence object
- [x] **AI-06**: Setups expose an ML↔LLM agreement flag (agree/disagree with confidence)
- [x] **AI-07**: System degrades gracefully to ML-only setups when the LLM endpoint is unavailable or slow

### Trade Setups

- [ ] **SETUP-01**: Each setup record contains symbol, direction, entry, SL, TP, R:R ratio, and the reason each level was chosen
- [ ] **SETUP-02**: Each setup persists an evidence object (zone IDs, sweep events, MTF bias, ML score contributors) consumable by LLM and dashboard
- [ ] **SETUP-03**: Setup lifecycle is tracked (active → TP hit / SL hit / expired / invalidated) via bar-close monitoring
- [ ] **SETUP-04**: Untriggered setups expire or invalidate per documented rules (N-bar window / structure break)

### Backtesting

- [x] **BT-01**: The backtester replays the identical pipeline bar-by-bar used by live analysis (one shared code path)
- [x] **BT-02**: Backtest outcomes model spread (from recorded bar spread) plus a slippage buffer; metrics reported net of costs
- [x] **BT-03**: Outcomes are labeled with triple-barrier logic and a documented intrabar tie rule (SL-first conservative default)
- [x] **BT-04**: Backtests report canonical stats (win rate, profit factor, expectancy, max drawdown, avg R, trade count) per symbol/timeframe
- [x] **BT-05**: Backtests produce per-time-window (walk-forward) reports to expose regime shifts

### Dashboard

- [ ] **DASH-01**: Dashboard shows a setup table with filters (symbol, status, direction, min probability, date range)
- [ ] **DASH-02**: Dashboard renders a candlestick chart with entry/SL/TP markers plus sweep and PD-zone annotations
- [ ] **DASH-03**: Each setup detail view displays its full evidence trace (zones, sweeps, bias, ML contributors, LLM narrative)
- [ ] **DASH-04**: Dashboard shows setup history with lifecycle outcomes for every emitted signal
- [ ] **DASH-05**: Dashboard shows performance stats (win rate, PF, expectancy, equity curve in R) aggregate and per symbol
- [ ] **DASH-06**: Dashboard shows a data/pipeline health strip (last bar time per feed, MT5 connection status, errors)

## v2 Requirements

Deferred to future release. Tracked but not in current roadmap.

### Execution (next milestone)

- **EXEC-01**: User can approve a signal for semi-auto execution via MT5 order_send
- **EXEC-02**: System can place orders automatically when setups pass configured filters (full-auto)

### SMC Expansion

- **SMCX-01**: Order blocks detected as first-class features (backtest-validated before UI exposure)
- **SMCX-02**: Fair value gaps / imbalances detected as first-class features
- **SMCX-03**: BOS/CHoCH structure-shift labeling

### Enhancements

- **ENH-01**: Calibration reliability report displayed in dashboard
- **ENH-02**: Per-pattern historical stats surfaced on live setups ("this pattern: 58% over 24 months")
- **ENH-03**: Session/kill-zone features and filters (London/NY)
- **ENH-04**: Alerts via browser notifications or email digest
- **ENH-05**: User journal notes per setup
- **ENH-06**: MTF confluence score badge (H4/H1 bias gating M15 entries)

## Out of Scope

Explicitly excluded. Documented to prevent scope creep.

| Feature | Reason |
|---------|--------|
| Order execution in v1 | PROJECT.md decision: build trust in signal quality before automating risk; next milestone |
| LLM-originated entry/SL/TP levels | LLMs hallucinate numbers; destroys the verifiable-trust core value |
| Full SMC kitchen sink in v1 (OB/FVG/BOS as labeled features) | Scope creep delaying the trust loop; each concept needs its own backtest validation |
| Real-time tick streaming | M15/H1/H4 system gains nothing; MT5 Python API is request/response oriented |
| Online/continuous ML retraining | Drift-and-overfit roulette; scheduled reviewed retrains instead |
| Non-forex instruments (indices/crypto/metals) | v1 scope: forex majors only per PROJECT.md |
| External data vendors | MT5 endpoint is the sole data source for v1 per PROJECT.md |
| Multi-user / hosted SaaS / mobile | Different product surface; depends on user's local MT5 terminal anyway |
| Push notifications (Telegram/Discord) in v1 | Third-party plumbing; v1.x candidates after the dashboard trust loop works |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| DATA-01 | Phase 1 | Complete |
| DATA-02 | Phase 1 | Complete |
| DATA-03 | Phase 1 | Complete |
| DATA-04 | Phase 1 | Complete |
| DATA-05 | Phase 1 | Complete |
| SMC-01 | Phase 2 | Complete |
| SMC-02 | Phase 2 | Complete |
| SMC-03 | Phase 2 | Complete |
| SMC-04 | Phase 2 | Complete |
| SMC-05 | Phase 2 | Complete |
| SMC-06 | Phase 2 | Complete |
| BT-01 | Phase 3 | Complete |
| BT-02 | Phase 3 | Complete |
| BT-03 | Phase 3 | Complete |
| BT-04 | Phase 3 | Complete |
| BT-05 | Phase 3 | Complete |
| AI-01 | Phase 4 | Complete |
| AI-02 | Phase 4 | Complete |
| AI-03 | Phase 4 | Complete |
| AI-04 | Phase 4 | Complete |
| AI-05 | Phase 5 | Complete |
| AI-06 | Phase 5 | Complete |
| AI-07 | Phase 5 | Complete |
| SETUP-01 | Phase 6 | Pending |
| SETUP-02 | Phase 6 | Pending |
| SETUP-03 | Phase 6 | Pending |
| SETUP-04 | Phase 6 | Pending |
| DASH-01 | Phase 6 | Pending |
| DASH-02 | Phase 6 | Pending |
| DASH-03 | Phase 6 | Pending |
| DASH-04 | Phase 6 | Pending |
| DASH-05 | Phase 6 | Pending |
| DASH-06 | Phase 6 | Pending |

**Coverage:**

- v1 requirements: 33 total
- Mapped to phases: 33
- Unmapped: 0 ✓

---
*Requirements defined: 2026-08-29*
*Last updated: 2026-08-29 after initial definition*
