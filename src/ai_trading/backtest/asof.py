"""Column-aware point-in-time visibility helper — the single anti-lookahead
choke point of the replay engine (BT-01 / ROADMAP SC1).

Every per-bar decision in the backtest consumes detector output ONLY through
``visible_mask``. The detector tiers stamp visibility times in two semantic
forms, and a single ``<= t_S`` filter over close-time stamps is off by one
bar (RESEARCH Pitfall 4) — hence two anchors:

    Stamp kind      Anchor         Applies to
    --------------  -------------  ----------------------------------------
    STAMP_CLOSE     close_t        swings.confirmed_at, zigzag.confirmed_at,
                    (t_S + TF)     zones.created_at, pools.activated_at
    STAMP_BAR       bar_t          pools.pierced_at, pools.resolved_at,
                    (t_S)          zones.mitigated_at, zones.invalidated_at

MTF payload rows are consumed as-is (row where time_utc == bar_t) and are
NEVER re-anchored through this helper (Phase 2 D-15 join is already
strictly-before).

Hard rules:
- NaT/None stamps are never visible (an event that never happened cannot be
  seen).
- The input frame is never mutated; the returned mask is a plain boolean
  Series aligned to the input index; dtypes are untouched (dtype-neutral).
- Pure transform: no MetaTrader5 import, no file I/O.
"""

from __future__ import annotations

import pandas as pd

from ai_trading.normalize import TIMEFRAME_MINUTES

STAMP_CLOSE = "close"  # close-time stamps: visible at t_S + TF
STAMP_BAR = "bar"  # bar-time stamps: visible at t_S

_STAMP_KINDS = (STAMP_CLOSE, STAMP_BAR)


def close_time_of(bar_t: pd.Timestamp, timeframe: str) -> pd.Timestamp:
    """Close time of the bar whose open time is ``bar_t``:
    ``bar_t + TIMEFRAME_MINUTES[timeframe]`` minutes (single source of truth
    for TF length). The input timestamp is passed through unchanged apart
    from the addition — no flooring, no tz conversion; non-timestamp scalars
    (float/bool) are never silently coerced."""
    return bar_t + pd.Timedelta(minutes=TIMEFRAME_MINUTES[timeframe])


def visible_mask(
    df: pd.DataFrame,
    col: str,
    stamp_kind: str,
    bar_t: pd.Timestamp,
    close_t: pd.Timestamp,
) -> pd.Series:
    """Boolean mask of rows whose ``col`` stamp is visible at the close of
    the decision bar ``bar_t`` (whose close time is ``close_t``).

    ``stamp_kind`` selects the anchor: STAMP_CLOSE compares against
    ``close_t`` (creation-style stamps), STAMP_BAR against ``bar_t``
    (lifecycle-event stamps). Rows with NaT/None stamps are excluded.
    """
    if col not in df.columns:
        raise ValueError(f"visible_mask invariant violated: {col!r} not in frame columns")
    if stamp_kind not in _STAMP_KINDS:
        raise ValueError(
            f"visible_mask invariant violated: stamp_kind {stamp_kind!r} "
            f"must be one of {_STAMP_KINDS}"
        )
    anchor = close_t if stamp_kind == STAMP_CLOSE else bar_t
    return df[col].notna() & (df[col] <= anchor)
