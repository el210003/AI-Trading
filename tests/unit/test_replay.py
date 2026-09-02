"""Unit tests for the forward-pass replay state machine (D-04/D-05/D-07/
D-12/D-21 + the resolver seam). Worlds are hand-built chain frames with the
pinned detector schemas so label expectations are hand-derivable; the
full-path look-ahead proof lives in test_replay_repaint.py.
"""

from __future__ import annotations

from datetime import datetime

import pandas as pd
import pytest
from _backtest_fixtures import bt_cfg, make_bars, set_spreads

from ai_trading.backtest.replay import (
    LABEL_COLUMNS,
    assert_offset_uniform,
    auto_warmup_bars,
    check_history_gate,
    replay_symbol,
)
from ai_trading.detectors.mtf import PAYLOAD_COLUMNS
from ai_trading.detectors.pools import EVENT_COLUMNS, POOL_COLUMNS
from ai_trading.detectors.swings import SWING_COLUMNS

SYMBOL = "EURUSD"
START = datetime(2026, 8, 20, 0, 0)
CFG = bt_cfg()
BASE = 1.10000


def _t(bar_idx: int) -> pd.Timestamp:
    return pd.Timestamp(START) - pd.Timedelta(hours=3) + pd.Timedelta(minutes=15 * bar_idx)


def _bars(count: int = 60) -> pd.DataFrame:
    df = make_bars(SYMBOL, "M15", START, count)
    df["open"] = BASE
    df["low"] = BASE
    df["close"] = BASE + 0.005
    df["high"] = BASE + 0.005
    return df


def _sweep_events(resolved_idx: int = 25, level: float = 1.08) -> pd.DataFrame:
    rows = [
        {
            "event_id": "E1",
            "pool_id": "P1",
            "symbol": SYMBOL,
            "timeframe": "M15",
            "side": "low",
            "level": level,
            "pierced_at": _t(resolved_idx),
            "resolved_at": _t(resolved_idx),
            "event_type": "sweep",
        }
    ]
    return pd.DataFrame(rows, columns=EVENT_COLUMNS).astype(
        {"pierced_at": "datetime64[us]", "resolved_at": "datetime64[us]"}
    )


def _tap_zones(tap_indices, range_high: float = 1.14, range_low: float = 1.09) -> pd.DataFrame:
    eq = (range_high + range_low) / 2.0
    rows = []
    for n, idx in enumerate(tap_indices, start=1):
        rows.append(
            {
                "zone_id": f"Z{n:04d}",
                "symbol": SYMBOL,
                "timeframe": "M15",
                "leg_direction": "up",
                "range_high": range_high,
                "range_low": range_low,
                "equilibrium": eq,
                "state": "mitigated",
                "created_at": _t(idx - 8),
                "mitigated_at": _t(idx),
                "invalidated_at": pd.NaT,
            }
        )
    return pd.DataFrame(rows, columns=[
        "zone_id", "symbol", "timeframe", "leg_direction", "range_high", "range_low",
        "equilibrium", "state", "created_at", "mitigated_at", "invalidated_at",
    ]).astype(
        {"created_at": "datetime64[us]", "mitigated_at": "datetime64[us]",
         "invalidated_at": "datetime64[us]"}
    )


def _world_pools(level: float = 1.08) -> pd.DataFrame:
    rows = [
        {
            "pool_id": "P1",
            "symbol": SYMBOL,
            "timeframe": "M15",
            "side": "low",
            "level": level,
            "touch_count": 2,
            "state": "swept",
            "first_touch_at": _t(8),
            "activated_at": _t(10),
            "resolved_at": _t(25),
        }
    ]
    return pd.DataFrame(rows, columns=POOL_COLUMNS).astype(
        {"first_touch_at": "datetime64[us]", "activated_at": "datetime64[us]",
         "resolved_at": "datetime64[us]"}
    )


def _payload_frame(bars: pd.DataFrame, bias: str = "bullish") -> pd.DataFrame:
    rows = []
    for t in bars["time_utc"]:
        row = {col: pd.NA for col in PAYLOAD_COLUMNS}
        row.update(
            {
                "symbol": SYMBOL,
                "time_utc": t,
                "bias_h1": bias,
                "bias_h4": pd.NA,
                "htf_zone_ids_h1": [],
                "htf_zone_ids_h4": [],
            }
        )
        rows.append(row)
    return pd.DataFrame(rows, columns=PAYLOAD_COLUMNS)


def _chain(
    bars: pd.DataFrame,
    tap_indices=(28,),
    pool_level: float = 1.08,
    zone_range: tuple[float, float] = (1.14, 1.09),
    bias: str = "bullish",
) -> dict[str, pd.DataFrame]:
    return {
        "swings15": pd.DataFrame(columns=SWING_COLUMNS),
        "pools15": _world_pools(pool_level),
        "events15": _sweep_events(level=pool_level),
        "zones15": _tap_zones(tap_indices, range_high=zone_range[0], range_low=zone_range[1]),
        "payload": _payload_frame(bars, bias=bias),
    }


