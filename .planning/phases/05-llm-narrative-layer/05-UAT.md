---
status: testing
phase: 05-llm-narrative-layer
source: [05-VERIFICATION.md]
started: 2026-09-04T10:30:00Z
updated: 2026-09-04T10:30:00Z
---

## Current Test

number: 1
name: Live vLLM end-to-end narrative
expected: |
  Run the opt-in integration test against the local vLLM endpoint: uv run pytest -m llm tests/integration/test_llm_live.py -q (with llm_enabled=true and http://192.168.5.178:8000/v1 reachable). Expect a verified structured narrative (verdict + confidence + reasoning + citations) and an ML↔LLM agreement flag generated from the real vLLM reasoning model (deepseek-v4-flash-vision-exp). The reasoning-model content=None / max_tokens gotcha is already handled (LLMTruncatedError retry/fallback).
awaiting: user response

## Tests

### 1. Live vLLM end-to-end narrative
expected: Run `uv run pytest -m llm tests/integration/test_llm_live.py -q` with the local vLLM endpoint reachable. Expect a verified narrative + agreement flag from the real model. Core SC1/SC2/SC3 already proven offline — this is the sole real-model confirmation.
result: [pending]

## Summary

total: 1
passed: 0
issues: 0
pending: 1
skipped: 0
blocked: 0

## Gaps
