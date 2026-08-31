"""Wilder ATR for bar frames — tolerance denominator for liquidity pools
(D-05) and distance-to-equilibrium units for the MTF payload (D-14, A1).

Pattern of record: RESEARCH.md Pattern 2 (verified pandas composition).

Hard rules:
- Wilder recursion == ``ewm(alpha=1/period, adjust=False)``. pandas seeds the
  recursion with the first True Range where Wilder's canonical seed is the SMA
  of the first ``period`` TRs — the seed difference decays geometrically and
  is immaterial for the 0.1x tolerance use (research assumption A4).
- ``min_periods=period`` keeps warmup rows NaN so callers skip clustering
  until ATR is finite (RESEARCH Pitfall 7).
- Pure transform: never mutates the input frame; no MetaTrader5 import.
"""

from __future__ import annotations

import pandas as pd

_REQUIRED_COLUMNS = ("high", "low", "close")


def wilders_atr(bars: pd.DataFrame, period: int = 14) -> pd.Series:
    """Return the Wilder ATR Series for ``bars`` (True Range smoothed by the
    Wilder recursion expressed as ``ewm(alpha=1/period, adjust=False,
    min_periods=period)``).

    Raises ValueError naming the invariant when required columns are missing
    or high/low/close carry non-finite values (Security V5 entry guard).
    """
    missing = [c for c in _REQUIRED_COLUMNS if c not in bars.columns]
    if missing:
        raise ValueError(
            f"wilders_atr invariant violated: bars is missing required columns {missing}"
        )
    for col in _REQUIRED_COLUMNS:
        if not bars[col].notna().all() or not pd.api.types.is_numeric_dtype(bars[col]):
            raise ValueError(
                f"wilders_atr invariant violated: column '{col}' must be finite numeric"
            )
    prev_close = bars["close"].shift(1)
    tr = pd.concat(
        [
            bars["high"] - bars["low"],
            (bars["high"] - prev_close).abs(),
            (bars["low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
