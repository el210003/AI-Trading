"""Liquidity-pool detection and sweep/breakout classification
(SMC-02, SMC-03, pool half of SMC-05).

Pattern of record: RESEARCH.md Pattern 4 (cluster-then-classify state machine,
explicit sequential loops over sparse events — deliberately not vectorized).

Hard rules (locked decisions):
- D-05: clustering tolerance = ``tolerance_atr_multiple x wilders_atr``
  evaluated AS-OF each joining swing's confirmation bar — never full-frame
  statistics (Pitfall 3: the reference library's full-range tolerance is a
  verified lookahead bug). Membership is inclusive (A3).
- D-06: 2 clustered touches activate a pool; level = mean of the two
  activating touch prices, FROZEN at activation — later within-tolerance
  swings increment ``touch_count`` without moving the level (A3).
- A5: a pierce while a candidate is still forming (1 touch) emits no event;
  the candidate stays ``forming`` and is dead — later equal-level swings open
  fresh candidates.
- D-07: sweep = wick pierce (high-side: bar high strictly above level; low
  mirror) AND a close back on the original side within the 2-bar INCLUSIVE
  window = the pierce bar's close plus the next bar's close (A8). Window
  expiry without close-back -> plain breakout, pool ``broken``.
- D-08: one-and-done — terminal states ``swept``/``broken`` are final; a
  resolved pool is never re-checked; post-resolution equal-level swings start
  new candidates (fresh pool_ids).
- Pitfall 6: per-bar ordering = cluster-confirm first, then event checks — a
  pool activating on the bar its level is pierced is classified normally.
- Pitfall 7: clustering skips while the as-of ATR is NaN (warmup) — the
  first ~atr_period bars produce no pool activity.
- Point-in-time pierce semantics: ANY bar whose wick crosses the level
  pierces (including bars that happen to be swing extremes) — deterministic
  under recompute. A cluster member on the original side of the level (price
  at/below a high pool's level) does not pierce; a rising touch's own extreme
  bar pierces a forming candidate and supersedes it (A5).
- Frame-end contract: a pool still inside its reclaim window when the frame
  ends stays ``active`` and unresolved (no event) — classification requires
  the full window.
- ``sweep_window_bars`` is pinned to 2 by A8 (pierce bar's close + next
  bar's close); the parameter exists for signature fidelity.
- Zero adapter-tier imports, zero file I/O; input frames never mutated;
  stored ``time_utc`` consumed as-is (no grid re-flooring, Pitfall 8).
"""

from __future__ import annotations

import pandas as pd

from ai_trading.detectors.atr import wilders_atr
from ai_trading.normalize import TIMEFRAME_MINUTES

POOL_COLUMNS = [
    "pool_id",
    "symbol",
    "timeframe",
    "side",
    "level",
    "touch_count",
    "state",
    "first_touch_at",
    "activated_at",
    "resolved_at",
]

EVENT_COLUMNS = [
    "event_id",
    "pool_id",
    "symbol",
    "timeframe",
    "side",
    "level",
    "pierced_at",
    "resolved_at",
    "event_type",
]

_REQUIRED_BARS = ("symbol", "time_utc", "open", "high", "low", "close")
_REQUIRED_SWINGS = ("symbol", "timeframe", "bar_time", "price", "side", "confirmed_at")

_STR_DTYPE = pd.StringDtype()


def _empty_pools_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "pool_id": pd.Series(dtype=_STR_DTYPE),
            "symbol": pd.Series(dtype=_STR_DTYPE),
            "timeframe": pd.Series(dtype=_STR_DTYPE),
            "side": pd.Series(dtype=_STR_DTYPE),
            "level": pd.Series(dtype="float64"),
            "touch_count": pd.Series(dtype="int64"),
            "state": pd.Series(dtype=_STR_DTYPE),
            "first_touch_at": pd.Series(dtype="datetime64[us]"),
            "activated_at": pd.Series(dtype="datetime64[us]"),
            "resolved_at": pd.Series(dtype="datetime64[us]"),
        }
    )


def _empty_events_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "event_id": pd.Series(dtype=_STR_DTYPE),
            "pool_id": pd.Series(dtype=_STR_DTYPE),
            "symbol": pd.Series(dtype=_STR_DTYPE),
            "timeframe": pd.Series(dtype=_STR_DTYPE),
            "side": pd.Series(dtype=_STR_DTYPE),
            "level": pd.Series(dtype="float64"),
            "pierced_at": pd.Series(dtype="datetime64[us]"),
            "resolved_at": pd.Series(dtype="datetime64[us]"),
            "event_type": pd.Series(dtype=_STR_DTYPE),
        }
    )


