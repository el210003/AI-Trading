---
phase: 05-llm-narrative-layer
verified: 2026-09-04T18:30:00Z
status: human_needed
score: 10/10 must-haves verified
behavior_unverified: 0
overrides_applied: 0
human_verification:
  - test: "Run the opt-in live end-to-end narrative against the real OpenAI-compatible vLLM endpoint: `uv run pytest -m llm tests/integration/test_llm_live.py -q` with `llm_enabled=true` and the endpoint reachable in config.local.toml"
    expected: "test_live_narrative_produces_verified_result yields `result.narrative is not None`, `citation_status == 'verified'`, `score_source == 'ml_llm'`, `narrative_status == 'ok'`, `agreement` in {agree, disagree, unclear}"
    why_human: "Requires a running local vLLM endpoint (http://192.168.5.178:8000/v1). The phase is provable offline via FakeLLMProvider, so SC1/SC2/SC3 need no live endpoint; this is the only path that exercises the real model's output against the citation check and agreement flag and cannot be verified without infrastructure."
---

# Phase 05: LLM Narrative Layer Verification Report

**Phase Goal:** Evidence-grounded LLM confirm/refute reasoning as a separable, degradable component
**Verified:** 2026-09-04
**Status:** human_needed (all automated checks pass; one opt-in live-endpoint UAT item requires a running vLLM)
**Re-verification:** No — initial verification

## Goal Achievement

Goal-backward: the phase must deliver a separable, degradable LLM confirm/refute component (AI-05) that exposes an ML↔LLM agreement flag (AI-06) and degrades gracefully to ML-only setups (AI-07), while the LLM never originates levels or probabilities (SC1). Verified below against the actual source — not SUMMARY claims.

### Observable Truths

| # | Truth | Status | Evidence |
| --- | ----- | ------ | -------- |
| 1 | Provider builds a chat.completions request carrying model, messages, response_format (strict json_schema from LLMNarrative), and generous max_tokens; content=None → LLMTruncatedError not a crash | ✓ VERIFIED | `src/ai_trading/llm/provider.py` (client built once from cfg; response_format gated by llm_structured_mode; content=None raises LLMTruncatedError). `test_llm_provider.py` monkeypatches the client and asserts cfg→params mapping + content=None path (passes). |
| 2 | LLMNarrative validates verdict in {confirm,refute}, confidence in [0,1], reasoning non-empty, citations list of str; FORBIDDEN_LEVEL_KEYS names level fields | ✓ VERIFIED | `src/ai_trading/llm/schema.py` (pydantic Literal/Field bounds, FORBIDDEN_LEVEL_KEYS frozenset). `test_llm_schema.py` passes. |
| 3 | Config carries 10 llm_* knobs with fail-fast validation; llm_api_key only in gitignored config.local.toml, never repr'd | ✓ VERIFIED | `src/ai_trading/config.py` (_REQUIRED_KEYS, fields+defaults, _validate, load_config). `config.toml` has public defaults incl. no llm_api_key; `config.local.toml` holds `llm_api_key`. Prior config tests still pass. |
| 4 | Provider path fully testable offline via duck-typed FakeLLMProvider; default suite never touches a live endpoint | ✓ VERIFIED | `tests/unit/_llm_fixtures.py` FakeLLMProvider + llm_cfg + make_evidence. addopts `-m "not mt5 and not llm"`; live test marked `llm` and excluded. Full suite green offline (489 passed, 1 skipped). |
| 5 | Prompt built only from the evidence object's fields; no raw OHLC/candle series, no recomputed levels | ✓ VERIFIED | `src/ai_trading/llm/prompt.py` (_evidence_projection strips FORBIDDEN_LEVEL_KEYS; system+user messages). `test_llm_prompt.py` asserts no OHLC/level keys and only passed evidence used (passes). |
| 6 | serialize_evidence produces the D-01 evidence object (top-5 contributors ranked by |pred_contrib| excluding bias, nulls dropped, point-in-time, no recomputed levels/no OHLC) | ✓ VERIFIED | `src/ai_trading/llm/evidence.py` (whitelist build, _rank_contributors, _FORBIDDEN_DERIVED_FIELDS structural guard). `test_llm_evidence.py` (7 tests incl. top-5 ranking and no-recompute) passes. |
| 7 | citation_check marks verified only when every citation is a real, non-level evidence field with matching value; any unknown/level/mismatch → unverified (D-05/SC1) | ✓ VERIFIED | `src/ai_trading/llm/citations.py` (dropped/unknown/mismatch → verified). `test_llm_citations.py` (level dropped, unknown, mismatch, valid) passes. `test_llm_fallback.py::test_citation_unverified_discard` proves the discard path. |
| 8 | agreement_flag yields a 3-state agree/disagree/unclear + confidence thresholded on llm_agree_min_confidence, NA-safe (AI-06) | ✓ VERIFIED | `src/ai_trading/llm/agreement.py`. `test_llm_agreement.py` (three-state + NA p_win) passes. |
| 9 | run_narrative_pipeline with a provider timeout/error emits a complete ML-only result (narrative=None, agreement=None, score_source='ml', narrative_status='llm_unavailable') bounded in wall-clock (AI-07/SC3) | ✓ VERIFIED | `src/ai_trading/llm/narrative.py` (fallback policy, LLMTruncatedError retry-then-fallback, llm_enabled short-circuit). `test_llm_fallback.py::test_timeout_emits_ml_only_setup`, `test_fallback_bounded_time` (<2s), `test_truncated_then_fallback_after_retry`, `test_llm_disabled_short_circuits` all pass. |
| 10 | Narrative writer persists atomically via tmp+os.replace with invariant column validation; no partial/corrupt artifact | ✓ VERIFIED | `src/ai_trading/llm/writer.py` (tmp+os.replace, required/unknown column validation, tmp unlink on failure). `test_llm_writer.py` (atomic round-trip, failed-write no partial, missing/unknown column refusal) passes. |