def entry_resolver(position, bars, cfg):
    """Constant fake resolver: outcome resolved AT the entry bar — no
    barrier window, values derive only from the position (prefix-stable)."""
    return {
        "outcome": "TIMEOUT",
        "exit_time": position.entry_time,
        "exit_price": position.entry_open,
        "exit_idx": position.entry_idx,
        "r_gross": 0.0,
        "r_raw": 0.0,
        "r_net": 0.0,
    }


def holding_resolver(hold: int = 10):
    """Resolver that keeps the D-05 slot held for ``hold`` bars after entry."""

    def _resolve(position, bars, cfg):
        exit_idx = min(position.entry_idx + hold, len(bars) - 1)
        return {
            "outcome": "WIN",
            "exit_time": bars["time_utc"].iloc[exit_idx],
            "exit_price": float(bars["close"].iloc[exit_idx]),
            "exit_idx": exit_idx,
            "r_gross": 1.0,
            "r_raw": 0.9,
            "r_net": 0.8,
        }

    return _resolve


# ---------------------------------------------------------------------------
# D-07 warmup
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_auto_warmup_constant():
    assert auto_warmup_bars(bt_cfg(warmup_bars=0)) == 28
    assert auto_warmup_bars(bt_cfg(warmup_bars=50)) == 50


@pytest.mark.unit
def test_warmup_skips_silently_no_errors():
    """Bars whose only candidate sits inside the warmup window produce zero
    labels and raise nothing (D-07)."""
    bars, chain = _world_bars_and_chain(tap_indices=(10,), count=30)
    labels = replay_symbol(bars, chain, CFG, entry_resolver)
    assert len(labels) == 0
    assert list(labels.columns) == list(LABEL_COLUMNS)


@pytest.mark.unit
def test_first_candidate_emitted_after_warmup():
    """A sweep+mitigation at the first post-warmup bar (28) labels with the
    next bar (29) as the entry."""
    bars, chain = _world_bars_and_chain(tap_indices=(28,), count=40)
    labels = replay_symbol(bars, chain, CFG, entry_resolver)
    assert len(labels) == 1
    assert labels.iloc[0]["entry_time"] == _t(29)


def _world_bars_and_chain(tap_indices, count: int = 60):
    bars = _bars(count)
    return bars, _chain(bars, tap_indices=tap_indices)


# ---------------------------------------------------------------------------
# D-05 one-at-a-time + slot-release timing
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_d05_one_at_a_time_suppression_and_release():
    """While the slot is held (resolver exit 10 bars out), a second valid
    tap produces no second label; after release the next tap labels."""
    bars, chain = _world_bars_and_chain(tap_indices=(28, 31, 45))
    labels = replay_symbol(bars, chain, CFG, holding_resolver(hold=10))
    assert len(labels) == 2
    assert labels.iloc[0]["entry_time"] == _t(29)  # tap at 28 -> entry 29
    assert labels.iloc[1]["entry_time"] == _t(46)  # tap at 45 (31 suppressed) -> entry 46


# ---------------------------------------------------------------------------
# D-04/D-14/D-15 fill prices
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_fill_uses_recorded_spread_and_slippage():
    bars, chain = _world_bars_and_chain(tap_indices=(28,))
    labels = replay_symbol(bars, chain, CFG, entry_resolver)
    # fill bar 29: recorded spread = 29 points (make_bars range), slip 0.5 pip
    assert labels.iloc[0]["entry_price"] == BASE + 29 * 0.00001 + 0.5 * 0.0001


@pytest.mark.unit
def test_fill_falls_back_to_default_spread_when_recorded_zero():
    bars, chain = _world_bars_and_chain(tap_indices=(28,))
    bars = set_spreads(bars, [0] * len(bars))
    labels = replay_symbol(bars, chain, CFG, entry_resolver)
    assert labels.iloc[0]["entry_price"] == BASE + 20 * 0.00001 + 0.5 * 0.0001  # D-15 default


@pytest.mark.unit
def test_fill_per_symbol_default_spread_override():
    bars, chain = _world_bars_and_chain(tap_indices=(28,))
    bars = set_spreads(bars, [0] * len(bars))
    cfg = bt_cfg(default_spread_points_by_symbol={"EURUSD": 30})
    labels = replay_symbol(bars, chain, cfg, entry_resolver)
    assert labels.iloc[0]["entry_price"] == BASE + 30 * 0.00001 + 0.5 * 0.0001


# ---------------------------------------------------------------------------
# D-12 min-R:R discard at fill
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_d12_discards_below_min_rr():
    """rr = (1.109 - 1.10) / (1.10 - 1.08) = 0.9 < 1.0 -> no label."""
    bars = _bars()
    idx = 28
    bars.iloc[idx, bars.columns.get_indexer(["open", "low", "close", "high"])] = [
        1.09600,
        1.09400,
        1.09500,
        1.09700,
    ]  # discount close vs eq 1.0995
    chain = _chain(bars, tap_indices=(28,), pool_level=1.09, zone_range=(1.109, 1.09))
    labels = replay_symbol(bars, chain, CFG, entry_resolver)
    assert len(labels) == 0


