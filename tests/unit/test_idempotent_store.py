"""Unit tests (DATA-04): idempotent + atomic Parquet bar store and the
SQLite WAL meta store. Uses the make_bars factory — zero MT5 dependency."""

from datetime import UTC, datetime

import pandas as pd
import pytest

from ai_trading.normalize import COLUMNS
from ai_trading.stores.bar_store import bar_path, merge_and_write, read_bars
from ai_trading.stores.meta_store import (
    connect,
    get_checkpoint,
    get_gaps,
    get_history_bounds,
    update_checkpoint,
    upsert_gaps,
    upsert_history_bounds,
)

# Well in the past relative to any realistic `now_utc`; 2026-08-20 00:00 is M15-aligned.
START = datetime(2026, 8, 20, 0, 0)
NOW_UTC = datetime(2026, 8, 30, 12, 0, tzinfo=UTC)  # aware clock -> tz-stripped for naive compare


# ---------------------------------------------------------------------------
# bar_store: idempotent merge + atomic write
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_bar_path_layout(tmp_path):
    p = bar_path(tmp_path / "bars", "EURUSD", "M15")
    assert p == tmp_path / "bars" / "EURUSD_M15.parquet"


@pytest.mark.unit
def test_read_bars_missing_returns_empty_canonical_frame(tmp_path):
    df = read_bars(tmp_path / "nope" / "EURUSD_M15.parquet")
    assert df.empty
    assert list(df.columns) == COLUMNS


@pytest.mark.unit
def test_fresh_write_creates_file_with_expected_rows_and_columns(tmp_path):
    path = bar_path(tmp_path, "EURUSD", "M15")
    new = _bars(10)
    n = merge_and_write(new, path, "M15", now_utc=NOW_UTC)
    assert n == 10
    assert path.exists()
    stored = read_bars(path)
    assert len(stored) == 10
    assert list(stored.columns) == COLUMNS


@pytest.mark.unit
def test_writing_identical_frame_twice_is_idempotent(tmp_path):
    path = bar_path(tmp_path, "EURUSD", "M15")
    new = _bars(10)
    merge_and_write(new, path, "M15", now_utc=NOW_UTC)
    first = read_bars(path)
    n = merge_and_write(new, path, "M15", now_utc=NOW_UTC)
    second = read_bars(path)
    assert n == len(first) == len(second) == 10
    pd.testing.assert_frame_equal(first, second)


@pytest.mark.unit
def test_overlap_refetch_with_revised_bar_wins_keep_last(tmp_path):
    path = bar_path(tmp_path, "EURUSD", "M15")
    stored = _bars(10)  # bars 0..9
    merge_and_write(stored, path, "M15", now_utc=NOW_UTC)

    refetch = _bars(15, start=START).iloc[5:].reset_index(drop=True)  # bars 5..14
    revised_time = refetch.loc[0, "time"]
    refetch.loc[0, "close"] = 5.55555  # broker revision on an overlapping bar
    n = merge_and_write(refetch, path, "M15", now_utc=NOW_UTC)

    final = read_bars(path)
    assert n == len(final) == 15  # bars 0..14, no duplicates
    assert final.loc[final["time"] == revised_time, "close"].item() == 5.55555  # keep="last" wins
    assert final["time"].is_monotonic_increasing  # sorted ascending


@pytest.mark.unit
def test_no_tmp_file_remains_after_successful_merge(tmp_path):
    path = bar_path(tmp_path, "EURUSD", "M15")
    merge_and_write(_bars(5), path, "M15", now_utc=NOW_UTC)
    assert list(tmp_path.glob("*.tmp")) == []


@pytest.mark.unit
def test_forming_bar_guard_raises_value_error(tmp_path):
    path = bar_path(tmp_path, "EURUSD", "M15")
    # offset 3: server 03:00..03:45 -> time_utc 00:00..00:45
    forming = _bars(4, start=datetime(2026, 8, 29, 3, 0))
    # now_utc 00:30 -> M15 floor 00:30; max time_utc 00:45 is at/after the floor
    with pytest.raises(ValueError, match="closed-bar invariant violated"):
        merge_and_write(forming, path, "M15", now_utc=datetime(2026, 8, 29, 0, 30, tzinfo=UTC))
    # one minute after the boundary the bars are all closed -> merge succeeds
    n = merge_and_write(forming, path, "M15", now_utc=datetime(2026, 8, 29, 1, 0, tzinfo=UTC))
    assert n == 4


