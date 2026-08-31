"""Unit tests (SMC-03 + D-07/D-08): sweep-vs-breakout classification per the
pinned 2-bar inclusive reclaim window. No adapter-tier (MetaTrader5) imports
anywhere.

Pinned window reading (assumption A8): the window counts the PIERCE BAR
itself as the first of the two closes — a close back on the original side on
the pierce bar or on the next bar resolves the pool as swept; the alternative
reading (two closes AFTER the pierce bar) is deliberately rejected.

Fixture design mirrors test_pools.py: constant-TR base (every True Range is
exactly TR = 0.01), TR-preserving swing sculpts, so the as-of ATR is exactly
TR and the pool level is exactly the mean of the two equal touch prices.
"""

from __future__ import annotations

from datetime import datetime

import pandas as pd
import pytest

from ai_trading.detectors.pools import EVENT_COLUMNS, POOL_COLUMNS, detect_pools
from ai_trading.detectors.swings import detect_swings

SYMBOL = "EURUSD"
TIMEFRAME = "M15"
START = datetime(2026, 8, 20, 0, 0)
TR = 0.01000
BASE = 1.10000
P = BASE + 1.5 * TR  # 1.115 — pool touch price (both swings)


def _atr_bars(count: int) -> pd.DataFrame:
    """Constant-TR base: open=low=BASE, close=high=BASE+TR (TR exact)."""
    from conftest import make_bars

    df = make_bars(SYMBOL, TIMEFRAME, START, count, offset_hours=3)
    df["open"] = BASE
    df["low"] = BASE
    df["close"] = BASE + TR
    df["high"] = BASE + TR
    return df


def _sculpt_swing_high(df: pd.DataFrame, idx: int, price: float) -> pd.DataFrame:
    """TR-preserving swing-high sculpt: high=price, low=open=close=price-TR."""
    out = df.copy()
    out.iloc[idx, out.columns.get_indexer(["open", "low", "close"])] = price - TR
    out.iloc[idx, out.columns.get_indexer(["high"])] = price
    return out


def _sweep_fixture(close30: float, close31: float, low30: float | None = None):
    """Standard fixture: pool from equal swing highs at 20/24 (level = P),
    pierce pair at bars 30/31 (equal highs at P + 0.0005 — not swings), with
    scripted closes. Returns (bars, pools, events)."""
    bars = _atr_bars(40)
    bars = _sculpt_swing_high(bars, 20, P)
    bars = _sculpt_swing_high(bars, 24, P)
    pierce_high = P + 0.0005
    for idx, close in ((30, close30), (31, close31)):
        low = low30 if (idx == 30 and low30 is not None) else close - 0.0001
        bars.iloc[idx, bars.columns.get_indexer(["open"])] = P + 0.0004
        bars.iloc[idx, bars.columns.get_indexer(["high"])] = pierce_high
        bars.iloc[idx, bars.columns.get_indexer(["low"])] = low
        bars.iloc[idx, bars.columns.get_indexer(["close"])] = close
    swings = detect_swings(bars.copy(), TIMEFRAME)
    pools, events = detect_pools(bars.copy(), swings)
    return bars, pools, events


# ---------------------------------------------------------------------------
# Classification (D-07, A8)
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_immediate_reclaim_swept_on_pierce_bar():
    """Pierce + close back below the level ON the pierce bar -> sweep resolved
    on the pierce bar (pierced_at == resolved_at)."""
    bars, pools, events = _sweep_fixture(close30=P - 0.0005, close31=P + 0.0002)
    assert len(events) == 1
    ev = events.iloc[0]
    assert ev["event_type"] == "sweep"
    assert ev["pierced_at"] == bars.iloc[30]["time_utc"]
    assert ev["resolved_at"] == bars.iloc[30]["time_utc"]
    assert pools[pools["pool_id"] == ev["pool_id"]].iloc[0]["state"] == "swept"


@pytest.mark.unit
def test_next_bar_reclaim_swept():
    """Pierce with close above the level, close-back on the NEXT bar -> sweep
    resolved on the next bar (the window's second close, A8)."""
    bars, pools, events = _sweep_fixture(close30=P + 0.0002, close31=P - 0.0005)
    assert len(events) == 1
    ev = events.iloc[0]
    assert ev["event_type"] == "sweep"
    assert ev["pierced_at"] == bars.iloc[30]["time_utc"]
    assert ev["resolved_at"] == bars.iloc[31]["time_utc"]
    assert pools[pools["pool_id"] == ev["pool_id"]].iloc[0]["state"] == "swept"


@pytest.mark.unit
def test_no_reclaim_breakout():
    """No close-back within the window -> plain breakout; pool state broken;
    resolved_at = the second window bar's time_utc."""
    bars, pools, events = _sweep_fixture(close30=P + 0.0002, close31=P + 0.0002)
    assert len(events) == 1
    ev = events.iloc[0]
    assert ev["event_type"] == "breakout"
    assert ev["resolved_at"] == bars.iloc[31]["time_utc"]
    assert pools[pools["pool_id"] == ev["pool_id"]].iloc[0]["state"] == "broken"


