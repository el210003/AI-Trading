"""Unit tests (SMC-02 + SMC-05 pool lifecycle + SC1 tier-3): equal-high/low
clustering with as-of ATR tolerance, 2-touch activation, warmup guard, empty
contracts, non-mutation, and pool repaint immutability.

Recorded assumption A6: pools arise from near-equal SWINGS clustering within
tolerance; exactly-equal BARS form no swings and no direct pool (literal
D-02+D-05 composition — research Open Question 3 default, accepted at plan
review). No adapter-tier (MetaTrader5) imports anywhere.

Fixture design: the constant-TR base keeps every True Range at exactly
``TR`` (open=low=base, close=high=base+TR), so ``wilders_atr`` is exactly
``TR`` after warmup and the as-of tolerance is exactly
``tolerance_atr_multiple * TR``. Swing sculpts preserve that invariant by
moving open/close/low together with the sculpted high (high=p, low=open=
close=p-TR) — TR stays TR at the sculpted bar and the bar after it, so test
expectations are hand-derivable without circular ATR computation.
"""

from __future__ import annotations

from datetime import datetime

import numpy as np
import pandas as pd
import pytest

from ai_trading.detectors.atr import wilders_atr
from ai_trading.detectors.pools import EVENT_COLUMNS, POOL_COLUMNS, detect_pools
from ai_trading.detectors.swings import detect_swings

SYMBOL = "EURUSD"
TIMEFRAME = "M15"
START = datetime(2026, 8, 20, 0, 0)
TR = 0.01000
BASE = 1.10000
TOL = 0.1 * TR  # exact as-of tolerance once ATR is warm (0.001)


def _atr_bars(count: int) -> pd.DataFrame:
    """Constant-TR base: open=low=BASE, close=high=BASE+TR for every bar.

    Every True Range is exactly TR (|high-low| = TR, |high - prev_close| = 0,
    |low - prev_close| = TR), so wilders_atr == TR exactly after the 14-bar
    warmup and the as-of tolerance == TOL everywhere."""
    from conftest import make_bars

    df = make_bars(SYMBOL, TIMEFRAME, START, count, offset_hours=3)
    df["open"] = BASE
    df["low"] = BASE
    df["close"] = BASE + TR
    df["high"] = BASE + TR
    return df


def _sculpt_swing_high(df: pd.DataFrame, idx: int, price: float) -> pd.DataFrame:
    """TR-preserving swing-high sculpt: high=price, low=open=close=price-TR.

    OHLC sanity holds while price <= BASE + 2*TR (low stays <= open/close is
    NOT required — low <= min(open, close) IS: open=close=price-TR=low)."""
    out = df.copy()
    out.iloc[idx, out.columns.get_indexer(["open", "low", "close"])] = price - TR
    out.iloc[idx, out.columns.get_indexer(["high"])] = price
    return out


def _equal_high_pair(df: pd.DataFrame, i: int, j: int, price: float) -> pd.DataFrame:
    """Two distant equal swing highs (both strict: neighbors stay at base)."""
    df = _sculpt_swing_high(df, i, price)
    df = _sculpt_swing_high(df, j, price)
    return df


def _pools_for(bars: pd.DataFrame):
    swings = detect_swings(bars.copy(), TIMEFRAME)
    return detect_pools(bars.copy(), swings)


# ---------------------------------------------------------------------------
# Clustering (SMC-02, D-05, A3)
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_equal_highs_cluster_within_tolerance():
    """Two sculpted swing highs within tolerance -> one active pool with
    level = mean of the two activating prices, touch_count = 2, side = high."""
    p = BASE + TR + 0.5 * TOL
    bars = _equal_high_pair(_atr_bars(40), 20, 24, p)
    pools, events = _pools_for(bars)
    active = pools[pools["state"] == "active"]
    assert len(active) == 1
    row = active.iloc[0]
    assert row["side"] == "high"
    assert row["touch_count"] == 2
    assert row["level"] == pytest.approx(p)  # mean of two equal prices
    assert row["pool_id"] == f"{SYMBOL}-{TIMEFRAME}-P0001"
    assert len(events) == 0  # never pierced -> no event


