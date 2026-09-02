"""Unit tests for the entry-candidate pure functions (D-01..D-04, D-08..D-13).

Worlds are hand-built frames with the pinned detector schemas so every SL/TP
expectation is derivable by hand; the real-chain integration of these rules
is proven by test_replay_repaint.py. Conventions: @pytest.mark.unit, direct
imports of _backtest_fixtures helpers.
"""

from __future__ import annotations

from datetime import datetime

import pandas as pd
import pytest
from _backtest_fixtures import bt_cfg, make_bars

from ai_trading.backtest.candidates import (
    CandidateState,
    bias_agrees,
    candidate_at_bar,
    compute_rr,
)
from ai_trading.detectors.mtf import PAYLOAD_COLUMNS
from ai_trading.detectors.pools import EVENT_COLUMNS, POOL_COLUMNS
from ai_trading.detectors.swings import SWING_COLUMNS
from ai_trading.detectors.zones import ZONE_COLUMNS

SYMBOL = "EURUSD"
START = datetime(2026, 8, 20, 0, 0)
CFG = bt_cfg()


def _bars(count: int = 40) -> pd.DataFrame:
    """Flat M15 base at 1.10 (open=low=1.10, close=high=1.105)."""
    df = make_bars(SYMBOL, "M15", START, count)
    df["open"] = 1.10000
    df["low"] = 1.10000
    df["close"] = 1.10500
    df["high"] = 1.10500
    return df


def _t(bar_idx: int) -> pd.Timestamp:
    return pd.Timestamp(START) - pd.Timedelta(hours=3) + pd.Timedelta(minutes=15 * bar_idx)


def _events(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=EVENT_COLUMNS).astype(
        {"pierced_at": "datetime64[us]", "resolved_at": "datetime64[us]"}
    )


def _zones(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=ZONE_COLUMNS).astype(
        {"created_at": "datetime64[us]", "mitigated_at": "datetime64[us]",
         "invalidated_at": "datetime64[us]"}
    )


def _pools(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=POOL_COLUMNS).astype(
        {"first_touch_at": "datetime64[us]", "activated_at": "datetime64[us]",
         "resolved_at": "datetime64[us]"}
    )


def _swings(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=SWING_COLUMNS).astype(
        {"bar_time": "datetime64[us]", "confirmed_at": "datetime64[us]"}
    )


def _payload(bias_h1="bullish", bias_h4=pd.NA, bar_idx: int | None = None) -> pd.Series:
    bar_idx = 30 if bar_idx is None else bar_idx
    row = {col: pd.NA for col in PAYLOAD_COLUMNS}
    row.update(
        {
            "symbol": SYMBOL,
            "time_utc": _t(bar_idx),
            "bias_h1": bias_h1,
            "bias_h4": bias_h4,
            "htf_range_high_h1": float("nan"),
            "htf_range_low_h1": float("nan"),
            "htf_equilibrium_h1": float("nan"),
            "htf_dist_to_eq_atr_h1": float("nan"),
            "htf_zone_ids_h1": [],
            "htf_range_high_h4": float("nan"),
            "htf_range_low_h4": float("nan"),
            "htf_equilibrium_h4": float("nan"),
            "htf_dist_to_eq_atr_h4": float("nan"),
            "htf_zone_ids_h4": [],
        }
    )
    return pd.Series(row)


def _sweep_event(
    event_id: str = "E1",
    pool_id: str = "P1",
    side: str = "low",
    level: float = 1.07000,
    resolved_idx: int = 29,
) -> dict:
    return {
        "event_id": event_id,
        "pool_id": pool_id,
        "symbol": SYMBOL,
        "timeframe": "M15",
        "side": side,
        "level": level,
        "pierced_at": _t(resolved_idx),
        "resolved_at": _t(resolved_idx),
        "event_type": "sweep",
    }


def _mitigated_zone(
    zone_id: str = "Z1",
    range_high: float = 1.12000,
    range_low: float = 1.08000,
    mitigated_idx: int = 30,
    state: str = "mitigated",
) -> dict:
    eq = (range_high + range_low) / 2.0
    return {
        "zone_id": zone_id,
        "symbol": SYMBOL,
        "timeframe": "M15",
        "leg_direction": "up",
        "range_high": range_high,
        "range_low": range_low,
        "equilibrium": eq,
        "state": state,
        "created_at": _t(20),
        "mitigated_at": _t(mitigated_idx),
        "invalidated_at": pd.NaT,
    }


