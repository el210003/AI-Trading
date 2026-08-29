# Feature Research

**Domain:** AI forex trading signal system (SMC-based, hybrid ML+LLM, MT5 data feed)
**Researched:** 2026-08-29
**Confidence:** MEDIUM-HIGH (primary sources verified; competitor-landscape claims MEDIUM — see Sources note)

> **Research note:** The SearXNG metasearch endpoint was rate-suspended during this session, so ecosystem-survey style web searches could not be run. Findings below rest on **verified primary sources** (official READMEs, PyPI, official docs — HIGH confidence) plus domain knowledge for competitor landscape (MEDIUM, flagged inline). Core feature design is well-grounded; competitor claims should not be quoted as authoritative market research.

## Feature Landscape

Scope anchor from PROJECT.md: v1 is **signals-only** (no execution), SMC focus = **liquidity sweeps + premium/discount zones** (swing detection is an internal dependency, not a user-facing feature), majors **EURUSD/GBPUSD/USDJPY** on **M15/H1/H4**, hybrid **ML scoring + LLM narrative** kept as separable components, backtesting mandatory before trusting live signals.

### Table Stakes (Users Expect These)

Features users assume exist. Missing these = product feels incomplete/untrustworthy.

**MT5 Data Ingestion**

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| OHLC pull per symbol via MetaTrader5 lib (`copy_rates_from_pos/range`) | Anything else (scraping, paid vendors) is off-spec per PROJECT.md; official lib is the canonical path | LOW | MT5 package v5.0.6147 (PyPI, verified): Windows-only, Python 3.8–3.14 wheels, needs running logged-in terminal. Returns numpy arrays incl. `spread` column — capture it, backtesting needs it |
| Multi-timeframe dataset (M15/H1/H4) per symbol | MTF confluence is core to SMC method; users expect H4/H1 structure informing M15 entries | MEDIUM | Three `copy_rates_*` calls per symbol; the hard part is alignment and timezone (broker time ≠ UTC, DST shifts) — normalize to UTC immediately at ingest |
| Local data cache with incremental updates | Re-downloading full history every scan cycle is slow and abusive to the terminal; users expect fast repeated scans | MEDIUM | Pull-once-backfill then append new closed bars; store Parquet/SQLite. Only act on **closed** bars — a bar that is still forming will repaint |
| Data hygiene: gaps, weekends, missing bars, session boundaries | Forex data has weekend gaps and broker-specific missing bars; silently misaligned timeframes corrupt every downstream feature | MEDIUM | Validate monotonic timestamps, reindex to expected bar grid per TF, flag gaps instead of interpolating |
| Terminal-health checks (`initialize`, `symbol_select`, symbol info) | If MT5 is logged out or symbol name differs per broker (e.g. "EURUSD.x"), the pipeline silently breaks | LOW | Fail loudly at startup: verify each of the 3 symbols is selectable and market-open; log broker symbol suffix variations |

**SMC Detection (liquidity sweeps + PD zones)**

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Swing-point detection (fractal-style, `swing_length` window) | The foundational dependency for everything SMC: liquidity pools AND PD zones are defined off swing highs/lows | LOW–MEDIUM | Canon: smc lib `swing_highs_lows(ohlc, swing_length=50)`; high/low is extreme within N candles before AND after. **Critical:** needs N future candles → confirmation lag; must be handled or every backtest is look-ahead-biased (see Pitfall note) |
| Equal highs/lows (liquidity pools) clustering | "Equal highs/lows" is the canonical liquidity concept users name first | MEDIUM | smc lib: `liquidity(ohlc, swings, range_percent=0.01)` groups swing highs/lows within tolerance → pooled Level + End index. Parameter must be tuned per instrument scale (pips-based tolerance works better than raw percent across 3 majors) |
| Sweep detection (pool taken out, then rejection) | The core v1 concept; users expect "this high was swept" events with timestamp and level | MEDIUM | smc lib returns `Swept` index directly. Definition choices to lock down: wick-through vs close-through, immediate rejection vs N-bar window. Sweeps *without* reclaim (pure breakouts) must be distinguishable — that rejection-back-through-close is the signal |
| Premium/discount zones from swing ranges | Second core v1 concept: users expect "price is in discount of the H4 range" statements | MEDIUM | Range = last confirmed swing high↔low; discount 0–50%, premium 50–100% (smc lib `retracements` computes current/deepest %). Zone = band, not a line; needs swing-range selection rules (which swing pair defines "the" range) |
| Zone/pool state tracking (unmitigated → mitigated → invalidated) | Stale zones poison setups; users expect only live zones offered | MEDIUM | Each zone needs lifecycle status updated bar-by-bar (touched? traded through? age?). This state machine is required by ML features, LLM narrative, and dashboard display simultaneously |
| Look-ahead-safe detection mode | Any credibility with a technical user dies if signals use future candles; mandatory for the backtest gate in PROJECT.md | MEDIUM–HIGH | Implement detection as "point-in-time": at bar t, only swings confirmed by t (i.e., swing bar ≤ t−N). Same code path for backtest and live — divergence here is the #1 silent killer |

