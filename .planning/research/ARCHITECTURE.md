# Architecture Research

**Domain:** AI-assisted forex trading system (SMC detection, hybrid ML + LLM, MT5 data feed, signals-only v1)
**Researched:** 2026-08-29
**Confidence:** HIGH for component decomposition and data flow (standard trading-system architecture, corroborated by real-world MT5 Python integrations such as FastAPI+MT5 bridge patterns); MEDIUM for process boundary choices (deployment-specific)

## Standard Architecture

### System Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                       Presentation Layer                            │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │  Dashboard (Streamlit v1; FastAPI+React deferred to          │  │
│  │  execution milestone per STACK.md)                           │  │
│  └──────────────────────────┬───────────────────────────────────┘  │
├─────────────────────────────┼───────────────────────────────────────┤
│                       Interface Layer                               │
│  ┌──────────────────────────▼───────────────────────────────────┐  │
│  │  Store access layer (SQLite setups + Parquet bars)           │  │
│  └──────────────────────────┬───────────────────────────────────┘  │
├─────────────────────────────┼───────────────────────────────────────┤
│                       Analysis Layer                                │
│  ┌──────────┐  ┌───────────┐  ┌──────────┐  ┌─────────────────┐    │
│  │ SMC      │→ │ Feature   │→ │ ML       │→ │ LLM Narrative   │    │
│  │ Engine   │  │ Builder   │  │ Scorer   │  │ (optional/deg.) │    │
│  └────┬─────┘  └────┬──────┘  └────┬─────┘  └────────┬────────┘    │
│       │             │              │                  │             │
│  ┌────▼─────────────▼──────────────▼──────────────────▼─────────┐   │
│  │              Setup Emitter → Setup Store                     │   │
│  └──────────────────────────────────────────────────────────────┘   │
├─────────────────────────────────────────────────────────────────────┤
│                       Validation Layer                              │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │  Backtesting Engine (replay OHLC → SMC → label outcomes)     │  │
│  └──────────────────────────┬───────────────────────────────────┘  │
├─────────────────────────────┼───────────────────────────────────────┤
│                       Data Layer                                    │
│  ┌──────────┐  ┌───────────┐  ┌──────────────┐                      │
│  │ Data     │  │ OHLC Store│  │ Model/Config │                      │
│  │ Collector│  │ (SQLite + │  │ Store        │                      │
│  │ (MT5)    │→ │  Parquet) │  │              │                      │
│  └────┬─────┘  └───────────┘  └──────────────┘                      │
├───────┼──────────────────────────────────────────────────────────────┤
│       │ External                                                    │
│  ┌────▼─────────────────────┐                                        │
│  │ MetaTrader 5 Terminal    │  (local Windows process, logged in)    │
│  └──────────────────────────┘                                        │
```

### Component Responsibilities

| Component | Responsibility | Typical Implementation |
|-----------|----------------|------------------------|
| Data Collector | Connect to MT5 terminal, poll OHLC bars per symbol/timeframe, normalize timestamps to UTC, handle reconnects and market-closed gaps | Long-running Python service; official `metatrader5` package; APScheduler or simple loop |
| OHLC Store | Persist bars (append-only), serve historical ranges for backtests and analysis | SQLite for metadata/setups + Parquet files for bar series (columnar, fast pandas I/O) |
| SMC Engine | Pure functions over OHLC DataFrames: swing points → liquidity pools (equal highs/lows) → sweep events → premium/discount zones; non-repainting (confirmation-shifted) | pandas/numpy vectorized module; deterministic and unit-testable |
| Feature Builder | Convert SMC state at each decision bar into ML feature vectors | pandas transforms, cached per (symbol, timeframe, bar) |
| ML Scorer | Score each candidate setup with calibrated probability | LightGBM (or sklearn) model; persisted artifacts; calibration layer (isotonic/Platt) |
| LLM Narrator | Generate human-readable rationale from structured evidence; flag agreement/disagreement with ML score | OpenAI-compatible client against local vLLM endpoint; low temperature; evidence-grounded prompt |
| Setup Emitter | Fuse ML score + LLM narrative into a TradeSetup record (direction, entry, SL, TP, probability, rationale) | Deterministic assembler writing to Setup Store |
| Backtesting Engine | Replay historical bars bar-by-bar (no lookahead), run SMC+ML pipeline, label outcomes (TP/SL hit, R-multiple), report metrics | Same SMC/ML code path as live; event-driven replay loop |
| Dashboard | Present setups, history, performance stats, data health; charts with SMC overlays | Streamlit 1.62 + plotly reading stores directly (single-user localhost); FastAPI + React deferred to the execution milestone per STACK.md |
| Web UI | Charts (candles + SMC overlays), setup cards, probability display, rationale, history table | React (Next.js/Vite) or lightweight alternative per STACK.md |

## Recommended Project Structure

```
src/
├── config/               # settings (symbols, timeframes, paths, model params)
├── mt5_client/           # terminal connection, retries, timeframe constants
├── collector/            # polling scheduler, gap backfill, UTC normalization
├── store/                # SQLite (setups/meta) + Parquet (bars) access layer
├── smc/                  # swings, liquidity pools, sweeps, PD zones (pure functions)
├── features/             # feature engineering from SMC state
├── models/               # training, inference, calibration, artifact persistence
├── llm/                  # narrative generation, evidence serialization
├── setups/               # setup assembly + persistence
├── backtest/             # replay engine, labeling, metrics, walk-forward harness
└── dashboard/            # Streamlit app (v1); FastAPI+React at execution milestone
```

### Structure Rationale

- **smc/ as pure functions:** every detector takes a DataFrame in and returns a DataFrame out — identical code path for live and backtest, which is the #1 correctness requirement for this domain
- **store/ isolated:** Parquet for bars (fast bulk reads for backtests), SQLite for transactional setup records — one access layer prevents schema drift
- **backtest/ reuses smc/+features/+models/:** prevents the classic split-brain bug where backtest logic diverges from live logic

## Architectural Patterns

### Pattern 1: Single Code Path (live == backtest)

**What:** The identical SMC → features → ML pipeline functions are called by both the live analysis run and the backtester; only the data source differs (latest bars vs replayed history).
**When to use:** Always, for signal systems.
**Trade-offs:** Slightly more discipline (no shortcut "backtest-only" logic); eliminates lookahead divergence.

```python
def analyze_bars(bars_by_tf: dict[str, pd.DataFrame]) -> list[Setup]:
    smc_state = detect_smc(bars_by_tf)          # pure
    feats = build_features(smc_state)           # pure
    scores = ml_scorer.score(feats)             # pure
    narrative = llm_narrator.narrate(smc_state, scores)  # optional
    return assemble_setups(smc_state, scores, narrative)
