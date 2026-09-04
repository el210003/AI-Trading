"""Unit tests for the setup lifecycle state machine (SETUP-03/04) — the
pending (D-01 trigger / D-04 invalidation / window expiry) and active
(D-02/D-03 ``walk_barriers`` reuse: TP/SL/96-bar timeout, D-10 SL-first tie,
D-11 gap-open fill) transitions.

Builds deterministic small bar frames; no MT5, no detector chain re-run.
"""

from __future__ import annotations

import pandas as pd
import pytest
from _setup_fixtures import make_setup_frame, setup_cfg

from ai_trading.setup.lifecycle import apply_lifecycle, resolve_active, resolve_pending

_START = pd.Timestamp("2026-08-20T12:00:00")


def _bars(n, *, offset=0.0, start=None):
    """Flat 1.10-frame with the canonical bar columns for the lifecycle tests."""
    from conftest import make_bars

    start = start if start is not None else _START
    df = make_bars("EURUSD", "M15", start.to_pydatetime(), n, offset_hours=0)
    for col in ("open", "high", "low", "close"):
        df[col] = 1.10 + offset
    df["spread"] = 20
    return df


def _setup(**overrides):
    base = {
        "symbol": "EURUSD",
        "timeframe": "M15",
        "direction": "long",
        "entry": 1.10,
        "sl_price": 1.09,
        "tp_price": 1.15,
        "zone_range_high": 1.16,
        "zone_range_low": 1.07,
        "created_at": _START,
    }
    base.update(overrides)
    return base


def _active_setup(idx, minutes):
    trigger_time = _START + pd.Timedelta(minutes=minutes)
    return _setup(status="active", trigger_bar_idx=idx, trigger_time=trigger_time)


# ---------------------------------------------------------------------------
# Pending phase (D-01 / D-04)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_pending_trigger_becomes_active():
    bars = _bars(12)
    bars.loc[2, "low"] = 1.095  # trades through entry 1.10 (long)
    setup = _setup()
    assert resolve_pending(setup, bars, setup_cfg()) == "active"


@pytest.mark.unit
def test_pending_window_expires():
    bars = _bars(12)
    setup = _setup(entry=1.08)  # default lows (~1.100) never touch 1.08
    assert resolve_pending(setup, bars, setup_cfg()) == "expired"


@pytest.mark.unit
def test_pending_structure_break_invalidates():
    bars = _bars(12)
    bars.loc[1, "close"] = 1.17  # close beyond zone_range_high 1.16 -> break
    setup = _setup(entry=1.08)
    assert resolve_pending(setup, bars, setup_cfg()) == "invalidated"


@pytest.mark.unit
def test_pending_short_trigger_becomes_active():
    bars = _bars(12, offset=0.0)
    bars.loc[3, "high"] = 1.105  # trades through entry 1.10 (short)
    setup = _setup(direction="short", zone_range_low=1.07)
    assert resolve_pending(setup, bars, setup_cfg()) == "active"


@pytest.mark.unit
def test_pending_stays_pending_inside_window():
    bars = _bars(6)
    setup = _setup(entry=1.08)
    assert resolve_pending(setup, bars, setup_cfg()) == "pending"


# ---------------------------------------------------------------------------
# Active phase (D-02 / D-03 via walk_barriers)
# ---------------------------------------------------------------------------

_WIN_BARS = _bars(20)
_WIN_BARS.loc[5, "high"] = 1.1500  # TP hit (long)
_SL_BARS = _bars(20)
_SL_BARS.loc[5, "low"] = 1.0899  # SL hit (long)
_TIMEOUT_BARS = _bars(20)


@pytest.mark.unit
def test_active_tp_hit_with_correct_r_gross():
    setup = _active_setup(3, 45)
    result = resolve_active(setup, _WIN_BARS, setup_cfg())
    assert result["next_status"] == "tp_hit"
    assert result["outcome"] == "WIN"
    # exit at TP 1.15 over risk (1.10-1.09=0.01): (1.15-1.10)/0.01 = 5.0
    assert result["r_gross"] == pytest.approx(5.0)
    assert result["exit_price"] == pytest.approx(1.15)


