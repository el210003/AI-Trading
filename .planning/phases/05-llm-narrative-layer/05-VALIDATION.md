---
phase: 5
slug: llm-narrative-layer
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-09-04
---

# Phase 5 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.x |
| **Config file** | pyproject.toml (`[tool.pytest.ini_options]`) |
| **Quick run command** | `uv run pytest -q -m "not mt5 and not llm" tests/unit` |
| **Full suite command** | `uv run pytest -m "not mt5 and not llm"` |
| **Estimated runtime** | ~60 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest -q -m "not mt5 and not llm" tests/unit`
- **After every plan wave:** Run `uv run pytest -m "not mt5 and not llm"`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 120 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 05-01-01 | 01 | 1 | AI-05 | — | Provider interface (openai SDK, base_url→vLLM), mockable FakeLLMProvider, no live endpoint in default suite | unit | `pytest tests/unit/test_ml_provider.py` | ⬜ W0 | ⬜ pending |
| 05-01-02 | 01 | 1 | AI-05 | — | Structured-output contract (pydantic LLMNarrative, response_format json_object, content=None retry/fallback) | unit | `pytest tests/unit/test_ml_contract.py` | ⬜ W0 | ⬜ pending |
| 05-01-03 | 01 | 1 | AI-05 | — | Schema-level guard drops any level field the LLM emits (D-02, never originate levels/prices) | unit | `pytest tests/unit/test_ml_schema_guard.py` | ⬜ W0 | ⬜ pending |
| 05-02-01 | 02 | 1 | AI-05 | — | Evidence serialization (scorer + SMC fields + top-5 contributors; point-in-time, no future data) | unit | `pytest tests/unit/test_ml_evidence.py` | ⬜ W0 | ⬜ pending |
| 05-02-02 | 02 | 1 | AI-06 | — | ML↔LLM agreement flag (verdict+confidence → agree/disagree with confidence) | unit | `pytest tests/unit/test_ml_agreement.py` | ⬜ W0 | ⬜ pending |
| 05-02-03 | 02 | 1 | AI-07 | — | Citation check (SC1) + graceful fallback to ML-only on timeout/disabled, proven offline | unit | `pytest tests/unit/test_ml_citation.py tests/unit/test_ml_fallback.py` | ⬜ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `uv add openai` — the only Wave-0 install (research-verified openai 3.8.0; anthropic/respx deferred/optional)
- [ ] Add `llm` pytest marker (live-endpoint integration tests opt-in; default suite stays offline)
- [ ] `tests/unit/test_ml_provider.py` — stubs for AI-05 provider
- [ ] `tests/unit/test_ml_contract.py` — stubs for AI-05 output contract
- [ ] `tests/unit/test_ml_schema_guard.py` — stubs for SC1/D-02
- [ ] `tests/unit/test_ml_evidence.py`, `test_ml_agreement.py`, `test_ml_citation.py`, `test_ml_fallback.py` — stubs for AI-05/06/07

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Live vLLM reasoning-model narrative | AI-05 | Requires the local vLLM endpoint running (reasoning model; content=None on small max_tokens) | Opt-in `llm`-marked integration test against http://192.168.5.178:8000/v1 |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 120s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
