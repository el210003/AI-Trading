"""Unit tests (SMC-04 + SC1 tier-3): per-completed-leg PD zone derivation —
ranges, equilibrium, creation timing, concurrent history, and zone repaint
immutability. Zones consume the ZIGZAG, never the raw swing list (D-04).
No adapter-tier (MetaTrader5) imports anywhere."""

from __future__ import annotations

from datetime import datetime

import pandas as pd
import pytest
from _detector_fixtures import swing_spec_bars

from ai_trading.detectors.swings import detect_swings
from ai_trading.detectors.zigzag import build_zigzag
from ai_trading.detectors.zones import ZONE_COLUMNS, derive_zones

SYMBOL = "EURUSD"
TIMEFRAME = "M15"
START = datetime(2026, 8, 20, 0, 0)

# Alternating legs with NO same-side replacement: low@10 -> high@15 ->
# low@25 -> high@32. Zigzag = [L0, H1, L1, H2]; pairs = 3 zones.
LEG_SPEC = [
    (10, "low", 1.08000),
    (15, "high", 1.11000),
    (25, "low", 1.07000),
    (32, "high", 1.12000),
]


def _leg_bars(count: int = 40) -> pd.DataFrame:
    """Build the LEG_SPEC sculpts on a full-size base (sculpts reach bar 32),
    then truncate to `count` bars for the test's visibility horizon."""
    base = swing_spec_bars(SYMBOL, TIMEFRAME, START, max(count, 40), LEG_SPEC)
    return base.iloc[:count].copy()


def _zones_for(bars: pd.DataFrame) -> pd.DataFrame:
    zigzag = build_zigzag(detect_swings(bars.copy(), TIMEFRAME))
    return derive_zones(zigzag.copy(), bars.copy())


def _confirm_close(bars: pd.DataFrame, extreme_idx: int) -> pd.Timestamp:
    """Close time of the confirmation bar (extreme + 2) = created_at."""
    return bars.iloc[extreme_idx + 2]["time_utc"] + pd.Timedelta(minutes=15)


# ---------------------------------------------------------------------------
# Per-leg derivation (D-09)
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_up_leg_zone_range_and_equilibrium():
    """Sculpted low->high leg yields one up zone with the sculpted extremes
    and equilibrium at the exact midpoint."""
    # Frame ends at the confirmation bar so the lifecycle never advances
    # (created_at = open time of the NEXT bar) — state stays unmitigated.
    bars = _leg_bars(18)
    zones = _zones_for(bars)
    assert len(zones) == 1
    z = zones.iloc[0]
    assert z["leg_direction"] == "up"
    assert z["range_low"] == 1.08000
    assert z["range_high"] == 1.11000
    assert z["equilibrium"] == pytest.approx((1.08000 + 1.11000) / 2)
    assert z["state"] == "unmitigated"


@pytest.mark.unit
def test_down_leg_zone_mirror():
    """Sculpted high->low leg yields one down zone (mirror)."""
    bars = _leg_bars(28)  # through L1's confirmation bar (27)
    zones = _zones_for(bars)
    down = zones[zones["leg_direction"] == "down"]
    assert len(down) == 1
    z = down.iloc[0]
    assert z["range_high"] == 1.11000
    assert z["range_low"] == 1.07000
    assert z["equilibrium"] == pytest.approx((1.07000 + 1.11000) / 2)


@pytest.mark.unit
def test_created_at_is_completing_swing_confirmation():
    """created_at equals the completing swing's confirmed_at (confirmation-bar
    close), not the extreme bar's time."""
    bars = _leg_bars(18)
    zigzag = build_zigzag(detect_swings(bars.copy(), TIMEFRAME))
    high_point = zigzag[zigzag["side"] == "high"].iloc[0]
    zones = _zones_for(bars)
    assert zones.iloc[0]["created_at"] == high_point["confirmed_at"]
    assert zones.iloc[0]["created_at"] == _confirm_close(bars, 15)
    assert zones.iloc[0]["created_at"] != bars.iloc[15]["time_utc"]


# ---------------------------------------------------------------------------
# Leg-completion gate (D-09)
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_incomplete_leg_yields_no_zone():
    """A zigzag with a single point yields zero zones; two same-side swings
    absorbed by the zigzag also yield zero zones."""
    # Only the low@10 confirmed (frame ends before high@15's confirmation).
    zones = _zones_for(_leg_bars(16))
    assert len(zones) == 0
    # Two same-side swing highs (20 then 24, more extreme) — the zigzag
    # absorbs them into ONE point -> no completed leg -> no zones.
    spec = [(20, "high", 1.11000), (24, "high", 1.12000)]
    bars = swing_spec_bars(SYMBOL, TIMEFRAME, START, 26, spec)
    assert len(_zones_for(bars)) == 0


