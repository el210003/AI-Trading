"""Pure unit tests for the dashboard History data layer (DASH-04).

Exercises ``data_layer.history_frame`` over in-memory setup frames: terminal-only
retention, newest-first ordering, the invalidated-no-WIN/LOSS honor rule, the
optional outcome filter, and the schema-correct empty frame for a store with no
closed setups (T-06-03). Runs offline (no Streamlit, no MT5).
"""

from __future__ import annotations

import pandas as pd
import pytest
from _setup_fixtures import SETUP_COLUMNS, make_setup_frame

from ai_trading.dashboard import data_layer as dl


def _resolved_frame() -> pd.DataFrame:
    """A mixed frame: three terminal setups (with distinct closed_at) plus one
    structural break and two non-terminal rows that must be excluded."""
    return make_setup_frame(
        [
            {
                "setup_id": "a",
                "symbol": "EURUSD",
                "direction": "long",
                "status": "tp_hit",
                "outcome": "WIN",
                "closed_at": pd.Timestamp("2026-08-20T10:00:00"),
                "r_net": 1.5,
                "r_gross": 1.5,
                "p_win": 0.62,
                "score_source": "ml_llm",
            },
            {
                "setup_id": "b",
                "symbol": "GBPUSD",
                "direction": "short",
                "status": "sl_hit",
                "outcome": "LOSS",
                "closed_at": pd.Timestamp("2026-08-19T10:00:00"),
                "r_net": -1.0,
                "r_gross": -1.0,
                "p_win": 0.55,
                "score_source": "ml",
            },
            {
                "setup_id": "c",
                "symbol": "USDJPY",
                "direction": "long",
                "status": "expired",
                "outcome": "TIMEOUT",
                "closed_at": pd.Timestamp("2026-08-21T10:00:00"),
                "r_net": -0.1,
                "r_gross": -0.1,
                "p_win": 0.48,
                "score_source": "heuristic",
            },
            {
                "setup_id": "d",
                "symbol": "EURUSD",
                "direction": "short",
                "status": "invalidated",
                "outcome": pd.NA,
                "closed_at": pd.Timestamp("2026-08-18T10:00:00"),
                "r_net": float("nan"),
                "r_gross": 0.0,
                "p_win": 0.51,
                "score_source": "ml",
            },
            {
                "setup_id": "pending",
                "symbol": "EURUSD",
                "direction": "long",
                "status": "pending",
                "closed_at": pd.NaT,
            },
            {
                "setup_id": "active",
                "symbol": "EURUSD",
                "direction": "long",
                "status": "active",
                "closed_at": pd.NaT,
            },
        ]
    )


@pytest.mark.unit
def test_history_only_terminal_rows_retained():
    frame = dl.history_frame(_resolved_frame())
    # only the four terminal statuses survive; pending/active are excluded.
    assert sorted(frame["status"].tolist()) == sorted(
        ["tp_hit", "sl_hit", "expired", "invalidated"]
    )
    assert sorted(frame["outcome"].tolist()) == sorted(["WIN", "LOSS", "TIMEOUT", "invalidated"])


@pytest.mark.unit
def test_history_ordering_newest_first():
    frame = dl.history_frame(_resolved_frame())
    closed = frame["closed_at"]
    assert list(closed) == sorted(closed, reverse=True)
    # newest first: the expired (08-21) beats the tp_hit (08-20).
    assert list(frame["symbol"].head(1)) == ["USDJPY"]


@pytest.mark.unit
def test_history_invalidated_keeps_status_no_badge():
    frame = dl.history_frame(_resolved_frame())
    inv = frame[frame["status"] == "invalidated"]
    assert not inv.empty
    # The invalidated structural break must NOT be mapped to a WIN/LOSS badge.
    assert inv["outcome"].tolist() == ["invalidated"]
    # Its R falls back to r_gross when r_net is NaN.
    assert float(inv["r"].iloc[0]) == 0.0


@pytest.mark.unit
def test_history_empty_store_schema_frame():
    """T-06-03: an empty / no-closed-setup store returns the schema-correct
    empty frame (never raises) so the view renders the Empty state."""
    empty = pd.DataFrame(columns=list(SETUP_COLUMNS))
    frame = dl.history_frame(empty)
    assert frame.empty
    assert list(frame.columns) == list(dl.HISTORY_COLUMNS)

    # A store with rows but zero terminal outcomes -> still the empty schema frame.
    only_pending = make_setup_frame(
        [{"setup_id": "x", "symbol": "EURUSD", "status": "pending", "closed_at": pd.NaT}]
    )
    frame2 = dl.history_frame(only_pending)
    assert frame2.empty
    assert list(frame2.columns) == list(dl.HISTORY_COLUMNS)


@pytest.mark.unit
def test_history_outcome_filter_narrows():
    frame = dl.history_frame(_resolved_frame(), outcome="LOSS")
    assert frame["outcome"].tolist() == ["LOSS"]
    assert frame["status"].tolist() == ["sl_hit"]
    # An invalidated-only filter excludes all WIN/LOSS/TIMEOUT rows.
    frame2 = dl.history_frame(_resolved_frame(), outcome="invalidated")
    assert frame2["status"].tolist() == ["invalidated"]


@pytest.mark.unit
def test_history_columns_schema():
    frame = dl.history_frame(_resolved_frame())
    assert list(frame.columns) == list(dl.HISTORY_COLUMNS)
    assert frame["symbol"].dtype == pd.StringDtype()
    assert frame["closed_at"].dtype.kind == "M"
