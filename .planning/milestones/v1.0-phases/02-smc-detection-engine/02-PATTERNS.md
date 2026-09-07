# Phase 2: SMC Detection Engine - Pattern Map

**Mapped:** 2026-08-31
**Files analyzed:** 17 (7 new detector-package files, 1 modified existing file, 1 test-fixture helper, 8 test modules)
**Analogs found:** 17 / 17

> **Context:** Unlike Phase 1 (greenfield), real code now exists. The in-repo **pattern-of-record for every new module is `src/ai_trading/normalize.py`** — pure DataFrame→DataFrame transforms, zero MetaTrader5 imports, module-docstring hard rules, `from __future__ import annotations`, `df.copy()` non-mutation discipline. Detector *algorithms* have no in-repo analog (none exist yet), so each detector file pairs an in-repo **style analog** with a RESEARCH.md **algorithm pattern** (verified Patterns 1–6, lines 217–359) that the planner must copy into plan actions verbatim.

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `src/ai_trading/detectors/__init__.py` | package marker | n/a | `src/ai_trading/__init__.py`, `src/ai_trading/stores/__init__.py` | role-match |
| `src/ai_trading/detectors/atr.py` | utility (pure Series math) | transform | `normalize.py` (pure transforms) + RESEARCH Pattern 2 | role-match |
| `src/ai_trading/detectors/swings.py` | pure detector (vectorized transform) | transform (DataFrame→DataFrame) | `normalize.py` + RESEARCH Pattern 1 | role-match |
| `src/ai_trading/detectors/zigzag.py` | pure detector (sequential loop) | transform (event-sparse sequential) | `history_report.compute_gaps` (explicit loop over events) + RESEARCH Pattern 3 | role-match |
| `src/ai_trading/detectors/pools.py` | pure detector (state machine) | transform + event-driven (bar-by-bar) | `compute_gaps` loop style + RESEARCH Pattern 4 | role-match |
| `src/ai_trading/detectors/zones.py` | pure detector (state machine) | transform + event-driven (bar-by-bar) | `compute_gaps` loop style + RESEARCH Pattern 5 | role-match |
| `src/ai_trading/detectors/mtf.py` | pure detector (as-of join) | transform (sorted-key join) | `collector.py` point-in-time discipline + RESEARCH Pattern 6 | role-match |
| `src/ai_trading/config.py` (modified) | config (frozen dataclass + validation) | transform | itself — extend the existing pattern | exact |
| `tests/unit/_detector_fixtures.py` (name at planner discretion) | test fixture helper (sculptors over `make_bars`) | transform/factory | `tests/conftest.py` `make_bars` + local `_bars` helpers in existing test modules | exact |
| `tests/unit/test_swings.py` | test (unit) | transform | `tests/unit/test_normalize_and_config.py` | exact |
| `tests/unit/test_repaint.py` | test (unit, SC1 centerpiece) | transform (point-in-time immutability) | `tests/unit/test_timezone_dst.py` (contract-locking test style) + RESEARCH repaint recipe | exact |
| `tests/unit/test_pools.py` | test (unit) | transform | `tests/unit/test_idempotent_store.py` (assert_frame_equal style) | exact |
| `tests/unit/test_sweeps.py` | test (unit) | event-driven classification | `tests/unit/test_idempotent_store.py` | exact |
| `tests/unit/test_zones.py` | test (unit) | transform | `tests/unit/test_normalize_and_config.py` | exact |
| `tests/unit/test_lifecycle.py` | test (unit) | event-driven (state transitions) | `tests/unit/test_idempotent_store.py` | exact |
| `tests/unit/test_mtf_join.py` | test (unit) | transform (join invariants + DST) | `tests/unit/test_timezone_dst.py` | exact |
| `tests/unit/test_detector_integration.py` | test (unit, integration-style SC5) | transform (end-to-end chain) | `tests/unit/test_idempotent_store.py` (cross-module chain tests) | exact |

**Provenance of the file list:** RESEARCH.md "Recommended Project Structure" (lines 190–213) defines the detector package + 8 test modules; "Wave 0 Gaps" (lines 558–567) adds the fixture-helper module and the optional `Config` extension; CONTEXT.md Discretion leaves module layout/naming to the planner.

---

## Pattern Assignments

