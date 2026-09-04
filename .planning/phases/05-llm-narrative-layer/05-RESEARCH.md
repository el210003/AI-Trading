# Phase 5: LLM Narrative Layer - Research

**Researched:** 2026-09-04
**Domain:** OpenAI-compatible LLM provider abstraction + evidence-grounded structured-output narrative pipeline over Phase 4 ML scoring
**Confidence:** MEDIUM (stack is verified; runtime behaviour of a reasoning model imposes operational caveats)

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** The LLM receives the **full structured evidence object** — the SMC context (tapped zone ID + lifecycle state, sweep event + pool, MTF bias from the D-14 payload, direction), the structural SL/TP/entry + R:R (framed reference-only), and the ML P(WIN) + **top 5 feature contributors** with effect direction. Rich and fully verifiable; aligns with SETUP-02's full evidence trace.
- **D-02:** Structural SL/TP/entry levels are **reference-only** — the LLM may *comment* on them but is structurally prevented from returning/recomputing alternatives. A **schema-level guard drops any level field** the LLM emits (enforces SC1; never rely on prompt adherence alone).
- **D-03:** The LLM receives **strictly the structured evidence object — no raw OHLC/candle series**. The prompt is tight, matches SC1's "only the structured evidence object" literally.
- **D-04:** The LLM returns structured JSON: `{verdict: confirm|refute, confidence: 0-1, reasoning: short evidence-grounded paragraph, citations: [field keys from the evidence object the reasoning references]}`.
- **D-05:** **Strict** citation check — citations must map to real evidence object fields (and values must match: zone state, direction, bias, etc.). A non-existent field or a factual mismatch flags the narrative `unverified` and **discards** it for that setup (counted, never silently kept).

### the agent's Discretion
- Agreement flag semantics (AI-06) — how verdict + ML P(WIN) map to agree/disagree, whether a 3-state with confidence (agree/disagree/unclear) is used, and what counts as disagreement (opposite verdict vs significant probability gap).
- Degradation/fallback policy (AI-07) — timeout threshold, retry, and what "complete ML-only setup" looks like (silent vs with a note).
- Provider + endpoint choice — local vLLM via OpenAI-compatible SDK as primary, abstracted interface so any OpenAI-compatible/Anthropic endpoint works; which model; whether Anthropic is in v1 scope.
- Evidence serialization format / details of the OpenAI-compatible structured-output (JSON schema) approach
- How the top-5 contributors are ranked/exposed (LightGBM pred_contrib) and how null contributors are handled

### Deferred Ideas (OUT OF SCOPE)
- Anthropic as a first-class provider in v1 — interface abstracts it, but wiring a second provider is a scope decision left to planning/research.
- Action-hint field ("trade/discard/watch") beyond confirm/refute — not selected for v1.
- ENH-xx calibration/agreement reporting — v2 display work; Phase 5 records the data.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| AI-05 | Each setup receives an LLM narrative that confirms or refutes using only the structured evidence object | Structured-output contract (D-04) + evidence serializer (Scorer.score/contributors + CandidateState fields) + strict citation check (D-05) + schema-level guard (D-02). §Provider Interface, §Evidence Serialization, §Citation Check. |
| AI-06 | Setups expose an ML↔LLM agreement flag (agree/disagree with confidence) | Verdict + confidence map to 3-state agreement flag. §Agreement Flag. |
| AI-07 | System degrades gracefully to ML-only setups when the LLM endpoint is unavailable or slow | Timeout/retry policy + ML-only emission path proven by offline fake-provider test. §Graceful Fallback. |
</phase_requirements>

## Project Constraints (from AGENTS.md)

No `./AGENTS.md`, `./CLAUDE.md`, or `./.claude/CLAUDE.md` exists at the repo root (verified). Follow the conventions documented in the phase CONTEXT.md canonical refs and the existing source under `src/ai_trading/`: Python 3.12, `pandas>=3.0`, `pytest 9.x` (unit/mt5 markers), `ruff line-length 100`, pure MT5-free modules in the tier, frozen `Config` dataclass extension, atomic `tmp+os.replace` writers.

## Summary

