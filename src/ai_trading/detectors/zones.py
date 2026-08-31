"""Premium/discount zone derivation and the monotone zone lifecycle state
machine (SMC-04, zone half of SMC-05).

Pattern of record: RESEARCH.md Pattern 5 (per-bar advancement loop,
``advance_zone`` core) with the sequential state-machine style of
``pools.py``.

Hard rules (locked decisions):
- D-09: every consecutive opposite-side zigzag pair (p1, p2) defines one
  zone at the moment p2 confirms: range_high = max(p1.price, p2.price),
  range_low = min, equilibrium = midpoint, leg_direction = ``up`` when p1 is
  a low and p2 a high (``down`` mirror), created_at = p2's confirmed_at (the
  completing swing's confirmation-bar close). No zone exists before the
  first completed leg.
- D-10 (operationalized per A7): mitigation = the bar's wick intersects the
  range interior (bar low strictly below range_high AND bar high strictly
  above range_low) — closes not required.
- D-11: invalidation = a COMMITTED close strictly beyond the far boundary
  (close above range_high or below range_low). Wick pokes beyond the
  boundary do NOT invalidate. Valid from unmitigated or mitigated.
- D-12: all zones tracked concurrently — overlapping ranges from different
  legs coexist; zones are never deleted or superseded.
- Pitfall 6: per-bar per-zone order = mitigation check FIRST, then
  invalidation check; one bar may stamp both timestamps
  (mitigated_at <= invalidated_at, final state invalidated). Lifecycle is
  monotone ``unmitigated -> mitigated -> invalidated``; timestamps are
  first-event and never overwritten; invalidated zones stop being evaluated.
- Planner pin: lifecycle advancement starts at the bar opening at
  created_at (bar time_utc >= created_at); the creating confirmation bar
  itself (time_utc == created_at - TF) never advances its own zone — zones
  are never born mitigated.
- Zero adapter-tier imports, zero file I/O; input frames never mutated;
  stored times consumed as-is (no grid re-flooring, Pitfall 8).
"""

from __future__ import annotations

import pandas as pd

ZONE_COLUMNS = [
    "zone_id",
    "symbol",
    "timeframe",
    "leg_direction",
    "range_high",
    "range_low",
    "equilibrium",
    "state",
    "created_at",
    "mitigated_at",
    "invalidated_at",
]

_REQUIRED_ZIGZAG = ("symbol", "timeframe", "bar_time", "price", "side", "confirmed_at")
_REQUIRED_BARS = ("symbol", "time_utc", "open", "high", "low", "close")

_STR_DTYPE = pd.StringDtype()


def _empty_zones_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "zone_id": pd.Series(dtype=_STR_DTYPE),
            "symbol": pd.Series(dtype=_STR_DTYPE),
            "timeframe": pd.Series(dtype=_STR_DTYPE),
            "leg_direction": pd.Series(dtype=_STR_DTYPE),
            "range_high": pd.Series(dtype="float64"),
            "range_low": pd.Series(dtype="float64"),
            "equilibrium": pd.Series(dtype="float64"),
            "state": pd.Series(dtype=_STR_DTYPE),
            "created_at": pd.Series(dtype="datetime64[us]"),
            "mitigated_at": pd.Series(dtype="datetime64[us]"),
            "invalidated_at": pd.Series(dtype="datetime64[us]"),
        }
    )


def _validate_zigzag(zigzag: pd.DataFrame) -> None:
    missing = [c for c in _REQUIRED_ZIGZAG if c not in zigzag.columns]
    if missing:
        raise ValueError(
            f"derive_zones invariant violated: zigzag is missing required columns {missing}"
        )
    unknown = (
        set(zigzag["side"].dropna().unique()) - {"high", "low"} if len(zigzag) else set()
    )
    if unknown:
        raise ValueError(
            f"derive_zones invariant violated: zigzag side values must be 'high' or "
            f"'low', got {sorted(unknown)}"
        )


def _validate_bars(bars: pd.DataFrame) -> None:
    missing = [c for c in _REQUIRED_BARS if c not in bars.columns]
    if missing:
        raise ValueError(
            f"derive_zones invariant violated: bars is missing required columns {missing}"
        )
    if not bars["time_utc"].is_monotonic_increasing or not bars["time_utc"].is_unique:
        raise ValueError(
            "derive_zones invariant violated: bars time_utc must be strictly "
            "increasing and unique"
        )
    for col in ("open", "high", "low", "close"):
        if not bars[col].notna().all():
            raise ValueError(
                f"derive_zones invariant violated: bars column '{col}' must be finite"
            )


