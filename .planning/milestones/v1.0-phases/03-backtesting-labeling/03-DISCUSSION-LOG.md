# Phase 3: Backtesting & Labeling - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-09-01
**Phase:** 3-Backtesting & Labeling
**Areas discussed:** Entry candidate definition, SL/TP placement rules, Slippage buffer sizing, Time barrier + walk-forward windows

---

## Entry Candidate Definition

| Option | Description | Selected |
|--------|-------------|----------|
| Sweep + zone tap | Classic SMC: sweep event, then price returns into PD zone on right side and mitigates it | ✓ |
| Sweep-only | Any sweep reclaim close generates a candidate | |
| Zone-only | Any PD zone mitigation generates a candidate | |

**User's choice:** Sweep + zone tap
**Notes:** Most selective, highest-conviction samples.

| Option | Description | Selected |
|--------|-------------|----------|
| Respect bias | Only label when H1/H4 bias agrees | ✓ |
| All, record bias | Label all, record bias for Phase 4 filtering | |
| Both variants | Two label sets | |

**User's choice:** Respect bias

| Option | Description | Selected |
|--------|-------------|----------|
| Define now, share | Phase 3 owns entry rule as pure functions, Phase 6 reuses | ✓ |
| Pluggable contract | Backtester accepts pluggable entry/SL/TP generators | |

**User's choice:** Define now, share

| Option | Description | Selected |
|--------|-------------|----------|
| Next-bar open | Signal at M15 close, fill at next bar open | ✓ |
| Limit at zone level | Fill if bar trades into level intrabar | |
| Both, configurable | Support both | |

**User's choice:** Next-bar open

| Option | Description | Selected |
|--------|-------------|----------|
| One at a time | Suppress new candidates until current resolves | ✓ |
| Allow concurrent | Allow overlapping candidates | |
| Configurable | Config default one-at-a-time | |

**User's choice:** One at a time

| Option | Description | Selected |
|--------|-------------|----------|
| M15 only | Candidates on M15; H1/H4 bias context only | ✓ |
| All timeframes | Also generate on H1/H4 | |

**User's choice:** M15 only

| Option | Description | Selected |
|--------|-------------|----------|
| Auto warmup, skip | Silently skip labels during warmup | ✓ |
| Fail fast | Refuse run if warmup bars missing | |
| Configurable | Warmup config override | |

**User's choice:** Auto warmup, skip

---

## SL/TP Placement Rules

| Option | Description | Selected |
|--------|-------------|----------|
| Structural, raw | SL beyond swept pool / zone far boundary, no buffer | ✓ |
| Structural + ATR buffer | Same anchor + ATR buffer | |
| ATR multiple | SL = ATR multiple from entry | |

**User's choice:** Structural, raw

| Option | Description | Selected |
|--------|-------------|----------|
| Structural target | Far side of zone / opposite pool / prior swing | ✓ |
| Fixed R:R | Entry + N × SL distance | |
| Structural, capped R:R | Structural with max R:R cap | |

**User's choice:** Structural target

| Option | Description | Selected |
|--------|-------------|----------|
| SL-first, all bars | Conservative uniform tie rule | ✓ |
| TP-first on entry bar | Different rule at entry bar | |
| Configurable | Default SL-first | |

**User's choice:** SL-first, all bars

| Option | Description | Selected |
|--------|-------------|----------|
| Fill at open | Exit at bar OPEN if gapped through | ✓ |
| Fill at open + flag | Also flag gap labels | |
| Ignore gaps | Assume SL always fills at level | |

**User's choice:** Fill at open

| Option | Description | Selected |
|--------|-------------|----------|
| Discard below min | R:R < 1.0 candidates discarded | ✓ |
| Label all, record ratio | Keep everything, record ratio | |
| Configurable | Default 1.0 | |

**User's choice:** Discard below min

| Option | Description | Selected |
|--------|-------------|----------|
| Raw detector levels | Zone boundaries / pool levels as-is | ✓ |
| Freeze at confirmation | Re-derive and freeze at trade open | |

**User's choice:** Raw detector levels

---

## Slippage Buffer Sizing

| Option | Description | Selected |
|--------|-------------|----------|
| Fixed pips per symbol | Config, e.g., 0.5 pip, per-symbol override | ✓ |
| ATR-relative | Fraction of bar ATR | |
| Per-symbol config | Fixed but overridable per symbol | |

**User's choice:** Fixed pips per symbol

| Option | Description | Selected |
|--------|-------------|----------|
| Bar spread + fallback | COLUMNS.spread with config default fallback | ✓ |
| Config default only | Uniform default spread | |
| No fallback, flag | Flag/skip missing spread | |

**User's choice:** Bar spread + fallback

| Option | Description | Selected |
|--------|-------------|----------|
| ~0.5 pip | Modest realistic buffer per side | ✓ |
| ~1.0 pip | Conservative pessimistic | |
| Spread-only baseline | Zero buffer | |

**User's choice:** ~0.5 pip

| Option | Description | Selected |
|--------|-------------|----------|
| Both raw + net | Raw and net metrics with cost delta | ✓ |
| Net only | One metric set | |
| Net + sensitivity table | Slippage sensitivity table | |

**User's choice:** Both raw + net

---

## Time Barrier + Walk-Forward Windows

| Option | Description | Selected |
|--------|-------------|----------|
| 96 bars / 24h | Time barrier = one trading day | ✓ |
| 192 bars / 48h | Two trading days | |
| 48 bars / 12h | One session | |
| Configurable, default 96 | Config knob | |

**User's choice:** 96 bars / 24h

| Option | Description | Selected |
|--------|-------------|----------|
| WIN/LOSS/TIMEOUT | Three classes | ✓ |
| Binary only | Profitable vs not | |
| 3 classes + flags | Classes with sub-flags | |

**User's choice:** WIN/LOSS/TIMEOUT

| Option | Description | Selected |
|--------|-------------|----------|
| Expanding train + rolling test | No overlap, chronological | ✓ |
| Rolling window | Fixed-length train slides too | |
| Planner decides | Parameterized harness only | |

**User's choice:** Expanding train + rolling test

| Option | Description | Selected |
|--------|-------------|----------|
| 6mo/1mo, configurable | Calendar windows, shorter supported | ✓ |
| Bar-count based | Split by bar counts | |
| Fixed calendar only | Strict calendar windows | |

**User's choice:** 6mo/1mo, configurable

| Option | Description | Selected |
|--------|-------------|----------|
| ~30 days min | Minimum history gate | ✓ |
| 90 days min | Strict | |
| No gate, flag coverage | Never block | |

**User's choice:** ~30 days min

| Option | Description | Selected |
|--------|-------------|----------|
| Per symbol/TF + per window | Full stats everywhere | ✓ |
| Full run + window summary | Window summary only | |

**User's choice:** Per symbol/TF + per window

---

## the agent's Discretion

- Report artifact format and on-disk layout
- Label store schema and caching strategy
- Replay engine implementation (vectorized vs per-bar loop)
- Intrabar path assumptions beyond O/H/L/C
- Entry-rule module layout
- Backtest runner invocation (CLI/config)

## Deferred Ideas

None discussed. (Cost-sensitivity table over slippage was offered, not selected — possible future enhancement.)
