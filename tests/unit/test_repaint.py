"""SC1 repaint suite — the two-tier point-in-time contract as an executable
specification (ROADMAP SC1 + D-04 + D-15). No adapter-tier imports anywhere.

Tiers proven here (swing tier; pools/zones tiers extend this suite in plans
02-02/02-03 per RESEARCH Pitfall 2):
- T1: appending future bars (1-by-1 or chunked) never alters already-visible
  swing records — prefix output equals the visible subset of full-frame
  output with check_exact=True.
- T2: zigzag rows before the final point are immutable across prefixes; the
  final point may be replaced only by a MORE-EXTREME same-side confirmation
  (D-04). The replacement-legitimacy test FAILS if tail replacement were
  disabled — it is the guard against over-strict repaint assertions.
- Structure-shift labels (BOS/CHoCH) derived from completed legs are stable
  across prefixes; labels for the incomplete tail leg may change.
"""

from __future__ import annotations

from datetime import datetime

import pandas as pd
import pytest
from _detector_fixtures import (
    assert_point_in_time_prefix_equality,
    prefix_close_time,
    swing_spec_bars,
)

from ai_trading.detectors.swings import detect_swings
from ai_trading.detectors.zigzag import build_zigzag

SYMBOL = "EURUSD"
TIMEFRAME = "M15"
START = datetime(2026, 8, 20, 0, 0)

# Known swing sequence: low@10 -> high@15 -> low@25 -> high@32, each leg
# completing (confirmed) well before the next extreme forms.
LEG_SPEC = [
    (10, "low", 1.08000),
    (15, "high", 1.11000),
    (25, "low", 1.07000),
    (32, "high", 1.12000),
]


def _leg_bars() -> pd.DataFrame:
    return swing_spec_bars(SYMBOL, TIMEFRAME, START, 40, LEG_SPEC)


def _structure_shifts(zigzag: pd.DataFrame, bars: pd.DataFrame) -> list[tuple]:
    """Minimal BOS/CHoCH labeler — REPAINT-TEST ONLY (never a src/ feature).

    A structure shift occurs when a bar's close crosses the most recent
    CONFIRMED opposite-side zigzag point (point-in-time: only points with
    confirmed_at <= the bar's close time are visible). BOS continues the
    current leg direction; CHoCH reverses it. Returns (bar_time, kind, level)
    tuples in bar order, at most one label per bar.
    """
    step = bars["time_utc"].iloc[1] - bars["time_utc"].iloc[0]
    labels: list[tuple] = []
    zz = zigzag.sort_values("confirmed_at")
    for i in range(len(bars)):
        close_time = bars.iloc[i]["time_utc"] + step
        visible = zz[zz["confirmed_at"] <= close_time]
        if visible.empty:
            continue
        last = visible.iloc[-1]
        if last["side"] == "high":
            last_high = visible[visible["side"] == "high"].iloc[-1]
            if bars.iloc[i]["close"] > last_high["price"]:
                labels.append((bars.iloc[i]["time_utc"], "BOS", last_high["price"]))
        else:
            last_low = visible[visible["side"] == "low"].iloc[-1]
            if bars.iloc[i]["close"] < last_low["price"]:
                labels.append((bars.iloc[i]["time_utc"], "BOS", last_low["price"]))
    return labels


# ---------------------------------------------------------------------------
# T1: swing immutability under future-bar appends (SC1)
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_repaint_t1_appending_bars_never_alters_confirmed_swings():
    """For every prefix, prefix swing output == visible subset of full output
    (check_exact=True) — the 1-by-1 T1 proof."""
    bars = _leg_bars()
    assert_point_in_time_prefix_equality(
        lambda b: detect_swings(b, TIMEFRAME), bars, min_prefix=10
    )


@pytest.mark.unit
def test_repaint_t1_chunked_appends():
    """T1 equality also holds when future bars arrive in +5 and +17-bar
    chunks (staged appends, not 1-by-1)."""
    bars = _leg_bars()
    full = detect_swings(bars.copy(), TIMEFRAME)
    for chunk in (5, 17):
        for k in range(10, len(bars) - chunk, chunk):
            staged = detect_swings(bars.iloc[:k].copy(), TIMEFRAME)
            visible = full[
                full["confirmed_at"] <= prefix_close_time(bars, k)
            ].reset_index(drop=True)
            pd.testing.assert_frame_equal(staged, visible, check_exact=True)