### `src/ai_trading/detectors/` package (all 7 files) — style-of-record

**Analog:** `src/ai_trading/normalize.py` — the proven "pure module" template. Every detector module copies this skeleton.

**Module docstring with hard rules + import block** (normalize.py lines 1–23):
```python
"""Pure UTC normalization transforms — the single source of truth for time math
(DATA-03). This module MUST NOT import or reference the MetaTrader5 package;
it operates on plain numpy structured arrays / DataFrames so it is unit-testable
with zero terminal dependency.

Hard rules (RESEARCH.md Pitfall 1 + Pitfall 7, PATTERNS "normalize.py"):
- ...
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pandas as pd
```
**Copy convention:** detector module docstrings cite the locked D-decisions they encode (e.g. swings.py → "D-01/D-02/D-03/D-04") and name the RESEARCH pattern implemented, exactly as `bar_store.py` (lines 1–10) and `collector.py` (lines 5–19) cite "Pattern of record:" sources. `from __future__ import annotations` first, stdlib imports, blank line, `import pandas as pd` (numpy only when masks need it), blank line, `from ai_trading.normalize import ...`.

**Non-mutation / copy-at-entry** (normalize.py `rederive_time_utc`, lines 66–79):
```python
def rederive_time_utc(df: pd.DataFrame, old_offset: int, new_offset: int) -> pd.DataFrame:
    """Re-derive ``time_utc`` from the RAW server-wall ``time`` column using
    ``new_offset``; return a copy, leaving the raw column untouched.
    ...
    Pure function; no MetaTrader5 import.
    """
    out = df.copy()
    out["time_utc"] = out["time"] - pd.Timedelta(hours=new_offset)
    return out
```
**Rule:** every detector that derives from `bars` works on `bars.copy()` or builds a fresh output frame; never assign into the input (RESEARCH Anti-Pattern "Mutating input frames", line 369; integration test must assert input-frame equality before/after each call).

**Fail-fast guard with actionable ValueError** (normalize.py `assert_closed_bars`, lines 82–98):
```python
    if df.empty:
        return
    ...
    if max_utc >= floor:
        raise ValueError(
            f"closed-bar invariant violated: max time_utc {max_utc} is at or after "
            f"the current {timeframe} floor {floor} — the forming bar must never be stored"
        )
```
**Copy convention (Security V5, RESEARCH line 580):** each detector entry validates — required columns present (COLUMNS subset), `time_utc` strictly increasing/unique, finite OHLC, `timeframe in TIMEFRAME_MINUTES` — and raises `ValueError` naming the violated invariant, mirroring this excerpt and `config._validate`'s field-naming style.

**TF constants reused, never re-derived** (normalize.py lines 26–39):
```python
COLUMNS = [...]
TIMEFRAME_MINUTES = {"M15": 15, "H1": 60, "H4": 240}
```
**Rule (Pitfall 8, RESEARCH lines 428–431):** detectors import `TIMEFRAME_MINUTES` (fractal width 2, sweep window 2, confirmation close = `time_utc.shift(-2) + Timedelta(minutes=TIMEFRAME_MINUTES[tf])`) and **never call `floor_to_timeframe` on stored bar times** — stored bars are already on-grid; re-flooring invites DST-anchor drift.

---

### `src/ai_trading/detectors/atr.py` (utility, transform)

**Analog:** `normalize.py` (module style) + **RESEARCH Pattern 2** (lines 252–272).

**Algorithm core to copy** (RESEARCH.md lines 259–271, verified):
```python
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
**Copy rules:** always `adjust=False` (RESEARCH "Deprecated/outdated", line 481 — default `adjust=True` is NOT Wilder); keep `min_periods=period` so warmup is NaN and callers skip (Pitfall 7); document the seed nuance in the module docstring (Research Open Question 2).

---

### `src/ai_trading/detectors/swings.py` (pure detector, vectorized transform)

**Analog:** `normalize.py` (module style) + **RESEARCH Pattern 1** (lines 217–250).

**Algorithm core to copy** (RESEARCH.md lines 226–248, verified):
```python
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
**Copy rules:** strict `>` / `<` only — no `>=`/`==` anywhere (D-02, Anti-Pattern line 364); NaN tail disqualifies the last 2 rows automatically; output schema is exactly `(symbol, timeframe, bar_time, price, side, confirmed_at)` (D-03); pin the same-bar dual-swing (high+low) deterministic order — recommended emit `high` then `low` (Pitfall 6 / A9) — in a named test.