**Score:** 10/10 truths verified (0 present-but-behavior-unverified)

### Required Artifacts

| Artifact | Expected | Status | Details |
| -------- | -------- | ------ | ------- |
| `src/ai_trading/llm/__init__.py` | package marker + Phase-6 exports | ✓ VERIFIED | exports run_narrative_pipeline, agreement_flag, NarrativeResult, LLMProvider, LLMNarrative; local-module convention preserved |
| `src/ai_trading/llm/schema.py` | LLMNarrative, FORBIDDEN_LEVEL_KEYS, ALLOWED_CITATION_KEYS, narrative_response_format | ✓ VERIFIED | substantive; openai import lazy (I/O-free at import) |
| `src/ai_trading/llm/provider.py` | LLMProvider Protocol, OpenAICompatProvider, LLMProviderError, LLMTruncatedError | ✓ VERIFIED | only module importing openai SDK |
| `src/ai_trading/llm/prompt.py` | build_prompt(evidence) -> (system, user) | ✓ VERIFIED | strips FORBIDDEN_LEVEL_KEYS (D-03) |
| `src/ai_trading/llm/evidence.py` | serialize_evidence | ✓ VERIFIED | pure point-in-time whitelist build |
| `src/ai_trading/llm/citations.py` | citation_check | ✓ VERIFIED | pure guard |
| `src/ai_trading/llm/agreement.py` | agreement_flag | ✓ VERIFIED | pure 3-state |
| `src/ai_trading/llm/narrative.py` | run_narrative_pipeline + NarrativeResult | ✓ VERIFIED | orchestrator + graceful fallback |
| `src/ai_trading/llm/writer.py` | write_narratives | ✓ VERIFIED | atomic parquet writer |
| `tests/unit/_llm_fixtures.py` | FakeLLMProvider, llm_cfg, make_evidence | ✓ VERIFIED | deterministic, no change needed in 05-02 |
| `tests/integration/test_llm_live.py` | opt-in `llm`-marked live test | ✓ VERIFIED | importable without endpoint; excluded by default addopts; requires live vLLM to actually run (see Human Verification) |

### Key Link Verification

