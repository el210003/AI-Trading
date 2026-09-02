"""Unit tests for the BT-05 walk-forward harness: chronological zero-overlap
windows (Pitfall 7), expanding train strictly before test (D-19), small
day-windows on short stores (D-20), exactly-one-window entry-time assignment,
per-(window, symbol, timeframe) canonical stats + cross-symbol aggregate
(D-22), and the zero-label contract (empty inputs are supported states, not
errors). Literal timestamp sets throughout; no MT5."""

from __future__ import annotations

import pandas as pd
import pytest

from ai_trading.backtest.stats import canonical_stats
from ai_trading.backtest.walkforward import (
    WINDOW_AGG_COLUMNS,
    WINDOW_STATS_COLUMNS,
    build_windows,
    label_window_assignment,
    window_aggregate,
    window_stats_table,
)

BASE = pd.Timestamp("2026-08-20 00:00:00")
_STR_DTYPE = pd.StringDtype()


def _entry_times(n_days: int = 5, per_day: int = 2) -> pd.Series:
    """Literal label entry times: ``per_day`` bars per day at 00:00/00:15."""
    times = [
        BASE + pd.Timedelta(days=d) + pd.Timedelta(minutes=15 * k)
        for d in range(n_days)
        for k in range(per_day)
    ]
    return pd.Series(times, dtype="datetime64[us]")


def _labels(
    times: pd.Series,
    symbol: str = "EURUSD",
    outcomes: tuple[str, ...] | None = None,
    r_raw: tuple[float, ...] | None = None,
    r_net: tuple[float, ...] | None = None,
) -> pd.DataFrame:
    n = len(times)
    outcomes = outcomes or ("WIN",) * n
    r_raw = r_raw or (1.0,) * n
    r_net = r_net or (0.9,) * n
    return pd.DataFrame(
        {
            "symbol": [symbol] * n,
            "timeframe": ["M15"] * n,
            "outcome": list(outcomes),
            "entry_time": list(times),
            "r_raw": list(r_raw),
            "r_net": list(r_net),
        }
    )


def _empty_labels() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "symbol": pd.Series(dtype=_STR_DTYPE),
            "timeframe": pd.Series(dtype=_STR_DTYPE),
            "outcome": pd.Series(dtype=_STR_DTYPE),
            "entry_time": pd.Series(dtype="datetime64[us]"),
            "r_raw": pd.Series(dtype="float64"),
            "r_net": pd.Series(dtype="float64"),
        }
    )


def _multi_symbol_labels() -> pd.DataFrame:
    """Two symbols across two days: hand-checkable pooled aggregate (D-22)."""
    rows = [
        # window 0 (Aug 20)
        ("EURUSD", pd.Timestamp("2026-08-20 00:00"), "WIN", 1.0, 0.9),
        ("EURUSD", pd.Timestamp("2026-08-20 06:00"), "LOSS", -1.0, -1.1),
        ("EURUSD", pd.Timestamp("2026-08-20 12:00"), "TIMEOUT", -0.1, -0.15),
        ("GBPUSD", pd.Timestamp("2026-08-20 03:00"), "WIN", 0.5, 0.4),
        ("GBPUSD", pd.Timestamp("2026-08-20 09:00"), "WIN", 1.0, 0.95),
        # window 1 (Aug 21)
        ("EURUSD", pd.Timestamp("2026-08-21 02:00"), "LOSS", -1.0, -1.2),
        ("GBPUSD", pd.Timestamp("2026-08-21 05:00"), "TIMEOUT", -0.1, -0.1),
    ]
    frame = pd.DataFrame(
        rows, columns=["symbol", "entry_time", "outcome", "r_raw", "r_net"]
    )
    frame["timeframe"] = "M15"
    return frame


# ---------------------------------------------------------------------------
# Chronology + zero overlap (Pitfall 7 / D-19)
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_windows_chronological_zero_overlap():
    times = _entry_times()
    windows = build_windows(times, test_days=1, train_days=2)
    assert len(windows) == 5
    starts = [w.test_start for w in windows]
    assert starts == sorted(starts)  # ascending
    assert [w.window_id for w in windows] == [0, 1, 2, 3, 4]
    for prev, nxt in zip(windows, windows[1:], strict=False):
        assert nxt.test_start == prev.test_end  # touch, no gap, no overlap
    for i, a in enumerate(windows):
        for b in windows[i + 1 :]:
            # test masks over the same label set are disjoint
            assert not (a.test_mask & b.test_mask).any()


