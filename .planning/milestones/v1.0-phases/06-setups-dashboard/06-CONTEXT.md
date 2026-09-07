# Phase 6: Setups & Dashboard - Context

**Gathered:** 2026-09-04
**Status:** Ready for planning

<domain>
## Phase Boundary

The product surface: a scheduled setup-assembly engine that builds live SMC+ML+LLM setups after each M15 close, persists them with a full lifecycle (pending → active → TP/SL/expired/invalidated), plus a Streamlit dashboard presenting setups, evidence, history, stats, and data-health. Scope covers SETUP-01…SETUP-04 and DASH-01…DASH-06 only. The UI look/feel is **locked by 06-UI-SPEC.md** (palette, layout, charts, components) — do not re-open visual decisions. v1 is signals-only (no order execution).

</domain>

<decisions>
## Implementation Decisions

### Setup Emit vs Fill Model (the core lifecycle semantic)
- **D-01:** A D-01 candidate fires a **live SIGNAL** at the M15 decision close (entry/SL/TP shown). It stays **`pending`** until price actually **trades through the entry** (a limit trigger) on a later M15 bar → becomes **`active`**; if never triggered it expires. Fit for v1 signals-only: the user decides whether to take the trade. (Diverges from the backtest's next-open D-04 fill, by design.)
- **D-02:** An **active** (entry-triggered) setup resolves via **TP hit → `tp_hit`**, **SL hit → `sl_hit`**, else after the **96-bar (24h) time barrier → `expired`** (closed at that bar). Invalidated first if the structure/zone invalidates.
- **D-03:** The live **exit rules mirror the Phase 3 label rules exactly**: SL-first intrabar tie on every bar incl. the trigger bar (D-10), gapped-open-beyond-barrier fills at the open (D-11), 96-bar inclusive time barrier → `expired` (D-17). This makes live active-outcomes directly comparable to the backtest R/stats panel (WR/PF/expectancy align) — one shared set of exit rules, no drift.
- **D-04:** **Pending phase:** a configurable trigger window (default ~8 M15 bars) for price to reach the entry (limit). If the tapped zone/pool **invalidates** before the trigger (structure break / close beyond the zone far boundary) → **`invalidated`** immediately (no entry). Else **`expired`** at the end of the window if never triggered. Bounded, avoids stale signals.

### the agent's Discretion
- **Scheduled engine trigger** — polling a new M15 close + running assembly (MT5 is request/response, no streaming per REQUIREMENTS out-of-scope; the Phase 1/3 collector + runner poll patterns apply). Not discussed — research/planner decides (e.g. a scheduled run per M15 close, or a manual/CLI trigger mode, + the run-on-demand path).
- **Setup qualification + LLM timing** — whether all detector-passing candidates become setups or are filtered by a min ML P(WIN) threshold; whether the LLM narrative runs eagerly at assembly or on-demand when a setup is viewed. Not discussed — research/planner decides.
- **Dashboard refresh + health semantics** — manual Refresh CTA (per UI-SPEC) plus optional auto-refresh on new-bar detection; whether the health strip reads live MT5 status or last-persisted state. Not discussed — research/planner decides within the UI-SPEC refresh/health contract.
- Trigger-window default bar-count, exact trigger-condition check (entry touched by bar high/low vs close), and whether per-symbol vs global windows apply
- Where the setup store lives (SQLite/Parquet under data/) and the setup record schema beyond the pinned fields (SETUP-01/02)

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Locked scope + goals
- `.planning/ROADMAP.md` — Phase 6 goal, success criteria SC1–5, plan breakdown 06-01…06-03
- `.planning/REQUIREMENTS.md` — SETUP-01…04, DASH-01…06; AI-06 agreement flag; Out of Scope (no order execution, no streaming)
- `.planning/PROJECT.md` — core value (transparent, verifiable evidence), v1 signals-only, hybrid AI separation

### UI design contract (MUST read — locks the visual layer)
- `.planning/phases/06-setups-dashboard/06-UI-SPEC.md` — approved design contract: palette (dark `#0B0F17`/`#141A26`/accent `#00C7FF` + semantic bull/bear/warning), typography (4 sizes, weights 400/600), 8-pt spacing, layout (health strip + filter sidebar + 4 tabs), plotly chart specs (candlestick + entry/SL/TP + sweep/PD-zone overlays; cumulative-R equity), component inventory, copy/empty/error states. Planner MUST honor these.

### Phase 5 contracts (LLM narrative + agreement the dashboard renders)
- `.planning/phases/05-llm-narrative-layer/05-CONTEXT.md` — evidence object, verdict+confidence+citations, reference-only levels + schema guard, strict citation check, 3-state agreement flag (D-01..D-05)
- `.planning/phases/05-llm-narrative-layer/05-02-SUMMARY.md` — exported Phase-6 surface (`serialize_evidence`, `run_narrative_pipeline`, `write_narratives`)

### Phase 4 contracts (ML score + provenance the dashboard renders)
- `.planning/phases/04-ml-scoring/04-CONTEXT.md` — P(WIN), score_source (ml/ml_llm/heuristic), versioned artifact + loadable scorer, ml_scores.parquet/provenance
- `.planning/phases/04-ml-scoring/04-03-SUMMARY.md` — scorer + runner CLI the setup assembly calls

### Phase 3 contracts (entry candidates + labels (exit rules mirrored) + stats)
- `.planning/phases/03-backtesting-labeling/03-CONTEXT.md` — D-01..D-13 entry-candidate pure functions (the setup assembly reuses these), D-08/09 structural SL/TP, D-10/D-11/D-17 exit rules mirrored in D-03
- `.planning/phases/03-backtesting-labeling/03-*SUMMARY.md` — walk-forward harness, canonical stats (WR/PF/expectancy/R) the Performance panel shows
- `src/ai_trading/backtest/candidates.py` — CandidateState / candidate_at_bar (setup assembly imports these exact functions per D-03)

### Phase 2 / Phase 1 contracts
- `.planning/phases/02-smc-detection-engine/02-CONTEXT.md` — zone/pool/sweep fields + lifecycle + as-of rule the evidence trace cites
- `.planning/phases/01-data-foundation/01-RESEARCH.md` — MT5 time semantics, closed-bars invariant, collector/poll patterns (scheduled engine)
- `src/ai_trading/collector.py` + `stores/bar_store.py` — read_bars / polling / merge_and_write patterns the engine + health strip use

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `backtest/candidates.py` `candidate_at_bar` / `CandidateState` — the entry-candidate pure functions setup assembly reuses (D-03 spirit / Phase 6 reuses Phase 3's exact functions)
- `ml/scorer.py` `score()` — loadable calibrated P(WIN) + contributors for the setup's ML field
- `llm/` `run_narrative_pipeline` / `serialize_evidence` / `write_narratives` — the LLM narrative + agreement flag attached to a setup
- `bar_store.read_bars`, `collector.py` polling/checkpoint patterns — the health strip + scheduled engine data source
- Phase 1 `stores/meta_store.py` (checkpoints/history bounds) — health strip last-bar-time + MT5 status source
- `config.py` frozen Config pattern — extend with setup_*/schedule knobs (trigger window, threshold, refresh)

### Established Patterns
- Pure, MT5-free domain modules; the setup-assembly engine stays MT5-free (reads bars/store) and delegates live MT5 to the adapter tier
- Frozen Config + fail-fast validation; atomic tmp+os.replace writers for the setup store
- pytest `unit`/`mt5` markers; Streamlit app under a `streamlit`/`ui` opt-in test marker (runs offline); ruff line-length 100
- Point-in-time / as-of discipline everywhere (no future data into a setup at its decision bar)

### Integration Points
- **Scheduled engine → setup store** — assembled setups persisted with lifecycle; the dashboard reads the store (not live MT5)
- **Dashboard (Streamlit)** — reads the setup store + reports (canonical stats, ml_reliability, narrative) for the table/chart/history/health tabs
- **Score + narrative** — assembly calls the loader (scorer) + narrative pipeline per setup; `score_source` + agreement flag shown honestly (UI-SPEC)

</code_context>

<specifics>
## Specific Ideas

- The setup lifecycle: `pending → active (on limit trigger) → tp_hit | sl_hit | expired (time barrier) | invalidated (structure/zone broken)`. Distinct from the backtest label outcomes by design (D-01).
- The Performance panel should note the live vs backtest comparability (live = trigger-filtered subset per D-01/02/03).
- Health strip: last-bar time per (symbol,timeframe) feed + MT5 connection status + recent errors, sourced from the store/meta (per the UI-SPEC health tab).
- `score_source` is shown honestly per UI-SPEC (ml / ml_llm / heuristic) — the LLM flag + ML agreement gate must be surfaced transparently.

</specifics>

<deferred>
## Deferred Ideas

- **Order execution / auto-fill** — deferred to the next milestone (v1 signals-only per PROJECT.md); the signal→limit-trigger model leaves room for it later.
- **ENH-xx calibration / agreement reporting, alerts, MLTMF confluence badge** — v2 tracked in REQUIREMENTS (ENH-01..06), not this phase.
- **Active-phase vs backtest label divergence note** — D-01 chooses live limit-trigger (differs from backtest next-open fill); the comparability caveat is documented in the Performance panel.

</deferred>

---

*Phase: 6-Setups & Dashboard*
*Context gathered: 2026-09-04*
