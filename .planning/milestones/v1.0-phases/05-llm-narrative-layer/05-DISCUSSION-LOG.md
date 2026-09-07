# Phase 5: LLM Narrative Layer - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-09-04
**Phase:** 5-LLM Narrative Layer
**Areas discussed:** Evidence object scope

---

## Evidence object scope

### Q1: What should the LLM's evidence object contain?

| Option | Description | Selected |
|--------|-------------|----------|
| Full structured evidence (Recommended) | SMC context (zone ID/state, sweep, pool, MTF bias, direction), structural SL/TP/entry + R:R (reference-only), ML P(WIN) + top feature contributors. | ✓ |
| Narrative-only subset | SMC narrative + ML verdict, no price levels/contributor details. | |
| Full + critique mode | Full evidence + LLM may flag suspicious/inconsistent inputs. | |

**User's choice:** Full structured evidence

### Q2: How strictly should structural SL/TP/entry levels be gated?

| Option | Description | Selected |
|--------|-------------|----------|
| Reference-only + schema guard (Recommended) | Labeled reference-only; schema drops any level field the LLM emits. | ✓ |
| Reference-only, prompt constraint | Instruction-only; no schema-level guard. | |
| AAT-only levels | Show only ATR-normalized/relative measures, no raw prices. | |

**User's choice:** Reference-only + schema guard

### Q3: Structured output contract

| Option | Description | Selected |
|--------|-------------|----------|
| Verdict+confidence+reasoning+citations (Recommended) | JSON `{verdict, confidence, reasoning, citations}` with mechanical map to evidence fields. | ✓ |
| Add action hint | Plus a trade/discard/watch action field. | |
| Free-form narrative | No forced structured verdict; flag by keyword. | |

**User's choice:** Verdict+confidence+reasoning+citations

### Q4: Citation check behavior on mismatch

| Option | Description | Selected |
|--------|-------------|----------|
| Strict — flag & discard on mismatch (Recommended) | Flag `unverified` + discard the narrative for that setup. | ✓ |
| Soft — downgrade | Downgrade confidence, keep narrative. | |
| Advisory-only | Log only; keep narrative. | |

**User's choice:** Strict — flag & discard on mismatch

### Q5: ML feature-contribution detail

| Option | Description | Selected |
|--------|-------------|----------|
| Top 5 contributors (Recommended) | Top-5 with effect direction. | ✓ |
| All 18 contributors | Full per-feature breakdown. | |
| Score only | Just P(WIN) + conviction summary. | |

**User's choice:** Top 5 contributors

### Q6: Raw price/candle data?

| Option | Description | Selected |
|--------|-------------|----------|
| Structured-only, no raw candles (Recommended) | Strictly the evidence object; no OHLC series. | ✓ |
| Add recent candle context | Last ~20 bars for price context. | |
| Structured + zone/pool ranges | Zone high/low + sweep/pool levels, no candle series. | |

**User's choice:** Structured-only, no raw candles

---

## the agent's Discretion (not discussed)

- Agreement flag semantics (AI-06) — verdict ↔ P(WIN) mapping, 3-state + confidence, disagreement definition
- Degradation/fallback policy (AI-07) — timeout, retry, ML-only appearance
- Provider + endpoint choice — local vLLM via OpenAI SDK, abstracted; Anthropic in v1?
- Evidence serialization format; top-5 contributor ranking mechanism

## Deferred Ideas

- Anthropic as first-class v1 provider
- Action-hint field (trade/discard/watch) beyond confirm/refute
- ENH calibration/agreement reporting (v2 display)
