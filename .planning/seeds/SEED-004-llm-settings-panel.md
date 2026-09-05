---
id: SEED-004
status: done
planted: 2026-09-05
planted_during: v1.0 milestone, Phase 6 (setups-dashboard) — final UAT check pending
trigger_when: v1.0 milestone closes (first /gsd-new-milestone planning)
scope: medium
---

# SEED-004: LLM settings panel in the dashboard

> **DONE — pulled forward and implemented 2026-09-05** (commit 1e45406):
> `config_writer` validate-before-write atomic editor, `scheduler.refresh_cfg`
> per-pass reload, Health-tab panel with write-only key field + Test-connection
> probe (`probe_endpoint`), 11 new tests (suite 580). Design deviations: none
> material — option (a) hot-reload chosen as the seed recommended.

## Why This Matters

LLM endpoint/model drift is a real, observed failure mode: the LAN vLLM server
silently swapped models (deepseek → GLM, 2026-09-05), 404ing every narrative
call until config was hand-edited, and the endpoint moved again to MiniMax the
same day. The LLM knobs are config-file-only by design (ASVS V14), but the user
wants a runtime interface — edit from the dashboard, not from a file. A settings
panel with a built-in connection test turns endpoint drift from a debugging
session into a two-click fix.

## When to Surface

**Trigger:** the v1.0 milestone closes — surface during the first
`/gsd-new-milestone` planning session alongside SEED-001/002/003.

## Scope Estimate

**Medium** — one small phase. Design analysis from 2026-09-05:

1. **Write path** — the panel writes `config.local.toml` (machine-local,
   gitignored) via a new config-writer module: atomic tmp+os.replace write
   (same discipline as the stores), then re-validates through the existing
   fail-fast `load_config` before committing the file; validation errors
   render inline, file never left half-written.
2. **Secret handling** — API key field is **write-only**: never displays the
   stored key (shows "key set ✓" state), never echoes it in logs/reprs/errors;
   key persists only on disk in config.local.toml. Threat model is a localhost
   single-user Streamlit app, so a write-only field keeps the ASVS V14 stance
   intact (no secrets committed, none leaked).
3. **Reload semantics (the subtle one)** — the engine monitor and collector
   load config ONCE at startup (`main()`), so dashboard edits do not reach a
   running monitor. Either: (a) monitor loop re-loads config each pass and
   rebuilds the provider when the config hash changes, or (b) the panel shows
   an explicit "restart the monitor to apply" state. Decide via research; (a)
   is the better UX and matches the existing config_hash artifact pattern.
4. **Test connection button** — probes `GET /v1/models` (lists served model
   ids) + a minimal chat call, reports status/latency/served models; the
   model-id drift from 2026-09-05 would have been a two-click fix.
5. **Fields** — `llm_enabled` toggle, `llm_base_url`, `llm_model`, `llm_api_key`
   (write-only), `llm_timeout_ms`, `llm_structured_mode`, `llm_max_tokens`;
   plus the served-model picker fed by the /v1/models probe.
6. **UI-SPEC note** — this adds a new UI surface to a LOCKED v1 spec; either
   fold into SEED-003's UI-SPEC v2 or ship as a minimal settings section under
   the Health tab. Composes with SEED-003 (shared visual language).

## Breadcrumbs

- `src/ai_trading/config.py` — load_config / _validate (fail-fast contract the panel reuses)
- `config.local.toml` — the file the panel writes (gitignored)
- `src/ai_trading/llm/provider.py` — OpenAICompatProvider (client built once from cfg)
- `src/ai_trading/setup/scheduler.py` — monitor loop config load point (reload semantics)
- `src/ai_trading/stores/` — atomic tmp+os.replace write discipline to mirror
- `SEED-003` — dashboard modernization; shared UI-SPEC v2 visual language

## Notes

Planted 2026-09-05 after the user explicitly requested an interface for LLM
configuration following the endpoint-drift fixes. Smallest of the four seeds;
could be pulled forward as a /gsd-quick if the user wants it before the
milestone boundary — but it touches the locked UI-SPEC and engine reload
semantics, so milestone-route is the default.
