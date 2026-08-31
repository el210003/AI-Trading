"""Alternating zigzag over confirmed swings — the canonical structure (D-04).

Pattern of record: RESEARCH.md Pattern 3 (explicit ordered loop; event-sparse
logic stays auditable, deliberately not vectorized) with the loop style of
``history_report.compute_gaps``.

Hard rules (locked decisions):
- D-04: the first confirmed swing seeds the structure. An opposite-side
  confirmation APPENDS (completing the previous leg). A same-side
  confirmation REPLACES the tail point only when it is strictly more extreme
  (higher high / lower low); a same-side less-extreme confirmation is
  ABSORBED — the swing still exists as a raw record for pool clustering
  (plan 02-02).
- Repaint tier 2 (SC1): the REPLACE branch mutates only the zigzag *tail* —
  rows before the final point are immutable across prefixes.
- Output carries ``symbol`` and ``timeframe`` through from the swing records;
  schema is exactly ``(symbol, timeframe, bar_time, price, side,
  confirmed_at)``.
- Swings are consumed sorted by ``["confirmed_at", "bar_time", "side"]`` —
  never the raw bar frame; the side tiebreak keeps the A9 dual-swing
  high-then-low order. Multi-symbol input is processed per symbol
  independently.
- Zero adapter-tier imports, zero file I/O; never writes into the swings
  frame.
"""

from __future__ import annotations

import pandas as pd

ZIGZAG_COLUMNS = [
    "symbol",
    "timeframe",
    "bar_time",
    "price",
    "side",
    "confirmed_at",
]

_REQUIRED_COLUMNS = ("symbol", "timeframe", "bar_time", "price", "side", "confirmed_at")


def _empty_zigzag_frame() -> pd.DataFrame:
    """Empty output frame carrying the exact pinned schema and dtypes."""
    return pd.DataFrame(
        {
            "symbol": pd.Series(dtype="object"),
            "timeframe": pd.Series(dtype="object"),
            "bar_time": pd.Series(dtype="datetime64[us]"),
            "price": pd.Series(dtype="float64"),
            "side": pd.Series(dtype="object"),
            "confirmed_at": pd.Series(dtype="datetime64[us]"),
        }
    )


def _validate(swings: pd.DataFrame) -> None:
    missing = [c for c in _REQUIRED_COLUMNS if c not in swings.columns]
    if missing:
        raise ValueError(
            f"build_zigzag invariant violated: swings is missing required columns {missing}"
        )
    unknown = set(swings["side"].dropna().unique()) - {"high", "low"}
    if unknown:
        raise ValueError(
            f"build_zigzag invariant violated: side values must be 'high' or 'low', "
            f"got {sorted(unknown)}"
        )


def build_zigzag(swings: pd.DataFrame) -> pd.DataFrame:
    """Reduce confirmed swings to the alternating zigzag structure (D-04).

    Processes each symbol's records independently in confirmation order.
    Empty input returns an empty frame with the exact pinned schema.
    """
    _validate(swings)
    if swings.empty:
        return _empty_zigzag_frame()

    ordered = swings.sort_values(
        ["confirmed_at", "bar_time", "side"], kind="mergesort"
    )
    points: list[dict] = []
    for row in ordered.itertuples(index=False):
        if not points or points[-1]["symbol"] != row.symbol:
            points.append(
                {
                    "symbol": row.symbol,
                    "timeframe": row.timeframe,
                    "bar_time": row.bar_time,
                    "price": row.price,
                    "side": row.side,
                    "confirmed_at": row.confirmed_at,
                }
            )
            continue
        last = points[-1]
        if row.side == last["side"]:
            more_extreme = (
                (row.price > last["price"]) if row.side == "high" else (row.price < last["price"])
            )
            if more_extreme:
                points[-1] = {
                    "symbol": row.symbol,
                    "timeframe": row.timeframe,
                    "bar_time": row.bar_time,
                    "price": row.price,
                    "side": row.side,
                    "confirmed_at": row.confirmed_at,
                }
            # else: absorbed — the swing remains a raw record for pool clustering
        else:
            points.append(
                {
                    "symbol": row.symbol,
                    "timeframe": row.timeframe,
                    "bar_time": row.bar_time,
                    "price": row.price,
                    "side": row.side,
                    "confirmed_at": row.confirmed_at,
                }
            )
    out = pd.DataFrame(points, columns=ZIGZAG_COLUMNS)
    return out.reset_index(drop=True)