# ---------------------------------------------------------------------------
# T2: zigzag tail-only mutability (D-04 + SC1)
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_repaint_t2_zigzag_rows_before_tail_immutable():
    """For every prefix, every non-tail prefix zigzag row is identical to the
    corresponding leading row of the full-frame zigzag (same bar_time, price,
    side, confirmed_at)."""
    bars = _leg_bars()
    full_zz = build_zigzag(detect_swings(bars.copy(), TIMEFRAME))
    for k in range(10, len(bars)):
        prefix_zz = build_zigzag(detect_swings(bars.iloc[:k].copy(), TIMEFRAME))
        if len(prefix_zz) <= 1:
            continue
        head = prefix_zz.iloc[:-1].reset_index(drop=True)
        expected = full_zz.iloc[: len(head)].reset_index(drop=True)
        pd.testing.assert_frame_equal(head, expected, check_exact=True)


@pytest.mark.unit
def test_repaint_t2_tail_replacement_is_legitimate():
    """A later same-side MORE-EXTREME confirmation replaces the zigzag tail
    (D-04). This test FAILS if tail replacement were disabled — it is the
    guard against over-strict repaint assertions."""
    # high@15 (1.11) confirms at close of bar 17; higher high@18 (1.115)
    # confirms at close of bar 20 -> replaces the tail.
    bars = swing_spec_bars(
        SYMBOL, TIMEFRAME, START, 40,
        [(10, "low", 1.08000), (15, "high", 1.11000), (18, "high", 1.11500)],
    )
    before = build_zigzag(detect_swings(bars.iloc[:20].copy(), TIMEFRAME))
    full = build_zigzag(detect_swings(bars.copy(), TIMEFRAME))
    # At the prefix, the HH@18 has only one right-side bar -> unconfirmed;
    # the tail is still high@15.
    assert len(before) == 2
    assert before.iloc[-1]["bar_time"] == bars.iloc[15]["time_utc"]
    assert before.iloc[-1]["price"] == 1.11000
    # In the full frame the tail was REPLACED, not appended (same side).
    assert len(full) == 2
    assert full.iloc[-1]["bar_time"] == bars.iloc[18]["time_utc"]
    assert full.iloc[-1]["price"] == 1.11500
    # Heads are immutable (tier-2 core).
    pd.testing.assert_frame_equal(
        before.iloc[:-1].reset_index(drop=True),
        full.iloc[:-1].reset_index(drop=True),
        check_exact=True,
    )


# ---------------------------------------------------------------------------
# Structure-shift label stability (completed legs only)
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_structure_shift_labels_stable_for_completed_legs():
    """BOS/CHoCH labels derived from COMPLETED legs are identical across every
    prefix (prefix labels are a leading slice of full labels); labels for the
    incomplete tail leg may change."""
    # Two BOS crossings against completed legs, sculpted so they create NO
    # same-side replacement swings:
    # - bars 18/19 carry EQUAL highs (1.12) -> neither is a swing (D-02), but
    #   bar 19's close (1.115) crosses the completed high@15 level (1.11)
    #   while the leg up is current -> bullish BOS.
    # - bars 28/29 carry EQUAL lows (1.06) -> neither is a swing; bar 29's
    #   close (1.065) crosses the completed low@25 level (1.07) while the leg
    #   down is current -> bearish BOS.
    bars = swing_spec_bars(
        SYMBOL, TIMEFRAME, START, 40,
        [(10, "low", 1.08000), (15, "high", 1.11000), (25, "low", 1.07000),
         (32, "high", 1.12000), (18, "high", 1.12000), (19, "high", 1.12000),
         (28, "low", 1.06000), (29, "low", 1.06000)],
    )
    bars = bars.copy()
    bars.iloc[19, bars.columns.get_indexer(["close"])] = 1.11500
    bars.iloc[19, bars.columns.get_indexer(["open"])] = 1.10000
    bars.iloc[29, bars.columns.get_indexer(["close"])] = 1.06500
    bars.iloc[29, bars.columns.get_indexer(["open"])] = 1.10000

    def _labels_for(frame: pd.DataFrame) -> list[tuple]:
        return _structure_shifts(
            build_zigzag(detect_swings(frame.copy(), TIMEFRAME)), frame
        )

    full_labels = _labels_for(bars.copy())
    assert any(kind == "BOS" and level == 1.11 for _, kind, level in full_labels), (
        "fixture must produce the completed-leg bullish BOS label"
    )
    assert any(kind == "BOS" and level == 1.07 for _, kind, level in full_labels), (
        "fixture must produce the completed-leg bearish BOS label"
    )
    for k in range(12, len(bars)):
        prefix_labels = _labels_for(bars.iloc[:k].copy())
        assert prefix_labels == full_labels[: len(prefix_labels)]