def _pool(
    pool_id: str,
    side: str,
    level: float,
    activated_idx: int = 15,
    resolved_idx: int | None = None,
) -> dict:
    return {
        "pool_id": pool_id,
        "symbol": SYMBOL,
        "timeframe": "M15",
        "side": side,
        "level": level,
        "touch_count": 2,
        "state": "active" if resolved_idx is None else "swept",
        "first_touch_at": _t(activated_idx - 2),
        "activated_at": _t(activated_idx),
        "resolved_at": pd.NaT if resolved_idx is None else _t(resolved_idx),
    }


def _swing(side: str, price: float, confirmed_idx: int = 25) -> dict:
    return {
        "symbol": SYMBOL,
        "timeframe": "M15",
        "bar_time": _t(confirmed_idx - 2),
        "price": price,
        "side": side,
        "confirmed_at": _t(confirmed_idx),
    }


_UNSET = object()


def _state(
    bars: pd.DataFrame | None = None,
    bar_idx: int = 30,
    events: pd.DataFrame | None = None,
    zones: pd.DataFrame | None = None,
    pools: pd.DataFrame | None = None,
    swings: pd.DataFrame | None = None,
    payload_row: object = _UNSET,
) -> CandidateState:
    """Decision-bar context = bars prefix through bar_idx (close sculpted to
    1.095 = discount vs the default zone equilibrium 1.10). Pass
    ``payload_row=None`` explicitly to test the missing-payload veto."""
    if bars is None:
        bars = _bars()
    if events is None:
        events = _events([_sweep_event()])
    if zones is None:
        zones = _zones([_mitigated_zone(mitigated_idx=bar_idx)])
    if pools is None:
        pools = _pools([_pool("P1", "low", 1.07)])
    if swings is None:
        swings = _swings([])
    row = _payload(bar_idx=bar_idx) if payload_row is _UNSET else payload_row
    return CandidateState(
        m15_bars=bars.iloc[: bar_idx + 1],
        events15=events,
        zones15=zones,
        pools15=pools,
        swings15=swings,
        payload_row=row,
    )


def _discount_close(bars: pd.DataFrame, bar_idx: int, close: float = 1.09500) -> pd.DataFrame:
    out = bars.copy()
    out.iloc[bar_idx, out.columns.get_indexer(["close"])] = close
    out.iloc[bar_idx, out.columns.get_indexer(["low"])] = min(out.iloc[bar_idx]["low"], close)
    return out


# ---------------------------------------------------------------------------
# Core D-01 composition: sweep + mitigated tap -> candidate
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_sweep_then_discount_mitigation_long_exact_sl_tp():
    """Sweep (pool side low) then mitigation bar in discount -> long with
    SL = min(pool.level, zone.range_low) and the NEAREST structural TP."""
    bars = _discount_close(_bars(), 30)
    pools = _pools(
        [
            _pool("P1", "low", 1.07),
            _pool("P2", "high", 1.15),  # live opposite pool beyond the zone
        ]
    )
    swings = _swings([_swing("high", 1.14)])  # nearer than the pool
    cand = candidate_at_bar(_state(bars=bars, pools=pools, swings=swings), CFG)
    assert cand is not None
    assert cand.direction == "long"
    assert cand.sl_price == 1.07  # min(pool 1.07, zone low 1.08)
    assert cand.tp_price == 1.14  # nearest beyond range_high 1.12: swing 1.14 < pool 1.15
    assert cand.entry_bar_idx == 31  # S+1
    assert cand.symbol == SYMBOL and cand.timeframe == "M15"
    assert cand.pool_id == "P1" and cand.event_id == "E1" and cand.zone_id == "Z1"
    assert cand.bias_h1 == "bullish" and cand.bias_h4 is pd.NA