@pytest.mark.unit
def test_tolerance_boundary_inclusive_exclusive():
    """Membership is inclusive at the as-of tolerance: a second high just
    inside the tolerance joins the forming candidate (activating it); a high
    beyond the tolerance opens a separate candidate.

    Both touches sit ABOVE the base high so they are strict swings, and the
    second touch is BELOW the first so its extreme bar cannot pierce the
    forming candidate (a rising touch supersedes it per A5 — tested in
    test_pierce_while_forming_supersedes_candidate). The as-of tolerance is
    exactly 0.1 * TR because the TR-preserving sculpt keeps every True Range
    at TR regardless of sculpt prices."""
    p1 = BASE + 1.5 * TR  # 1.115 — strict swing above neighbors (1.11)
    t = 0.1 * TR  # the exact as-of tolerance (ATR == TR after warmup)
    # inclusive: second high just inside the tolerance (one ulp closer)
    p2_in = np.nextafter(p1 - t, p1)
    assert 0 < p1 - p2_in <= t  # boundary semantics: inclusive (<=)
    bars_in = _sculpt_swing_high(_sculpt_swing_high(_atr_bars(40), 20, p1), 24, p2_in)
    pools_in, _ = _pools_for(bars_in)
    assert len(pools_in[pools_in["state"] == "active"]) == 1
    assert pools_in[pools_in["state"] == "active"].iloc[0]["touch_count"] == 2

    # exclusive: second high beyond the tolerance -> two forming singles
    p2_out = p1 - 2 * t
    assert p1 - p2_out > t
    assert p2_out > BASE + TR  # still a strict swing above the base high
    bars_out = _sculpt_swing_high(_sculpt_swing_high(_atr_bars(40), 20, p1), 24, p2_out)
    pools_out, _ = _pools_for(bars_out)
    assert len(pools_out[pools_out["state"] == "active"]) == 0
    assert len(pools_out[pools_out["state"] == "forming"]) == 2


@pytest.mark.unit
def test_equal_lows_cluster_mirror():
    """Mirror behavior for equal lows (side = low)."""
    bars = _atr_bars(40)
    # TR-preserving swing-low sculpt: low=price, high=open=close=price+TR.
    p = BASE - 0.5 * TOL
    for idx in (20, 24):
        bars = bars.copy()
        bars.iloc[idx, bars.columns.get_indexer(["open", "high", "close"])] = p + TR
        bars.iloc[idx, bars.columns.get_indexer(["low"])] = p
    pools, _ = _pools_for(bars)
    active = pools[pools["state"] == "active"]
    assert len(active) == 1
    assert active.iloc[0]["side"] == "low"
    assert active.iloc[0]["touch_count"] == 2


@pytest.mark.unit
def test_two_touch_activation_timing_and_level_mean():
    """activated_at equals the second touch swing's confirmed_at; level is
    the mean of the two activating prices."""
    p1 = BASE + TR + 0.5 * TOL
    p2 = p1 - 0.25 * TOL  # lower high, within tolerance, at/below pool level
    bars = _atr_bars(40)
    bars = _sculpt_swing_high(bars, 20, p1)
    bars = _sculpt_swing_high(bars, 24, p2)
    swings = detect_swings(bars.copy(), TIMEFRAME)
    pools, _ = detect_pools(bars.copy(), swings)
    active = pools[pools["state"] == "active"]
    assert len(active) == 1
    second_confirmed = swings[swings["bar_time"] == bars.iloc[24]["time_utc"]].iloc[0][
        "confirmed_at"
    ]
    assert active.iloc[0]["activated_at"] == second_confirmed
    assert active.iloc[0]["level"] == pytest.approx((p1 + p2) / 2)


