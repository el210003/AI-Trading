"""Pure frame sculptors for detector tests — shared helpers built over
``conftest.make_bars`` (root conftest is consumed, never extended — Phase 1
contract).

Helpers shape known swing/pool/zone sequences on flat OHLC bases so repaint
and unit expectations are hand-derivable. All helpers return new frames and
never mutate their inputs.
"""

from __future__ import annotations

from datetime import datetime

import pandas as pd


def flat_bars(
    symbol: str,
    timeframe: str,
    start: datetime,
    count: int,
    price: float = 1.10000,
    offset_hours: int = 3,
) -> pd.DataFrame:
    """Constant open/high/low/close frame at ``price`` — a no-swing baseline."""
    from conftest import make_bars

    df = make_bars(symbol, timeframe, start, count, offset_hours=offset_hours)
    for col in ("open", "high", "low", "close"):
        df[col] = price
    return df


def sculpt_high(df: pd.DataFrame, bar_index: int, price: float) -> pd.DataFrame:
    """Set one bar's high to ``price``, preserving OHLC sanity
    (high >= max(open, close), low <= high). Returns a new frame."""
    out = df.copy()
    out.iloc[bar_index, out.columns.get_indexer(["open"])] = min(
        out.iloc[bar_index]["open"], price
    )
    out.iloc[bar_index, out.columns.get_indexer(["close"])] = min(
        out.iloc[bar_index]["close"], price
    )
    out.iloc[bar_index, out.columns.get_indexer(["high"])] = price
    out.iloc[bar_index, out.columns.get_indexer(["low"])] = min(
        out.iloc[bar_index]["low"], price
    )
    return out


def sculpt_low(df: pd.DataFrame, bar_index: int, price: float) -> pd.DataFrame:
    """Set one bar's low to ``price``, preserving OHLC sanity
    (low <= min(open, close), high >= low). Returns a new frame."""
    out = df.copy()
    out.iloc[bar_index, out.columns.get_indexer(["open"])] = max(
        out.iloc[bar_index]["open"], price
    )
    out.iloc[bar_index, out.columns.get_indexer(["close"])] = max(
        out.iloc[bar_index]["close"], price
    )
    out.iloc[bar_index, out.columns.get_indexer(["low"])] = price
    out.iloc[bar_index, out.columns.get_indexer(["high"])] = max(
        out.iloc[bar_index]["high"], price
    )
    return out


def swing_spec_bars(
    symbol: str,
    timeframe: str,
    start: datetime,
    count: int,
    spec,
    offset_hours: int = 3,
) -> pd.DataFrame:
    """Build a frame from ``(bar_index, side, price)`` sculpt specs applied to
    a flat base — the workhorse for known swing sequences."""
    df = flat_bars(symbol, timeframe, start, count, offset_hours=offset_hours)
    for bar_index, side, price in spec:
        if side == "high":
            df = sculpt_high(df, bar_index, price)
        elif side == "low":
            df = sculpt_low(df, bar_index, price)
        else:
            raise ValueError(f"unknown sculpt side {side!r}")
    return df


def prefix_close_time(bars: pd.DataFrame, k: int) -> pd.Timestamp:
    """Close time (time_utc + TF minutes) of the prefix ``bars.iloc[:k]``'s
    last bar — the visibility horizon for point-in-time filtering."""
    step = bars["time_utc"].iloc[1] - bars["time_utc"].iloc[0]
    return bars.iloc[:k]["time_utc"].iloc[-1] + step


def assert_point_in_time_prefix_equality(runner, bars: pd.DataFrame, min_prefix: int = 10) -> None:
    """Generic T1 machinery: run ``runner`` over every prefix ``bars.iloc[:k]``
    and assert the prefix output equals exactly the rows of the full-frame
    output visible at that prefix (check_exact=True).

    ``runner`` maps a bars frame to an output frame that carries a
    ``confirmed_at`` column (swings today; pools/zones tiers in plans
    02-02/02-03).
    """
    full = runner(bars.copy())
    for k in range(min_prefix, len(bars)):
        prefix = runner(bars.iloc[:k].copy())
        visible = full[full["confirmed_at"] <= prefix_close_time(bars, k)].reset_index(drop=True)
        pd.testing.assert_frame_equal(prefix, visible, check_exact=True)