Phase 5 builds a **separable, degradable evidence-grounded LLM narrative** as a pure, MT5-free tier that consumes the Phase 4 calibrated scorer. Plan 05-01 delivers the **provider interface + structured-output contract**: an abstract `LLMProvider` (duck-typed, mirroring the codebase's `FakeMT5Client` pattern) with an `OpenAICompatProvider` wrapping the `openai` SDK pointed at a local vLLM endpoint via `base_url`, plus a pydantic-validated `LLMNarrative` schema (`verdict`, `confidence`, `reasoning`, `citations`). Plan 05-02 delivers the **narrative pipeline**: evidence serialization from `Scorer.score()` (calibrated P(WIN)) + `Scorer.contributors()` (raw pred_contrib, top-5) + `CandidateState` SMC fields, a strict citation check, an ML↔LLM agreement flag, and a timeout/retry fallback that emits complete ML-only setups.

Two verified facts dominate the design. First, the local vLLM endpoint is **live and OpenAI-compatible** at `http://192.168.5.178:8000/v1` serving model `deepseek-v4-flash-vision-exp` (vLLM 0.25.2, verified by direct probe). Second — and critically — this is a **reasoning model**: the request confirmed it emits chain-of-thought in a separate `reasoning` field and lands the final answer in `content`, and `content` is `null` with `finish_reason="length"` when `max_tokens` is too small (the model burns the budget reasoning). The provider adapter MUST set a generous `max_tokens` budget and must handle `content=None` (retry-on-truncation or fallback). vLLM accepts both `response_format={"type":"json_object"}` (validated to work) and `response_format={"type":"json_schema",...}` (accepted, but requires the larger token budget), so the structured-output approach is viable but the *operational* caveat is real and must be in the plan.

The remaining design is deliberately mechanical so the phase can be proven offline (AI-07/SC3). The provider abstracted behind an interface means tests inject a `FakeLLMProvider` (scripted responses / scripted timeouts) exactly as `FakeMT5Client` does today; the citation check is a value-vs-schema comparison; the agreement flag is a pure function of verdict + confidence; and the fallback path is a straightforward `try/except` around the provider call that emits the ML-only setup. No live endpoint is required for any unit test.

**Primary recommendation:** Use an abstract `LLMProvider` Protocol + `OpenAICompatProvider` (openai SDK, `base_url` → vLLM) + `FakeLLMProvider` for tests. Request JSON via `response_format={"type":"json_schema"}` with pydantic validation as the safety net, set a generous `max_tokens` (≥2048) to accommodate the reasoning model, and enforce the citation check + level-field guard as a **schema-level whitelist**, not prompt trust.
## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| LLM provider abstraction / API client | API / Backend (adapter) | — | The `LLMProvider` + `OpenAICompatProvider` lives in the pure backend tier; it owns the HTTP call and response parsing, never business logic. |
| Structured-output schema + validation | API / Backend (pure model) | — | Pydantic `LLMNarrative` schema is a pure contract; validates `verdict/confidence/reasoning/citations`. |
| Evidence serialization (evidence object dict) | API / Backend (pure) | — | Builds the evidence object from `Indicator/Scorer` outputs; pure function, MT5-free, no I/O. |
| Citation check + level-field guard | API / Backend (pure) | — | Schema-level value comparison against the evidence object; mechanical, deterministic. |
| Agreement flag (ML↔LLM) | API / Backend (pure) | — | Pure function of verdict + confidence vs ML P(WIN). |
| Graceful fallback / timeout / retry | API / Backend | — | `try/except` around the provider call; emits ML-only setup. |
| Config knobs (endpoint, model, timeout) | API / Backend (config) | — | Frozen `Config` dataclass extension with fail-fast validation. |
| Persisting the narrative artifact | Database / Storage | — | Atomic `tmp+os.replace` Parquet/JSON writer for per-setup narrative records (consumed by Phase 6). |
| Prompt construction | API / Backend (pure) | — | Tight prompt built ONLY from the evidence object (D-03); never injects OHLC or levels. |

No browser/frontend tier responsibilities exist in this phase — the dashboard (Phase 6) merely consumes the recorded narrative + agreement flag.

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `openai` | 3.8.0 | OpenAI-compatible client for the local vLLM endpoint (and any other OpenAI-compatible server) | Official OpenAI Python SDK; supports `base_url` for a custom/local endpoint and `response_format` structured output; uses the widely-adopted chat completions surface. `[VERIFIED: PyPI 2026-09-03]` |
| `pydantic` | 2.x (inherited/transitive) | Structured-output schema + validation of `LLMNarrative` | The openai SDK natively accepts a pydantic model as `response_format` and converts it to a strict JSON schema (`type_to_response_format_param`). `[CITED: openai-python _parsing/_completions.py]` |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `anthropic` (optional) | 1.3.0 | Anthropic provider (`client.beta.messages.create(..., output_config={"format":{"type":"json_schema","schema":...}})` or `.parse(...)`) | Only when wiring the second provider; interface abstracts it. `[VERIFIED: PyPI 2026-09-01]` |
| `respx` (optional, dev) | 0.23.1 | HTTP-level mocking of the openai client for offline tests | Only if you want to exercise the real `OpenAICompatProvider` request/response path without a live endpoint; the codebase's `FakeMT5Client` duck-typed pattern is preferred. `[VERIFIED: PyPI]` |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `openai` SDK | raw `httpx` + manual `POST /v1/chat/completions` | The SDK handles base_url, retries, timeouts, and pydantic-driven schema conversion; hand-rolling the HTTP + JSON body invites serialization bugs. Use the openai SDK. |
| pydantic model for `LLMNarrative` | plain `dict` + manual key checks | Pydantic gives strict validation + native JSON-schema conversion; manual dict checks are easy to get wrong (Pitfall: missing enum check on `verdict`). |
| `FakeLLMProvider` (duck-typed) for tests | `respx` / `httpx.MockTransport` | The duck-typed fake matches the existing `FakeMT5Client` convention and needs zero extra deps; respx only for exercising the real HTTP layer. |
| `json_object` response_format | `json_schema` response_format | `json_schema` (strict) structurally constrains the output shape so the citation check has a fixed contract; `json_object` only guarantees it is *some* valid JSON. Prefer `json_schema` with pydantic validation. |

**Installation:**
```bash
uv add "openai>=3.8.0"
# optional, only if wiring the second provider in v1:
# uv add "anthropic>=1.3.0"
# optional dev-only HTTP mocking (prefer FakeLLMProvider instead):
# uv add --dev "respx>=0.23.1"
```

**Version verification:** Verified against PyPI via the registry JSON API (not training data):
- `openai` → 3.8.0 (published 2026-09-03)
- `anthropic` → 1.3.0 (published 2026-09-01)
- `respx` → 0.23.1

> Note: the `openai` SDK's `OpenAI` client should be constructed once (or as a lazy singleton) and reused, not per-request; under vLLM keep `max_retries` low and rely on the phase's own timeout policy.
## Package Legitimacy Audit

> Gate protocol run against PyPI. All three packages point at **authoritative, official source repos** (openai-python by OpenAI, anthropic-sdk-python by Anthropic, respx by lundberg), but the seam cannot read pypistats weekly-download data in this environment, so the automated verdict is `SUS` on `too-new`/`unknown-downloads`. None has a suspicious `postinstall` script and none is a hallucinated/slopped name. Treat the `SUS` here as a **download-data false-positive on official SDKs**, not a supply-chain risk — but per the protocol the planner should add a `checkpoint:human-verify` watermark before each install.

| Package | Registry | Age | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----|-----------|-------------|---------|-------------|
| openai | PyPI | ~long-lived (3.8.0 published 2026-09-03) | n/a (unknown) | github.com/openai/openai-python | [SUS] | Flagged — planner adds `checkpoint:human-verify` (official SDK; low real risk) |
| anthropic | PyPI | ~long-lived (1.3.0 published 2026-09-01) | n/a (unknown) | github.com/anthropics/anthropic-sdk-python | [SUS] | Flagged — only if wired in v1 (optional/deferred) |
| respx | PyPI | mature (0.23.1) | n/a (unknown) | lundberg.github.io/respx | [SUS] | Flagged — optional dev-only HTTP mock (prefer FakeLLMProvider) |

**Packages removed due to [SLOP] verdict:** none.
**Packages flagged as suspicious [SUS]:** `openai` [WARNING: flagged as suspicious — verify before using.], `anthropic` [WARNING: flagged as suspicious — verify before using.], `respx` [WARNING: flagged as suspicious — verify before using.]

> All three are official, authoritative packages (`[CITED: official source repo]`). The `SUS` verdict is a data-availability artifact (weekly downloads unreadable here), not evidence of a slop/squat. Confidence in legitimacy: HIGH. The `checkpoint:human-verify` watermark is still added per protocol convention.

## Architecture Patterns

### System Architecture Diagram

```
                       Phase 5 — LLM Narrative Layer (pure backend tier, MT5-free)
 ┌────────────────────────────────────────────────────────────────────────────────┐
 │                                                                                │
 │  Phase 4 Scorer                       Phase 2/3 SMC evidence                   │
 │  ┌──────────────────────┐             ┌───────────────────────────┐            │
 │  │ Scorer.score()       │             │ CandidateState: zone_id,  │            │
 │  │   → calibrated P(WIN)│             │  event_id, pool_id, dir,  │            │
 │  │ Scorer.contributors()│             │  sl_price, tp_price,      │            │
 │  │   → raw pred_contrib │             │  bias_h1/h4               │            │
 │  │   (top-5 by |contrib|)│            └─────────────┬─────────────┘            │
 │  └──────────┬───────────┘                          │                           │
 │             └──────────────┬───────────────────────┘                           │
 │                            ▼                                                   │
 │  ┌──────────────────────────────────────────────┐                              │
 │  │  serialize_evidence()  → evidence object dict │  (point-in-time; never      │
 │  │  (symbol, dir, zone, sweep, bias, entry/SL/TP │   recomputes levels/feats)  │
 │  │   ref-only, P(WIN), top-5 contributors)       │                              │
 │  └──────────────────────┬───────────────────────┘                              │
 │                         ▼                                                       │
 │  ┌──────────────────────────────────────────────┐                              │
 │  │  build_prompt(evidence)  → system+user text   │  (D-03: ONLY evidence obj;  │
 │  │  + response_format json_schema for LLMNarrative│   NO OHLC, no level recompute)│
 │  └──────────────────────┬───────────────────────┘                              │
 │                         ▼                                                       │
 │  ┌──────────────────────────────────────────────┐      ┌──────────────────────┐ │
 │  │  LLMProvider.build_narrative(evidence, schema)│──────│ OpenAICompatProvider │ │
 │  │  (interface; injected for tests)              │      │  → openai SDK base_url│ │
 │  │                                              │      │  → local vLLM         │ │
 │  └───────────────┬──────────────────────────────┘      └──────────┬───────────┘ │
 │                  │                             …timeout / error…  │             │
 │                  ▼                                  ▼              ▼             │
 │   ┌────────────────────────────┐        ┌────────────────────┐                    │
 │   │ parse + pydantic validate  │        │  FALLBACK (AI-07)  │                    │
 │   │ LLMNarrative               │        │  emit ML-only setup │                 │
 │   └─────────────┬──────────────┘        └─────────┬──────────┘                    │
 │                 │                                  │                             │
 │                 ▼                                  ▼                             │
 │   ┌────────────────────────────┐        ┌────────────────────┐                    │
 │   │ citation_check(narrative,  │        │ narrative=None,    │                    │
 │   │  evidence) → verified/unver│        │ agreement=None,    │                    │
 │   │  (whitelist level fields → │        │ score_source='ml'  │                    │
 │   │   drop any level field)    │        └────────────────────┘                    │
 │   └─────────────┬──────────────┘                                                 │
 │                 ▼                                                                │
 │   ┌────────────────────────────┐                                                 │
 │   │ agreement_flag(verdict,    │  (AI-06: agree/disagree/unclear + confidence)   │
 │   │  confidence, p_win)        │                                                 │
 │   └─────────────┬──────────────┘                                                 │
 │                 ▼                                                                │
 │   ┌──────────────────────────────────────────────┐                               │
 │   │  atomic tmp+os.replace writer →              │                               │
 │   │  data/reports/llm_narratives.<parquet/json>  │  (consumed by Phase 6)        │
 │   └──────────────────────────────────────────────┘                               │
 │                                                                                 │
 └────────────────────────────────────────────────────────────────────────────────┘
```

**Trace the primary use case:** evidence serializer → prompt builder → provider call → parse/validate → citation check → agreement flag → atomic persist. The fallback branch (dashed right side) is the SC3 path: any provider timeout/error emits a complete ML-only setup (narrative/agreement absent, `score_source='ml'`).

### Recommended Project Structure
```
src/ai_trading/llm/
├── __init__.py          # public exports: LLMProvider, OpenAICompatProvider, build_narrative, agreement_flag
├── schema.py            # LLMNarrative pydantic model + JSON-schema builder + ALLOWED_CITATION_KEYS / FORBIDDEN (level) keys
├── provider.py          # LLMProvider Protocol + OpenAICompatProvider (+ optional AnthropicProvider stub)
├── evidence.py          # serialize_evidence(scorer_result, candidate_state, contributors, cfg) -> evidence dict (pure)
├── prompt.py            # build_prompt(evidence) -> sys/user messages (pure, D-03 no OHLC/levels bonus)
├── citations.py         # citation_check(narrative, evidence) -> verdict + drop-level guard (pure)
├── agreement.py         # agreement_flag(verdict, confidence, p_win, cfg) -> (agreement, confidence) (pure)
├── narrative.py         # run_narrative_pipeline(provider, evidence, cfg) -> NarrativeResult (orchestrates; try/except fallback)
└── writer.py            # atomic tmp+os.replace writer for narrative artifacts

tests/unit/
├── _llm_fixtures.py     # FakeLLMProvider (scripted responses/timeouts) + sample evidence builder
├── test_llm_schema.py
├── test_llm_provider.py        # OpenAICompatProvider param mapping (monkeypatched client, no network)
├── test_llm_evidence.py        # evidence serialization; no future info; top-5 contributor ranking
├── test_llm_prompt.py          # prompt contains only evidence; NO OHLC/level recompute
├── test_llm_citations.py       # citation check + level-field guard (D-02/SC1)
├── test_llm_agreement.py       # agreement flag (AI-06)
├── test_llm_fallback.py        # AI-07: fake provider timeout → ML-only setup
└── test_llm_writer.py          # atomic artifact write
tests/integration/
└── test_llm_live.py            # `llm`-marked opt-in live vLLM test (auto-excluded by default)
```

### Pattern 1: Provider Interface (duck-typed, mirroring `FakeMT5Client`)
**What:** A `Protocol` (or the established duck-typing convention) defining `build_narrative(evidence, response_schema) -> str` (returns raw JSON text), with a real `OpenAICompatProvider` and a test `FakeLLMProvider` implementing the same surface.
**When to use:** Always — this is what makes the AI-07 fallback provable offline and keeps `mt5`-free purity (the LLM provider is the only module touching the network, and it is fully behind the interface).
**Example (extracted from openai SDK docs + Codebase `FakeMT5Client` convention):**
```python
# src/ai_trading/llm/provider.py
from typing import Protocol, Any

class LLMProvider(Protocol):
    def build_narrative(self, evidence: dict, response_schema: dict, *, cfg) -> str: ...

class OpenAICompatProvider:
    """Wraps the openai SDK pointed at a local/OpenAI-compatible endpoint."""
    def __init__(self, cfg):
        from openai import OpenAI
        # base_url points at the local vLLM (verified live: http://192.168.5.178:8000/v1)
        self._client = OpenAI(api_key=cfg.llm_api_key, base_url=cfg.llm_base_url)
    def build_narrative(self, evidence, response_schema, *, cfg):
        resp = self._client.chat.completions.create(
            model=cfg.llm_model,
            messages=build_prompt(evidence),
            max_tokens=cfg.llm_max_tokens,       # generous: reasoning model burns budget
            response_format=response_schema,      # {"type":"json_schema","json_schema":{...}}
        )
        # REASONING-MODEL caveat: content may be None if tokens ran out during reasoning.
        content = resp.choices[0].message.content
        if content is None:
            raise LLMTruncatedError("no content (token budget consumed by reasoning)")
        return content
```
**Source:** `[CITED: openai-python _client.py / api.md]`; interface shape mirrors `tests/conftest.py` `FakeMT5Client` convention `[VERIFIED: codebase]`.

### Pattern 2: Structured Output Contract (pydantic → strict JSON schema)
**What:** Define `LLMNarrative` as a pydantic model; pass it to the openai SDK as `response_format` so the client converts it to a strict JSON schema, and validate the returned JSON against the same model.
**When to use:** Always — the pydantic model is the single source of truth for the contract (D-04), and it guarantees `verdict ∈ {confirm, refute}`, `confidence ∈ [0,1]`, `citations` is a list of known keys.
**Example (D-04 contract):**
```python
# src/ai_trading/llm/schema.py
from pydantic import BaseModel, Field
from typing import Literal, Annotated

class LLMNarrative(BaseModel):
    verdict: Literal["confirm", "refute"]            # D-04: never a soft third value here
    confidence: Annotated[float, Field(ge=0.0, le=1.0)]
    reasoning: str = Field(min_length=1)             # short evidence-grounded paragraph
    citations: list[str]                             # field keys from the evidence object

# Response format param the openai SDK accepts directly (it converts the model
# to a strict json_schema via type_to_response_format_param):
from openai.lib._parsing._completions import type_to_response_format_param
RESPONSE_SCHEMA = type_to_response_format_param(LLMNarrative)
```
**Source:** `[CITED: openai-python _parsing/_completions.py]`.

### Pattern 3: Schema-Level Guard + Citation Check (D-02 / D-05 / SC1)
**What:** Two independent mechanisms. (a) A **schema-level whitelist** of allowed top-level output fields and allowed citation keys — any field the LLM emits that is a price level (entry/sl/tp/recomputed level) is dropped, and (b) a **value-match check** that each cited key exists in the evidence object and the cited value matches the evidence value.
**When to use:** Always. This is the SC1 enforcement proof (the LLM never *originates* levels or probabilities — structurally, not by prompt trust).
**Example:**
```python
# src/ai_trading/llm/citations.py
FORBIDDEN_LEVEL_KEYS = {"entry", "sl", "tp", "sl_price", "tp_price", "entry_price", "take_profit", "stop_loss"}

def citation_check(narrative: LLMNarrative, evidence: dict) -> dict:
    """Return {status: 'verified'|'unverified', dropped: [...], mismatches: [...]}."""
    dropped = [k for k in set(narrative.citations) if k in FORBIDDEN_LEVEL_KEYS]
    unknown = [k for k in narrative.citations if k not in evidence]
    mismatch = [
        k for k in narrative.citations
        if k in evidence and str(evidence[k]) != str(narrative_cited_value)
    ]
    # Any unknown citation, any level-field citation, or any value mismatch ⇒ unverified.
    status = "verified" if not (dropped or unknown or mismatch) else "unverified"
    return {"status": status, "dropped": dropped, "unknown": unknown, "mismatch": mismatch}
```
Guaranteed invariant: `entry/sl/tp` and any recomputed-level field **cannot** survive because the whitelist drops them — provenance (the ML `p_win` + `score_source`) is never authored by the LLM either.

### Anti-Patterns to Avoid
- **Trusting prompt adherence for SC1:** The prompt saying "return only verdict/citations" is NOT the enforcement. D-02 mandates a schema-level guard; never rely on the LLM being well-behaved.
- **Ignoring the reasoning-model token budget:** This vLLM model emits a large `reasoning` field before `content`; if `max_tokens` is small you get `content=None` + `finish_reason="length"`. Always set a generous budget and treat `content=None` as a retry/fallback trigger, not a parse crash.
- **Recomputing R:R / levels inside the evidence serializer:** The narrative must consume `Scorer.contributors()` and `CandidateState` fields as-is; never recompute a decision-close R:R or re-derive SL/TP (that would hand the LLM-originates-levels problem to the pipeline itself).
- **Letting the citation check silently pass unknown keys:** D-05 mandates `unverified` + discard + count; a future key the model invents must be flagged, not ignored.
- **Serializing raw OHLC / candle series into the prompt:** D-03 forbids it; it also silently expands the surface the citation check must verify. Keep the prompt a tight evidence-object projection.
- **Per-call client construction:** Build the `OpenAI` client once (config-driven); don't construct it per setup (connection overhead and no reuse of connection pooling).
## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Calling the LLM API | raw `httpx`/requests + manual `POST /v1/chat/completions` | `openai` SDK with `base_url` | SDK handles base_url resolution (`OPENAI_BASE_URL` env), retries, timeouts, JSON-param building, and pydantic→schema conversion. Hand-rolled serialization is where `content=None` and schema bugs hide. |
| Structured output validation | manually check `verdict`/`confidence`/`citations` keys | pydantic `LLMNarrative` | Pydantic enforces the `Literal["confirm","refute"]` enum, `confidence∈[0,1]`, and required fields, and optionally drives the strict json_schema. Manual checks miss enum/facets. |
| JSON-schema conversion | hand-write the `response_format` JSON schema dict | pydantic model passed as `response_format` | The SDK's `type_to_response_format_param` builds `{"type":"json_schema","json_schema":{...strict:true}}` from the model — one source of truth, no drift. |
| Mocking the provider for tests | a network stub or real local calls in `unit` | `FakeLLMProvider` (duck-typed, matches `FakeMT5Client`) | Keeps the suite offline, deterministic, and dependency-free; the AI-07 fallback is provable without a running vLLM. |
| Retry/timeout policy | bespoke loop with no backoff semantics | `openai` SDK `timeout`/`max_retries` + the phase's own `try/except` fallback to ML-only | Rely on the SDK's transport-level timeout; the phase owns the *semantic* degradation (emit ML-only), not HTTP mechanics. |
| Feature-contributor ranking (`pred_contrib`) | re-derive SHAP values in the pipeline | `Scorer.contributors()` top-5 by `|contrib|` (excluding `bias`) | Phase 4 already computes raw-model TreeSHAP contributions deterministically; don't reimplement attribution. |

**Key insight:** The two things that make this phase degrade-proof are (1) a thin provider interface with a duck-typed fake, and (2) a pydantic + whitelist contract so malformed or over-reaching LLM output is *rejected mechanically*, never trusted. Reimplementing the HTTP client or the schema validation re-introduces exactly the failure modes (null content, hallucinated keys) the phase is designed to catch.

## Common Pitfalls

### Pitfall 1: Reasoning model returns `content=None` (token budget consumed by chain-of-thought)
**What goes wrong:** With a small `max_tokens`, the vLLM model emits a long `reasoning` field and finishes with `finish_reason="length"` and `content=null`; the pipeline then tries to parse `None` and crashes or silently drops the narrative.
**Why it happens:** This model (`deepseek-v4-flash-vision-exp`) is a reasoning model — its chain-of-thought is a separate field and competes for the same `max_tokens` budget as the final answer.
**How to avoid:** Set a generous `max_tokens` (≥2048 recommended) and treat `content is None` as a retry-once-then-fallback signal, never a hard crash. Optionally cap reasoning budget if the serving config exposes a reasoning knob.
**Warning signs:** `finish_reason == "length"`; `message.content is None` while `message.reasoning` is long; tests passing against a fake (which returns short content) but failing live.

### Pitfall 2: SC1 under-enforcement (the LLM "originates" a level despite the prompt)
**What goes wrong:** The LLM returns `entry=1.1234` or a recomputed R:R inside `reasoning`/`citations`. The narrative is stored and later rendered, silently suggesting a level the pipeline never computed — breaking the verifiable-trust core value.
**Why it happens:** Prompt-only prohibition is unreliable for generative models.
**How to avoid:** Enforce D-02 with a schema-level whitelist that **drops** any level field the LLM emits before it reaches the narrative record, and mark the narrative `unverified` + discard when a citation references a level/unknown key (D-05). Never persist what the guard rejected.
**Warning signs:** `reasoning` text containing numeric price literals; `citations` containing `entry`/`sl`/`tp`; a narrative record containing keys not in the evidence object.

### Pitfall 3: Evidence serialization leaks or recomputes post-decision information
**What goes wrong:** The serializer pulls post-decision columns (fill-based `rr`, `entry_price`, `exit_*`, `outcome`) from the label frame, or recomputes decision-close R:R with a different rule than Phase 4 — introducing lookahead or an inconsistent R:R.
**Why it happens:** `features.py` docstring explicitly lists these as FORBIDDEN inputs; the narrative consumes `CandidateState` + `Scorer` outputs and must not reach into the label frame.
**How to avoid:** Serialize only from the frozen `CandidateState` structural fields + `Scorer.score()`/`contributors()` outputs. Reuse `compute_rr`/the decision-close convention if an R:R is presented (it is framed reference-only per D-01 anyway). Keep the serializer pure and MT5-free; no new feature computation.
**Warning signs:** Evidence dict keys named `entry_price`/`exit_*`/`outcome`/`rr` that were not recomputed at the decision close.

### Pitfall 4: `json_schema` structured output unsupported/partial on some serving stacks
**What goes wrong:** The software advertises `response_format={"type":"json_schema"}` but a particular OpenAI-compatible server (older vLLM, proxies) rejects it or ignores `strict`.
**Why it happens:** Structured outputs (`json_schema` with `strict`) are a newer capability; `json_object` guided decoding is older and more widely supported on vLLM.
**How to avoid:** The live endpoint here accepts both (verified); keep pydantic validation as the authority so even a loosely-constrained `json_object` response is re-validated before acceptance. Gate the choice behind config (`llm_structured_mode: json_schema|json_object|none`).
**Warning signs:** HTTP 400 on `json_schema`; server logs about unsupported `response_format`; response parses as JSON but fails pydantic (bad enum/out-of-range confidence).

### Pitfall 5: Timeout fallback never exercised (tested only against a live endpoint)
**What goes wrong:** The graceful-degradation path (AI-07/SC3) is only gentle-tested against a running vLLM, so a production timeout or a down endpoint crashes or hangs the pipeline.
**Why it happens:** The fallback is a `try/except` around the provider call, and if tests never force that path the exception handling rots.
**How to avoid:** Add a `FakeLLMProvider` that scripts a timeout/`LLMError`, and assert the pipeline emits a complete ML-only setup (narrative/agreement absent, `score_source='ml'`) with a bounded wall-clock time. Keep the `llm` live test opt-in and auto-excluded.
**Warning signs:** No unit test forcing the exception path; live test marked `mt5`/`llm` is the only coverage.

## Code Examples

### Common Operation 1: Configure the OpenAI SDK for a local OpenAI-compatible endpoint
```python
# Source: [CITED: openai/openai-python _client.py — base_url resolution]
from openai import OpenAI

client = OpenAI(
    api_key=cfg.llm_api_key,          # may be a dummy key for local vLLM
    base_url=cfg.llm_base_url,        # e.g. "http://192.168.5.178:8000/v1"
    timeout=cfg.llm_timeout_ms / 1000,
    max_retries=1,
)
```
The client also honours `OPENAI_BASE_URL` env when `base_url` is omitted.

### Common Operation 2: Request structured JSON via `response_format` json_schema (pydantic-driven)
```python
# Source: [CITED: openai/openai-python _parsing/_completions.py]
from openai.lib._parsing._completions import type_to_response_format_param
from ai_trading.llm.schema import LLMNarrative

response_format = type_to_response_format_param(LLMNarrative)
# → {"type": "json_schema", "json_schema": {"schema": {...}, "name": "LLMNarrative", "strict": True}}

completion = client.chat.completions.create(
    model=cfg.llm_model,
    messages=build_prompt(evidence),
    response_format=response_format,
    max_tokens=cfg.llm_max_tokens,   # generous — reasoning model
)
content = completion.choices[0].message.content   # NOTE: may be None on truncation
```

### Common Operation 3: Anthropic structured output (optional, deferred)
```python
# Source: [CITED: anthropic-sdk-python MIGRATION.md / tools.md]
# client.beta.messages.create(..., output_config={"format": {"type": "json_schema",
#     "schema": LLMNarrative.model_json_schema()}})
# or the helper that builds the schema AND parses the result:
# client.beta.messages.parse(..., output_format=LLMNarrative)
```

### Common Operation 4: Fake provider for offline tests (mirrors `FakeMT5Client`)
```python
# tests/unit/_llm_fixtures.py
class FakeLLMProvider:
    """Test double for LLMProvider — scripted responses / scripted errors."""
    def __init__(self, responses=None, errors=None):
        self.responses = list(responses or [])   # FIFO of raw JSON strings
        self.errors = list(errors or [])         # FIFO of exceptions (e.g. TimeoutError)
        self.calls: list[tuple[dict, dict]] = []
    def build_narrative(self, evidence, response_schema, *, cfg):
        self.calls.append((evidence, response_schema))
        if self.errors:
            raise self.errors.pop(0)
        if not self.responses:
            raise AssertionError("no scripted response")
        return self.responses.pop(0)
```
The pipeline injects `FakeLLMProvider`; a scripted `TimeoutError` in `errors` proves the AI-07 ML-only fallback with no live endpoint.
## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Free-form text prompt + `temperature` for "narrative" | Structured `response_format={"type":"json_schema"}` + pydantic coercion | ~2024-2025 (structured outputs GA on OpenAI-compatible stacks) | Guarantees a parseable, enum-constrained JSON contract (D-04) instead of hoping for it. |
| Naive single request, no fallback | Provider abstraction + graceful ML-only degradation | This phase | AI-07/SC3: a slow/down endpoint never blocks setup emission. |
| Manual SHAP/attribution in the narrative path | Consume `Scorer.contributors()` (LightGBM `pred_contrib`) | Phase 4 (already shipped) | One deterministic attribution source; no reimplementation. |
| Anthropic-only / vendor-tied narrative code | OpenAI-compatible-first with an interface for Anthropic | This phase | One code path for local vLLM + any OpenAI-compatible endpoint; Anthropic optional behind the same interface. |

**Deprecated/outdated:**
- **`finetune-…`/classic chat models assumed to emit clean JSON:** reasoning models (this vLLM one included) interleave a `reasoning` channel; you must budget `max_tokens` for it and handle `content=None`. Treating the model as a plain JSON printer is the top live-path failure.
- **`response_format={"type":"json_object"}` as the only mechanism:** works but only guarantees *some* valid JSON; tighten with `json_schema` + pydantic for a fixed contract.

## Assumptions Log

> Claims tagged `[ASSUMED]` here are training-knowledge-only and need user confirmation before locking.

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | The local vLLM endpoint `http://192.168.5.178:8000/v1` is the intended phase-provided endpoint and should be the default `llm_base_url` in `config.local.toml` (the only reachable endpoint of the two found; `.171:8888` is offline and the opencode `boboLLM` model id does not match the served `deepseek-v4-flash-vision-exp`). | Environment Availability | Wrong endpoint/model ⇒ the live integration test fails; config default must be re-pointed. Values are verified live for `.178` but the *intent* to use it is assumed. |
| A2 | The phase should pin `openai` as a runtime dependency (not just dev). | Standard Stack | Not installing it breaks `OpenAICompatProvider` import at runtime; the phase needs it in `[project].dependencies`. |
| A3 | `content=None` handling should be "retry once, then fall back to ML-only" (rather than fall back immediately). | Graceful Fallback / Pitfall 1 | A one-shot retry may be unnecessary; but falling back immediately on a transient truncation is also valid. User preference; defaults are reasonable either way. |
| A4 | A separate `llm` pytest marker (excluded by default) is the intended way to gate the live-endpoint integration test, rather than reusing `mt5`. | Validation Architecture | Reusing `mt5` would conflate an MT5 terminal requirement with an LLM endpoint requirement; but either is acceptable. Default choice (new `llm` marker) assumed. |
| A5 | The top-5 contributors should be ranked by absolute raw `pred_contrib` value (excluding the trailing `bias` column), and null/`NaN` contributors (warmup rows) are dropped from the top-5 rather than zero-filled. | Evidence Serialization | If the user prefers signed-rank or zero-fill, the ranking/filter rule changes. Default assumed. |

## Open Questions (RESOLVED)

> All four open questions below are resolved by recommendations pinned in the plan actions (05-01 / 05-02) — see the planner-pinned semantics in the plan `<action>` bodies and the `llm_*` config knobs. Questions 1 (agreement flag), 2 (fallback policy), 3 (citation value matching), and 4 (config key placement) are each implemented per the recommendations here; no open ambiguity remains for the executor.

1. **Agreement flag semantics (AI-06 — agent's discretion).**
   - What we know: verdict is `confirm|refute` with `confidence∈[0,1]`; the ML headline is calibrated `p_win`; the phase must expose agree/disagree with confidence.
   - What's unclear: what counts as "disagree" — an opposite verdict against a high `p_win`, or any verdict opposite to the ML direction? Whether a 3-state `agree|disagree|unclear` (vs a binary) is used, and the confidence threshold.
   - **Recommendation:** 3-state `agree|disagree|unclear` derived from verdict + confidence + `p_win`: `agree` = verdict matches ML direction AND confidence ≥ `llm_agree_min_confidence` (e.g. 0.6); `disagree` = verdict opposes ML direction AND confidence above the same floor; `unclear` = confidence below the floor OR verdict is neutral-ambiguous. Expose the raw verdict + confidence alongside. Keep it a pure, config-thresholded function.

2. **Degradation/fallback policy (AI-07 — agent's discretion).**
   - What we know: on timeout/error the pipeline must emit a complete ML-only setup.
   - What's unclear: timeout threshold, number of retries, and whether the ML-only setup carries a note (e.g. `narrative_status="llm_unavailable"`) vs being fully silent.
   - **Recommendation:** `llm_timeout_ms` (default 8000), `llm_max_retries` (default 1), and emit a **note** (`narrative_status="llm_unavailable"`, `narrative=None`, `agreement=None`, `score_source="ml"`, `reason="timeout|error"`) — a visible, auditable record rather than total silence. A `reason` column makes the degradation testable and the dashboard able to show it.

3. **Citation value matching (D-05 strictness detail).**
   - What we know: citations must map to real evidence fields and values must match.
   - What's unclear: whether the LLM must *reproduce* the value (string compare) or only reference the key (the check verifies the key exists). D-05 says "values must match" — strict reproduction.
   - **Recommendation:** For scalar/none-numeric fields (zone state, direction, bias) require the LLM's quoted value to match the evidence value (string equality, normalised lower-case). For numeric fields (P(WIN), top-5 contribs) require a tolerance (`abs(diff) <= 0.02`) or a textual reference; recomputed numeric values never originate, so strict equality on numerics is not required — existence-in-evidence is what matters.

4. **Which LLM config keys belong in `config.toml` (committed) vs `config.local.toml`.**
   - What we know: `config.local.toml` (gitignored) wins key-by-key; committed `config.toml` must hold no secrets (ASVS V14).
   - What's unclear: `llm_api_key` is a credential → must live in `config.local.toml` only; endpoint/model may be committed as the public vLLM default.
   - **Recommendation:** Commit `llm_enabled=false`, `llm_base_url="http://192.168.5.178:8000/v1"`, `llm_model="deepseek-v4-flash-vision-exp"`, `llm_timeout_ms`, `llm_max_tokens`, `llm_top_n_contributors`, `llm_structured_mode` to `config.toml`; gate `llm_enabled` and put the (dummy) `llm_api_key` in `config.local.toml`.

## Environment Availability

> The phase depends on the local vLLM serving the model (for the live integration path only — every unit test is offline).

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Local vLLM endpoint `.178:8000/v1` | Live LLM integration test (opt-in) | ✓ | vLLM 0.25.2 (system_fingerprint); model `deepseek-v4-flash-vision-exp` | FakeLLMProvider for unit tests; vLLM-served model covers the live annotation |
| Local vLLM endpoint `.171:8888/v1` | (secondary endpoint found in opencode config) | ✗ | — | Not reachable; ignore for this phase |
| `openai` package | `OpenAICompatProvider` | ✗ (not installed) | 3.8.0 on PyPI | Add to `[project].dependencies` |
| Python | Runtime | ✓ | 3.12.12 (project venv via `uv`) | — |
| `uv` | Dep/run management | ✓ | 0.11.28 | — |
| pytest | Tests | ✓ (project) | 9.x | — |
| MT5 terminal | Not required this phase | n/a | — | Phase 5 is MT5-free |

**Missing dependencies with no fallback:** none — the only hard dependency is the `openai` SDK, which is installed via `uv add` (not a service). The live vLLM endpoint is used only by the opt-in `llm`-marked test; every unit test runs offline against the fake provider.

**Missing dependencies with fallback:** the live vLLM endpoint (`.178`) is only needed for the opt-in live test; the fallback is the `FakeLLMProvider` (proven offline). The `.171` endpoint is offline and not needed.
## Validation Architecture

> `workflow.nyquist_validation` is `true` in `.planning/config.json` — validation section is required.

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.x (via `uv`) |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` — existing markers `unit`/`mt5`, `addopts='-m "not mt5"'` |
| Quick run command | `uv run pytest -q` (unit-only default) |
| Full suite command | `uv run pytest -q -m "unit or mt5"` |
| LLM live test command | `uv run pytest -m llm -q` (opt-in, excluded by default) |

**Marker change required (Wave 0):** Add an `llm` marker to `pyproject.toml` and change `addopts` from `-m "not mt5"` to `-m "not mt5 and not llm"` so the live-endpoint integration test is excluded by default, keeping the suite offline-clean (the CONTEXT mandate: the LLM-provider path must be testable without a live endpoint). This is the only `pyproject.toml` change the phase needs.

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| AI-05 | Narrative confirms/refutes using ONLY the evidence object; never originates levels/probabilities (D-01/D-02/D-03) | unit | `uv run pytest tests/unit/test_llm_prompt.py::test_prompt_contains_only_evidence -q` and `tests/unit/test_llm_evidence.py::test_evidence_no_ohlc_no_recompute` | ❌ Wave 0 |
| AI-05 | Schema-level guard drops any level field (D-02); citation check flags+discards (D-05) | unit | `uv run pytest tests/unit/test_llm_citations.py::test_level_field_dropped` / `test_unknown_citation_unverified` / `test_value_mismatch_unverified` | ❌ Wave 0 |
| AI-05 | `verdict∈{confirm,refute}`, `confidence∈[0,1]`, citations validate against pydantic schema | unit | `uv run pytest tests/unit/test_llm_schema.py::test_verdict_enum_and_confidence_bounds` | ❌ Wave 0 |
| AI-05 | `OpenAICompatProvider` maps config → correct `chat.completions.create` params (base_url/model/response_format/max_tokens) | unit | `uv run pytest tests/unit/test_llm_provider.py::test_request_params_mapped` (monkeypatched client, no network) | ❌ Wave 0 |
| AI-06 | Agreement flag: verdict + confidence map to agree/disagree/unclear with confidence | unit | `uv run pytest tests/unit/test_llm_agreement.py::test_agree_disagree_unclear_three_state` | ❌ Wave 0 |
| AI-07 | Timeout/error → complete ML-only setup (narrative=None, agreement=None, score_source='ml', reason recorded) | unit | `uv run pytest tests/unit/test_llm_fallback.py::test_timeout_emits_ml_only_setup` (fake provider raises TimeoutError) | ❌ Wave 0 |
| AI-07 | Graceful fallback bounded in wall-clock (does not hang) | unit | `uv run pytest tests/unit/test_llm_fallback.py::test_fallback_bounded_time` | ❌ Wave 0 |
| AI-07 | Narrative artifact write is atomic (tmp+os.replace) | unit | `uv run pytest tests/unit/test_llm_writer.py::test_atomic_write` | ❌ Wave 0 |
| AI-05/06/07 | Live end-to-end against the real vLLM endpoint (opt-in) | integration (`llm` marker) | `uv run pytest -m llm tests/integration/test_llm_live.py -q` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest -q`
- **Per wave merge:** `uv run pytest -q -m "unit or mt5"`
- **Phase gate:** Full suite green (unit + mt5) before `/gsd-verify-work`; the opt-in `llm` live test run separately against the running vLLM.

### Wave 0 Gaps
- [ ] `pyproject.toml` — add `llm` marker and change `addopts` to `-m "not mt5 and not llm"` (and register the marker in the `markers` list)
- [ ] `uv add "openai>=3.8.0"` to `[project].dependencies`
- [ ] `tests/unit/_llm_fixtures.py` — `FakeLLMProvider` (scripted responses/timeouts) + `make_evidence` sample builder
- [ ] `tests/unit/test_llm_{schema,provider,evidence,prompt,citations,agreement,fallback,writer}.py` — the 8 new test modules (see map)
- [ ] `tests/integration/test_llm_live.py` — `llm`-marked opt-in live test (auto-excluded by default)

*(If no gaps: "None — existing test infrastructure covers all phase requirements." — not applicable; Wave 0 gaps are listed above.)*

## Security Domain

> `workflow.security_enforcement` is `true` (ASVS level 1). Required section.

### Applicable ASVS Categories
| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | LLM endpoints require no user auth in this tier (local vLLM); API key is a dummy for a local endpoint |
| V3 Session Management | no | Stateless per-request LLM calls; no sessions |
| V4 Access Control | no | No authorization surface in this phase (pure backend narrative) |
| V5 Input Validation | yes | pydantic `LLMNarrative` (strict enum, bounds, required fields) + citation whitelist/guard (D-02/D-05). Never trust raw LLM JSON — validate against the schema |
| V6 Cryptography | yes (minor) | `llm_api_key` is a secret → must live in gitignored `config.local.toml` (V14), never `config.toml`; the full `Config` is never repr'd (established config.py hygiene) |

### Known Threat Patterns for the LLM tier
| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| TLS/transport to a local endpoint | Spoofing | `base_url` points at the configured LAN vLLM; no manifests/remote URLs interpolated from untrusted input |
| LLM returns out-of-contract / hallucinated fields (levels, unknown citations) | Tampering | Schema-level whitelist drops level fields (D-02); citation check flags unknown/mismatch → `unverified` + discard (D-05). Never trust prompt adherence |
| Secret leakage in config | Information Disclosure | `llm_api_key` only in gitignored `config.local.toml`; committed `config.toml` holds no secrets (ASVS V14); `Config` never repr'd |
| Injection via evidence fields into the prompt | Tampering | Evidence values are serialized as data (not executable) into a tightly-scoped structured prompt; validate/pydantic-coerce before persist; the LLM cannot escape to real execution (narrative is record-only) |
| Prompt-injection forcing a fabricated verdict | Tampering | Citation check requires cited values match evidence; a verdict not grounded in matching cited evidence is marked `unverified` and discarded — so a low-confidence/hallucinated verdict cannot masquerade as verified |
| Down/timeout service disruption | DoS | `llm_timeout_ms` + `llm_max_retries` bound the call; AI-07 fallback emits ML-only setup, so a slow/down endpoint never blocks the pipeline |

## Sources

### Primary (HIGH confidence)
- [CITED: openai/openai-python] `_client.py` (base_url resolution, `OPENAI_BASE_URL` env, http_client), `_parsing/_completions.py` (`type_to_response_format_param` → strict json_schema), `api.md` (`POST /chat/completions`) — via Context7.
- [CITED: anthropics/anthropic-sdk-python] `MIGRATION.md` (`output_config` / `.parse(output_format=...)`), `tools.md` — via Context7 (optional provider).
- [VERIFIED: PyPI registry API] openai 3.8.0 (2026-09-03), anthropic 1.3.0 (2026-09-01), respx 0.23.1 — versions confirmed live.
- [VERIFIED: live probe] local vLLM at `http://192.168.5.178:8000/v1` (vLLM 0.25.2, model `deepseek-v4-flash-vision-exp`); `response_format={"type":"json_object"}` works; `json_schema` accepted; reasoning model — `content=None` + `finish_reason="length"` at small `max_tokens`.
- [VERIFIED: codebase] `src/ai_trading/ml/scorer.py` (`Scorer.score`/`contributors` via `pred_contrib`), `ml/features.py` (FEATURE_SPEC/_CATEGORICAL_CATEGORIES), `backtest/candidates.py` (`CandidateState` fields), `config.py` (frozen `Config` fail-fast pattern), `tests/conftest.py` (`FakeMT5Client` duck-typed pattern).

### Secondary (MEDIUM confidence)
- Phase 5 CONTEXT.md (D-01…D-05 locked decisions, canonical refs) — authoritative project decision record.
- Phase 4 VERIFICATION.md/SUMMARY.md, ml_scores.parquet schema, scorer/features — the evidence object's ML portion.

### Tertiary (LOW confidence)
- The exact mapping of "disagree" (opposite verdict vs probability gap) and the `content=None` retry-vs-fallback choice are functional recommendations (Assumptions A3) not yet confirmed by the user — resolve in planning.
- Native JSON-schema `response_format` code examples outside the openai/Anthropic docs are training-derived and not re-verified this session.

## Metadata

**Confidence breakdown:**
- Standard stack: **HIGH** — openai/anthropic versions verified on PyPI; API usage cited from official SDK docs; live vLLM endpoint probed.
- Architecture: **MEDIUM** — the provider-interface/citation/agreement design follows the codebase's established `FakeMT5Client` + pydantic + whitelist conventions (verified) but the exact agreement semantics and fallback policy remain user-discretion (Open Questions 1–2).
- Pitfalls: **MEDIUM** — the reasoning-model `content=None` and SC1 under-enforcement pitfalls are empirically verified; the structured-output portability caveat is partially verified.
- Domain: **MEDIUM** — LLM narrative on a reasoning model; the live-path materiality (token budget, null content) is verified but the phase's day-to-day narrative quality thresholds are not.

**Research date:** 2026-09-04
**Valid until:** 2026-10-04 (fast-moving LLM SDKs — re-verify `openai`/`anthropic` versions and the vLLM structured-output capability if the phase is planned after this window)

