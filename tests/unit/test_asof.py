"""Unit tests for the point-in-time visibility helper (backtest.asof) — the
single anti-lookahead choke point. Pins both stamp kinds at boundary
equality, NaT exclusion, TF close-time math, and the invariant errors.
Conventions mirror test_mtf_join.py (@pytest.mark.unit, direct imports).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from ai_trading.backtest.asof import STAMP_BAR, STAMP_CLOSE, close_time_of, visible_mask

BAR_T = pd.Timestamp("2026-08-20 10:00:00")
CLOSE_T_M15 = pd.Timestamp("2026-08-20 10:15:00")
CLOSE_T_H4 = pd.Timestamp("2026-08-20 14:00:00")


def _frame(stamps) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "stamp": pd.Series(list(stamps), dtype="datetime64[us]"),
            "value": range(len(stamps)),
        }
    )


# ---------------------------------------------------------------------------
# Close-kind stamps (confirmed_at / created_at / activated_at)
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_close_stamp_at_close_time_is_visible():
    """A close-time stamp equal to close_t IS visible (<= anchor)."""
    df = _frame([CLOSE_T_M15])
    mask = visible_mask(df, "stamp", STAMP_CLOSE, BAR_T, CLOSE_T_M15)
    assert mask.tolist() == [True]


@pytest.mark.unit
def test_close_stamp_one_tf_before_close_is_visible():
    """A close-time stamp at bar_t is the PREVIOUS bar's confirmation (it
    completed a full TF before the decision close) and IS visible — a naive
    ``stamp <= t_S`` mental model confuses this boundary, while the pinned
    ``stamp <= close_t`` anchor includes it, and the decision bar's own
    confirmation (stamp == close_t) is visible too. Only stamps strictly
    after close_t are excluded."""
    df = _frame([BAR_T, CLOSE_T_M15, CLOSE_T_M15 + pd.Timedelta(minutes=15)])
    mask = visible_mask(df, "stamp", STAMP_CLOSE, BAR_T, CLOSE_T_M15)
    assert mask.tolist() == [True, True, False]


@pytest.mark.unit
def test_close_stamp_after_close_time_is_not_visible():
    df = _frame([CLOSE_T_M15 + pd.Timedelta(minutes=15)])
    mask = visible_mask(df, "stamp", STAMP_CLOSE, BAR_T, CLOSE_T_M15)
    assert mask.tolist() == [False]


# ---------------------------------------------------------------------------
# Bar-kind stamps (pierced_at / resolved_at / mitigated_at / invalidated_at)
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_bar_stamp_at_bar_time_is_visible():
    """A bar-time event stamped exactly at bar_t is known at that bar's
    close (bar-time anchors compare against bar_t, not close_t)."""
    df = _frame([BAR_T])
    mask = visible_mask(df, "stamp", STAMP_BAR, BAR_T, CLOSE_T_M15)
    assert mask.tolist() == [True]


@pytest.mark.unit
def test_bar_stamp_at_close_time_is_not_visible():
    """A bar-time stamp at close_t (one TF after bar_t) is NOT visible at
    bar_t — bar-kind and close-kind anchors are not interchangeable."""
    df = _frame([CLOSE_T_M15])
    mask = visible_mask(df, "stamp", STAMP_BAR, BAR_T, CLOSE_T_M15)
    assert mask.tolist() == [False]


# ---------------------------------------------------------------------------
# NaT / None exclusion + mixed frames
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_nat_stamps_never_visible():
    df = _frame([pd.NaT, BAR_T, pd.NaT, CLOSE_T_M15 + pd.Timedelta(minutes=15)])
    mask_close = visible_mask(df, "stamp", STAMP_CLOSE, BAR_T, CLOSE_T_M15)
    assert mask_close.tolist() == [False, True, False, False]
    mask_bar = visible_mask(df, "stamp", STAMP_BAR, BAR_T, CLOSE_T_M15)
    assert mask_bar.tolist() == [False, True, False, False]


# ---------------------------------------------------------------------------
# close_time_of
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_close_time_of_m15_and_h4():
    assert close_time_of(BAR_T, "M15") == CLOSE_T_M15
    assert close_time_of(BAR_T, "H4") == CLOSE_T_H4


@pytest.mark.unit
def test_close_time_of_passthrough_timestamp_types():
    """datetime and numpy datetime64 inputs pass through unchanged apart
    from the TF addition — no flooring, no tz conversion."""
    dt = close_time_of(pd.Timestamp("2026-08-20 10:00:00"), "M15")
    assert dt == CLOSE_T_M15 and isinstance(dt, pd.Timestamp)
    from datetime import datetime

    assert close_time_of(datetime(2026, 8, 20, 10, 0), "M15") == CLOSE_T_M15
    np_dt = close_time_of(np.datetime64("2026-08-20T10:00:00"), "H4")
    assert pd.Timestamp(np_dt) == CLOSE_T_H4


@pytest.mark.unit
def test_close_time_of_rejects_non_timestamp_scalars():
    """float/bool inputs are never silently coerced into timestamps."""
    with pytest.raises(TypeError):
        close_time_of(1.5, "M15")
    with pytest.raises(TypeError):
        close_time_of(True, "M15")


# ---------------------------------------------------------------------------
# Invariants + purity
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_missing_column_raises_invariant():
    df = _frame([CLOSE_T_M15])
    with pytest.raises(ValueError, match="invariant violated"):
        visible_mask(df, "nope", STAMP_CLOSE, BAR_T, CLOSE_T_M15)


@pytest.mark.unit
def test_unknown_stamp_kind_raises_invariant():
    df = _frame([CLOSE_T_M15])
    with pytest.raises(ValueError, match="invariant violated"):
        visible_mask(df, "stamp", "instant", BAR_T, CLOSE_T_M15)


@pytest.mark.unit
def test_input_frame_not_mutated_and_dtype_neutral():
    df = _frame([pd.NaT, BAR_T, CLOSE_T_M15, CLOSE_T_M15 + pd.Timedelta(minutes=15)])
    before = df.copy(deep=True)
    mask = visible_mask(df, "stamp", STAMP_CLOSE, BAR_T, CLOSE_T_M15)
    pd.testing.assert_frame_equal(before, df)
    assert mask.dtype == bool
    assert list(mask.index) == list(df.index)
