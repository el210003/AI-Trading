"""Unit tests for the BT-02 cost model (backtest.costs) — pure-math style
with literal expected floats (test_normalize_and_config.py convention).

Float precision note: chained sums (open + spread_px + slip) land 1-2 ulp
from their decimal literals in binary floating point, so fill-price tests
assert EXACT equality against the same decomposition the implementation
uses (catching operand swaps / wrong conversions / missing slippage) plus
pytest.approx guards against the hand-computed decimal values, and
abs=1e-15 guards on composite round-trip deltas.
"""

from __future__ import annotations

import pytest
from _backtest_fixtures import bt_cfg

from ai_trading.backtest.costs import (
    effective_slippage_pips,
    effective_spread_points,
    entry_fill_price,
    exit_fill_price,
    pip_size,
    point_size,
)

CFG = bt_cfg()
OPEN = 1.10000
LEVEL = 1.09000
SPREAD_PTS = 20
SLIP_PIPS = 0.5
SPREAD_PX = SPREAD_PTS * 0.00001  # exactly 0.0002
SLIP_PX = SLIP_PIPS * 0.0001  # exactly 0.00005


# ---------------------------------------------------------------------------
# Points -> price conversion (Pitfall 2)
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_pip_and_point_sizes():
    assert pip_size(CFG, "EURUSD") == 0.0001
    assert pip_size(CFG, "USDJPY") == 0.01
    assert point_size(CFG, "EURUSD") == 0.00001
    assert point_size(CFG, "USDJPY") == 0.001


@pytest.mark.unit
def test_spread_points_to_price():
    """EURUSD spread 20 points -> 0.0002; 42 points -> 0.00042; USDJPY
    20 points -> 0.020."""
    assert effective_spread_points(CFG, "EURUSD", 20) * point_size(CFG, "EURUSD") == 0.0002
    assert effective_spread_points(CFG, "EURUSD", 42) * point_size(CFG, "EURUSD") == pytest.approx(
        0.00042
    )
    assert effective_spread_points(CFG, "USDJPY", 20) * point_size(CFG, "USDJPY") == pytest.approx(
        0.020
    )


@pytest.mark.unit
def test_pip_size_absent_symbol_raises_naming_symbol():
    cfg = bt_cfg(pip_size={})
    with pytest.raises(ValueError, match="AUDUSD"):
        pip_size(cfg, "AUDUSD")


# ---------------------------------------------------------------------------
# D-15 fallback (recorded spread 0/absent is the dominant stored path)
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_d15_fallback_zero_spread_uses_default():
    assert effective_spread_points(CFG, "EURUSD", 0) == 20
    assert entry_fill_price("long", OPEN, 0, CFG, "EURUSD") == pytest.approx(
        OPEN + 0.0002 + 0.00005
    )


@pytest.mark.unit
def test_d15_no_fallback_when_recorded_positive():
    assert effective_spread_points(CFG, "EURUSD", 18) == 18


@pytest.mark.unit
def test_d15_per_symbol_override_wins():
    cfg = bt_cfg(default_spread_points_by_symbol={"EURUSD": 30})
    assert effective_spread_points(cfg, "EURUSD", 0) == 30
    assert effective_spread_points(cfg, "USDJPY", 0) == 20  # scalar default elsewhere


@pytest.mark.unit
def test_d15_nan_and_none_treated_as_absent():
    assert effective_spread_points(CFG, "EURUSD", None) == 20
    assert effective_spread_points(CFG, "EURUSD", float("nan")) == 20


@pytest.mark.unit
def test_negative_spread_raises_invariant():
    with pytest.raises(ValueError, match="invariant violated"):
        effective_spread_points(CFG, "EURUSD", -1)
    with pytest.raises(ValueError, match="invariant violated"):
        entry_fill_price("long", OPEN, -3, CFG, "EURUSD")


# ---------------------------------------------------------------------------
# D-14 per-symbol slippage override
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_d14_slippage_override_and_scalar_default():
    cfg = bt_cfg(slippage_pips_by_symbol={"USDJPY": 1.2})
    assert effective_slippage_pips(cfg, "USDJPY") == 1.2
    assert effective_slippage_pips(cfg, "EURUSD") == 0.5


# ---------------------------------------------------------------------------
# Fill math with literal floats
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_entry_fill_prices_literal():
    """EURUSD open 1.10000, spread 20 pt (0.0002), slip 0.5 pip (0.00005):
    long entry 1.10025, short entry 1.09995."""
    long_entry = entry_fill_price("long", OPEN, SPREAD_PTS, CFG, "EURUSD")
    short_entry = entry_fill_price("short", OPEN, SPREAD_PTS, CFG, "EURUSD")
    assert long_entry == OPEN + SPREAD_PX + SLIP_PX
    assert long_entry == pytest.approx(1.10025, abs=1e-12)
    assert short_entry == OPEN - SLIP_PX
    assert short_entry == pytest.approx(1.09995, abs=1e-12)