@pytest.mark.unit
def test_opposite_pool_tp_override_when_nearer():
    """Pool 1.15 nearer than swing 1.155 -> TP = the pool target."""
    bars = _discount_close(_bars(), 30)
    pools = _pools([_pool("P1", "low", 1.07), _pool("P2", "high", 1.15)])
    swings = _swings([_swing("high", 1.155)])
    cand = candidate_at_bar(_state(bars=bars, pools=pools, swings=swings), CFG)
    assert cand is not None and cand.tp_price == 1.15


@pytest.mark.unit
def test_prior_swing_tp_when_no_opposite_pool():
    """No opposite pool beyond the zone but a prior confirmed swing beyond
    it (confirmed_at <= close_t) -> TP = that swing level (D-09)."""
    bars = _discount_close(_bars(), 30)
    cand = candidate_at_bar(
        _state(bars=bars, swings=_swings([_swing("high", 1.14)])), CFG
    )
    assert cand is not None and cand.tp_price == 1.14


@pytest.mark.unit
def test_tp_fallback_to_zone_far_boundary():
    """Neither alternative beyond the zone -> TP = the zone's far boundary."""
    bars = _discount_close(_bars(), 30)
    cand = candidate_at_bar(_state(bars=bars), CFG)
    assert cand is not None and cand.tp_price == 1.12  # zone.range_high


@pytest.mark.unit
def test_tp_tie_resolves_to_pool():
    """Pool and swing at the SAME level beyond the zone -> pool target."""
    bars = _discount_close(_bars(), 30)
    pools = _pools([_pool("P1", "low", 1.07), _pool("P2", "high", 1.15)])
    swings = _swings([_swing("high", 1.15)])
    cand = candidate_at_bar(_state(bars=bars, pools=pools, swings=swings), CFG)
    assert cand is not None and cand.tp_price == 1.15
    # Tie via the pools-only/None-swing path is covered by the pool-override test.


@pytest.mark.unit
def test_swing_visible_only_when_confirmed_by_decision_close():
    """A swing confirmed AFTER the decision close is not yet a TP candidate
    (close-time anchor); one confirmed exactly AT the decision close is."""
    bars = _discount_close(_bars(), 30)
    late = _swings([_swing("high", 1.14, confirmed_idx=32)])  # after close_t = _t(31)
    cand_late = candidate_at_bar(_state(bars=bars, swings=late), CFG)
    assert cand_late is not None and cand_late.tp_price == 1.12  # fallback
    at_close = _swings([_swing("high", 1.14, confirmed_idx=31)])  # == close_t
    cand_at = candidate_at_bar(_state(bars=bars, swings=at_close), CFG)
    assert cand_at is not None and cand_at.tp_price == 1.14


@pytest.mark.unit
def test_resolved_opposite_pool_not_selected_as_tp():
    """An opposite pool resolved at/before the decision bar is NOT a TP
    candidate (no remaining liquidity); unresolved (NaT) or later-resolved
    pools ARE selectable."""
    bars = _discount_close(_bars(), 30)
    resolved_now = _pools([_pool("P1", "low", 1.07), _pool("P2", "high", 1.15, resolved_idx=30)])
    cand = candidate_at_bar(_state(bars=bars, pools=resolved_now), CFG)
    assert cand is not None and cand.tp_price == 1.12  # falls through to the boundary

    resolved_later = _pools([_pool("P1", "low", 1.07), _pool("P2", "high", 1.15, resolved_idx=31)])
    cand_later = candidate_at_bar(_state(bars=bars, pools=resolved_later), CFG)
    assert cand_later is not None and cand_later.tp_price == 1.15  # still live at the decision


@pytest.mark.unit
def test_mirrored_short_case():
    """Sweep of a high-side pool + mitigation bar in premium -> short with
    SL = max(pool.level, zone.range_high), TP = nearest below the zone."""
    bars = _bars()
    idx = 30
    bars = bars.copy()
    bars.iloc[idx, bars.columns.get_indexer(["close"])] = 1.10500  # premium vs eq 1.10
    bars.iloc[idx, bars.columns.get_indexer(["high"])] = 1.10500
    events = _events([_sweep_event(side="high", level=1.13)])
    zones = _zones([_mitigated_zone(range_high=1.12, range_low=1.08, mitigated_idx=idx)])
    pools = _pools([_pool("P1", "high", 1.13), _pool("P2", "low", 1.05)])
    swings = _swings([_swing("low", 1.06)])
    payload = _payload(bias_h1="bearish")  # short needs a bearish HTF lean (D-02)
    cand = candidate_at_bar(
        _state(
            bars=bars, events=events, zones=zones, pools=pools, swings=swings,
            payload_row=payload,
        ),
        CFG,
    )
    assert cand is not None
    assert cand.direction == "short"
    assert cand.sl_price == 1.13  # max(pool 1.13, zone high 1.12)
    assert cand.tp_price == 1.06  # nearest below range_low 1.08: swing 1.06 > pool 1.05
    assert cand.entry_bar_idx == 31


