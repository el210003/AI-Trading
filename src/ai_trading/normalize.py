"""Pure UTC normalization transforms — the single source of truth for time math.

Minimal stub created in plan 01-01 Task 2 so the test scaffold (conftest) can
import COLUMNS/TIMEFRAME_MINUTES; Task 3 replaces this module with the full
pure-transform implementation (rates_to_dataframe, floor_to_timeframe,
assert_closed_bars). This module must never import MetaTrader5.
"""

COLUMNS = [
    "symbol",
    "time",
    "time_utc",
    "open",
    "high",
    "low",
    "close",
    "tick_volume",
    "spread",
    "real_volume",
]

TIMEFRAME_MINUTES = {"M15": 15, "H1": 60, "H4": 240}