@pytest.mark.unit
def test_d12_keeps_at_or_above_min_rr():
    bars, chain = _world_bars_and_chain(tap_indices=(28,))
    labels = replay_symbol(bars, chain, CFG, entry_resolver)
    assert len(labels) == 1
    assert labels.iloc[0]["rr"] == (1.14 - BASE) / (BASE - 1.08)  # 2.0


# ---------------------------------------------------------------------------
# Schema + contracts
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_label_schema_and_pinned_dtypes():
    bars, chain = _world_bars_and_chain(tap_indices=(28,))
    labels = replay_symbol(bars, chain, CFG, entry_resolver)
    assert list(labels.columns) == list(LABEL_COLUMNS)
    str_cols = ("symbol", "timeframe", "direction", "pool_id", "event_id", "zone_id",
                "bias_h1", "bias_h4", "outcome")
    for col in str_cols:
        assert labels[col].dtype == pd.StringDtype(), col
    for col in ("entry_time", "exit_time"):
        assert str(labels[col].dtype) == "datetime64[us]", col
    assert labels["exit_idx"].dtype == "int64"
    for col in ("entry_price", "sl_price", "tp_price", "rr", "exit_price",
                "r_gross", "r_raw", "r_net"):
        assert labels[col].dtype == "float64", col
    row = labels.iloc[0]
    assert row["symbol"] == SYMBOL and row["timeframe"] == "M15"
    assert row["direction"] == "long"
    assert row["sl_price"] == 1.08 and row["tp_price"] == 1.14
    assert row["pool_id"] == "P1" and row["event_id"] == "E1"
    assert row["bias_h1"] == "bullish" and row["bias_h4"] is pd.NA


@pytest.mark.unit
def test_empty_input_yields_schema_correct_empty_frame():
    bars, chain = _world_bars_and_chain(tap_indices=(28,))
    for frame in (bars.iloc[:0], bars.iloc[:1]):
        labels = replay_symbol(frame, chain, CFG, entry_resolver)
        assert len(labels) == 0
        assert list(labels.columns) == list(LABEL_COLUMNS)
        assert labels["exit_idx"].dtype == "int64"
        assert str(labels["entry_time"].dtype) == "datetime64[us]"
        assert labels["symbol"].dtype == pd.StringDtype()


@pytest.mark.unit
def test_input_frames_not_mutated():
    bars, chain = _world_bars_and_chain(tap_indices=(28,))
    bars_before = bars.copy(deep=True)
    chain_before = {k: v.copy(deep=True) for k, v in chain.items()}
    replay_symbol(bars, chain, CFG, entry_resolver)
    pd.testing.assert_frame_equal(bars_before, bars)
    for key in chain:
        pd.testing.assert_frame_equal(chain_before[key], chain[key])


# ---------------------------------------------------------------------------
# D-21 history gate
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_history_gate_refuses_below_minimum_with_actionable_message():
    with pytest.raises(RuntimeError) as exc:
        check_history_gate(9, 30, "EURUSD", "M15")
    msg = str(exc.value)
    assert "EURUSD" in msg and "M15" in msg
    assert "9" in msg and "30" in msg
    assert "extend collection (Phase 1 purge + backfill) or pass --min-history-days override" in msg


@pytest.mark.unit
def test_history_gate_passes_at_and_above_minimum():
    assert check_history_gate(30, 30, "EURUSD", "M15") is None
    assert check_history_gate(115, 30, "EURUSD", "H4") is None


# ---------------------------------------------------------------------------
# Pitfall 10: offset uniformity
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_offset_uniform_passes_on_uniform_frames():
    bars = _bars(20)
    assert assert_offset_uniform(bars) is None


@pytest.mark.unit
def test_offset_uniform_raises_on_mixed_offsets():
    bars = _bars(20)
    bars.iloc[10:, bars.columns.get_indexer(["time_utc"])] += pd.Timedelta(hours=1)
    with pytest.raises(RuntimeError, match="EURUSD"):
        assert_offset_uniform(bars)


# ---------------------------------------------------------------------------
# Resolver seam
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_resolver_values_land_in_label_row():
    def marker_resolver(position, bars, cfg):
        return {
            "outcome": "WIN",
            "exit_time": pd.Timestamp("2026-09-01 12:00:00"),
            "exit_price": 1.23456,
            "exit_idx": 35,
            "r_gross": 1.0,
            "r_raw": 0.9,
            "r_net": 0.8,
        }

    bars, chain = _world_bars_and_chain(tap_indices=(28,))
    labels = replay_symbol(bars, chain, CFG, marker_resolver)
    assert len(labels) == 1
    row = labels.iloc[0]
    assert row["outcome"] == "WIN"
    assert row["exit_time"] == pd.Timestamp("2026-09-01 12:00:00")
    assert row["exit_price"] == 1.23456
    assert row["exit_idx"] == 35
    assert row["r_gross"] == 1.0 and row["r_raw"] == 0.9 and row["r_net"] == 0.8
