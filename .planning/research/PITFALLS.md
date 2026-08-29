# Pitfalls Research

**Domain:** AI-assisted forex trading system (SMC detection, hybrid ML + LLM, MT5 data feed, signals-only v1)
**Researched:** 2026-08-29
**Confidence:** HIGH for MT5 API gotchas (official docs + PyPI-verified package constraints + long-standing community reports); MEDIUM-HIGH for ML/backtest pitfalls (well-established quant practice); MEDIUM for LLM pitfalls (evolving practice)

## Critical Pitfalls

### Pitfall 1: MT5 Server Timezone & DST Misalignment

**What goes wrong:** `copy_rates_*` returns bar-open times in the broker's server timezone as naive epoch seconds. Treating them as UTC silently shifts everything. When US/EU DST flips, the offset between server time and UTC changes, so session logic (London/NY kills zones), day boundaries, and MTF joins drift by an hour twice a year — differently for each broker.
**Why it happens:** The API gives naive timestamps and most tutorials ignore the issue; each broker's server timezone differs (often EET/EEST, UTC+2/+3).
**How to avoid:** Normalize to UTC immediately in the collector using the broker's known server offset, configured per broker and validated empirically; re-validate offset around DST transitions; never mix naive server time with system-local time.
**Warning signs:** Session-filtered setups appearing an hour early/late after March/November; H1 bars that don't align with known London open; duplicates/gaps in MTF joins.
**Phase to address:** Phase 1 (data foundation) — bake UTC normalization into ingestion, never downstream.

---

### Pitfall 2: Lookahead / Repainting in Swing Detection

**What goes wrong:** Swing highs/lows (and therefore PD zones, liquidity pools, sweeps) can only be confirmed N bars after the extremum — a new extreme invalidates the swing. Detecting swings on the full series and then attributing them to their bar gives the model the future: backtests look brilliant, live results collapse.
**Why it happens:** Vectorized "detect all swings" over the whole array is easy; tracking confirmation latency is work; the bug is invisible in plots.
**How to avoid:** Confirmation-shifted logic — a swing exists only once confirmed (e.g., N subsequent closes on the correct side); index all downstream state by confirmation bar, not formation bar; backtester must replay bar-by-bar with only past data visible.
**Warning signs:** Backtest hit rates implausibly above base rates; zone boundaries drawn from "future" highs when eyeballing charts; metrics that degrade sharply in walk-forward vs random split.
**Phase to address:** Phase 2 (SMC engine) — design detectors as non-repainting from the first commit; add a repaint unit test.

---

### Pitfall 3: Data Leakage in ML Scoring

**What goes wrong:** Random train/test splits on overlapping forex bars, features computed with information unavailable at decision time, or targets whose outcome window overlaps the evaluation window — all inflate validation scores and produce a confidently wrong model.
**Why it happens:** Standard sklearn workflow defaults (random K-fold) are wrong for time series; bars are autocorrelated.
**How to avoid:** Walk-forward / purged K-fold with embargo between train and test; every feature gets a "known-at-time" audit; labels computed strictly forward from the setup bar; never shuffle.
**Warning signs:** Test metrics far better than later live-paper performance; feature importance dominated by price-derived features that "predict" the immediate next bar.
**Phase to address:** Phase 3 (backtesting/labeling) and Phase 4 (ML) — walk-forward harness is part of the backtest deliverable, not an afterthought.

---

### Pitfall 4: MT5 History Availability & Synchronization Limits

**What goes wrong:** Backtests request years of M15 data and get less than expected: broker history depth varies per symbol; the terminal's "Max bars in chart" setting caps what `copy_rates_*` can return; on first `initialize()` after fresh install, data synchronizes lazily and early requests return empty/short arrays.
**Why it happens:** MT5 is a terminal-first product; Python is a client of the terminal's local cache, not a direct broker feed.
**How to avoid:** After connect, request data in chunks and verify counts; surface actual available range per (symbol, timeframe); document broker limits in the store; make the backtester refuse ranges with insufficient data rather than silently truncating.
**Warning signs:** `copy_rates_range` returning fewer bars than requested window; backtest equity curves that start suspiciously recently.
**Phase to address:** Phase 1 (collector must record actual available history) and Phase 3 (backtest range validation).

---

### Pitfall 5: Naive Backtest Cost Model

