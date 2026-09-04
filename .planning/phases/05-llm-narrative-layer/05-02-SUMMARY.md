---
phase: 05-llm-narrative-layer
plan: 02
subsystem: llm
tags: [llm, pydantic, evidence, citation-check, agreement, fallback, atomic-writer, offline]

# Dependency graph
requires:
  - phase: 05-01
    provides: LLMProvider interface, OpenAICompatProvider, LLMNarrative pydantic contract, FORBIDDEN_LEVEL_KEYS / ALLOWED_CITATION_KEYS, build_prompt, FakeLLMProvider / llm_cfg / make_evidence fixtures
  - phase: 04-ml-scoring
    provides: Scorer.score() (p_win/score_source/artifact_version) + Scorer.contributors() (raw pred_contrib) + CandidateState SMC fields
provides:
  - The AI-05/AI-06/AI-07 behaviour: `serialize_evidence` (D-01 evidence object), `citation_check` (D-02/D-05 strict guard), `agreement_flag` (AI-06 3-state), `run_narrative_pipeline` (AI-07 graceful ML-only fallback), `write_narratives` (atomic persistence).
  - Public exports for Phase 6: run_narrative_pipeline, agreement_flag, NarrativeResult, LLMProvider, LLMNarrative.
affects: [phase 06 setup assembly + dashboard (narrative + agreement flag render)]

# Tech tracking
tech-stack:
  added: []  # no new dependencies this plan (all reuse existing pandas/pydantic/openai from 05-01)
  patterns:
    - Evidence serializer: pure whitelsit-build from Scorer + CandidateState (never recompute levels, never emit post-decision/OHLC — Pitfall 3).
    - Citation check: refuse-and-name discipline (drop FORBIDDEN_LEVEL_KEYS, flag unknown, flag enum value contradiction).
    - Agreement flag: pure, NA-safe, config-thresholded 3-state (mirrors candidates.bias_agrees).
    - Orchestrator with graceful fallback: try/except around the provider, emits labeled ML-only state (never silence).
    - Atomic parquet writer: tmp + os.replace with required/unknown invariant validation (copied from reports.py).

key-files:
  created:
    - src/ai_trading/llm/evidence.py
    - src/ai_trading/llm/citations.py
    - src/ai_trading/llm/agreement.py
    - src/ai_trading/llm/narrative.py
    - src/ai_trading/llm/writer.py
    - tests/unit/test_llm_evidence.py
    - tests/unit/test_llm_citations.py
    - tests/unit/test_llm_agreement.py
    - tests/unit/test_llm_fallback.py
    - tests/unit/test_llm_writer.py
    - tests/integration/test_llm_live.py
  modified:
    - src/ai_trading/llm/__init__.py  # public re-exports added

key-decisions:
  - "citation_check value-match is contradiction-detection on the scalar enum fields (direction/zone_state/bias_h1/bias_h4/sweep_side): an unknown key or a level-field citation is a hard unverified; a real non-level field is verified unless the reasoning explicitly asserts a DIFFERENT allowed enum value than the evidence. Numeric fields (p_win/contributors) are existence-checked only (research OQ3)."
  - "run_narrative_pipeline returns a complete NarrativeResult on every path (never raises on provider failure/disable/unverified citation); the ML-only fallback is labeled (narrative_status=llm_unavailable, reason=timeout|error|llm_disabled), not silence (research OQ2)."
  - "tests/unit/_llm_fixtures.py needed NO change for Task 3: FakeLLMProvider already FIFO-scripts arbitrary exceptions (TimeoutError / LLMTruncatedError) and make_evidence is already well-formed (has p_win/artifact_version), so the scripted-timeout/truncation requirement was already satisfied."
  - "The failed-write test drives the atomic rollback via monkeypatched os.replace (OSError) rather than an unserializable value — a deterministic proof that a failed write leaves no partial artifact and no .tmp residue."

requirements-completed: [AI-05, AI-06, AI-07]

