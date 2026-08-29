# Project Research Summary

**Project:** AI Forex SMC Trading System
**Domain:** AI-assisted forex trading signal system (SMC detection, hybrid ML+LLM, MT5 data feed, signals-only v1)
**Researched:** 2026-08-29
**Confidence:** HIGH

## Executive Summary

This is a single-user, local-first Python trading *signal* system for Windows: a data collector feeds OHLC bars from the user's logged-in MetaTrader 5 terminal into a local Parquet/SQLite store; a look-ahead-safe SMC engine (swing points → liquidity pools → sweeps → premium/discount zones) produces structured market-state events on M15/H1/H4 for EURUSD, GBPUSD and USDJPY; a hybrid AI layer scores each candidate setup — a calibrated gradient-boosted model owns the probability, an LLM consumes the same evidence object and adds a confirm/refute narrative with an agreement flag; a backtester replays the identical pipeline over history (spread-modeled, walk-forward) to validate setup quality before live signals are trusted; and a Streamlit dashboard presents setups with full evidence traces, lifecycle outcomes and performance stats.

The recommended approach follows the trust loop the user asked for: every setup carries direction, entry, SL, TP, calibrated probability and a verifiable rationale. The single most important engineering decision — enforced across all research docs — is **one point-in-time code path shared by live analysis and backtests** (confirmation-shifted swing detection, no repainting, no lookahead). The main risks are silent correctness failures, not performance: broker-time/DST misalignment, lookahead in SMC detection, ML leakage, and naive backtest cost models. Each has an explicit prevention owner in the phase plan below.

## Key Findings

### Recommended Stack

Python 3.12 on Windows, with versions verified live against PyPI on 2026-08-29 (see STACK.md for the full matrix).

**Core technologies:**
- **metatrader5 5.0.6147** — official MetaQuotes feed; Windows x86-64 only, terminal must run logged-in; returns numpy arrays incl. `spread`
- **pandas 2.3.3 / numpy 2.2.6** — SMC detection as vectorized, confirmation-shifted pure functions
- **LightGBM 4.7.0 + scikit-learn 1.7.2** — setup-probability scorer + `CalibratedClassifierCV` (honest probabilities)
- **OpenAI SDK 3.6.0 / Anthropic SDK 1.2.0 behind one provider interface** — LLM narrative; local vLLM (OpenAI-compatible) works today, Ollama for dev
- **SQLite (SQLAlchemy 2.0.52) + Parquet (pyarrow 25.0.1)** — setups/meta relational; bars columnar/append-only
- **Streamlit 1.62.0 + plotly 7.0.0** — v1 dashboard (FastAPI 0.141 + React deferred to the execution milestone)
- **APScheduler 3.11.3 (<4)** — M15-bar-close scheduling in one engine process; uv + ruff + pytest for tooling

### Expected Features

**Must have (table stakes):**
- MT5 ingestion: 3 majors × 3 TFs, UTC-normalized, incremental cache, terminal health checks
- Look-ahead-safe swing detection → liquidity pools → sweep events (reclaim rule) → PD zones with lifecycle state
- Complete setup record (symbol, direction, entry, SL, TP, RR, evidence) + lifecycle tracking (active → TP/SL/expired/invalidated)
- Calibrated ML probability + walk-forward evaluation
- LLM narrative + confirm/refute + ML↔LLM agreement flag
- Backtest engine (same pipeline, spread-modeled) with canonical stats (WR, PF, expectancy, max DD, per symbol/TF)
- Dashboard: filtered setup table, annotated candlestick chart, history with outcomes, performance panel, data-health strip

**Should have (differentiators):**
- Transparent evidence trace on every setup (the headline: verifiability)
- Calibration reliability report; per-pattern historical stats surfaced live
- MTF confluence score; session/kill-zone awareness; sweep-quality micro-features

**Defer (v1.x / v2+):**
- Alerts (browser/email), user journal notes, per-pattern live stats (v1.x)
- Order execution — next milestone, gated on signal trust
- More SMC concepts (OB/FVG/BOS-CHoCH), more instruments, multi-user (v2+)

### Architecture Approach

Five processes over shared stores: a long-running **collector** (MT5 → Parquet/SQLite, UTC-normalized, health-checked), a scheduled **analysis pipeline** (SMC → features → ML → optional LLM → setup store), **backtest jobs** (CLI, same code path, produces labels), the **dashboard** (Streamlit, read-only), and the **MT5 terminal** as an external dependency. Components communicate only through stores; SMC/features/ML are pure functions over DataFrames so live and backtest literally call the same functions.

**Major components:**
1. Data Collector + OHLC Store — MT5 polling, gap backfill, UTC normalization
2. SMC Engine — point-in-time swings/pools/sweeps/PD-zones with state machines
3. Hybrid AI layer — ML scorer (calibrated) + LLM narrator (evidence-grounded, degradable)
4. Backtester/Labeler — replay, spread costs, triple-barrier labels, walk-forward
5. Dashboard — Streamlit presentation + lifecycle + stats

### Critical Pitfalls

1. **MT5 server-time/DST misalignment** — normalize to UTC at ingestion; broker offset is config, validated around DST flips
2. **Lookahead/repainting in swing detection** — confirmation-shifted detectors + repaint unit tests + one shared code path
3. **ML data leakage** — walk-forward/purged CV, "known-at-time" feature audit, never shuffle
4. **Naive backtest costs** — use the bar `spread` column + slippage buffer; net-of-cost metrics only
5. **LLM hallucination** — LLM only confirms/refutes over structured evidence; never originates levels or probabilities; ML-only fallback

## Implications for Roadmap

Based on research, suggested phase structure (standard granularity; roadmapper finalizes):

