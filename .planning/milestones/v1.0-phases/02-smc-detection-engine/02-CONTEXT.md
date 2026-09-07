# Phase 2: SMC Detection Engine - Context

**Gathered:** 2026-08-30
**Status:** Ready for planning

<domain>
## Phase Boundary

Pure, point-in-time SMC detectors over the Phase 1 bar store: confirmation-shifted swing detection, liquidity pools from equal highs/lows, sweep events (take-out + reclaim), premium/discount zones with bar-by-bar lifecycle state, and point-in-time H1/H4 context joined to each M15 decision bar. All detectors are pure DataFrame→DataFrame functions with pytest coverage (ROADMAP SC1–5). Scope covers SMC-01…06 only — swing structure is an internal dependency (not a user-facing feature), and order blocks / FVG / BOS-CHoCH as first-class labeled features are excluded (BOS/CHoCH appear solely as structure-shift labels in the repaint tests).

</domain>

<decisions>
## Implementation Decisions

### Swing Detection (SMC-01)
- **D-01:** Swing window is a **2/2 fractal** (5-bar fractal): a swing high requires a bar whose high is exceeded by no neighbor within 2 bars on each side (mirror for lows). The swing is stamped at its extreme bar but only becomes visible/confirmed on the close of the 2nd right-side bar (`confirmed_at` = that confirmation bar's close time).
- **D-02:** **Strict comparisons** — exactly-equal prices do NOT form swings. Equal highs/lows are not double-labeled as structure; the equal level itself surfaces as a liquidity pool (feeds SMC-02). Lowercase rule: swing high needs strict `>` against all 4 neighbors; `>=` never qualifies.
- **D-03:** Swing records are **minimal**: `(symbol, timeframe, bar_time, price, side, confirmed_at)`. No derived strength/prominence metrics — downstream consumers compute what they need from raw bars around the swing.
- **D-04:** Confirmed swings are sequenced into an **alternating zigzag** as the canonical structure: a newly confirmed same-side swing REPLACES the previous same-side extreme if it is more extreme (classic zigzag). PD-zone ranges and the structure-shift (BOS/CHoCH) labeling in repaint tests consume the zigzag, never the raw swing list.

### Liquidity Pools + Sweeps (SMC-02/03)
- **D-05:** Pool clustering tolerance = **0.1 × ATR(14)** computed on the detector's own timeframe (per instrument, per timeframe). Swing highs/lows whose prices fall within tolerance cluster to one pool level.
- **D-06:** **2 touches** (the clustered swing extremes themselves) form an active pool.
- **D-07:** **Sweep rule:** a bar's wick pierces the pool level AND price closes back on the original side of the level within **2 bars** (detector-timeframe bars, inclusive window) → sweep event. If no close-back occurs within the window → the event is reclassified as a plain breakout and the pool is broken.
- **D-08:** Pools are **one-and-done**: a swept pool's lifecycle ends as `swept` (reclaimed) or `broken` (reclassified breakout). New equal-level clusters form new pools; no re-sweeping of a spent level.

### Premium/Discount Zones + Lifecycle (SMC-04/05)
- **D-09:** Zone range = **each completed zigzag leg**: one confirmed low→high leg (or high→low) defines one range. Premium = upper 50% of the range, discount = lower 50%; the equilibrium (50%) value is carried on the zone record.
- **D-10:** Mitigation trigger = **wick touch**: price trading into the zone (wick reaching the near boundary) transitions the zone to `mitigated`. Closes are not required for mitigation.
- **D-11:** Invalidation trigger = **close beyond the far boundary** of the zone's range (close above premium top or below discount bottom). Wick pokes beyond the boundary do NOT invalidate; only committed closes do.
- **D-12:** **Track all zones** concurrently — every completed leg spawns a zone that lives until its lifecycle resolves. Zone records carry: range high/low, equilibrium, direction (premium/discount orientation of the leg), lifecycle state (`unmitigated → mitigated → invalidated`), `created_at`, `mitigated_at`, `invalidated_at`. Full history is retained for Phase 4 ML features and Phase 6 evidence traces.

### MTF Context (SMC-06)
- **D-13:** HTF bias per M15 decision bar = **position of the M15 close inside the HTF zone range**: in premium → bearish bias, in discount → bullish bias. Reuses the locked zone machinery; no separate bias rule.
- **D-14:** **Lean payload** joined per M15 bar, per HTF (H1 and H4): bias direction, HTF range high/low/equilibrium, distance-to-equilibrium in ATR units, and the IDs of HTF zones whose range contains the M15 close. No HTF pool/sweep payload in v1.
- **D-15:** **Confirmation-time as-of** rule (the #1 lookahead trap, pinned explicitly): an M15 bar at time T sees only HTF state whose CONFIRMATION happened strictly before T. Never join on HTF bar-open time; never take "the latest HTF row". H1/H4 context shifts as HTF swings confirm — that shift is part of the contract and must be covered by the repaint/point-in-time tests (ROADMAP SC4).

### the agent's Discretion
- ATR implementation details (Wilder vs SMA smoothing) and exact pool-clustering algorithm internals
- Gap/weekend/session-boundary handling inside detectors (bars only exist where the market traded); DST-shifted H4 anchor (21:00-UTC close lattice) must be covered by tests
- Zone/pool/sweep ID scheme and internal state-machine implementation (pure functions over frames)
- Detector module layout under `src/ai_trading/` and exact output frame schemas beyond the fields pinned above
- Whether/how detector state persists (SQLite/Parquet) vs recomputes per cycle — planner decides with the shared-pipeline constraint in mind

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Locked scope + goals
- `.planning/ROADMAP.md` — Phase 2 goal, success criteria SC1–5, plan breakdown 02-01…02-04
- `.planning/REQUIREMENTS.md` — SMC-01…06 definitions; Out of Scope table (OB/FVG/BOS exclusions); SMCX-01/02 v2 deferrals
- `.planning/PROJECT.md` — core value, constraints: one shared look-ahead-safe code path for live AND backtest (non-negotiable), hybrid AI separation

### Phase 1 foundations (proven behavior detectors build on)
- `.planning/phases/01-data-foundation/01-RESEARCH.md` — MT5 time semantics (raw server wall time + validated offset), closed-bars invariant, pandas 3.x realities (CoW, zoneinfo)
- `.planning/phases/01-data-foundation/01-VERIFICATION.md` — verified Phase 1 contract: `start_pos=1` closed-bar invariant, forming-bar guard, `time − time_utc == validated offset` uniformity, store invariants
- `.planning/phases/01-data-foundation/01-PATTERNS.md` — pattern-of-record conventions for new modules (copy-from sources, shared patterns §1–§7)

### Code (integration surface)
- `src/ai_trading/normalize.py` — `COLUMNS`, `TIMEFRAME_MINUTES`, `floor_to_timeframe`, `assert_closed_bars` (reuse; do not duplicate tz/TF logic)
- `src/ai_trading/stores/bar_store.py` — `read_bars` as the detector input path; `merge_and_write` discipline reference
- `src/ai_trading/collector.py` — the shared pipeline entry detectors hang off; point-in-time discipline reference (pos=1, trim-before-merge)
- `tests/conftest.py` — `make_bars` synthetic bar factory + FakeMT5Client (reuse for repaint test fixtures)

### Test conventions
- `.planning/phases/01-data-foundation/01-VALIDATION.md` — Nyquist verification map; unit/mt5 marker layering to mirror

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `normalize.py` pure transforms: `floor_to_timeframe` for range/boundary math, `TIMEFRAME_MINUTES` for bar-count windows (sweep reclaim window, fractal widths)
- `make_bars` test factory: synthetic OHLC frames with configurable offset — basis for swing/repaint/sweep fixtures
- `bar_store.read_bars`: detector input path returning COLUMNS-ordered frames (empty-frame contract when file missing)

### Established Patterns
- Pure DataFrame→DataFrame functions with zero MetaTrader5 imports outside the adapter tier (ROADMAP SC5 mirrors Phase 1's normalize.py discipline)
- Point-in-time discipline: collector proves the pattern (closed bars only, confirmation before visibility) — detectors extend it to swing confirmation-time semantics
- pytest markers `unit` (MT5-free, default) / `mt5` (live integration); ruff line-length 100; config-driven parameters via the frozen `Config` dataclass pattern

### Integration Points
- New detector package under `src/ai_trading/` consuming bars via `read_bars` (M15/H1/H4 per symbol)
- Phase 3 backtester replays the identical detector functions bar-by-bar (BT-01) — detector purity is what makes that possible
- Phase 4 ML assembles features point-in-time from pool/zone/sweep state + the lean MTF payload (D-14); Phase 6 evidence traces cite zone/pool/sweep IDs (D-12)

</code_context>

<specifics>
## Specific Ideas

- Sweep close-back window is measured in **detector-timeframe bars** (2 bars), not wall-clock time
- DST caveat from Phase 1 carries forward: broker offset is +3 during US summer time, +2 after it ends — the H4 anchor shifts with it; tz/DST tests in this phase's suite must cover the transition contract
- The repaint suite (02-01) is the phase's centerpiece: appending future bars must never alter already-emitted detector output (SC1) — zigzag replacement happens only among CONFIRMED swings, so it rewrites unconfirmed tail state only

</specifics>

<deferred>
## Deferred Ideas

- **FVG / imbalance detection as first-class features** — user asked ("FVG?") during discussion. Already tracked as **SMCX-02 (v2)**; locked rationale: each SMC concept needs its own backtest validation before becoming a first-class feature (same reason order blocks are deferred, SMCX-01). User's interest noted — candidate for prioritization in the v2 milestone.

</deferred>

---

*Phase: 2-SMC Detection Engine*
*Context gathered: 2026-08-30*