@pytest.mark.unit
def test_identical_pierce_paths_differ_only_by_close_back_timing():
    """Identical pierce paths (same wick highs) classify sweep / sweep /
    breakout SOLELY by close-back timing within the pinned window."""
    _, _, ev_immediate = _sweep_fixture(close30=P - 0.0005, close31=P + 0.0002)
    _, _, ev_next = _sweep_fixture(close30=P + 0.0002, close31=P - 0.0005)
    _, _, ev_none = _sweep_fixture(close30=P + 0.0002, close31=P + 0.0002)
    assert list(ev_immediate["event_type"]) == ["sweep"]
    assert list(ev_next["event_type"]) == ["sweep"]
    assert list(ev_none["event_type"]) == ["breakout"]
    # Same pierce bar and level across all three paths.
    assert ev_immediate.iloc[0]["pierced_at"] == ev_next.iloc[0]["pierced_at"]
    assert ev_immediate.iloc[0]["level"] == ev_none.iloc[0]["level"]


@pytest.mark.unit
def test_wick_reclaim_alone_does_not_count():
    """A wick back through the level without the CLOSE returning does not
    reclaim: closes stay above the level -> breakout (closes, not wicks,
    drive reclaim)."""
    bars, pools, events = _sweep_fixture(
        close30=P + 0.0002, close31=P + 0.0002, low30=P - 0.0005
    )
    # bar 30's low pierced back below the level (wick reclaim) but its close
    # stayed above -> still a breakout.
    assert bars.iloc[30]["low"] < P < bars.iloc[30]["close"]
    assert len(events) == 1
    assert events.iloc[0]["event_type"] == "breakout"


# ---------------------------------------------------------------------------
# One-and-done (D-08)
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_spent_level_never_re_swept_new_cluster_new_pool():
    """A swept pool is never re-swept; a later equal-level cluster gets a
    fresh pool_id which can itself be swept."""
    bars, pools, events = _sweep_fixture(close30=P - 0.0005, close31=P + 0.0002)
    assert len(events) == 1 and events.iloc[0]["event_type"] == "sweep"
    # Rebuild the same scenario on a longer frame: first pool resolved by the
    # 30/31 pierce pair, then a new equal-level cluster (36/40) that itself
    # gets swept by the 44/45 pair.
    bars = _atr_bars(60)
    for idx in (20, 24, 36, 40):
        bars = _sculpt_swing_high(bars, idx, P)
    for idx, close in ((30, P - 0.0005), (31, P + 0.0002)):
        bars.iloc[idx, bars.columns.get_indexer(["open"])] = P + 0.0004
        bars.iloc[idx, bars.columns.get_indexer(["high"])] = P + 0.0005
        bars.iloc[idx, bars.columns.get_indexer(["low"])] = close - 0.0001
        bars.iloc[idx, bars.columns.get_indexer(["close"])] = close
    for idx, close in ((44, P - 0.0005), (45, P + 0.0002)):
        bars.iloc[idx, bars.columns.get_indexer(["open"])] = P + 0.0004
        bars.iloc[idx, bars.columns.get_indexer(["high"])] = P + 0.0005
        bars.iloc[idx, bars.columns.get_indexer(["low"])] = close - 0.0001
        bars.iloc[idx, bars.columns.get_indexer(["close"])] = close
    swings = detect_swings(bars.copy(), TIMEFRAME)
    pools2, events2 = detect_pools(bars.copy(), swings)
    resolved = pools2[pools2["state"].isin(["swept", "broken"])]
    assert len(resolved) == 2
    assert list(resolved["pool_id"]) == [
        f"{SYMBOL}-{TIMEFRAME}-P0001",
        f"{SYMBOL}-{TIMEFRAME}-P0002",
    ]
    assert list(events2["event_type"]) == ["sweep", "sweep"]
    assert events2.iloc[1]["pool_id"] == f"{SYMBOL}-{TIMEFRAME}-P0002"


# ---------------------------------------------------------------------------
# Payload + contracts
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_event_payload_completeness_and_single_event_per_pool():
    """Every event carries the full pinned payload; exactly one event per
    resolved pool; event_id = {pool_id}-E1."""
    bars, pools, events = _sweep_fixture(close30=P - 0.0005, close31=P + 0.0002)
    assert list(events.columns) == EVENT_COLUMNS
    assert len(events) == 1
    resolved = pools[pools["state"].isin(["swept", "broken"])]
    assert len(resolved) == 1
    ev = events.iloc[0]
    assert ev["event_id"] == f"{resolved.iloc[0]['pool_id']}-E1"
    assert ev["pool_id"] == resolved.iloc[0]["pool_id"]
    assert ev["symbol"] == SYMBOL and ev["timeframe"] == TIMEFRAME
    assert ev["side"] == "high"
    assert ev["level"] == pytest.approx(P)
    assert pd.notna(ev["pierced_at"]) and pd.notna(ev["resolved_at"])
    assert ev["event_type"] == "sweep"


@pytest.mark.unit
def test_empty_frame_contract():
    """Empty bars/swings -> schema-correct empty pools and events frames."""
    bars = _atr_bars(0)
    swings = detect_swings(bars.copy(), TIMEFRAME)
    pools, events = detect_pools(bars.copy(), swings)
    assert len(pools) == 0 and list(pools.columns) == POOL_COLUMNS
    assert len(events) == 0 and list(events.columns) == EVENT_COLUMNS
