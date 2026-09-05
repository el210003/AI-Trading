---
created: 2026-09-05T01:22:50.256Z
title: Fix LLM vLLM endpoint 404
area: llm
files:
  - config.toml:106-117
  - config.local.toml:25-28
  - src/ai_trading/llm/provider.py
---

## Problem

The local vLLM endpoint (`http://192.168.5.178:8000/v1`, model `deepseek-v4-flash-vision-exp`) returns **HTTP 404 Not Found** on `POST /v1/chat/completions` (observed 2026-09-05 ~08:57 during the Phase-6 backfill). The server is up but the chat-completions route 404s — likely the vLLM instance was restarted with a different app/model or a changed API surface.

Impact: every `run_narrative_pipeline` call degrades to the graceful ML-only fallback (`narrative_status=llm_unavailable`, `score_source=ml`), so no setup can attach a narrative or promote to `ml_llm` until this is fixed. Phase-5 validation had the endpoint live (verified ~2026-09-04), so this regressed within a day.

## Solution

1. Probe the endpoint: `GET /v1/models` to see what is served now; try a raw chat-completions POST with curl.
2. Update `llm_base_url` / `llm_model` in `config.toml` (+ key stays in `config.local.toml`) to match the live server.
3. Re-run `run_narrative_pipeline` on a fixture evidence object and confirm `narrative_status=ok`, structured verdict/citations parse, and `score_source` promotes to `ml_llm`.
4. If the server is misconfigured beyond a model rename, restart/redeploy vLLM with the chat-completions route enabled.