@pytest.mark.unit
def test_third_touch_increments_count_not_level():
    """A third within-tolerance swing before resolution increments
    touch_count; the level stays frozen (A3)."""
    p = BASE + TR + 0.5 * TOL
    bars = _atr_bars(40)
    for idx in (20, 24, 30):
        bars = _sculpt_swing_high(bars, idx, p)
    pools, _ = _pools_for(bars)
    active = pools[pools["state"] == "active"]
    assert len(active) == 1
    assert active.iloc[0]["touch_count"] == 3
    assert active.iloc[0]["level"] == pytest.approx(p)  # mean of equals


# ---------------------------------------------------------------------------
# Forming candidates (A5) + warmup (Pitfall 7)
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_pierce_while_forming_supersedes_candidate():
    """Single touch + a later pierce: no event, candidate remains forming
    (dead-by-supersession, A5)."""
    bars = _atr_bars(40)
    bars = _sculpt_swing_high(bars, 20, BASE + TR + 0.5 * TOL)
    # Pierce the forming candidate's level after its confirmation: equal-high
    # pair at 26/27 above the level (neither is a swing — D-02).
    lvl = BASE + TR + 0.5 * TOL
    for idx in (26, 27):
        bars.iloc[idx, bars.columns.get_indexer(["high"])] = lvl + 0.25 * TOL
    pools, events = _pools_for(bars)
    assert len(events) == 0
    forming = pools[pools["state"] == "forming"]
    assert len(forming) == 1
    assert forming.iloc[0]["touch_count"] == 1
    assert pd.isna(forming.iloc[0]["activated_at"])


@pytest.mark.unit
def test_atr_warmup_produces_no_pools():
    """Swings confirming inside the first ~atr_period bars produce no pools
    (ATR still NaN — clustering skipped, Pitfall 7)."""
    bars = _atr_bars(40)
    bars = _sculpt_swing_high(bars, 5, BASE + TR + 0.5 * TOL)
    bars = _sculpt_swing_high(bars, 8, BASE + TR + 0.5 * TOL)
    pools, events = _pools_for(bars)
    assert len(pools) == 0
    assert len(events) == 0


# ---------------------------------------------------------------------------
# Contracts (Pitfall 10, SC5)
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_empty_frame_contracts():
    """Empty bars or empty swings -> schema-correct empty frames."""
    bars = _atr_bars(0)
    swings = detect_swings(bars.copy(), TIMEFRAME)
    pools, events = detect_pools(bars.copy(), swings)
    assert len(pools) == 0 and list(pools.columns) == POOL_COLUMNS
    assert len(events) == 0 and list(events.columns) == EVENT_COLUMNS

    bars_full = _atr_bars(40)
    empty_swings = detect_swings(bars_full.iloc[:0].copy(), TIMEFRAME)
    pools_b, events_b = detect_pools(bars_full.copy(), empty_swings)
    assert len(pools_b) == 0 and list(pools_b.columns) == POOL_COLUMNS
    assert len(events_b) == 0 and list(events_b.columns) == EVENT_COLUMNS


@pytest.mark.unit
def test_input_frames_not_mutated():
    """bars and swings frames are bit-identical before/after detect_pools."""
    bars = _equal_high_pair(_atr_bars(40), 20, 24, BASE + TR + 0.5 * TOL)
    swings = detect_swings(bars.copy(), TIMEFRAME)
    bars_before = bars.copy(deep=True)
    swings_before = swings.copy(deep=True)
    detect_pools(bars.copy(), swings.copy())
    pd.testing.assert_frame_equal(bars_before, bars)
    pd.testing.assert_frame_equal(swings_before, swings)