---

### `src/ai_trading/detectors/zigzag.py` (pure detector, sequential loop)

**Analog:** `history_report.compute_gaps` for the explicit-loop-over-sparse-events style + **RESEARCH Pattern 3** (lines 274–301).

**In-repo loop-style excerpt** (history_report.py lines 170–178 — clear, auditable sequential logic over sparse events; do not contort into vector form):
```python
    gaps: list[tuple[pd.Timestamp, pd.Timestamp]] = []
    i = 0
    while i < len(missing):
        j = i
        while j + 1 < len(missing) and missing[j + 1] - missing[j] == step_delta:
            j += 1
        gaps.append((missing[i], missing[j] + step_delta))
        i = j + 1
    return gaps
```

**Algorithm core to copy** (RESEARCH.md lines 282–299, locked D-04 semantics):
```python
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
**Copy rule (repaint tier 2):** the REPLACE branch mutates only the zigzag *tail* — entries before the final leg are immutable; zones consume only completed legs (CONTEXT specifics + Pitfall 2).

---

### `src/ai_trading/detectors/pools.py` (pure state machine, event-driven)

**Analog:** `compute_gaps` loop style + **RESEARCH Pattern 4** (lines 303–324).

**Algorithm core to copy** (RESEARCH.md lines 310–323, locked D-05..D-08):
```python
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
**Copy rules (pin in plan):** tolerance = `0.1 × wilders_atr(...)` evaluated **as-of the joining swing's `confirmed_at`** — never full-frame statistics (Pitfall 3; the reference library's `high.max() − low.min()` is the verified lookahead bug); cluster membership inclusive `≤ tol` (A3); pool level = mean of member prices (A3); 2 touches activate (D-06); window = pierce bar's close + next bar's close (A8); terminal states final, one-and-done (D-08); ordering per bar = cluster-confirm first, then event checks (Pitfall 6); skip clustering until ATR is finite (Pitfall 7).

---

### `src/ai_trading/detectors/zones.py` (pure state machine, event-driven)

**Analog:** `compute_gaps` loop style + **RESEARCH Pattern 5** (lines 326–342).

**Algorithm core to copy** (RESEARCH.md lines 332–341, locked D-09..D-12):
```python
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
**Copy rules:** one zone per completed zigzag leg, `created_at` = completing swing's confirmation (D-09); `equilibrium = (high+low)/2` carried on the record; wick-touch mitigates (D-10), committed close beyond far boundary invalidates (D-11 — wick pokes do NOT); lifecycle monotone `unmitigated → mitigated → invalidated`, one bar may stamp both timestamps (pin order: mitigation check then invalidation check, Pitfall 6); zones never deleted — full history retained (D-12); zone records carry `range_high/range_low/equilibrium/leg_direction/state/created_at/mitigated_at/invalidated_at` (+ ID scheme at planner discretion).

---

### `src/ai_trading/detectors/mtf.py` (pure join, transform)

**Analog:** `collector.py` point-in-time discipline (in-repo) + **RESEARCH Pattern 6** (lines 344–359).

**In-repo point-in-time discipline excerpt** (collector.py `fetch_closed_bars` docstring, lines 126–133 — the shared-path lookahead-safety root the join extends):
```python
    """Fetch CLOSED bars for (symbol, timeframe) as the canonical bar frame.

    start_pos MUST be literally 1: position 0 is the still-forming bar and is
    never fetched or stored (research-verified; the project's look-ahead-safety
    root for this shared code path). ...
    """
```
and the defensive-trim idiom (collector.py lines 369–375):
```python
    # Defensive trim: drop rows at/after the current timeframe floor (the
    # forming bar that an inclusive range fetch can carry).
    trim_now = now_utc if now_utc is not None else datetime.now(UTC)
    ...
    df = df[df["time_utc"] < floor]