| From | To | Via | Status | Details |
| ---- | -- | -- | ------ | ------- |
| schema.py | provider.py | response_format = narrative_response_format() derived from LLMNarrative; returned JSON re-validated via LLMNarrative.model_validate_json | ✓ WIRED | provider.py imports narrative_response_format; narrative.py re-validates; single source of truth |
| config.py | provider.py | llm_base_url/llm_api_key/llm_timeout_ms/llm_max_retries feed OpenAI client constructor; llm_max_tokens guards truncation | ✓ WIRED | provider.py __init__ uses all; max_tokens in create kwargs |
| provider.py | prompt.py | build_prompt returns message list the provider flattens into chat.completions.create | ✓ WIRED | provider.py imports build_prompt and flattens |
| evidence.py | schema.py | evidence keys align with ALLOWED_CITATION_KEYS (+ reference-only levels); citations validates against same key set | ✓ WIRED | evidence whitelist builds those keys; citations imports FORBIDDEN_LEVEL_KEYS |
| citations.py | schema.py | FORBIDDEN_LEVEL_KEYS is the citation check's D-02 guard | ✓ WIRED | citations.py imports it |
| narrative.py | agreement.py + writer.py | orchestrator computes agreement flag and persists fallback | ✓ WIRED | narrative.py imports agreement_flag; writer used by consumers (Phase 6) |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
| -------- | ------- | ------ | ------ |
| 40 LLM unit tests validate contract/provider/prompt/evidence/citations/agreement/fallback/writer | `uv run pytest -q` on the 8 test_llm_*.py modules | `40 passed in 0.92s` | ✓ PASS |
| SC1 citation check — level/unknown/mismatch each → unverified; valid → verified | test_llm_citations.py (in suite above) | 4 passed | ✓ PASS |
| SC3 graceful fallback — timeout → ML-only, bounded <2s, disabled short-circuit | test_llm_fallback.py (in suite above) | 6 passed | ✓ PASS |
| Full offline suite green | `uv run pytest -q -m "not mt5 and not llm" tests/unit` | `489 passed, 1 skipped` | ✓ PASS |

### Probe Execution

No phase-declared probes. The phase verification is by unit-test-based probes above; no `scripts/*/tests/probe-*.sh` declared in PLAN/SUMMARY.

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
| ----------- | ----------- | ----------- | ------ | -------- |
| AI-05 | 05-01, 05-02 | Each setup receives an LLM narrative that confirms or refutes using only the structured evidence object | ✓ SATISFIED | provider.py + schema.py + prompt.py + evidence.py + citations.py; all tested |
| AI-06 | 05-02 | Setups expose an ML↔LLM agreement flag (agree/disagree with confidence) | ✓ SATISFIED | agreement.py 3-state + test_llm_agreement.py |
| AI-07 | 05-02 | System degrades gracefully to ML-only setups when the LLM endpoint is unavailable or slow | ✓ SATISFIED | narrative.py fallback + test_llm_fallback.py (timeout/bounded/disabled proven) |

Requirement cross-reference complete: every ID declared in plan frontmatter (AI-05, AI-06, AI-07) is accounted for; no orphaned requirements in the phase. REQUIREMENTS.md marks AI-05/AI-06/AI-07 Complete and maps them to Phase 5.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
| ---- | ---- | ------- | -------- | ------ |
| — | — | No TBD/FIXME/XXX/TODO/HACK/PLACEHOLDER markers in any llm module | ℹ️ none | No unresolved debt markers; no stubs found |

No stub patterns detected: all source modules contain real logic, no `return null/{} / []` hollow implementations, no empty handlers, no hardcoded empty data flowing to output. The writer's atomic fallback uses a deterministic monkeypatched `os.replace` OSError (documented decision), and the prompt strips — rather than leaks — level fields (consistent with plan acceptance criteria, recorded as a decision, not a deviation).

### Human Verification Required

1. **Live vLLM end-to-end narrative (opt-in)** — `uv run pytest -m llm tests/integration/test_llm_live.py -q` with `llm_enabled=true` and the endpoint reachable.
   - Expected: `test_live_narrative_produces_verified_result` yields a verified narrative (`citation_status == 'verified'`) and a valid agreement flag from the real model.
   - Why human: requires a running local vLLM endpoint; cannot be verified offline. SC1/SC2/SC3 are already proven by the offline unit tests above, so this is the sole remaining UAT confirmation against the real model.

### Gaps Summary

No blocking gaps. All 10 must-have truths are verified against actual source, each backed by passing behavioral unit tests. All three success criteria (SC1 evidence-only LLM + never-originates-levels, SC2 agreement flag, SC3 graceful ML-only fallback proven by test) are satisfied by real, wired, tested code. The full offline suite is green (489 passed, 1 skipped).

The single outstanding item is the opt-in live-end-to-end narrative against the real vLLM endpoint — a human/infrastructure verification, not a gap in implementation. Because a human-verification item exists, the phase status is `human_needed` rather than `passed`; the phase implementation itself is complete and ready to feed Phase 6.

---

_Verified: 2026-09-04_
_Verifier: the agent (gsd-verifier)_