def _bars(count: int, start: datetime = START) -> pd.DataFrame:
    from conftest import make_bars

    return make_bars("EURUSD", "M15", start, count, offset_hours=3)


# ---------------------------------------------------------------------------
# meta_store: WAL, checkpoints, bounds, gaps
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_connect_enables_wal_and_creates_tables(tmp_path):
    conn = connect(tmp_path / "meta" / "meta.sqlite")
    assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
    names = {
        r[0]
        for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    }
    assert {"collection_state", "history_bounds", "bar_gaps"} <= names
    conn.close()


@pytest.mark.unit
def test_checkpoint_roundtrip_and_single_row_per_key(tmp_path):
    conn = connect(tmp_path / "meta.sqlite")
    assert get_checkpoint(conn, "EURUSD", "M15") is None
    update_checkpoint(conn, "EURUSD", "M15", "2026-08-29T21:00:00", "2026-08-29T21:00:05")
    assert get_checkpoint(conn, "EURUSD", "M15") == "2026-08-29T21:00:00"
    update_checkpoint(conn, "EURUSD", "M15", "2026-08-29T21:15:00", "2026-08-29T21:15:03")
    assert get_checkpoint(conn, "EURUSD", "M15") == "2026-08-29T21:15:00"
    rows = conn.execute(
        "SELECT COUNT(*) FROM collection_state WHERE symbol = ? AND timeframe = ?",
        ("EURUSD", "M15"),
    ).fetchone()[0]
    assert rows == 1  # exactly one row per (symbol, timeframe) after repeated upserts
    conn.close()


@pytest.mark.unit
def test_history_bounds_roundtrip_includes_terminal_maxbars(tmp_path):
    conn = connect(tmp_path / "meta.sqlite")
    assert get_history_bounds(conn, "GBPUSD", "H1") is None
    upsert_history_bounds(
        conn, "GBPUSD", "H1", "2024-01-01T00:00:00", "2026-08-29T21:00:00", 24000, 100000,
        "2026-08-30T00:00:00",
    )
    got = get_history_bounds(conn, "GBPUSD", "H1")
    assert got is not None
    assert got["first_bar_utc"] == "2024-01-01T00:00:00"
    assert got["bar_count"] == 24000
    assert got["terminal_maxbars"] == 100000
    # second upsert overwrites the single row for the key
    upsert_history_bounds(
        conn, "GBPUSD", "H1", "2023-06-01T00:00:00", "2026-08-29T22:00:00", 26000, 100000,
        "2026-08-30T01:00:00",
    )
    got2 = get_history_bounds(conn, "GBPUSD", "H1")
    assert got2 is not None and got2["bar_count"] == 26000
    rows = conn.execute("SELECT COUNT(*) FROM history_bounds").fetchone()[0]
    assert rows == 1
    conn.close()


@pytest.mark.unit
def test_upsert_gaps_twice_same_key_no_duplicates(tmp_path):
    conn = connect(tmp_path / "meta.sqlite")
    gaps = [
        ("2026-08-22T21:00:00", "2026-08-23T21:00:00"),
        ("2026-08-25T21:00:00", "2026-08-26T00:00:00"),
    ]
    upsert_gaps(conn, "USDJPY", "H1", gaps, "2026-08-30T00:00:00")
    # re-detect the first gap with an extended end -> insert-or-replace, no dup row
    upsert_gaps(
        conn,
        "USDJPY",
        "H1",
        [("2026-08-22T21:00:00", "2026-08-23T22:00:00")],
        "2026-08-30T01:00:00",
    )
    stored = get_gaps(conn, "USDJPY", "H1")
    assert len(stored) == 2
    assert ("2026-08-22T21:00:00", "2026-08-23T22:00:00") in stored
    assert ("2026-08-25T21:00:00", "2026-08-26T00:00:00") in stored
    conn.close()
