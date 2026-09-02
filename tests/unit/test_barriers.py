"""Unit tests for the triple-barrier walk (BT-03): the D-10 SL-first tie rule
(entry bar included), D-11 gap-open fills in both directions, the D-17
inclusive 96-bar window with the TIMEOUT at bar E+95's close, and the
convention-(a) R math — gross/raw/net all normalized by the SAME structural
risk distance |entry_open - sl_price|, with the D-16 cost delta visible in R
units. Worlds are hand-sculpted make_bars frames so every expectation is
hand-derivable. No MT5, no I/O.

Float-literal strategy (carried from test_costs.py): chained sums land 1-2
ulp from decimal literals, so R assertions use pytest.approx(abs=1e-12)
guards around hand-derived values.
"""

from __future__ import annotations

import dataclasses
from datetime import datetime

import pandas as pd
import pytest
from _backtest_fixtures import bt_cfg, make_bars, set_spreads
from _detector_fixtures import sculpt_high, sculpt_low

from ai_trading.backtest.barriers import (
    OUTCOME_LOSS,
    OUTCOME_TIMEOUT,
    OUTCOME_WIN,
    walk_barriers,
)
from ai_trading.backtest.costs import effective_spread_points, entry_fill_price
from ai_trading.backtest.replay import Position, replay_symbol

SYMBOL = "EURUSD"
START = datetime(2026, 8, 20, 0, 0)
CFG = bt_cfg()
BASE = 1.10000
SL = 1.09900
TP = 1.10200
RISK = BASE - SL  # 0.00100
ENTRY_IDX = 5
SPREAD_POINTS = 20  # 0.00020 price units; slippage 0.5 pip = 0.00005 (bt_cfg defaults)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _bars(count: int = 120) -> pd.DataFrame:
    """Flat never-touch world: O=H=L=C=BASE everywhere, recorded spread 20."""
    df = make_bars(SYMBOL, "M15", START, count)
    for col in ("open", "high", "low", "close"):
        df[col] = BASE
    return set_spreads(df, [SPREAD_POINTS] * count)


def _sculpt(df: pd.DataFrame, idx: int, *, open_, high, low, close) -> pd.DataFrame:
    """Set all four OHLC values of one bar (test-only sanity is the caller's)."""
    out = df.copy()
    for col, value in (("open", open_), ("high", high), ("low", low), ("close", close)):
        out.iloc[idx, out.columns.get_indexer([col])] = value
    return out


def _position(
    bars: pd.DataFrame,
    *,
    direction: str = "long",
    entry_open: float = BASE,
    sl: float = SL,
    tp: float = TP,
    entry_idx: int = ENTRY_IDX,
    cfg=CFG,
) -> Position:
    spread = effective_spread_points(cfg, SYMBOL, bars.iloc[entry_idx]["spread"])
    return Position(
        symbol=SYMBOL,
        timeframe="M15",
        direction=direction,
        entry_open=entry_open,
        entry_spread_points=spread,
        entry_price=entry_fill_price(direction, entry_open, spread, cfg, SYMBOL),
        sl_price=sl,
        tp_price=tp,
        entry_idx=entry_idx,
        entry_time=bars["time_utc"].iloc[entry_idx],
        evidence={},
        rr=0.0,
    )


# ---------------------------------------------------------------------------
# D-10: SL-first tie rule, entry bar included
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_tie_sl_first_including_entry_bar():
    """A bar touching BOTH SL and TP labels LOSS at the SL level — the D-10
    conservative pin. Fails if TP-first or close-direction logic sneaks in."""
    bars = _sculpt(
        _bars(count=8), ENTRY_IDX,
        open_=BASE, high=1.10300, low=1.09800, close=BASE + 0.0005,
    )
    result = walk_barriers(_position(bars), bars, CFG)
    assert result["outcome"] == OUTCOME_LOSS
    assert result["exit_price"] == SL
    assert result["exit_idx"] == ENTRY_IDX


@pytest.mark.unit
def test_tie_on_mid_window_bar_is_loss_at_sl():
    bars = _bars(count=40)
    tie_idx = 30
    bars = _sculpt(
        bars, tie_idx, open_=BASE, high=1.10300, low=1.09800, close=BASE + 0.0005,
    )
    result = walk_barriers(_position(bars), bars, CFG)
    assert result["outcome"] == OUTCOME_LOSS
    assert result["exit_price"] == SL
    assert result["exit_idx"] == tie_idx


