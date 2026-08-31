"""Unit tests (SMC-01 + SC1 foundations): strict 2/2 fractal swings with
confirmation-shifted stamping, output schema, edge contracts, and Wilder ATR.
No adapter-tier (MetaTrader5) imports anywhere."""

from __future__ import annotations

from datetime import datetime

import numpy as np
import pandas as pd
import pytest
from _detector_fixtures import flat_bars, swing_spec_bars

from ai_trading.detectors.atr import wilders_atr
from ai_trading.detectors.swings import SWING_COLUMNS, detect_swings
from ai_trading.normalize import TIMEFRAME_MINUTES

SYMBOL = "EURUSD"
TIMEFRAME = "M15"
START = datetime(2026, 8, 20, 0, 0)


def _bars(count: int) -> pd.DataFrame:
    return flat_bars(SYMBOL, TIMEFRAME, START, count)


def _spec(count: int, spec) -> pd.DataFrame:
    return swing_spec_bars(SYMBOL, TIMEFRAME, START, count, spec)


# ---------------------------------------------------------------------------
# Strictness (D-02)
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_flat_frame_has_no_swings():
    """A constant-price frame produces zero swing records."""
    out = detect_swings(_bars(40), TIMEFRAME)
    assert len(out) == 0


@pytest.mark.unit
def test_equal_neighbor_price_disqualifies_swing():
    """An equal-price neighbor high within the 2-bar window disqualifies the
    otherwise-valid swing (strict > only — D-02)."""
    # bars 20 and 21 carry the SAME elevated high -> neither is a swing.
    bars = _spec(40, [(20, "high", 1.11000), (21, "high", 1.11000)])
    out = detect_swings(bars, TIMEFRAME)
    assert len(out[out["side"] == "high"]) == 0
    assert len(out) == 0  # flat lows cannot swing either


@pytest.mark.unit
def test_single_sculpted_peak_emits_one_swing_high():
    """One sculpted strict peak at bar i -> exactly one swing-high record."""
    bars = _spec(40, [(20, "high", 1.11000)])
    out = detect_swings(bars, TIMEFRAME)
    highs = out[out["side"] == "high"]
    assert len(highs) == 1
    row = highs.iloc[0]
    assert row["bar_time"] == bars.iloc[20]["time_utc"]
    assert row["price"] == 1.11000
    assert row["side"] == "high"
    assert row["confirmed_at"] == bars.iloc[22]["time_utc"] + pd.Timedelta(
        minutes=TIMEFRAME_MINUTES[TIMEFRAME]
    )


# ---------------------------------------------------------------------------
# Confirmation stamping (D-01)
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_swing_confirmed_only_at_second_right_bar_close():
    """confirmed_at equals the confirmation bar's close time:
    extreme bar i -> time_utc[i+2] + TF minutes."""
    bars = _spec(40, [(20, "high", 1.11000)])
    out = detect_swings(bars, TIMEFRAME)
    expected = bars.iloc[22]["time_utc"] + pd.Timedelta(minutes=15)
    assert out.iloc[0]["confirmed_at"] == expected


@pytest.mark.unit
def test_truncated_frame_hides_unconfirmed_swing():
    """A frame truncated before the confirmation bar contains NO record of the
    swing (D-01 confirmation-shift proof)."""
    bars = _spec(40, [(20, "high", 1.11000)])
    short = bars.iloc[:22]  # extreme at 20, only ONE right-side bar (21)
    assert len(detect_swings(short, TIMEFRAME)) == 0
    just_enough = bars.iloc[:23]  # two right-side bars (21, 22) -> confirms
    out = detect_swings(just_enough, TIMEFRAME)
    assert len(out) == 1 and out.iloc[0]["side"] == "high"


@pytest.mark.unit
def test_last_two_bars_never_emit():
    """The last 2 rows of any frame can never emit (NaN-tail disqualification)."""
    n = 30
    bars = _spec(n, [(n - 1, "high", 1.11000), (n - 2, "high", 1.10900)])
    out = detect_swings(bars, TIMEFRAME)
    assert len(out) == 0


