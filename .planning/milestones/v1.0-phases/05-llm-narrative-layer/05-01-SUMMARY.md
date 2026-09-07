---
phase: 05-llm-narrative-layer
plan: 01
subsystem: llm
tags: [openai, vllm, pydantic, structured-output, llm-provider, config]

# Dependency graph
requires:
  - phase: 04-ml-scoring
    provides: loadable Scorer (calibrated P(WIN)) + contributors, frozen Config with ml_* knobs, frozen dataclass Config pattern
provides:
  - The `ai_trading.llm` package (schema / provider / prompt) — the provider interface + D-04 structured-output contract that plan 05-02 (narrative pipeline) consumes.
  - Extended frozen Config with the 10 `llm_*` knobs (fail-fast).
  - Duck-typed `FakeLLMProvider` / `llm_cfg` / `make_evidence` offline fixtures.
affects: [phase 05-02 narrative pipeline, phase 06 setup assembly + dashboard]

# Tech tracking
tech-stack:
  added:
    - openai>=3.8.0 (official OpenAI SDK, OpenAI-compatible client for the local vLLM endpoint)
    - llm pytest marker (opt-in live-endpoint integration tests)
  patterns:
    - Adapter-tier isolation: the openai SDK is imported exactly once, in llm/provider.py (mirrors mt5_client.py).
    - Duck-typed provider double (FakeLLMProvider) mirroring FakeMT5Client for fully-offline AI-07 provable tests.
    - Pydantic model as single source of truth for the strict json_schema response_format (no drift).
    - Schema-level level-field guard (FORBIDDEN_LEVEL_KEYS) — never trust prompt adherence (SC1).

key-files:
  created:
    - src/ai_trading/llm/__init__.py
    - src/ai_trading/llm/schema.py
    - src/ai_trading/llm/provider.py
    - src/ai_trading/llm/prompt.py
    - tests/unit/_llm_fixtures.py
    - tests/unit/test_llm_schema.py
    - tests/unit/test_llm_provider.py
    - tests/unit/test_llm_prompt.py
  modified:
    - pyproject.toml
    - config.toml
    - config.local.toml (gitignored — llm_api_key)
    - src/ai_trading/config.py
    - uv.lock
    - tests/unit/test_backtest_config.py
    - tests/unit/test_normalize_and_config.py

key-decisions:
  - "Strips FORBIDDEN_LEVEL_KEYS from build_prompt's evidence projection: the prompt never contains price-level keys/values (D-02/D-03), consistent with the plan's test spec 'no level values'; the full evidence object remains available to the citation check in plan 05-02."
  - "build_prompt returns (system_messages, user_messages); the provider flattens them into the chat.completions.create messages list."
  - "The openai SDK is imported at module top in provider.py (not lazily) so the client is monkeypatch-able in offline tests and the 'only module imports the SDK' rule holds."
  - "llm_api_key lives only in gitignored config.local.toml (ASVS V14); committed config.toml carries public llm_* defaults only."

patterns-established:
  - "Provider interface (LLMProvider Protocol) + OpenAICompatProvider + FakeLLMProvider: the full LLM path is provable offline."
  - "Pydantic LLMNarrative drives the strict json_schema response_format and is the re-validation authority."
  - "Config._validate reuses the _is_int/_is_number discipline for llm_* fail-fast (bool-as-int rejected)."

requirements-completed: [AI-05]

