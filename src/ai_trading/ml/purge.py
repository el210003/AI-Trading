"""Boundary purge + embargo over label exit stamps (OQ5 — the Phase 3 deferred
obligation, documented in backtest.walkforward's module docstring).

Phase 3's ``train_mask`` is ``entry_time < test_start`` (D-19) — it INCLUDES
labels whose outcome resolves INSIDE the test window. This module closes that
leak: for each test window k with test span starting ``test_start``, a train
label is kept only when its exit BAR's open time is strictly before
``test_start − embargo_bars × bar_minutes``.

The single keep-condition implements BOTH mechanics:

- With ``embargo_bars=0`` it is the mandatory purge: a label whose ``exit_time``
  is at or after ``test_start`` is DROPPED (its outcome resolves inside the
  test window), and an ``exit_time`` one bar before ``test_start`` is KEPT
  (the exit bar opens 15m earlier and closes exactly at the window start).
  ``exit_time`` is the exit bar's OPEN time (replay/barriers emit the bar open
  stamp), which is what makes both boundary sides exact.
- ``embargo_bars = N`` extends the cut N bars earlier as a serial-correlation
  guard (AFML ch. 7 adapted): the boundary drops train rows whose exit closes
  within N bars of the window start.

WHY THE EMBARGO DEFAULT IS 0: the 96-bar outcome barrier (``time_barrier_bars``)
means a label whose outcome resolves before the window start is the only one
eligible anyway — the purge already removes every overlapping label. Embargo
only guards regime continuity between the last pre-window bars and the window
itself, and it costs train depth on an already-tiny store; revisit after deep
history backfill. The knob is a config setting (``ml_embargo_bars``), not a
constant.

Contract: pure pandas, no I/O, no MetaTrader5 import, inputs NEVER mutated.
``train_mask`` and ``exit_times`` are positionally indexed series (callers pass
reset-index frames). NaN/NaT ``exit_times`` are conservatively excluded — an
undetermined outcome never trains.
"""

from __future__ import annotations

import pandas as pd


def purged_train_mask(
    train_mask: pd.Series,
    exit_times: pd.Series,
    test_start: pd.Timestamp,
    embargo_bars: int = 0,
    bar_minutes: int = 15,
) -> pd.Series:
    """Boolean Series aligned to ``train_mask``'s index — True where the row is
    in ``train_mask`` AND ``exit_time`` is not NaT AND ``exit_time`` is strictly
    before ``(test_start − embargo_bars × bar_minutes minutes)``.

    Args:
        train_mask: boolean Series over the training slice (expanding train
            mask from ``walkforward.build_windows``); the result is aligned to
            its index.
        exit_times: Series of the exit bar's OPEN time per row, aligned
            positionally to ``train_mask`` (reset-index frames).
        test_start: the test window's start stamp (window boundary b_k).
        embargo_bars: whole-bar serial-correlation buffer (default 0 = purge
            only).
        bar_minutes: minutes per bar for the embargo math (default M15 15).

    Returns:
        Boolean Series aligned to ``train_mask``'s index; ``False`` for every
        ``train_mask`` False row, every NaT ``exit_time`` row, and every row
        whose exit is at/after the (possibly embargo-extended) boundary.
    """
    embargo_min = int(embargo_bars) * int(bar_minutes)
    boundary = pd.Timestamp(test_start) - pd.Timedelta(minutes=embargo_min)

    train = pd.Series(train_mask)
    exits = pd.Series(exit_times).reindex(train.index)

    keep = exits.notna() & (exits < boundary) & train.astype(bool)
    return pd.Series(keep, index=train.index, dtype=bool)
