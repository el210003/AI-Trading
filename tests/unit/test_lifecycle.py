"""Unit tests (SMC-05 zone half + D-10/D-11/D-12): bar-by-bar monotone zone
lifecycle — wick-touch mitigation, committed-close invalidation, first-event
timestamps, and the pinned same-bar mitigation-then-invalidation order
(Pitfall 6). No adapter-tier (MetaTrader5) imports anywhere.

Pool terminal-state one-and-done coverage lives in tests/unit/test_sweeps.py
(plan 02-02) — deliberately not duplicated here.

Fixture discipline: engineered bars use EQUAL-HIGH pairs wherever a bar's
high exceeds the zone's completing swing (1.11) — equal highs never form
swings (D-02), so the engineered path cannot replace Z0001's completing
zigzag point. Bars whose high stays below 1.11 may be absorbed swings
(harmless: absorption never alters the zigzag). Low sculpts may append new
zigzag points (new zones) — assertions always target Z0001 by id.
"""

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

# Single up-leg: low@10 (1.08) -> high@15 (1.11). Zone Z0001:
# range 1.08-1.11, equilibrium 1.095, created_at = close of bar 17.
LEG_SPEC = [(10, "low", 1.08000), (15, "high", 1.11000)]

ZID = f"{SYMBOL}-{TIMEFRAME}-Z0001"


def _set_bar(
    df: pd.DataFrame, idx: int, open_: float, high: float, low: float, close: float
) -> pd.DataFrame:
    """Overwrite one bar's OHLC (caller keeps values OHLC-sane)."""
    out = df.copy()
    out.iloc[idx, out.columns.get_indexer(["open", "high", "low", "close"])] = (
        open_,
        high,
        low,
        close,
    )
    return out


def _zone_bars(count: int = 40) -> pd.DataFrame:
    """Base frame with the single-leg sculpt (built full-size, then
    truncated to the requested horizon)."""
    base = swing_spec_bars(SYMBOL, TIMEFRAME, START, max(count, 40), LEG_SPEC)
    return base.iloc[:count].copy()


def _zones_for(bars: pd.DataFrame) -> pd.DataFrame:
    zigzag = build_zigzag(detect_swings(bars.copy(), TIMEFRAME))
    return derive_zones(zigzag.copy(), bars.copy())


def _z0001(bars: pd.DataFrame) -> pd.Series:
    zones = _zones_for(bars)
    matches = zones[zones["zone_id"] == ZID]
    assert len(matches) == 1
    return matches.iloc[0]


# ---------------------------------------------------------------------------
# Mitigation (D-10/A7)
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_wick_touch_mitigates_without_close():
    """A wick into the range interior mitigates with NO close required:
    bar 18 wicks to 1.09 (inside 1.08-1.11) and closes 1.107 (inside)."""
    bars = _zone_bars()
    bars = _set_bar(bars, 18, 1.1000, 1.1080, 1.0900, 1.1070)
    z = _z0001(bars)
    assert z["state"] == "mitigated"
    assert z["mitigated_at"] == bars.iloc[18]["time_utc"]
    assert pd.isna(z["invalidated_at"])


@pytest.mark.unit
def test_wick_poke_beyond_does_not_invalidate():
    """A wick poking BEYOND the far boundary with the close still inside
    mitigates but does NOT invalidate (D-11 committed-close rule)."""
    bars = _zone_bars()
    # Equal-high pair at 18/19 (no swings) poking above range_high = 1.11.
    bars = _set_bar(bars, 18, 1.1000, 1.1130, 1.0900, 1.1080)
    bars = _set_bar(bars, 19, 1.1000, 1.1130, 1.1000, 1.1080)
    z = _z0001(bars)
    assert z["state"] == "mitigated"
    assert z["mitigated_at"] == bars.iloc[18]["time_utc"]
    assert pd.isna(z["invalidated_at"])


# ---------------------------------------------------------------------------
# Invalidation (D-11)
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_close_beyond_invalidates_from_unmitigated():
    """A committed close beyond the far boundary invalidates DIRECTLY from
    unmitigated (invalidated_at stamped, mitigated_at stays NA)."""
    bars = _zone_bars()
    # Equal-high pair: wicks/closes entirely above range_high (low 1.1115
    # never enters the range interior -> no mitigation).
    bars = _set_bar(bars, 18, 1.1000, 1.1150, 1.1115, 1.1150)
    bars = _set_bar(bars, 19, 1.1000, 1.1150, 1.1115, 1.1150)
    z = _z0001(bars)
    assert z["state"] == "invalidated"
    assert pd.isna(z["mitigated_at"])
    assert z["invalidated_at"] == bars.iloc[18]["time_utc"]


@pytest.mark.unit
def test_close_beyond_invalidates_from_mitigated():
    """Mitigation first, then a committed close beyond -> invalidated with
    mitigated_at preserved."""
    bars = _zone_bars()
    bars = _set_bar(bars, 18, 1.1000, 1.1080, 1.0900, 1.1070)  # mitigates
    bars = _set_bar(bars, 19, 1.1000, 1.1150, 1.1115, 1.1150)  # closes beyond
    bars = _set_bar(bars, 20, 1.1000, 1.1150, 1.1115, 1.1150)
    z = _z0001(bars)
    assert z["state"] == "invalidated"
    assert z["mitigated_at"] == bars.iloc[18]["time_utc"]
    assert z["invalidated_at"] == bars.iloc[19]["time_utc"]


