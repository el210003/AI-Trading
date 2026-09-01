# Phase 3: Backtesting & Labeling - Research

**Researched:** 2026-09-01
**Domain:** Bar-by-bar replay engine over stored MT5 history, cost modeling, triple-barrier labeling, canonical + walk-forward statistics (Python 3.12 / pandas 3.x, MT5-free by design)
**Confidence:** HIGH (replay architecture grounded in verified Phase 2 contracts + in-repo data audit; MEDIUM for external conventions cited from secondary sources)

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** A labeled trade = **sweep + zone tap**: a sweep event (take-out + reclaim, SMC-03) followed by price returning into a PD zone on the right side (discount for longs, premium for shorts) and mitigating it (SMC-05). Sweep-only and zone-only candidates are NOT labeled.
- **D-02:** **Respect HTF bias**: a candidate is only labeled when the H1/H4 bias (D-13: premium→bearish, discount→bullish, via the lean MTF payload D-14) agrees with trade direction. Bias is recorded on the label regardless.
- **D-03:** The entry-candidate spec is **defined once in this phase** as pure functions; Phase 6 setup assembly uses the exact same functions (no parallel rule definitions). BT-01 spirit: whatever live analysis does, the backtester replays.
- **D-04:** Entry fill = **next-bar open** (signal detected at M15 close; entry at the next M15 bar's open). No intrabar/limit fills in v1.
- **D-05:** **One at a time**: per (symbol, timeframe), a new candidate is suppressed until the current one resolves (TP/SL/timeout). No concurrent candidates on the same symbol/TF.
- **D-06:** Candidates are generated on **M15 only** (execution timeframe); H1/H4 supply bias context only — no HTF candidate generation.
- **D-07:** **Auto warmup, skip**: the first N bars (ATR(14) + fractal confirmation + one completed zigzag leg + HTF history for as-of join) are warmup; candidates within warmup are silently skipped, not errors.
- **D-08:** SL is **structural, raw**: beyond the swept pool level / the zone's far boundary, with no buffer. No ATR buffer at the SL.
- **D-09:** TP is **structural**: the far side of the PD zone, or the opposite liquidity pool / prior confirmed swing level. R:R varies per trade (no fixed R:R, no hard cap).
- **D-10:** Intrabar tie rule = **SL-first, ALL bars** (entry bar included): if SL and TP are both touched within one bar, label SL-first. Matches BT-03's documented conservative default.
- **D-11:** Gap handling: if a bar **opens beyond the SL level**, the exit fills at the bar's **OPEN price** (marked SL). Same rule for gapped TP: fill at open. No ignore-gaps mode.
- **D-12:** **Discard below min R:R**: candidates whose structural SL/TP distance yields R:R below a minimum (default 1.0, configurable) are discarded from the label set.
- **D-13:** SL/TP price levels are **raw detector outputs** (zone boundaries / pool levels), used as-is; no freeze-at-confirmation re-derivation in v1.
- **D-14:** Slippage buffer = **fixed pips per symbol** (default 0.5 pip, per-symbol override in config). Charged on BOTH entry and exit fills (worse for entry, worse for exit).
- **D-15:** Spread = **recorded per-bar spread** (normalize.py `COLUMNS.spread`) at the fill bar; when a bar's spread is 0/absent (HTF/M1 aggregation artifacts), fall back to a per-symbol default spread from config.
- **D-16:** Reports show **both raw (spread-only) and net (spread + slippage)** metrics, with the cost delta visible.
- **D-17:** Time barrier = **96 M15 bars (24h)**. If neither barrier is hit within the window, the label is TIMEOUT (exit at final bar close). Configurable default 96.
- **D-18:** Outcome classes = **WIN (TP hit) / LOSS (SL hit) / TIMEOUT**; no extra sub-flags in v1.
- **D-19:** Walk-forward split = **expanding train + rolling test**: training window expands monotonically, fixed-length test windows slide forward, strictly chronological, NO overlap, NO shuffled splits (AI-04).
- **D-20:** Default window sizes = **6 months train / 1 month test** (configurable). The harness must also support shorter windows (e.g., 2mo/2wk) given ~90 days of currently stored history.
- **D-21:** History gate (SC2) = **~30 days minimum stored history** per symbol/timeframe before a run is allowed; refuse with an actionable message below that.
- **D-22:** Walk-forward reports = **full canonical stats per (symbol, timeframe) AND per window**, plus a per-window aggregate across symbols (BT-05).

### the agent's Discretion
- Exact report artifact format (JSON/Parquet/markdown) and on-disk layout under `data/` or `config` — planner decides
- Label store schema/table design (Parquet/SQLite) and whether labels are recomputed or cached per run
- Replay engine implementation approach (vectorized vs per-bar loop) and how detector functions are invoked bar-by-bar
- CLV/tick-level refinement beyond open-based fills; intrabar path assumptions (only open/high/low/close are used)
- Where the entry-rule pure functions live (module layout under `src/ai_trading/`)
- How the backtest runner is invoked (CLI flags, config sections) — follows Phase 1/2 config-dataclass discipline

### Deferred Ideas (OUT OF SCOPE)
None — discussion stayed within phase scope. (Cost-sensitivity table over slippage 0/0.5/1.0 pip was offered and not selected; natural candidate for a later enhancement.)
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| BT-01 | Backtester replays the identical pipeline bar-by-bar used by live analysis (one shared code path) | Replay architecture Pattern 1: run the Phase 2 chain ONCE over the range and consume outputs via a column-aware as-of slicer — same detector functions, zero re-implementation. Verified Phase 2 tier-3 guarantees (prefix == visible subset) make full-frame + filter equivalent to per-bar. Key-link test: `test_replay_equals_prefix_runs` extends `assert_point_in_time_prefix_equality` (Pattern: look-ahead verification). |
| BT-02 | Outcomes model spread (recorded bar spread) + slippage buffer; metrics net of costs | Pattern 4 cost model: `spread` column is in POINTS (verified in stored data — EURUSD 17–42, GBPUSD weekend 101; points→price via point_size), D-15 fallback to per-symbol default when spread==0 (0.92–1.00 zero-fraction on EURUSD/USDJPY files — fallback is heavily exercised), D-14 slippage pips→price (pip_size 0.0001/0.01), bid-side bar prices, spread crossed once (long at entry, short at exit) + slippage both fills; raw vs net dual reporting. |
| BT-03 | Triple-barrier labeling with documented intrabar tie rule (SL-first conservative) | Pattern 3 barrier walk: entry bar included, SL-first tie, D-11 gap=open-fill, 96-bar inclusive window (bars E..E+95), TIMEOUT at final bar close. Intrabar order is provably unknowable from OHLC — the locked SL-first convention matches the conservative standard (MDPI corroboration) and must be a named, pinned test. AFML close-only reference used for context only (does NOT detect intrabar H/L touches). |
| BT-04 | Canonical stats (win rate, PF, expectancy, max DD, avg R, trade count) per symbol/timeframe | Pattern 6 stats as pure pandas functions with explicit edge-case guards (zero-loss PF, empty sets, all-wins/all-losses); raw & net variants per D-16. |
| BT-05 | Per-time-window (walk-forward) reports to expose regime shifts; per-window aggregate across symbols | Pattern 7 walk-forward: expanding train + rolling test, strictly chronological, no overlap (sklearn TimeSeriesSplit semantics); entry-time-based window assignment; labels carry entry/exit stamps so Phase 4 can purge boundary-overlapping labels (AFML Ch.7), per D-19/D-20/D-22. Small-window support is REQUIRED — current store can only support degenerate windows (see Environment Availability). |
</phase_requirements>

## Project Constraints (from AGENTS.md)

No `./AGENTS.md`, `./CLAUDE.md`, `.claude/CLAUDE.md`, `.claude/skills/`, `.agents/skills/`, or `.planning/graphs/graph.json` exists in the repo root (verified via Test-Path this session). No additional project-specific directives beyond the locked decisions above and the conventions documented in `.planning/ROADMAP.md`, `.planning/PROJECT.md`, and the phase 1–3 CONTEXT/VALIDATION artifacts. The one governance rule the research must respect: PROJECT.md "One shared, look-ahead-safe code path for live analysis AND backtests (non-negotiable)".

## Summary

Phase 3 builds the first runtime artifact chain ABOVE the Phase 2 detectors: a replay engine that turns stored bars + detector outputs into labeled trades and statistics. The decisive architectural insight from reading the Phase 2 code is that **the replay engine does NOT need to re-run detectors per bar** — every Phase 2 detector is a stateless pure function whose output is already confirmation-time-immune (proven by the 02-01…02-04 tier-3 repaint tests: prefix output == visible subset of full-frame output, `check_exact=True`). The engine runs the identical chain once over the loaded range and consumes outputs through a **column-aware as-of slicer**. The hard part is that timestamp semantics are heterogeneous across the chain (close-time stamps: `swings.confirmed_at`, `zones.created_at`, `pools.activated_at`; bar-time stamps: `pools.resolved_at`/`pierced_at`, `zones.mitigated_at`/`invalidated_at`) — one visibility helper with two anchors (decision bar time and decision close time) keeps every tier honest, and a prefix-equivalence test proves it.

The second decisive finding is a data-reality check: the current store holds ~501–541 bars per combo — **M15 only ≈ 9 days (Aug 21–31), H1 ≈ 29 days, H4 ≈ 115 days** — and stored spread is **0 on 50–100% of rows** (EURUSD/USDJPY ≈ 92–100% zero). Consequences: (1) D-15's per-symbol default-spread fallback is not an edge case, it is the default path; (2) D-21's ~30-day gate currently REFUSES M15/H1 runs — a real run needs either more stored history (Phase 1's sanctioned purge + restart backfill; terminal-available depth is 250k M15 bars back to 2016, persisted in `history_bounds`) or a documented gate override; (3) D-20's small-window support is mandatory, not optional, because 6mo/1mo windows cannot execute on what's on disk today. These three facts shape plans 03-01…03-03 more than any library choice.

Cost model and label spec are locked (D-14…D-18) and implementable as pure functions with zero new dependencies: the recorded MT5 `spread` column is in **points** (empirically verified: EURUSD values 17–42 on a 5-digit quote ⇒ 1.7–4.2 pips; GBPUSD 101 on a weekend bar), so both spread and slippage convert through the symbol's point/pip size. Intrabar tie order is provably ambiguous with OHLC-only data — the SL-first convention (D-10) is a locked conservative choice corroborated across sources (MDPI paper: "stop-loss checked first"; MT5's own M1 OHLC tester uses a deterministic synthetic path that can fabricate phantom wins; backtesting.py uses pessimistic ordering).

**Primary recommendation:** Zero new packages. One `backtest/` package under `src/ai_trading/` with (a) a pure chain-runner + as-of slicer, (b) pure entry-rule functions (D-01…D-04, D-08…D-13 — owned here, reused by Phase 6), (c) a forward-pass replay loop in the established event-sparse sequential-loop style (`pools.py`/`zones.py` precedent, "deliberately not vectorized"), (d) pure triple-barrier + cost functions, (e) pure stats/report functions over pandas, (f) a CLI runner following the `history_report.py` argparse/exit-code pattern, and (g) extension of the repaint/prefix-equality test machinery for look-ahead-proof verification. Artifacts: Parquet label file + JSON canon + Parquet per-window breakdown under `data/labels/` and `data/reports/` (recommended, planner owns).

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Historical range validation + history gate (D-21) | Service (runner) | Storage (`bar_store.read_bars`, `history_bounds`) | Runner validates before executing; gate is config-driven, refuses with actionable message |
| Detector chain execution over a range | Domain (pure chain-runner) | — | Same functions as live; no adapter/MT5 dependency; deterministic by Phase 2 guarantee |
| Point-in-time as-of slicing of detector output | Domain (pure helper) | — | Column-aware visibility helper is the anti-lookahead choke point; unit-testable in isolation |
| Entry-candidate generation (D-01…D-04, D-08…D-13) | Domain (pure functions, THIS phase owns) | — | Defined once here; Phase 6 setup assembly imports them (BT-01/D-03) |
| Position state machine (D-05 one-at-a-time, D-07 warmup skip) | Domain (replay loop) | Service | Sequential forward pass; state lives in the loop, not in a store |
| Fill/cost modeling (D-14/D-15, bid/ask asymmetry) | Domain (pure functions) | Config (pip_size, default_spread, slippage) | Pure arithmetic; config carries per-symbol knobs |
| Triple-barrier outcome evaluation (D-10/D-11/D-17/D-18) | Domain (pure functions) | — | Bar-by-bar walk over 96-bar window; entry bar included |
| Canonical stats (BT-04) | Domain (pure functions) | — | pandas/numpy only; raw & net variants |
| Walk-forward windowing + per-window stats (D-19/D-20/D-22) | Domain (harness) | Service (runner) | Expanding-train/rolling-test split; entry-time assignment; Phase 4 reuses |
| Artifact persistence (labels, reports) | Storage layer | — | Established Parquet/SQLite discipline (atomic write, `merge_and_write` style must NOT be re-purposed for labels without care) |
| CLI invocation | Service | Config | `python -m ai_trading.backtest` + argparse `--config/--range/--symbols` pattern |

## Standard Stack

### Core

**No new runtime dependencies.** The phase reuses the locked stack: Python 3.12, `pandas>=3.0,<4` (installed), `pyarrow>=25.0.1` (installed), stdlib `sqlite3`, `argparse`, `dataclasses`, `timedelta`. numpy via pandas.

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| pandas | >=3.0,<4 (pinned, installed) | DataFrame/Series arithmetic, merge_asof-free slicing, parquet IO | Locked stack (Phase 1); `%`-free vectorized guards; dtype pinned to datetime64[us] convention |
| pyarrow | >=25.0.1 (installed) | Parquet read/write for labels/reports | Locked stack; `zstd` compression convention from `bar_store` |
| numpy | via pandas | NaN guards, arithmetic on R-curves | Already transitive; no direct pin needed |
| sqlite3 | stdlib 3.12 | Optional run registry / artifact index | Established `meta_store` WAL pattern — only if planner chooses SQLite for run bookkeeping |

### Supporting (project-internal, no installs)
| Item | Location | Purpose | When to Use |
|------|----------|---------|-------------|
| `detectors/*` chain | `src/ai_trading/detectors/` | The replay's sole signal source (BT-01) | Always — never re-implement |
| `bar_store.read_bars` | `src/ai_trading/stores/bar_store.py` | Replay input path (COLUMNS-ordered, empty-frame contract) | Always (MT5-free) |
| `meta_store` history_bounds | `src/ai_trading/stores/meta_store.py` | Range validation inputs (stored bounds) | Gate checks |
| `normalize.TIMEFRAME_MINUTES` / `COLUMNS` | `src/ai_trading/normalize.py` | Bar-count math (96-bar window), spread column | Always — single source of truth |
| `tests/conftest.make_bars` + `_detector_fixtures` | tests | Synthetic frames with configurable spread/offset for deterministic label tests | Extend, never mutate (Phase 1/2 contract) |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Own forward-pass replay loop (recommended) | `vectorbt` (PyPI: exists, seam verdict **SUS** — unknown-downloads only) | vectorbt is vectorized-first and cannot host stateful per-bar detector calls with confirmation-time as-of discipline; would force rewriting fills into a black box — violates BT-01 |
| Own barrier walk | `backtesting.py` (PyPI install name is `backtesting`; seam verdict **SLOP** — `backtesting.py` does not exist; `backtesting` itself unverified this session) | Framework Strategy API + its own fill semantics create TWO code paths; requirement is the same functions as live, not a framework demo |
| Own stats | `quantstats` (seam **SUS**, unknown-downloads) | Report format must be per (symbol, TF) × window × raw/net — groupby logic becomes custom glue anyway; torch of dependencies for 5 formulas |
| Own labeling | `mlfinlab` (seam **SLOP** — no PyPI package; docs are the Hudson&Thames autodocs) | Its canonical method is close-only (no intrabar H/L) and its free package is gone; project rules differ (D-10/D-11) — reference only |
| Pure-python loop | numba/Cython acceleration | 501–16k bars/range is milliseconds in pandas; premature |

**Installation:**
```bash
# NONE. No new packages. Existing locked stack suffices.
# Verify pinned stack if 30+ days elapse:
uv run python -c "import pandas, pyarrow, numpy; print(pandas.__version__, pyarrow.__version__, numpy.__version__)"
```

**Version verification:** No new packages to verify against a registry. Existing pinned versions were verified in Phase 1 (pandas 3.0.x, pyarrow 25.x). Current environment check this session: `uv 0.11.28` present; `uv run pytest` collects 174/177 (3 mt5-deselected) — Phase 2 state green.

## Package Legitimacy Audit

> **No external packages are installed by this phase** — the phase uses only the already-locked, already-installed stack (verified in `pyproject.toml`). The audit below documents the candidates that were evaluated and rejected, per the protocol.

| Package | Registry | Age | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----|-----------|-------------|---------|-------------|
| (none — no installs) | — | — | — | — | — | Approved: zero-dependency phase |
| vectorbt | PyPI | exists; pub 2026-07-05 | unknown (seam) | github.com/polakowo/vectorbt | SUS | NOT INSTALLED — rejected by design (BT-01 purity); if ever used, `checkpoint:human-verify` |
| quantstats | PyPI | exists; pub 2026-01-13 | unknown (seam) | github.com/ranaroussi/quantstats | SUS | NOT INSTALLED — rejected by design (report structure); if ever used, `checkpoint:human-verify` |
| backtesting.py | PyPI | **does not exist** (install name is `backtesting`) | n/a | n/a | SLOP | REMOVED — never reference as installable |
| mlfinlab | PyPI | **does not exist** (free package removed; docs-only) | n/a | n/a | SLOP | REMOVED — cite book/autodocs as reference only |

**Packages removed due to [SLOP] verdict:** `backtesting.py`, `mlfinlab` (neither is installable from PyPI; excluded from all recommendations).
**Packages flagged as suspicious [SUS]:** `vectorbt`, `quantstats` — flagged but NOT installed; no checkpoint required because no install occurs this phase.

## Architecture Patterns

### System Architecture Diagram

```
                        config.toml (backtest knobs: slippage, spread default,
                        min_rr, time_barrier_bars, wf_train/test, min_history_days)
                                    │
                                    ▼
   ┌────────────────────────────────────────────────────────────────┐
   │  Runner CLI  (python -m ai_trading.backtest)                   │
   │  1. Range validation + D-21 history gate (read_bars /          │
   │     history_bounds)  ── refuse with actionable message         │
   │  2. Load M15 bars [start,end] + HTF bars [start−warmup,end]    │
   └────────────────────────────┬───────────────────────────────────┘
                                ▼
   ┌────────────────────────────────────────────────────────────────┐
   │  Chain runner (BT-01 — THE SAME functions as live analysis)    │
   │  M15:  detect_swings → build_zigzag → detect_pools             │
   │        → derive_zones  (events, pools, zones)                  │
   │  H1/H4: detect_swings → build_zigzag → derive_zones            │
   │        → htf_context(m15, zones_h1, zones_h4)                  │
   │  (pure, MT5-free, deterministic — Phase 2 verified)            │
   └────────────────────────────┬───────────────────────────────────┘
                                ▼
   ┌────────────────────────────────────────────────────────────────┐
   │  As-of slicer (column-aware visibility helper)                 │
   │  close-time stamps ≤ decision_close; bar-time stamps ≤         │
   │  decision_bar_time; payload row index = decision bar           │
   │  (the ONLY future-data choke point)                            │
   └────────────────────────────┬───────────────────────────────────┘
                                ▼  visible state at close of bar S
   ┌────────────────────────────────────────────────────────────────┐
   │  Forward-pass replay loop (per symbol, M15 bars)               │
   │  ├─ warmup skip (D-07: ATR(14)+fractal+leg+HTF history)        │
   │  ├─ entry-rule pure functions (D-01…D-04,D-08…D-13) →           │
   │  │   candidate (dir, SL, TP, R:R, evidence IDs) or None        │
   │  │   [D-05: suppress while a position is open; D-12: min R:R]  │
   │  ├─ fill model: next-bar open ± spread/slippage (D-04,D-14,15) │
   │  ├─ barrier walk bars E..E+95: SL-first (D-10), gap=open (D-11)│
   │  │   TIMEOUT at final bar close (D-17) → label WIN/LOSS/TIME   │
   │  └─ label record: entry/exit, R, costs raw+net (D-16)          │
   └────────────────────────────┬───────────────────────────────────┘
                                ▼
   ┌────────────────────────────┬───────────────────────────────────┐
   │  Stats (pure)              │  Walk-forward harness (D-19/20/22)│
   │  canonical per (sym,TF)    │  expanding train / rolling test   │
   │  win rate, PF, expectancy, │  per-window stats + aggregate     │
   │  maxDD, avgR, count (raw + │                                   │
   │  net variants)             │                                   │
   └───────────────┬────────────┴───────────────┬───────────────────┘
                   ▼                            ▼
        data/labels/*.parquet + canon JSON   data/reports/walkforward_{ts}.parquet
        (atomic write discipline)            (atomic write discipline)
```

Primary use-case trace: `backtest --symbols EURUSD --range last-30d` → gate pass → chain once → as-of slice per M15 close → candidate → next-bar-open fill → 96-bar barrier walk → label → canonical + per-window stats → artifacts. No MT5 call anywhere; `mt5` marker never applies to the replay path.

### Recommended Project Structure

```
src/ai_trading/
├── backtest/                    # NEW — MT5-free, pure, tests mirror Phase 2 style
│   ├── __init__.py              # bare marker (mirror detectors/__init__.py)
│   ├── asof.py                  # column-aware visibility helper (+ anchors)
│   ├── chain.py                 # run_chain over loaded bars (may reuse detector
│   │                            #   integration test runner shape)
│   ├── candidates.py            # D-01…D-04, D-08…D-13 entry-rule PURE functions
│   │                            #   (owned here; Phase 6 imports these)
│   ├── costs.py                 # pip/point conversion, fill math, spread fallback
│   ├── barriers.py              # triple-barrier walk (D-10/D-11/D-17/D-18)
│   ├── replay.py                # forward-pass loop: one-candidate state machine,
│   │                            #   warmup skip, orchestrates candidates+barriers
│   ├── stats.py                 # canonical stats (raw+net) + edges
│   ├── walkforward.py           # D-19/D-20 window derivation (expanding/rolling)
│   ├── reports.py               # artifact writers (Parquet+JSON), atomic writes
│   └── runner.py                # CLI: argparse --config/--range/--symbols/--write
│                                #   exit codes 2 config / 1 runtime (history_report pattern)
└── config.py                    # EXTEND frozen Config with backtest knobs
                                 #   (slippage_pips, default_spread_points, pip_size,
                                 #    min_rr, time_barrier_bars, wf_train_days,
                                 #    wf_test_days, min_history_days, warmup knobs)
tests/unit/
├── test_asof.py                 # visibility helper: each tier's stamp semantics
├── test_candidates.py           # entry-rule composition (sweep+zone+bias)
├── test_costs.py                # points→price, spread fallback, raw vs net
├── test_barriers.py             # SL-first tie, gap=open, 96-bar window off-by-one
├── test_replay.py               # forward-pass, one-at-a-time, warmup skip
├── test_replay_repaint.py       # THE anti-lookahead suite (prefix equivalence)
├── test_stats.py                # PF/expectancy/maxDD/avgR edges
├── test_walkforward.py          # no overlap, chronological, expanding train,
│                                #   small-window support
└── test_reports.py              # artifacts + atomic writes + determinism
```

### Pattern 1: Single-pass chain runner + as-of slicer (the BT-01 answer)

**What:** Run the identical detector chain ONCE over the loaded range (and a warmup-padded HTF lead-in), then compute every per-bar decision from that output through a pure `visible(state, bar)` helper. Do NOT re-invoke detectors per bar.

**Why it is sound:** Phase 2 already proves tier-3 immutability — 02-VERIFICATION table rows show resolved pools (pools.py L324-339), completed-leg zones (zones.py L203-212), and swings (swings.py `confirmed_at` stamps) are all prefix-stable (`check_exact=True`). A decision at the close of bar S therefore sees exactly the same records whether the chain ran over `bars[:S+1]` or over the full range — provided the slicer uses the correct per-tier horizon.

**The heterogeneous timestamp semantics (the thing that makes this hard):**

| Detector column | Stamp form | Visible at close of bar S iff |
|---|---|---|
| `swings.confirmed_at`, `zigzag.confirmed_at` | close-time (`t + TF`) | `stamp <= close_time(S)` = `t_S + TF` |
| `zones.created_at` | close-time (p2.confirmed_at) | `stamp <= close_time(S)` |
| `pools.activated_at` | close-time | `stamp <= close_time(S)` |
| `pools.pierced_at`, `pools.resolved_at` | bar-time (`t`) | `stamp <= t_S` |
| `zones.mitigated_at`, `zones.invalidated_at` | bar-time (`t`) | `stamp <= t_S`; liveness additionally requires `invalidated_at` is NA or `>= t_S` (mirror `mtf._is_live`) |
| MTF payload row for bar S | as-of `t_S` (D-15, strictly-before) | use `payload[payload.time_utc == t_S]` as-is — NEVER re-anchor |

**When to use:** always — it is the only shape that guarantees BT-01 (no second implementation) and SC1 (no lookahead).

**Example (helper shape):**
```python
# Source: derived from verified Phase 2 contracts (swings.py D-01 close-time
# stamps; pools.py L252-275 bar-time event stamps; zones.py L162-175 lifecycle
# stamps; mtf.py D-15 strictly-before join); implementation detail
def visible_mask(df: pd.DataFrame, col: str, stamp_kind: str,
                 bar_t: pd.Timestamp, close_t: pd.Timestamp) -> pd.Series:
    """`stamp_kind`: 'close' (confirmed_at/created_at/activated_at) or
    'bar' (resolved_at/pierced_at/mitigated_at/invalidated_at)."""
    anchor = close_t if stamp_kind == "close" else bar_t
    return df[col].notna() & (df[col] <= anchor)  # NaT stamps (never happened) excluded
```

### Pattern 2: Forward-pass replay loop (not vectorized — project precedent)

**What:** One sequential loop over M15 bars per symbol; loop-local state = current open position (D-05), plus the as-of slices. This is the `pools.py`/`zones.py` explicit-sequential-loop style ("deliberately not vectorized"), which Phase 2 established as the pattern-of-record for event-sparse logic.

**What it looks like (per symbol, M15 frame, indexes i over bars):**
```python
# decision at CLOSE of bar S; entry at bar i = S+1 open (D-04)
# warmup: i < warmup_bars -> skip silently (D-07)
# D-05: if position_open: skip generation until resolved
if not position_open:
    cand = entry_rule(visible_state(bar_S), bars)   # pure (D-03)
    if cand and cand.rr >= cfg.min_rr:              # D-12
        position = open_position(cand, bars.iloc[i])  # fill at open + costs
for pos in active_positions:
    label = walk_barriers(pos, bars, i, i + cfg.time_barrier_bars - 1)  # Pattern 3
```

**When to use:** for the replay loop, the candidate rule, and the barrier walk. Vectorization is only appropriate for the stats/aggregation layer (Pattern 6).

### Pattern 3: Triple-barrier barrier walk (SL-first, gap=open, 96 bars inclusive)

**What:** For a position entered at bar E's open, evaluate bars E…E+95 (96 bars inclusive = 24h in detector-timeframe bars, per D-17 and the locked "detector-timeframe bars, not wall-clock" convention). Per bar, in order: (1) gap check on the bar's OPEN (D-11 — open beyond SL ⇒ exit at open, marked as LOSS; open beyond TP ⇒ exit at open, marked WIN), (2) SL check then TP check (D-10 — SL-first on ALL bars, entry bar included), (3) after E+95 with neither hit ⇒ TIMEOUT, exit at that bar's CLOSE (D-17).

**Tie-rule grounding (why SL-first is right, and why it can't be derived):** with only OHLC, the intrabar path is unknowable — both levels inside one bar is genuinely ambiguous (an MT5 M1-backtest article (FXNX, 2026-08) shows MT5 fabricating a deterministic Open→Low→High→Close path and, depending on entry timing, printing a phantom win). Conservative SL-first is corroborated as the "conservative priority" convention (MDPI paper) and matches pessimistic ordering in backtesting.py. The project's D-10 is the same convention — pin it with a named test that would FAIL if a "TP-first" or "close-direction" heuristic sneaks into the walk.

**Off-by-one that must be pinned by test:** window = entry bar E through bar E+95 ⇔ 96 bars ⇔ exactly `time_barrier_bars` bars including the entry bar; TIMEOUT bar = E+95. Tests must assert both the inclusive count and the TIMEOUT-at-close fill.

### Pattern 4: Cost model (D-14/D-15/D-16) — bid-side prices, points-to-price conversion

**What:** The bar frame is bid-side OHLC (MT5 rates). Two price-unit conversions are mandatory: **pip size** = 0.0001 (EURUSD, GBPUSD) / 0.01 (USDJPY) and **point size** = pip/10 for 5-digit quotes (EURUSD/GBPUSD point = 0.00001; USDJPY point = 0.001). The stored `spread` column is in **points** (verified in-repo: EURUSD M15 values 17–42 → 1.7–4.2 pips; GBPUSD weekend 101 → 10.1 pips — sane only under points semantics).

**Recommended fill convention (dir = long/short):**
```
entry  long:  bid_open + spread_px + slip_px      # cross the spread at entry, buy ask
entry  short: bid_open − slip_px                  # sell at bid, no spread at entry
exit   long:  level − slip_px                     # sell at bid (barrier hit on bid)
exit   short: level + spread_px + slip_px         # buy back at ask (+ spread)
where spread_px = (recorded_spread_points if >0 else cfg.default_spread_points) * point_size
      slip_px   = cfg.slippage_pips * pip_size
```
Net round-trip cost = spread (once) + 2×slippage, matching the standard "cost = spread + 2 slippage" convention [CITED: mql5.com pip article; cost convention verified across secondary sources]. Reports carry BOTH raw (spread only, no slippage) and net (D-16).

**D-15 fallback is the hot path in practice:** stored spread is 0 on 50% (GBPUSD) to 96–100% (EURUSD/USDJPY H1/H4) of rows — the per-symbol `default_spread_points` config key will be exercised by nearly every fill. Test both branches explicitly, including the unrealistic-but-legal "spread==0 with no default configured" path.

### Pattern 5: One-candidate state machine + warmup skip (D-05/D-07)

**What:** Per (symbol, timeframe): a single slot. While a position is open (until its label resolves), no new candidate is generated. Warmup length = max(ATR(14) NaN warmup, 2-bar fractal right side (≈2 bars), one completed zigzag leg (≈4+ swings), HTF lead-in bars for the as-of join) — candidates inside warmup are skipped silently, never errors. The state machine is loop-local (Pattern 2), not a store; the label-set remains the single source of truth for "what happened" (re-run ⇒ identical labels ⇒ same trades).

### Pattern 6: Canonical stats as pure functions with explicit edge guards

**What:** win rate = wins/trades (exclude TIMEOUT? no — D-18 counts WIN/LOSS/TIMEOUT as the three classes; define `wins = WIN`, `losses = LOSS`, timouts reported separately but INCLUDED in expectancy as 0-R? Recommendation: expectancy = mean signed R over ALL labeled trades (TIMEOUT R computed from cost-adjusted close exit; usually slightly negative or ~0); win rate = WIN/(WIN+LOSS) with TIMEOUT excluded from win-rate denominator (document, pin by test). Profit factor = Σgross_win_R / |Σloss_R| (use R-units; guard zero losses → report `inf` + flag; zero wins → 0). Max DD = min(cum_eq / cummax(cum_eq) − 1) over the per-trade cumulative R curve. Avg R = mean signed R; trade count per (symbol, TF). Everything computed twice: raw + net (D-16).

```python
# Source: derived from textbook definitions [ASSUMED]; verified guards
def profit_factor(r: pd.Series) -> float | float("inf"):
    wins = r[r > 0].sum(); losses = r[r < 0].sum()
    if losses == 0: return float("inf") if wins != 0 else float("nan")
    return wins / abs(losses)
def max_drawdown(r: pd.Series) -> float:          # R-curve (summed per trade)
    eq = r.cumsum(); return float((eq / eq.cummax() - 1).min()) if len(r) else 0.0
```

### Pattern 7: Walk-forward harness (D-19/D-20/D-21/D-22)

**What:** window derivation over the sorted label set (or over the bar index domain): `train = all entries before window start (expanding)`, `test = [w_start, w_start + test_len)`; slide test_len forward; strictly chronological; zero overlap (`w_start_{k+1} = w_end_k`); no shuffles. Defaults 6mo train / 1mo test (config); MUST support bar-count or short-day windows (2mo/2wk and below) because the current store cannot hold 6mo of M15. Labels are assigned to the window containing their **entry bar time**; each window gets canonical stats + an aggregate across symbols (D-22). Because labels span up to 24h, Phase 4 must purge train labels whose outcome interval overlaps a test window (AFML Ch. 7 purging/embargo) — Phase 3's harness must therefore persist `entry_time`, `exit_time` per label and expose a window → label-index mapping so Phase 4 can reuse it.

```python
# Source: sklearn TimeSeriesSplit semantics (expanding train, fixed test,
# chronological, no shuffles) [CITED: scikit-learn docs]
def walkforward_windows(boundaries: list[pd.Timestamp], train_len, test_len):
    """boundaries = timestamps at which windows start; yields (train_mask, test_window)."""
    for k in range(len(boundaries)):
        test = boundaries[k]
        train = [b for b in boundaries if b < test]
        yield train, test       # caller groups labels by entry_time
```

### Anti-Patterns to Avoid
- **Re-implementing detectors for speed:** "fast path" sweeps/zones logic destroys BT-01; the replay must literally import `detect_swings`, `build_zigzag`, `detect_pools`, `derive_zones`, `htf_context`. Verified-no-vendor-import test in Phase 2 extends naturally to `backtest/` (MT5-free).
- **Close-only barrier semantics (AFML default):** AFML labels on close-to-close returns and MISSES intrabar hits; D-10/D-11 explicitly require H/L intrabar detection. Do not "simplify" to AFML style.
- **Treating spread as pips or price:** it is POINTS; a missing/incorrect `point_size` silently shifts every cost by 10×.
- **One as-of filter for all tiers:** close-time vs bar-time stamps differ (Pattern 1 table); a single `<= t_S` filter on `confirmed_at` is wrong by one bar and will be caught only by the prefix-equivalence suite.
- **Wall-clock time barrier:** 96 bars across a weekend is NOT 24h of wall clock; barrier is bar-count (locked convention).
- **Global monotonic validation on multi-symbol frames:** Phase 2 validators are per-symbol; the replay loops per symbol — never concatenate before validating.
- **Storing labels non-atomically / overwriting determinism:** label + report writes follow the tmp + `os.replace` discipline; re-runs of the same range/config must produce identical artifacts (determinism test).
- **Silently falling back when the gate fails:** D-21 requires refusal with an actionable message; never an empty "0 trades" report masking insufficient history.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Detector chain (swings/pools/zones/MTF) | Any backtest-side detection logic | `ai_trading.detectors.*` — call the verified, repaint-tested pure functions | Second implementation = drifted rules = invalid labels; BT-01 is the phase's core constraint |
| Time/bar arithmetic (bar counts, 96-bar windows, TF minutes) | Duplicated constants | `normalize.TIMEFRAME_MINUTES` + `floor_to_timeframe` | Single source of truth (Phase 1 pattern #3) |
| Parquet artifact I/O | Custom serialization | `pandas.to_parquet` (zstd) + tmp/`os.replace` atomic write | Established `bar_store.merge_and_write` discipline; crash-safe |
| Triple-barrier/convention reasoning | A "generic backtest library" | Pure project functions implementing the LOCKED spec | Frameworks impose their own tie rules/fill semantics; the spec is project-specific and pinned |
| Stats formulas | Statistical suite dependencies | Pure pandas (5 formulas, ~30 lines) with edge guards | PF/expectancy/maxDD/avgR are elementary; dependencies add surface, not correctness |
| Walk-forward splits | A bespoke shuffling CV | Expanding/walk-forward window derivation (TimeSeriesSplit semantics) | Time-series splits must never shuffle (AI-04); the simple chronological form is the standard |

**Key insight:** the one thing that MUST NOT be hand-rolled is *detection*; everything else in this phase (fills, barriers, stats) is deliberately simple arithmetic over locked specs — simple enough that its correctness is provable by pinning tests, and its cost model is transparent to a human reviewing evidence (the project's core value).

## Common Pitfalls

### Pitfall 1: Intrabar tie "solution" that isn't (the D-10 trap)
**What goes wrong:** implementing the barrier walk so the tie between SL and TP in one bar is decided by close direction, open proximity, or "TP-first" — producing optimistic labels and inflated win rates.
**Why it happens:** with OHLC only the intrabar path is unknowable; MT5's own M1 tester uses a fabricated path (Open→Low→High→Close) that demonstrably produces phantom wins when the real sequence was SL-first. Any heuristic looks plausible.
**How to avoid:** hard-code the locked SL-first rule (D-10) as the ONLY branch; name the test `test_tie_sl_first_including_entry_bar` and make it fail if TP-first/close-direction logic is added; document in the code that the tie is a convention (conservative), never claim to know the path.
**Warning signs:** win rate jumps when you "fix" the tie; MT5 strategy tester results differ from engine labels on the same bars.

### Pitfall 2: Spread units — points, not pips, not price
**What goes wrong:** `spread` column (points) used directly as price units or as pips → costs 10× off (points) or 10× too small (pips vs price).
**Why it happens:** MT5 `MqlRates.spread` is documented in points; 5-digit quotes make 1 pip = 10 points. In-repo evidence: EURUSD M15 spread 17–42 → 1.7–4.2 pips (sane); GBPUSD weekend 101 → 10.1 pips (sane); if interpreted as price, 17 meaning 1.7 vs 0.0017 — visibly wrong.
**How to avoid:** single `costs.py` conversion: `points * point_size` where `point_size` is per-symbol config (or derived as `pip_size/10`); a Wave-0 sanity test asserts `spread_pips = points/10` in `[0.1, 10]` for the live symbols; NEVER render spread into the artifact without recording units.
**Warning signs:** avg R near zero on a "great" strategy; costs in reports that don't match broker statement spreads (IC Markets ~1 pip typical).

### Pitfall 3: The M15 history gate — current store FAILS D-21 today
**What goes wrong:** planner assumes the default run works; actually M15 stored history = 541 bars ≈ 9 days (verified: `data/bars/EURUSD_M15.parquet` 2026-08-21→08-31), H1 ≈ 29 days, H4 ≈ 115 days — M15 and H1 are BELOW the ~30-day gate. A default run refuses.
**Why it happens:** Phase 1 human chose 501 bars/combo as-is (01-VERIFICATION human item #2); terminal-available depth (250k M15 back to 2016) is persisted but not stored.
**How to avoid:** runner gate = explicit check with actionable message ("only X days stored for EURUSD M15; extend collection (purge+backfill, Phase 1 mechanism) or pass --min-history-days override"); unit tests use `make_bars`; plan a real-data run with the human deciding (deepen history vs override). Never produce an empty-trade report silently.
**Warning signs:** "0 trades" or refused runs in demo; gate exits code 1 with generic message.

### Pitfall 4: One as-of filter for heterogeneous timestamps
**What goes wrong:** using `confirmed_at <= t_S` (close-time rule) on `resolved_at` or `mitigated_at` (bar-time stamps) mis-orders by one bar; a sweep resolved at the close of bars ≤ S is excluded, or a zone mitigation at bar S is included when it should be visible only at close S.
**Why it happens:** Phase 2 stamps two semantic forms (Pattern 1 table) — swings/zones creation are close-time; events/lifecycle are bar-time.
**How to avoid:** one `asof.visible()` helper taking `(stamp_kind, bar_t, close_t)`; unit tests per tier; and the prefix-equivalence suite (Pitfall 5) as the catch-all.
**Warning signs:** off-by-one trades where an entry occurs one bar after the sweep resolves; MTF payload tests pass but replay trades look shifted.

### Pitfall 5: No replay-level look-ahead proof
**What goes wrong:** per-tier repaint tests exist (Phase 2) but nothing proves the REPLAY (candidate → entry → label) is prefix-stable; a bug in the slicer or state machine can leak future bars while all Phase 2 tests stay green.
**Why it happens:** the phase-2 suites assert detector output only; the replay adds state (one-open-position) and fills that no current test covers.
**How to avoid:** extend `assert_point_in_time_prefix_equality` convention: `replay(bars[:S+1])` trades ⊇... exactly == `replay(full)` trades with entry time ≤ close(S), `check_exact=True`, across 1-by-1 prefixes and chunked appends; plus a dedicated `test_no_future_bar_access` spot check (runner asserts it only reads indexes ≤ current).
**Warning signs:** label count or entry times change when trailing bars are appended.

### Pitfall 6: Barrier-window off-by-one and entry-bar inclusion
**What goes wrong:** 96 bars interpreted as "exit at close of bar E+96" (97 bars) or excluding the entry bar (95 bars) — TIMEOUTs and win rates shift.
**Why it happens:** "24h from entry" is ambiguous against "96 bars"; bars are 15 min so 24h = 96 bars INCLUDING the entry bar.
**How to avoid:** pin `window = bars[E : E + 96]` inclusive; test `test_timeout_after_exactly_96_bars` with an engineered never-touch scenario; config `time_barrier_bars=96` documented as inclusive count.
**Warning signs:** TIMEOUT count suspiciously high/low; tests using 97-bar windows pass buggy code.

### Pitfall 7: Walk-forward leakage / overlap / shuffle
**What goes wrong:** shuffled splits (AI-04 violation), overlapping windows (labels counted twice), or test windows before training windows.
**Why it happens:** copy-pasting standard `train_test_split` or naive k-fold habits.
**How to avoid:** window generator (Pattern 7) is the ONLY splitter; `test_no_overlap_between_consecutive_windows`, `test_expanding_train_strictly_before_test`, `test_labels_assigned_by_entry_time_once`; assert every label appears in exactly one window.
**Warning signs:** per-window stats sum ≠ canonical totals; date-sorted runs give different results than the same run repeated.

### Pitfall 8: Bid/ask direction asymmetry applied symmetrically
**What goes wrong:** adding spread to BOTH entry and exit for longs and shorts → double-charged spread, or skipping spread entirely for shorts.
**Why it happens:** bar prices are bid; the spread is crossed once per round-trip, but WHICH side pays depends on direction (long pays at entry=ask, short pays at exit=ask).
**How to avoid:** Pattern 4 fills are direction-aware; `test_long_short_cost_symmetry` asserts net R cost = spread + 2×slippage for both directions on identical bar paths.
**Warning signs:** cost delta in reports differs between raw and net by exactly 2×spread.

### Pitfall 9: Warmup mis-implemented as error or as zero-trade silent gap
**What goes wrong:** D-07 says warmup candidates are silently skipped (not errors) — but a bug can (a) raise ValueError on the first N bars, or (b) treat warmup as a stride (dropping detection e.g. only 1 candidate per N bars).
**Why it happens:** the chain produces no events for the first ~ATR(14)+fractal+leg bars; naive per-bar loops assume contiguous signals.
**How to avoid:** warmup threshold = explicit computed constant (e.g., `max(atr_period+2, 30)`-style with config knobs), skip silently, `test_warmup_produces_no_candidates_and_no_errors`, and assert a warmup-tolerant candidate is emitted at the first eligible bar after warmup.
**Warning signs:** first candidate appears suspiciously late; errors at range start.

### Pitfall 10: DST/offset mixing across the range (carried obligation)
**What goes wrong:** replay ranges spanning the US-DST flip (+3→+2 expected ~early Nov) mixing bars normalized under different offsets.
**Why it happens:** Phase 1 validation found uniform +3 on stored rows; Phase 2 deferred live re-validation to Phase 3 (02-VERIFICATION Deferred Items).
**How to avoid:** Phase 3's runner validates offset uniformity over the loaded range (like `assert_closed_bars` does for forming bars) and warns/refuses on mixed-offset rows; carry-forward task in plan 03-01 (live re-validation with the terminal is a human-assisted mt5-marked check — out of unit-test scope).
**Warning signs:** H4 21:00-UTC anchor discontinuity inside the range; `time − time_utc` not uniform.

### Pitfall 11: Report artifacts that are not deterministic or not atomic
**What goes wrong:** partial parquet files after a crash; per-run IDs or timestamps baked into label files break byte-identical re-runs, and Phase 4 caching by content hash gets confused.
**How to avoid:** tmp + `os.replace` for every artifact; run metadata in a separate manifest/JSON (run id, config hash, range); determinism test: same inputs ⇒ identical label parquet bytes; labels keyed by (symbol, entry_time) — idempotent overwrite on re-run.
**Warning signs:** `.tmp` residue in data dirs; re-running produces new files for the same range.

## Code Examples

### 1. Barrier walk core (SL-first + gap-open + inclusive 96-bar window)
```python
# Source: derived from locked D-10/D-11/D-17/D-18; structure patterned after
# the per-bar state-machine style of detectors/pools.py (verified in-repo)
from ai_trading.normalize import TIMEFRAME_MINUTES

def walk_barriers(pos, bars, entry_idx, time_barrier_bars=96):
    """Evaluate the window [entry_idx, entry_idx + time_barrier_bars).  Returns
    (outcome, exit_price, exit_idx).  Outcomes: 'WIN' | 'LOSS' | 'TIMEOUT'.
    SL-first on ALL bars incl. the entry bar (D-10); gap fills at open (D-11)."""
    t = bars.iloc[entry_idx]
    # D-11: entry bar itself may gap beyond a level
    if pos.direction == "long":
        if t["open"] <= pos.sl:  return "LOSS", t["open"], entry_idx   # gapped SL
        if t["open"] >= pos.tp:  return "WIN",  t["open"], entry_idx   # gapped TP
    else:
        if t["open"] >= pos.sl:  return "LOSS", t["open"], entry_idx
        if t["open"] <= pos.tp:  return "WIN",  t["open"], entry_idx
    for idx in range(entry_idx, min(entry_idx + time_barrier_bars, len(bars))):
        b = bars.iloc[idx]
        if pos.direction == "long":
            if b["low"]  <= pos.sl: return "LOSS", pos.sl, idx   # D-10 SL first
            if b["high"] >= pos.tp: return "WIN",  pos.tp, idx
        else:
            if b["high"] >= pos.sl: return "LOSS", pos.sl, idx
            if b["low"]  <= pos.tp: return "WIN",  pos.tp, idx
    last = bars.iloc[min(entry_idx + time_barrier_bars, len(bars)) - 1]
    return "TIMEOUT", last["close"], min(entry_idx + time_barrier_bars, len(bars)) - 1  # D-17 (bar E+95 close)
```

### 2. Fill prices with spread (points→price) + slippage (D-14/D-15)
```python
# Source: derived from locked D-14/D-15 + MQL5 pip/point conventions
# [CITED: mql5.com articles — pip_size 0.0001 / 0.01 (JPY)]
PIP = {"EURUSD": 0.0001, "GBPUSD": 0.0001, "USDJPY": 0.01}

def fill_prices(side, bar_open, sl_level_or_none, spread_points, cfg):
    point = PIP[cfg.symbol] / 10                # 5-digit point (USDJPY 0.001)
    spread_px = (spread_points if spread_points > 0 else cfg.default_spread_points) * point  # D-15
    slip = cfg.slippage_pips * PIP[cfg.symbol]  # D-14 fixed pips, both fills
    if side == "long":
        return bar_open + spread_px + slip      # entry at ask + slip
    return bar_open - slip                      # short entry at bid - slip
# exit longs sell at bid: level - slip; exit shorts buy at ask: level + spread_px + slip
```

### 3. Canonical stats with edge guards (BT-04)
```python
# Source: derived from textbook definitions [ASSUMED: standard formulas];
# guards reflect documented edge-case policy
def canonical_stats(r: pd.Series, wins: int, losses: int, timeouts: int) -> dict:
    n = len(r)
    return {
        "trades": n, "wins": wins, "losses": losses, "timeouts": timeouts,
        "win_rate": wins / (wins + losses) if (wins + losses) else float("nan"),
        "profit_factor": (r[r > 0].sum() / abs(r[r < 0].sum()))
                         if (r < 0).any() else float("inf"),
        "expectancy": float(r.mean()) if n else float("nan"),   # signed R, incl. TIMEOUTs
        "avg_r": float(r.mean()) if n else float("nan"),
        "max_dd": _max_drawdown(r),                             # R-equity curve
    }
```

### 4. Walk-forward windows (expanding train, rolling test — AI-04)
```python
# Source: sklearn TimeSeriesSplit semantics [CITED: scikit-learn time series split docs]
def build_windows(label_times: pd.Series, train_len, test_len):
    """Chronological, non-overlapping, expanding-train windows over label entry
    times. `train_len`/`test_len` accept days or bar counts (D-20 small windows)."""
    times = label_times.sort_values().unique()
    idx = 0
    while idx + test_len <= len(times):
        test_start, test_end = times[idx], times[idx + test_len - 1]
        train = [t for t in times if t < test_start]            # expanding, strictly before
        yield train, (test_start, test_end)
        idx += test_len                                         # no overlap (D-19)
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| AFML triple-barrier on close-to-close returns (2018) | Intrabar H/L detection with explicit SL-first tie + gap-open fills | post-AFML practice; MT5 M1 tester uses fabricated 4-point paths (FXNX 2026) | The project's D-10/D-11 are the tighter, deterministic, conservative variant; AFML is reference-only and would UNDER-detect intrabar hits |
| Generic backtest frameworks (backtesting.py, vectorbt) as the engine | Project-owned sequential replay over verified pure detectors | Phase 2's purity made BYO viable; BT-01 (same code path) forbids a framework's second fill engine | Zero new deps; verification concentrates on the as-of slicer + state machine |
| Whole-run label recalc every time | Deterministic label artifacts (Parquet keyed by symbol+entry_time) with atomic writes; optional caching | established data discipline (bar_store) applied to labels | Phase 4 can hash/version; re-runs byte-identical |
| M5/M15 spread as a constant | Recorded per-bar spread (points) + per-symbol default fallback (D-15) | MT5 rates carry per-bar spread; aggregation zeros make fallback mandatory | Costs reflect actual liquidity at the fill bar (with fallback where artifacts) |

**Deprecated/outdated:**
- `mlfinlab` free PyPI package: removed from PyPI (seam `SLOP` — does not exist); afml code snippets are stubbed in the public repo. Use the AFML book or autodocs for CONCEPTS only; never plan an install.
- Installing `backtesting.py`: PyPI name is `backtesting`; the `.py` name does not exist. Not recommended regardless (BT-01).

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Bar OHLC prices are bid-side (MT5 default rates), so long pays spread at entry and short pays at exit | Pattern 4 | Medium — flips cost asymmetry by one spread; cost-delta tests + Wave-0 live spot check (terminal spread vs stored row) resolve it |
| A2 | MT5 `spread` column is in POINTS (5-digit: 1 point = pip/10) | Pattern 4, Pitfall 2 | High — 10× cost error; mitigated: in-repo empirical check (EURUSD 17–42, GBPUSD 101) fits points semantics; still pin a named unit test + Wave-0 broker check |
| A3 | pip size = 0.0001 (EURUSD/GBPUSD) / 0.01 (USDJPY) — no per-instrument digit anomalies at this broker | Pattern 4 | Low — IC Markets majors are standard 5-digit/3-digit; symbol_info.point could later replace config |
| A4 | Win-rate denominator treats TIMEOUTs as NOT wins/losses: suggested convention `win_rate = wins / (wins + losses)`, TIMEOUT share reported separately, TIMEOUTs included in expectancy/avg R (usually ≈ 0/negative outcomes) | Pattern 6, Pitfall 6 | Medium — the definition affects every reported win rate; planner must pin it explicitly and consistently in all reports (canonical + per-window) |
| A5 | Expectancy/avg R include TIMEOUT trades (exit at last-bar close, R usually ≈ 0/slightly negative) | Pattern 6 | Low — reasonable; pinned by test |
| A6 | Walk-forward "train" windows are unused by Phase 3 (no model yet); Phase 3 reports stats PER WINDOW and exposes the split for Phase 4 | Pattern 7 | Low — D-19 wording assumes a model; Phase 4 will consume the same harness |
| A7 | SL-first tie convention matches the industry-standard conservative bias | Pattern 3 | Low — D-10 locked; external corroboration is secondary |
| A8 | HTF lead-in (warmup) must load HTF bars BEFORE the range start (zones need confirmed legs before the first decision bar) | Pattern 1, D-07 | Medium — if omitted, the first ~1-5 days of labels lack bias context; loaded with `start − htf_warmup_days` |
| A9 | `point_size` derived as `pip_size/10` holds for the three majors (5-digit/3-digit) | Pattern 4 | Low — same as A3 |
| A10 | Stats artifacts: labels Parquet + JSON canon + walk-forward Parquet is the recommended format; exact layout is planner discretion per CONTEXT | Pattern 6/7 | Low |

## Open Questions

1. **M15 stored history is below the D-21 gate (~9 days vs 30 required) — run what?**
   - What we know: data audit this session: M15 501–541 bars (2026-08-21→08-31), H1 501 (≈29 d), H4 501 (≈115 d); terminal-available 250k M15 bars back to 2016 persisted in `history_bounds`; Phase 1 recorded the sanctioned mechanism (purge data/ + restart backfill under confirmed offset) and a human decision to stay at 501 bars/combo.
   - What's unclear: whether the human wants the history deepened now (real 6mo/1mo walks) or runs on short windows/overrides.
   - Recommendation: plan a `checkpoint:human-verify` for the demo run; defaults stay per D-21; runner supports `--min-history-days` override; all logic verified on synthetic data.

2. **Cost asymmetry convention (which side crosses the spread) — confirm.**
   - What we know: Pattern 4 (long pays at entry, short at exit) is the standard interpretation of bid-side bars; D-14/15/16 lock the rest.
   - What's unclear: whether the user's mental model charges spread on both entry and exit (some systems model "spread = cost per side").
   - Recommendation: land the asymmetric convention with a named symmetry test; flag in plan for a 10-second human confirm at verification.

3. **Win-rate denominator (TIMEOUT inclusion).**
   - What we know: D-18 defines three classes; D-16 wants raw/net; A4 recommends wins/(wins+losses).
   - What's unclear: no locked decision on the denominator.
   - Recommendation: pin `timeouts_excluded_from_win_rate=True` in config docs + tests; show TIMEOUT share separately in every report.

4. **Where do PD zones for the candidate come from (M15 zones only, or HTF zones as well)?**
   - What we know: D-06 = M15 candidate generation; D-01 = "a PD zone"; Phase 2 produces M15 zones AND HTF zones.
   - What's unclear: CONTEXT leaves the entry-rule's exact inputs to the planner (candidate functions are discretionary in composition, D-03 locked).
   - Recommendation: M15 zones for the tap (execution-timeframe structure) + H1/H4 zone containment via the payload (D-14 ids) as bias corroboration; the entry-rule function signature should accept the full as-of state so Phase 6 can match it exactly.

5. **Phase-4 label overlap/purge contract.**
   - What we know: labels span up to 96 bars (24h); train/test boundaries can cut through a label's life.
   - What's unclear: Phase 3 has no model, so purging is deferred; the harness should still persist entry/exit stamps (Pattern 7).
   - Recommendation: persist `entry_time`, `exit_time`, `outcome`, `R_raw`, `R_net` per label + window assignment map; document the Phase-4 purge obligation (AFML Ch. 7) as a deferred item.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|-------------|-----------|---------|----------|
| uv | test/lint/runtime env | ✓ | 0.11.28 | — |
| Python 3.12 (uv-managed) | all code | ✓ (uv run; system py is 3.10.10 — use `uv run` only) | 3.12.x | uv fetches managed CPython |
| pandas / pyarrow / numpy | all plans | ✓ (locked stack installed) | pandas ≥3.0,<4; pyarrow ≥25 | — |
| pytest | tests | ✓ | 9.1.1 (dev group) | — |
| ruff | lint | ✓ | ≥0.16.5 | — |
| git | commits | ✓ | repo | — |
| MT5 terminal | NOT required by the backtester (MT5-free: `read_bars` from Parquet) | n/a | — | — |
| MT5 terminal | Optional: deepening stored history to pass D-21 on M15; live offset re-validation (carried Phase 2 obligation) | not running (per Phase 1 record); human prerequisite | — | gate override; synthetic-data tests; H4-only runs (115 d) |

**Current data inventory (verified this session via `uv run python` over `data/bars/*.parquet`):**
- 9 files, 501–541 rows each; M15 ≈ 9 days (2026-08-21→08-31), H1 ≈ 29 days, H4 ≈ 115 days.
- `spread` column: 0 on ~50% (GBPUSD) and ~92–100% (EURUSD/USDJPY) of rows → D-15 fallback is the dominant path.
- Stored rows are offset-uniform (Phase 1 verified); no re-verify needed for unit work, but runner should assert uniformity over loaded ranges (Pitfall 10).

**Missing dependencies with no fallback:** none (all code paths are MT5-free; the optional terminal-dependent steps are documented as human-assisted, mt5-marked, out of the unit gate).
**Missing dependencies with fallback:** M15-depth for D-21 default runs (fallback: `--min-history-days` override + synthetic-data tests + H4-range demo).

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.1.1 (existing, via uv dev group) |
| Config file | `pyproject.toml` — markers `unit`/`mt5`, default `-m "not mt5"` (no changes expected; backtester is unit-only, no mt5 tests needed) |
| Quick run command | `uv run pytest tests/unit -q` (~<30 s; currently 174 collected) |
| Full suite command | `uv run pytest -q` (unit; MT5-free) / `uv run pytest -q -m "unit or mt5"` with terminal |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| BT-01 | Replay calls the same detectors (file-content imports, no re-implementation); prefix-equivalence: `replay(bars[:S+1])` == visible subset of `replay(full)` | unit | `uv run pytest tests/unit/test_replay_repaint.py tests/unit/test_asof.py -q` | ❌ Wave 0 |
| BT-02 | Spread points→price conversion; default-spread fallback when `spread==0`; slippage on both fills; raw vs net delta; long/short cost symmetry | unit | `uv run pytest tests/unit/test_costs.py -q` | ❌ Wave 0 |
| BT-03 | SL-first tie on entry bar + all bars (test fails on TP-first); gap-open fills both directions; 96-bar inclusive window; TIMEOUT at final bar close; min-R:R discard | unit | `uv run pytest tests/unit/test_barriers.py tests/unit/test_candidates.py -q` | ❌ Wave 0 |
| BT-04 | Win rate / PF (inf guard) / expectancy / max DD / avg R / counts per (symbol, TF); raw + net variants; empty & all-win & all-loss edge cases | unit | `uv run pytest tests/unit/test_stats.py -q` | ❌ Wave 0 |
| BT-05 | Walk-forward: chronological, non-overlapping, expanding train strictly before test; small windows (days+bars); per-window = canonical stats + cross-symbol aggregate; label assigned to exactly one window | unit | `uv run pytest tests/unit/test_walkforward.py -q` | ❌ Wave 0 |
| Config | New backtest keys validated fail-fast (positive floats, bounds); history gate refuses < min_history_days with actionable message | unit | `uv run pytest tests/unit/test_backtest_config.py -q` (extend `test_normalize_and_config.py` style) | ❌ Wave 0 |
| Repaint/look-ahead | 1-by-1 + chunked prefix equivalence over candidate→entry→label; no-future-access assertions | unit | `uv run pytest tests/unit/test_replay_repaint.py -q` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/unit -q`
- **Per wave merge:** full `uv run pytest -q` (all unit)
- **Phase gate:** full suite green + one real-data backtest demo (history depth decision per Open Question 1) before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] New `tests/unit/test_*` modules listed above (8 modules; all new — Phase 3 is the first code that consumes detector output as a service)
- [ ] `tests/unit/_detector_fixtures.py` — likely needs one addition (spread-rich bar sculptors: `make_bars` emits `spread=list(range(count))` — zeros at bar 0 and low values; label tests need controllable spread bars; extend via a local helper in the new test modules or a new `_backtest_fixtures.py` — DO NOT mutate conftest per Phase 1 contract)
- [ ] `src/ai_trading/backtest/__init__.py` package marker
- [ ] Config keys added to `config.py` frozen dataclass + `_REQUIRED_KEYS` (backtest knobs) — follow the existing field-validation pattern (`config.py` L14–45, `_validate` L114–160)
- Existing infrastructure covers: frame factories (`make_bars`), CLI pattern (`history_report.py`), atomic-write discipline (Pattern 3), frozen-Config validation. No new framework needed.

## Security Domain

> `security_enforcement: true` (config.json), ASVS level 1, block-on high.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | N/A — no credentials in the backtester (MT5-free by design; terminal path/config stay in the adapter tier) |
| V3 Session Management | no | N/A |
| V4 Access Control | partial | Config-driven paths only; report paths validated under `data/` root (no arbitrary path injection); no web surface in this phase |
| V5 Input Validation | yes | Frozen `Config` dataclass validation for new keys (positive floats, sensible bounds, per-symbol pip/spread maps); detector-chain inputs validated by Phase 2 validators (reused) |
| V6 Cryptography | no | N/A — never hand-roll crypto |
| V7 Errors & Logging | yes | Actionable error messages (history-gate refusal, range validation); no secrets/path dumps; runner exit codes mirror `history_report` (2 config / 1 runtime) |
| V14 Config | yes | New backtest knobs in committed `config.toml` (no secrets); `data/labels|reports` under gitignored `data/` (already ignored per Phase 1) |

### Known Threat Patterns for {pandas replay + stats stack}

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Look-ahead / future-data leakage in labels (the phase's #1 integrity risk) | Tampering (integrity of evidence) | As-of slicer as the single choke point + prefix-equivalence repaint suite (Pattern 1, Pitfall 5); detector chain itself already repaint-proven (Phase 2) |
| Silent data gaps → empty/biased reports | Denial of Service (of the evidence) | D-21 history gate refuses below minimum with actionable message; never emit empty-trade reports as "success" |
| Report/label file corruption (partial writes, crashes) | Tampering | tmp + `os.replace` atomic writes; determinism test (same inputs ⇒ byte-identical artifacts) |
| Config-driven path traversal for report output | Elevation | Validate report paths resolve under `data/`; no user-supplied input surfaces exist |
| Cross-symbol contamination in stats/walk-forward | Tampering | Per-symbol grouping everywhere; per-symbol validators (Phase 2) + per-symbol grouping in stats/wf (Patterns 6/7) |

## Sources

### Primary (HIGH confidence)
- Locked decisions 03-CONTEXT.md D-01…D-22 (the spec itself — highest authority) [VERIFIED: project artifact]
- Phase 2 contracts + verification: 02-CONTEXT.md (D-01…D-15), 02-VERIFICATION.md (30/30 truths incl. per-tier repaint guarantees, timestamp semantics of pools.py L252–275 / zones.py L162–175 / swings.py L87–89 / mtf.py D-15) [VERIFIED: project artifacts + source read]
- Source read this session: `src/ai_trading/detectors/{swings,zigzag,pools,zones,mtf,atr}.py`, `normalize.py`, `stores/bar_store.py`, `config.py`, `history_report.py` (CLI pattern), `tests/conftest.py` (make_bars/FakeMT5Client), `tests/unit/_detector_fixtures.py` (prefix-equality machinery), `test_repaint.py`, `test_detector_integration.py` [VERIFIED: in-repo]
- Data audit this session: all 9 `data/bars/*.parquet` — row counts, ranges, spread zero-fractions and value distributions; `history_bounds`/collection state referenced via Phase 1 verification [VERIFIED: local execution]
- Context7 `/hudson-and-thames/mlfinlab` autodocs — `get_events`, `add_vertical_barrier`, `PurgedKFold` (purging/embargo) [CITED: Context7 docs]
- Context7 `/kernc/backtesting.py` — next-candle-open execution documented (matches D-04) [CITED: Context7 docs]

### Secondary (MEDIUM confidence)
- MDPI paper (2571-9394/8/3/40) — "conservative priority used in label generation (stop-loss checked first)" [CITED: mdpi.com]
- FXNX article (2026-08-23) — MT5 M1 OHLC synthetic path Open→Low→High→Close; phantom-win fabrication; intra-bar execution dilemma [CITED: fxnx.com]
- backtesting.py source (github.com/kernc/backtesting.py `_process_orders`) — pessimistic same-bar stop/limit ordering [CITED: GitHub source]
- MQL5 pip conventions article (pip size 0.01 JPY / 0.0001 others) [CITED: mql5.com]
- SearXNG results: walk-forward expanding-window standard (multiple sources), r/algotrading OHLC ambiguity thread [CITED: web]

### Tertiary (LOW confidence)
- AFML book Snippet 3.2 internals (close-only barrier application, exact first-index tie handling) — the public mlfinlab repo now stubs these (`pass`); used for concepts only [ASSUMED]
- Quant conventions on TIMEOUT counting, expectancy inclusion — textbook, pinned by project tests instead [ASSUMED]

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — zero new packages; existing locked stack verified in-repo this session (phases' own versions pinned and installed)
- Architecture (chain-once + as-of slicer): HIGH — derived from verified Phase 2 timestamp/repaint contracts and the tier-3 immutability guarantees; the heterogeneous-stamp table is source-verified
- Cost model: MEDIUM-HIGH — spread-in-points empirically verified from stored data; bid-side + spread-once convention is the industry-standard [CITED secondary]; directional asymmetry worth a human eyeball
- Labels/stats: HIGH for the locked rules; MEDIUM for the TIMEOUT-denominator and cost-asymmetry choices (flagged assumptions A1/A4)
- Pitfalls/verification: HIGH — phase-2 test convention reuse is prescriptive; data-reality findings are session-verified

**Research date:** 2026-09-01
**Valid until:** 2026-10-01 (stack stable — no new deps; the risk is data drift, e.g., US-DST offset flip ~early Nov, not library movement)