@pytest.mark.unit
def test_sl_hit_on_entry_bar():
    """SL touched on the entry bar itself -> LOSS at the SL level (the window
    includes the entry bar)."""
    bars = _sculpt(
        _bars(count=10), ENTRY_IDX,
        open_=BASE, high=BASE + 0.0001, low=SL - 0.0005, close=BASE,
    )
    result = walk_barriers(_position(bars), bars, CFG)
    assert result["outcome"] == OUTCOME_LOSS
    assert result["exit_price"] == SL  # filled at the level, not the low
    assert result["exit_idx"] == ENTRY_IDX


@pytest.mark.unit
def test_tp_hit_on_entry_bar_long():
    bars = _sculpt(
        _bars(count=10), ENTRY_IDX,
        open_=BASE, high=TP, low=BASE - 0.0001, close=BASE + 0.0002,
    )
    result = walk_barriers(_position(bars), bars, CFG)
    assert result["outcome"] == OUTCOME_WIN
    assert result["exit_price"] == TP
    assert result["exit_idx"] == ENTRY_IDX


# ---------------------------------------------------------------------------
# D-11: gap fills at the bar's open, both directions
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_long_gap_below_sl_fills_at_open():
    bars = _bars(count=10)
    gap_idx = ENTRY_IDX + 1
    o = SL - 0.0005
    bars = _sculpt(bars, gap_idx, open_=o, high=o + 0.0001, low=o - 0.0001, close=o)
    result = walk_barriers(_position(bars), bars, CFG)
    assert result["outcome"] == OUTCOME_LOSS
    assert result["exit_price"] == o  # the OPEN, never the SL level (D-11)
    assert result["exit_idx"] == gap_idx


@pytest.mark.unit
def test_long_gap_above_tp_fills_at_open():
    bars = _bars(count=10)
    gap_idx = ENTRY_IDX + 1
    o = TP + 0.0005
    bars = _sculpt(bars, gap_idx, open_=o, high=o + 0.0001, low=o - 0.0001, close=o)
    result = walk_barriers(_position(bars), bars, CFG)
    assert result["outcome"] == OUTCOME_WIN
    assert result["exit_price"] == o  # gapped TP also fills at the open
    assert result["exit_idx"] == gap_idx


@pytest.mark.unit
def test_short_gap_above_sl_fills_at_open():
    sl_s, tp_s = 1.10100, 1.09900
    bars = _bars(count=10)
    gap_idx = ENTRY_IDX + 1
    o = sl_s + 0.0005
    bars = _sculpt(bars, gap_idx, open_=o, high=o + 0.0001, low=o - 0.0001, close=o)
    result = walk_barriers(_position(bars, direction="short", sl=sl_s, tp=tp_s), bars, CFG)
    assert result["outcome"] == OUTCOME_LOSS
    assert result["exit_price"] == o
    assert result["exit_idx"] == gap_idx


@pytest.mark.unit
def test_short_gap_below_tp_fills_at_open():
    sl_s, tp_s = 1.10100, 1.09900
    bars = _bars(count=10)
    gap_idx = ENTRY_IDX + 1
    o = tp_s - 0.0005
    bars = _sculpt(bars, gap_idx, open_=o, high=o + 0.0001, low=o - 0.0001, close=o)
    result = walk_barriers(_position(bars, direction="short", sl=sl_s, tp=tp_s), bars, CFG)
    assert result["outcome"] == OUTCOME_WIN
    assert result["exit_price"] == o
    assert result["exit_idx"] == gap_idx


@pytest.mark.unit
def test_entry_bar_gap_tp_fills_at_open_both_directions():
    """D-11 gap check runs on the entry bar too: a long filled already above
    TP wins at the open; a short filled already below TP wins at the open."""
    long_open = TP + 0.0005
    bars = _sculpt(
        _bars(count=10), ENTRY_IDX,
        open_=long_open, high=long_open + 0.0001, low=long_open - 0.0001, close=long_open,
    )
    result = walk_barriers(_position(bars, entry_open=long_open), bars, CFG)
    assert result["outcome"] == OUTCOME_WIN
    assert result["exit_price"] == long_open
    assert result["exit_idx"] == ENTRY_IDX

    short_open = 1.09900 - 0.0005  # below a short TP of 1.09900
    bars = _sculpt(
        _bars(count=10), ENTRY_IDX,
        open_=short_open, high=short_open + 0.0001, low=short_open - 0.0001, close=short_open,
    )
    result = walk_barriers(
        _position(bars, direction="short", entry_open=short_open, sl=1.10100, tp=1.09900),
        bars, CFG,
    )
    assert result["outcome"] == OUTCOME_WIN
    assert result["exit_price"] == short_open
    assert result["exit_idx"] == ENTRY_IDX