def _zones_for_symbol(
    sym_zigzag: pd.DataFrame, sym_bars: pd.DataFrame
) -> list[dict]:
    """Derive zones from consecutive zigzag pairs and advance their
    lifecycles bar-by-bar for one symbol."""
    tf = str(sym_zigzag["timeframe"].iloc[0])
    points = sym_zigzag.sort_values(
        ["confirmed_at", "bar_time", "side"], kind="mergesort"
    ).reset_index(drop=True)

    zones: list[dict] = []
    for i in range(len(points) - 1):
        p1 = points.iloc[i]
        p2 = points.iloc[i + 1]
        if p1.side == p2.side:
            raise ValueError(
                "derive_zones invariant violated: zigzag sides must alternate "
                f"(consecutive {p1.side!r} points at {p1.bar_time} / {p2.bar_time})"
            )
        range_high = max(p1.price, p2.price)
        range_low = min(p1.price, p2.price)
        zones.append(
            {
                "zone_id": None,  # assigned after creation-order is known
                "symbol": p1.symbol,
                "timeframe": tf,
                "leg_direction": "up" if p1.side == "low" else "down",
                "range_high": float(range_high),
                "range_low": float(range_low),
                "equilibrium": (range_high + range_low) / 2.0,
                "state": "unmitigated",
                "created_at": p2.confirmed_at,
                "mitigated_at": pd.NaT,
                "invalidated_at": pd.NaT,
            }
        )
    for n, zone in enumerate(zones, start=1):
        zone["zone_id"] = f"{zone['symbol']}-{tf}-Z{n:04d}"

    # Lifecycle advancement: bars in time order; a zone is evaluated from the
    # first bar whose open time is at or after created_at (planner pin — the
    # creating confirmation bar itself is earlier and never advances it).
    times = sym_bars["time_utc"].reset_index(drop=True)
    for i in range(len(sym_bars)):
        bar = sym_bars.iloc[i]
        t = times.iloc[i]
        for zone in zones:
            if zone["state"] == "invalidated" or t < zone["created_at"]:
                continue
            # D-10/A7: wick intersects the range interior.
            if zone["state"] == "unmitigated" and (
                bar["low"] < zone["range_high"] and bar["high"] > zone["range_low"]
            ):
                zone["state"] = "mitigated"
                zone["mitigated_at"] = t
            # D-11: committed close beyond the far boundary (checked after
            # mitigation — Pitfall 6 same-bar double-stamp order).
            if bar["close"] > zone["range_high"] or bar["close"] < zone["range_low"]:
                zone["state"] = "invalidated"
                zone["invalidated_at"] = t

    return zones


def derive_zones(zigzag: pd.DataFrame, bars: pd.DataFrame) -> pd.DataFrame:
    """Derive premium/discount zones from completed zigzag legs and advance
    their monotone lifecycles bar-by-bar.

    Returns a zones frame with the pinned schema ``(zone_id, symbol,
    timeframe, leg_direction, range_high, range_low, equilibrium, state,
    created_at, mitigated_at, invalidated_at)``, sorted by (symbol,
    created_at); IDs ``{SYMBOL}-{TF}-Z{n:04d}`` in creation order.
    """
    _validate_zigzag(zigzag)
    _validate_bars(bars)
    if zigzag.empty or bars.empty:
        return _empty_zones_frame()

    zone_rows: list[dict] = []
    for symbol, sym_zigzag in zigzag.groupby("symbol", sort=False):
        sym_bars = bars[bars["symbol"] == symbol]
        if sym_bars.empty:
            continue
        sz = sym_zigzag.sort_values("confirmed_at").reset_index(drop=True)
        sbs = sym_bars.sort_values("time_utc").reset_index(drop=True)
        zone_rows.extend(_zones_for_symbol(sz, sbs))

    zones_frame = pd.DataFrame(zone_rows, columns=ZONE_COLUMNS)
    for col in ("zone_id", "symbol", "timeframe", "leg_direction", "state"):
        if col in zones_frame.columns:
            zones_frame[col] = zones_frame[col].astype(_STR_DTYPE)
    for col in ("created_at", "mitigated_at", "invalidated_at"):
        if col in zones_frame.columns:
            zones_frame[col] = zones_frame[col].astype("datetime64[us]")
    return zones_frame.sort_values(["symbol", "created_at"], kind="mergesort").reset_index(drop=True)
