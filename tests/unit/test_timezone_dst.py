"""Timezone/DST validation tests (DATA-03, roadmap deliverable): lock the
project's time-semantics contract — raw server time preserved, offset
re-derivable, boundary alignment preserved by normalization, DST-transition
misalignment detected, weekend gaps reported not raised, and the offset-drift
predicate. All MT5-free (shared pattern #7).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import numpy as np
import pandas as pd
import pytest

from ai_trading.collector import offset_drift_detected
from ai_trading.history_report import classify_gap, compute_gaps
from ai_trading.normalize import TIMEFRAME_MINUTES, rates_to_dataframe, rederive_time_utc

SYMBOL = "EURUSD"

# MT5 copy_rates* structured-array dtype (time = epoch seconds of server wall time).
RATES_DTYPE = [
    ("time", "int64"),
    ("open", "float64"),
    ("high", "float64"),
    ("low", "float64"),
    ("close", "float64"),
    ("tick_volume", "int64"),
    ("spread", "int64"),
    ("real_volume", "float64"),
]

SERVER_START = datetime(2026, 8, 28, 0, 0)  # server wall, aligned to all TF grids


def _epoch(naive_server_wall: datetime) -> int:
    return int(naive_server_wall.replace(tzinfo=UTC).timestamp())


def _bars(count: int, start: datetime = SERVER_START, minutes: int = 15, offset: int = 3):
    """Canonical bar frame: `count` bars stepping `minutes` from `start`
    (server wall) normalized with `offset`."""
    rows = [
        (
            _epoch(start + timedelta(minutes=minutes * i)),
            1.10000 + 0.00010 * i,
            1.20000 + 0.00010 * i,
            1.00000 + 0.00010 * i,
            1.15000 + 0.00010 * i,
            10 + i,
            2,
            0,
        )
        for i in range(count)
    ]
    return rates_to_dataframe(np.array(rows, dtype=RATES_DTYPE), SYMBOL, offset)


# ---------------------------------------------------------------------------
# (a) offset re-derivation semantics: only time_utc moves, raw is identical
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_offset_two_vs_three_shifts_utc_by_exactly_one_hour():
    df2 = _bars(8, offset=2)
    df3 = _bars(8, offset=3)
    # raw server wall time identical under both offsets
    assert df2["time"].equals(df3["time"])
    # time_utc differs by exactly one hour everywhere (a larger offset shifts
    # true UTC EARLIER, since time_utc = raw - offset)
    diff = df3["time_utc"] - df2["time_utc"]
    assert (diff == -pd.Timedelta(hours=1)).all()
    # and each time_utc = raw - offset
    assert (df2["time_utc"] == df2["time"] - pd.Timedelta(hours=2)).all()
    assert (df3["time_utc"] == df3["time"] - pd.Timedelta(hours=3)).all()


# ---------------------------------------------------------------------------
# (b) rederive_time_utc: matches a fresh normalization, raw byte-identical
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_rederive_matches_fresh_normalize_and_preserves_raw():
    from conftest import make_bars

    stale = make_bars(SYMBOL, "M15", SERVER_START, 12, offset_hours=3)  # stored under 3
    rederived = rederive_time_utc(stale, old_offset=3, new_offset=2)
    fresh = make_bars(SYMBOL, "M15", SERVER_START, 12, offset_hours=2)  # fresh normalize at 2

    assert rederived["time_utc"].equals(fresh["time_utc"])  # identical to fresh
    assert rederived["time"].equals(stale["time"])  # raw column byte-identical
    assert str(rederived["time"].dtype) == str(stale["time"].dtype)
    # a fresh copy was returned — the input frame is untouched
    assert (stale["time_utc"] == stale["time"] - pd.Timedelta(hours=3)).all()


# ---------------------------------------------------------------------------
# (c) boundary alignment: normalization preserves the timeframe's UTC grid
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_time_utc_lands_on_boundary_grid_for_every_timeframe():
    """Normalization preserves bar-open alignment: every time_utc lands on the
    timeframe's boundary grid as expressed in true UTC. The UTC grid is the
    server grid shifted by the broker offset (minutes-since-midnight UTC ==
    (-offset*60) mod TF). For M15/H1 at offset 3 this reduces to plain
    minutes-since-midnight mod TF == 0; for H4 it encodes the broker's
    21:00-UTC daily-close anchor — the grid independently corroborated live in
    plan 01-02 ({1,5,9,13,17,21}-hour UTC bars)."""
    offset = 3
    for tf, minutes in TIMEFRAME_MINUTES.items():
        expected_remainder = (-(offset * 60)) % minutes
        df = _bars(12, start=SERVER_START, minutes=minutes, offset=offset)
        for ts in df["time_utc"]:
            minutes_since_midnight = ts.hour * 60 + ts.minute
            assert minutes_since_midnight % minutes == expected_remainder, (
                f"{tf}: time_utc {ts} is off the {minutes}-minute boundary grid "
                f"(expected remainder {expected_remainder} at offset {offset})"
            )


# ---------------------------------------------------------------------------
# (d) DST-transition week: stale-offset misalignment is detectable — and why
#     the offset must be re-validated at startup and corrected by re-derivation
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_dst_transition_flags_misaligned_rows_and_rederivation_fixes_them():
    """Broker offset changes 2->3 mid-series (US DST begins; per the confirmed
    IC Markets policy). A collector normalizing the raw column with the STALE
    constant offset 2 stamps every post-transition bar +1h away from its true
    UTC open. The expected-open boundary check FLAGS exactly those rows; the
    naive :15-grid check does NOT (documenting why grid alignment alone cannot
    catch drift); per-row re-derivation realigns everything; and a stored file
    written entirely under the stale offset is fixed by rederive_time_utc."""
    true_opens = pd.date_range("2026-08-24 00:00", periods=480, freq="15min")  # Mon-Fri
    transition_at = 240  # offset changes 2->3 after Mon+Tue (Wed 00:00 UTC)
    offsets = np.array([2] * transition_at + [3] * (480 - transition_at))
    raw = pd.DatetimeIndex(true_opens) + pd.to_timedelta(offsets, unit="h")  # server wall

    # stale collector: one configured offset (2) applied to the whole column
    stale_utc = raw - pd.Timedelta(hours=2)
    misaligned = stale_utc != pd.DatetimeIndex(true_opens)

    # the boundary check against expected true opens FLAGS exactly the
    # post-transition rows
    assert list(np.flatnonzero(misaligned)) == list(range(transition_at, 480))

    # the naive grid-membership check passes on ALL rows including the
    # misaligned ones — offset drift is invisible to alignment alone, hence
    # the startup re-validation obligation
    grid_ok = ((stale_utc.hour * 60 + stale_utc.minute) % 15 == 0)
    assert grid_ok.all()

    # per-row re-derivation with the true (per-bar) offsets realigns everything
    fixed_utc = raw - pd.to_timedelta(offsets, unit="h")
    assert (fixed_utc == pd.DatetimeIndex(true_opens)).all()

    # a stored file holding ONLY post-transition bars (all written under the
    # stale offset 2) is corrected wholesale by rederive_time_utc
    stored = pd.DataFrame(
        {
            "time": raw[transition_at:],
            "time_utc": stale_utc[transition_at:],
        }
    )
    corrected = rederive_time_utc(stored, old_offset=2, new_offset=3)
    assert (
        corrected["time_utc"].equals(pd.Series(true_opens[transition_at:]))
    )
    assert corrected["time"].equals(stored["time"])  # raw preserved


# ---------------------------------------------------------------------------
# (e) weekend handling: gaps reported and classified, never raised
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_weekend_gap_reported_and_classified_not_raised():
    friday = _bars(84, start=datetime(2026, 8, 28, 3, 0))  # true-UTC Fri 00:00 -> 20:45
    sunday = _bars(4, start=datetime(2026, 8, 31, 0, 0))  # true-UTC Sun 21:00 -> 22:45
    df = pd.concat([friday, sunday], ignore_index=True)

    gaps = compute_gaps(df, "M15")  # must not raise

    assert len(gaps) == 1
    gap_start, gap_end = gaps[0]
    span_hours = (gap_end - gap_start).total_seconds() / 3600.0
    assert 47 <= span_hours <= 49  # one weekend-sized hole
    assert classify_gap(gap_start, gap_end) == "weekend"


# ---------------------------------------------------------------------------
# (f) offset drift predicate (the startup re-validation trigger)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_offset_drift_detected_flags_only_real_drift(make_cfg):
    cfg = make_cfg(broker_offset_hours=3)
    assert offset_drift_detected(cfg, 2) is True  # freshly validated differs
    assert offset_drift_detected(cfg, 3) is False  # matches configured