# Coverage metadata (#1602)
coverage:
  - id: D1
    description: "openai>=3.8.0 dependency, llm pytest marker, and addopts='-m \"not mt5 and not llm\"' so the suite runs offline-clean"
    requirement: "AI-05"
    verification:
      - kind: unit
        ref: "uv add \"openai>=3.8.0\"; uv run python -c \"import openai; assert openai.__version__ >= '3.8.0'\" (exit 0)"
        status: pass
      - kind: unit
        ref: "uv run pytest -q -m \"not mt5 and not llm\" (464 passed, 1 skipped, 3 deselected)"
        status: pass
    human_judgment: false
  - id: D2
    description: "Frozen Config gains the 10 llm_* knobs with fail-fast validation; config.toml holds public defaults, gitignored config.local.toml holds llm_api_key"
    requirement: "AI-05"
    verification:
      - kind: unit
        ref: "tests/unit/test_backtest_config.py::test_load_config_carries_backtest_knobs; tests/unit/test_normalize_and_config.py::test_load_config_happy_path"
        status: pass
      - kind: other
        ref: "manual python probe: load_config rejects llm_structured_mode/timeout/max_tokens(<2048)/agree_min_confidence/top_n(<1) naming the field"
        status: pass
    human_judgment: false
  - id: D3
    description: "LLMNarrative validates verdict/confidence/reasoning/citations; FORBIDDEN_LEVEL_KEYS schema guard; strict json_schema response_format builder"
    requirement: "AI-05"
    verification:
      - kind: unit
        ref: "tests/unit/test_llm_schema.py (verdict enum, confidence bounds, non-empty reasoning, forbidden-level keys, strict json_schema)"
        status: pass
    human_judgment: false
  - id: D4
    description: "OpenAICompatProvider maps config to chat.completions params, raises LLMTruncatedError on content=None, builds the client once with base_url/timeout/max_retries"
    requirement: "AI-05"
    verification:
      - kind: unit
        ref: "tests/unit/test_llm_provider.py (client construction, request params, content=None -> LLMTruncatedError, response_format gating)"
        status: pass
    human_judgment: false
  - id: D5
    description: "build_prompt emits only the evidence-object projection — no OHLC/candle keys and no level values (D-03)"
    requirement: "AI-05"
    verification:
      - kind: unit
        ref: "tests/unit/test_llm_prompt.py (evidence fields present, no OHLC keys, level values stripped, only passed evidence used)"
        status: pass
    human_judgment: false
  - id: D6
    description: "Duck-typed FakeLLMProvider / llm_cfg / make_evidence fixtures available and deterministic for offline tests"
    requirement: "AI-05"
    verification:
      - kind: unit
        ref: "tests/unit/_llm_fixtures.py consumed by test_llm_provider.py and test_llm_prompt.py"
        status: pass
    human_judgment: false

# Metrics
duration: 16min
completed: 2026-09-04
status: complete
---

# Phase 5 Plan 01: LLM Narrative Layer — Provider Interface & Structured-Output Contract Summary

**OpenAI-compatible LLM provider interface (duck-typed `LLMProvider` + `OpenAICompatProvider` at the local vLLM) over a pydantic-validated `LLMNarrative` structured-output contract, a schema-level level-field guard, an evidence-only prompt builder, and extended `llm_*` config knobs — all provable offline via a `FakeLLMProvider`.**

## Performance

- **Duration:** 16 min
- **Started:** 2026-09-04T05:28:17Z
- **Completed:** 2026-09-04T05:44:xxZ
- **Tasks:** 3 (Task 1 package-legitimacy checkpoint — human-approved pre-run)
- **Files modified:** 14 (7 Task 2 scaffold + 8 Task 3 llm package/tests; `config.local.toml` also edited but gitignored)

## Accomplishments

- `openai>=3.8.0` installed as a runtime dependency; `llm` pytest marker registered; `addopts` changed to `-m "not mt5 and not llm"` so the live-endpoint path is opt-in and the default suite runs offline.
- Frozen `Config.gains` 10 `llm_*` knobs (`llm_enabled`, `llm_base_url`, `llm_model`, `llm_api_key`, `llm_timeout_ms`, `llm_max_tokens`, `llm_top_n_contributors`, `llm_structured_mode`, `llm_agree_min_confidence`, `llm_max_retries`) with fail-fast validation (structured_mode set, timeout positive, max_tokens>=2048 reasoning budget, top_n>=1, agree_confidence in [0,1]) in all four `ml_*`-analogous places.
- Config secret split per ASVS V14: `llm_api_key` only in gitignored `config.local.toml`; committed `config.toml` carries public defaults only.
- `ai_trading.llm` package: `LLMNarrative` pydantic contract (D-04), `FORBIDDEN_LEVEL_KEYS` D-02 schema guard, `ALLOWED_CITATION_KEYS`, and a strict `json_schema` response_format builder (single source of truth from the pydantic model).
- `OpenAICompatProvider` (the only module importing the openai SDK) constructs the client once from config and raises `LLMTruncatedError` on `content=None`; `response_format` gated behind `llm_structured_mode`.
- `build_prompt` emits only the evidence-object projection (no OHLC, no level values — D-03).
- Duck-typed `FakeLLMProvider` + `llm_cfg` + `make_evidence` fixtures; 15 offline unit tests across 3 modules; default suite stays green (464 passed, 1 skipped).

## Task Commits

Each task was committed atomically:

1. **Task 2: Wave 0 scaffold** — `cf88cd0` (feat)
2. **Task 3: LLM schema / provider / prompt + offline unit tests** — `868a42e` (feat)

**Task 1 (package-legitimacy checkpoint):** pre-execution `checkpoint:human-verify` for `uv add openai` — **APPROVED by the user before this run** (official OpenAI SDK, [SUS] is a download-data false-positive).

**Plan metadata:** committed in the final docs commit below.

## Files Created/Modified

