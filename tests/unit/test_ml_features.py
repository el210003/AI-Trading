"""Unit tests for the point-in-time feature builder (AI-01): FEATURE_SPEC,
features_at_decision, build_feature_frame.

Named tests pin the anti-lookahead rules and contracts:
- decision-close R:R (never the fill-based label column)
- session-gap-robust decision-bar location
- categorical payload-as-is missing policy
- ATR warmup NA propagation
- zone/sweep recency features as as-of bar counts
- schema/dtype/alignment, empty-frame, and multi-symbol rejection

No MetaTrader5 import anywhere.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest
from _ml_fixtures import make_labels, ml_cfg, sculpted_label_world

from ai_trading.backtest.asof import close_time_of
from ai_trading.backtest.candidates import CandidateState, compute_rr
from ai_trading.backtest.chain import run_chain
from ai_trading.ml.features import FEATURE_SPEC, build_feature_frame, features_at_decision

M15 = "M15"


def _feat_names() -> list[str]:
    return [entry["name"] for entry in FEATURE_SPEC]


@pytest.fixture
def world():
    m15, h1, h4, labels = sculpted_label_world()
    chain = run_chain(m15, h1, h4)
    return m15, h1, h4, labels, chain


# ---------------------------------------------------------------------------
# The subtle leak: R:R recomputed at the decision close, not the fill open
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_rr_feature_uses_decision_close_not_fill_open(world):
    m15, _, _, labels, chain = world
    frame = build_feature_frame(labels, chain, m15)
    row = frame.iloc[0]
    # First label: decision bar 33, fill bar 34 (open 1.10), sl 1.068, tp 1.16,
    # decision close = 1.105 (the sculpted flat close).
    decision_bar = 33
    expected = compute_rr("long", float(m15.iloc[decision_bar]["close"]), 1.068, 1.16)
    assert row["rr_at_decision"] == pytest.approx(expected)
    # The label's fill-based rr differs (fill open 1.10 vs decision close 1.105).
    label_rr = float(labels.iloc[0]["rr"])
    assert row["rr_at_decision"] != pytest.approx(label_rr)
    # Mutation check: the fill-based rr must never equal the feature value.
    assert not math.isclose(float(label_rr), float(row["rr_at_decision"]))


# ---------------------------------------------------------------------------
# Session-gap decision-bar location (positional predecessor, never time math)
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_decision_bar_located_across_session_gap(tmp_path):
    from datetime import datetime

    from _detector_fixtures import flat_bars
    from conftest import make_bars

    start = datetime(2026, 8, 20, 0, 0)
    bars = make_bars("EURUSD", "M15", start, 120)
    # Insert a multi-day gap: shift every bar from index 100 onward +2 days.
    gap = pd.Timedelta(days=2)
    bars.loc[bars.index >= 100, "time_utc"] += gap
    bars.loc[bars.index >= 100, "time"] += gap
    h1 = flat_bars("EURUSD", "H1", start, 40)
    h4 = flat_bars("EURUSD", "H4", start, 40)
    chain = run_chain(bars, h1, h4)

    entry_time = bars.iloc[100]["time_utc"]
    labels = make_labels(
        [
            {
                "symbol": "EURUSD",
                "timeframe": "M15",
                "direction": "long",
                "entry_time": entry_time,
                "sl_price": 1.09,
                "tp_price": 1.13,
                "zone_id": "Z1",
                "event_id": "E1",
                "outcome": "WIN",
                "exit_idx": 106,
            }
        ]
    )
    frame = build_feature_frame(labels, chain, bars)
    assert len(frame) == 1
    row = frame.iloc[0]
    # Naive entry_time - 15min would land 2 days too early (not a real bar).
    assert row["decision_close_time"] != entry_time - pd.Timedelta(minutes=15)
    # The positional predecessor of the fill bar (bar 99) is the decision bar.
    assert row["decision_close_time"] == close_time_of(
        bars.iloc[99]["time_utc"], "M15"
    )


# ---------------------------------------------------------------------------
# Categorical payload consumed as-is (NA when payload_row is None)
# ---------------------------------------------------------------------------

def _empty_state(bars: pd.DataFrame, payload_row=None) -> CandidateState:
    """CandidateState over empty tier frames + an optional payload_row."""
    return CandidateState(
        m15_bars=bars,
        events15=pd.DataFrame(
            columns=[
                "event_id", "resolved_at", "event_type", "side",
                "symbol", "pool_id", "level", "timeframe",
            ]
        ),
        zones15=pd.DataFrame(
            columns=[
                "zone_id", "range_high", "range_low", "equilibrium", "state",
                "created_at", "mitigated_at", "symbol", "timeframe",
                "leg_direction", "invalidated_at",
            ]
        ),
        pools15=pd.DataFrame(columns=["pool_id", "side", "level", "symbol", "timeframe"]),
        swings15=pd.DataFrame(columns=["confirmed_at", "price", "side", "symbol"]),
        payload_row=payload_row,
    )


@pytest.mark.unit
def test_categorical_features_from_payload_as_is():
    bars = _small_bars()
    state = _empty_state(bars, payload_row=None)
    label_row = _label_row()
    feats = features_at_decision(state, label_row, ml_cfg())
    assert pd.isna(feats["bias_h1"])
    assert pd.isna(feats["bias_h4"])
    # Payload-as-is numeric columns are NaN when payload_row is None.
    assert pd.isna(feats["htf_dist_to_eq_atr_h1"])
    assert pd.isna(feats["htf_dist_to_eq_atr_h4"])
    assert feats["htf_bias_agreement"] == 0


# ---------------------------------------------------------------------------
# ATR warmup NA propagation
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_atr_warmup_propagates_missing():
    bars = _small_bars(count=5)  # < ATR(14) warmup
    state = _empty_state(bars, payload_row=None)
    feats = features_at_decision(state, _label_row(), ml_cfg())
    assert pd.isna(feats["atr14"])
    assert pd.isna(feats["sl_dist_atr"])
    assert pd.isna(feats["tp_dist_atr"])


# ---------------------------------------------------------------------------
# Zone/sweep recency features (as-of bar counts)
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_zone_and_sweep_recency_features(world):
    m15, _, _, labels, chain = world
    frame = build_feature_frame(labels, chain, m15)
    row = frame.iloc[0]
    entry_time = labels.iloc[0]["entry_time"]
    entry_pos = int(
        np.searchsorted(m15["time_utc"].to_numpy(), pd.Timestamp(entry_time), side="left")
    )
    decision_idx = entry_pos - 1
    decision_close_time = close_time_of(m15.iloc[decision_idx]["time_utc"], "M15")
    assert row["decision_close_time"] == decision_close_time

    # Sweep recency: the swept event resolved_at's bar index
    event_id = labels.iloc[0]["event_id"]
    ev = chain["events15"][chain["events15"]["event_id"] == event_id]
    assert len(ev) == 1
    resolved_at = pd.Timestamp(ev.iloc[0]["resolved_at"])
    sweep_pos = int(np.searchsorted(m15["time_utc"].to_numpy(), resolved_at, side="left"))
    assert m15.iloc[sweep_pos]["time_utc"] == resolved_at
    assert row["bars_since_sweep"] == decision_idx - sweep_pos

    # Zone recency: the tapped zone's created_at -> latest bar at or before it
    zone_id = labels.iloc[0]["zone_id"]
    zn = chain["zones15"][chain["zones15"]["zone_id"] == zone_id]
    created_at = pd.Timestamp(zn.iloc[0]["created_at"])
    pos = int(np.searchsorted(m15["time_utc"].to_numpy(), created_at, side="right")) - 1
    assert row["bars_since_zone_created"] == decision_idx - pos


# ---------------------------------------------------------------------------
# Schema / dtype / alignment / empty / multi-symbol
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_feature_frame_schema_and_row_alignment(world):
    m15, _, _, labels, chain = world
    frame = build_feature_frame(labels, chain, m15)
    expected_cols = list(_feat_names()) + ["entry_time", "decision_close_time"]
    assert list(frame.columns) == expected_cols
    assert frame.columns.is_unique
    # Row order equals label order.
    assert list(frame["entry_time"]) == list(labels["entry_time"])
    # Categorical columns are category dtype; numeric are float64.
    for name in _feat_names():
        entry = next(e for e in FEATURE_SPEC if e["name"] == name)
        if entry["dtype"] == "categorical":
            assert str(frame[name].dtype) == "category" or isinstance(
                frame[name].dtype, pd.CategoricalDtype
            ), name
        else:
            assert str(frame[name].dtype) == "float64", name
    assert str(frame["entry_time"].dtype) == "datetime64[us]"
    assert str(frame["decision_close_time"].dtype) == "datetime64[us]"


@pytest.mark.unit
def test_empty_labels_schema_correct_empty_frame(world):
    m15, _, _, _, chain = world
    empty_labels = make_labels([])
    frame = build_feature_frame(empty_labels, chain, m15)
    assert list(frame.columns) == list(_feat_names()) + ["entry_time", "decision_close_time"]
    assert len(frame) == 0
    for name in _feat_names():
        entry = next(e for e in FEATURE_SPEC if e["name"] == name)
        if entry["dtype"] == "categorical":
            assert isinstance(frame[name].dtype, pd.CategoricalDtype), name
        else:
            assert str(frame[name].dtype) == "float64", name
    assert str(frame["entry_time"].dtype) == "datetime64[us]"
    assert str(frame["decision_close_time"].dtype) == "datetime64[us]"


@pytest.mark.unit
def test_build_feature_frame_rejects_multi_symbol_labels(world):
    m15, _, _, labels, chain = world
    other = labels.copy()
    other.iloc[0, other.columns.get_indexer(["symbol"])] = "GBPUSD"
    with pytest.raises(ValueError):
        build_feature_frame(other, chain, m15)


def _small_bars(count: int = 60) -> pd.DataFrame:
    from datetime import datetime

    from conftest import make_bars

    df = make_bars("EURUSD", "M15", datetime(2026, 8, 20, 0, 0), count)
    return df


def _label_row() -> pd.Series:
    return pd.Series(
        {
            "symbol": "EURUSD",
            "timeframe": "M15",
            "direction": "long",
            "entry_time": pd.Timestamp("2026-08-20 01:00:00"),
            "sl_price": 1.09,
            "tp_price": 1.13,
            "zone_id": "Z1",
            "event_id": "E1",
        }
    )


@pytest.mark.unit
def test_feature_spec_covers_exactly_18_named_entries():
    assert len(FEATURE_SPEC) == 18
    names = [e["name"] for e in FEATURE_SPEC]
    assert len(set(names)) == 18
    for entry in FEATURE_SPEC:
        assert entry["dtype"] in ("categorical", "float64")
        assert entry["source_tier"]
        assert entry["source_columns"]
        assert entry["stamp_kind"] in ("close", "bar", "payload-as-is")