```

**Algorithm core to copy** (RESEARCH.md lines 350–359, locked D-13..D-15):
```python
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
**Copy rules:** HTF state timeline keyed on **confirmation timestamps** (`created_at`/transitions), never HTF bar-open time, never "latest HTF row" (D-15, Pitfall 1); explicit `sort_values` immediately before `merge_asof` (Pitfall 9); bias from joined range — `close > equilibrium → bearish (premium)`, `close < equilibrium → bullish (discount)`, `close == equilibrium → neutral` (pin the equal case, A9); lean payload = bias, range high/low/equilibrium, distance-to-equilibrium in M15 ATR units (A1, signed), IDs of live HTF zones whose range contains the M15 close (A2) via small cross-join filter; no HTF pool/sweep payload in v1 (D-14).

---

### `src/ai_trading/config.py` (modified — optional Config extension, planner decision)

**Analog:** itself — extend the established frozen-dataclass + fail-fast pattern.

**Existing pattern to extend** (config.py lines 48–64 and `_validate` excerpt lines 145–151):
```python
@dataclass(frozen=True)
class Config:
    symbols: tuple[str, ...]
    timeframes: tuple[str, ...]
    ...
    initial_backfill_days: int
```
```python
    for name, value in (
        ("min_maxbars", cfg.min_maxbars),
        ("lookback_bars", cfg.lookback_bars),
        ("initial_backfill_days", cfg.initial_backfill_days),
    ):
        if not _is_int(value) or value <= 0:
            raise ValueError(f"{name} must be a positive integer, got {value!r}")
```
**Copy rule (Security V14, RESEARCH line 583):** if detector params are added (`fractal_width`, `atr_period`, `tolerance_atr_multiple`, `sweep_window_bars`), give each explicit bounds validation in `_validate` (period ≥ 1, multiple > 0, window ≥ 1) with locked D-values as defaults; note `_ALLOWED_TIMEFRAMES = frozenset({"M15", "H1", "H4"})` (line 27) is the existing TF whitelist to reuse, and `tomllib`-free `_make_cfg` overrides in `tests/conftest.py` (lines 63–84) must gain matching defaults if fields are added. Alternative: keep detector params as function defaults — no Config change at all (RESEARCH Wave 0 marks this optional).

---

### Test files (8 modules + fixture helper)

**Analog:** existing unit modules — exact role + data-flow matches. Structure-of-record from `test_normalize_and_config.py` lines 1–17 and 80–90:

**Module skeleton, helpers, markers** (test_normalize_and_config.py):
```python
"""Unit tests (DATA-03 foundation): config loader/validation + pure UTC
normalization. No MT5 import anywhere."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from ai_trading.config import load_config
from ai_trading.normalize import COLUMNS, rates_to_dataframe

# MT5 copy_rates* structured-array dtype (...) — module-level constants/helpers
def _server_epoch_seconds(naive_server_wall: datetime) -> int:
    """..."""
    ...

# ---------------------------------------------------------------------------
# UTC normalization math (DATA-03)
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_offset_three_maps_server_wall_to_true_utc():
    """Plan success criterion: server 2026-08-29 00:00 -> time_utc 2026-08-28 21:00."""
    ...
```
**Copy conventions:** module docstring names the requirement IDs covered ("SMC-01 …", "SC1 repaint") and states "no MT5 import anywhere" (SC5 requires detectors grep-clean of MetaTrader5); **`@pytest.mark.unit` on every test** (pyproject.toml lines 19–25: markers `unit`/`mt5`, `addopts = '-m "not mt5"'`; all Phase 2 tests are unit-marked); `_`-prefixed local helpers; `# ---` section banners grouping by behavior; docstrings cite the plan success criterion; `pytest.raises(ValueError, match="...")` for guard tests (lines 163, 196–197).

**Factory + local-sculptor pattern** — `tests/conftest.py` `make_bars` (lines 26–60) is the basis, consumed **without extending conftest** (Phase 1 contract, RESEARCH Wave 0 line 564). Existing per-module helper style to copy (test_idempotent_store.py lines 104–107):
```python
def _bars(count: int, start: datetime = START) -> pd.DataFrame:
    from conftest import make_bars

    return make_bars("EURUSD", "M15", start, count, offset_hours=3)
```
plus module-level clock constants (lines 22–23):
```python
START = datetime(2026, 8, 20, 0, 0)
NOW_UTC = datetime(2026, 8, 30, 12, 0, tzinfo=UTC)
```
**Rule:** put swing/pool/zone **sculptors** (helpers that override `make_bars` highs/lows to shape known swings, equal-level clusters, pierce-and-reclaim paths) in a new `tests/unit/_detector_fixtures.py` (name at planner discretion) or module-local helpers — never in root conftest.py.