# Coverage metadata (#1602)
coverage:
  - id: D1
    description: "serialize_evidence assembles the D-01 evidence object (SMC context + reference-only levels + p_win + top-5 contributors ranked by |pred_contrib| excluding bias, nulls dropped)"
    requirement: "AI-05"
    verification:
      - kind: unit
        ref: "tests/unit/test_llm_evidence.py (7 tests: allowed keys + level fields, top-5 ranking/capping, no-ohlc-no-recompute, missing-field ValueErrors)"
        status: pass
    human_judgment: false
  - id: D2
    description: "citation_check enforces D-02/D-05/SC1 — any level-field/unknown/mismatch citation flags the narrative unverified"
    requirement: "AI-05"
    verification:
      - kind: unit
        ref: "tests/unit/test_llm_citations.py (level dropped, unknown unverified, value mismatch unverified, valid verified)"
        status: pass
    human_judgment: false
  - id: D3
    description: "agreement_flag yields the 3-state agree/disagree/unclear + confidence (AI-06), NA-safe, thresholded on llm_agree_min_confidence"
    requirement: "AI-06"
    verification:
      - kind: unit
        ref: "tests/unit/test_llm_agreement.py (agree/disagree/unclear three-state + NA p_win)"
        status: pass
    human_judgment: false
  - id: D4
    description: "run_narrative_pipeline emits complete ML-only setups on provider timeout/error/disable/unverified-citation, bounded in wall-clock (AI-07/SC3) — proven offline by a scripted fake provider"
    requirement: "AI-07"
    verification:
      - kind: unit
        ref: "tests/unit/test_llm_fallback.py (timeout ML-only, bounded time, truncated retry->success, truncated->fallback, citation-rejected, llm_disabled no-call)"
        status: pass
    human_judgment: false
  - id: D5
    description: "write_narratives persists atomically (tmp+os.replace) with required/unknown invariant column validation; no partial artifact"
    requirement: "AI-06"
    verification:
      - kind: unit
        ref: "tests/unit/test_llm_writer.py (atomic round-trip, failed-write no partial artifact, missing/unknown column refusal)"
        status: pass
    human_judgment: false
  - id: D6
    description: "opt-in `llm`-marked live vLLM integration test (importable without the endpoint; excluded by default)"
    verification:
      - kind: integration
        ref: "tests/integration/test_llm_live.py (requires a live OpenAI-compatible endpoint at llm_base_url)"
        status: unknown
    human_judgment: true
    rationale: "Requires a running local vLLM endpoint; excluded by default (``-m \"not mt5 and not llm\"``) and not exercised offline. Must be run against the live endpoint to confirm end-to-end verification."

# Metrics
duration: 16min
completed: 2026-09-04
status: complete
---

# Phase 5 Plan 02: LLM Narrative Layer — Evidence Serializer, Citation Check, Agreement Flag & Graceful ML-Only Fallback Summary

**The evidence-grounded narrative pipeline: `serialize_evidence` builds the D-01 evidence object (top-5 contributors ranked by |pred_contrib| excluding bias, point-in-time, no post-decision/OHLC leak), `citation_check` enforces the strict D-05/SC1 guard (level/unknown/mismatch ⇒ unverified + discard), `agreement_flag` yields the 3-state ML↔LLM agreement (AI-06), and `run_narrative_pipeline` degrades gracefully to complete ML-only setups on timeout/error/disable/unverified-citation (AI-07) — all proven offline against a scripted fake provider and persisted atomically.**

## Performance

- **Duration:** 16 min
- **Started:** 2026-09-04T05:59:14Z
- **Completed:** 2026-09-04T06:15:09Z
- **Tasks:** 3
- **Files modified:** 12 (11 created + `__init__.py` modified; `_llm_fixtures.py` unchanged — no extension needed)

## Accomplishments

