# Phase 5: LLM Narrative Layer - Context

**Gathered:** 2026-09-04
**Status:** Ready for planning

<domain>
## Phase Boundary

Evidence-grounded LLM confirm/refute reasoning as a separable, degradable component, built on the Phase 4 calibrated ML scoring. A provider interface (local vLLM via the OpenAI-compatible SDK; Anthropic optional) with a structured-output contract, and a narrative pipeline that serializes the setup evidence object, produces a structured narrative + verdict with a citation check, derives an ML↔LLM agreement flag, and degrades gracefully to ML-only setups when the LLM endpoint is unavailable or slow. Scope covers AI-05…AI-07 only: no setup assembly or dashboard (Phase 6), no order execution, and — critically — the LLM NEVER originates entry/SL/TP levels or probabilities (PROJECT.md out-of-scope, core-value constraint).

</domain>

<decisions>
## Implementation Decisions

### Evidence Object Scope (the LLM's input)
- **D-01:** The LLM receives the **full structured evidence object** — the SMC context (tapped zone ID + lifecycle state, sweep event + pool, MTF bias from the D-14 payload, direction), the structural SL/TP/entry + R:R (framed reference-only), and the ML P(WIN) + **top 5 feature contributors** with effect direction. Rich and fully verifiable; aligns with SETUP-02's full evidence trace.
- **D-02:** Structural SL/TP/entry levels are **reference-only** — the LLM may *comment* on them but is structurally prevented from returning/recomputing alternatives. A **schema-level guard drops any level field** the LLM emits (enforces SC1; never rely on prompt adherence alone).
- **D-03:** The LLM receives **strictly the structured evidence object — no raw OHLC/candle series**. The prompt is tight, matches SC1's "only the structured evidence object" literally, and keeps the citation check airtight (every claim maps to a field).

### Structured Output Contract
- **D-04:** The LLM returns structured JSON: `{verdict: confirm|refute, confidence: 0-1, reasoning: short evidence-grounded paragraph, citations: [field keys from the evidence object the reasoning references]}`. Citations map exactly to real evidence fields so the citation check is mechanical. (AI-06 agreement flag derives from this verdict + confidence.)

### Citation Check (SC1 enforcement)
- **D-05:** **Strict** — citations must map to real evidence object fields (and values must match: zone state, direction, bias, etc.). A non-existent field or a factual mismatch flags the narrative `unverified` and **discards** it for that setup (counted, never silently kept). This is the mechanism that proves the LLM never *originates* information (SC1).