# ---------------------------------------------------------------------------
# D-17: inclusive window + TIMEOUT at the final window bar's close
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_timeout_after_exactly_96_bars():
    """96 INCLUSIVE bars: TIMEOUT at exit_idx == E + 95 (NOT E+96), filled at
    that bar's close."""
    bars = _bars(count=200)
    result = walk_barriers(_position(bars), bars, CFG)
    assert result["outcome"] == OUTCOME_TIMEOUT
    assert result["exit_idx"] == ENTRY_IDX + 95
    assert result["exit_price"] == BASE  # flat close of bar E+95
    assert result["exit_time"] == bars["time_utc"].iloc[ENTRY_IDX + 95]
    assert result["exit_idx"] - ENTRY_IDX + 1 == 96  # exactly 96 INCLUSIVE bars


@pytest.mark.unit
def test_timeout_with_two_bar_window():
    cfg = bt_cfg(time_barrier_bars=2)
    bars = _bars(count=20)
    result = walk_barriers(_position(bars, cfg=cfg), bars, cfg)
    assert result["outcome"] == OUTCOME_TIMEOUT
    assert result["exit_idx"] == ENTRY_IDX + 1
    assert result["exit_price"] == BASE


@pytest.mark.unit
def test_two_bar_window_sl_on_last_window_bar():
    cfg = bt_cfg(time_barrier_bars=2)
    bars = _bars(count=20)
    bars = sculpt_low(bars, ENTRY_IDX + 1, SL - 0.0001)
    result = walk_barriers(_position(bars, cfg=cfg), bars, cfg)
    assert result["outcome"] == OUTCOME_LOSS
    assert result["exit_idx"] == ENTRY_IDX + 1


@pytest.mark.unit
def test_touch_just_outside_window_times_out():
    """A touch on bar E+2 lies OUTSIDE a 2-bar window [E, E+1] -> TIMEOUT."""
    cfg = bt_cfg(time_barrier_bars=2)
    bars = _bars(count=20)
    bars = sculpt_low(bars, ENTRY_IDX + 2, SL - 0.0001)
    result = walk_barriers(_position(bars, cfg=cfg), bars, cfg)
    assert result["outcome"] == OUTCOME_TIMEOUT
    assert result["exit_idx"] == ENTRY_IDX + 1


@pytest.mark.unit
def test_timeout_near_end_of_data():
    """len(bars) < E + time_barrier_bars -> TIMEOUT at the LAST available bar."""
    bars = _bars(count=ENTRY_IDX + 40)
    result = walk_barriers(_position(bars), bars, CFG)
    assert result["outcome"] == OUTCOME_TIMEOUT
    assert result["exit_idx"] == len(bars) - 1
    assert result["exit_price"] == BASE
    assert result["exit_time"] == bars["time_utc"].iloc[-1]


# ---------------------------------------------------------------------------
# R math literals (convention (a), D-16 cost delta in R units)
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_r_literals_win():
    """Long WIN at TP: r_gross 2.0, r_raw 1.80, r_net 1.70 over risk 0.00100."""
    bars = _bars(count=20)
    bars = sculpt_high(bars, ENTRY_IDX + 1, TP)
    result = walk_barriers(_position(bars), bars, CFG)
    assert result["outcome"] == OUTCOME_WIN
    assert result["r_gross"] == pytest.approx(2.0, abs=1e-12)
    assert result["r_raw"] == pytest.approx(1.80, abs=1e-12)
    assert result["r_net"] == pytest.approx(1.70, abs=1e-12)


@pytest.mark.unit
def test_r_literals_loss():
    """Long LOSS at SL: r_gross exactly -1.0 structural; the entry spread
    pushes r_raw to -1.20 and slippage on both fills pushes r_net to -1.30 —
    both strictly below -1.0 (convention (a) pin)."""
    bars = _bars(count=20)
    bars = sculpt_low(bars, ENTRY_IDX + 1, SL)
    result = walk_barriers(_position(bars), bars, CFG)
    assert result["outcome"] == OUTCOME_LOSS
    assert result["r_gross"] == pytest.approx(-1.0, abs=1e-12)
    assert result["r_raw"] == pytest.approx(-1.20, abs=1e-12)
    assert result["r_net"] == pytest.approx(-1.30, abs=1e-12)
    assert result["r_net"] < result["r_raw"] < -1.0
    # D-16 per-trade cost delta: -2 * slip_px / risk = -2*0.00005/0.001 = -0.10
    assert result["r_net"] - result["r_raw"] == pytest.approx(-0.10, abs=1e-12)