- `serialize_evidence(scorer_result, candidate_state, contributor_frame, cfg) -> dict` — the D-01 evidence object: SMC context + reference-only structural levels + `p_win`/`score_source`/`artifact_version` provenance + `top_contributors` (top-5 by |raw pred_contrib|, bias excluded, null/NaN dropped not zero-filled). Whitelist build structurally excludes post-decision/fill-derived keys (`entry_price`/`exit_*`/`outcome`/`rr`) and any raw OHLC (D-03 / Pitfall 3); fail-fast guard names any missing required scorer/candidate field.
- `citation_check(narrative, evidence)` — strict D-02/D-05/SC1 guard. Any `FORBIDDEN_LEVEL_KEYS` citation (entry/sl/tp) is `dropped`; any key not in the evidence is `unknown`; any scalar enum field whose reasoning asserts a different value than the evidence is a `mismatch`. A single violation ⇒ `unverified` and the pipeline discards the narrative (counted, never kept). Numeric fields are existence-checked only (research OQ3).
- `agreement_flag(verdict, confidence, p_win, cfg)` — pure, NA-safe, config-thresholded 3-state `agree | disagree | unclear` (AI-06), with the raw confidence returned alongside so the agreement is a derived view and never hides raw values.
- `run_narrative_pipeline(provider, evidence, cfg) -> NarrativeResult` — orchestrates serialize → prompt → provider → pydantic-validate → citation_check → agreement_flag. On provider timeout/error/truncation (one retry on `LLMTruncatedError`) it emits a complete ML-only setup (`narrative=None`, `agreement=None`, `score_source="ml"`, `narrative_status="llm_unavailable"`, `reason="timeout"|"error"`), bounded in wall-clock; `llm_enabled=False` short-circuits ML-only with no provider call; an unverified citation discards (`narrative_status="citation_rejected"`). The success path carries the verified narrative + agreement flag with `score_source="ml_llm"`.
- `write_narratives(df, path)` — atomic parquet writer (tmp + os.replace, tmp unlinked on failure) with required/unknown invariant column validation, targeting `data/reports/llm_narratives.parquet` for Phase 6.
- `__init__.py` re-exports `run_narrative_pipeline`, `agreement_flag`, `NarrativeResult`, `LLMProvider`, `LLMNarrative` for Phase 6.
- 25 new offline unit tests; full default offline suite green (**489 passed, 1 skipped, 4 deselected**) — the `llm`-marked live test excluded by default.

## Task Commits

Each task was committed atomically:

1. **Task 1: Evidence serializer** — `df1d795` (feat)
2. **Task 2: Strict citation check + 3-state agreement flag** — `3ae6fd2` (feat)
3. **Task 3: Narrative orchestrator + atomic writer + exports** — `3f6590c` (feat)

## Files Created/Modified

Created:
- `src/ai_trading/llm/evidence.py` — `serialize_evidence` + fail-fast guards + top-5 contributor ranking.
- `src/ai_trading/llm/citations.py` — `citation_check` (dropped/unknown/mismatch → verified/unverified).
- `src/ai_trading/llm/agreement.py` — `agreement_flag` 3-state.
- `src/ai_trading/llm/narrative.py` — `run_narrative_pipeline` + `NarrativeResult`.
- `src/ai_trading/llm/writer.py` — `write_narratives` atomic parquet writer + `NARRATIVE_COLUMNS`.
- `tests/unit/test_llm_evidence.py` (7), `test_llm_citations.py` (4), `test_llm_agreement.py` (4), `test_llm_fallback.py` (6), `test_llm_writer.py` (4).
- `tests/integration/test_llm_live.py` — `llm`-marked opt-in live endpoint test.

Modified:
- `src/ai_trading/llm/__init__.py` — public exports added.

## Decisions Made