**Frame-equality assertions** (test_idempotent_store.py lines 56–64 — the idempotency/immutability assertion style the repaint suite generalizes):
```python
    first = read_bars(path)
    n = merge_and_write(new, path, "M15", now_utc=NOW_UTC)
    second = read_bars(path)
    assert n == len(first) == len(second) == 10
    pd.testing.assert_frame_equal(first, second)
```

**DST/point-in-time contract-test style** (test_timezone_dst.py lines 132–143 — docstring-heavy contract locking that `test_mtf_join.py`'s DST H4-anchor test and `test_repaint.py` mirror):
```python
@pytest.mark.unit
def test_dst_transition_flags_misaligned_rows_and_rederivation_fixes_them():
    """Broker offset changes 2->3 mid-series (US DST begins; per the confirmed
    IC Markets policy). ... """
    true_opens = pd.date_range("2026-08-24 00:00", periods=480, freq="15min")  # Mon-Fri
    transition_at = 240  # offset changes 2->3 after Mon+Tue (Wed 00:00 UTC)
    offsets = np.array([2] * transition_at + [3] * (480 - transition_at))
    raw = pd.DatetimeIndex(true_opens) + pd.to_timedelta(offsets, unit="h")  # server wall
```

**Repaint suite algorithm (SC1 centerpiece)** — copy RESEARCH.md "Repaint / point-in-time test recipe" (lines 447–468) verbatim as the executable spec, written FIRST (plan 02-01). Two-tier contract per Pitfall 2: (T1) swing records strictly immutable; (T2) zigzag rows immutable except the final point, replaceable only by a more-extreme same-side confirmation; (T3) zones/pools/sweeps from completed legs strictly immutable; plus standalone-vs-in-frame pool consistency (Pitfall 3) and the joined-row invariant `confirmed_at ≤ time_utc` (Pitfall 9). Per-requirement test files map 1:1 to the Validation Architecture test map (RESEARCH lines 541–551).

**Empty/short-frame contract tests** — mirror the verified empty-return pattern (history_report.py `compute_gaps` lines 161–162 and `bar_store.read_bars` lines 28–33):
```python
    if df.empty:
        return []
```
```python
def read_bars(path: Path) -> pd.DataFrame:
    """Read a bar file; missing file -> empty frame with the canonical columns."""
    ...
    return pd.DataFrame(columns=COLUMNS)
```
Every detector gets a named test: empty frame → correct output schema (full columns, zero rows); short frame (< fractal width, < ATR warmup) → no events (Pitfall 10).

---

## Shared Patterns

### 1. Purity: zero MetaTrader5 imports, zero file I/O in detectors
**Source:** `normalize.py` (lines 1–4, 75), ROADMAP SC5; `bar_store.read_bars` is the ONLY input path and belongs to the caller/integration layer, never inside detectors (CONTEXT integration points).
**Apply to:** all 7 `detectors/` files. Modules operate on frames and return frames; `read_bars` is invoked by whatever orchestrates the chain (plan 02-04 integration test wires it explicitly).

### 2. Non-mutation under pandas 3.x CoW
**Source:** `normalize.rederive_time_utc` (lines 77–79); RESEARCH Anti-Pattern (line 369).
**Apply to:** all detectors — `bars.copy()` at entry or fresh output frames; integration test asserts input equality before/after every detector call.

### 3. Empty/short-frame early return with full output schema
**Source:** `history_report.compute_gaps` (lines 161–162), `bar_store.read_bars` (lines 28–33).
**Apply to:** every detector module + a named test per detector (Pitfall 10).

### 4. Fail-fast ValueError guards naming the violated invariant
**Source:** `normalize.assert_closed_bars` (lines 94–98), `config._validate` (lines 114–151); Security V5 (RESEARCH line 580).
**Apply to:** all detector entry points — COLUMNS-subset check, monotonic unique `time_utc`, finite OHLC, timeframe in `TIMEFRAME_MINUTES`.

### 5. Reuse normalize.py primitives — never duplicate tz/TF logic
**Source:** `normalize.py` `COLUMNS`/`TIMEFRAME_MINUTES` (lines 26–39); Pitfall 8 (no `floor_to_timeframe` inside detectors — the H4 lattice is the 21:00-UTC server-midnight anchor, verified in Phase 1).
**Apply to:** swings (confirmation close = shift(-2) + TF), pools (2-bar window), mtf (join keys on raw `time_utc` values).

### 6. Point-in-time discipline (the phase's security-grade property)
**Source:** `collector.fetch_closed_bars` docstring (lines 126–133) + defensive trim (lines 369–375); RESEARCH Pitfall 1; Security threat table (RESEARCH line 589).
**Apply to:** swings (`confirmed_at` stamping), pools (as-of ATR tolerance), mtf (`allow_exact_matches=False`); violations are build-breaking — repaint suite is the enforcement mechanism.

### 7. Test layering & markers (unchanged from Phase 1)
**Source:** `pyproject.toml` (lines 19–32), `tests/conftest.py` header (lines 1–12); RESEARCH Validation Architecture (lines 533–539).
**Apply to:** all 8 new test modules — `@pytest.mark.unit` everywhere; root conftest consumed, never extended (sculptors live in `tests/unit/` local helpers); per-task `uv run pytest -q`, per-wave `-m "unit or mt5"`, `uv run ruff check .` (line-length 100, target py312) clean at phase gate.

---

## No Analog Found

No file lacks an analog, but the **detector algorithm cores have no in-repo functional analog** (no detector code exists). For each, the algorithm body is copied from the verified RESEARCH pattern — never improvised:

| File | Role | Data Flow | Reason algorithm comes from RESEARCH |
|------|------|-----------|----------------------------------------|
| `detectors/swings.py` | pure detector | transform | No swing/fractal code exists; RESEARCH Pattern 1 (lines 217–250) is the verified implementation of D-01/D-02 |
| `detectors/zigzag.py` | pure detector | sequential transform | No zigzag code exists; RESEARCH Pattern 3 (lines 274–301) encodes D-04 |
| `detectors/pools.py` | pure state machine | event-driven | No pool/sweep code exists; RESEARCH Pattern 4 (lines 303–324) encodes D-05..D-08 |
| `detectors/zones.py` | pure state machine | event-driven | No zone-lifecycle code exists; RESEARCH Pattern 5 (lines 326–342) encodes D-09..D-12 |
| `detectors/mtf.py` | pure join | as-of transform | No MTF join exists; RESEARCH Pattern 6 (lines 344–359) encodes D-13..D-15 |
| `detectors/atr.py` | utility | transform | No ATR code exists; RESEARCH Pattern 2 (lines 252–272) is the verified 6-line composition |

**Deliberate hand-roll note (RESEARCH "Don't Hand-Roll" counter-point, lines 381–385):** the locked D-01..D-15 semantics ARE the product's IP — the `smartmoneyconcepts` reference library is negative-evidence only (repainting centered swings, `==` ties, full-frame-range tolerance lookahead, no reclaim rule/lifecycle/as-of join). Hand-rolling applies to the SMC semantics layer only; infrastructure (joins, smoothing, windows) uses verified pandas primitives per the RESEARCH table.

---

## Metadata

**Analog search scope:** `src/ai_trading/` (9 modules), `tests/` (unit + integration + conftest), `pyproject.toml`, `.planning/phases/01-data-foundation/01-PATTERNS.md`
**Files scanned:** 13 in-repo files read (normalize.py, config.py, bar_store.py, collector.py, history_report.py §compute_gaps, conftest.py, test_normalize_and_config.py, test_idempotent_store.py, test_timezone_dst.py, pyproject.toml, 01-PATTERNS.md; mt5_client.py and meta_store.py excluded — adapter/storage tiers untouched by Phase 2)
**Pattern extraction date:** 2026-08-31
**Downstream notes for the planner:** (1) RESEARCH.md Patterns 1–6 code excerpts are verified and copy-ready — embed them in plan actions alongside the in-repo style analogs above; (2) assumptions A1–A11 (RESEARCH lines 483–499) pin discretion items (pool level = mean, inclusive tolerance, sweep window = pierce bar + next bar, dual-swing order high-then-low, neutral at exact equilibrium) — each pinned rule needs a named test (Pitfall 6); (3) plan 02-01 writes the repaint suite FIRST as the executable spec.
