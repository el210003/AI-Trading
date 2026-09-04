# Phase 6: Setups & Dashboard - Research

**Researched:** 2026-09-04
**Domain:** Scheduled setup-assembly engine + lifecycle monitor + Streamlit/plotly dashboard
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01 (Emit vs Fill):** A D-01 candidate fires a **live SIGNAL** at the M15 decision close (entry/SL/TP shown). It stays **`pending`** until price actually **trades through the entry** (a limit trigger) on a later M15 bar → becomes **`active`**; if never triggered it expires. Fit for v1 signals-only. (Diverges from the backtest's next-open D-04 fill, by design.)
- **D-02:** An **active** (entry-triggered) setup resolves via **TP hit → `tp_hit`**, **SL hit → `sl_hit`**, else after the **96-bar (24h) time barrier → `expired`**. Invalidated first if structure/zone invalidates.
- **D-03:** The live **exit rules mirror the Phase 3 label rules exactly**: SL-first intrabar tie on every bar incl. the trigger bar (D-10), gapped-open-beyond-barrier fills at the open (D-11), 96-bar inclusive time barrier → `expired` (D-17). One shared set of exit rules, no drift.
- **D-04:** **Pending phase:** a configurable trigger window (default ~8 M15 bars) for price to reach the entry (limit). If the tapped zone/pool **invalidates** before the trigger (structure break / close beyond the zone far boundary) → **`invalidated`** immediately. Else **`expired`** at the end of the window. Bounded, avoids stale signals.
- **UI look/feel is LOCKED by 06-UI-SPEC.md** (palette `#0B0F17`/`#141A26`/`#00C7FF` + semantic bull/bear/warning, 4 sizes / 2 weights, 8-pt spacing, layout health strip + filter sidebar + 4 tabs, plotly chart specs, component inventory, copy/empty/error states). Do NOT re-open visual decisions.
- v1 is **signals-only** (no order execution); order execution is the next milestone.

### the agent's Discretion
- **Scheduled engine trigger** — polling a new M15 close + running assembly (MT5 request/response, no streaming; Phase 1/3 collector + runner poll patterns apply). Research/planner decides (scheduled run per M15 close, manual/CLI trigger mode, + run-on-demand path).
- **Setup qualification + LLM timing** — whether all detector-passing candidates become setups or are filtered by a min ML P(WIN) threshold; whether the LLM narrative runs eagerly at assembly or on-demand when a setup is viewed.
- **Dashboard refresh + health semantics** — manual Refresh CTA (per UI-SPEC) plus optional auto-refresh on new-bar detection; whether the health strip reads live MT5 status or last-persisted state.
- Trigger-window default bar-count, exact trigger-condition check (entry touched by bar high/low vs close), and whether per-symbol vs global windows apply.
- Where the setup store lives (SQLite/Parquet under `data/`) and the setup record schema beyond the pinned fields (SETUP-01/02).

### Deferred Ideas (OUT OF SCOPE)
- **Order execution / auto-fill** — deferred to the next milestone (v1 signals-only per PROJECT.md); the signal→limit-trigger model leaves room for it later.
- **ENH-xx calibration / agreement reporting, alerts, MTF confluence badge** — v2 tracked in REQUIREMENTS (ENH-01..06), not this phase.
- **Active-phase vs backtest label divergence note** — D-01 chooses live limit-trigger (differs from backtest next-open fill); the comparability caveat is documented in the Performance panel.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| SETUP-01 | Setup record contains symbol, direction, entry, SL, TP, R:R ratio, and the reason each level was chosen | Setup-assembly engine builds the record from `candidate_at_bar` (`Candidate`: symbol/direction/sl_price/tp_price + pool_id/event_id/zone_id) → entry derived at assembly; RR via `compute_rr`; level rationale = structural origin of SL (D-08 swept pool + zone far boundary) and TP (D-09 nearest opposite pool/swing / zone far boundary) |
| SETUP-02 | Setup persists an evidence object (zone IDs, sweep events, MTF bias, ML score contributors) consumable by LLM and dashboard | `serialize_evidence(scorer_result, candidate_state, contributor_frame, cfg)` returns the D-01 evidence object (SMC context + reference-only levels + p_win/score_source/artifact_version + top-5 contributors); persisted verbatim on the setup record |
| SETUP-03 | Setup lifecycle is tracked (active → TP hit / SL hit / expired / invalidated) via bar-close monitoring | Lifecycle monitor reuses the `walk_barriers` resolver (D-10/D-11/D-17) for active setups; a new pending-resolution rule handles the D-01 limit-trigger + D-04 invalidation/expiry |
| SETUP-04 | Untriggered setups expire or invalidate per documented rules (N-bar window / structure break) | Pending-phase monitor evaluates, per new M15 bar, the trigger-window expiry and zone/structure invalidation (D-04) |
| DASH-01 | Setup table with filters (symbol, status, direction, min probability, date range) | `st.dataframe` + `column_config` (sortable/searchable), `st.multiselect`/`st.selectbox`/`st.slider`/`st.date_input` in the sidebar per UI-SPEC |
| DASH-02 | Candlestick chart with entry/SL/TP markers plus sweep and PD-zone annotations | `plotly graph_objects.Candlestick` + `add_shape` rect zones (`layer="below"`) + `add_hline` entry/SL/TP + `add_trace`/`Scatter` sweep `◇` markers |
| DASH-03 | Each setup detail view displays its full evidence trace (zones, sweeps, bias, ML contributors, LLM narrative) | `st.container(border=True)` ordered sub-sections rendered from the persisted evidence object + `NarrativeResult` (verdict/confidence/agreement/citations; `llm_unavailable` rendered as `⌀`) |
| DASH-04 | Setup history with lifecycle outcomes for every emitted signal | `st.dataframe` over closed setups sorted newest-first; outcome binding from the lifecycle status enum |
| DASH-05 | Performance stats (WR, PF, expectancy, equity curve in R) aggregate and per symbol | Reuse `stats.canonical_stats` / `stats_by_symbol_timeframe` over the resolved-setup trace; `plotly Scatter` cumulative-R line per symbol toggle |
| DASH-06 | Data/pipeline health strip (last bar time per feed, MT5 connection status, errors) | Last-bar time from `bar_store.read_bars` max `time_utc` per (symbol,timeframe); MT5 status + errors from persisted meta/history-report state; rendered as `st.status`/`st.metric` strip (56px) |
</phase_requirements>

## Summary

Phase 6 is the **product surface** of the SMC+ML+LLM pipeline: a scheduled, MT5-free setup-assembly engine that turns a fresh M15 close into a fully-evidenced trade setup, persistence with a run-to-resolution lifecycle, and a Streamlit+plotly dashboard that renders setups, chart overlays, evidence traces, history, performance stats, and a data-health strip. The single biggest architectural fact: **almost the entire assembly and lifecycle logic already exists as pure, MT5-free functions from Phases 2–5** — this phase is an *orchestration + persistence + presentation* layer, not a reimplementation. Reusing `candidate_at_bar` (D-03), `features_at_decision`/`build_feature_frame`, `load_scorer`/`Scorer.score()`+`contributors()`, `serialize_evidence`, `run_narrative_pipeline`, `walk_barriers`, and the `stats`/`walkforward` stats functions is mandatory per CONTEXT (one shared code path — BT-01).

The setup-assembly engine runs per M15 close by (1) reading closed bars via `bar_store.read_bars` (M15/H1/H4), (2) running `run_chain` to get M15/H1/H4 detector tiers, (3) building an as-of `CandidateState` at the last closed bar and calling `candidate_at_bar` → `Candidate`, (4) building the 18 `FEATURE_SPEC` features at the decision bar, (5) scoring via `load_scorer`, (6) `serialize_evidence`, (7) `run_narrative_pipeline`, and (8) persisting a setup record to a store under `data/setups/`. The lifecycle monitor then re-schedules per new M15 bar, evaluating pending setups (D-04 limit-trigger / invalidation / window expiry) and active setups (D-02/D-03 TP/SL/time-barrier — reusing `walk_barriers` the exact resolver).

**Primary recommendation:** Build a pure MT5-free `ai_trading.setup` package (assembly + lifecycle + store + CLI/`__main__`) plus an `ai_trading.dashboard` Streamlit app; **reuse the Phase 3/4/5 pure functions verbatim** rather than writing new rule logic; persist setups as a dedup-on-`setup_id` Parquet store under `data/setups/` with atomic rewrite (the repo's established store discipline); and test the dashboard logic via Streamlit `AppTest` (offline) plus pure unit tests on the data/serialization layer.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Setup assembly (candidate + features + score + narrative) | API / Backend (`ai_trading.setup`) | — (reuses Frontend-Agnostic pure funcs from Phases 3/4/5) | Rule is pure; runs in a scheduled engine process, MT5-free |
| Setup persistence (lifecycle store) | Database / Storage (`data/setups/`) | Backend | Point-in-time store the dashboard reads; atomic parquet rewrite |
| Lifecycle monitor (pending→active→exit) | API / Backend (`ai_trading.setup.lifecycle`) | — | Pure per-bar resolution over the stored bars; no MT5 |
| Scheduled engine trigger (M15 close poll) | API / Backend | OS scheduler / CLI | Polls a new closed bar, runs assembly + monitor per cycle |
| Setup table + filters (DASH-01) | Browser / Client (Streamlit) | Backend (store read) | Streamlit sidebar + dataframe widgets; reads the store |
| Candlestick chart + overlays (DASH-02) | Browser / Client (Streamlit+plotly) | — | Client-side plotly rendering from store + bar data |
| Evidence detail trace (DASH-03) | Browser / Client | Backend (evidence object) | Renders the persisted evidence + narrative record |
| History + performance stats (DASH-04/05) | Browser / Client | Backend (`ai_trading.backtest.stats`) | Display layer; stats computed by reused Phase 3 functions |
| Health strip (DASH-06) | Browser / Client | Backend (bar/meta store) | Last-bar time + MT5 status + errors read from stores |
| MT5 interaction (health check, collector) | API / Backend adapter (`ai_trading.mt5_client`) | — | Only via the existing adapter tier; engine/dashboard are MT5-free |
</phase_requirements>
## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| streamlit | `>=1.39` (latest 1.63.0) | Dashboard app shell, tabs, sidebar, dataframe, metric, status | Locked by UI-SPEC; native widgets required (no React/design system) |
| plotly | `>=5.23` (latest 7.0.0) | Candlestick, entry/SL/TP overlays, zone bands, equity curve | Locked by UI-SPEC for all charts via `st.plotly_chart` |
| pandas | `>=3.0,<4` (already in deps) | All data frames / store reads | Existing project dependency |
| pyarrow | `>=25.0.1` (already in deps) | Parquet store read/write (atomic tmp + os.replace) | Existing project dependency |

> **Version note:** the UI-SPEC pins `streamlit>=1.39` and `plotly>=5.23`; the current PyPI latest are **streamlit 1.63.0** and **plotly 7.0.0** (verified via `pip index versions`). Both floors are satisfied and `uv add` resolves to the latest by default. `plotly 7.0` is a major-version bump from the 5.23 floor — do NOT pin to a hard major; keep `>=5.23` so the resolved version is compatible with the `streamlit` version. Verify `import plotly; plotly.__version__` after install.

### Supporting (all existing project modules — reuse, do not re-add)
| Module | Purpose | When to Use |
|---------|---------|-------------|
| `ai_trading.backtest.candidates` (`candidate_at_bar`, `CandidateState`, `compute_rr`) | The entry-candidate pure functions the setup assembly imports (D-03) | Always — never reimplement the entry rule |
| `ai_trading.backtest.chain` (`run_chain`) | Runs the detector chain once per M15 close to get M15/H1/H4 tiers | Assembly data source |
| `ai_trading.ml.features` (`features_at_decision`, `build_feature_frame`) | Builds the 18 `FEATURE_SPEC` features at the decision bar | Pre-score feature vector |
| `ai_trading.ml.scorer` (`load_scorer`, `Scorer.score`, `Scorer.contributors`) | Loaded calibrated P(WIN) + raw contribution attribution | Setup ML field + evidence contributors |
| `ai_trading.llm` (`serialize_evidence`, `run_narrative_pipeline`, `NarrativeResult`, `agreement_flag`) | Evidence object + narrative + agreement flag (AI-05/06/07) | Evidence trace + fallback |
| `ai_trading.backtest.barriers` (`walk_barriers`) | Active-setup barrier resolution (D-10/D-11/D-17) | Lifecycle monitor exit rule — the exact resolver |
| `ai_trading.backtest.stats` (`canonical_stats`, `stats_by_symbol_timeframe`) | WR/PF/expectancy/R + per-symbol stats (DASH-05) | Performance panel |
| `ai_trading.stores.bar_store` (`read_bars`) | Closed-bar reads; last-bar-time for health strip | Assembly data + DASH-06 |
| `ai_trading.stores.meta_store` | SQLite meta (checkpoints / history bounds) | Health strip + engine bookkeeping |
| `ai_trading.config` (`Config`) | Frozen config pattern to extend with `setup_*`/schedule knobs | New config keys |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Parquet setup store under `data/setups/` | SQLite store | Parquet matches repo store discipline (dedup keep="last" + atomic rewrite) and is naturally dataframe-shaped for the dashboard; SQLite is better for high-frequency row updates but adds a second store type — recommend Parquet for v1 (setups are low-volume, rewritten whole-file per cycle) |
| `st.tabs` single-page app | `st.navigation`/multipage | UI-SPEC locks the single-page `st.tabs` + shared sidebar layout — no routing lib |
| `st.plotly_chart` + `add_shape` | `st.vega_lite_chart` / `altair` | Plotly is locked for candlestick + shape/gap overlays |
| Reuse `walk_barriers` for active setups | New live wave-comparison logic | Reuse guarantees D-03 (identical exit rules, no drift) |

**Installation:**
```bash
uv add "streamlit>=1.39" "plotly>=5.23"     # runtime deps (pyproject [project].dependencies)
```

**Version verification (run before planning finalizes):**
```bash
uv add "streamlit>=1.39" "plotly>=5.23"
uv run python -c "import streamlit, plotly; print(streamlit.__version__, plotly.__version__)"
```

## Package Legitimacy Audit

| Package | Registry | Age | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----|-----------|-------------|---------|-------------|
| streamlit | PyPI | mature (~9 yrs; published 2026-09-01 latest release) | n/a (null from seam) | streamlit.io | SUS (heuristic) | Approved — false positive |
| plotly | PyPI | mature (~13 yrs; published 2026-08-25) | n/a (null from seam) | plotly.com/python | SUS (heuristic) | Approved — false positive |

**Packages removed due to [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** streamlit, plotly — **both flagged solely on the `too-new`/`unknown-downloads` heuristics** (the legitimacy seam received null weekly-download data and a recent publish date). These are NOT slopsquats: they are the canonical, first-party Streamlit/Plotly packages whose **official documentation domains** (`streamlit.io`, `plotly.com`) are confirmed as the `repoUrl`, and whose APIs I verified via **Context7 authoritative docs** (High reputation). The flagged verdict is a heuristic false-positive from null download metadata. Given the protocol, the planner should still add a lightweight `checkpoint:human-verify` before install to confirm the resolved `streamlit`/`plotly` versions on this machine (Python 3.12), but no naming/supply-chain suspicion applies.

**Ecosystem cross-check:** both are PyPI packages (this is a Python project); `pip index versions streamlit` and `pip index versions plotly` both resolve, confirming the correct ecosystem (no npm/PyPI confusion).

## Architecture Patterns

### System Architecture Diagram

```
   ┌─────────────────────────────────────────────── M15 close trigger ─────────────────────────────────────────────┐
   │                                    (poll new closed bar per cycle)                                             │
   │                                                                                                               │
   ▼                                                                                                               ▼
┌──────────────┐      ┌─────────────────────────────────────┐        ┌───────────────────────────────────────────┐
│  STORES      │      │  SETUP ASSEMBLY (ai_trading.setup)  │        │  LIFECYCLE MONITOR                        │
│  data/bars/  │─────▶│ 1. read_bars M15/H1/H4              │        │  (per new M15 bar)                        │
│  *.parquet   │      │ 2. run_chain → M15 + HTF tiers      │       ─▶│  pending → active (limit trigger)         │
│  data/       │      │ 3. as-of CandidateState @ decision  │        │        │ invalidated (zone/struct break)   │
│    setups/   │◀─────│ 4. candidate_at_bar → Candidate     │        │        └ expired (window, D-04)         │
│    reports/  │      │ 5. features_at_decision → 18 feats  │        │  active  → tp_hit / sl_hit (walk_barriers)│
└──────────────┘      │ 6. load_scorer.score/contributors   │        │          └ expired (96-bar, D-17)        │
   ▲     ▲     ▲      │ 7. serialize_evidence (SETUP-02)    │        └──────────────┬────────────────────────────┘
   │     │     │      │ 8. run_narrative_pipeline (AI-05/07)│                       │ writes lifecycle updates
   │     │     │      └───────────────┬─────────────────────┘                       │
   │     │     │                      └──────────────▶ SETUP STORE (data/setups/setups.parquet)◀───┘
   │     │     │                                            ▲  (dedup on setup_id, atomic rewrite)
   │     │     │                                            │
   │     │     └────────────────────────────────────────────┘
   │     │        (setup_id → evidence object, p_win/score_source, narrative/agreement, lifecycle status)
   │     ▼
┌───────────────────────────────────────────────────────────────────────────────────────────────────────┐
│  STREAMLIT DASHBOARD (ai_trading.dashboard)   —  st.tabs single page + shared sidebar + sticky health strip │
│  [Setups]  table(filters) → selected row → candlestick chart (entry/SL/TP + sweep ◇ + PD zones) + evidence │
│  [History] lifecycle outcomes            [Performance] WR/PF/expectancy + cumulative-R curve (per symbol)  │
│  [Health]  last-bar time per feed · MT5 status · recent errors                                            │
└───────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

**Entry point:** the scheduled engine (CLI/`__main__`, or the Phase 6 scheduler) triggers on a fresh M15 close. **Processing stages:** bars→chain→candidate→features→score→evidence→narrative→persist→lifecycle-update. **Decision points:** candidate gate (D-01/D-02), min-P(WIN) filter (discretion), entry derivation, pending→active on limit trigger, per-bar lifecycle resolution. **External dependencies:** the store layer (`data/`) only — no MT5 in the engine or dashboard; MT5 connectivity lives in the collector/adapter tier and is surfaced only as last-persisted state in the health strip.

### Recommended Project Structure
```
src/ai_trading/
├── setup/                     # NEW — MT5-free setup surface
│   ├── __init__.py            # public exports (assemble_setup, resolve_pending, resolve_active, ...)
│   ├── assembly.py            # assemble_setup(cfg, symbol, ...) → SetupRecord  (candidate+features+score+evidence+narrative)
│   ├── lifecycle.py           # resolve_pending(...)/resolve_active(...) per-bar sequence reusing walk_barriers
│   ├── store.py               # SetupRecord schema, read_setups/upsert_setups (Parquet, dedup setup_id, atomic rewrite)
│   ├── scheduler.py           # poll-new-M15-close loop + run-on-demand path (reuses seconds_until_next_close)
│   └── __main__.py            # `python -m ai_trading.setup [--once|--monitor]`
├── dashboard/                 # NEW — Streamlit app
│   ├── app.py                 # st.set_page_config + health strip + st.tabs + shared sidebar; entry point
│   ├── data_layer.py          # read setup store + bars + reports + meta into frames (the testable surface)
│   ├── charts.py              # plotly candlestick + overlays (entry/SL/TP, sweep ◇, PD zones) + equity curve
│   ├── views_setups.py        # setup table + filters + evidence trace (DASH-01/02/03)
│   ├── views_history.py       # history table (DASH-04)
│   ├── views_performance.py   # KPI cards + per-symbol breakdown + equity curve (DASH-05)
│   ├── views_health.py        # health strip (DASH-06)
│   └── theme.py               # the locked palette constants (single source; plotly colors + streamlit theming)
└── .streamlit/                # NEW (repo root or project)
    └── config.toml            # [theme] dark + primaryColor #00C7FF + server/browser per UI-SPEC
data/
└── setups/                    # NEW — runtime setup store
    └── setups.parquet         # dedup on setup_id, atomic rewrite
tests/
├── unit/
│   ├── test_setup_assembly.py # mock chain/features/score/llm → record assembly, evidence object, no leaks
│   ├── test_setup_lifecycle.py# pending→active/tp/sl/expired/invalidated state machine
│   ├── test_setup_store.py    # read/upsert round-trip, dedup, atomic write, empty-frame contract
│   └── test_dashboard_data.py # data_layer/serialization (filters, stats, health aggregation) — pure
└── ui/
    └── test_dashboard_app.py  # streamlit.testing.v1 AppTest smoke (labels the app renders, no exception)
```

### Pattern 1: Setup Assembly — reuse Phase 3/4/5 pure functions verbatim
**What:** Per M15 close, assemble one fully-evidenced setup by calling the *existing* pure functions — no reimputed rule logic.
**When to use:** The core of plan 06-01; mandated by D-03 / BT-01 (one shared code path).
**Example:**
```python
# src/ai_trading/setup/assembly.py (illustrative — signatures match Phase 3/4/5 exports)
from ai_trading.backtest.chain import run_chain
from ai_trading.backtest.candidates import CandidateState, candidate_at_bar, compute_rr
from ai_trading.backtest.asof import STAMP_BAR, STAMP_CLOSE, close_time_of, visible_mask
from ai_trading.ml.features import features_at_decision
from ai_trading.ml.scorer import load_scorer
from ai_trading.llm import serialize_evidence, run_narrative_pipeline

def assemble_setup(cfg, symbol, m15, h1, h4, scorer, llm_provider):
    chain = run_chain(m15, h1, h4)                      # reuse detector exports (BT-01)
    bar_t = m15["time_utc"].iloc[-1]; close_t = close_time_of(bar_t, "M15")
    state = CandidateState(                             # as-of slices at the decision bar
        m15_bars=m15,                                   # prefix up to & including decision bar
        events15=chain["events15"][visible_mask(chain["events15"], "resolved_at", STAMP_BAR, bar_t, close_t)],
        zones15=chain["zones15"][visible_mask(chain["zones15"], "mitigated_at", STAMP_BAR, bar_t, close_t)],
        pools15=chain["pools15"][visible_mask(chain["pools15"], "activated_at", STAMP_CLOSE, bar_t, close_t)],
        swings15=chain["swings15"][visible_mask(chain["swings15"], "confirmed_at", STAMP_CLOSE, bar_t, close_t)],
        payload_row=chain["payload"][chain["payload"]["time_utc"]==bar_t].iloc[0]
                    if len(chain["payload"][chain["payload"]["time_utc"]==bar_t]) else None,
    )
    cand = candidate_at_bar(state, cfg)                 # Phase 3 rule reused verbatim
    if cand is None:
        return None
    entry = _derive_entry(cand, state, m15)             # DISCRETION — see Open Question / Assumption A3
    rr = compute_rr(cand.direction, entry, cand.sl_price, cand.tp_price)
    synth_label = {**vars(cand), "entry": entry, "rr_at_decision": rr, "zone_id": cand.zone_id}
    feats = features_at_decision(state, synth_label, cfg)   # 18 FEATURE_SPEC features
    score = scorer.score(pd.DataFrame([feats])).iloc[0]      # p_win / score_source="ml" / artifact_version
    contrib = scorer.contributors(pd.DataFrame([feats]))
    evidence = serialize_evidence(score, {**synth_label, "entry": entry, "sl": cand.sl_price,
                                          "tp": cand.tp_price, "rr_at_decision": rr}, contrib, cfg)
    narrative = run_narrative_pipeline(llm_provider, evidence, cfg)   # NarrativeResult (AI-07 fallback)
    return build_setup_record(cand, entry, rr, feats, score, evidence, narrative)
```
**Key points:** `features_at_decision` needs a label-like row supplying `direction/sl_price/tp_price/zone_id/event_id/symbol/timeframe` plus the decision close from `state.m15_bars`; the scorer `score()` reindexes to `FEATURE_NAMES` and restores categorical dtypes (unseen categories → missing, LightGBM-native). `serialize_evidence` requires `entry/sl/tp/rr_at_decision` in the candidate dict and emits the D-01 evidence object whose whitelist build structurally forbids post-decision/fill-derived fields.

### Pattern 2: Lifecycle Monitor — pending trigger + shared active-exit resolver
**What:** Maintain per-setup status as new M15 bars close; reuse `walk_barriers` for active exits.
**When to use:** Plan 06-01 lifecycle; D-01/D-02/D-03/D-04.
**Example:**
```python
# src/ai_trading/setup/lifecycle.py (illustrative)
from ai_trading.backtest.barriers import walk_barriers

def resolve_pending(setup, bars, cfg):
    """D-04: check limit trigger (entry traded through), zone/structure invalidation, window expiry."""
    window = bars[bars["time_utc"] > setup["created_at"]].head(cfg.setup_trigger_window)
    if _zone_invalidated(setup, bars):                       # structure/zone break
        return "invalidated"
    if _entry_touched(setup, window):                        # limit trigger fired
        return "active"
    return "expired" if len(window) >= cfg.setup_trigger_window else "pending"

def resolve_active(setup, bars, cfg):
    """D-02/D-03: TP/SL/96-bar time barrier — reuse the exact resolver so live R matches backtest R."""
    position = build_position(setup, entry_open=setup["entry"], entry_idx=_trigger_idx(setup, bars))
    result = walk_barriers(position, bars, cfg)              # D-10 SL-first, D-11 gap=open, D-17 barrier
    return {**result, "next_status": "tp_hit" if result["outcome"]=="WIN"
            else "sl_hit" if result["outcome"]=="LOSS" else "expired"}
```
**Key point:** the entry (`setup["entry"]`) serves as the structural risk basis (`entry_open`) so a clean SL/loss yields `r ≈ -1` and the live R units match the backtest. `walk_barriers` computes `r_gross/r_raw/r_net` over the D-16 cost model — for v1 signals-only the `r_net` cost terms (spread/slippage) are estimates, so rely on `r_gross` (structural) for the performance panel and note the comparability caveat.

### Pattern 3: Dashboard — Streamlit single page + shared sidebar + sticky health strip
**What:** `st.set_page_config(layout="wide")` + `st.tabs` (Setups/History/Performance/Health) with shared sidebar filters and a health strip rendered on every tab.
**When to use:** Plan 06-02/06-03; the UI-SPEC locks layout/components/copy exactly.
**Example:**
```python
# src/ai_trading/dashboard/app.py
import streamlit as st
st.set_page_config(layout="wide", page_title="SMC Setups")
from ai_trading.dashboard import views_health, views_setups, views_history, views_performance

filters = views_setups.sidebar_filters()   # symbol/status/direction/min-prob/date + Reset + Refresh (st.rerun)
views_health.render_health_strip()          # sticky 56px strip on every tab
tab_s, tab_h, tab_p, tab_sv = st.tabs(["Setups", "History", "Performance", "Health"])
with tab_s: views_setups.render(filters)    # table (DASH-01) + chart + evidence (DASH-02/03)
with tab_h: views_history.render(filters)   # DASH-04
with tab_p: views_performance.render()      # DASH-05
with tab_sv: views_health.render_detail()   # DASH-06
```
**Refresh model (UI-SPEC):** no `@st.cache_data` on the *refresh* path — the Refresh button and a health-strip "Refresh" re-query the stores via `st.rerun()`. Use `@st.cache_data(ttl=…)` only on expensive immutable historical artifacts (bars, labels, canonical stats). Robustness: a missing/empty store renders the Empty state (`st.info`) on the affected view only; other tabs stay functional.

### Pattern 4: Plotly candlestick + overlays (DASH-02)
**What:** `go.Candlestick` with `add_shape` rects (PD zones, `layer="below"`, semi-transparent), `add_hline` entry/SL/TP, and a `go.Scatter` `◇` marker for the sweep.
**When to use:** The chart in plan 06-02; the UI-SPEC chart spec (height 520px, margin `l=8 r=8 t=24 b=8`, `hovermode="x unified"`).
```python
fig = go.Figure(data=[go.Candlestick(x=bars["time_utc"], open=bars["open"], high=bars["high"],
                                     low=bars["low"], close=bars["close"],
                                     increasing_line_color="#26A69A", decreasing_line_color="#EF5350")])
for _, z in zones.iterrows():                      # PD-zone bands drawn below candles
    fig.add_shape(type="rect", xref="x", yref="y", x0=z.created_at, x1=now,
                  y0=z["range_low"], y1=z["range_high"], layer="below",
                  fillcolor="#00C7FF", opacity=0.14, line=dict(width=0))
fig.add_hline(y=entry, line_color="#00C7FF", annotation_text="Entry")   # accent entry line
fig.add_hline(y=sl, line_color="#EF5350", annotation_text="SL")
fig.add_hline(y=tp, line_color="#26A69A", annotation_text="TP")
fig.add_trace(go.Scatter(x=[sw.pierced_at], y=[sw.level], mode="markers",
                         marker=dict(symbol="diamond", size=10, color="#00C7FF"), name="Sweep"))
fig.update_layout(height=520, margin=dict(l=8, r=8, t=24, b=8), hovermode="x unified")
st.plotly_chart(fig, config={"displayModeBar": True})
```

### Anti-Patterns to Avoid
- **Re-implementing candidate / barrier / stats logic in `setup/`:** violates D-03 / BT-01 and guarantees drift. Always import `candidate_at_bar`, `walk_barriers`, `canonical_stats`.
- **Reading future bars into a setup:** any as-of slice must go through `visible_mask` with the exact per-tier anchors (events `resolved_at` bar-time, zones `mitigated_at` bar-time, pools `activated_at` close-time, swings `confirmed_at` close-time). The assembly and monitor are point-in-time by construction — a setup at bar T must never see bar T+1.
- **Hardcoding the entry price:** the entry is a *derived* value the assembly must supply (since `Candidate` carries no entry price). Do not leave it as the backtest next-open unless deliberately chosen; document the D-01 limit-trigger derivation (see Open Question / A3).
- **Caching the refresh path:** caching live setup store reads makes the dashboard stale and defeats the manual-Refresh contract in UI-SPEC. Cache only immutable historical artifacts with a `ttl`.
- **Letting an exception blank the whole app:** a missing/empty setup store or bars store must render the Empty/Error state (`st.info`/`st.warning`) for the affected view, not crash the page. Wrap store reads defensively.
- **Ignoring the `score_source` honesty rule:** `p_win` must always render beside its `score_source` tag (ml/ml_llm/heuristic); `heuristic` renders in the warning hue. Never present a heuristic score as model-calibrated.
- **Adding `setup_*` keys to `_REQUIRED_KEYS` without updating `config.toml`:** `load_config` raises on any missing required key. Add the new keys to `Config`, `_REQUIRED_KEYS`, `_validate`, `config.toml`, AND `tests/conftest._make_cfg` defaults together.
## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Entry-candidate rule (sweep+zone+HTF+bias+SL/TP) | A new live rule | `candidate_at_bar` / `CandidateState` (Phase 3) | D-03 / BT-01: one shared rule; a parallel definition drifts |
| Exit/triple-barrier resolution (SL-first, gap, 96-bar) | A new wave-comparison loop | `walk_barriers` (Phase 3) | D-03: identical D-10/D-11/D-17 semantics; keeps live R comparable to backtest R |
| Feature assembly + ML scoring | New feature math or raw model calls | `features_at_decision` + `load_scorer`/`Scorer.score`/`contributors` (Phase 4) | Point-in-time feature spec; calibrated p_win + provenance; contributors for evidence |
| Evidence object construction | Hand-built evidence dict | `serialize_evidence` (Phase 5) | Whitelist build structurally forbids post-decision/fill leakage; reference-only levels |
| LLM narrative + agreement + fallback | New provider orchestration | `run_narrative_pipeline` / `agreement_flag` (Phase 5) | AI-05/06/07 graceful ML-only fallback, labeled provenance, citation guard |
| WR/PF/expectancy/R stats | Recompute stat math | `canonical_stats` / `stats_by_symbol_timeframe` (Phase 3) | Pinned A4/A5/D-16 conventions (TIMEOUT exclusion, raw/net variants) |
| Bar storage & atomic writes | New Parquet writer | `bar_store.read_bars` + `merge_and_write` discipline | Repo store pattern; tmp+os.replace atomic, dedup keep="last" |
| Config load/validation | New config system | Frozen `Config` dataclass + `_validate` | Fail-fast, frozen, pattern-of-record |
| SQLite meta (checkpoints/history) | New bookkeeping store | `meta_store` | Health strip + engine resume state |

**Key insight:** nearly every numerical rule this phase needs already exists as a pure, tested, MT5-free function from Phases 2–5. Hand-rolling any of them breaks the core value (transparent, provable evidence) and the one-shared-code-path constraint. This phase is orchestration + persistence + presentation.

## Common Pitfalls

### Pitfall 1: Forgetting the entry-price derivation (D-01 limit-trigger)
**What goes wrong:** `Candidate` has no entry price (`entry_bar_idx`/SL/TP only); building the setup record with a missing or arbitrary entry breaks the limit-trigger semantics, the R:R, and the chart's entry line.
**Why it happens:** `candidate_at_bar` deliberately omits fill math (D-04); in live the entry is a *signal price* to be held until price trades through it.
**How to avoid:** The setup record must carry an explicit `entry`. Derive it at assembly (see Open Question A3) and keep it fixed for the setup's life; the active-trigger rule fires when a later M15 bar's high/low crosses `entry` in the trade direction.
**Warning signs:** setup records with `entry` `NaN`/missing, or a chart with no entry line, or R:R that doesn't match SL/TP.

### Pitfall 2: Future-data leak in the as-of slices
**What goes wrong:** The assembly/monitor slices M15/H1/H4 state and could see bars/events confirmed *after* the decision bar, inflating the evidence and the score.
**Why it happens:** The detector frames are full-run; slicing naively by timestamp (not by confirmation anchors) pulls future state.
**How to avoid:** Always slice through `visible_mask` with the per-tier anchors (`resolved_at` bar-time, `mitigated_at` bar-time, `activated_at`/`confirmed_at` close-time) and re-use the `payload_row` as-is (never re-anchored). The existing `features_at_decision`/`build_feature_frame` already encode these; reuse them.
**Warning signs:** evidence object carries `zone_state`/`pool_state` values that only exist after the decision bar; the assembled `p_win` shifts when later bars are appended.

### Pitfall 3: Diverging live exit rules from the backtest
**What goes wrong:** A custom active-exit comparison produces WIN/LOSS frequencies that don't match the backtest label distribution, so the performance panel is misleading.
**Why it happens:** Stray from `walk_barriers` (SL-first tie, gap-at-open, 96-bar inclusive barrier).
**How to avoid:** Resolve active setups with `walk_barriers` verbatim; only the *entry model* differs (D-01 limit-trigger vs backtest next-open) — document that caveat in the Performance panel.
**Warning signs:** live `r_net`/outcomes systematically diverge from the Phase-3 backtest stats on the same bars.

### Pitfall 4: Streamlit script-caching the live store
**What goes wrong:** `@st.cache_data` on the setup-store read makes the table/chart stale after a manual Refresh, or auto-refresh fights the cache.
**Why it happens:** Caching is tempting for speed but the refresh contract needs live reads.
**How to avoid:** No cache on the refresh path; `@st.cache_data(ttl=…)` only for immutable bars/labels/stats. Refresh CTA re-queries and `st.rerun()`.
**Warning signs:** clicking Refresh doesn't surface a new setup; the health-strip timestamp stays frozen.

### Pitfall 5: Unhandled missing-store crash vs Empty-state
**What goes wrong:** An empty `data/setups/setups.parquet` or missing bar file raises, blanking the whole app instead of the Empty state.
**Why it happens:** The app assumes stores exist and are populated.
**How to avoid:** `data_layer` reads defensively (missing file → empty frame), and each view catches read errors to render the UI-SPEC Empty/Error copy (`st.info`/`st.warning`) while leaving other tabs functional.
**Warning signs:** a red traceback on first run before any setup has been emitted.

### Pitfall 6: Missed `score_source` / agreement honesty
**What goes wrong:** Rendering `p_win` without its provenance tag, or styling a `heuristic` score like a calibrated ML score, undermines the trust core value.
**Why it happens:** The display layer treats probability as a plain number.
**How to avoid:** Always render `p_win` with its `score_source` tag (`ML`/`ML+LLM`/`heur`); `heur` in warning hue; render the `narrative_status=llm_unavailable` `⌀` + reason rather than omitting it (UI-SPEC honesty rule).
**Warning signs:** probability cells with no provenance chip; missing `heuristic` warning styling.

## Code Examples

Verified patterns from official sources:

### Streamlit AppTest (offline dashboard test)
```python
# Source: https://streamlit.io/docs (api-reference/testing + app-testing concepts)
from streamlit.testing.v1 import AppTest

def test_setups_tab_renders():
    at = AppTest.from_file("src/ai_trading/dashboard/app.py")
    at.secrets["DATA_ROOT"] = "data"           # or set a monkeypatched cfg
    at.run()
    assert not at.exception                     # app must not raise
    assert len(at.tabs) >= 4                    # Setups/History/Performance/Health
    # interact: at.sidebar.selectbox[0].select("EURUSD").run()
```

### Plotly candlestick with shaded zone bands (verified via plotly graphing-library docs)
```python
# Source: https://plotly.com/python/candlestick-charts/ + shapes docs
fig.add_shape(type="rect", xref="x", yref="y", x0="2017-01-31", x1="2017-02-01",
              y0=0, y1=1, fillcolor="#d3d3d3", opacity=0.2, line=dict(width=0))
```

### st.plotly_chart config + native theme (verified via streamlit docs)
```python
# Source: https://streamlit.io/docs (api-examples charts.plotly_chart_config)
import streamlit as st, plotly.graph_objects as go
fig = go.Figure(data=[go.Scatter(x=[1,2,3], y=[1,3,2])])
st.plotly_chart(fig, config={"scrollZoom": False})
```
(For the dashboard pass `theme=None` or rely on Streamlit theming; per UI-SPEC the `.streamlit/config.toml` `[theme]` block is the source of the palette.)

### st.dataframe + column_config (verified via streamlit docs)
```python
# Source: https://streamlit.io/docs (develop/api-reference/data/dataframe.md)
st.dataframe(filtered_df, column_config=column_configuration, use_container_width=True)
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Custom exit-resolution logic per live setup | Reuse `walk_barriers` (Phase 3 pure resolver) | This phase — mandated by D-03 | Guarantees live outcomes match backtest R/stats semantics |
| Ad-hoc evidence dicts | `serialize_evidence` whitelist build (Phase 5) | Phase 5 | Structurally prevents post-decision/fill leakage into the LLM/dashboard |
| Raw model probability | Calibrated `Scorer.score()` + `contributors()` (Phase 4) | Phase 4 | Honest, provenance-tagged P(WIN) + attribution for evidence |
| Manual stat math | `canonical_stats`/`stats_by_symbol_timeframe` (Phase 3) | Phase 3 | Pinned A4/A5/D-16 conventions — no drift in the Performance panel |

**Deprecated/outdated:**
- **Fallback-to-silence narrative:** replaced by `run_narrative_pipeline`'s labeled ML-only `NarrativeResult` (AI-07) — never render a blank gap for an unavailable LLM.
- **Uncoupled detector reimplementation:** any parallel backtest/live rule definition is deprecated by BT-01; always import the shared pure functions.

## Assumptions Log

> All claims tagged `[ASSUMED]` in this research. The planner and discuss-phase use this section to identify decisions that need user confirmation before execution.

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | The setup store is a dedup-on-`setup_id` Parquet file under `data/setups/setups.parquet` written atomically (tmp + os.replace, keep="last") | Architecture / store | Medium — if SQLite is preferred, the store API differs; the dashboard reads the same logical records regardless |
| A2 | The dashboard lives under `src/ai_trading/dashboard/` (Python package) with the app entry in `app.py`; `.streamlit/config.toml` applies the locked theme | Project structure | Low — location is internal; only the app path and theme config matter |
| A3 | The setup's `entry` price is derived at assembly (agent discretion, see Open Questions); recommendation is the decision-bar close, with the limit-trigger firing when a later M15 bar's high/low trades through it | Assembly | **Medium-High** — an incorrect entry derivation breaks D-01 limit-trigger semantics, R:R, and the chart; should be confirmed before locking the plan |
| A4 | The active-setup R for the performance panel uses structural `r_gross` (entry/sl distance) given v1 is signals-only (no real cost model); `r_raw`/`r_net` from `walk_barriers` are estimates | Lifecycle / DASH-05 | Medium — if live R must reflect costs, `r_net` with the D-16 cost model is used; the comparability caveat differs |
| A5 | The scheduled engine reuses the collector's `seconds_until_next_close("M15", ...)` polling convention for the M15-close trigger | Scheduler | Low — the trigger cadence mechanism is the established pattern |
| A6 | Dashboard tests run offline via Streamlit `AppTest` and do NOT require the MT5 terminal or LLM endpoint (stores are faked/stubbed in the test env) | Validation | Medium — if AppTest cannot be used in this env, the dashboard is validated via the pure `data_layer`/serialization tests instead |

**If this table is not empty:** Items A1–A6 need user confirmation (or planner lock-in for the discretion areas) before execution. A3 in particular should be confirmed before plan 06-01 locks the entry-derivation rule.

## Open Questions (RESOLVED)

> **RESOLVED — all five questions below are pinned in-plan with rationale** (see the "Discretion Decisions Pinned In-Plan" sections of 06-01-PLAN.md and 06-03-PLAN.md). Do not re-open: (1) entry = decision-bar close, limit-trigger on a later bar's high/low crossing entry (OQ1/A3, pinned in 06-01); (2) LLM narrative eager at assembly with the AI-07 labeled fallback (OQ2); (3) persist all detector-passing candidates, min-P(WIN) is a display filter via `setup_min_p_win` default 0.0 (OQ3); (4) health strip reads last-persisted heartbeat freshness, MT5-free (OQ4, pinned in 06-03); (5) single global `setup_trigger_window_bars` default 8, trigger on bar high/low crossing entry (OQ5).

1. **What exact price is the setup's `entry` (the D-01 limit-trigger level)?**
   - What we know: `Candidate` carries SL/TP/bias/zone/pool/event but **no entry price** (D-04 defers fill math). The live signal (D-01) must quote an entry that goes `pending` until price trades through it.
   - What's unclear: should the entry be (a) the decision-bar close (price at the signal), (b) the zone's near boundary (the retracement the limit sits at), or (c) another structural reference? This determines R:R, the trigger condition, and the chart's entry line.
   - Recommendation: default to the **decision-bar close** as the quoted entry for v1 (simplest, matches "signal fires at the decision close"), with the limit-trigger defined as a later M15 bar's high/low crossing it in the trade direction. Confirm this with the user (discretion area) before locking plan 06-01.
2. **Does the LLM narrative run eagerly at assembly or on-demand when a setup is viewed?**
   - What we know: `run_narrative_pipeline` is a provider call potentially slow/failing; AI-07 falls back to ML-only. The UI-SPEC renders the evidence trace incl. narrative.
   - What's unclear: eager (narrative persisted on the setup at assembly, richer records, slower assembly, provider dependency in the scheduled path) vs on-demand (rendered at view time, faster engine, needs a cached/missing-narrative state).
   - Recommendation: **eager at assembly** with the AI-07 fallback persisted (records include `narrative_status`/`reason`/`agreement`), so the dashboard is purely a reader and offline events render `⌀` (UI-SPEC). This is a discretion area — confirm.
3. **Is there a min-P(WIN) filter on which candidates become setups?**
   - What we know: Phase 6 discretion; UI-SPEC exposes a min-probability *display* filter (default 0), separate from a qualification threshold.
   - What's unclear: whether the engine persists only setups above a configurable `setup_min_p_win`, or persists all detector-passing candidates and lets the dashboard filter.
   - Recommendation: persist all candidates (so the history is complete/provable) and apply the min-`p_win` only as a display/qualification knob; confirm with the user whether a hard engine-side minimum is wanted.
4. **Does the health strip read live MT5 status or last-persisted state?**
   - What we know: UI-SPEC health strip shows last-bar time per feed + MT5 connection status + recent errors. The dashboard is MT5-free (reads stores).
   - What's unclear: "MT5 connected" as a persisted heartbeat (meta/checkpoint timestamp freshness) vs an actual live MT5 probe in the dashboard.
   - Recommendation: show **last-persisted state** (checkpoint `last_success_at` freshness + stall detection) so the dashboard stays MT5-free; a live probe belongs in the collector/health adapter, surfaced as a degraded/stale warning (UI-SPEC MT5-disconnected copy). Discretion area — confirm.
5. **Per-symbol vs global trigger window and the exact trigger check.**
   - What we know: D-04 default window ~8 M15 bars; the trigger is "price trades through entry".
   - What's unclear: single global `setup_trigger_window_bars` vs per-symbol; whether the trigger tests bar high/low crossing `entry` or bar close crossing it.
   - Recommendation: single global `setup_trigger_window_bars` (default 8) and trigger on **bar high/low crossing `entry`** in the trade direction (wick tolerance matches the SMC wick-touch convention). Discretion area — confirm.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.12 | Project runtime (`requires-python >=3.12`) | ✓ | 3.12.12 (in `.venv`) | `uv python` can fetch 3.13/3.14 if needed |
| uv | Package management / `uv add` | ✓ | (uv.exe on PATH) | — |
| streamlit | Dashboard | ✗ (not installed; to be added) | — | Add via `uv add "streamlit>=1.39"` |
| plotly | Charts | ✗ (not installed; to be added) | — | Add via `uv add "plotly>=5.23"` |
| MT5 terminal + adapter | Real-data collection/health (NOT the engine/dashboard) | known-running per project; MT5-free for this phase | — | Dashboard/engine never touch MT5 directly |
| `streamlit.testing.v1.AppTest` | Offline dashboard tests | requires installed streamlit | — | tests skip if AppTest unavailable; pure data-layer tests cover logic |

**Missing dependencies with no fallback:** streamlit, plotly — must be installed via `uv add` (this is an intentional new runtime dependency for the phase; no alternative for the locked Streamlit/plotly stack).

**Missing dependencies with fallback:** MT5 terminal (the engine and dashboard are MT5-free by design; only the health strip displays last-persisted state, so a stopped terminal degrades to a stale-warning rather than blocking).

> **Step 2.6 note:** The setup-engine + dashboard are code/config changes over the existing stores — the only *new* external dependencies are `streamlit`/`plotly` (runtime) which this phase must add. MT5 is NOT required by the engine/dashboard (MT5-free design), so this is an environment-available-with-install-step, not a blocker.

## Validation Architecture

> `workflow.nyquist_validation` is `true` in `.planning/config.json` — this section applies.

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (project default, `pytest>=9.1.1`); Streamlit `AppTest` for the app |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` (testpaths `tests`, addopts `-m "not mt5 and not llm and not streamlit"`) |
| Quick run command | `uv run pytest -q tests/unit/test_setup_assembly.py tests/unit/test_setup_lifecycle.py tests/unit/test_setup_store.py` |
| Full suite command | `uv run pytest -q -m "not mt5 and not llm and not streamlit"` |

> Add a `streamlit` pytest marker (to `[tool.pytest.ini_options] markers`) for Streamlit `AppTest` tests so they can be selected/desellected independently. `AppTest` is offline but the standardized marker excludes it from the default suite (`-m "not mt5 and not llm and not streamlit"`); AppTest cases run via the explicit `-m streamlit` selector, matching the `llm` precedent.

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| SETUP-01 | Record: symbol/direction/entry/SL/TP/RR + level rationale | unit | `uv run pytest -q tests/unit/test_setup_assembly.py -x` | ❌ Wave 0 |
| SETUP-02 | Evidence object persisted (zone/sweep/bias/ML contributors) | unit | `uv run pytest -q tests/unit/test_setup_assembly.py -x` | ❌ Wave 0 |
| SETUP-03 | Lifecycle active→tp_hit/sl_hit/expired via bar-close | unit | `uv run pytest -q tests/unit/test_setup_lifecycle.py -x` | ❌ Wave 0 |
| SETUP-04 | Untriggered expire/invalidate (N-bar window / structure break) | unit | `uv run pytest -q tests/unit/test_setup_lifecycle.py -x` | ❌ Wave 0 |
| DASH-01 | Setup table filters (symbol/status/direction/min-prob/date) | unit (data_layer) + AppTest | `uv run pytest -q tests/unit/test_dashboard_data.py tests/ui/test_dashboard_app.py -x` | ❌ Wave 0 |
| DASH-02 | Candlestick + entry/SL/TP + sweep + PD-zone overlays | unit (chart build) + AppTest | `uv run pytest -q tests/unit/test_dashboard_data.py -x` | ❌ Wave 0 |
| DASH-03 | Evidence trace ordering + narrative/agreement render | unit + AppTest | `uv run pytest -q tests/ui/test_dashboard_app.py -x` | ❌ Wave 0 |
| DASH-04 | History lifecycle outcomes | unit (data_layer) | `uv run pytest -q tests/unit/test_dashboard_data.py -x` | ❌ Wave 0 |
| DASH-05 | WR/PF/expectancy + R equity curve (aggregate + per symbol) | unit (stats reuse) | `uv run pytest -q tests/unit/test_dashboard_data.py -x` | ❌ Wave 0 |
| DASH-06 | Health strip last-bar time + MT5 status + errors | unit (data_layer) + AppTest | `uv run pytest -q tests/unit/test_dashboard_data.py -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest -q tests/unit/test_setup_*.py tests/unit/test_dashboard_data.py -x`
- **Per wave merge:** `uv run pytest -q -m "not mt5 and not llm and not streamlit"`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps
- [x] `tests/conftest.py` — `_make_cfg` must gain `setup_*` defaults so `Config(...)` direct construction keeps working
- [x] `tests/unit/_backtest_fixtures.py` / bar factories — reuse `make_bars` + `run_chain` fixtures to feed assembly/lifecycle tests
- [x] `tests/integration/test_dashboard_app.py` (optional) — AppTest smoke against a fixture store dir
- [x] Add the `streamlit` pytest marker to `pyproject.toml`
- [x] `tests/unit/_setup_fixtures.py` (new) — shared setup-record / chain / bar fixtures

## Security Domain

> `security_enforcement` is `true` (ASVS Level 1) in `.planning/config.json` — this section applies.

### Applicable ASVS Categories
| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | No authentication — local single-user Streamlit app reading local files (no user input to gate on this phase) |
| V3 Session Management | no | No sessions/accounts — stateless local app |
| V4 Access Control | yes | Path traversal guard on data-root (`resolve`-under-root) for any new `data/setups` + report readers; the setup store/report paths derive from a fixed config-driven root (mirror `backtest._output_dirs` / `_output_dirs` guard) |
| V5 Input Validation | yes | Filter inputs validated/typed in the data layer (display filters); frozen `Config` validates `setup_*`/schedule knobs at load |
| V6 Cryptography | no | No secrets/crypto in this phase (no API keys; data is local SMC/ML records) |

### Known Threat Patterns for the Streamlit/setup stack
| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Path traversal via a store/report path | Tampering | Fixed config-driven filenames; resolve-under-data-root guard on any derived output dir (reuse `_output_dirs`) |
| Untrusted display data → HTML/script injection | Tampering | Render via Streamlit native widgets (`st.dataframe`/`st.plotly_chart`/`st.markdown` with no unsanitized `unsafe_allow_html`); never inject raw evidence strings as HTML |
| Stale/missing store crash → info exposure | Denial of Service | Defensive reads + Empty/Error states; per-view suppression |
| Overly long LLM/call time-blocking the engine | Availability | `run_narrative_pipeline` is wall-clock-bounded (AI-07) with ML-only fallback; scheduler polls with `poll_delay` |
| Config secret in the dashboard | Information Disclosure | `llm_api_key` stays only in gitignored `config.local.toml`; the dashboard reads only non-secret setup/report records — never render the key |

## Sources

### Primary (HIGH confidence)
- [Context7 `/streamlit/docs`] — `st.plotly_chart` config, `AppTest` (from_file/run, session_state, secrets), `st.dataframe` + `column_config`, `st.cache_data(ttl=)` / session-state patterns
- [Context7 `/plotly/graphing-library-docs`] — candlestick + `add_shape` rect shaded bands, `layer`, annotations
- [PyPI registry via `pip index versions`] — streamlit latest 1.63.0, plotly latest 7.0.0
- [Repo source: `backtest/candidates.py`, `backtest/barriers.py`, `backtest/replay.py`, `backtest/stats.py`] — `candidate_at_bar`/`CandidateState`/`compute_rr`, `walk_barriers`, `LABEL_COLUMNS`, `canonical_stats`/`stats_by_symbol_timeframe`
- [Repo source: `ml/features.py`, `ml/scorer.py`] — `features_at_decision`/`build_feature_frame`, `load_scorer`/`Scorer.score`/`contributors`
- [Repo source: `llm/evidence.py`, `llm/narrative.py`] — `serialize_evidence`, `run_narrative_pipeline`, `NarrativeResult`, `agreement_flag`
- [Repo source: `config.py`, `stores/bar_store.py`, `stores/meta_store.py`, `collector.py`, `history_report.py`] — frozen Config pattern, store discipline, polling + health data source

### Secondary (MEDIUM confidence)
- [Context7 `/streamlit/streamlit`] — cross-check of Streamlit APIs (benchmark-matched to official docs)
- [.planning/phases/02/03/04/05 CONTEXT.md + SUMMARY] — locked D-rules, evidence/summary contracts

### Tertiary (LOW confidence)
- [Seam package-legitimacy check WARNINGS] — `streamlit`/`plotly` flagged `too-new`/`unknown-downloads`; treated as heuristics (mark as noted; official-domain docs confirm identity)

## Metadata

**Confidence breakdown:**
- Standard stack: **HIGH** — streamlit/plotly versions verified against PyPI registry + Context7 official docs
- Architecture: **HIGH** — module-level reuse verified directly in repo source; the assembly/lifecycle call-chain is grounded in the actual Phase 3/4/5 exports
- Pitfalls: **HIGH** — grounded in verified repo contracts (as-of discipline, D-10/D-11/D-17, UI-SPEC honesty rules)
- Entry-price derivation & discretion-area items: **MEDIUM** — flagged as open/discretion needing user confirmation (A3)

**Research date:** 2026-09-04
**Valid until:** 2026-10-04 (30 days; stack stable, streamlit/plotly fast-moving — re-check pinned versions at install time)

