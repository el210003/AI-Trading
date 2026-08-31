"""Confirmation-shifted strict 2/2 fractal swing detection (SMC-01, SC1).

Pattern of record: RESEARCH.md Pattern 1 (verified vectorized composition).

Hard rules (locked decisions):
- D-01: a swing is emitted only on the close of the 2nd right-side bar —
  ``confirmed_at = time_utc.shift(-2) + Timedelta(minutes=TIMEFRAME_MINUTES[timeframe])``
  (the confirmation bar's close time). A frame truncated before confirmation
  contains no record of the swing.
- D-02: STRICT comparisons only — exactly-equal neighbor prices never form
  swings (no ``>=``/``==`` anywhere). Equal levels surface as liquidity pools
  instead (plan 02-02).
- D-03: output schema is exactly ``(symbol, timeframe, bar_time, price, side,
  confirmed_at)`` where ``bar_time`` is the EXTREME bar's ``time_utc``.
- A9: a bar that is both a strict swing high and swing low emits two records,
  high before low (final sort on ``["bar_time", "side"]`` — deterministic).
- The NaN tail of ``shift(-2)`` disqualifies the last 2 rows automatically —
  no manual trimming and no special casing.
- Zero adapter-tier imports, zero file I/O; stored ``time_utc`` values are
  consumed as-is with no grid re-flooring (Pitfall 8). Never mutates the
  input frame.
"""

from __future__ import annotations

import pandas as pd

from ai_trading.normalize import TIMEFRAME_MINUTES

SWING_COLUMNS = [
    "symbol",
    "timeframe",
    "bar_time",
    "price",
    "side",
    "confirmed_at",
]

_REQUIRED_COLUMNS = ("symbol", "time_utc", "high", "low")


def _empty_swing_frame() -> pd.DataFrame:
    """Empty output frame carrying the exact pinned schema and dtypes."""
    return pd.DataFrame(
        {
            "symbol": pd.Series(dtype="object"),
            "timeframe": pd.Series(dtype="object"),
            "bar_time": pd.Series(dtype="datetime64[ns]"),
            "price": pd.Series(dtype="float64"),
            "side": pd.Series(dtype="object"),
            "confirmed_at": pd.Series(dtype="datetime64[ns]"),
        }
    )


def _validate(bars: pd.DataFrame, timeframe: str) -> None:
    if timeframe not in TIMEFRAME_MINUTES:
        raise ValueError(
            f"detect_swings invariant violated: unknown timeframe {timeframe!r} — "
            f"expected one of {sorted(TIMEFRAME_MINUTES)}"
        )
    missing = [c for c in _REQUIRED_COLUMNS if c not in bars.columns]
    if missing:
        raise ValueError(
            f"detect_swings invariant violated: bars is missing required columns {missing}"
        )
    if not bars["time_utc"].is_monotonic_increasing:
        raise ValueError(
            "detect_swings invariant violated: time_utc must be strictly increasing"
        )
    if not bars["time_utc"].is_unique:
        raise ValueError(
            "detect_swings invariant violated: time_utc must be unique"
        )
    for col in ("high", "low"):
        if not bars[col].notna().all():
            raise ValueError(
                f"detect_swings invariant violated: column '{col}' must be finite "
                "(no NaN/inf prices)"
            )


def _side_records(
    bars: pd.DataFrame, timeframe: str, mask: pd.Series, side: str
) -> pd.DataFrame:
    confirmed_at = bars["time_utc"].shift(-2) + pd.Timedelta(
        minutes=TIMEFRAME_MINUTES[timeframe]
    )
    return pd.DataFrame(
        {
            "symbol": bars.loc[mask, "symbol"].to_numpy(),
            "timeframe": timeframe,
            "bar_time": bars.loc[mask, "time_utc"].to_numpy(),
            "price": bars.loc[mask, side].to_numpy(),
            "side": side,
            "confirmed_at": confirmed_at.loc[mask].to_numpy(),
        }
    )


def detect_swings(bars: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    """Detect strict 2/2 fractal swings in ``bars`` and return records with
    the pinned 6-column schema (D-03), confirmation-stamped per D-01.

    Swing high: ``high`` strictly greater than the highs at shifts +1, +2,
    -1, -2 (all four comparisons). Swing low: strict mirror on ``low``.
    Equality never qualifies (D-02). Empty or too-short input returns an
    empty frame with the exact schema (Pitfall 10).
    """
    _validate(bars, timeframe)
    if bars.empty:
        return _empty_swing_frame()

    h, low = bars["high"], bars["low"]
    swing_high = (h > h.shift(1)) & (h > h.shift(2)) & (h > h.shift(-1)) & (h > h.shift(-2))
    swing_low = (
        (low < low.shift(1)) & (low < low.shift(2))
        & (low < low.shift(-1)) & (low < low.shift(-2))
    )

    highs = _side_records(bars, timeframe, swing_high, "high")
    lows = _side_records(bars, timeframe, swing_low, "low")
    out = pd.concat([highs, lows], ignore_index=True)
    # A9: deterministic same-bar dual-swing order — "high" sorts before "low".
    out = out.sort_values(["bar_time", "side"], kind="mergesort").reset_index(drop=True)
    return out[SWING_COLUMNS]
