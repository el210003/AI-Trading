"""Pure UTC normalization transforms — the single source of truth for time math
(DATA-03). This module MUST NOT import or reference the MetaTrader5 package;
it operates on plain numpy structured arrays / DataFrames so it is unit-testable
with zero terminal dependency.

Hard rules (RESEARCH.md Pitfall 1 + Pitfall 7, PATTERNS "normalize.py"):
- MT5 epoch seconds decode to broker SERVER WALL time, not true UTC.
- The raw ``time`` column is preserved server-wall (success criterion 2).
- ``time_utc = time - broker_offset_hours`` where the offset comes from
  validated config only (ai_trading.config.load_config).
- NEVER tz_localize broker times to an IANA zone; use tz-aware arithmetic
  (datetime.now(timezone.utc), never deprecated utcnow) only for non-broker
  clocks, and strip tz before comparing against naive UTC bar stamps.
- pandas 3.x only: tz ops via tz_localize/tz_convert, never astype(...) — pytz
  is not used anywhere.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pandas as pd

# Exact stored column layout for every bar frame in the project.
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


def rates_to_dataframe(rates: Any, symbol: str, broker_offset_hours: int) -> pd.DataFrame:
    """Convert a numpy structured rates array (from copy_rates_*) into the
    canonical bar frame with both raw server-wall ``time`` and derived
    ``time_utc`` columns, ordered exactly as COLUMNS."""
    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s")  # naive server wall time (RAW, preserved)
    # true UTC = server wall time minus the validated offset (DATA-03)
    df["time_utc"] = df["time"] - pd.Timedelta(hours=broker_offset_hours)
    df.insert(0, "symbol", symbol)
    return df[COLUMNS]


def floor_to_timeframe(ts: datetime, timeframe: str) -> datetime:
    """Floor a timestamp (naive or aware) to its timeframe grid boundary.

    The grid is minutes-since-midnight of the timestamp's own calendar day
    (server-wall for naive broker times, local for non-broker clocks)."""
    minutes = TIMEFRAME_MINUTES[timeframe]
    start_of_day = ts.replace(hour=0, minute=0, second=0, microsecond=0)
    elapsed_minutes = int((ts - start_of_day).total_seconds() // 60)
    floored_minutes = (elapsed_minutes // minutes) * minutes
    return start_of_day + timedelta(minutes=floored_minutes)


def assert_closed_bars(df: pd.DataFrame, timeframe: str, now_utc: datetime) -> None:
    """Forming-bar guard (Pitfall 4): refuse any frame carrying a bar at or
    after the current timeframe floor of ``now_utc``.

    ``time_utc`` values are naive UTC wall stamps; an aware ``now_utc`` is
    converted to UTC and stripped before the naive comparison."""
    if df.empty:
        return
    floor = floor_to_timeframe(now_utc, timeframe)
    if floor.tzinfo is not None:
        floor = floor.astimezone(UTC).replace(tzinfo=None)
    max_utc = df["time_utc"].max()
    if max_utc >= floor:
        raise ValueError(
            f"closed-bar invariant violated: max time_utc {max_utc} is at or after "
            f"the current {timeframe} floor {floor} — the forming bar must never be stored"
        )