@pytest.mark.unit
def test_r_literals_short_loss_symmetry():
    """Short LOSS mirrors the long math through the shared structural risk."""
    sl_s, tp_s = 1.10100, 1.09800
    bars = _bars(count=20)
    bars = sculpt_high(bars, ENTRY_IDX + 1, sl_s)
    result = walk_barriers(_position(bars, direction="short", sl=sl_s, tp=tp_s), bars, CFG)
    assert result["outcome"] == OUTCOME_LOSS
    assert result["r_gross"] == pytest.approx(-1.0, abs=1e-12)
    assert result["r_raw"] == pytest.approx(-1.20, abs=1e-12)
    assert result["r_net"] == pytest.approx(-1.30, abs=1e-12)
    assert result["r_net"] - result["r_raw"] == pytest.approx(-0.10, abs=1e-12)


@pytest.mark.unit
def test_r_gross_gap_fill_uses_open():
    bars = _bars(count=10)
    gap_open = TP + 0.0005
    bars = _sculpt(bars, ENTRY_IDX + 1, open_=gap_open, high=gap_open, low=BASE, close=gap_open)
    result = walk_barriers(_position(bars), bars, CFG)
    assert result["outcome"] == OUTCOME_WIN
    assert result["exit_price"] == gap_open
    assert result["r_gross"] == pytest.approx((gap_open - BASE) / RISK, abs=1e-12)


@pytest.mark.unit
def test_r_gross_timeout_uses_final_close():
    bars = _bars(count=110)
    result = walk_barriers(_position(bars), bars, CFG)
    assert result["outcome"] == OUTCOME_TIMEOUT
    assert result["r_gross"] == pytest.approx(0.0, abs=1e-12)  # flat close == entry_open


# ---------------------------------------------------------------------------
# Invariants + contract
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_zero_risk_distance_raises():
    bars = _bars(count=10)
    with pytest.raises(ValueError, match="invariant violated"):
        walk_barriers(_position(bars, sl=BASE), bars, CFG)  # sl == entry_open


@pytest.mark.unit
def test_return_dict_has_exactly_resolver_keys():
    bars = _bars(count=20)
    result = walk_barriers(_position(bars), bars, CFG)
    assert set(result) == {
        "outcome", "exit_price", "exit_idx", "exit_time", "r_gross", "r_raw", "r_net",
    }


@pytest.mark.unit
def test_missing_bar_columns_raise():
    full = _bars(count=10)
    pos = _position(full)
    bars = full.drop(columns=["spread"])
    with pytest.raises(ValueError, match="invariant violated"):
        walk_barriers(pos, bars, CFG)


@pytest.mark.unit
def test_none_position_fields_raise():
    bars = _bars(count=10)
    for field in ("entry_open", "sl_price", "tp_price", "entry_idx"):
        bad = dataclasses.replace(_position(bars), **{field: None})
        with pytest.raises(ValueError, match="invariant violated"):
            walk_barriers(bad, bars, CFG)


@pytest.mark.unit
def test_entry_idx_out_of_range_raises():
    bars = _bars(count=10)
    bad = dataclasses.replace(_position(bars), entry_idx=len(bars))
    with pytest.raises(ValueError, match="invariant violated"):
        walk_barriers(bad, bars, CFG)


@pytest.mark.unit
def test_input_bars_not_mutated():
    bars = _bars(count=20)
    bars = sculpt_high(bars, ENTRY_IDX + 1, TP)
    before = bars.copy(deep=True)
    walk_barriers(_position(bars), bars, CFG)
    pd.testing.assert_frame_equal(before, bars)


@pytest.mark.unit
def test_walk_barriers_satisfies_replay_resolver_seam():
    """Lifecycle consistency: replay_symbol accepts walk_barriers as its
    resolver and lands the returned dict verbatim in the label row (the
    03-01 seam contract)."""
    from test_replay import _bars as replay_bars
    from test_replay import _chain

    bars = replay_bars()
    chain = _chain(bars, tap_indices=(28,))
    labels = replay_symbol(bars, chain, CFG, walk_barriers)
    assert len(labels) == 1
    row = labels.iloc[0]
    # The replay world never touches SL 1.08 / TP 1.14 inside 60 bars ->
    # end-of-data TIMEOUT at the last bar's close (the 03-01 boundary lens).
    assert row["outcome"] == OUTCOME_TIMEOUT
    assert row["exit_idx"] == len(bars) - 1
    assert row["exit_time"] == bars["time_utc"].iloc[-1]
    assert row["exit_price"] == float(bars["close"].iloc[-1])
