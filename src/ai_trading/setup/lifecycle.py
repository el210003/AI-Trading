"""Setup lifecycle monitor (SETUP-03/04) — the D-01/D-02/D-03/D-04 state
machine, implemented purely over stored bars (no MT5, no chain re-run).

Transitions (pinned in 06-CONTEXT / RESEARCH Pattern 2):

- ``pending``: the signal is live, waiting for price to trade through the
  D-01 limit at ``entry``.
  - ``active``: a window bar's high/low crosses ``entry`` in the trade
    direction (wick tolerance, OQ5) — the limit trigger fires.
  - ``invalidated``: a window bar CLOSES beyond the tapped zone's far boundary
    (structure/zone break, D-04) — checked BEFORE the trigger.
  - ``expired``: the window elapses with no trigger (D-04 N-bar window).
- ``active``: resolves via ``walk_barriers`` VERBATIM (D-03) so live R is
  comparable to backtest R: ``tp_hit`` (WIN), ``sl_hit`` (LOSS), ``expired``
  (TIMEOUT, 96-bar inclusive barrier, D-17), with ``r_gross``/``r_raw``/
  ``r_net`` carried onto the record.

Pure: zero I/O, zero MetaTrader5 imports, input records/frames never mutated
(``apply_lifecycle`` returns a new frame).
"""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pandas as pd

from ai_trading.backtest.barriers import walk_barriers

#: Terminal statuses that are never re-resolved.
_TERMINAL_STATUSES = frozenset({"tp_hit", "sl_hit", "expired", "invalidated"})

#: Statuses that suppress new setup assembly for a symbol (D-05).
ACTIVE_LIFECYCLE_STATUSES = frozenset({"pending", "active"})


def _window_positions(bars: pd.DataFrame, created_at, window_bars: int) -> list[int]:
    """Positions (in ``bars``) of the pending trigger window: the bars strictly
    after ``created_at``, capped at the first ``window_bars`` of them. Uses
    positional arithmetic so it is robust regardless of the frame index."""
    created_ns = np.datetime64(pd.Timestamp(created_at).to_datetime64())
    after = np.flatnonzero(bars["time_utc"].to_numpy() > created_ns)
    return [int(p) for p in after[:window_bars]]


def _window_frame(bars: pd.DataFrame, positions: list[int]) -> pd.DataFrame:
    if not positions:
        return bars.iloc[0:0]
    return bars.iloc[positions]


def _entry_touched(setup, window_bars: pd.DataFrame) -> bool:
    """D-01 limit trigger: a window bar's high/low crosses ``entry`` in the
    trade direction (long: bar low <= entry; short: bar high >= entry)."""
    if window_bars.empty:
        return False
    entry = float(setup["entry"])
    if setup["direction"] == "long":
        return bool((window_bars["low"] <= entry).any())
    return bool((window_bars["high"] >= entry).any())


def _zone_invalidated(setup, window_bars: pd.DataFrame) -> bool:
    """D-04 structure/zone break: a window bar CLOSES beyond the tapped zone's
    far boundary (rejection of the discount/premium tap). Uses only founder
    record fields + bar closes (no chain re-run)."""
    if window_bars.empty:
        return False
    if setup["direction"] == "long":
        far = float(setup["zone_range_high"])
        return bool((window_bars["close"] > far).any())
    far = float(setup["zone_range_low"])
    return bool((window_bars["close"] < far).any())


def _trigger_info(setup, bars: pd.DataFrame, cfg):
    """''(trigger_time, trigger_bar_idx) of the FIRST window bar that crosses
    ``entry``, or ``None`` when no window bar triggers."""
    positions = _window_positions(bars, setup["created_at"], int(cfg.setup_trigger_window_bars))
    entry = float(setup["entry"])
    direction = setup["direction"]
    for p in positions:
        bar = bars.iloc[p]
        if direction == "long":
            if float(bar["low"]) <= entry:
                return bar["time_utc"], p
        elif float(bar["high"]) >= entry:
            return bar["time_utc"], p
    return None


