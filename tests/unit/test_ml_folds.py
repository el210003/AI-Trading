"""Unit tests for the harness-derived calibration fold pairs (SC3 / AI-04).

Named tests pin the SC3 "the Phase 3 harness is the only splitter" rule and the
purge-at-every-boundary requirement:

- ``test_folds_derived_from_build_windows_expanding``: fold pairs are positional
  projections of ``walkforward.build_windows`` (expanding train, sequential
  non-overlapping ascending test blocks), not a new splitter.
- ``test_folds_purge_applied_at_every_boundary``: a label whose ``exit_time``
  lands at/after a fold's test_start is absent from that fold's train but
  present in the later fold whose test_start is beyond its exit.
- ``test_folds_embargo_applied``: ``embargo_bars=1`` shrinks every fold's train
  by exactly the rows whose exit falls inside the embargo window.
- ``test_folds_empty_entry_times_returns_empty_list`` and
  ``test_folds_reject_harness_invalid_days``.

No MetaTrader5 import anywhere.
"""

from __future__ import annotations

import pandas as pd
import pytest
from _ml_fixtures import make_labels

from ai_trading.backtest.walkforward import build_windows
from ai_trading.ml.folds import calibration_folds
from ai_trading.ml.purge import purged_train_mask

TF_MIN = 15


def _freq_labels(
    start: pd.Timestamp, periods: int, freq: str = "h", exit_minutes: int = 60
) -> pd.DataFrame:
    """Positionally-indexed label frame with ``freq``-spaced entries and an
    ``exit_minutes`` offset for every exit (custom exits are added per-test)."""
    idx = pd.date_range(start, periods=periods, freq=freq)
    rows = [
        {
            "symbol": "EURUSD",
            "timeframe": "M15",
            "direction": "long",
            "entry_time": e,
            "exit_time": e + pd.Timedelta(minutes=exit_minutes),
        }
        for e in idx
    ]
    return make_labels(rows)


def _hourly_labels(start: pd.Timestamp, periods: int, exit_minutes: int = 60) -> pd.DataFrame:
    """Hourly-spaced variant of :func:`_freq_labels` (the common case)."""
    return _freq_labels(start, periods, freq="h", exit_minutes=exit_minutes)


def _custom_labels(rows: list[tuple[pd.Timestamp, pd.Timestamp]]) -> pd.DataFrame:
    return make_labels(
        [
            {
                "symbol": "EURUSD",
                "timeframe": "M15",
                "direction": "long",
                "entry_time": e,
                "exit_time": x,
            }
            for e, x in rows
        ]
    )


def _expected_folds(entry, exit_, test_days, train_days, embargo_bars):
    """Recompute the fold pairs independently from build_windows + the purge —
    the ground truth the implementation must match."""
    expected: list[tuple[list[int], list[int]]] = []
    for w in build_windows(entry, test_days=test_days, train_days=train_days):
        tr = purged_train_mask(w.train_mask, exit_, w.test_start, embargo_bars, TF_MIN)
        tr_pos = tr.to_numpy().nonzero()[0].tolist()
        te_pos = w.test_mask.to_numpy().nonzero()[0].tolist()
        if tr_pos and te_pos:
            expected.append((tr_pos, te_pos))
    return expected


@pytest.mark.unit
def test_folds_derived_from_build_windows_expanding():
    # 5 days of hourly entries -> windows b=01-01/01-03/01-05/01-07; the first
    # window's train is empty (expanding), so only later windows yield pairs.
    labels = _hourly_labels(pd.Timestamp("2026-01-01 00:00"), 5 * 24)
    entry, exit_ = labels["entry_time"], labels["exit_time"]
    folds = calibration_folds(entry, exit_, test_days=2, train_days=2, embargo_bars=0)

    assert len(folds) >= 2
    # Exactly the build_windows-derived pairs (no second splitter).
    assert folds == _expected_folds(entry, exit_, 2, 2, 0)

    train_sets = [set(t) for t, _ in folds]
    # Expanding: each fold's train is a superset of the previous fold's.
    for i in range(len(train_sets) - 1):
        assert train_sets[i] <= train_sets[i + 1], "train positions must expand monotonically"
    # Sequential, non-overlapping, ascending test blocks (D-19).
    for i in range(len(folds) - 1):
        # folds[i] is (train_positions, test_positions).
        assert max(folds[i][1]) < min(folds[i + 1][1]), (
            "test blocks must be sequential and non-overlapping"
        )


@pytest.mark.unit
def test_folds_purge_applied_at_every_boundary():
    # Entry 01-02 20:00 exits 01-03 06:00: at the 01-03 test_start its outcome
    # resolves inside the test window (exit >= test_start) -> purged from that
    # fold's train; at the later 01-05 test_start (beyond its exit) it trains.
    labels = _hourly_labels(pd.Timestamp("2026-01-01 00:00"), 5 * 24)
    special = _custom_labels(
        [(pd.Timestamp("2026-01-02 20:00"), pd.Timestamp("2026-01-03 06:00"))]
    ).iloc[0]
    # Append the special label at the end (positional tail).
    labels = pd.concat([labels, special.to_frame().T], ignore_index=True)
    entry, exit_ = labels["entry_time"], labels["exit_time"]

    folds = calibration_folds(entry, exit_, test_days=2, train_days=2, embargo_bars=0)
    assert len(folds) == 2  # windows b=01-03 and b=01-05
    # Fold 0 = window b=01-03 (test_start 01-03): the special label is purged.
    assert len(entry) - 1 not in folds[0][0]
    # Fold 1 = window b=01-05 (test_start 01-05): the special label trains.
    assert len(entry) - 1 in folds[1][0]


@pytest.mark.unit
def test_folds_embargo_applied():
    # 15-minute entries over 5 days so the embargo window (exit within 15m of a
    # test_start, but resolved just before it) actually catches labels the
    # purge leaves in — proving the knob moves the boundary.
    labels = _freq_labels(pd.Timestamp("2026-01-01 00:00"), 5 * 24 * 4, freq="15min")
    entry, exit_ = labels["entry_time"], labels["exit_time"]
    folds_0 = calibration_folds(entry, exit_, test_days=2, train_days=2, embargo_bars=0)
    folds_1 = calibration_folds(entry, exit_, test_days=2, train_days=2, embargo_bars=1)

    assert folds_0 == _expected_folds(entry, exit_, 2, 2, 0)
    assert folds_1 == _expected_folds(entry, exit_, 2, 2, 1)
    assert len(folds_0) == len(folds_1)
    for (tr0, _), (tr1, _) in zip(folds_0, folds_1, strict=True):
        # Embargo strictly shrinks the train not just in count.
        assert set(tr1) < set(tr0)


@pytest.mark.unit
def test_folds_empty_entry_times_returns_empty_list():
    empty = pd.Series([], dtype="datetime64[us]")
    assert calibration_folds(empty, empty, test_days=2, train_days=2) == []


@pytest.mark.unit
def test_folds_reject_harness_invalid_days():
    labels = _hourly_labels(pd.Timestamp("2026-01-01 00:00"), 10)
    entry, exit_ = labels["entry_time"], labels["exit_time"]
    with pytest.raises(ValueError):
        calibration_folds(entry, exit_, test_days=0, train_days=2)
    with pytest.raises(ValueError):
        calibration_folds(entry, exit_, test_days=2, train_days=0)
