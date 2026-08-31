# Phase 2: SMC Detection Engine - Research

**Researched:** 2026-08-31
**Domain:** Point-in-time SMC detectors on pandas 3.x DataFrames — confirmation-shifted swing/fractal detection, alternating zigzag construction, ATR-relative liquidity-pool clustering, sweep/reclaim event state machines, premium/discount zone lifecycles, and confirmation-time MTF as-of joins
**Confidence:** HIGH (stack and pandas primitives verified from official docs + live probes; SMC reference semantics verified from a full source-code audit; lookahead pitfalls grounded in a concrete verified library bug)

<user_constraints>
## User Constraints (from CONTEXT.md)

15 locked decisions (D-01..D-15). **The planner MUST honor all of them; research did not explore alternatives to any locked decision.**

### Locked Decisions

**Swing Detection (SMC-01)**
- **D-01:** Swing window is a **2/2 fractal** (5-bar fractal): a swing high requires a bar whose high is exceeded by no neighbor within 2 bars on each side (mirror for lows). The swing is stamped at its extreme bar but only becomes visible/confirmed on the close of the 2nd right-side bar (`confirmed_at` = that confirmation bar's close time).
- **D-02:** **Strict comparisons** — exactly-equal prices do NOT form swings. Equal highs/lows are not double-labeled as structure; the equal level itself surfaces as a liquidity pool (feeds SMC-02). Lowercase rule: swing high needs strict `>` against all 4 neighbors; `>=` never qualifies.
- **D-03:** Swing records are **minimal**: `(symbol, timeframe, bar_time, price, side, confirmed_at)`. No derived strength/prominence metrics — downstream consumers compute what they need from raw bars around the swing.
- **D-04:** Confirmed swings are sequenced into an **alternating zigzag** as the canonical structure: a newly confirmed same-side swing REPLACES the previous same-side extreme if it is more extreme (classic zigzag). PD-zone ranges and the structure-shift (BOS/CHoCH) labeling in repaint tests consume the zigzag, never the raw swing list.

**Liquidity Pools + Sweeps (SMC-02/03)**
- **D-05:** Pool clustering tolerance = **0.1 × ATR(14)** computed on the detector's own timeframe (per instrument, per timeframe). Swing highs/lows whose prices fall within tolerance cluster to one pool level.
- **D-06:** **2 touches** (the clustered swing extremes themselves) form an active pool.
- **D-07:** **Sweep rule:** a bar's wick pierces the pool level AND price closes back on the original side of the level within **2 bars** (detector-timeframe bars, inclusive window) → sweep event. If no close-back occurs within the window → the event is reclassified as a plain breakout and the pool is broken.
- **D-08:** Pools are **one-and-done**: a swept pool's lifecycle ends as `swept` (reclaimed) or `broken` (reclassified breakout). New equal-level clusters form new pools; no re-sweeping of a spent level.

**Premium/Discount Zones + Lifecycle (SMC-04/05)**
- **D-09:** Zone range = **each completed zigzag leg**: one confirmed low→high leg (or high→low) defines one range. Premium = upper 50% of the range, discount = lower 50%; the equilibrium (50%) value is carried on the zone record.
- **D-10:** Mitigation trigger = **wick touch**: price trading into the zone (wick reaching the near boundary) transitions the zone to `mitigated`. Closes are not required for mitigation.
- **D-11:** Invalidation trigger = **close beyond the far boundary** of the zone's range (close above premium top or below discount bottom). Wick pokes beyond the boundary do NOT invalidate; only committed closes do.
- **D-12:** **Track all zones** concurrently — every completed leg spawns a zone that lives until its lifecycle resolves. Zone records carry: range high/low, equilibrium, direction (premium/discount orientation of the leg), lifecycle state (`unmitigated → mitigated → invalidated`), `created_at`, `mitigated_at`, `invalidated_at`. Full history is retained for Phase 4 ML features and Phase 6 evidence traces.

**MTF Context (SMC-06)**
- **D-13:** HTF bias per M15 decision bar = **position of the M15 close inside the HTF zone range**: in premium → bearish bias, in discount → bullish bias. Reuses the locked zone machinery; no separate bias rule.
- **D-14:** **Lean payload** joined per M15 bar, per HTF (H1 and H4): bias direction, HTF range high/low/equilibrium, distance-to-equilibrium in ATR units, and the IDs of HTF zones whose range contains the M15 close. No HTF pool/sweep payload in v1.
- **D-15:** **Confirmation-time as-of** rule (the #1 lookahead trap, pinned explicitly): an M15 bar at time T sees only HTF state whose CONFIRMATION happened strictly before T. Never join on HTF bar-open time; never take "the latest HTF row". H1/H4 context shifts as HTF swings confirm — that shift is part of the contract and must be covered by the repaint/point-in-time tests (ROADMAP SC4).

### the agent's Discretion
- ATR implementation details (Wilder vs SMA smoothing) and exact pool-clustering algorithm internals
- Gap/weekend/session-boundary handling inside detectors (bars only exist where the market traded); DST-shifted H4 anchor (21:00-UTC close lattice) must be covered by tests
- Zone/pool/sweep ID scheme and internal state-machine implementation (pure functions over frames)
- Detector module layout under `src/ai_trading/` and exact output frame schemas beyond the fields pinned above
- Whether/how detector state persists (SQLite/Parquet) vs recomputes per cycle — planner decides with the shared-pipeline constraint in mind

### Deferred Ideas (OUT OF SCOPE)
- **FVG / imbalance detection as first-class features** — tracked as **SMCX-02 (v2)**; locked rationale: each SMC concept needs its own backtest validation before becoming a first-class feature (same reason order blocks are deferred, SMCX-01). Order blocks (SMCX-01) and BOS/CHoCH as first-class labeled features are also out of scope — BOS/CHoCH appear solely as structure-shift labels inside the repaint tests.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| SMC-01 | Detect swing highs/lows with confirmation-shifted logic (non-repainting) | Verified vectorized strict-inequality 2/2 fractal pattern (Pattern 1): `high > high.shift(±1/±2)` comparisons with `confirmed_at = time_utc.shift(-2) + TF`; NaN-tail naturally disqualified; repaint test design in Validation Architecture + Pitfall 2 |
| SMC-02 | Cluster equal highs/lows into liquidity pools with ATR-relative tolerance per instrument | D-05 tolerance = 0.1 × Wilder ATR(14) per (symbol, timeframe); verified ATR formula [CITED: en.wikipedia.org/wiki/Average_true_range] + pandas `ewm(alpha=1/14, adjust=False, min_periods=14)` mapping; cluster-then-activate state machine (Pattern 4); reference library's tolerance lookahead bug documents what to avoid |
| SMC-03 | Emit sweep events distinguishing take-out+reclaim from pure breakouts | D-07 pierce+close-back ≤ 2-bar inclusive window state machine (Pattern 4); terminal states swept/broken (D-08); pin inclusive-window counting convention (Assumption A8) |
| SMC-04 | Derive premium/discount zones from confirmed swing ranges | D-09 per-completed-zigzag-leg ranges; zigzag from Pattern 3 (replacement among confirmed swings only); zone records carry range high/low + equilibrium |
| SMC-05 | Every pool and zone carries lifecycle state updated bar-by-bar | Pure state machines: zones `unmitigated → mitigated → invalidated` via wick-touch / close-beyond checks (Pattern 5); pools `forming → active → swept|broken` (Pattern 4); all timestamps first-event |
| SMC-06 | H1/H4 context joined point-in-time as of each M15 decision bar | D-15 strictly-before confirmation join; verified `pd.merge_asof(direction='backward', allow_exact_matches=False, by=...)` semantics [CITED: pandas.pydata.org merge_asof] + both-frames-sorted requirement; zone-ID containment via small cross-join filter; DST H4-anchor test coverage per CONTEXT specifics |
</phase_requirements>

## Summary

Phase 2 is a **pure-pandas detector library** layered on the verified Phase 1 contract (`read_bars` → `COLUMNS` frames with naive `time_utc`). Four detector families — swings → zigzag, pools → sweeps, zones → lifecycle, MTF as-of join — all expressed as pure `DataFrame → DataFrame` functions with **zero MetaTrader5 imports** (ROADMAP SC5 mirrors Phase 1's normalize.py discipline). No new dependencies are required: every primitive needed (centered/shifted rolling comparisons, `ewm(alpha=1/n, adjust=False)` for Wilder ATR, `merge_asof` with `direction='backward', allow_exact_matches=False` for strictly-before joins) was verified against official pandas 3.x documentation this session, and the versions were probed live on the target machine.

The decisive research finding is a **full source-code audit of the most popular SMC reference implementation** (`smartmoneyconcepts` v0.0.27, 2k stars, MIT [CITED: github.com/joshyattridge/smart-money-concepts]). It confirms the domain semantics are standard (centered-window swings, same-side-more-extreme zigzag replacement, level clustering, sweep indices) — but its concrete implementation **conflicts with three locked decisions and contains a textbook lookahead bug**: (1) its swings use `==` ties and a centered window with no confirmation stamp, i.e. they repaint by construction (D-01/D-02 forbid this); (2) its liquidity tolerance derives from the **full-frame price range** (`ohlc["high"].max() - ohlc["low"].min()`), leaking future data into every historical pool decision (D-05 requires as-of ATR); (3) it has no reclaim rule, no zone lifecycle, and no as-of MTF join at all. **Conclusion: the detectors are deliberately hand-rolled** — not because no library exists, but because the locked D-01..D-15 semantics ARE the product's core IP and no library encodes them.

The phase's centerpiece is the **repaint test suite** (ROADMAP SC1). The key design insight from D-04 + CONTEXT specifics: repaint immutability is a **two-tier contract** — raw swing records are strictly immutable once confirmed; the alternating zigzag's *tail* (the current incomplete leg's endpoint) is legitimately rewritable when a more-extreme same-side swing confirms; completed-leg zones/pools are strictly immutable because they derive only from closed legs. Tests must assert immutability at each tier with the right granularity — testing the zigzag as strictly immutable would fail on valid tail replacement and force a wrong implementation.

**Primary recommendation:** Build four small detector modules as pure functions exactly per D-01..D-15 — strict 2/2 fractal with `confirmed_at` stamping (emit only at confirmation close), explicit alternation loop for the zigzag, cluster-then-activate pool machine with 2-bar inclusive reclaim window, wick-touch/close-beyond zone machine over completed legs, and a `merge_asof(backward, allow_exact_matches=False)` confirmation-time join — **writing the repaint/point-in-time suite first as the executable specification** (plan 02-01).

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Swing detection + confirmation stamping (SMC-01) | Domain/transform (pure detector functions) | — | Vectorizable math over bar frames; must be unit-testable with zero MT5/IO dependency (SC5) |
| Alternating zigzag construction (D-04) | Domain/transform | — | Consumes swing records; consumed by zones + repaint structure labels |
| ATR(14) computation | Domain/transform (pure) | Config (period as config field) | Pure series math; feeds pool tolerance and D-14 distance units |
| Liquidity pool clustering + activation (SMC-02) | Domain (pure state machine) | — | Event-sparse sequential logic; clarity over cleverness for auditability |
| Sweep/breakout classification (SMC-03) | Domain (pure state machine) | — | Bar-by-bar pierce/reclaim resolution; terminal-state semantics per D-07/D-08 |
| Zone derivation + lifecycle (SMC-04/05) | Domain (pure state machine) | — | Per-leg ranges + monotone lifecycle; full history retained for Phase 4/6 |
| MTF point-in-time context join (SMC-06) | Domain/transform (pure join) | normalize.py (TF constants) | `merge_asof` on confirmation timestamps; uses `TIMEFRAME_MINUTES`, never re-derives grids |
| Detector input path | Storage (existing `bar_store.read_bars`) | — | Already built and verified in Phase 1; detectors receive frames, never touch files/MT5 |
| Output persistence | **Open — planner decision** | Storage | Discretion item; research recommends pure recompute-per-cycle (frames are small, functions deterministic) |

No browser/frontend/API tiers exist in this phase; everything is local pure computation. The MT5 adapter and collector tiers are **untouched** — detectors consume already-stored closed bars.

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| pandas | 3.0.5 (already pinned `>=3.0,<4`) | All detector math: `shift` comparisons, `rolling`, `ewm`, `merge_asof`, frame construction | Already the project standard; 3.x CoW default keeps detector purity visible [VERIFIED: local probe 2026-08-31] |
| numpy | 2.5.2 (transitive via pandas) | Vectorized masks, `np.where`, float arrays | Transitive hard dep of pandas 3.x [VERIFIED: local probe] |
| Python | 3.12.12 (uv-managed) | Runtime | Locked stack [VERIFIED: local probe] |
| pytest | 9.1.1 | Repaint + unit suites; markers `unit`/`mt5` | Locked test framework [VERIFIED: local probe] |
| ruff | 0.16.5 | Lint (line-length 100) | Locked toolchain [VERIFIED: local probe] |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `ai_trading.normalize` (existing) | — | `COLUMNS`, `TIMEFRAME_MINUTES`, `floor_to_timeframe` — reuse for TF windows (fractal width = 2 bars, sweep window = 2 bars) and any boundary math | Always; never duplicate tz/TF logic (CONTEXT integration points) |
| `ai_trading.stores.bar_store.read_bars` (existing) | — | Detector input path (empty-frame contract when file missing) | Caller/integration layer only — detectors take DataFrames |
| `tests/conftest.make_bars` (existing) | — | Synthetic TF-aligned OHLC fixtures; sculpt highs/lows to shape known swings/pools/sweeps | All detector tests |
| zoneinfo/datetime (stdlib) | — | Only for test clocks; detector math stays on naive `time_utc` | Tests only |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Bespoke pure detector modules | `smartmoneyconcepts` (PyPI `smartmoneyconcepts`, MIT, 2k★) | Rejected: semantics conflict with locked D-01/D-02/D-05/D-07 (repainting centered swings, `==` ties, full-frame-range tolerance, no reclaim rule, no zone lifecycle, no as-of join). Would require fighting the library everywhere. Kept as **reference reading only** [CITED: github.com/joshyattridge/smart-money-concepts] |
| Hand-clustered pools | `scipy.cluster` (agglomerative/single-link) | Rejected: single-link transitive chaining violates "cluster to one pool level" semantics (a chain of near-equal levels would span a huge range); adds a dependency for ~20 lines of sequential logic over sparse swings [ASSUMED: scipy clustering semantics] |
| Hand-rolled ATR | `pandas-ta` / TA-Lib | Rejected: indicator-zoo dependency for one function; TA-Lib is a C-extension install burden on Windows; the 6-line TR + `ewm` composition is fully verified [ASSUMED: pandas-ta/TA-Lib install characteristics] |
| `merge_asof` join | Manual `searchsorted` per M15 bar | `merge_asof` is the verified blessed path; searchsorted only as fallback if per-symbol multi-key semantics get awkward |
| Recompute-per-cycle | Persisted detector state (SQLite/Parquet) | Discretion (CONTEXT); recommendation: recompute — 501→250k bars is milliseconds for vectorized detection, purity is the BT-01 contract, state persistence adds invalidation bugs with zero benefit at this scale |

**Installation:** none — no new packages. Existing `uv.lock` covers everything.

**Version verification:** All versions probed live this session via `uv run python -c "import sys, pandas, numpy; ..."` / `pytest --version` / `ruff --version`: python 3.12.12, pandas 3.0.5, numpy 2.5.2, pytest 9.1.1, ruff 0.16.5 [VERIFIED: local probe 2026-08-31].

## Package Legitimacy Audit

> Protocol note: this phase installs **no external packages** — the locked stack (pandas/pyarrow/pytest/ruff) was verified and human-approved in Phase 1. One candidate library was evaluated and rejected by research without installation.

| Package | Registry | Age | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----|-----------|-------------|---------|-------------|
| smartmoneyconcepts | PyPI | v0.0.27; project active since ~2023 [CITED: github repo PyPI badge + releases] | not probed (rejected before registry check) | github.com/joshyattridge/smart-money-concepts (2k★, 845 forks, MIT) [CITED: github] | Not rated — **evaluated and rejected on semantics, not provenance** | Not adopted — no install task; keep as reference reading only |

**Packages removed due to [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none (nothing is being installed)

*If the planner chooses to adopt `smartmoneyconcepts` anyway, it must first run the full legitimacy gate (`gsd-tools query package-legitimacy check --ecosystem pypi smartmoneyconcepts` + `pip index versions`) and add a `checkpoint:human-verify` task. Research recommendation: do not adopt — the three verified semantic conflicts (repainting swings, `==` ties, full-frame-range tolerance lookahead) and missing features (no reclaim rule, no zone lifecycle, no MTF join) make it unusable under D-01..D-15.*

## Architecture Patterns

### System Architecture Diagram

```
   data/bars/{SYMBOL}_{TF}.parquet  (Phase 1 store — closed bars only)
        │
        ▼
   bar_store.read_bars(path)          ── caller/integration layer (NOT inside detectors)
        │  COLUMNS frames: naive time (server wall) + naive time_utc
        ▼
┌──────────────────────────────  DETECTOR TIER (pure DataFrame→DataFrame) ──────────────────────────────┐
│                                                                                                       │
│   [wilders_atr] ◄── TR from high/low/prev-close ──► ATR(14) series per (symbol, timeframe)            │
│        │ tol = 0.1 × ATR  (D-05)                                                                      │
│        ▼                                                                                              │
│   [detect_swings]  ──► swing records (symbol, tf, bar_time, price, side, confirmed_at)   (D-01..03)   │
│        │   strict 2/2 fractal; confirmed_at = close time of 2nd right bar; IMMUTABLE once emitted     │
│        ▼                                                                                              │
│   [build_zigzag]  ──► alternating structure points                       (D-04)                       │
│        │   same-side: replace if more extreme / absorb; tail-only mutability                          │
│        ├──► (structure-shift labels for repaint tests only — NOT a first-class feature)               │
│        ▼                                                                                              │
│   ┌──────────────────────┐        ┌───────────────────────────────┐                                   │
│   │ [detect_pools]        │        │ [derive_zones]                 │                                  │
│   │ cluster swings        │        │ per COMPLETED zigzag leg:      │                                  │
│   │ 2 touches → active    │        │ range, equilibrium, direction  │                                  │
│   │ per bar: pierce?      │        │ per bar: wick-touch →          │                                  │
│   │  ├ close back ≤2 bars │        │   mitigated; close beyond →    │                                  │
│   │  │  → swept  (D-07)   │        │   invalidated  (D-10/11/12)    │                                  │
│   │  └ else → broken      │        │ unmitigated→mitigated→         │                                  │
│   │ one-and-done (D-08)   │        │ invalidated, monotone          │                                  │
│   └──────────┬───────────┘        └──────────────┬────────────────┘                                   │
│              │ pool/sweep events                 │ zone state timeline (created/mitigated/invalidated) │
│              ▼                                   ▼                                                     │
│   ┌───────────────────────────────────────────────────────────┐                                        │
│   │ [mtf_context]  (D-13..D-15)                                │                                        │
│   │ H1 zones + H4 zones ──► state timeline sorted by           │                                        │
│   │ confirmed_at                                               │                                        │
│   │ merge_asof(M15 bars ← HTF timeline,                        │                                        │
│   │   direction='backward', allow_exact_matches=False,         │                                        │
│   │   by='symbol')  ── strictly-before confirmation join       │                                        │
│   │ + zone-ID containment (cross-join filter, tiny volumes)    │                                        │
│   │ payload: bias, range hi/lo/eq, dist-to-eq (ATR), zone_ids  │                                        │
│   └────────────────────────────┬──────────────────────────────┘                                        │
└────────────────────────────────┼───────────────────────────────────────────────────────────────────────┘
                                 ▼
          Output frames (pure, deterministic, no side effects)
          → Phase 3 replays the IDENTICAL functions bar-by-bar (BT-01)
          → Phase 4 assembles features point-in-time (AI-01)
          → Phase 6 evidence traces cite zone/pool/sweep IDs (D-12)
```

Primary use-case trace: `read_bars(M15/H1/H4)` → swings confirm 2 bars after extremes → zigzag forms → equal-level swings cluster into pools; pierce+reclaim emits sweeps (else breakout) → each completed leg spawns a zone whose state advances bar-by-bar → every M15 bar joins H1+H4 zone state whose confirmation is strictly earlier than the bar's time → lean MTF payload.

### Recommended Project Structure

```
src/ai_trading/
├── normalize.py              # EXISTING — reuse TIMEFRAME_MINUTES/COLUMNS; do not duplicate
├── stores/bar_store.py       # EXISTING — read_bars is the input path
└── detectors/                # NEW package — pure functions only, zero MT5 imports, zero file I/O
    ├── __init__.py
    ├── atr.py                # wilders_atr(bars, period=14) -> Series        (SMC-02 support)
    ├── swings.py             # detect_swings(bars, timeframe) -> swing frame   (SMC-01, D-01..03)
    ├── zigzag.py             # build_zigzag(swings) -> structure frame         (D-04)
    ├── pools.py              # detect_pools(bars, swings, atr, ...) -> pools + events (SMC-02/03, D-05..08)
    ├── zones.py              # derive_zones(zigzag, bars) -> zones + lifecycle (SMC-04/05, D-09..12)
    └── mtf.py                # htf_context(m15, htf_zones, ...) -> payload     (SMC-06, D-13..15)
tests/
├── conftest.py               # EXISTING — make_bars + FakeMT5Client (do not extend for detectors;
│                             #   add a tests/unit/detectors conftest or local helpers instead)
└── unit/
    ├── test_swings.py        # strict fractal, confirmation stamping, edge cases
    ├── test_repaint.py       # SC1 centerpiece — append-future-bars immutability, all tiers
    ├── test_pools.py         # tolerance clustering incl. boundary cases, 2-touch activation
    ├── test_sweeps.py        # sweep vs breakout classification
    ├── test_zones.py         # per-leg ranges, equilibrium
    ├── test_lifecycle.py     # bar-by-bar zone + pool state transitions, timestamps
    ├── test_mtf_join.py      # strictly-before as-of, DST H4 anchor, payload contents
    └── test_detector_integration.py  # end-to-end chain over synthetic multi-TF frames
```

*(Module layout is the agent's discretion — this is the research recommendation; names are chosen so plan 02-01..02-04 map cleanly onto them.)*

### Pattern 1: Strict 2/2 fractal with confirmation shift (SMC-01)
**What:** Vectorized swing detection using `shift(+1/+2)` (left neighbors) and `shift(-1/-2)` (right neighbors) comparisons; the right-side comparisons are what make the detector confirmation-shifted — a swing physically cannot be emitted before its 2 right neighbors exist. Stamp `confirmed_at` as the **close time** of the confirmation bar (bar i+2's open + TF minutes).
**When to use:** plan 02-01. NaN handling is free: comparisons against `NaN` are `False`, so the last 2 rows of any frame can never be swings — exactly the desired unconfirmed-tail behavior.
**Example:**
```python
# Source: pandas shift/comparison semantics [CITED: pandas.pydata.org]; locked D-01/D-02
import pandas as pd
from ai_trading.normalize import TIMEFRAME_MINUTES

def detect_swings(bars: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    h, l = bars["high"], bars["low"]
    swing_high = (h > h.shift(1)) & (h > h.shift(2)) & (h > h.shift(-1)) & (h > h.shift(-2))
    swing_low  = (l < l.shift(1)) & (l < l.shift(2)) & (l < l.shift(-1)) & (l < l.shift(-2))
    mask = swing_high | swing_low

    # confirmation bar = extreme_bar + 2; its close time = its open + TF minutes
    confirmed_at = bars["time_utc"].shift(-2) + pd.Timedelta(
        minutes=TIMEFRAME_MINUTES[timeframe]
    )

    side = pd.Series(pd.NA, index=bars.index).mask(swing_high, "high").mask(swing_low, "low")
    price = bars["high"].where(swing_high, bars["low"])

    out = pd.DataFrame({
        "symbol":       bars.loc[mask, "symbol"].to_numpy(),
        "timeframe":    timeframe,
        "bar_time":     bars.loc[mask, "time_utc"].to_numpy(),   # extreme bar (D-03)
        "price":        price.loc[mask].to_numpy(),
        "side":         side.loc[mask].to_numpy(),
        "confirmed_at": confirmed_at.loc[mask].to_numpy(),
    })
    return out.reset_index(drop=True)
```
**Edge case to pin in the plan:** a single bar can be BOTH a swing high and swing low (wide outside bar strictly exceeding all 4 neighbors on both sides). Both records are correct per D-01/D-03; the zigzag must pin a same-bar ordering (discretion — recommend emitting `high` then `low` deterministically and testing it).

### Pattern 2: Wilder ATR(14) (D-05 support)
**What:** True Range = `max(high−low, |high−prev_close|, |low−prev_close|)`; ATR is Wilder's recursive smoothing `ATR_t = (ATR_{t-1}×(n−1) + TR_t)/n`, i.e. an EMA with `alpha = 1/n` [CITED: en.wikipedia.org/wiki/Average_true_range]. pandas `ewm(alpha=1/period, adjust=False)` is exactly that recursion, seeded with the first TR instead of Wilder's SMA-of-first-n seed — the seed difference decays exponentially and is immaterial for a 0.1× tolerance use.
**When to use:** plan 02-02 (and for the D-14 distance units). **Recommendation (discretion): Wilder/RMA variant**, since it is the canonical ATR traders expect and `ewm` gives it in one line; document the seed nuance so tests hand-compute expectations with the same convention.
**Example:**
```python
# Source: TR/ATR formula [CITED: en.wikipedia.org/wiki/Average_true_range];
# ewm semantics [CITED: pandas.pydata.org DataFrame.ewm]
def wilders_atr(bars: pd.DataFrame, period: int = 14) -> pd.Series:
    prev_close = bars["close"].shift(1)
    tr = pd.concat(
        [bars["high"] - bars["low"],
         (bars["high"] - prev_close).abs(),
         (bars["low"] - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    # Wilder recursion == EMA(alpha=1/n, adjust=False). pandas seeds with TR[0];
    # Wilder's canonical seed is the SMA of the first n TRs — difference decays
    # geometrically and is immaterial for tolerance use. min_periods=14 keeps
    # the warmup NaN so callers can guard.
    return tr.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
```

### Pattern 3: Alternating zigzag over confirmed swings (D-04)
**What:** An explicit, ordered loop over swing records sorted by `confirmed_at`. Same-side confirmation: replace the tail if the new swing is more extreme, otherwise absorb it (it still exists as a swing record for pools — D-02/D-05 — it just never enters structure). Opposite-side confirmation: append, which completes the previous leg.
**When to use:** plan 02-01/02-03. Swings are sparse (a small fraction of bars), so a Python loop over them is correct, clear, and fast; do not contort this into vector form.
**Why a loop and not the reference library's vectorized approach:** the library post-processes its centered swings in a `while True` removal loop to enforce alternation — same outcome, but its input repaints. Working from immutable confirmed swings makes the loop's output deterministic and repaint-safe by construction [CITED: github.com/joshyattridge/smart-money-concepts smc.py].
**Example:**
```python
# Locked D-04 semantics; reference for the alternation convention:
# github.com/joshyattridge/smart-money-concepts (same-side more-extreme rule)
def build_zigzag(swings: pd.DataFrame) -> pd.DataFrame:
    points: list[dict] = []
    for s in swings.sort_values(["confirmed_at", "bar_time"]).itertuples(index=False):
        if not points:
            points.append({"bar_time": s.bar_time, "price": s.price, "side": s.side,
                           "confirmed_at": s.confirmed_at})
            continue
        last = points[-1]
        if s.side == last["side"]:
            more_extreme = (s.price > last["price"]) if s.side == "high" else (s.price < last["price"])
            if more_extreme:                      # REPLACE tail (classic zigzag)
                points[-1] = {"bar_time": s.bar_time, "price": s.price, "side": s.side,
                              "confirmed_at": s.confirmed_at}
            # else: absorbed — remains a raw swing for pool clustering only
        else:
            points.append({"bar_time": s.bar_time, "price": s.price, "side": s.side,
                           "confirmed_at": s.confirmed_at})   # leg completes
    return pd.DataFrame(points)
```
**Repaint contract tier 2 (critical):** the REPLACE branch mutates only the zigzag *tail* — the endpoint of the current incomplete leg. Entries before the final leg are immutable. Zones derive only from *completed* legs, so they never observe tail mutation (CONTEXT specifics: "zigzag replacement … rewrites unconfirmed tail state only").

### Pattern 4: Pool clustering + sweep classification (SMC-02/03)
**What:** Two sequential pure passes. **Pass 1 (cluster):** iterate confirmed swings per side in confirmation order; a swing joins the most recent open cluster on its side when `|price − cluster_level| ≤ tol` (tol = 0.1 × ATR(14) evaluated as-of that swing's confirmation — never from full-frame statistics); otherwise it opens a new candidate. A cluster reaching **2 members activates a pool** (D-06); its level is the mean of member prices (recommended discretion). **Pass 2 (classify):** walk bars; for each active pool, a bar whose wick pierces the level (`high > level` for equal-high/sell-side pools, `low < level` for equal-low/buy-side pools) opens a 2-bar inclusive window: if any close in the pierce bar or the next bar is back on the original side → `swept`; if the window ends with no close-back → `broken` (plain breakout). Terminal states are final (D-08); post-resolution equal-level swings start NEW candidates.
**Pinned ordering rule (discretion — plan must state it):** within one bar, first apply swing confirmations/clustering, then event checks — so a pool that activates on the same bar its level is pierced is classified normally.
**Example:**
```python
# Locked D-05..D-08; anti-pattern evidence (full-frame tolerance lookahead):
# github.com/joshyattridge/smart-money-concepts smc.py liquidity()
def classify_pool_event(pool_level: float, pool_side: str, bars: pd.DataFrame) -> str:
    """Vectorized-per-pool helper; the state machine iterates active pools per bar."""
    if pool_side == "high":                       # sell-side liquidity above the level
        pierced = bars["high"] > pool_level
        reclaimed = bars["close"] < pool_level
    else:                                         # buy-side liquidity below the level
        pierced = bars["low"] < pool_level
        reclaimed = bars["close"] > pool_level
    pierce_idx = pierced.idxmax() if pierced.any() else None
    if pierce_idx is None:
        return "unresolved"
    pos = bars.index.get_loc(pierce_idx)
    window = reclaimed.iloc[pos : pos + 2]        # 2-bar INCLUSIVE window (D-07)
    return "swept" if window.any() else "broken"  # no close-back => plain breakout
```

### Pattern 5: Zone derivation + monotone lifecycle (SMC-04/05)
**What:** Each pair of consecutive opposite zigzag points defines one zone at the moment the second point *confirms* (`created_at` = that confirmation time): `range_high = max(p1, p2)`, `range_low = min(p1, p2)`, `equilibrium = (high + low) / 2`, `leg_direction` = up (low→high) or down (high→low). Then every live zone is checked bar-by-bar: **mitigation** = first bar whose wick intersects the range interior — `(low < range_high) and (high > range_low)` (D-10 wick touch; closes not required); **invalidation** = first bar whose **close** is beyond the range — `close > range_high or close < range_low` (D-11 committed closes only). Lifecycle is monotone `unmitigated → mitigated → invalidated`; both checks run every bar, so one bar can stamp both timestamps (pin the recording order in the plan). Zones are never deleted — full history retained (D-12).
**Why wick-intersection operationalizes "near boundary":** after an up-leg tops out, price approaches the range from above, so the first wick entering `(range_low, range_high)` touches the near (top) boundary; symmetric for down-legs. The boolean pair above covers both approaches without needing an approach-side state variable.
**Example:**
```python
# Locked D-09..D-12
def advance_zone(zone: dict, bar: pd.Series) -> dict:
    if zone["state"] == "invalidated":
        return zone
    in_range_wick = (bar["low"] < zone["range_high"]) and (bar["high"] > zone["range_low"])
    close_beyond  = (bar["close"] > zone["range_high"]) or (bar["close"] < zone["range_low"])
    if zone["state"] == "unmitigated" and in_range_wick:
        zone["state"], zone["mitigated_at"] = "mitigated", bar["time_utc"]
    if close_beyond:   # valid from either state (D-11 commits closes only)
        zone["state"], zone["invalidated_at"] = "invalidated", bar["time_utc"]
    return zone
```

### Pattern 6: Confirmation-time MTF as-of join (SMC-06)
**What:** Build the HTF zone-state timeline keyed by **confirmation timestamps** (zone `created_at`/`mitigated_at`/`invalidated_at`, HTF zigzag confirmations), sort by it, then `merge_asof` each M15 decision bar against that timeline with `direction='backward', allow_exact_matches=False` — the verified pandas way to express D-15's "strictly before T" [CITED: pandas.pydata.org merge_asof: "use allow_exact_matches=False to match rows only with prior data"]. Both frames must be sorted by the join key. The multi-zone containment payload (IDs of HTF zones whose range contains the M15 close) is a small cross-join + boolean filter — 8,640 M15 bars per 90 days × tens of zones is trivially cheap; do not build an interval-tree.
**When to use:** plan 02-04. Compute bias from the joined range: `close > equilibrium → bearish (premium)`, `close < equilibrium → bullish (discount)`, `close == equilibrium → neutral` (pin the exact-equal case in the plan — discretion).
**Example:**
```python
# Source: [CITED: pandas.pydata.org merge_asof + user_guide/merging.html]
def join_htf_context(m15: pd.DataFrame, htf_state: pd.DataFrame) -> pd.DataFrame:
    m15 = m15.sort_values("time_utc")
    htf_state = htf_state.sort_values("confirmed_at")     # REQUIRED: both sorted
    return pd.merge_asof(
        m15, htf_state,
        left_on="time_utc", right_on="confirmed_at",
        by="symbol",
        direction="backward",
        allow_exact_matches=False,   # D-15: strictly BEFORE the decision bar
    )
```

### Anti-Patterns to Avoid
- **Centered-window swings without a confirmation stamp** (the reference library's approach): a swing "exists" only because future bars exist → repaints by construction, violates SC1 outright. Always emit at confirmation time. [CITED: smc.py swing_highs_lows]
- **`==`/`>=` tie handling in swings:** D-02 locks strict `>` / `<`. Exactly-equal neighbor prices disqualify; the near-equal level surfaces via pool clustering instead. Do not "fix" the strictness to be tolerant.
- **Full-frame statistics anywhere in detection:** the reference library computes pool tolerance from the *entire frame's* `high.max() − low.min()` — a genuine lookahead bug. Every tolerance, normalization, and ATR must be computed as-of the decision point. [CITED: smc.py liquidity]
- **Joining HTF context on HTF bar-open time or "latest HTF row":** an H4 bar stamped 12:00 contains information through 15:59; a 12:15 M15 bar must not see it. Join axis is HTF *confirmation* time, strictly before the M15 bar time (D-15 — the #1 trap, explicitly pinned by the user).
- **Testing the zigzag as strictly immutable:** valid tail replacement would then force a wrong implementation. Test the two-tier contract (see Pitfall 2).
- **Vectorizing the state machines into obscurity:** pools/zones are event-sparse; loops over events are auditable and fast. Reserve vectorization for the swing mask, TR, and the final joins.
- **Mutating input frames:** pandas 3.x CoW makes accidental writes visible — detectors must return new frames and never write into `bars` (Phase 1 discipline).
- **Re-deriving timeframe grids with `floor_to_timeframe` on stored bars:** stored bar times are already on-grid from Phase 1; use `time_utc` directly. Re-flooring invites DST-anchor drift bugs (the H4 lattice is anchored at the 21:00-UTC server-midnight grid, verified in Phase 1).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| As-of / point-in-time matching | Manual per-row scans or "latest row before T" loops | `pd.merge_asof(direction='backward', allow_exact_matches=False, by=...)` | Verified semantics for strictly-before matching; sorted-input contract is documented; per-symbol `by=` is built in [CITED: pandas.pydata.org merge_asof] |
| Neighbor-window extremes | Nested Python loops over bars | `Series.shift(±k)` comparisons; `rolling(...).max()/.min()` (with `center=True` where a centered view is genuinely needed) | Vectorized C-speed; NaN tails handled by comparison semantics [CITED: pandas.pydata.org window user guide] |
| Exponential smoothing | Manual recursive Python loop for ATR | `Series.ewm(alpha=1/n, adjust=False, min_periods=n)` | Exactly Wilder's recursion in one vectorized call [CITED: pandas.pydata.org DataFrame.ewm] |
| Bar input, TF constants, boundary math | Any re-implementation of columns/timeframes/flooring | `ai_trading.normalize` + `bar_store.read_bars` | Phase 1 contract is verified; duplication is how tz bugs are born |
| Test bar fixtures | Hand-building DataFrames in every test | `conftest.make_bars` + small local sculpting helpers | Factory already guarantees TF alignment, OHLC sanity, COLUMNS order |
| **The detectors themselves** | *(see counter-point below)* | Bespoke pure functions per D-01..D-15 | **Deliberate exception** — the locked semantics ARE the product's IP |

**Counter-point (important):** unlike Phase 1, this phase *deliberately hand-rolls its core domain logic*. The `smartmoneyconcepts` reference library proves the concepts are standard, but its verified implementation conflicts with D-01 (repainting centered swings), D-02 (`==` ties), D-05 (full-frame-range tolerance — a lookahead bug), D-07 (no reclaim rule), D-09..D-12 (no zone lifecycle), and D-15 (no as-of join). The "don't hand-roll" rule targets *infrastructure* (joins, smoothing, windows) — the SMC semantics layer is exactly what this project exists to own, test, and eventually backtest-validate.

**Key insight:** every hand-rolled substitute in the table above re-encodes verified pandas/stdlib behavior and would leak subtle bugs (off-by-one windows, unsorted as-of inputs, wrong decay seeds). The detector layer hand-roll exists because no library can encode decisions a user has already locked.

## Common Pitfalls

### Pitfall 1: Joining HTF state on bar-open time (THE lookahead trap)
**What goes wrong:** an M15 bar at 12:15 "sees" the H4 bar that *opened* at 12:00 — whose high/low/close won't exist until 15:59. Every backtest result becomes fiction; SC4 fails.
**Why it happens:** HTF frames are indexed by open time, and "latest H4 row" is the natural-looking join.
**How to avoid:** the only join axis is the HTF **confirmation timestamp** (swing `confirmed_at`, zone `created_at`/transitions), matched `strictly before` the M15 bar time via `merge_asof(..., allow_exact_matches=False)` (D-15).
**Warning signs:** MTF payload identical for all M15 bars inside one H4 bar; repaint test where appending M15 bars changes H4 context retroactively.

### Pitfall 2: Misreading tail replacement as a repaint violation
**What goes wrong:** D-04 says a more-extreme same-side confirmation REPLACES the zigzag tail. A naive repaint test asserting "all previously emitted zigzag rows are immutable" fails on this *correct* behavior, pressuring the implementer to disable replacement — breaking D-04.
**Why it happens:** SC1's "no output changes" is true at the record tiers (swings, completed-leg zones, resolved pools), while the zigzag's *incomplete tail* is legitimately provisional.
**How to avoid:** encode the two-tier contract in tests: (T1) raw swing records strictly immutable; (T2) zigzag rows immutable **except the final point**, which may be replaced only by a more-extreme same-side confirmation; (T3) zones/pools/sweeps derived from completed legs strictly immutable. CONTEXT specifics explicitly bless this: "zigzag replacement happens only among CONFIRMED swings, so it rewrites unconfirmed tail state only."
**Warning signs:** a repaint test failure whose diff is exactly one row — the last zigzag point.

### Pitfall 3: Full-frame statistics leaking future data into tolerances
**What goes wrong:** pool tolerance computed from the frame's global range (as the reference library does) means a pool decision in 2020 depends on a spike in 2026. Same class of bug: normalizing by global min/max anywhere.
**Why it happens:** it is the vectorized-convenient shortcut.
**How to avoid:** tolerance = `0.1 × ATR(14)` evaluated **as of each clustering decision** (recommended: the ATR value at the joining swing's `confirmed_at`); guard warmup NaN (skip clustering until ATR is finite). [CITED: smc.py liquidity — verified negative example]
**Warning signs:** identical input prefix producing different pools when computed standalone vs inside a longer frame (a great repaint assertion to add).

### Pitfall 4: Exactly-equal prices never form swings — don't "fix" it
**What goes wrong:** two highs at exactly 1.10000 fail D-02's strict `>` against each other... but note they'd also need to beat the other 3 neighbors. The subtle case is an equal-price *neighbor within the 2-bar window* disqualifying an otherwise-valid swing. That is the locked intent: equal levels are liquidity, not structure.
**Why it happens:** implementer instinct treats ties as noise to smooth over.
**How to avoid:** keep strictness; pools cluster *near*-equal swings within `0.1 × ATR` (D-05), which is how "equal highs" surface as pools. If the user intended exact-equal bars to form pools directly, that is a CONTEXT change — flag, don't improvise (Assumption A6).
**Warning signs:** a plan task adding `>=` comparisons or special exact-equal pool seeding.

### Pitfall 5: Sweep window counting ambiguity
**What goes wrong:** "within 2 bars, inclusive window" admits two readings: (a) pierce bar + the next bar, or (b) the two bars *after* the pierce bar. Different implementations classify the same price path differently.
**How to avoid:** pin one convention in the plan — research recommends (a): closes checked on the pierce bar itself (immediate reclaim) and the following bar; window ends there → `broken`. Derives directly from "within 2 bars (inclusive)" and keeps fast reclaims realistic. (Assumption A8 — confirm at plan review.)
**Warning signs:** test fixtures where the expected swept/broken label flips between readings; ambiguous phrases like "2 more bars" in plan tasks.

### Pitfall 6: Same-bar coincidences inside the state machines
**What goes wrong:** one bar can (i) confirm a swing that completes a pool AND pierce it, (ii) mitigate and invalidate a zone simultaneously, (iii) carry dual swing high+low. Unpinned ordering makes outputs implementation-dependent.
**How to avoid:** pin per-machine ordering rules: pools = cluster-confirm first, then event checks; zones = mitigation check then invalidation check (both may stamp the same bar); zigzag = deterministic same-bar dual-swing order (recommended `high` then `low`). Each pinned rule gets its own named test.
**Warning signs:** tests passing only because fixtures accidentally avoid coincidences.

### Pitfall 7: ATR warmup NaN poisoning early decisions
**What goes wrong:** `ewm(min_periods=14)` yields NaN for the first bars; `0.1 × NaN` silently drops or (worse, without min_periods) mis-seeds early pool clustering.
**How to avoid:** keep `min_periods=period`; detectors skip clustering/classification until ATR is finite; document that the first ~15 bars of any frame produce no pools/zones.
**Warning signs:** pools appearing at bar index < 15; NaN comparisons returning `False` and silently skipping events.

### Pitfall 8: DST-shifted H4 anchor breaks naive grid assumptions
**What goes wrong:** H4 bars live on the server-midnight lattice (verified 21:00-UTC anchor at offset +3); when the broker offset flips +3→+2 (US DST end, early November), `time_utc` shifts while raw `time` stays put. Code that re-floors `time_utc` to an assumed grid mis-aligns joins by an hour.
**How to avoid:** detectors consume stored bar times as-is; MTF joins key on `time_utc` values themselves, never on re-derived boundaries; the DST transition contract gets a dedicated test (build bars around a +3→+2 flip; assert join continuity).
**Warning signs:** H1/H4 context jumping at 02:00–03:00 UTC in November fixtures; any use of `floor_to_timeframe` inside detector internals.

### Pitfall 9: Unsorted frames breaking merge_asof silently
**What goes wrong:** `merge_asof` requires both frames sorted by the join key; with unsorted input it raises — or worse, mis-joins after a sort on the wrong column.
**How to avoid:** explicit `sort_values` immediately before every `merge_asof`; integration test asserts sortedness invariants on detector outputs.
**Warning signs:** ` ValueError` from merge_asof in integration tests; payload rows whose `confirmed_at > time_utc` (impossible under D-15 — assert it as an invariant).

### Pitfall 10: Empty-frame and short-frame contracts
**What goes wrong:** `read_bars` returns an empty COLUMNS frame when a file is missing (verified Phase 1 contract); detectors that assume ≥1 row crash or emit garbage schemas.
**How to avoid:** every detector has an explicit empty/short-frame early return producing the correct output schema (mirror `compute_gaps`' documented empty-return pattern from Phase 1); named tests per detector.
**Warning signs:** `KeyError`/`IndexError` on empty inputs in integration tests.

## Code Examples

See Architecture Patterns 1–6 — all six verified patterns carry their source citations inline (swing detection, Wilder ATR, zigzag, pool classification, zone lifecycle, MTF as-of join). The repaint test recipe below is the phase's centerpiece pattern:

### Repaint / point-in-time test recipe (SC1)
```python
# Spec: ROADMAP SC1 + D-15 + CONTEXT specifics. Assert: appending future bars
# never changes already-visible detector output.
import pandas as pd

def test_appending_bars_never_alters_confirmed_swings(sculpted_bars):
    bars = sculpted_bars("M15", n=60)          # make_bars + sculpted highs/lows
    for k in range(10, len(bars)):
        prefix = detect_swings(bars.iloc[:k].copy(), "M15")
        full = detect_swings(bars.copy(), "M15")
        prefix_close = bars.iloc[:k]["time_utc"].iloc[-1] + pd.Timedelta(minutes=15)
        # only records whose confirmation precedes the prefix's last close are visible
        visible = full[full["confirmed_at"] <= prefix_close].reset_index(drop=True)
        pd.testing.assert_frame_equal(prefix, visible, check_exact=True)

def test_zigzag_only_tail_may_change(sculpted_bars):
    # assert zigzag rows[:-1] identical across prefixes; last row may be replaced
    # by a MORE EXTREME same-side confirmation only (D-04 + CONTEXT specifics)
    ...
```
Test-tier mapping: T1 swings (above), T2 zigzag tail rule, T3 zone/pool/sweep immutability, plus the standalone-vs-in-frame consistency check from Pitfall 3 and the MTF strictly-before invariant from Pitfall 9 (`confirmed_at ≤ time_utc` on every joined row).

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| pandas 2.x + pytz habits | pandas 3.x: CoW default, pyarrow hard dep, zoneinfo, str dtype | 2026 (3.0 line, 3.0.5 current) | Detector functions must be copy-safe; `.copy()` at function entry where frames are transformed |
| Indicator libraries (TA-Lib/pandas-ta) for everything | Small verified compositions (`shift`/`ewm`/`rolling`/`merge_asof`) | Ongoing | Fewer deps, exact semantics under test — this phase's approach |
| Repainting centered pivots (TradingView-style) | Confirmation-shifted stamps with `confirmed_at` columns | Standard practice in serious backtesting systems | SC1 mandates it; Phase 3 replay depends on it |
| Resample-based MTF context ("previous completed HTF bar") | Confirmation-time as-of joins over event state | This project's D-15 (stricter than library practice) | Even the reference library only does completed-*period* lookups; D-15 adds intra-bar confirmation shifting |

**Deprecated/outdated:**
- Centered-window swing APIs without confirmation semantics: unusable for any backtest-grade system (verified negative example in `smartmoneyconcepts`).
- `df.ewm(...).mean()` with default `adjust=True` for Wilder indicators: gives the bias-corrected variant, not Wilder's recursion — always pass `adjust=False` for Wilder semantics [CITED: pandas.pydata.org DataFrame.ewm].

## Assumptions Log

> All claims tagged `[ASSUMED]` in this research are consolidated here. Items marked "discretion" fall inside CONTEXT's the agent's Discretion but are pinned by research so the planner can lock them into the plan; the discuss-phase/user may override.

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | D-14 "distance-to-equilibrium in ATR units" uses **M15 ATR(14)** as the denominator (decision-bar perspective), signed | Pattern 6, SMC-06 support | Low-Medium — payload semantics; cheap to change, but pins test expectations |
| A2 | D-14 zone-ID containment lists **live (not-yet-invalidated)** HTF zones as of T | Pattern 6, SMC-06 | Low-Medium — an invalidated zone's range can re-contain price; including it would change payload tests |
| A3 | Pool level = **mean of member swing prices**; clustering checks membership against the running cluster level with **inclusive** tolerance (`≤ 0.1×ATR`) | Pattern 4 | Low — discretion item; boundary inclusivity must be pinned for tests either way |
| A4 | pandas `ewm(alpha=1/14, adjust=False)` (first-TR seed) is an acceptable stand-in for exact Wilder SMA-seeded ATR in tolerance use | Pattern 2 | Low — formula difference verified; decays geometrically; test expectations use the same convention |
| A5 | A pierce while a pool is still **forming** (1 touch) does not emit an event; the candidate is superseded (new clusters may form post-pierce per D-08) | Pattern 4, Pitfall 6 | Medium — affects sweep-count semantics; alternative is resolving forming pools as broken |
| A6 | D-02's "equal level surfaces as a liquidity pool" means near-equal swings cluster into pools (exact-equal bars form no swings and no direct pool) | Pitfall 4 | Medium — if the user intended exact-equal bars to seed pools directly, pool fixtures and D-05 interplay change; surface at plan review |
| A7 | Zone mitigation = wick intersects range interior from either side (operationalizes D-10's "near boundary"); invalidation closes beyond either extreme (D-11's own text) | Pattern 5 | Medium — a stricter "approach-side" reading would need approach-state tracking; current reading is symmetric and matches D-11's parenthetical |
| A8 | Sweep 2-bar inclusive window = pierce bar's close + next bar's close (research recommendation; D-07 admits a second reading) | Pattern 4, Pitfall 5 | Medium — flips swept/broken labels on edge fixtures; must be pinned in plan |
| A9 | Same-bar dual swings (high+low) ordered `high` then `low` in zigzag; bias at exactly equilibrium = neutral | Pattern 1/6, Pitfall 6 | Low — pins deterministic behavior; either choice is defensible |
| A10 | Detector state recomputes per cycle (no persistence) for v1; planner owns the final call | Architectural Responsibility Map | Low — recompute is cheap at current scale; persistence can be added later without contract change |
| A11 | Repaint testing patterns (prefix-vs-visible equality, chunked appends) as designed are the accepted SC1 proof method | Validation Architecture | Low — engineering convention; the SC1 text supports it directly |

## Open Questions

1. **Does the two-tier repaint contract (Pitfall 2) match user intent for tail replacement?**
   - What we know: D-04 locks replacement among confirmed swings; CONTEXT specifics say it "rewrites unconfirmed tail state only" — the two-tier test design follows directly.
   - What's unclear: whether the user also wants the *swing record list* to expose the replacement (it does not — D-03 records are independent of zigzag).
   - Recommendation: proceed with the two-tier design; it is the only reading consistent with both D-04 and SC1. No user gate needed unless plan review surfaces doubt.
2. **Which ATR convention to pin for test expectations (A4)?**
   - What we know: Wilder's canonical seed (SMA of first 14 TRs) vs pandas `ewm` seed (first TR) differ only in warmup, decaying geometrically.
   - What's unclear: none material — but tests must hand-compute expectations with the chosen convention.
   - Recommendation: pin `ewm(alpha=1/14, adjust=False, min_periods=14)`; document the seed nuance in the module docstring.
3. **Exact-equal highs/lows and pool formation (A6).**
   - What we know: D-02 forbids equal prices from forming swings; D-05 pools cluster swings. Net effect: exactly-equal price pairs produce no pool from those bars.
   - What's unclear: whether the user's "equal level itself surfaces as a liquidity pool" intends direct seeding for exact-equal bars.
   - Recommendation: raise at plan review as a one-line confirmation; default implementation follows the literal D-02+D-05 composition (no special casing).

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python (uv-managed) | All plans | ✓ | 3.12.12 | — |
| pandas | All detectors | ✓ | 3.0.5 | — |
| numpy | Masks/arrays (transitive) | ✓ | 2.5.2 | — |
| pytest | All test suites | ✓ | 9.1.1 | — |
| ruff | Lint gate | ✓ | 0.16.5 | — |
| MT5 terminal | **Nothing in this phase** — detectors are pure and unit-testable without it | n/a | — | Not needed; only Phase 1's mt5-marked tests use it |
| Existing Phase 1 modules | Input path + TF constants | ✓ verified (`normalize.py`, `stores/bar_store.py`, `conftest.make_bars`) | — | — |

**Missing dependencies with no fallback:** none.
**Missing dependencies with fallback:** none. (SearXNG web-search engines were rate-limited/CAPTCHA-blocked during this session; research compensated by fetching official sources directly — pandas docs via Context7, Wikipedia ATR, and the full SMC reference source from GitHub. No impact on findings.)

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.1.1 (uv dev dependency) |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` — markers `unit`, `mt5`; `addopts = '-m "not mt5"'` (existing, verified in Phase 1) |
| Quick run command | `uv run pytest -q` (unit only, no MT5, <30 s) |
| Full suite command | `uv run pytest -q -m "unit or mt5"` (mt5 tests unchanged from Phase 1; all Phase 2 tests are unit-marked) |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| SMC-01 | Strict 2/2 fractal: equal-price neighbor disqualifies; swing stamped at extreme bar; `confirmed_at` = confirmation-bar close time; tail 2 bars never emit | unit | `uv run pytest tests/unit/test_swings.py -q` | ❌ Wave 0 |
| SMC-01 (SC1) | Repaint: appending future bars (1-by-1 and chunked) never alters visible swings; zigzag only-tail-may-change rule; zones/pools immutable; standalone-vs-in-frame pool consistency | unit | `uv run pytest tests/unit/test_repaint.py -q` | ❌ Wave 0 |
| SMC-02 | Tolerance clustering `≤ 0.1×ATR(14)` per (symbol, TF) incl. exact-boundary case; 2-touch activation; ATR warmup NaN guard; empty-frame contract | unit | `uv run pytest tests/unit/test_pools.py -q` | ❌ Wave 0 |
| SMC-03 | Pierce + close-back within 2-bar inclusive window → `swept`; window expiry without reclaim → `broken`; identical pierce paths classified differently only by close-back timing | unit | `uv run pytest tests/unit/test_sweeps.py -q` | ❌ Wave 0 |
| SMC-04 | Each completed zigzag leg spawns zone with range high/low, equilibrium, leg direction; `created_at` = completing swing's confirmation | unit | `uv run pytest tests/unit/test_zones.py -q` | ❌ Wave 0 |
| SMC-05 | Bar-by-bar monotone lifecycles: zone `unmitigated→mitigated (wick)→invalidated (close beyond)`, wick-poke-beyond does NOT invalidate, same-bar double-stamp allowed; pool terminal states one-and-done | unit | `uv run pytest tests/unit/test_lifecycle.py -q` | ❌ Wave 0 |
| SMC-06 | Strictly-before confirmation join (`allow_exact_matches=False`); invariant `confirmed_at ≤ time_utc` on every joined row; bias/premium-discount mapping; DST +3→+2 H4-anchor continuity; lean payload field completeness | unit | `uv run pytest tests/unit/test_mtf_join.py -q` | ❌ Wave 0 |
| SC5 (integration) | Full chain swings→zigzag→pools→zones→MTF over synthetic multi-TF frames: no zone before leg completion; no payload before first HTF confirmation; pure functions (no MT5 imports — grep-checked) | unit (integration-style) | `uv run pytest tests/unit/test_detector_integration.py -q` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest -q` (unit suite, MT5-free, <30 s)
- **Per wave merge:** full `uv run pytest -q -m "unit or mt5"`
- **Phase gate:** full suite green + `uv run ruff check .` clean before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `src/ai_trading/detectors/` package skeleton (all six modules with correct output schemas, empty-frame contracts) — enables schema-asserting tests to be written first
- [ ] `tests/unit/test_swings.py` + `tests/unit/test_repaint.py` — SMC-01/SC1 (repaint suite FIRST, as the executable spec)
- [ ] `tests/unit/test_pools.py`, `tests/unit/test_sweeps.py` — SMC-02/03
- [ ] `tests/unit/test_zones.py`, `tests/unit/test_lifecycle.py` — SMC-04/05
- [ ] `tests/unit/test_mtf_join.py`, `tests/unit/test_detector_integration.py` — SMC-06 + SC5
- [ ] Detector-fixture helpers (swing/pool/zone sculptors over `make_bars`) — local to `tests/unit/`, do NOT extend root `conftest.py` (Phase 1 contract: downstream plans consume it without extending)
- [ ] Optional `Config` extension for detector params (fractal width, ATR period, tolerance multiple, sweep window) with locked D-values as defaults — planner decision

*(No existing test infrastructure covers any Phase 2 requirement — verified by file listing: no detector modules or detector tests exist yet.)*

## Security Domain

> `security_enforcement: true`, ASVS level 1, block-on high (config.json). Phase 2 is pure local computation: no network, no auth surface, no secrets, no persistence beyond caller-provided frames.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | N/A — no auth surface in pure detector functions |
| V3 Session Management | no | N/A |
| V4 Access Control | no | N/A — single-user local process |
| V5 Input Validation | **yes** | Detector entry guards: required columns present (`COLUMNS` subset check), monotonic strictly-increasing unique `time_utc`, finite OHLC (no NaN/inf in high/low/close), timeframe in `TIMEFRAME_MINUTES`; fail fast with actionable `ValueError` mirroring Phase 1's config-validation pattern |
| V6 Cryptography | no | N/A — never hand-roll crypto, ever |
| V7 Errors & Logging | **yes** | Explicit exception taxonomy for contract violations (malformed frames, unsorted inputs); never swallow NaN silently (Pitfall 7); no logging of data contents in exceptions beyond bounds info |
| V14 Config | partial | If planner extends `Config` with detector params (Wave 0 optional item): frozen-dataclass field validation with explicit bounds (period ≥ 1, tolerance multiple > 0, window ≥ 1); no secrets involved |

### Known Threat Patterns for {pure pandas detector stack}

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Lookahead bias (future data leaking into historical decisions) | Tampering / Repudiation (evidence integrity) | Point-in-time discipline as tested invariants: repaint suite (SC1), `confirmed_at ≤ time_utc` assertion on every joined row, as-of ATR only (Pitfall 3); this is the phase's security-grade correctness property — treat violations as build-breaking |
| NaN/inf poisoning propagating through detector outputs | Tampering | V5 input guards + `min_periods` warmup + explicit empty-frame contracts; tests feed NaN/short frames per detector |
| Schema drift between detector outputs and downstream consumers (Phase 3/4/6) | Tampering (interface) | Output schemas pinned in plan + schema-asserting tests in `test_detector_integration.py`; empty-frame outputs carry the full schema |
| Silent mutation of shared input frames under pandas 3.x CoW | Tampering | Detectors return new frames; never assign into `bars`; integration test asserts input frame equality before/after each detector call |

## Sources

### Primary (HIGH confidence)
- **Official pandas documentation via Context7** (`/websites/pandas_pydata`): `rolling(center=True)` + `Rolling.max/min/rank` (window user guide); `pandas.merge_asof` full parameter semantics + sorting requirement + `allow_exact_matches=False` "strictly prior" behavior (API reference + merging user guide); `DataFrame.ewm` `alpha`/`adjust=False`/`min_periods` recursion semantics (API reference)
- **Local probes (this session):** python 3.12.12, pandas 3.0.5, numpy 2.5.2, pytest 9.1.1, ruff 0.16.5; Phase 1 module contracts read from source (`normalize.py`, `stores/bar_store.py`, `tests/conftest.py`)

### Secondary (MEDIUM confidence)
- **Wikipedia — Average true range** [CITED: en.wikipedia.org/wiki/Average_true_range]: TR definition, Wilder recursion `ATR_t = (ATR_{t-1}(n−1)+TR_t)/n`, α=1/14, SMA-of-first-n seed, 14-period recommendation — cross-checked with pandas `ewm` docs (two-source agreement → treated as HIGH for the formula itself)
- **smartmoneyconcepts v0.0.27 full source + README** [CITED: github.com/joshyattridge/smart-money-concepts]: swing/liquidity/BOS-CHoCH/previous-high-low implementation semantics; verified negative examples (repainting centered swings, `==` ties, full-frame-range tolerance lookahead, period-boundary point-in-time lookup)

### Tertiary (LOW confidence)
- Web-search engines (SearXNG) were unavailable during this session (all engines rate-limited/CAPTCHA-blocked; verified via instance status). Claims that would normally cite community discussion (fractal-indicator conventions, general lookahead-bias literature) are instead grounded in the verified reference implementation and first-principles derivation from the locked D-01..D-15 decisions, and are tagged `[ASSUMED]` where they go beyond those sources. No claim in this document rests solely on unverified web content.

## Metadata

**Confidence breakdown:**
- Standard stack: **HIGH** — no new dependencies; all versions probed live; pandas primitives verified from official docs via Context7
- Architecture (detector patterns + MTF join): **HIGH** — every pattern maps to verified pandas semantics; zigzag/pool/zone logic derived from locked decisions with reference-implementation cross-check
- Pitfalls: **HIGH** for the lookahead class (concrete verified library bug + merge_asof docs); **MEDIUM** for convention pins (sweep window counting, boundary inclusivity) which are discretion-locked in the Assumptions Log
- SMC domain semantics: **MEDIUM** — grounded in the locked CONTEXT decisions (authoritative for this project) + one full reference audit; community literature was unreachable this session

**Research date:** 2026-08-31
**Valid until:** 2026-09-30 (stable domain — pandas 3.x line and locked semantics; re-verify only if pandas minor version bumps)