def resolve_pending(setup, bars: pd.DataFrame, cfg) -> str:
    """D-04 pending-phase resolution: ``invalidated`` (zone break first),
    ``active`` (limit trigger), ``expired`` (window fully elapsed), else
    ``pending``."""
    positions = _window_positions(bars, setup["created_at"], int(cfg.setup_trigger_window_bars))
    window = _window_frame(bars, positions)
    if _zone_invalidated(setup, window):
        return "invalidated"
    if _entry_touched(setup, window):
        return "active"
    if len(positions) >= int(cfg.setup_trigger_window_bars):
        return "expired"
    return "pending"


def resolve_active(setup, bars: pd.DataFrame, cfg) -> dict:
    """D-02/D-03 active-position resolution via ``walk_barriers`` verbatim.

    Builds a ``walk_barriers``-compatible position (structural entry basis) and
    maps ``WIN -> tp_hit``, ``LOSS -> sl_hit``, ``TIMEOUT -> expired``, carrying
    the exit R/outcome onto the record. Returns
    ``{next_status, outcome, exit_price, exit_time, exit_idx, r_gross, r_raw,
    r_net}``.
    """
    entry = float(setup["entry"])
    position = SimpleNamespace(
        symbol=setup["symbol"],
        timeframe=setup["timeframe"],
        direction=setup["direction"],
        entry_open=entry,  # structural risk basis (A4: live R uses structural)
        entry_price=entry,  # v1 signals-only: no net cost model
        entry_spread_points=0,
        sl_price=float(setup["sl_price"]),
        tp_price=float(setup["tp_price"]),
        entry_idx=int(setup["trigger_bar_idx"]),
        entry_time=setup.get("trigger_time"),
        evidence={},
    )
    result = walk_barriers(position, bars, cfg)
    if result["outcome"] == "WIN":
        next_status = "tp_hit"
    elif result["outcome"] == "LOSS":
        next_status = "sl_hit"
    else:
        next_status = "expired"
    return {
        "next_status": next_status,
        "outcome": result["outcome"],
        "exit_price": result["exit_price"],
        "exit_time": result["exit_time"],
        "exit_idx": result["exit_idx"],
        "r_gross": result["r_gross"],
        "r_raw": result["r_raw"],
        "r_net": result["r_net"],
    }


def apply_lifecycle(setups: pd.DataFrame, bars_by_symbol: dict, cfg) -> pd.DataFrame:
    """Resolve every pending/active setup in ``setups`` against the latest bars
    for its symbol, returning a NEW frame with status/exit fields filled.

    Pure: the input frame is never mutated. Terminal statuses are skipped; a
    symbol missing from ``bars_by_symbol`` is left unchanged (defensive)."""
    if setups is None or setups.empty:
        return setups.copy() if setups is not None else setups
    records: list[dict] = []
    for _, row in setups.iterrows():
        rec = row.to_dict()
        status = rec["status"]
        if status in _TERMINAL_STATUSES:
            records.append(rec)
            continue
        bars = bars_by_symbol.get(str(rec["symbol"]))
        if bars is None or bars.empty:
            records.append(rec)
            continue
        if status == "pending":
            next_status = resolve_pending(rec, bars, cfg)
            if next_status == "active":
                trigger = _trigger_info(rec, bars, cfg)
                if trigger is not None:
                    rec["trigger_time"] = trigger[0]
                    rec["trigger_bar_idx"] = trigger[1]
                    rec["status"] = "active"
                else:
                    rec["status"] = "pending"
            elif next_status == "invalidated":
                rec["status"] = "invalidated"
            elif next_status == "expired":
                rec["status"] = "expired"
            else:
                rec["status"] = "pending"
        elif status == "active":
            result = resolve_active(rec, bars, cfg)
            rec["status"] = result["next_status"]
            rec["outcome"] = result["outcome"]
            rec["exit_price"] = result["exit_price"]
            rec["exit_time"] = result["exit_time"]
            rec["exit_idx"] = result["exit_idx"]
            rec["closed_at"] = result["exit_time"]
            rec["r_gross"] = result["r_gross"]
            rec["r_raw"] = result["r_raw"]
            rec["r_net"] = result["r_net"]
        records.append(rec)
    out = pd.DataFrame(records)
    if len(out) == 0:
        return setups.iloc[0:0]
    return out
