# Phase 3: Backtesting & Labeling - Context

**Gathered:** 2026-09-01
**Status:** Ready for planning

<domain>
## Phase Boundary

A bar-by-bar replay engine that runs the IDENTICAL SMC detector pipeline (Phase 2) over stored MT5 history: it generates entry candidates from sweep+zone SMC signals, models costs (recorded bar spread + slippage buffer), labels every trade with triple-barrier outcomes, and reports canonical + walk-forward statistics per symbol/timeframe. Scope covers BT-01…BT-05 only: one shared code path (BT-01), cost modeling (BT-02), triple-barrier labels (BT-03), canonical stats (BT-04), walk-forward reports (BT-05). The entry-candidate rule is OWNED by this phase as pure functions — Phase 6 setup assembly reuses them. No ML (Phase 4), no LLM (Phase 5), no UI, no order execution.

</domain>

<decisions>
## Implementation Decisions

### Entry Candidate Definition
- **D-01:** A labeled trade = **sweep + zone tap**: a sweep event (take-out + reclaim, SMC-03) followed by price returning into a PD zone on the right side (discount for longs, premium for shorts) and mitigating it (SMC-05). Sweep-only and zone-only candidates are NOT labeled.
- **D-02:** **Respect HTF bias**: a candidate is only labeled when the H1/H4 bias (D-13: premium→bearish, discount→bullish, via the lean MTF payload D-14) agrees with trade direction. Bias is recorded on the label regardless.
- **D-03:** The entry-candidate spec is **defined once in this phase** as pure functions; Phase 6 setup assembly uses the exact same functions (no parallel rule definitions). BT-01 spirit: whatever live analysis does, the backtester replays.
- **D-04:** Entry fill = **next-bar open** (signal detected at M15 close; entry at the next M15 bar's open). No intrabar/limit fills in v1.
- **D-05:** **One at a time**: per (symbol, timeframe), a new candidate is suppressed until the current one resolves (TP/SL/timeout). No concurrent candidates on the same symbol/TF.
- **D-06:** Candidates are generated on **M15 only** (execution timeframe); H1/H4 supply bias context only — no HTF candidate generation.
- **D-07:** **Auto warmup, skip**: the first N bars (ATR(14) + fractal confirmation + one completed zigzag leg + HTF history for as-of join) are warmup; candidates within warmup are silently skipped, not errors.

### SL/TP Placement Rules
- **D-08:** SL is **structural, raw**: beyond the swept pool level / the zone's far boundary, with no buffer. No ATR buffer at the SL.
- **D-09:** TP is **structural**: the far side of the PD zone, or the opposite liquidity pool / prior confirmed swing level. R:R varies per trade (no fixed R:R, no hard cap).
- **D-10:** Intrabar tie rule = **SL-first, ALL bars** (entry bar included): if SL and TP are both touched within one bar, label SL-first. Matches BT-03's documented conservative default.
- **D-11:** Gap handling: if a bar **opens beyond the SL level**, the exit fills at the bar's **OPEN price** (marked SL). Same rule for gapped TP: fill at open. No ignore-gaps mode.
- **D-12:** **Discard below min R:R**: candidates whose structural SL/TP distance yields R:R below a minimum (default 1.0, configurable) are discarded from the label set.
- **D-13:** SL/TP price levels are **raw detector outputs** (zone boundaries / pool levels), used as-is; no freeze-at-confirmation re-derivation in v1.

### Cost Model (BT-02)
- **D-14:** Slippage buffer = **fixed pips per symbol** (default 0.5 pip, per-symbol override in config). Charged on BOTH entry and exit fills (worse for entry, worse for exit).
- **D-15:** Spread = **recorded per-bar spread** (normalize.py `COLUMNS.spread`) at the fill bar; when a bar's spread is 0/absent (HTF/M1 aggregation artifacts), fall back to a per-symbol default spread from config.
- **D-16:** Reports show **both raw (spread-only) and net (spread + slippage)** metrics, with the cost delta visible.

### Triple-Barrier Labels + Walk-Forward (BT-03/04/05)
- **D-17:** Time barrier = **96 M15 bars (24h)**. If neither barrier is hit within the window, the label is TIMEOUT (exit at final bar close). Configurable default 96.
- **D-18:** Outcome classes = **WIN (TP hit) / LOSS (SL hit) / TIMEOUT**; no extra sub-flags in v1.
- **D-19:** Walk-forward split = **expanding train + rolling test**: training window expands monotonically, fixed-length test windows slide forward, strictly chronological, NO overlap, NO shuffled splits (AI-04).
- **D-20:** Default window sizes = **6 months train / 1 month test** (configurable). The harness must also support shorter windows (e.g., 2mo/2wk) given ~90 days of currently stored history.
- **D-21:** History gate (SC2) = **~30 days minimum** stored history per symbol/timeframe before a run is allowed; refuse with an actionable message below that.
- **D-22:** Walk-forward reports = **full canonical stats per (symbol, timeframe) AND per window**, plus a per-window aggregate across symbols (BT-05).

### the agent's Discretion
- Exact report artifact format (JSON/Parquet/markdown) and on-disk layout under `data/` or `config` — planner decides
- Label store schema/table design (Parquet/SQLite) and whether labels are recomputed or cached per run
- Replay engine implementation approach (vectorized vs per-bar loop) and how detector functions are invoked bar-by-bar
- CLV/tick-level refinement beyond open-based fills; intrabar path assumptions (only open/high/low/close are used)
- Where the entry-rule pure functions live (module layout under `src/ai_trading/`)
- How the backtest runner is invoked (CLI flags, config sections) — follows Phase 1/2 config-dataclass discipline

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Locked scope + goals
- `.planning/ROADMAP.md` — Phase 3 goal, success criteria SC1–4, plan breakdown 03-01…03-03
- `.planning/REQUIREMENTS.md` — BT-01…BT-05 definitions; AI-04 (walk-forward, no shuffled splits); Out of Scope table
- `.planning/PROJECT.md` — core value, constraints: one shared look-ahead-safe code path for live AND backtest (non-negotiable); hybrid AI separation; backtesting mandatory before trusting live signals

### Phase 2 contracts (what gets replayed)
- `.planning/phases/02-smc-detection-engine/02-CONTEXT.md` — D-01…D-15 (swings/windows, pools/sweeps, zone lifecycle, D-12 full history retention, D-13/D-14 bias + lean MTF payload, D-15 confirmation-time as-of rule) — entry candidates consume these contracts
- `.planning/phases/02-smc-detection-engine/02-VERIFICATION.md` — verified detector chain: pure/deterministic/schema-locked, confirmation-shifted (repaint-safe); the replay engine must preserve these guarantees
- `.planning/phases/01-data-foundation/01-RESEARCH.md` — MT5 time semantics (server wall time + validated offset), closed-bars invariant, pandas 3.x realities
- `.planning/phases/01-data-foundation/01-VERIFICATION.md` — verified Phase 1 contract: `start_pos=1` closed-bar invariant, `time − time_utc == validated offset`, store invariants, `read_bars` empty-frame contract
- `.planning/phases/01-data-foundation/01-PATTERNS.md` — pattern-of-record conventions for new modules (copy-from sources, shared patterns §1–§7)

### Code (integration surface)
- `src/ai_trading/normalize.py` — `COLUMNS` (incl. `spread` used by D-15), `TIMEFRAME_MINUTES` (bar-count math for the 96-bar/24h barrier), `floor_to_timeframe`
- `src/ai_trading/stores/bar_store.py` — `read_bars` as the replay input path (COLUMNS-ordered frames, empty-frame contract)
- `src/ai_trading/detectors/` — `swings.py`, `zigzag.py`, `pools.py`, `zones.py`, `mtf.py`, `atr.py`; `detectors/__init__.py` (bare marker — import submodules directly). The replay engine calls these identical functions (BT-01)
- `src/ai_trading/collector.py` — point-in-time discipline reference (closed bars only, trim-before-merge)
- `src/ai_trading/config.py` — frozen `Config` dataclass + fail-fast validation pattern for the new backtest config keys (slippage, spread defaults, window sizes, min R:R, history gate)
- `tests/conftest.py` — `make_bars` synthetic bar factory + FakeMT5Client (fixture reuse for replay/label unit tests)
- `tests/unit/_detector_fixtures.py` — shared detector fixture helpers used by Phase 2 suites

### Test conventions
- `.planning/phases/01-data-foundation/01-VALIDATION.md` — Nyquist verification map; pytest `unit`/`mt5` marker layering to mirror
- `.planning/phases/02-smc-detection-engine/02-*` suites (`test_repaint.py`, `test_sweeps.py`, `test_zones.py`, `test_mtf_join.py`, `test_lifecycle.py`) — conventions for look-ahead-safety tests the backtester must extend

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `normalize.py` `COLUMNS` gives the bar frame with `spread` available at every fill bar (D-15 source)
- `detectors/*` pure DataFrame→DataFrame functions — the replay engine literally re-invokes them per bar window; no backtest-specific rewrite
- `bar_store.read_bars` — returns COLUMNS-ordered frames per (symbol, timeframe); suffices as the replay data source (no MT5 dependency in the backtester)
- `make_bars` + `_detector_fixtures.py` — synthetic bar factories with configurable spread/offset for deterministic label tests
- Frozen `Config` dataclass + `_validate` (config.py) — extend with backtest knobs (slippage_pips, default_spread_pips, min_rr, warmup, time_barrier_bars, wf_train_days, wf_test_days, min_history_days) without inventing a new pattern

### Established Patterns
- Pure functions, zero vendor imports outside the adapter tier (replay engine must stay MT5-free; `mt5` pytest marker for live-only)
- Point-in-time discipline: confirmation-time as-of joins (D-15) — the replay engine must not access future bars for candidate generation OR label evaluation
- Pytest markers `unit` (default) / `mt5`; ruff line-length 100; config-driven parameters
- Parquet + SQLite store layering with atomic writes (bar_store `merge_and_write` discipline)

### Integration Points
- **Phase 4 ML**: consumes the labeled trades (WIN/LOSS/TIMEOUT + features assembled point-in-time); reuses the same walk-forward harness (expanding train/rolling test)
- **Phase 6 Setups**: setup assembly imports the exact entry-candidate pure functions (D-03) so live setups match backtest labels
- **Phase 6 Dashboard**: stats panel consumes the canonical + per-window report artifacts

</code_context>

<specifics>
## Specific Ideas

- Time barrier is measured in **detector-timeframe bars** (96 × M15 = 24h), not wall-clock — consistent with the sweep-window convention from Phase 2
- DST caveat carries forward: broker offset +3 (US summer) / +2 after early November; H4 anchor shifts — backtest ranges must not mix offsets; Phase 1's tz/DST test conventions apply
- The "one shared code path" is most at risk in plan 03-01: the replay engine must call the SAME exported detector functions, not re-implement sweeps/zones to be faster
- History is currently ~90 days per symbol/TF — walk-forward harness must be usable with shorter windows NOW (D-20), not just at 6mo/1mo defaults

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope. (Cost-sensitivity table over slippage 0/0.5/1.0 pip was offered as an option and not selected; a natural candidate for a later enhancement if cost robustness becomes a concern.)

</deferred>

---

*Phase: 3-Backtesting & Labeling*
*Context gathered: 2026-09-01*