**AI/ML Analysis**

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| ML probability score per setup (0–100%) | Users of AI signal tools expect a ranked, comparable number; PROJECT.md mandates ML scoring | MEDIUM | Gradient-boosted trees (HistGradientBoosting/LightGBM-class) over SMC-derived features (sweep quality, zone depth, MTF bias, session, ATR-normalized distances). **Must be calibrated** (`CalibratedClassifierCV`, sklearn docs verified) — raw tree scores are not probabilities |
| Point-in-time ML feature assembly | Features must be computable at decision time from past data only | MEDIUM | Same discipline as look-ahead-safe detection; assemble features from the zone/pool state machines and confirmed swings only |
| Walk-forward training/evaluation protocol | Users (and the project's own trust goal) expect the score to mean something out-of-sample | MEDIUM–HIGH | sklearn `TimeSeriesSplit`-style rolling train/test; never shuffled k-fold on time series. Retraining cadence is manual/scheduled, not online |
| LLM narrative reasoning per setup | PROJECT.md core value: "transparent, reasoned evidence the user can trust and verify" — narrative is the trust layer | MEDIUM | LLM receives structured evidence JSON (swept level, zone boundaries, MTF bias, ML score + top features) and returns structured narrative + agree/disagree + confidence. Constrain via structured output/schema; the LLM **confirms and explains**, never originates price levels (hallucination risk — see Anti-Features) |
| ML↔LLM agreement flag | With two AI layers, users immediately ask "do they agree?" | LOW | Trivial once both components exist (LLM verdict + score band); huge clarity gain — expose in UI as a first-class field |

**Trade Setup Presentation**

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Complete setup record: symbol, direction, entry (zone/level), SL, TP, timestamp, timeframe | A signal without SL/TP is unusable; every signal provider (good or bad) shows this quartet | LOW | SL below/above swept level or zone boundary; TP at opposite range extreme or fixed-R (e.g. 2R). Store the *reason* each level was chosen, not just the number |
| Risk:reward ratio displayed | Traders filter on RR before anything else | LOW | Derived field; also normalize outcome tracking to R-multiples |
| Rationale/evidence list attached to each setup | The stated differentiator of AI systems over Telegram signal groups; without it the system is a black box | LOW (once detection exists) | Render the same evidence object given to the LLM: sweep event, PD zone, MTF bias, session, ML score contributors |
| Setup lifecycle status (active → TP hit / SL hit / expired / invalidated) | Users check "what happened to the signal?" within minutes; unresolved signals pile up as noise | MEDIUM | Needs bar-close monitoring of open setups + expiry rules (e.g. invalid if N bars pass or opposite structure breaks). Outcome records feed ALL performance stats |
| Setup expiry/invalidation rules | Setups that never trigger must stop being "active" | LOW–MEDIUM | E.g. sweep reclaim setup expires if price closes through invalidation level within K bars |

**Backtesting**

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Historical replay of the full pipeline (detect → score → simulate outcome) | PROJECT.md: mandatory before trusting live signals; SMC users habitually eyeball history but expect systematic validation | HIGH–MEDIUM | Either wrap a point-in-time detector in an event loop (custom, full control over intrabar SL/TP ordering) or adapt backtesting.py (8.9k stars, AGPL — fine for private local use). Intrabar ambiguity rule needed: if a bar touches both SL and TP, assume worst case |
| Standard performance stats | Win rate, profit factor, expectancy, max drawdown, avg R, trade count, per symbol/TF breakdown — the canon every backtest report includes (verified: backtesting.py stat set) | LOW | These exact fields are table stakes; a backtest without PF/expectancy/DD reads as toy |
| Spread + cost modeling | Forex backtests ignoring spread (EURUSD ~0.6–1.5 pips typical retail) systematically overstate edge; MT5 rate arrays include a spread column — use it | LOW–MEDIUM | Apply per-bar spread to SL/TP checks; optionally add slippage buffer constant |
| Walk-forward report (per time window) | A single aggregate hides regime shifts; users doing SMC know 2022-style trends differ from ranges | MEDIUM | Same protocol as ML evaluation — share infrastructure |
| Per-setup-pattern stats (by sweep type, zone depth, session, TF) | The question users actually ask: "which of these setups is worth taking?" | MEDIUM | Requires setup tagging at detection time (see Differentiators — this doubles as differentiator when surfaced live) |

**Dashboard**

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Candlestick chart of the pair with entry/SL/TP marked | Every trading interface shows the trade on the chart; non-negotiable | MEDIUM | TradingView Lightweight Charts (verified: 17.1k stars, v5 API, candlestick + markers + price lines, Apache-2.0 with attribution) is the standard embed |
| SMC annotation overlay (swept levels, PD zones shaded, swing points) | An SMC system whose charts don't show the SMC objects forces users to re-verify in TradingView manually — kills the trust loop | MEDIUM–HIGH | Zones as semi-transparent bands (LWC plugins), sweeps as markers at event bars. This is the visual proof of the evidence trace |
| Setup list/table with filters (symbol, status, date, min probability, direction) | With 3 pairs × 3 TFs, unfiltered signal lists become noise | LOW–MEDIUM | Server-side query + simple filters; sort by probability/R pending status |
| Setup history with outcomes | Journaling is table stakes for any trading tool (Tradervue built a 207k-user business on it) | LOW | Persistent setup + outcome records; detail view showing the chart at entry with annotations frozen |
| Performance stats panel (win rate, PF, expectancy, equity curve in R) | Users judge the system by its aggregate track record before trusting individual signals | MEDIUM | Aggregate + per-symbol + per-pattern; R-multiple based equity curve (no position sizing needed in v1) |
| Data/pipeline health indicator (last sync time, MT5 connection, errors) | Single-machine dependency on a running MT5 terminal means silent staleness is the most likely failure mode | LOW | "Last bar: EURUSD M15 14:45 UTC ✓" style status strip |

### Differentiators (Competitive Advantage)

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Transparent evidence trace (every setup links to exact bars/levels/zones) | Direct expression of PROJECT.md Core Value; counter-positions against black-box AI signal tools and opaque Telegram groups — the user can *verify* each claim on their own chart | MEDIUM | Mostly a data-model + UI discipline: persist the evidence object (zone IDs, bar timestamps, level values) and render it. No new math — high value per cost. **Make this the headline differentiator** |
| Dual-layer AI verdict: ML probability + LLM confirm/refute with agreement flag | Nobody in the SMC-tool space does structured dual-AI confirmation; separability is already mandated by PROJECT.md — surface it | MEDIUM | LLM sees ML output + evidence, returns {agree/disagree, confidence, reasoning, concerns}. Track agreement rate vs outcomes — that meta-statistic itself becomes a differentiating display ("LLM agreement adds +X% precision") |
| Calibrated probability + public reliability curve | "When we say 70%, it wins ~70%" — calibration reporting is standard ML practice but almost never surfaced in trading tools | MEDIUM | sklearn calibration_curve over backtest predictions; a simple reliability plot in the dashboard. Cheap, builds enormous trust |
| Backtest-validated pattern stats shown live ("this setup type: 58% over 24 months") | Closes the loop between backtesting and live signal presentation; live setups inherit historical credibility | MEDIUM–HIGH | Requires stable pattern taxonomy (sweep type × zone context × session) shared between backtest and live paths — design the tag vocabulary early |
| MTF confluence scoring (H4/H1 bias gating M15 entries) | Core SMC practice; generic SMC indicators show objects but don't *score* confluence | MEDIUM | H4/H1 premium/discount + structure bias → a small ordinal confluence score consumed by ML as a feature AND displayed as user-facing badge. Depends on MTF-aligned data (table stakes) |
| Sweep-quality micro-features feeding ML | Sweep speed (bars from take-out to reclaim), wick/body ratio, volume/tick surge, distance into pool — improves scoring and gives the LLM richer narrative | MEDIUM | Pure feature engineering on top of sweep events; no new detection infra |
| Session/kill-zone awareness (London/NY) | Forex-specific: sweep setups during London open/NY open have documented following-power; smc lib even ships session primitives | LOW–MEDIUM | Timestamp-based feature + dashboard filter; also removes dead-hour noise signals |
| Per-setup journal notes (user annotations) | Borrowed from trading journals: user records "took it / skipped it / why" — enables comparing system signals vs user behavior later, feeds execution milestone | LOW | Simple notes field on setup records; near-zero cost, compounds value at the execution milestone |

### Anti-Features (Commonly Requested, Often Problematic)

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| Order execution / one-click trading | "If the signal is good, why not auto-trade?" | Explicitly out of scope in PROJECT.md; execution before validated signal quality automates losses; broker API surface (orders, positions, error handling) roughly doubles the system | Signals-only + outcome tracking; execution is the *next milestone* by design |
| LLM-generated entry/SL/TP levels | "Let the AI decide everything" | LLMs hallucinate numbers; unconstrained numeric outputs are unverifiable and will occasionally be absurd; destroys the trust core value | LLM may only **confirm/refute and explain** a setup whose levels come from deterministic SMC rules; structured output schema forbids level invention |
| Full SMC kitchen sink in v1 (order blocks, FVG, BOS/CHoCH as labeled features) | "Just detect everything, more indicators = better" | Scope creep that delays the trust loop; each concept adds detection bugs, ML dimensionality, UI clutter; smc lib makes them *easy* to add later precisely because the base is done | v1 = sweeps + PD zones per PROJECT.md; add one concept per later phase with its own backtest validation |
| Real-time tick streaming / sub-second dashboard updates | "Traders need live data" | M15/H1/H4 system gains nothing from ticks; tick infra (websockets, reconnect logic, terminal load) is large; MT5 Python API is request/response oriented | Poll on bar close (M15 cadence) + a manual refresh; dashboard polls the local API every 30–60s |
| Online/continuous auto-retraining of the ML model | "The model should learn as markets change" | Unmonitored retraining on live outcomes is drift-and-overfit roulette; makes signal quality non-reproducible and backtest↔live comparisons meaningless | Scheduled, reviewed, versioned retrains (e.g. monthly) with walk-forward report diff before promotion |
| Multi-user accounts / hosted service | "Make it a SaaS" | Changes licensing posture (e.g. backtesting.py is AGPL), adds auth/billing infra, distracts from signal quality; system depends on *user's local* MT5 terminal anyway | Single-user local web app (localhost); revisit at commercialization |
| Push notifications to phone (Telegram/Discord alerts) in v1 | "I want signals on my phone" | Third-party bot plumbing, delivery-reliability concerns, and a temptation to act on signals away from the evidence-rich dashboard — undercutting the verify-the-evidence value | v1.x: browser notifications or email digest; only after the dashboard trust loop works. (Cheap enough to be first v1.x item) |
| Signal marketplace / social sharing / copy trading | Community appeal | Entirely different product (regulatory surface, moderation, infrastructure); zero contribution to signal quality | Keep the journal-notes differentiator; community is a possible v3+ pivot |

## Feature Dependencies

```
[MT5 ingestion: symbols/timeframes/cache]
        └──requires──> [running MT5 terminal + health checks]
        └──enables──> [data hygiene / UTC normalization]
                            └──requires by──> [MTF alignment]

[Swing-point detection (look-ahead-safe)]
        └──requires──> [MTF-aligned cached bars]
        └──enables──> [Equal highs/lows pools]
                            └──enables──> [Sweep detection + sweep-quality features]
        └──enables──> [PD zones + zone state machine]

[Sweep events] + [PD zone states] + [MTF bias]
        └──assemble──> [Evidence object (point-in-time)]
                            └──feeds──> [ML feature vector]  →  [calibrated probability score]
                            └──feeds──> [LLM narrative + confirm/refute]
                            └──feeds──> [Dashboard chart annotations]
        └──produces──> [Trade setup: entry/SL/TP/RR]
                            └──monitored by──> [Lifecycle tracking (active→outcome)]
                                                    └──feeds──> [Performance stats]
                                                    └──feeds──> [Calibration reporting]
                                                    └──feeds──> [Pattern-history stats]

[Backtest engine]
        └──requires──> [look-ahead-safe detection]  (conflicts with any lazy global-state detector)
        └──requires──> [spread/cost model]
        └──produces──> [walk-forward stats] → gates trust in live signals
        └──provides──> [labeled outcomes] → enables [ML calibration] (chicken-and-egg: bootstrap v0 model on heuristic score)

[Session/kill-zone features] ──enhances──> [ML scoring] + [dashboard filters]
[User journal notes] ──enhances──> [setup records] (feeds execution milestone)
[Alerts] ──requires──> [lifecycle tracking] (only notify on state changes)
```

### Dependency Notes

- **PD zones and sweeps both require swing detection:** This is the reason swing logic must be the first detection component built and tested; both headline concepts are thin layers over it.
- **Backtesting requires look-ahead-safe detection:** If detectors peek forward (swing confirmation, zone mitigation), backtest results are fiction and the mandatory trust gate fails. One code path for backtest/live is non-negotiable.
- **ML calibration requires labeled outcomes:** Only the backtester (and later, lifecycle-tracked live setups) produce labels. Early system runs on heuristic-scored setups until enough labeled data exists — plan the bootstrap explicitly.
- **LLM narrative requires the evidence object:** The LLM is a *consumer* of the same structured evidence the ML uses; building the evidence object before wiring the LLM avoids retrofitting.
- **Performance stats require lifecycle tracking:** Outcomes must be recorded as state transitions; stats are then pure queries.
- **MTF confluence conflicts with naive per-TF processing:** Confluence needs the H1/H4 context *as of the M15 bar's timestamp* — point-in-time joins across TFs, not "latest H4 row" (subtle look-ahead).

## MVP Definition

### Launch With (v1)

- [ ] MT5 ingestion: 3 majors × 3 TFs, UTC-normalized, cached with incremental updates, health checks — everything downstream depends on it
- [ ] Look-ahead-safe swing detection + liquidity pools + sweep events (with reclaim rule) — the core v1 SMC concept, done as point-in-time from day one
- [ ] PD zones from confirmed swing ranges, with zone lifecycle state machine — the second core concept; state machine is shared infra for ML/LLM/UI
- [ ] Setup generation with entry/SL/TP + RR + evidence object + lifecycle tracking — the product *is* the setup record; outcome tracking powers all stats
- [ ] ML probability scoring (gradient boosting, calibrated, walk-forward evaluated) — PROJECT.md mandate; calibration makes the number meaningful
- [ ] LLM narrative + confirm/refute over evidence object (structured output) — PROJECT.md mandate; must stay a separate component
- [ ] Backtest engine replaying the same pipeline with spread modeling + canonical stats (WR, PF, expectancy, max DD, per symbol/TF) — mandatory trust gate
- [ ] Web dashboard: setup table with filters, candlestick chart with entry/SL/TP + sweep/zone annotations, setup history + outcomes, aggregate performance panel, data-health strip — the delivery surface

### Add After Validation (v1.x)

- [ ] Calibration reliability report in dashboard — trigger: enough labeled outcomes from backtest/live to plot meaningfully
- [ ] Per-pattern historical stats surfaced on live setups ("this pattern: 58%/24mo") — trigger: stable pattern taxonomy from backtest runs
- [ ] Session/kill-zone features + filters — trigger: backtest shows session-dependent performance worth exposing
- [ ] Sweep-quality micro-features — trigger: ML plateaued on coarse features
- [ ] Alerts (browser notifications / email digest) — trigger: user trusts signals enough to want them away from the dashboard
- [ ] User journal notes per setup — trigger: user actively triaging signals manually

### Future Consideration (v2+)

- [ ] Order execution milestone (semi-auto first) — explicitly the next milestone per PROJECT.md; only after v1 signals are trusted
- [ ] Additional SMC concepts as first-class features (order blocks, FVG, BOS/CHoCH) — one concept per phase, each backtest-validated before UI exposure
- [ ] More instruments (indices/crypto/metals) and data vendors — blocked in v1 by PROJECT.md scope
- [ ] Multi-user/hosted or mobile — different product surface; revisit after execution milestone

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| MT5 ingestion + cache + hygiene | HIGH | MEDIUM | P1 |
| Look-ahead-safe swings/pools/sweeps | HIGH | MEDIUM–HIGH (correctness-critical) | P1 |
| PD zones + lifecycle state | HIGH | MEDIUM | P1 |
| Setup record + SL/TP + lifecycle tracking | HIGH | MEDIUM | P1 |
| Calibrated ML probability score | HIGH | MEDIUM | P1 |
| LLM narrative + confirm/refute | HIGH | MEDIUM | P1 |
| Backtest engine + spread + canonical stats | HIGH | MEDIUM–HIGH | P1 |
| Dashboard: table + annotated chart + history + stats + health | HIGH | MEDIUM | P1 |
| Evidence trace UI (verify every claim) | HIGH | LOW–MEDIUM | P1 |
| ML↔LLM agreement flag | MEDIUM | LOW | P1 |
| Calibration reliability report | MEDIUM | LOW–MEDIUM | P2 |
| Per-pattern historical stats on live setups | MEDIUM–HIGH | MEDIUM | P2 |
| MTF confluence score (badge + ML feature) | MEDIUM–HIGH | MEDIUM | P2 |
| Session/kill-zone features | MEDIUM | LOW–MEDIUM | P2 |
| Sweep-quality micro-features | MEDIUM | MEDIUM | P2 |
| Alerts (browser/email) | MEDIUM | LOW–MEDIUM | P2 |
| User journal notes | MEDIUM | LOW | P2 |
| Order execution | HIGH (later) | HIGH | P3 (next milestone, gated on trust) |
| Additional SMC concepts (OB/FVG/BOS) | MEDIUM | MEDIUM each | P3 |
| Other instruments / vendors / multi-user | LOW–MEDIUM now | MEDIUM–HIGH | P3 |

**Priority key:**
- P1: Must have for launch
- P2: Should have, add when possible
- P3: Nice to have, future consideration

## Competitor Feature Analysis

| Feature | smartmoneyconcepts lib (open-source) | SMC indicators (TradingView/LuxAlgo class)* | Trading journals (Tradervue class) | Generic AI signal tools (black-box class)* | Our Approach |
|---------|--------------------------------------|----------------------------------------------|-------------------------------------|---------------------------------------------|--------------|
| SMC detection (sweeps, PD zones) | Yes — code primitives incl. `Swept` index | Yes — rich visual SMC object rendering | No | Implied, not shown | Same primitives, but **point-in-time safe** + persisted as queryable events |
| Setup lifecycle tracking | No | No | Yes (for user trades) | Rarely | First-class: every setup has status + recorded outcome |
| Probability scoring | No | No | No | Yes (score only) | **Calibrated** probability + published reliability curve |
| Narrative reasoning | No | No | No | Marketing claims only | LLM narrative over verifiable evidence, confirm/refute stance |
| Evidence transparency | Code-level only | Visual only | Charts per trade | None | Evidence object rendered: levels, zones, bars, MTF bias |
| Backtesting | No | Strategy-tester manual | N/A | Vague claims | Same pipeline replays history; spread-modeled, walk-forward |
| Dashboard | None (library) | Chart platform | Strong stats, weak AI | Web dashboards, opaque | Chart + SMC annotations + journal-grade stats + AI layers |

\* Training-knowledge characterization (MEDIUM confidence — web survey unavailable this session; verify if these become design-critical).

**Positioning takeaway:** No existing free/open option combines SMC detection + lifecycle-tracked setups + calibrated scoring + transparent narrative + backtest parity. The differentiated core is **trust through verifiability**, which maps exactly to the PROJECT.md Core Value.

## Sources

- smartmoneyconcepts library README (github.com/joshyattridge/smart-money-concepts, official, ~2k stars, MIT) — HIGH: detection canon, parameters, `Swept` index, swing lookahead behavior
- MetaTrader5 PyPI page (official MetaQuotes, v5.0.6147, 2026-08-27) — HIGH: version, Windows-only, Python 3.6–3.14 support; API surface via MetaTrader5 documentation MCP context (context7, MEDIUM): copy_rates_*, symbol info, timeframes
- TradingView Lightweight Charts README (official, 17.1k stars, v5, Apache-2.0 + attribution) — HIGH: dashboard charting capability set
- backtesting.py README (official, 8.9k stars, AGPL-3.0) — HIGH: canonical backtest stat set, cost modeling expectations
- Tradervue homepage (official site, market-leading journal) — HIGH: journal/dashboard table-stakes feature set (tags→performance, MFE/MAE, calendar, reports)
- scikit-learn official docs via context7 (CalibratedClassifierCV, HistGradientBoostingClassifier, calibration curve) — MEDIUM-HIGH: ML scoring mechanics
- Competitor landscape rows (LuxAlgo-class indicators, black-box AI signal tools) — MEDIUM/LOW: characterized from domain knowledge; SearXNG web search was rate-suspended during the session (all engines: brave/duckduckgo/startpage/karmasearch unresponsive), so these were not web-verified

---
*Feature research for: AI forex SMC trading signal system (hybrid ML+LLM, MT5 feed)*
*Researched: 2026-08-29*