def _validate_bars(bars: pd.DataFrame) -> None:
    missing = [c for c in _REQUIRED_BARS if c not in bars.columns]
    if missing:
        raise ValueError(
            f"detect_pools invariant violated: bars is missing required columns {missing}"
        )
    # Multi-symbol frames are time-monotonic and unique per symbol, not
    # globally — combined frames legitimately repeat timestamps across symbols.
    for _, sym_bars in bars.groupby("symbol", sort=False):
        t = sym_bars["time_utc"]
        if not t.is_monotonic_increasing or not t.is_unique:
            raise ValueError(
                "detect_pools invariant violated: bars time_utc must be strictly "
                "increasing and unique within each symbol"
            )
    for col in ("open", "high", "low", "close"):
        if not bars[col].notna().all():
            raise ValueError(
                f"detect_pools invariant violated: bars column '{col}' must be finite"
            )


def _validate_swings(swings: pd.DataFrame) -> None:
    missing = [c for c in _REQUIRED_SWINGS if c not in swings.columns]
    if missing:
        raise ValueError(
            f"detect_pools invariant violated: swings is missing required columns {missing}"
        )
    unknown = set(swings["side"].dropna().unique()) - {"high", "low"} if len(swings) else set()
    if unknown:
        raise ValueError(
            f"detect_pools invariant violated: swing side values must be 'high' or "
            f"'low', got {sorted(unknown)}"
        )


def _close_back(side: str, close: float, level: float) -> bool:
    """True when the bar's close is back on the ORIGINAL side of the level."""
    return close < level if side == "high" else close > level


def _pierces(side: str, bar: pd.Series, level: float) -> bool:
    """True when the bar's wick crosses the level (strictly)."""
    return bar["high"] > level if side == "high" else bar["low"] < level


def _emit(pool: dict, pierced_at, resolved_at, event_type: str) -> dict:
    return {
        "event_id": f"{pool['pool_id']}-E1",
        "pool_id": pool["pool_id"],
        "symbol": pool["symbol"],
        "timeframe": pool["timeframe"],
        "side": pool["side"],
        "level": pool["level"],
        "pierced_at": pierced_at,
        "resolved_at": resolved_at,
        "event_type": event_type,
    }


def _detect_for_symbol(
    sym_bars: pd.DataFrame,
    sym_swings: pd.DataFrame,
    atr_period: int,
    tolerance_atr_multiple: float,
) -> tuple[list[dict], list[dict]]:
    """Run the cluster-then-classify timeline for one symbol; returns
    (all candidate/pool dicts in creation order, event dicts in resolution
    order)."""
    tf = str(sym_swings["timeframe"].iloc[0])
    tf_delta = pd.Timedelta(minutes=TIMEFRAME_MINUTES[tf])
    atr = wilders_atr(sym_bars, atr_period).reset_index(drop=True)
    times = sym_bars["time_utc"].reset_index(drop=True)

    # Swings grouped by confirmation close time, in deterministic order.
    ordered = sym_swings.sort_values(
        ["confirmed_at", "bar_time", "side"], kind="mergesort"
    )
    due: dict[pd.Timestamp, list] = {}
    for row in ordered.itertuples(index=False):
        due.setdefault(row.confirmed_at, []).append(row)

    all_pools: list[dict] = []  # every candidate ever opened, creation order
    open_candidates: dict[str, list[dict]] = {"high": [], "low": []}
    events: list[dict] = []
    activation_counter = 0

    for i in range(len(sym_bars)):
        close_time = times.iloc[i] + tf_delta
        bar = sym_bars.iloc[i]

        # -- 1) cluster-confirm due at this bar's close (Pitfall 6: first) --
        for swing in due.get(close_time, []):
            side = swing.side
            atr_val = atr.iloc[i]
            if pd.isna(atr_val):
                continue  # Pitfall 7: warmup — no pool activity yet
            tolerance = tolerance_atr_multiple * atr_val
            candidates = open_candidates[side]
            target = None
            for cand in reversed(candidates):
                if cand["open"]:
                    target = cand
                    break
            if target is not None and abs(swing.price - target["level"]) <= tolerance:
                target["touch_count"] += 1
                if target["state"] == "forming":
                    # 2-touch activation (D-06): level = mean, frozen (A3).
                    target["state"] = "active"
                    target["level"] = (target["level"] + swing.price) / 2.0
                    target["activated_at"] = close_time
                    target["pierced_pending"] = False
                    activation_counter += 1
                    target["pool_id"] = f"{swing.symbol}-{tf}-P{activation_counter:04d}"
                # active pools: touch_count increments, level frozen (A3)
            else:
                cand = {
                    "open": True,
                    "state": "forming",
                    "pool_id": None,
                    "symbol": swing.symbol,
                    "timeframe": tf,
                    "side": side,
                    "level": float(swing.price),
                    "touch_count": 1,
                    "first_touch_at": close_time,
                    "activated_at": pd.NaT,
                    "resolved_at": pd.NaT,
                }
                open_candidates[side].append(cand)
                all_pools.append(cand)

        # -- 2) resolve pools pierced on an earlier bar (window's 2nd close) --
        for pool in all_pools:
            if pool["state"] != "active" or not pool["pierced_pending"]:
                continue
            reclaimed = _close_back(pool["side"], bar["close"], pool["level"])
            event_type = "sweep" if reclaimed else "breakout"
            pool["state"] = "swept" if reclaimed else "broken"
            pool["resolved_at"] = times.iloc[i]
            pool["open"] = False
            events.append(_emit(pool, pool["pierced_at"], times.iloc[i], event_type))

        # -- 3) fresh pierce checks on active pools (incl. just-activated) --
        for pool in all_pools:
            if pool["state"] != "active" or pool["pierced_pending"]:
                continue
            if _pierces(pool["side"], bar, pool["level"]):
                if _close_back(pool["side"], bar["close"], pool["level"]):
                    # close-back on the pierce bar itself (first window close)
                    pool["state"] = "swept"
                    pool["resolved_at"] = times.iloc[i]
                    pool["open"] = False
                    events.append(
                        _emit(pool, times.iloc[i], times.iloc[i], "sweep")
                    )
                elif i + 1 < len(sym_bars):
                    # window stays open: next bar's close is the 2nd close (A8)
                    pool["pierced_pending"] = True
                    pool["pierced_at"] = times.iloc[i]
                # else: frame ends inside the window — pool stays active,
                # unresolved (no event); documented contract.

        # -- 4) forming candidates: pierce while forming -> dead (A5) --
        for side in ("high", "low"):
            for cand in open_candidates[side]:
                if cand["open"] and cand["state"] == "forming":
                    if _pierces(side, bar, cand["level"]):
                        cand["open"] = False  # dead-by-supersession, stays forming

    return all_pools, events


