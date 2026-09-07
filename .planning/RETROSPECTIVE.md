# Project Retrospective

*A living document updated after each milestone. Lessons feed forward into future planning.*

## Milestone: v1.0 — MVP (signals-only SMC trading system)

**Shipped:** 2026-09-07
**Phases:** 6 | **Plans:** 18 | **Tasks:** 58 | **Timeline:** 9 days (2026-08-29 → 2026-09-07)

### What Was Built

- MT5→UTC-normalized data foundation: health-checked collector, idempotent gap backfill, DST-validated broker offset, history to 2016 (M15)/1996 (H1/H4)
- Non-repainting SMC detection chain (swings→liquidity pools→sweeps→PD zones) with lifecycle state and point-in-time MTF context (Phase 2: 177-test suite, 30/30 must-haves)
- Shared-code-path backtester: identical pipeline replay, spread+slippage costs, triple-barrier labels, walk-forward harness (358-test suite)
- Calibrated LightGBM P(WIN) scorer with 18-feature point-in-time builder and mechanical 3-layer leak audit; versioned artifact bundles
- Evidence-grounded LLM narrative pipeline: strict citation check, 3-state ML↔LLM agreement, graceful ML-only fallback
- Streamlit dashboard (setup table, candlestick + SMC overlays, evidence trace, history, performance, health) + scheduled per-M15-close setup engine; first 4 live setups assembled and lifecycle-proven 2026-09-07

### What Worked

- Wave-blocked plan structure (Wave 1→2→3 with explicit "blocked on") kept execution linear and unblocked
- Offline-first testing: FakeMT5Client hooks, scripted fake LLM provider, fixture-config injection and tmp stores made every phase testable with zero MT5/LLM dependency
- Machine-checked invariants over prose rules: AST-pinned BT-01 shared code path, prefix-equivalence repaint suites, 3-layer leak audit, citation-check schema guard
- Human-verify at end-of-phase plus live phase-gate runs (real MT5 data) before declaring done
- Atomic write conventions (tmp+os.replace, dedup-on-key, byte-deterministic artifacts) established early in Phase 1 and reused by every later phase

### What Was Inefficient

- Subagent spawns repeatedly aborted in this runtime — research had to be redone inline (Init blocker, recurred)
- pandas 3 dtype instability surfaced late in Phase 2: three consecutive "[Rule 1 - Bug]" fix plans for empty-frame/path-dependent dtypes — a dtype-contract spike up front would have avoided the churn
- STATE.md velocity table stayed mostly manual/incomplete ("—" averages) — cost/time data was lost
- Phase 05 UAT status left stale at `testing` with 0 pending scenarios until milestone close audit caught it

### Patterns Established

- One shared, look-ahead-safe code path for live and backtest — enforced structurally, not by convention
- Honesty rules as code: never fabricate a model, labeled `llm_unavailable` fallbacks, `P(win) [score_source]` provenance chips, live-vs-backtest comparability captions
- Version gates at artifact boundaries (FEATURE_LIST_VERSION, config_hash) with determinism pinned at probability level, not bytes
- Pure DataFrame→DataFrame detector functions; all state persisted via Parquet + SQLite meta stores
- Dashboard as defensive pure reader (no MT5 probe; last-persisted health state only)

### Key Lessons

1. Broker-timezone/DST offsets need human confirmation plus an automated re-derivation guard, and re-validation at every DST transition (UTC+3→+2 due early November)
2. Pin ambiguous conventions (cost direction, PF ratio definition, TP liveness) as tests + docstring decisions at plan time — silent ambiguity becomes rework
3. Single-writer topology is law: the fixed-.tmp merge path raced under concurrency and hardening slipped to v2 — enforce guards, not assumptions
4. Live-evidence beats simulation for trust: the pending→expired lifecycle proven on real M15 closes was the strongest v1 verification moment
5. Keep phase UAT/verification status fields current — stale statuses pollute the close-time audit

### Cost Observations

- Model mix: adaptive profile (per config.json) — not tracked per-plan
- Plan durations ranged ~3 min to ~1h 50m (Phase 04 P01); median ~30 min
- Notable: verification-heavy phases (2, 3) ran longest but carried the highest test yield; dashboard phases were fast thanks to reusable stats/store layers

---

## Cross-Milestone Trends

### Process Evolution

| Milestone | Sessions | Phases | Key Change |
|-----------|----------|--------|------------|
| v1.0 | — | 6 | Full GSD chain established: discuss→plan→execute→verify→UAT per phase |

### Cumulative Quality

| Milestone | Tests | Coverage | Zero-Dep Additions |
|-----------|-------|----------|-------------------|
| v1.0 | 358+ (backtest suite; 177 at Phase 2) | pytest, incl. AST-pinned invariants | Offline testability of every phase (no MT5/LLM needed) |

### Top Lessons (Verified Across Milestones)

1. Establish write/atomicity conventions in the first phase — every later phase inherited them
2. Make the non-negotiable architectural rules mechanically checkable