**What goes wrong:** Assuming zero or fixed spread and no slippage. Forex spreads vary enormously by session (NY open vs. rollover hour) and by pair; a strategy profitable at 0 spread can be deeply negative at realistic costs. Rollover (swap) and weekend gap behavior also distort intraday setups.
**Why it happens:** Spread data requires extra effort; tick_volume and spread columns exist on MT5 bars but are ignored.
**How to avoid:** Model entry cost with the bar's recorded `spread` column (MT5 provides it) or a session-dependent spread table; add slippage buffer; report metrics net of costs; treat rollover-hour signals as a separate filter category.
**Warning signs:** Sharpe/profit factor that flips sign when a 1-pip cost is applied; strategies whose edge concentrates in rollover hours.
**Phase to address:** Phase 3 (backtesting) — cost model is part of the labeling engine from day one.

---

### Pitfall 6: LLM Hallucination & Non-Determinism in Rationale

**What goes wrong:** Letting the LLM "analyze" raw data or free-form chart context produces confident narratives that contradict the actual SMC state, non-reproducible outputs across runs, and probabilities that are not calibrated to reality.
**Why it happens:** LLMs are fluent storytellers; open-ended prompts feel natural for "analysis."
**How to avoid:** LLM receives only structured, pre-computed evidence (detected sweep, zone boundaries, ML score, session context) and must cite it; low temperature; deterministic seeds where supported; the ML score — not the LLM — is the probability of record; LLM output is labeled as narrative; system degrades gracefully to ML-only setups when the LLM is unavailable/slow.
**Warning signs:** Narrative mentions levels/zones absent from the SMC state; two runs on identical input produce contradictory conclusions.
**Phase to address:** Phase 5 (LLM layer) — evidence-grounded prompt contract and agreement flag designed in.

---

### Pitfall 7: Ambiguous Win/Loss Labels

**What goes wrong:** "High probability" is meaningless without a crisp target definition: does TP hit before SL within N bars? What R-multiple counts as a win? When both TP and SL are touched within one bar, which wins? Ambiguity here poisons training data and dashboard statistics.
**Why it happens:** Defining outcomes feels trivial; intrabar ambiguity and overlapping windows make it subtle.
**How to avoid:** Formal label spec: SL/TP as placed, intrabar ties resolved pessimistically (SL first) by default with a documented conservative mode; fixed evaluation horizon; label config stored alongside trained models so scores are always interpretable.
**Warning signs:** Dashboard win-rate that can't be reproduced from raw setup + bar data; arguments about what counts as a win.
**Phase to address:** Phase 3 (labeling engine) — spec written before ML training.

---

### Pitfall 8: Equal-Highs/Lows Tolerance Mis-Specification

**What goes wrong:** Liquidity pools (equal highs/lows) require a price tolerance to cluster levels. Too tight → almost no pools detected; too loose → unrelated levels merge, sweeps fire everywhere, and the feature becomes noise that the ML model overfits to.
**Why it happens:** Tolerance is instrument-dependent (pip size, volatility regime); a fixed absolute value breaks across pairs.
**How to avoid:** Express tolerance in ATR multiples or relative terms per instrument; expose as config with sensible defaults; add per-symbol sanity metrics (pools per 100 bars) with alerts at extremes.
**Warning signs:** Sweep counts differing by 10x between EURUSD and USDJPY with the same config; ML feature importance concentrated in pool-count features.
**Phase to address:** Phase 2 (SMC engine) — parameterized detection + validation metrics.

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Storing bars only in SQLite rows | One storage engine | Slow bulk backtest reads; bloat | Never — use Parquet for bars |
| Hardcoding symbols/timeframes | Faster start | Config sprawl when expanding | v1 prototype only, centralize by Phase 2 |
| Skipping calibration (raw LightGBM outputs) | Ship sooner | Dashboard probabilities are lies | Never — calibrate before showing to user |
| Log-and-continue on collector errors | Silence during dev | Silent data gaps poison labels later | Dev only; alerting by Phase 3 |
| Free-text LLM prompt without evidence schema | Quick demo | Unverifiable narratives | Never for this project |

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| MT5 terminal | Calling API functions without checking `initialize()` success / terminal running | Explicit connect lifecycle, health check per cycle, actionable error if terminal closed/logged out |
| MT5 symbol access | Assuming symbol is available | `symbol_select()` before use; record availability per symbol |
| MT5 timestamps | Mixing naive server time with UTC | Normalize once in collector; store UTC everywhere |
| LLM endpoint | Blocking the pipeline on slow responses | Timeout + fallback to ML-only setup; narrative generation is best-effort |
| FastAPI ↔ stores | API doing writes at runtime | Read-only API; writes via collector/pipeline/jobs only |

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Per-bar Python loops in SMC detection | Backtests take hours | Vectorized pandas/numpy rolling/groupby ops | First multi-month backtest |
| Re-downloading full history per analysis run | Collector hogs CPU, MT5 chokes | Incremental fetch of new bars only; local Parquet is source of truth for analysis | First week of live polling |
| Retraining ML model on every new label | Model churn, no baseline | Scheduled walk-forward retraining with versioned artifacts | Phase 4+ |