@pytest.mark.unit
def test_expanding_train_strictly_before_test():
    times = _entry_times(n_days=3)
    windows = build_windows(times, test_days=1, train_days=2)
    for w in windows:
        train_times = times[w.train_mask]
        assert (train_times < w.test_start).all()  # STRICTLY before (D-19)
        # expanding: later windows see every earlier label
        if w.window_id > 0:
            prev_test = times[windows[w.window_id - 1].test_mask]
            assert (prev_test.index.isin(train_times.index)).all()


@pytest.mark.unit
def test_label_at_test_start_is_test_not_train():
    """Boundary pin: a label AT test_start belongs to the TEST mask only."""
    times = pd.Series(
        [
            pd.Timestamp("2026-08-20 10:00"),
            pd.Timestamp("2026-08-21 00:00"),  # exactly on boundary b_1
        ],
        dtype="datetime64[us]",
    )
    windows = build_windows(times, test_days=1, train_days=2)
    assert len(windows) == 2  # <= loop bound covers the boundary-aligned end
    boundary_label = windows[1].test_start
    w0, w1 = windows
    assert bool(times.loc[times == boundary_label].index.isin(times[w0.test_mask].index)) is False
    assert times[w1.test_mask].tolist() == [boundary_label]
    assert times[w1.train_mask].tolist() == [pd.Timestamp("2026-08-20 10:00")]
    assigned = label_window_assignment(_labels(times), windows)
    assert assigned["window_id"].tolist() == [0, 1]


@pytest.mark.unit
def test_no_shuffle_input_order_preserved():
    times = _entry_times(n_days=3)
    shuffled = times.sample(frac=1.0, random_state=7)
    windows = build_windows(shuffled, test_days=1, train_days=1)
    for w in windows:
        assert w.train_mask.index.equals(shuffled.index)
        assert w.test_mask.index.equals(shuffled.index)
        assert w.test_mask.dtype == bool
        selected = shuffled[w.test_mask]
        assert ((selected >= w.test_start) & (selected < w.test_end)).all()
    # same labels, same windows regardless of input order
    ordered = build_windows(times.sort_values().reset_index(drop=True), 1, 1)
    assert len(ordered) == len(windows)
    for a, b in zip(ordered, windows, strict=True):
        assert (a.test_start, a.test_end) == (b.test_start, b.test_end)


# ---------------------------------------------------------------------------
# Small day-windows (D-20)
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_small_windows_one_day_tests():
    times = _entry_times(n_days=5, per_day=2)  # 10 labels over 5 days
    windows = build_windows(times, test_days=1, train_days=2)
    assert len(windows) == 5
    for w in windows:
        assert int(w.test_mask.sum()) == 2  # exactly the day's two labels
        if w.window_id >= 2:  # train_days=2 accumulated
            assert int(w.train_mask.sum()) == 2 * w.window_id


@pytest.mark.unit
def test_small_windows_two_day_tests():
    times = _entry_times(n_days=5, per_day=2)
    windows = build_windows(times, test_days=2, train_days=2)
    assert len(windows) == 3
    assert [int(w.test_mask.sum()) for w in windows] == [4, 4, 2]


@pytest.mark.unit
def test_invalid_window_sizes_raise():
    times = _entry_times(n_days=2)
    for bad in (0, -1):
        with pytest.raises(ValueError, match="test_days"):
            build_windows(times, test_days=bad, train_days=2)
        with pytest.raises(ValueError, match="train_days"):
            build_windows(times, test_days=1, train_days=bad)
    with pytest.raises(ValueError, match="test_days"):
        build_windows(times, test_days=True, train_days=1)  # bool is not an int size


