"""Pure cost arithmetic (BT-02) — spread/slippage conversion and direction-
aware fill prices. Validate-then-compute, mirrors detectors/atr.py style.

UNITS (Pitfall 2 — stated explicitly, pinned by literal-float tests):
- The stored ``spread`` column is in POINTS (MqlRates semantics; a 5-digit
  quote has 1 pip = 10 points). It is NEVER pips and NEVER price. EURUSD
  spread 20 points = 2.0 pips = 0.00020 price units; USDJPY spread 20
  points = 2.0 pips = 0.020 price units.
- pip size: 0.0001 for EURUSD/GBPUSD, 0.01 for USDJPY (config.pip_size).
- point size = pip size / 10 (5-digit quotes; USDJPY point = 0.001).

DIRECTION-ASYMMETRY (convention A1): bar OHLC prices are BID-side, so the
spread is crossed exactly once per round trip — a LONG crosses at entry
(buys the ask), a SHORT crosses at exit (buys back the ask). Slippage
(D-14, fixed pips per symbol) is charged on BOTH fills, always adverse.

D-15 fallback: a bar's recorded spread of 0/absent (the dominant path in
stored data — HTF/M1 aggregation artifacts) falls back to the per-symbol
default spread in points from config.

Pure functions: no MetaTrader5 import, no I/O, inputs never mutated.
"""

from __future__ import annotations

import pandas as pd

_VALID_DIRECTIONS = ("long", "short")


def _lookup(mapping: dict, symbol: str):
    """Per-symbol override lookup resolving suffixed broker symbols
    (``EURUSD.a``) through their base name, mirroring config validation."""
    if symbol in mapping:
        return mapping[symbol]
    return mapping.get(symbol.split(".", 1)[0])


def _validate_direction(direction: str) -> None:
    if direction not in _VALID_DIRECTIONS:
        raise ValueError(
            f"cost invariant violated: direction {direction!r} must be one of {_VALID_DIRECTIONS}"
        )


def _spread_points_or_raise(cfg, symbol: str, bar_spread) -> int:
    if bar_spread is not None and not pd.isna(bar_spread):
        if bar_spread < 0:
            raise ValueError(
                f"cost invariant violated: bar_spread {bar_spread!r} is negative"
            )
        if bar_spread > 0:
            return int(bar_spread)
    override = _lookup(cfg.default_spread_points_by_symbol, symbol)
    return int(override if override is not None else cfg.default_spread_points)


def pip_size(cfg, symbol: str) -> float:
    """Price units of one pip for ``symbol`` (config.pip_size; suffixed
    symbols resolve via base name). Raises ValueError naming the symbol when
    absent."""
    value = _lookup(cfg.pip_size, symbol)
    if value is None:
        raise ValueError(f"pip_size invariant violated: no pip size configured for {symbol!r}")
    return float(value)


def point_size(cfg, symbol: str) -> float:
    """Price units of one point = pip_size / 10 (5-digit quotes; USDJPY
    point = 0.001)."""
    return pip_size(cfg, symbol) / 10


def effective_spread_points(cfg, symbol: str, bar_spread) -> int:
    """Recorded bar spread in POINTS when positive, else the D-15 fallback:
    the per-symbol default_spread_points_by_symbol override, else the scalar
    cfg.default_spread_points."""
    return _spread_points_or_raise(cfg, symbol, bar_spread)


def effective_slippage_pips(cfg, symbol: str) -> float:
    """D-14 slippage in PIPS: the per-symbol slippage_pips_by_symbol
    override when present, else the scalar cfg.slippage_pips."""
    override = _lookup(cfg.slippage_pips_by_symbol, symbol)
    return float(override if override is not None else cfg.slippage_pips)


def entry_fill_price(
    direction: str,
    bar_open: float,
    bar_spread,
    cfg,
    symbol: str,
    apply_slippage: bool = True,
) -> float:
    """Net (or raw, when ``apply_slippage=False``) entry fill price.

    long:  bar_open + spread_px + slip   (buy the ask, cross the spread)
    short: bar_open - slip               (sell the bid, no spread at entry)
    where spread_px = effective_spread_points * point_size and
    slip = effective_slippage_pips * pip_size.
    """
    _validate_direction(direction)
    spread_px = _spread_points_or_raise(cfg, symbol, bar_spread) * point_size(cfg, symbol)
    slip_px = (
        effective_slippage_pips(cfg, symbol) * pip_size(cfg, symbol) if apply_slippage else 0.0
    )
    if direction == "long":
        return float(bar_open + spread_px + slip_px)
    return float(bar_open - slip_px)


def exit_fill_price(
    direction: str,
    level: float,
    bar_spread,
    cfg,
    symbol: str,
    apply_slippage: bool = True,
) -> float:
    """Net (or raw, when ``apply_slippage=False``) exit fill price at a
    barrier ``level``.

    long:  level - slip                  (sell the bid; spread already paid)
    short: level + spread_px + slip      (buy back the ask, cross the spread)
    """
    _validate_direction(direction)
    spread_px = _spread_points_or_raise(cfg, symbol, bar_spread) * point_size(cfg, symbol)
    slip_px = (
        effective_slippage_pips(cfg, symbol) * pip_size(cfg, symbol) if apply_slippage else 0.0
    )
    if direction == "long":
        return float(level - slip_px)
    return float(level + spread_px + slip_px)
