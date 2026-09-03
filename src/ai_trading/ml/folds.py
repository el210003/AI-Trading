"""Harness-derived calibration fold pairs (SC3 / AI-04).

``CalibratedClassifierCV`` needs an explicit ``cv`` iterable of
``(train_indices, test_indices)`` pairs. SC3 forbids ANY shuffled split (the
silent ``StratifiedKFold`` default inside the calibrator is a verified time-order
bug), so these pairs are derived EXCLUSIVELY from
``backtest.walkforward.build_windows`` — the splitter of record (D-19). No new
splitter is invented here; fold boundaries are positional projections of the
harness's Window ``train_mask``/``test_mask`` with the OQ5 purge applied.

Each fold pair is (expanding-train positions, sequential-test positions):
``train`` = the window's ``train_mask`` after ``purged_train_mask`` (every label
whose outcome resolves at/after the fold's test_start is dropped); ``test`` =
the window's ``test_mask`` positions. Only pairs where BOTH sides are non-empty
are returned — a leading window whose train is empty (expanding from data
start) or a trailing window with no test labels is a supported state, never an
error, mirroring the harness's zero-label contract.

CONTRACT: positions are 0-based positional indices into the (positionally
indexed) training slice — callers must pass reset-index frames. ``entry_times``
and ``exit_times`` are positionally aligned Series; empty ``entry_times`` yields
an empty list.

Pure pandas: no I/O, no MetaTrader5 import, inputs never mutated.
"""

from __future__ import annotations

import pandas as pd

from ai_trading.backtest.walkforward import build_windows
from ai_trading.ml.purge import purged_train_mask


def calibration_folds(
    entry_times: pd.Series,
    exit_times: pd.Series,
    test_days: int,
    train_days: int,
    embargo_bars: int = 0,
) -> list[tuple[list[int], list[int]]]:
    """Return expanding/sequential (train_positions, test_positions) pairs derived
    exclusively from ``walkforward.build_windows`` over ``entry_times``.

    Args:
        entry_times: positional Series of label entry-bar open times.
        exit_times: positional Series of label exit-bar open times, aligned to
            ``entry_times`` (same reset index).
        test_days: test-block length in days (forwarded to ``build_windows``).
        train_days: train length in days (retained as documented metadata by the
            harness — D-20; the train mask is expanding accumulation).
        embargo_bars: whole-bar purge buffer applied at every fold boundary.

    Returns:
        List of ``(train, test)`` positional index lists, chronological and
        non-overlapping. Raises the harness's own ``ValueError`` on invalid
        day values (test_days/train_days <= 0) — validation is never duplicated.
    """
    entry = entry_times if isinstance(entry_times, pd.Series) else pd.Series(entry_times)
    exits = exit_times
    if not isinstance(exits, pd.Series):
        exits = pd.Series(exits, index=entry.index)
    exits = exits.reindex(entry.index)

    windows = build_windows(entry, test_days=test_days, train_days=train_days)
    folds: list[tuple[list[int], list[int]]] = []
    for w in windows:
        tr = purged_train_mask(w.train_mask, exits, w.test_start, embargo_bars)
        tr_pos = tr.to_numpy().nonzero()[0].tolist()
        te_pos = w.test_mask.to_numpy().nonzero()[0].tolist()
        if tr_pos and te_pos:
            folds.append((tr_pos, te_pos))
    return folds