# ---------------------------------------------------------------------------
# Exactly-one-window assignment
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_every_label_assigned_exactly_one_window():
    times = _entry_times(n_days=5, per_day=2)
    windows = build_windows(times, test_days=1, train_days=2)
    labels = _labels(times)
    assigned = label_window_assignment(labels, windows)
    assert "window_id" in assigned.columns
    assert assigned["window_id"].dtype == "int64"
    assert assigned["window_id"].notna().all()
    # domain edges: first and last labels assign to the first/last windows
    assert assigned["window_id"].iloc[0] == 0
    assert assigned["window_id"].iloc[-1] == 4
    # per-window counts match the masks
    for w in windows:
        assert int((assigned["window_id"] == w.window_id).sum()) == int(w.test_mask.sum())
    # input frame never mutated
    assert "window_id" not in labels.columns


@pytest.mark.unit
def test_duplicate_entry_times_both_assign():
    stamp = pd.Timestamp("2026-08-20 06:00")
    times = pd.Series([stamp, stamp, pd.Timestamp("2026-08-20 07:00")], dtype="datetime64[us]")
    windows = build_windows(times, test_days=1, train_days=1)
    assigned = label_window_assignment(_labels(times), windows)
    assert assigned["window_id"].tolist() == [0, 0, 0]


@pytest.mark.unit
def test_outside_domain_label_raises_naming_entry_time():
    times = _entry_times(n_days=5, per_day=2)
    windows = build_windows(times, test_days=1, train_days=2, start=pd.Timestamp("2026-08-21"))
    labels = _labels(times)  # Aug 20 labels precede the explicit start domain
    with pytest.raises(ValueError, match="2026-08-20 00:00:00"):
        label_window_assignment(labels, windows)


@pytest.mark.unit
def test_labels_present_with_no_windows_raises():
    labels = _labels(_entry_times(n_days=1))
    with pytest.raises(ValueError, match="no windows"):
        label_window_assignment(labels, [])


# ---------------------------------------------------------------------------
# Per-window stats (D-22 / D-16)
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_window_stats_table_matches_canonical_per_group():
    labels = _multi_symbol_labels()
    windows = build_windows(labels["entry_time"], test_days=1, train_days=2)
    assigned = label_window_assignment(labels, windows)
    table = window_stats_table(assigned)

    assert list(table.columns) == list(WINDOW_STATS_COLUMNS)
    assert len(table) == 4  # 2 windows x 2 symbols

    def _same(a, b) -> bool:
        return bool(a == b) or (pd.isna(a) and pd.isna(b))

    for _, row in table.iterrows():
        subset = assigned[
            (assigned["window_id"] == row["window_id"]) & (assigned["symbol"] == row["symbol"])
        ]
        raw = canonical_stats(subset, "r_raw")
        net = canonical_stats(subset, "r_net")
        assert row["trades"] == raw["trades"]
        assert row["wins"] == raw["wins"] and row["losses"] == raw["losses"]
        assert row["timeouts"] == raw["timeouts"]
        assert _same(row["raw_win_rate"], raw["win_rate"])  # nan == nan path (all-TIMEOUT group)
        assert _same(row["net_profit_factor"], net["profit_factor"])
        assert _same(row["raw_expectancy"], raw["expectancy"])
        assert _same(row["net_expectancy"], net["expectancy"])
        if not (pd.isna(raw["expectancy"]) or pd.isna(net["expectancy"])):
            assert row["cost_delta_expectancy"] == pytest.approx(
                net["expectancy"] - raw["expectancy"], abs=1e-12
            )
        assert row["window_start"] == subset["entry_time"].min()
        assert row["window_end"] == subset["entry_time"].max()


@pytest.mark.unit
def test_window_stats_table_sorted_and_raw_net_present():
    labels = _multi_symbol_labels()
    windows = build_windows(labels["entry_time"], test_days=1, train_days=2)
    table = window_stats_table(label_window_assignment(labels, windows))
    keys = list(zip(table["window_id"], table["symbol"], strict=True))
    assert keys == sorted(keys)
    for prefix in ("raw_", "net_"):
        for key in ("win_rate", "profit_factor", "expectancy", "avg_r", "max_dd"):
            assert f"{prefix}{key}" in table.columns
    assert "cost_delta_expectancy" in table.columns