@pytest.mark.unit
def test_exit_fill_prices_literal():
    long_exit = exit_fill_price("long", LEVEL, SPREAD_PTS, CFG, "EURUSD")
    short_exit = exit_fill_price("short", LEVEL, SPREAD_PTS, CFG, "EURUSD")
    assert long_exit == LEVEL - SLIP_PX
    assert short_exit == LEVEL + SPREAD_PX + SLIP_PX


@pytest.mark.unit
def test_apply_slippage_false_returns_raw_spread_only_fill():
    assert entry_fill_price("long", OPEN, SPREAD_PTS, CFG, "EURUSD", apply_slippage=False) == (
        OPEN + SPREAD_PX
    )
    assert entry_fill_price("short", OPEN, SPREAD_PTS, CFG, "EURUSD", apply_slippage=False) == OPEN
    assert exit_fill_price("long", LEVEL, SPREAD_PTS, CFG, "EURUSD", apply_slippage=False) == LEVEL
    assert exit_fill_price("short", LEVEL, SPREAD_PTS, CFG, "EURUSD", apply_slippage=False) == (
        LEVEL + SPREAD_PX
    )


# ---------------------------------------------------------------------------
# Long/short cost symmetry (Pitfall 8: spread crossed exactly once)
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_long_short_cost_symmetry():
    """Identical bar paths long vs short: round-trip net cost = spread_px +
    2*slip for BOTH directions (convention A1 — long pays the spread at
    entry, short at exit; never double-charged, never skipped)."""
    entry_long = entry_fill_price("long", OPEN, SPREAD_PTS, CFG, "EURUSD")
    exit_long = exit_fill_price("long", LEVEL, SPREAD_PTS, CFG, "EURUSD")
    entry_short = entry_fill_price("short", OPEN, SPREAD_PTS, CFG, "EURUSD")
    exit_short = exit_fill_price("short", LEVEL, SPREAD_PTS, CFG, "EURUSD")

    frictionless_long = LEVEL - OPEN
    frictionless_short = OPEN - LEVEL
    cost_long = frictionless_long - (exit_long - entry_long)
    cost_short = frictionless_short - (entry_short - exit_short)
    expected = SPREAD_PX + 2 * SLIP_PX
    assert cost_long == pytest.approx(expected, abs=1e-15)
    assert cost_short == pytest.approx(expected, abs=1e-15)
    assert cost_long == pytest.approx(cost_short, abs=1e-15)


@pytest.mark.unit
def test_raw_vs_net_delta_is_exactly_twice_slippage():
    """D-16: round-trip RAW cost = spread_px only; NET = spread_px + 2*slip;
    the delta is 2*slip_px in PRICE units (the R-unit expression of this
    delta is specified in plan 03-02's barrier R math)."""
    for direction, fric in (("long", LEVEL - OPEN), ("short", OPEN - LEVEL)):
        entry_net = entry_fill_price(direction, OPEN, SPREAD_PTS, CFG, "EURUSD")
        exit_net = exit_fill_price(direction, LEVEL, SPREAD_PTS, CFG, "EURUSD")
        raw = dict(cfg=CFG, symbol="EURUSD", apply_slippage=False)
        entry_raw = entry_fill_price(direction, OPEN, SPREAD_PTS, **raw)
        exit_raw = exit_fill_price(direction, LEVEL, SPREAD_PTS, **raw)
        # Long pnl = exit - entry; short pnl = entry - exit; cost = frictionless - pnl.
        if direction == "long":
            pnl_net, pnl_raw = exit_net - entry_net, exit_raw - entry_raw
        else:
            pnl_net, pnl_raw = entry_net - exit_net, entry_raw - exit_raw
        cost_net, cost_raw = fric - pnl_net, fric - pnl_raw
        assert cost_raw == pytest.approx(SPREAD_PX, abs=1e-15)
        assert cost_net == pytest.approx(SPREAD_PX + 2 * SLIP_PX, abs=1e-15)
        assert cost_net - cost_raw == pytest.approx(2 * SLIP_PX, abs=1e-15)


# ---------------------------------------------------------------------------
# Wave-0 sanity: sampled spreads are sane in pips
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_sampled_spreads_lie_in_sane_pip_range():
    """EURUSD 17 / GBPUSD 42 / USDJPY 20 points -> 1.7 / 4.2 / 2.0 pips,
    all inside [0.1, 10] (a spread misread as pips or price breaks this)."""
    for symbol, points in (("EURUSD", 17), ("GBPUSD", 42), ("USDJPY", 20)):
        spread_pips = points / 10
        assert 0.1 <= spread_pips <= 10
        px = effective_spread_points(CFG, symbol, points) * point_size(CFG, symbol)
        assert px == pytest.approx(spread_pips * pip_size(CFG, symbol))


# ---------------------------------------------------------------------------
# Direction validation
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_invalid_direction_raises_invariant():
    with pytest.raises(ValueError, match="invariant violated"):
        entry_fill_price("up", OPEN, SPREAD_PTS, CFG, "EURUSD")
    with pytest.raises(ValueError, match="invariant violated"):
        exit_fill_price("LONG", LEVEL, SPREAD_PTS, CFG, "EURUSD")