# ---------------------------------------------------------------------------
# Tier-3 repaint (SC1 pool tier) + standalone-vs-in-frame (Pitfall 3)
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_resolved_pools_immutable_under_appended_bars():
    """For every prefix, resolved pools equal the visible subset of full-frame
    resolved pools (terminal states final); chunked appends preserve this.

    Visibility: a pool resolved on bar b is visible in a prefix iff bar b is
    IN the prefix — i.e. resolved_at (the resolving bar's open time) <= the
    prefix's last bar open time."""
    bars = _equal_high_pair(_atr_bars(60), 20, 24, BASE + TR + 0.5 * TOL)
    # Resolve the pool mid-frame: pierce + close-back below the level.
    lvl = BASE + TR + 0.5 * TOL
    bars.iloc[30, bars.columns.get_indexer(["high"])] = lvl + 0.25 * TOL
    bars.iloc[30, bars.columns.get_indexer(["close"])] = lvl - 0.25 * TOL
    bars.iloc[30, bars.columns.get_indexer(["open"])] = lvl + 0.25 * TOL
    bars.iloc[30, bars.columns.get_indexer(["low"])] = lvl - 0.25 * TOL
    full_pools, _ = _pools_for(bars)
    full_resolved = full_pools[full_pools["state"].isin(["swept", "broken"])]
    assert len(full_resolved) == 1  # fixture must resolve exactly once

    def _visible(k: int) -> pd.DataFrame:
        horizon = bars.iloc[:k]["time_utc"].iloc[-1]
        return full_resolved[full_resolved["resolved_at"] <= horizon].reset_index(drop=True)

    for k in range(16, len(bars)):
        prefix_pools, _ = _pools_for(bars.iloc[:k].copy())
        prefix_resolved = prefix_pools[
            prefix_pools["state"].isin(["swept", "broken"])
        ].reset_index(drop=True)
        pd.testing.assert_frame_equal(prefix_resolved, _visible(k), check_exact=True)

    # chunked appends
    for k in range(16, len(bars) - 5, 5):
        prefix_pools, _ = _pools_for(bars.iloc[:k].copy())
        prefix_resolved = prefix_pools[
            prefix_pools["state"].isin(["swept", "broken"])
        ].reset_index(drop=True)
        pd.testing.assert_frame_equal(prefix_resolved, _visible(k), check_exact=True)


@pytest.mark.unit
def test_pools_standalone_match_in_frame():
    """Pools computed from a truncated frame equal the corresponding pools
    computed on the full frame whose far-future tail carries extreme,
    ATR-changing volatility — no full-frame statistics may leak into
    tolerance decisions (Pitfall 3 warning-sign test)."""
    bars = _equal_high_pair(_atr_bars(60), 20, 24, BASE + TR + 0.5 * TOL)
    lvl = BASE + TR + 0.5 * TOL
    bars.iloc[30, bars.columns.get_indexer(["high"])] = lvl + 0.25 * TOL
    bars.iloc[30, bars.columns.get_indexer(["close"])] = lvl - 0.25 * TOL
    bars.iloc[30, bars.columns.get_indexer(["open"])] = lvl + 0.25 * TOL
    bars.iloc[30, bars.columns.get_indexer(["low"])] = lvl - 0.25 * TOL
    # Extreme ATR-changing tail: bars 50-59 carry 50x the base True Range.
    for idx in range(50, 60):
        bars.iloc[idx, bars.columns.get_indexer(["open", "close"])] = BASE + 0.25
        bars.iloc[idx, bars.columns.get_indexer(["high"])] = BASE + 0.50
        bars.iloc[idx, bars.columns.get_indexer(["low"])] = BASE - 0.50
    truncated = bars.iloc[:40].copy()

    standalone_pools, _ = _pools_for(truncated)
    full_pools, _ = _pools_for(bars)

    # Sanity: the tail really is ATR-changing.
    atr_full = wilders_atr(bars, 14)
    assert atr_full.iloc[-1] > 5 * atr_full.iloc[35]

    standalone_resolved = standalone_pools[
        standalone_pools["state"].isin(["swept", "broken"])
    ].reset_index(drop=True)
    horizon = bars.iloc[:40]["time_utc"].iloc[-1]
    full_visible = full_pools[
        full_pools["state"].isin(["swept", "broken"])
        & (full_pools["resolved_at"] <= horizon)
    ].reset_index(drop=True)
    pd.testing.assert_frame_equal(standalone_resolved, full_visible, check_exact=True)
