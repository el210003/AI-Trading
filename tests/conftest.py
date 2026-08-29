"""Shared test fixtures: synthetic OHLC bar factory (MT5-free).

`make_bars` emits TF-aligned, OHLC-sane closed bars with the exact column
layout produced by `ai_trading.normalize.rates_to_dataframe`, so unit tests
never need a running MetaTrader 5 terminal (shared pattern #7).
"""

from datetime import datetime

import pandas as pd

from ai_trading.normalize import COLUMNS, TIMEFRAME_MINUTES


def make_bars(
    symbol: str,
    timeframe: str,
    start: datetime,
    count: int,
    offset_hours: int = 3,
) -> pd.DataFrame:
    """Create `count` synthetic bars stepping by the timeframe minutes.

    `start` is a naive broker-server wall-clock datetime and is expected to be
    aligned to the timeframe grid. The raw ``time`` column keeps server wall
    time; ``time_utc = time - offset_hours`` (DATA-03 semantics).
    """
    step = TIMEFRAME_MINUTES[timeframe]
    times = [start + pd.Timedelta(minutes=step * i) for i in range(count)]
    opens = [1.10000 + 0.00010 * i for i in range(count)]
    closes = [open_ + 0.00005 for open_ in opens]
    highs = [max(open_, close_) + 0.00010 for open_, close_ in zip(opens, closes, strict=True)]
    lows = [min(open_, close_) - 0.00010 for open_, close_ in zip(opens, closes, strict=True)]

    df = pd.DataFrame(
        {
            "symbol": [symbol] * count,
            "time": times,
            "time_utc": [t - pd.Timedelta(hours=offset_hours) for t in times],
            "open": opens,
            "high": highs,
            "low": lows,
            "close": closes,
            "tick_volume": list(range(1, count + 1)),  # positive ints
            "spread": list(range(count)),  # non-negative ints
            "real_volume": [0] * count,
        }
    )
    return df[COLUMNS]