### Phase 1: Data Foundation
**Rationale:** Everything downstream consumes stored, UTC-normalized bars; correctness here prevents the most poisonous silent failures.
**Delivers:** MT5 collector (3 symbols × 3 TFs), incremental Parquet store, SQLite metadata, UTC normalization + broker-offset config, health checks, history-availability report.
**Addresses:** Data-ingestion table stakes (FEATURES.md).
**Avoids:** Timezone/DST pitfall, history-limit surprise (PITFALLS.md 1, 4).

### Phase 2: SMC Detection Engine
**Rationale:** Swings are the shared dependency of both v1 concepts; point-in-time discipline must be built in from the first commit.
**Delivers:** Confirmation-shifted swing detection, equal-highs/lows pools (ATR-relative tolerance), sweep events with reclaim rule, PD zones with lifecycle state machine; pytest repaint tests.
**Avoids:** Lookahead/repaint pitfall (PITFALLS.md 2), tolerance mis-specification (8).

### Phase 3: Backtesting & Labeling
**Rationale:** Labels from backtests are the prerequisite for ML training (not just validation); the trust gate comes before the AI layer.
**Delivers:** Bar-by-bar replay of the full pipeline, spread/slippage cost model, triple-barrier labels with documented intrabar tie rule, canonical stats, walk-forward harness.
**Avoids:** Naive cost model (5), label ambiguity (7), leakage groundwork (3).

### Phase 4: ML Scoring
**Rationale:** Needs labeled data from Phase 3; bootstrap with heuristic scores until labels accumulate.
**Delivers:** Feature builder from SMC state, LightGBM scorer, calibration, walk-forward evaluation reports, versioned model artifacts.
**Avoids:** Data leakage (3); uncalibrated probability display.

### Phase 5: LLM Narrative Layer
**Rationale:** Consumes the evidence object built in Phases 2–4; must remain separable and degradable.
**Delivers:** Provider interface (local vLLM via OpenAI SDK; Anthropic optional), evidence-grounded structured narrative + agree/disagree flag, ML-only fallback.
**Avoids:** LLM hallucination (6).

### Phase 6: Dashboard
**Rationale:** Presentation layer last — it renders persisted setups, evidence, outcomes and stats that already exist.
**Delivers:** Streamlit app: setup table with filters, plotly candlestick + SMC overlays (sweeps, zones), setup detail with evidence trace, history with lifecycle outcomes, performance panel, data-health strip.
**Avoids:** UX pitfalls (uncalibrated probability display, missing lifecycle).

### Phase Ordering Rationale

- Dependency chain discovered in research: ingestion → swings → pools/sweeps/zones → backtest labels → ML → LLM → dashboard (ML needs labels; LLM and dashboard consume evidence objects; dashboard renders everything)
- Backtest-before-ML ordering directly honors PROJECT.md's "backtesting validates setup quality before live signals are trusted"
- One shared code path (live == backtest) is enforced by building the backtester immediately after detection, before ML exists

### Research Flags

Phases likely needing deeper research during planning:
- **Phase 1:** broker server-offset must be validated empirically against the user's terminal (empirical task, not docs)
- **Phase 4:** label spec + calibration details (bootstrap strategy, class balance) — do phase-specific research
- **Phase 5:** LLM provider config for the user's local vLLM endpoint (structured-output support varies by model)

Phases with standard patterns (skip research-phase):
- **Phase 2:** detection math is fully specified in research cache + FEATURES.md
- **Phase 6:** Streamlit + plotly patterns are well-documented

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | All versions live-verified on PyPI 2026-08-29; official vendor docs fetched |
| Features | HIGH | Primary sources verified (smartmoneyconcepts, Lightweight Charts, backtesting.py, sklearn); competitor landscape MEDIUM (flagged inline) |
| Architecture | HIGH | Standard component decomposition corroborated by real MT5+Python integration patterns |
| Pitfalls | HIGH | MT5 gotchas grounded in official docs + community reports; ML pitfalls are established quant practice |

**Overall confidence:** HIGH

### Gaps to Address

- **Broker server timezone offset:** unknown until we connect to the user's actual terminal — Phase 1 must include an empirical probe
- **Available history depth per symbol/TF:** broker- and terminal-config dependent — Phase 1 reports it, Phase 3 refuses insufficient ranges
- **Local vLLM structured-output reliability:** varies by served model — Phase 5 plans a fallback path
- **Competitor landscape specifics:** survey-grade only (SearXNG rate-suspended mid-session); not design-critical

## Sources

### Primary (HIGH confidence)
- PyPI metatrader5 5.0.6147 page (live-fetched 2026-08-29) — version, wheel matrix, constraints
- MQL5 official Python integration docs — copy_rates semantics, bar-0 forming bar, "Max bars in chart" cap
- smartmoneyconcepts library README (MIT, ~2k stars) — detection canon incl. `Swept` index, centered-window repaint behavior
- scikit-learn official docs (via context7) — CalibratedClassifierCV, HistGradientBoosting, calibration curves
- TradingView Lightweight Charts README; backtesting.py README — dashboard charting and canonical backtest stats

### Secondary (MEDIUM confidence)
- Live PyPI version checks for all recommended packages (2026-08-29)
- Context7 library docs (openai-python, lightgbm readthedocs)
- Established quant-ML practice (Lopez de Prado AFML) — walk-forward, triple-barrier labels
- MT5 community threads (Stack Overflow, MQL5 forums) — timezone/gotcha reports

### Tertiary (LOW confidence)
- Competitor landscape characterization (LuxAlgo-class indicators, black-box AI signal tools) — domain knowledge; SearXNG rate-suspended mid-session, not web-verified

---
*Research completed: 2026-08-29*
*Ready for roadmap: yes*