# ---------------------------------------------------------------------------
# Schema (D-03)
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_output_schema_exact_columns():
    """Output schema is exactly the 6 pinned columns with correct dtypes."""
    bars = _spec(40, [(20, "high", 1.11000), (30, "low", 1.09000)])
    out = detect_swings(bars, TIMEFRAME)
    assert list(out.columns) == SWING_COLUMNS
    assert pd.api.types.is_datetime64_any_dtype(out["bar_time"])
    assert pd.api.types.is_datetime64_any_dtype(out["confirmed_at"])
    assert out["bar_time"].dt.tz is None
    assert out["confirmed_at"].dt.tz is None
    assert pd.api.types.is_float_dtype(out["price"])


# ---------------------------------------------------------------------------
# Edge contracts (Pitfall 10, A9, SC5)
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_empty_frame_returns_full_schema():
    """Empty input -> empty frame with all 6 columns."""
    out = detect_swings(_bars(0), TIMEFRAME)
    assert len(out) == 0
    assert list(out.columns) == SWING_COLUMNS


@pytest.mark.unit
def test_short_frame_below_fractal_width_no_swings():
    """A frame shorter than the 5-bar fractal window emits nothing."""
    out = detect_swings(_bars(4), TIMEFRAME)
    assert len(out) == 0
    assert list(out.columns) == SWING_COLUMNS


@pytest.mark.unit
def test_dual_swing_same_bar_high_then_low():
    """One bar sculpted as both strict swing high and swing low emits two
    records, high before low (A9)."""
    # bar 20: high 1.12 above all neighbor highs (1.09), low 1.08 below all
    # neighbor lows (1.11) on a flat 1.10 base — strict on BOTH sides.
    band = swing_spec_bars(
        SYMBOL, TIMEFRAME, START, 40,
        [(18, "high", 1.09000), (18, "low", 1.11000),
         (19, "high", 1.09000), (19, "low", 1.11000),
         (20, "high", 1.12000), (20, "low", 1.08000),
         (21, "high", 1.09000), (21, "low", 1.11000),
         (22, "high", 1.09000), (22, "low", 1.11000)],
    )
    out = detect_swings(band, TIMEFRAME)
    assert len(out) == 2
    assert list(out["side"]) == ["high", "low"]
    assert out.iloc[0]["bar_time"] == out.iloc[1]["bar_time"] == band.iloc[20]["time_utc"]
    assert out.iloc[0]["price"] == 1.12000 and out.iloc[1]["price"] == 1.08000


@pytest.mark.unit
def test_input_frame_not_mutated():
    """The bars frame is bit-identical before/after detect_swings (SC5)."""
    bars = _spec(40, [(20, "high", 1.11000), (30, "low", 1.09000)])
    before = bars.copy(deep=True)
    detect_swings(bars, TIMEFRAME)
    pd.testing.assert_frame_equal(before, bars)


# ---------------------------------------------------------------------------
# Wilder ATR (A4, Pitfall 7)
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_wilders_atr_warmup_nan_and_hand_computed_values():
    """Rows before min_periods accumulate are NaN; a hand-computed constant-TR
    series (TR == 2.0 per bar) yields exactly 2.0 after the warmup under the
    pinned ewm convention."""
    n = 20
    base = _bars(n)
    # Force TR == 2.0 for every bar: high = low + 2, close = high (so both
    # gap terms equal 2 as well).
    df = base.copy()
    df["high"] = base["low"] + 2.0
    df["close"] = df["high"]
    atr = wilders_atr(df, period=14)
    assert atr.iloc[:13].isna().all()  # min_periods=14 warmup
    assert np.isclose(atr.iloc[13:], 2.0).all()
    # hand-computed: constant TR series under ewm(alpha=1/14, adjust=False)
    # seeds with TR[0]=2.0 and stays 2.0 forever.
    hand = pd.Series(np.nan, index=df.index)
    hand.iloc[13:] = 2.0
    pd.testing.assert_series_equal(atr, hand, check_names=False)