# ---------------------------------------------------------------------------
# D-01 gates: sweep-only / zone-only / side / equilibrium
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_sweep_only_no_mitigated_tap_is_none():
    bars = _discount_close(_bars(), 30)
    zones = _zones([_mitigated_zone(mitigated_idx=10)])  # mitigated on an earlier bar
    assert candidate_at_bar(_state(bars=bars, zones=zones), CFG) is None


@pytest.mark.unit
def test_zone_only_no_sweep_is_none():
    bars = _discount_close(_bars(), 30)
    assert candidate_at_bar(_state(bars=bars, events=_events([])), CFG) is None


@pytest.mark.unit
def test_breakout_event_is_not_a_sweep():
    bars = _discount_close(_bars(), 30)
    events = _events([{**_sweep_event(), "event_type": "breakout"}])
    assert candidate_at_bar(_state(bars=bars, events=events), CFG) is None


@pytest.mark.unit
def test_side_mismatch_is_none():
    """Sweep of a high pool + discount close -> no trade (D-01 right side)."""
    bars = _discount_close(_bars(), 30)
    events = _events([_sweep_event(side="high", level=1.13)])
    assert candidate_at_bar(_state(bars=bars, events=events), CFG) is None


@pytest.mark.unit
def test_close_at_equilibrium_is_none():
    bars = _discount_close(_bars(), 30, close=1.10)  # == equilibrium
    assert candidate_at_bar(_state(bars=bars), CFG) is None


# ---------------------------------------------------------------------------
# D-02 bias gates
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_bias_veto_when_both_disagree():
    bars = _discount_close(_bars(), 30)
    payload = _payload(bias_h1="bearish", bias_h4="bearish")
    assert candidate_at_bar(_state(bars=bars, payload_row=payload), CFG) is None


@pytest.mark.unit
def test_bias_agrees_via_h4_only_and_records_both():
    bars = _discount_close(_bars(), 30)
    payload = _payload(bias_h1="bearish", bias_h4="bullish")
    cand = candidate_at_bar(_state(bars=bars, payload_row=payload), CFG)
    assert cand is not None and cand.direction == "long"
    assert cand.bias_h1 == "bearish" and cand.bias_h4 == "bullish"


@pytest.mark.unit
def test_missing_payload_row_vetoes_candidate():
    bars = _discount_close(_bars(), 30)
    assert candidate_at_bar(_state(bars=bars, payload_row=None), CFG) is None


@pytest.mark.unit
def test_bias_agrees_truth_table():
    assert bias_agrees("bullish", pd.NA, "long") is True
    assert bias_agrees(pd.NA, "bullish", "long") is True
    assert bias_agrees("neutral", "neutral", "long") is False
    assert bias_agrees("bearish", "bearish", "long") is False
    assert bias_agrees("bearish", "bearish", "short") is True
    assert bias_agrees(pd.NA, pd.NA, "short") is False


# ---------------------------------------------------------------------------
# R:R math + edge cases
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_compute_rr_literals():
    assert compute_rr("long", 1.10, 1.09, 1.12) == pytest.approx(2.0)
    assert compute_rr("short", 1.10, 1.11, 1.08) == pytest.approx(2.0)
    # 24-pip risk / 48-pip reward
    assert compute_rr("long", 1.1000, 1.0976, 1.1048) == pytest.approx(2.0)
    assert compute_rr("long", 1.10, 1.08, 1.11) == pytest.approx(0.5)


@pytest.mark.unit
def test_empty_decision_context_is_none():
    assert candidate_at_bar(_state(bars=_bars().iloc[:0]), CFG) is None