@pytest.mark.unit
def test_active_sl_hit_with_correct_r_gross():
    setup = _active_setup(3, 45)
    result = resolve_active(setup, _SL_BARS, setup_cfg())
    assert result["next_status"] == "sl_hit"
    assert result["outcome"] == "LOSS"
    # exit at SL 1.09: (1.09-1.10)/0.01 = -1.0
    assert result["r_gross"] == pytest.approx(-1.0)
    assert result["exit_price"] == pytest.approx(1.09)


@pytest.mark.unit
def test_active_time_barrier_expires():
    setup = _active_setup(2, 30)
    cfg = setup_cfg(time_barrier_bars=5)  # compact 5-bar inclusive barrier (D-17)
    result = resolve_active(setup, _TIMEOUT_BARS, cfg)
    assert result["next_status"] == "expired"
    assert result["outcome"] == "TIMEOUT"
    # timeout exits at the final window bar close (trigger 2 + 5 = bar 6 -> idx 6)
    assert result["exit_idx"] == 6
    assert result["exit_price"] == pytest.approx(float(_TIMEOUT_BARS["close"].iloc[6]))


@pytest.mark.unit
def test_active_gap_open_beyond_barrier_is_d11():
    """D-11: a bar OPENING beyond a barrier fills at the open (entry bar too)."""
    bars = _bars(20)
    bars.loc[4, "open"] = 1.088 # gap below SL 1.09 on the entry bar
    bars.loc[4, "low"] = 1.088
    bars.loc[4, "high"] = 1.095
    setup = _active_setup(4, 60)
    result = resolve_active(setup, bars, setup_cfg())
    assert result["next_status"] == "sl_hit"
    assert result["outcome"] == "LOSS"
    assert result["exit_price"] == pytest.approx(1.088)  # filled at the OPEN


@pytest.mark.unit
def test_active_sl_first_tie_on_one_bar_is_d10():
    """D-10: with both SL and TP inside one bar, the SL-first convention wins."""
    bars = _bars(20)
    bars.loc[6, "low"] = 1.0800   # touches SL
    bars.loc[6, "high"] = 1.1600  # also touches TP in the same bar
    setup = _active_setup(5, 75)
    result = resolve_active(setup, bars, setup_cfg())
    assert result["next_status"] == "sl_hit"
    assert result["outcome"] == "LOSS"


# ---------------------------------------------------------------------------
# apply_lifecycle
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_apply_lifecycle_transitions_pending_to_active_and_fills_trigger():
    bars = _bars(12)
    bars.loc[2, "low"] = 1.0900
    setups = make_setup_frame(
        [{"status": "pending", "entry": 1.095, "created_at": _START}]
    )
    out = apply_lifecycle(setups, {"EURUSD": bars}, setup_cfg())
    assert out.iloc[0]["status"] == "active"
    assert not pd.isna(out.iloc[0]["trigger_bar_idx"])
    assert out.iloc[0]["trigger_bar_idx"] == 2


@pytest.mark.unit
def test_apply_lifecycle_does_not_mutate_input():
    bars = _bars(12)
    bars.loc[2, "low"] = 1.0900
    setups = make_setup_frame(
        [{"status": "pending", "entry": 1.095, "created_at": _START}]
    )
    before = setups.copy()
    out = apply_lifecycle(setups, {"EURUSD": bars}, setup_cfg())
    pd.testing.assert_frame_equal(setups, before)
    assert out.iloc[0]["status"] == "active"


@pytest.mark.unit
def test_apply_lifecycle_skips_terminal_statuses():
    bars = _bars(20)
    setups = make_setup_frame([{"status": "tp_hit", "entry": 1.10}])
    out = apply_lifecycle(setups, {"EURUSD": bars}, setup_cfg())
    assert out.iloc[0]["status"] == "tp_hit"