def detect_pools(
    bars: pd.DataFrame,
    swings: pd.DataFrame,
    atr_period: int = 14,
    tolerance_atr_multiple: float = 0.1,
    sweep_window_bars: int = 2,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Cluster confirmed swings into equal-high/low liquidity pools and
    classify pierce events as sweeps or breakouts.

    Returns ``(pools, events)`` with the pinned schemas:
    pools ``(pool_id, symbol, timeframe, side, level, touch_count, state,
    first_touch_at, activated_at, resolved_at)``; events ``(event_id,
    pool_id, symbol, timeframe, side, level, pierced_at, resolved_at,
    event_type)``. Pool IDs ``{SYMBOL}-{TF}-P{n:04d}`` in activation order;
    exactly one event (``{pool_id}-E1``) per resolved pool. Forming
    candidates appear with ``state='forming'`` and NA pool_id (A5).
    """
    _validate_bars(bars)
    _validate_swings(swings)
    if bars.empty or swings.empty:
        return _empty_pools_frame(), _empty_events_frame()

    pool_rows: list[dict] = []
    event_rows: list[dict] = []
    for symbol, sym_bars in bars.groupby("symbol", sort=False):
        sym_swings = swings[swings["symbol"] == symbol]
        if sym_swings.empty:
            continue
        sb = sym_bars.sort_values("time_utc").reset_index(drop=True)
        ss = sym_swings.sort_values("confirmed_at").reset_index(drop=True)
        pools, events = _detect_for_symbol(
            sb, ss, atr_period, tolerance_atr_multiple
        )
        pool_rows.extend(pools)
        event_rows.extend(events)

    pools_frame = pd.DataFrame(pool_rows, columns=POOL_COLUMNS)
    events_frame = pd.DataFrame(event_rows, columns=EVENT_COLUMNS)
    for frame, str_cols, ts_cols in (
        (pools_frame, ("pool_id", "symbol", "timeframe", "side", "state"),
         ("first_touch_at", "activated_at", "resolved_at")),
        (events_frame, ("event_id", "pool_id", "symbol", "timeframe", "side", "event_type"),
         ("pierced_at", "resolved_at")),
    ):
        for col in str_cols:
            if col in frame.columns:
                frame[col] = frame[col].astype(_STR_DTYPE)
        # Pin datetime units — pandas infers [s]/[us] from values, which made
        # prefix vs full-frame repaint comparisons dtype-unstable.
        for col in ts_cols:
            if col in frame.columns:
                frame[col] = frame[col].astype("datetime64[us]")
    return pools_frame.reset_index(drop=True), events_frame.reset_index(drop=True)