Created:
- `src/ai_trading/llm/__init__.py` — bare package marker.
- `src/ai_trading/llm/schema.py` — `LLMNarrative`, `FORBIDDEN_LEVEL_KEYS`, `ALLOWED_CITATION_KEYS`, `narrative_response_format()`.
- `src/ai_trading/llm/provider.py` — `LLMProvider` Protocol, `OpenAICompatProvider`, `LLMProviderError`, `LLMTruncatedError`.
- `src/ai_trading/llm/prompt.py` — `build_prompt(evidence)` -> (system, user) messages.
- `tests/unit/_llm_fixtures.py` — `FakeLLMProvider`, `llm_cfg`, `make_evidence`.
- `tests/unit/test_llm_schema.py`, `test_llm_provider.py`, `test_llm_prompt.py` — 15 offline unit tests.

Modified:
- `pyproject.toml` — openai dep, `llm` marker, `addopts`.
- `src/ai_trading/config.py` — `llm_*` block in `_REQUIRED_KEYS`, Config fields, `_validate`, `load_config`.
- `config.toml` — public `llm_*` defaults (no secret).
- `config.local.toml` (gitignored) — `llm_api_key`.
- `uv.lock` — openai resolution.
- `tests/unit/test_backtest_config.py`, `test_normalize_and_config.py` — `_base_values` helper extended with `llm_*` required keys.

## Decisions Made

- **Stripped `FORBIDDEN_LEVEL_KEYS` from the prompt projection.** The plan's prompt spec explicitly asserts "no level values" in the prompt, while `make_evidence` carries reference-only level fields for the citation/schema tests. To satisfy both, `build_prompt` strips level fields from what it serializes (D-02/D-03), keeping the prompt a tight evidence projection; the full evidence object stays available to the citation check in plan 05-02. This is consistent with the plan's test spec.
- **`build_prompt` returns `(system, user)`; the provider flattens** into the `messages` list for `chat.completions.create` (a valid API messages array).
- **openai SDK imported at module top** in `provider.py` (not lazily) so the client is monkeypatch-able in offline tests and the adapter-tier single-import rule holds (mirrors `mt5_client.py`).
- **`llm_api_key` only in gitignored `config.local.toml`** (ASVS V14); committed `config.toml` carries public defaults. Config is never repr'd (existing discipline maintained).

## Deviations from Plan

None - plan executed exactly as written (all three tasks completed; Task 1 checkpoint was human-approved pre-run). Two implementation-interpretation decisions above are recorded under Decisions Made, not deviations (each satisfies the plan's written acceptance criteria).

## Issues Encountered

- Initial `test_llm_provider.py` fake client lacked a `.chat` namespace (provider accesses `self._client.chat.completions.create`) — restructured the fake to `_FakeChat`/`_FakeCompletions`. Fixed inline.
- `test_llm_prompt.py::test_prompt_has_no_ohlc_or_candle_keys` substring check falsely matched the legit `sweep_side: "low"` evidence value — rewritten to parse the JSON projection and assert on top-level keys. Fixed inline.
- Ruff flagged import ordering in the two new test modules and one >100-char line in `test_llm_schema.py` — auto-fixed (health gate passes).

## User Setup Required

None - no external service configuration required for this plan. `llm_api_key` is provided in gitignored `config.local.toml` for the local vLLM; the live endpoint is only used by the opt-in `llm`-marked integration test added later.

## Next Phase Readiness

- Plan 05-02 (narrative pipeline) can build on `LLMProvider` / `LLMNarrative` / `FORBIDDEN_LEVEL_KEYS` / `ALLOWED_CITATION_KEYS` / `build_prompt` and the `FakeLLMProvider`/`llm_cfg`/`make_evidence` fixtures to implement evidence serialization, the strict citation check, agreement flag, and graceful ML-only fallback.
- Additive config change: all prior-phase collector/backtest/ml_* behavior preserved; the existing two config test files still pass with the extended `_base_values`.

---
*Phase: 05-llm-narrative-layer*
*Completed: 2026-09-04*

## Self-Check: PASSED

- [x] All 8 llm package/test source files exist on disk.
- [x] SUMMARY.md exists at `.planning/phases/05-llm-narrative-layer/05-01-SUMMARY.md`.
- [x] Task commits verified in `git log`: `cf88cd0` (Task 2 scaffold), `868a42e` (Task 3 llm package + tests).
- [x] Full default suite green: `uv run pytest -q -m "not mt5 and not llm"` → **464 passed, 1 skipped, 3 deselected**.
- [x] `uv run python -c "import ai_trading.llm.schema, ai_trading.llm.provider, ai_trading.llm.prompt"` imports cleanly.
- [x] ruff health gate passes for all modified/new python files.
