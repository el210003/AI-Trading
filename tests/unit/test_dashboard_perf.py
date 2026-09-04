"""Pure unit tests for the dashboard Performance / equity data layer (DASH-05).

Exercises ``data_layer.performance_stats`` (label-like mapping, reuse of
``stats_by_symbol_timeframe``, exclusion of non-resolved statuses, empty-state
schema) and ``data_layer.cumulative_r_curve`` (closed_at ordering, per-symbol
filtering, exclusion of structural breaks). Runs offline (no Streamlit, no MT5).
"""

from __future__ import annotations

import pandas as pd
import pytest
from _setup_fixtures import SETUP_COLUMNS, make_setup_frame

from ai_trading.backtest.stats import STATS_COLUMNS, stats_by_symbol_timeframe
from ai_trading.dashboard import data_layer as dl


def _resolved_frame() -> pd.DataFrame:
    """A mixed frame: four resolved outcomes across two symbols plus three
    non-resolved rows (pending / active / invalidated) that must be excluded."""
    return make_setup_frame(
        [
            {
                "setup_id": "a",
                "symbol": "EURUSD",
                "timeframe": "M15",
                "status": "tp_hit",
                "outcome": "WIN",
                "r_gross": 2.0,
                "r_raw": 2.0,
                "r_net": 2.0,
                "closed_at": pd.Timestamp("2026-08-20T10:00:00"),
            },
            {
                "setup_id": "b",
                "symbol": "EURUSD",
                "timeframe": "M15",
                "status": "sl_hit",
                "outcome": "LOSS",
                "r_gross": -1.0,
                "r_raw": -1.0,
                "r_net": -1.0,
                "closed_at": pd.Timestamp("2026-08-19T10:00:00"),
            },
            {
                "setup_id": "c",
                "symbol": "GBPUSD",
                "timeframe": "M15",
                "status": "expired",
                "outcome": "TIMEOUT",
                "r_gross": -0.5,
                "r_raw": -0.5,
                "r_net": -0.5,
                "closed_at": pd.Timestamp("2026-08-21T10:00:00"),
            },
            {
                "setup_id": "d",
                "symbol": "EURUSD",
                "timeframe": "M15",
                "status": "sl_hit",
                "outcome": "LOSS",
                "r_gross": -1.0,
                "r_raw": -1.0,
                "r_net": -1.0,
                "closed_at": pd.Timestamp("2026-08-18T10:00:00"),
            },
            {
                "setup_id": "pending",
                "symbol": "EURUSD",
                "timeframe": "M15",
                "status": "pending",
                "r_gross": float("nan"),
            },
            {
                "setup_id": "active",
                "symbol": "EURUSD",
                "timeframe": "M15",
                "status": "active",
                "r_gross": float("nan"),
            },
            {
                "setup_id": "inv",
                "symbol": "GBPUSD",
                "timeframe": "M15",
                "status": "invalidated",
                "r_gross": 0.0,
            },
        ]
    )


@pytest.mark.unit
def test_performance_stats_aggregate_and_per_symbol():
    result = dl.performance_stats(_resolved_frame())
    agg = result["aggregate"]
    # 4 resolved trades (1 WIN, 2 LOSS, 1 TIMEOUT); pending/active/invalidated out.
    assert agg["trades"] == 4
    assert agg["wins"] == 1
    assert agg["losses"] == 2
    assert agg["timeouts"] == 1
    # A4 win-rate denominator excludes TIMEOUT: 1 / (1 + 2).
    assert agg["win_rate"] == pytest.approx(1 / 3)
    # A4-consistent decided-trade PF: 2.0 / (1.0 + 1.0).
    assert agg["profit_factor"] == pytest.approx(1.0)
    # A5 expectancy over ALL trades incl. TIMEOUT: (2 - 1 - 0.5 - 1) / 4.
    assert agg["expectancy"] == pytest.approx(-0.125)