### the agent's Discretion
- **Agreement flag semantics** (AI-06) — how verdict + ML P(WIN) map to agree/disagree, whether a 3-state with confidence (agree/disagree/unclear) is used, and what counts as disagreement (opposite verdict vs significant probability gap). Not discussed — research/planner decides within the AI-06 "word: agree/disagree with confidence" contract.
- **Degradation/fallback policy** (AI-07) — timeout threshold, retry, and what "complete ML-only setup" looks like (silent vs with a note). Not discussed — research/planner decides within SC3's "graceful fallback proven by test".
- **Provider + endpoint choice** — local vLLM via OpenAI-compatible SDK as primary (matches existing infra, e.g. the machine's local vLLM server), abstracted interface so any OpenAI-compatible/Anthropic endpoint works; which model; whether Anthropic is in v1 scope. Not discussed — research/planner decides (plan 05-01 sketch names OpenAI SDK + optional Anthropic).
- Evidence serialization format / details of the OpenAI-compatible structured-output (JSON schema) approach
- How the top-5 contributors are ranked/exposed (LightGBM pred_contrib) and how null contributors are handled

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Locked scope + goals
- `.planning/ROADMAP.md` — Phase 5 goal, success criteria SC1–3, plan breakdown 05-01…05-02
- `.planning/REQUIREMENTS.md` — AI-05…AI-07 definitions; OUT of Scope table (LLM never originates entry/SL/TP levels; AI-06 agreement flag; AI-07 ML-only fallback); ENH items are v2
- `.planning/PROJECT.md` — core value (transparent, verifiable evidence); hybrid AI separation (ML owns probability; LLM separable, degradable component); out-of-scope "LLM-originated levels"

### Phase 4 contracts (what the LLM narrates)
- `.planning/phases/04-ml-scoring/04-CONTEXT.md` — D-01…D-05 (P(WIN) decided-only, pooled model, calibrated scorer); the setup evidence/provenance the LLM consumes
- `.planning/phases/04-ml-scoring/04-VERIFICATION.md` + `04-01/02/03-SUMMARY.md` — versioned artifact + loadable scorer API, ml_scores.parquet schema (p_win, score_source, provenance, artifact_version), feature contributors
- `data/reports/ml_scores.parquet` (runtime) — per-setup record the narrative attaches to; `data/reports/ml_reliability.parquet` — calibration context
- `src/ai_trading/ml/scorer.py` — the loadable scorer Phase 6 / narrative pipeline calls; the P(WIN) the LLM comments on
- `src/ai_trading/ml/features.py` — FEATURE_SPEC + _CATEGORICAL_CATEGORIES; the feature names/contributors the evidence object exposes

### Phase 2/3 contracts (the SMC evidence fields)
- `.planning/phases/02-smc-detection-engine/02-CONTEXT.md` — zone/pool/sweep fields (D-12 zone state + lifecycle, D-14 lean MTF payload bias, D-15 as-of), the IDs the evidence object cites
- `.planning/phases/03-backtesting-labeling/03-CONTEXT.md` — labels D-18 (WIN/LOSS/TIMEOUT), entry-candidate evidence (D-01…D-13, zone_id/event_id/pool_id, structural SL/TP), SETUP-02 evidence object lineage

### Integration surface (code)
- `src/ai_trading/ml/` — scorer + features the narrative consumes (MT5-free, pure)
- `src/ai_trading/backtest/candidates.py` — CandidateState / evidence fields (direction, sl/tp, zone/event/pool ids, bias)
- Phase 6 setup assembly (imports these) — the narrative attaches to the setup record later

### Test conventions
- `.planning/phases/01-data-foundation/01-VALIDATION.md` — Nyquist verification map; unit/mt5 marker layering; the LLM-provider path must be testable WITHOUT a live endpoint (mock/fake provider — AI-07 fallback must be proven offline)
- `.planning/phases/04-ml-scoring/04-RESEARCH.md` — verified API/patterns the narrative pipeline should follow

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `ml/scorer.py` `score()` — returns P(WIN) + provenance + feature contributors; the evidence object's ML portion
- `ml/features.py` FEATURE_SPEC + `_CATEGORICAL_CATEGORIES` — the feature names/contributors to surface (top 5)
- `backtest/candidates.py` CandidateState — zone/event/pool IDs, direction, structural SL/TP — the SMC evidence fields
- `backtest/asof.py` STAMP_CLOSE/STAMP_BAR + `visible_mask` — point-in-time discipline the evidence serialization must respect (no future data)
- Plan 03 runner CLI exit-code contract + atomic writer pattern — the narrative pipeline's output/fallback conventions

### Established Patterns
- Pure, MT5-free modules in the tier; provider interface must be mockable for offline tests
- Frozen `Config` dataclass (config.py) extension for LLM knobs (endpoint, model, timeout, top-n contributors)
- Atomic tmp+os.replace artifact writers for narrative output
- pytest `unit`/`mt5` markers; the LLM path must be `unit`-testable with a fake provider (no live endpoint); ruff line-length 100

### Integration Points
- **Phase 6 Setups**: narrative + agreement flag attaches to the setup record; the dashboard renders it (DASH-03 evidence trace)
- **Phase 6 Dashboard**: shows the ML↔LLM agreement flag; the narrative is a user-facing evidence field
- **Provider**: OpenAI-compatible endpoint (local vLLM on this machine) via the openai SDK; abstracted so Anthropic/other OpenAI-compatible endpoints work

</code_context>

<specifics>
## Specific Ideas

- The ML↔LLM agreement flag (AI-06) and the confidence field feed the dashboard's agreement display; the verdict is `confirm`/`refute` per D-04
- SC1 is the hard constraint: the LLM receives the evidence object, returns verdict + citations, never levels/probabilities. The citation check (D-05) is the enforcement proof
- SC3 is the other hard constraint: with the endpoint disabled or timing out, the pipeline still emits complete ML-only setups — must be proven by an offline test (AI-07)
- The provider must be an interface so tests inject a fake; a live-endpoint integration test stays under the `mt5`-style opt-in marker (or a separate `llm`/integration marker) so the suite stays offline-clean

</specifics>

<deferred>
## Deferred Ideas

- **Anthropic as a first-class provider in v1** — plan names it optional; whether to wire a second provider is a scope decision left to planning/research. (Non-blocking — the interface abstracts it either way.)
- **Action-hint field** ("trade/discard/watch") beyond confirm/refute — offered during discussion, not selected for v1; a natural enhancement if agreement/labels support it later.
- **ENH-xx calibration/agreement reporting** — v2 display work; Phase 5 records the data.

</deferred>

---

*Phase: 5-LLM Narrative Layer*
*Context gathered: 2026-09-04*