@pytest.mark.unit
def test_same_bar_double_stamp_order():
    """One bar that wick-enters the range AND closes beyond stamps BOTH
    timestamps (mitigation checked first): mitigated_at <= invalidated_at,
    final state invalidated (Pitfall 6)."""
    bars = _zone_bars()
    # bar 18: wick to 1.09 (enters range) AND closes 1.115 (beyond 1.11);
    # equal-high pair with bar 19 so no swing replaces the completing point.
    bars = _set_bar(bars, 18, 1.1000, 1.1150, 1.0900, 1.1150)
    bars = _set_bar(bars, 19, 1.1000, 1.1150, 1.1115, 1.1150)
    z = _z0001(bars)
    assert z["state"] == "invalidated"
    assert z["mitigated_at"] == bars.iloc[18]["time_utc"]
    assert z["invalidated_at"] == bars.iloc[18]["time_utc"]
    assert z["mitigated_at"] <= z["invalidated_at"]


# ---------------------------------------------------------------------------
# Monotonicity + creation-bar pin
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_lifecycle_monotone_first_event_timestamps():
    """No fixture path regresses the state or overwrites first-event
    timestamps: mitigation at bar 18 survives pokes and re-touches; the
    later invalidation stamps invalidated_at without touching mitigated_at."""
    bars = _zone_bars()
    bars = _set_bar(bars, 18, 1.1000, 1.1080, 1.0900, 1.1070)  # mitigates
    bars = _set_bar(bars, 19, 1.1000, 1.1130, 1.1000, 1.1080)  # poke, no invalidation
    bars = _set_bar(bars, 20, 1.1000, 1.1130, 1.1000, 1.1080)
    bars = _set_bar(bars, 21, 1.1000, 1.1080, 1.0900, 1.1070)  # re-touch inside
    bars = _set_bar(bars, 22, 1.1000, 1.1080, 1.0900, 1.1070)
    bars = _set_bar(bars, 23, 1.1000, 1.1150, 1.1115, 1.1150)  # closes beyond
    bars = _set_bar(bars, 24, 1.1000, 1.1150, 1.1115, 1.1150)
    bars = _set_bar(bars, 25, 1.1000, 1.1080, 1.0900, 1.0950)  # post-invalidation
    z = _z0001(bars)
    assert z["state"] == "invalidated"
    assert z["mitigated_at"] == bars.iloc[18]["time_utc"]
    assert z["invalidated_at"] == bars.iloc[23]["time_utc"]


@pytest.mark.unit
def test_zone_not_advanced_before_creation_bar():
    """The creating confirmation bar (17) never advances its own zone:
    through bar 17 the zone is unmitigated even though bar 17 trades inside
    the range; advancement starts at the bar opening at created_at (bar 18)."""
    through_confirmation = _zone_bars(18)  # bars 0..17
    z = _z0001(through_confirmation)
    assert z["state"] == "unmitigated"
    assert pd.isna(z["mitigated_at"])
    created_at = z["created_at"]
    assert created_at == through_confirmation.iloc[17]["time_utc"] + pd.Timedelta(
        minutes=15
    )
    through_first_advancing = _zone_bars(19)  # bars 0..18 — bar 18 opens at created_at
    z2 = _z0001(through_first_advancing)
    assert z2["state"] == "mitigated"
    assert z2["mitigated_at"] == through_first_advancing.iloc[18]["time_utc"]


@pytest.mark.unit
def test_zone_frozen_after_invalidation():
    """Bars after invalidation never touch the zone: state and timestamps
    stay frozen even when later bars wick deep into the range."""
    bars = _zone_bars()
    bars = _set_bar(bars, 18, 1.1000, 1.1150, 1.1115, 1.1150)  # invalidates
    bars = _set_bar(bars, 19, 1.1000, 1.1150, 1.1115, 1.1150)
    bars = _set_bar(bars, 20, 1.1000, 1.1080, 1.0900, 1.0950)  # deep inside
    bars = _set_bar(bars, 21, 1.1000, 1.1080, 1.0900, 1.0950)
    z = _z0001(bars)
    assert z["state"] == "invalidated"
    assert z["invalidated_at"] == bars.iloc[18]["time_utc"]
    assert pd.isna(z["mitigated_at"])


# ---------------------------------------------------------------------------
# Contracts
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_empty_frame_contract():
    """Empty zigzag or empty bars -> schema-correct empty frame."""
    bars = _zone_bars(18)
    zigzag = build_zigzag(detect_swings(bars.copy(), TIMEFRAME))
    zones = derive_zones(zigzag.iloc[:0].copy(), bars.copy())
    assert len(zones) == 0 and list(zones.columns) == ZONE_COLUMNS
    zones_b = derive_zones(zigzag.copy(), bars.iloc[:0].copy())
    assert len(zones_b) == 0 and list(zones_b.columns) == ZONE_COLUMNS