```

### Pattern 2: Confirmation-Shifted (non-repainting) Detection

**What:** Swing points and zone formations are only "known" N bars after the extremum (confirmation via close beyond/structure). All downstream features index by confirmation time, not formation time.
**When to use:** Any feature feeding ML or backtests.
**Trade-offs:** Slightly delayed entries vs. honesty; essential — unconfirmed swings silently leak the future.

### Pattern 3: Process Separation with a Shared Store

**What:** Four independent processes — collector (long-running), analysis pipeline (scheduled/on-demand), backtest jobs (CLI), dashboard API+UI — communicate only through the stores, never in-memory.
**When to use:** Single-machine deployments (this project).
**Trade-offs:** Polling latency (irrelevant at M15) vs. simple, restartable, independently testable processes.

## Data Flow

### Request Flow (live signal)

```
Scheduler (M15 close) → Collector checks for new bars → Store append
    ↓
Analysis pipeline: load bars (M15/H1/H4) → SMC Engine → Features → ML score
    ↓
LLM narrative (if enabled) → Setup Emitter → Setup Store
    ↓
Dashboard polls API → renders setup card + chart overlay + rationale
```

### Key Data Flows

1. **OHLC ingestion:** MT5 `copy_rates_*` returns numpy structured arrays → normalized to UTC → appended to Parquet per (symbol, timeframe); idempotent upsert by bar-open time
2. **Backtest labeling:** replay bars through the same `analyze_bars`, record the setup, then walk forward until TP or SL is hit → label (outcome, R-multiple) → these labels are the ML training set
3. **Model lifecycle:** labels from backtests → walk-forward training → calibrated model artifact → ML Scorer reloads artifact; versioned by date

## Scaling Considerations

| Scale | Architecture Adjustments |
|-------|--------------------------|
| 1 user, 3 symbols, 3 TFs (v1) | Single Windows machine; SQLite + Parquet; everything sequential — completely sufficient |
| More symbols/TFs | Vectorize SMC detection fully (avoid per-bar Python loops); parallelize per-symbol analysis |
| Near-real-time | Move from polling to MT5 tick events; only needed if dropping below M5 |

### Scaling Priorities

1. **First bottleneck:** per-bar Python loops in SMC detection during backtests over years of M15 bars — fix with vectorized pandas/numpy from day one
2. **Second bottleneck:** Parquet read amplification for repeated backtests — cache in-memory per run; partition by symbol

## Anti-Patterns

### Anti-Pattern 1: Separate Backtest Implementation

**What people do:** Write a simplified "backtest version" of the SMC logic.
**Why it's wrong:** The two implementations drift; backtest results no longer predict live behavior.
**Do this instead:** One pure pipeline shared by both (Pattern 1).

### Anti-Pattern 2: Using Unconfirmed Swings

**What people do:** Detect swings on the full series, then "go back in time" for features.
**Why it's wrong:** The last swing can change as new bars arrive (repainting) — silent lookahead bias.
**Do this instead:** Confirmation-shifted detection (Pattern 2).

### Anti-Pattern 3: LLM as the Decision Maker

**What people do:** Ask the LLM "is this a good setup?" and use its answer as the probability.
**Why it's wrong:** Non-deterministic, uncalibrated, easily hallucinated — probabilities won't be honest.
**Do this instead:** ML owns the probability; LLM only narrates provided structured evidence and may flag disagreement.

## Integration Points

### External Services

| Service | Integration Pattern | Notes |
|---------|---------------------|-------|
| MetaTrader 5 terminal | `metatrader5` Python package, IPC to local terminal | Terminal must be running and logged in; Windows-only; one connection per terminal; initialize/shutdown lifecycle managed by collector |
| LLM endpoint | OpenAI-compatible REST client (OpenAI SDK with custom baseURL, behind a provider interface) | Local vLLM endpoint already available to the user; Anthropic SDK as hosted alternative per STACK.md; timeout + fallback to ML-only setups |

### Internal Boundaries

| Boundary | Communication | Notes |
|----------|---------------|-------|
| Collector ↔ Store | Direct file/DB writes | Idempotent appends; collector is the only writer of bars |
| Analysis ↔ ML/LLM | In-process function calls | Same process as scheduled job; ML/LLM are injectable dependencies (LLM skippable) |
| Dashboard ↔ Stores | Streamlit reads SQLite/Parquet directly (localhost, single user) | Read-only discipline even without an API boundary; FastAPI introduced at execution milestone |

## Sources

- Official MetaTrader5 Python docs (mql5.com/en/docs/integration/python_metatrader5) — terminal lifecycle, copy_rates semantics
- PyPI metatrader5 5.0.6147 page (verified 2026-08-29) — platform constraints, wheel availability
- Community MT5+FastAPI/bridge architectures (medium.com, GitHub topics/metatrader5) — process-boundary patterns
- Established event-driven backtesting literature (vectorbt/backtesting.py design docs) — replay and labeling conventions

---
*Architecture research for: AI forex SMC trading system*
*Researched: 2026-08-29*