- **Citation value-match is contradiction-detection on enum fields.** The `LLMNarrative.citations` contract (05-01) carries only field keys (D-04), not values, so the check detects contradiction by scanning the `reasoning` for a different allowed enum value (word-boundary, normalized). Unknown/level citations remain a hard `unverified`; a real non-level field is verified unless its value is explicitly contradicted (research OQ3).
- **`run_narrative_pipeline` never raises on the provider path** — a complete `NarrativeResult` is returned on timeout/error/truncation/disable/unverified-citation. The ML-only fallback is labeled (`narrative_status="llm_unavailable"`, `reason="timeout"|"error"|"llm_disabled"`), never silence (research OQ2 / T-05-08).
- **`tests/unit/_llm_fixtures.py` needed no change.** `FakeLLMProvider` already FIFO-scripts arbitrary exceptions (`TimeoutError`/`LLMTruncatedError`) and `make_evidence` is already well-formed (has `p_win`/`artifact_version`), so the Task-3 "extend if needed" requirement was already satisfied and the fixture was left untouched (no needless churn).
- **The failed-write test uses a monkeypatched `os.replace` (`OSError`)** to deterministically drive the atomic rollback (no partial artifact + no `.tmp` residue), instead of relying on a serialization error that pandas/pyarrow may absorb into a valid write.

## Deviations from Plan

None - plan executed exactly as written. All 3 tasks completed per their `<action>` specs, `<acceptance_criteria>` verified green, and the two interpretation decisions above (enum value-match semantics, unchanged `_llm_fixtures`) are recorded under **Decisions Made** — each satisfies the plan's written acceptance criteria.

## Issues Encountered

- Initial `test_llm_fallback.py` runs returned `reason="llm_disabled"` because `llm_cfg()` defaults to `llm_enabled=False` (05-01 default). The provider-call tests now pass `llm_cfg(llm_enabled=True)` so the timeout/truncation/citation paths are actually exercised; the `llm_enabled=False` short-circuit is its own dedicated test.
- The first failed-write test used a dict-in-column value that pandas/pyarrow serialized successfully (write did not raise). Replaced with a deterministic monkeypatched-`os.replace` failure per the decision above.

## User Setup Required

None - no external service configuration required for this plan. The local vLLM endpoint is used only by the opt-in `llm`-marked live integration test (`uv run pytest -m llm tests/integration/test_llm_live.py -q` with `llm_enabled` set locally); every unit test runs offline against the fake provider.

## Next Phase Readiness

- **Phase 6 (setup assembly + dashboard)** can consume: `run_narrative_pipeline` / `agreement_flag` (AI-06) via the public `ai_trading.llm` exports, the D-01 evidence object from `serialize_evidence`, and the persisted narrative records in `data/reports/llm_narratives.parquet` (via `write_narratives`), which carry the ML↔LLM agreement flag + provenance for the DASH-03 evidence trace.
- The narrative workflow is fully provable offline (AI-07/SC3) with a complete ML-only setup on any provider failure/disable.
- **Deferred:** the specific mapping of `NarrativeResult` records into the Phase 6 setup record (and the dashboard field wiring) is Phase 6 scope. The live vLLM annotation is opt-in; verify against the running endpoint before Phase 6 UAT.

---

*Phase: 05-llm-narrative-layer*
*Completed: 2026-09-04*

## Self-Check: PASSED

- [x] All 11 new source/test files exist on disk (`evidence.py`, `citations.py`, `agreement.py`, `narrative.py`, `writer.py`, 5 test modules, `test_llm_live.py`); `__init__.py` exports verified via `import ai_trading.llm`.
- [x] Task commits verified in `git log`: `df1d795`, `3ae6fd2`, `3f6590c`.
- [x] Full offline default suite green: `uv run pytest -q -m "not mt5 and not llm"` → **489 passed, 1 skipped, 4 deselected** (the new `llm` test is deselected by default).
- [x] Target commands green: `uv run pytest -q tests/unit/test_llm_evidence.py` (7 passed), `test_llm_citations.py`+`test_llm_agreement.py` (8 passed), `test_llm_fallback.py`+`test_llm_writer.py` (10 passed).
- [x] ruff health gate passes for all modified/new python files.
- [x] `uv run python -c "import ai_trading.llm"` imports cleanly with the Phase-6 exports.
