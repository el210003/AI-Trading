# Phase 2: SMC Detection Engine - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-08-30
**Phase:** 2-SMC Detection Engine
**Areas discussed:** Swing definition, Pools + sweep/reclaim rule, PD zones + lifecycle, MTF context payload

---

## Swing Definition

| Option | Description | Selected |
|--------|-------------|----------|
| 2/2 fractal | Standard 5-bar fractal; confirms 2 bars after extreme; fewer whipsaws on M15 | ✓ |
| 1/1 pivot | 3-bar pivot; earlier confirmation but ~2-3x more swings, noisier pools | |
| 3/3 fractal | 7-bar fractal; only major swings, much later confirmation | |

**User's choice:** 2/2 fractal
**Notes:** —

| Option | Description | Selected |
|--------|-------------|----------|
| Strict | Equal prices never form swings; equal levels surface as liquidity pools | ✓ |
| Ties allowed | >= on one side; equal highs can both be swings; double-counts levels | |

**User's choice:** Strict
**Notes:** Equal-level logic belongs to pool clustering (SMC-02).

| Option | Description | Selected |
|--------|-------------|----------|
| Minimal | (symbol, timeframe, bar_time, price, side, confirmed_at) only | ✓ |
| Enriched | + prominence/bars-since/range-span metrics now | |

**User's choice:** Minimal
**Notes:** Downstream computes what it needs; smaller repaint-test surface.

| Option | Description | Selected |
|--------|-------------|----------|
| Alternating zigzag | Same-side confirmed swing replaces previous extreme if more extreme; clean ranges + unambiguous BOS/CHoCH labeling | ✓ |
| Raw swing list | All confirmed swings independent; ranges ad-hoc | |

**User's choice:** Alternating zigzag
**Notes:** —

## Pools + Sweep/Reclaim Rule

| Option | Description | Selected |
|--------|-------------|----------|
| ATR(14) × 0.1 | Tight standard clustering | ✓ |
| ATR(14) × 0.25 | Loose; more pools, more noise | |
| Fixed pips | Transparent but ignores volatility regimes | |

**User's choice:** ATR(14) × 0.1
**Notes:** —

| Option | Description | Selected |
|--------|-------------|----------|
| 2 touches | Cluster members themselves form the pool | ✓ |
| 3+ touches | Fewer, stronger pools; misses fresh liquidity | |

**User's choice:** 2 touches
**Notes:** —

| Option | Description | Selected |
|--------|-------------|----------|
| Close-back ≤ 2 bars | Wick pierce + close back within 2 bars = sweep; else reclassified breakout | ✓ |
| Same-bar reclaim only | Strictest stop-hunt signature; misses multi-bar sweeps | |
| Close-back ≤ 3-5 bars | Catches slow sweeps; fuzzy, late sweep-vs-breakout boundary | |

**User's choice:** Close-back ≤ 2 bars
**Notes:** Window measured in detector-timeframe bars.

| Option | Description | Selected |
|--------|-------------|----------|
| One-and-done | Swept pool ends lifecycle (swept/broken); new clusters = new pools | ✓ |
| Re-sweepable | Pool stays active, can be swept again in layers | |

**User's choice:** One-and-done
**Notes:** Clean evidence attribution for ML/LLM later.

## PD Zones + Lifecycle

| Option | Description | Selected |
|--------|-------------|----------|
| Per zigzag leg | Each completed confirmed leg defines one range; premium/discount = 50/50 split | ✓ |
| N-leg dealing range | Larger dealing-range style; more selection logic to keep repaint-safe | |
| Sweep-anchored range | Zone only exists post-sweep; misses pre-sweep context | |

**User's choice:** Per zigzag leg
**Notes:** —

| Option | Description | Selected |
|--------|-------------|----------|
| Wick touch | Trades into zone (near boundary) = mitigated | ✓ |
| Close inside | Stricter; wick pokes don't count | |
| Beyond equilibrium | Most conservative; only deep incursions | |

**User's choice:** Wick touch
**Notes:** —

| Option | Description | Selected |
|--------|-------------|----------|
| Close beyond far boundary | Committed close kills the zone; wick pokes don't | ✓ |
| Structure break (zigzag) | Invalidation tied to new opposite zigzag leg | |
| Either rule | OR'd; most responsive, more complex | |

**User's choice:** Close beyond far boundary
**Notes:** Aligns with sweep close-back discipline.

| Option | Description | Selected |
|--------|-------------|----------|
| Track all zones | Full zone history with lifecycle timestamps for ML/evidence | ✓ |
| Latest-only per direction | Lean state; loses ML history | |

**User's choice:** Track all zones
**Notes:** —

## MTF Context Payload

| Option | Description | Selected |
|--------|-------------|----------|
| Premium/discount position | M15 close inside HTF range: premium → bearish, discount → bullish | ✓ |
| Last HTF leg direction | Structure-following; flips later | |
| Both fields | pd_bias + structure_bias | |

**User's choice:** Premium/discount position
**Notes:** Reuses the locked zone machinery.

| Option | Description | Selected |
|--------|-------------|----------|
| Lean payload | bias, HTF range high/low/EQ, distance-to-EQ (ATR units), containing-zone IDs | ✓ |
| Extended payload | + HTF pools/sweeps/lifecycle states as-of bar | |

**User's choice:** Lean payload
**Notes:** —

| Option | Description | Selected |
|--------|-------------|----------|
| Confirmation-time as-of | M15 bar at T sees only HTF state confirmed strictly before T | ✓ |
| Bar-open-time join | Leaks future HTF structure — lookahead bug class | |

**User's choice:** Confirmation-time as-of
**Notes:** The #1 MTF lookahead trap, pinned explicitly (ROADMAP SC4).

## the agent's Discretion

- ATR smoothing variant and clustering algorithm internals
- Gap/weekend/session handling; DST-shifted H4 anchor test coverage
- Zone/pool/sweep ID scheme; state-machine implementation; module layout; output schema details beyond pinned fields
- Detector state persistence vs recomputation (planner decides under the shared-pipeline constraint)

## Deferred Ideas

- FVG / imbalance detection as first-class features — user asked ("FVG?"); already tracked as SMCX-02 (v2), out of scope for v1 per the locked scope decision (each SMC concept needs its own backtest validation). Noted as v2 prioritization candidate.