## Security Mistakes

| Mistake | Risk | Prevention |
|---------|------|------------|
| LLM/API keys in code or committed configs | Credential leak | .env / local secrets file, gitignored; template .env.example committed |
| Dashboard bound to 0.0.0.0 without auth | Anyone on LAN sees trading data | Bind localhost by default; auth before any LAN exposure |
| MT5 credentials handled by Python scripts | Credential sprawl | Terminal stays logged in by user; Python never touches account credentials (signals-only v1) |

## UX Pitfalls

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| Showing raw probability without calibration context | User trusts 0.87 that means nothing | Calibrated probability + historical bucket hit-rates displayed |
| Setup cards without rationale evidence | User can't verify; trust erodes | Every card links its evidence: zones, sweeps, ML features, narrative |
| No way to see invalidated/expired setups | Dashboard looks dishonest over time | Setup lifecycle states (active, TP, SL, expired) shown in history |
| Timezone confusion in displayed times | User misses context | Display UTC + broker time explicitly on all timestamps |

## "Looks Done But Isn't" Checklist

- [ ] **Data ingestion:** Often missing gap backfill after terminal/PC downtime — verify idempotent catch-up on restart
- [ ] **SMC detection:** Often missing repaint test — verify no detector uses data beyond its confirmation bar
- [ ] **Backtest:** Often missing cost model — verify metrics computed net of spread/slippage
- [ ] **ML scoring:** Often missing calibration — verify predicted vs observed frequencies plotted
- [ ] **LLM layer:** Often missing fallback — verify system still emits setups with LLM endpoint disabled
- [ ] **Dashboard:** Often missing setup lifecycle tracking — verify TP/SL/expired outcomes visible

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Timezone misalignment discovered late | HIGH | Re-normalize all stored bars, re-run backtests, retrain models |
| Lookahead found in detector | MEDIUM | Fix detector, re-run full labeling + walk-forward, compare honestly |
| Leaked ML model in production | MEDIUM | Retrain with walk-forward, recalibrate, re-publish artifacts |
| LLM hallucinated narratives | LOW | Tighten evidence contract, re-generate narratives (setups unchanged) |

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| Timezone/DST | Phase 1 | Stored timestamps UTC; DST-transition spot check passes |
| Lookahead/repaint | Phase 2 | Repaint unit test; walk-forward vs random-split gap small |
| ML leakage | Phase 3/4 | Purged walk-forward harness in place; no shuffle anywhere |
| History limits | Phase 1 | Available-range report per symbol/TF persisted |
| Cost model | Phase 3 | Metrics net of recorded spread; sensitivity report |
| LLM hallucination | Phase 5 | Evidence-citation check; ML-only fallback demo |
| Label ambiguity | Phase 3 | Label spec doc; reproducible outcome stats from raw data |
| Tolerance mis-spec | Phase 2 | Per-symbol pool-rate sanity metrics in CI |

## Sources

- Official MetaTrader5 Python integration docs (mql5.com) — initialize/copy_rates semantics, terminal-first data model
- PyPI metatrader5 5.0.6147 (verified 2026-08-29) — Windows-only, platform constraints
- Community reports on MT5 timezone/broker-time issues (Stack Overflow, MQL5 forum threads)
- Established quant ML practice (walk-forward/purged CV literature; vectorbt/backtesting.py design docs)
- SMC detection libraries (smartmoneyconcepts on PyPI) — confirmation-shifted conventions for swings/zones

---
*Pitfalls research for: AI forex SMC trading system*
*Researched: 2026-08-29*
