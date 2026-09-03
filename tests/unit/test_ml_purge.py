"""Unit tests for the OQ5 boundary purge over label exit stamps (AI-04).

Named tests pin BOTH boundary cases of the purge and the embargo knob:

- ``test_purge_drops_exit_at_test_start``: a label whose ``exit_time`` equals
  the test-window start is DROPPED — its outcome resolves inside the window.
- ``test_purge_keeps_exit_closing_at_test_start``: an ``exit_time`` one bar
  before the start (the exit bar's open 15m earlier, closing exactly at the
  window start) is KEPT with embargo 0 — ``exit_time`` is the exit bar's OPEN
  time, which is what makes both boundary sides exact.
- ``test_purge_embargo_extends_boundary``: ``embargo_bars`` moves the boundary
  EARLIER by whole bars (embargo 1 drops the 15m-prior row; embargo 2 drops the
  30m-prior row too).
- ``test_purge_preserves_mask_alignment_and_inputs``: result aligned to the
  input index; non-train rows stay False; inputs never mutated.
- ``test_purge_nat_exit_excluded``: a NaT ``exit_time`` row never trains.

No MetaTrader5 import anywhere.
"""

from __future__ import annotations

import pandas as pd
import pytest
from _ml_fixtures import make_labels

from ai_trading.ml.purge import purged_train_mask

TF_MIN = 15


def _labels(entry_times: list[pd.Timestamp], exit_times: list[pd.Timestamp]) -> pd.DataFrame:
    """Label frame (replay.LABEL_COLUMNS) over the given entry/exit stamps; the
    returned frame is positionally indexed (0-based) so the entry/exit columns
    extract as positional series — the purge/folds reset-index contract."""
    rows = [
        {
            "symbol": "EURUSD",
            "timeframe": "M15",
            "direction": "long",
            "entry_time": e,
            "exit_time": x,
        }
        for e, x in zip(entry_times, exit_times)
    ]
    return make_labels(rows)


@pytest.mark.unit
def test_purge_drops_exit_at_test_start():
    test_start = pd.Timestamp("2026-01-02 00:00")
    labels = _labels(
        [
            pd.Timestamp("2026-01-01 08:00"),
            pd.Timestamp("2026-01-01 12:00"),
            pd.Timestamp("2026-01-01 23:00"),
            pd.Timestamp("2026-01-02 00:00"),
        ],
        [
            pd.Timestamp("2026-01-01 08:00"),  # before start -> keep
            pd.Timestamp("2026-01-01 12:00"),  # before start -> keep
            test_start,  # exit == test_start -> dropped (boundary)
            pd.Timestamp("2026-01-02 01:00"),  # after start -> dropped
        ],
    )
    train_mask = pd.Series(True, index=labels.index)
    keep = purged_train_mask(train_mask, labels["exit_time"], test_start, 0, TF_MIN)
    assert bool(keep.iloc[0]) and bool(keep.iloc[1])
    assert not bool(keep.iloc[2]) and not bool(keep.iloc[3])


@pytest.mark.unit
def test_purge_keeps_exit_closing_at_test_start():
    test_start = pd.Timestamp("2026-01-02 00:00")
    labels = _labels(
        [
            pd.Timestamp("2026-01-01 23:45"),
            pd.Timestamp("2026-01-01 23:30"),
        ],
        [
            test_start - pd.Timedelta(minutes=TF_MIN),  # exit bar opens 15m before, closes at start -> keep
            test_start - pd.Timedelta(minutes=2 * TF_MIN),  # clearly before -> keep
        ],
    )
    train_mask = pd.Series(True, index=labels.index)
    keep = purged_train_mask(train_mask, labels["exit_time"], test_start, 0, TF_MIN)
    assert list(keep) == [True, True]


@pytest.mark.unit
def test_purge_embargo_extends_boundary():
    test_start = pd.Timestamp("2026-01-02 00:00")
    labels = _labels(
        [
            pd.Timestamp("2026-01-01 23:45"),
            pd.Timestamp("2026-01-01 23:30"),
            pd.Timestamp("2026-01-01 23:29"),
        ],
        [
            test_start - pd.Timedelta(minutes=TF_MIN),  # 1 bar before
            test_start - pd.Timedelta(minutes=2 * TF_MIN),  # 2 bars before
            test_start - pd.Timedelta(minutes=2 * TF_MIN + 1),  # 2 bars + 1min before
        ],
    )
    train_mask = pd.Series(True, index=labels.index)
    r0 = purged_train_mask(train_mask, labels["exit_time"], test_start, 0, TF_MIN)
    r1 = purged_train_mask(train_mask, labels["exit_time"], test_start, 1, TF_MIN)
    r2 = purged_train_mask(train_mask, labels["exit_time"], test_start, 2, TF_MIN)
    assert list(r0) == [True, True, True]
    # embargo 1: the 15m-prior row (closing exactly at start) drops.
    assert list(r1) == [False, True, True]
    # embargo 2: the 30m-prior row drops too; the one 1min beyond stays.
    assert list(r2) == [False, False, True]


@pytest.mark.unit
def test_purge_preserves_mask_alignment_and_inputs():
    test_start = pd.Timestamp("2026-01-02 00:00")
    labels = _labels(
        [
            pd.Timestamp("2026-01-01 08:00"),
            pd.Timestamp("2026-01-01 09:00"),
            pd.Timestamp("2026-01-01 10:00"),
            pd.Timestamp("2026-01-01 11:00"),
        ],
        [
            pd.Timestamp("2026-01-01 08:30"),
            pd.Timestamp("2026-01-01 09:30"),
            pd.Timestamp("2026-01-01 10:30"),
            pd.Timestamp("2026-01-01 11:30"),
        ],
    )
    train_mask = pd.Series([True, False, True, True], index=labels.index)
    train_before = train_mask.copy()
    exit_before = labels["exit_time"].copy()
    keep = purged_train_mask(train_mask, labels["exit_time"], test_start, 0, TF_MIN)
    assert keep.index.equals(train_mask.index)
    # The False train row stays False even though its exit is before the start.
    assert not bool(keep.iloc[1])
    assert bool(keep.iloc[0]) and bool(keep.iloc[2]) and bool(keep.iloc[3])
    # Inputs never mutated.
    pd.testing.assert_series_equal(train_mask, train_before)
    pd.testing.assert_series_equal(labels["exit_time"], exit_before)


@pytest.mark.unit
def test_purge_nat_exit_excluded():
    test_start = pd.Timestamp("2026-01-02 00:00")
    labels = _labels(
        [
            pd.Timestamp("2026-01-01 08:00"),
            pd.Timestamp("2026-01-01 09:00"),
        ],
        [
            pd.NaT,  # undetermined outcome -> never trains
            test_start - pd.Timedelta(minutes=TF_MIN),
        ],
    )
    train_mask = pd.Series(True, index=labels.index)
    keep = purged_train_mask(train_mask, labels["exit_time"], test_start, 0, TF_MIN)
    assert not bool(keep.iloc[0])
    assert bool(keep.iloc[1])