@pytest.mark.unit
def test_window_aggregate_pools_across_symbols():
    labels = _multi_symbol_labels()
    windows = build_windows(labels["entry_time"], test_days=1, train_days=2)
    assigned = label_window_assignment(labels, windows)
    agg = window_aggregate(assigned)
    table = window_stats_table(assigned)

    assert list(agg.columns) == list(WINDOW_AGG_COLUMNS)
    assert len(agg) == 2
    w0 = agg[agg["window_id"] == 0].iloc[0]
    # counts equal the sum of the per-(symbol, TF) rows for the same window
    per_symbol_w0 = table[table["window_id"] == 0]
    assert w0["trades"] == int(per_symbol_w0["trades"].sum()) == 5
    assert w0["wins"] == int(per_symbol_w0["wins"].sum()) == 3
    assert w0["losses"] == int(per_symbol_w0["losses"].sum()) == 1
    assert w0["timeouts"] == int(per_symbol_w0["timeouts"].sum()) == 1
    # win_rate computed on the POOLED R series (3 decided of 5 trades)
    pooled = assigned[assigned["window_id"] == 0]
    assert w0["net_win_rate"] == canonical_stats(pooled, "r_net")["win_rate"] == 0.75
    assert w0["net_expectancy"] == pytest.approx(pooled["r_net"].mean(), abs=1e-12)
    assert w0["window_start"] == pooled["entry_time"].min()


@pytest.mark.unit
def test_window_stats_missing_columns_raise():
    labels = _multi_symbol_labels()
    windows = build_windows(labels["entry_time"], test_days=1, train_days=2)
    assigned = label_window_assignment(labels, windows)
    with pytest.raises(ValueError, match="invariant violated"):
        window_stats_table(assigned.drop(columns=["r_net"]))
    with pytest.raises(ValueError, match="invariant violated"):
        window_aggregate(assigned.drop(columns=["window_id"]))
    with pytest.raises(ValueError, match="r_col"):
        window_stats_table(assigned, r_col="r_gross")


# ---------------------------------------------------------------------------
# Zero-label contract (supported state, never an error)
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_build_windows_empty_entry_times_returns_empty_list():
    assert build_windows(pd.Series(dtype="datetime64[us]"), test_days=1, train_days=2) == []


@pytest.mark.unit
def test_assignment_empty_labels_returns_input_schema_plus_window_id():
    empty = _empty_labels()
    assigned = label_window_assignment(empty, [])
    assert len(assigned) == 0
    assert list(assigned.columns) == list(empty.columns) + ["window_id"]
    assert assigned["window_id"].dtype == "int64"
    # input untouched
    assert "window_id" not in empty.columns


@pytest.mark.unit
def test_stats_helpers_empty_labels_schema_correct():
    empty_assigned = label_window_assignment(_empty_labels(), [])
    table = window_stats_table(empty_assigned)
    agg = window_aggregate(empty_assigned)
    assert len(table) == 0 and list(table.columns) == list(WINDOW_STATS_COLUMNS)
    assert len(agg) == 0 and list(agg.columns) == list(WINDOW_AGG_COLUMNS)
    # pinned dtypes survive the empty path
    assert table["window_id"].dtype == "int64" and agg["window_id"].dtype == "int64"
    assert table["window_start"].dtype == "datetime64[us]"
    assert str(table["symbol"].dtype) == "string"
    assert table["net_expectancy"].dtype == "float64"


@pytest.mark.unit
def test_boundary_aligned_domain_fully_assigned():
    """End-to-end pin of the <= loop bound: a store whose last entry lands
    exactly on a window boundary still assigns every label exactly once."""
    times = pd.Series(
        [BASE + pd.Timedelta(days=d) for d in range(5)], dtype="datetime64[us]"
    )  # daily labels Aug 20..24; Aug 24 == boundary b_4
    windows = build_windows(times, test_days=1, train_days=1)
    assert len(windows) == 5
    assigned = label_window_assignment(_labels(times), windows)
    assert assigned["window_id"].tolist() == [0, 1, 2, 3, 4]