@pytest.mark.unit
def test_performance_stats_agrees_with_stats_func():
    result = dl.performance_stats(_resolved_frame())
    direct = stats_by_symbol_timeframe(result["labels"])
    pd.testing.assert_frame_equal(
        result["stats"].reset_index(drop=True), direct.reset_index(drop=True)
    )
    # Per-symbol row for EURUSD (3 trades, no timeout).
    eur = result["stats"][result["stats"]["symbol"] == "EURUSD"].iloc[0]
    assert eur["trades"] == 3
    assert eur["net_win_rate"] == pytest.approx(1 / 3)
    assert eur["net_expectancy"] == pytest.approx(0.0)


@pytest.mark.unit
def test_performance_stats_excludes_non_resolved():
    """pending/active/invalidated never reach the stats (the label frame only
    carries the mapped resolved outcome enums)."""
    result = dl.performance_stats(_resolved_frame())
    outcomes = set(result["labels"]["outcome"].unique())
    assert outcomes == {"WIN", "LOSS", "TIMEOUT"}
    assert "invalidated" not in outcomes
    # r_raw == r_net == r_gross structural-R basis.
    assert (result["labels"]["r_raw"] == result["labels"]["r_net"]).all()


@pytest.mark.unit
def test_performance_stats_all_expired_non_crashing():
    all_expired = make_setup_frame(
        [
            {"setup_id": "e1", "symbol": "EURUSD", "timeframe": "M15",
             "status": "expired", "outcome": "TIMEOUT", "r_gross": -0.2,
             "closed_at": pd.Timestamp("2026-08-20T10:00:00")},
            {"setup_id": "e2", "symbol": "GBPUSD", "timeframe": "M15",
             "status": "expired", "outcome": "TIMEOUT", "r_gross": -0.3,
             "closed_at": pd.Timestamp("2026-08-21T10:00:00")},
        ]
    )
    result = dl.performance_stats(all_expired)
    agg = result["aggregate"]
    assert agg["trades"] == 2
    assert agg["timeouts"] == 2
    # A4: no decided trades -> win_rate nan (never 0), PF nan, never raises.
    assert pd.isna(agg["win_rate"])
    assert pd.isna(agg["profit_factor"])
    # A5 expectancy is the signed mean over all incl. TIMEOUTs.
    assert agg["expectancy"] == pytest.approx(-0.25)
    # Per-symbol stats frame still schema-correct with the timeout rows.
    assert set(result["stats"]["symbol"]) == {"EURUSD", "GBPUSD"}


@pytest.mark.unit
def test_cumulative_r_curve_ordering_and_filter():
    frame = _resolved_frame()
    curve = dl.cumulative_r_curve(frame)
    assert list(curve["time_utc"]) == sorted(curve["time_utc"])
    # cumulative sums of the sorted r_gross (ascending by closed_at):
    # d(-1) -> b(-1) -> a(+2) -> c(-0.5).
    assert curve["cum_r"].tolist() == pytest.approx([-1.0, -2.0, 0.0, -0.5])
    # Per-symbol filter narrows to that symbol only.
    eur = dl.cumulative_r_curve(frame, symbol="EURUSD")
    assert set(eur["time_utc"]) == {
        pd.Timestamp("2026-08-18T10:00:00"),
        pd.Timestamp("2026-08-19T10:00:00"),
        pd.Timestamp("2026-08-20T10:00:00"),
    }
    # The resolved-only frame the curve uses must not contain invalidated.
    perf_statuses = set(frame[frame["status"].isin(dl.PERF_OUTCOME_STATUSES)]["status"])
    assert "invalidated" not in perf_statuses


@pytest.mark.unit
def test_cumulative_r_curve_empty_schema():
    empty = pd.DataFrame(columns=list(SETUP_COLUMNS))
    curve = dl.cumulative_r_curve(empty)
    assert curve.empty
    assert list(curve.columns) == ["time_utc", "cum_r"]


@pytest.mark.unit
def test_performance_stats_empty_schema():
    """T-06-03: an empty store yields a schema-correct empty stats frame + a
    nan aggregate (never raises) so the view renders the Empty state."""
    empty = pd.DataFrame(columns=list(SETUP_COLUMNS))
    result = dl.performance_stats(empty)
    assert result["labels"].empty
    assert result["stats"].empty
    assert list(result["stats"].columns) == list(STATS_COLUMNS)
    assert result["aggregate"]["trades"] == 0
    assert pd.isna(result["aggregate"]["win_rate"])