@pytest.mark.unit
def test_two_legs_two_coexisting_zones():
    """Two completed legs -> two zones present simultaneously (full history,
    D-12), each with its own state/timestamps."""
    bars = _leg_bars(28)  # zigzag = [L0, H1, L1]
    zones = _zones_for(bars)
    assert len(zones) == 2
    assert list(zones["leg_direction"]) == ["up", "down"]
    assert zones.iloc[0]["range_low"] == 1.08 and zones.iloc[0]["range_high"] == 1.11
    assert zones.iloc[1]["range_low"] == 1.07 and zones.iloc[1]["range_high"] == 1.11


# ---------------------------------------------------------------------------
# IDs + ordering
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_zone_ids_sequential_and_sorted():
    """IDs sequential Z0001.. per symbol in creation order; frame sorted by
    (symbol, created_at)."""
    bars = _leg_bars(35)  # zigzag = [L0, H1, L1, H2] -> 3 zones
    zones = _zones_for(bars)
    assert len(zones) == 3
    assert list(zones["zone_id"]) == [
        f"{SYMBOL}-{TIMEFRAME}-Z0001",
        f"{SYMBOL}-{TIMEFRAME}-Z0002",
        f"{SYMBOL}-{TIMEFRAME}-Z0003",
    ]
    assert list(zones["created_at"]) == sorted(zones["created_at"])
    assert list(zones.columns) == ZONE_COLUMNS


# ---------------------------------------------------------------------------
# Contracts (Pitfall 10, SC5)
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_empty_frame_contracts():
    """Empty zigzag or empty bars -> schema-correct empty frame."""
    bars = _leg_bars(18)
    zigzag = build_zigzag(detect_swings(bars.copy(), TIMEFRAME))
    empty_zigzag = zigzag.iloc[:0].copy()
    zones = derive_zones(empty_zigzag, bars.copy())
    assert len(zones) == 0 and list(zones.columns) == ZONE_COLUMNS
    zones_b = derive_zones(zigzag.copy(), bars.iloc[:0].copy())
    assert len(zones_b) == 0 and list(zones_b.columns) == ZONE_COLUMNS


@pytest.mark.unit
def test_input_frames_not_mutated():
    """zigzag and bars frames are bit-identical before/after derive_zones."""
    bars = _leg_bars(28)
    zigzag = build_zigzag(detect_swings(bars.copy(), TIMEFRAME))
    zigzag_before = zigzag.copy(deep=True)
    bars_before = bars.copy(deep=True)
    derive_zones(zigzag.copy(), bars.copy())
    pd.testing.assert_frame_equal(zigzag_before, zigzag)
    pd.testing.assert_frame_equal(bars_before, bars)


# ---------------------------------------------------------------------------
# Tier-3 repaint (SC1 zone tier)
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_completed_leg_zones_immutable_under_appended_bars():
    """Zones derived from completed legs are identical between every prefix
    run and the visible subset of the full-frame run; chunked appends
    preserve this.

    Visibility horizon: a zone is point-in-time comparable at prefix k iff
    its lifecycle could start within the prefix — created_at STRICTLY before
    the prefix's last close (created_at == the prefix's last close means the
    first advancing bar lies beyond the prefix, so its lifecycle stamps are
    not yet determined). Both sides are filtered with the same strict
    horizon."""
    bars = _leg_bars(60)
    full = _zones_for(bars)

    def _visible(k: int) -> pd.DataFrame:
        horizon = bars.iloc[:k]["time_utc"].iloc[-1] + pd.Timedelta(minutes=15)
        return full[full["created_at"] < horizon].reset_index(drop=True)

    for k in range(13, len(bars)):
        prefix = _zones_for(bars.iloc[:k].copy())
        horizon = bars.iloc[:k]["time_utc"].iloc[-1] + pd.Timedelta(minutes=15)
        prefix_visible = prefix[prefix["created_at"] < horizon].reset_index(drop=True)
        pd.testing.assert_frame_equal(prefix_visible, _visible(k), check_exact=True)

    for k in range(13, len(bars) - 5, 5):
        prefix = _zones_for(bars.iloc[:k].copy())
        horizon = bars.iloc[:k]["time_utc"].iloc[-1] + pd.Timedelta(minutes=15)
        prefix_visible = prefix[prefix["created_at"] < horizon].reset_index(drop=True)
        pd.testing.assert_frame_equal(prefix_visible, _visible(k), check_exact=True)
