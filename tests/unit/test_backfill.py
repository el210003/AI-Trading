"""Unit tests (DATA-04): retry-until-stable range fetching, checkpoint-driven
idempotent backfill, injected-gap restoration, crash-between-write-and-
checkpoint convergence, and the forming-bar defensive trim — all against
FakeMT5Client (no terminal).

Consumes the conftest hooks built in plan 01-02: per-(symbol, timeframe)
response deques for per-round scripting and the calls list / per-method
counters for exact-argument assertions. No conftest changes needed.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from ai_trading.collector import (
    backfill_all,
    backfill_range,
    backfill_symbol_timeframe,
    fetch_range_until_stable,
    run_startup,
)
from ai_trading.mt5_client import MT5DataError
from ai_trading.normalize import TIMEFRAME_MINUTES, rates_to_dataframe
from ai_trading.stores import bar_store, meta_store

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

# Aligned to every TF grid; safely in the past so forming-bar checks pass.
SERVER_START = datetime(2026, 8, 28, 0, 0)
OFFSET = 3


def _epoch(naive_server_wall: datetime) -> int:
    return int(naive_server_wall.replace(tzinfo=UTC).timestamp())


def _rates(count: int, start: datetime = SERVER_START, minutes: int = 15) -> np.ndarray:
    """Structured rates array of `count` bars stepping `minutes` from `start`
    (naive server-wall, TF-aligned)."""
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
    return np.array(rows, dtype=RATES_DTYPE)


def _bars_df(count: int, start: datetime = SERVER_START, minutes: int = 15) -> pd.DataFrame:
    return rates_to_dataframe(_rates(count, start, minutes), "EURUSD", OFFSET)


def _backfill_cfg(make_cfg, tmp_path, **overrides):
    return make_cfg(
        bars_dir=tmp_path / "bars",
        meta_db=tmp_path / "meta" / "meta.sqlite",
        backfill_pause_seconds=0.0,  # no sleeping in unit tests
        **overrides,
    )


def _connect(cfg):
    return meta_store.connect(cfg.meta_db)


def _bar_path(cfg, symbol="EURUSD", timeframe="M15"):
    return bar_store.bar_path(Path(cfg.bars_dir), symbol, timeframe)


def _range_calls(fake) -> list[tuple[tuple, dict]]:
    return [call for name, call in fake.calls if name == "copy_rates_range"]


# ---------------------------------------------------------------------------
# fetch_range_until_stable (DATA-04 retry loop)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_returns_only_after_two_consecutive_equal_counts(fake_mt5):
    """Growing counts keep the loop going; the full array returns only once the
    count is stable across two consecutive rounds (officially sanctioned test)."""
    tf = fake_mt5.timeframe_enum("M15")
    fake_mt5.script_rates("EURUSD", tf, [_rates(5), _rates(10), _rates(10)])
    res = fetch_range_until_stable(
        "EURUSD", tf, SERVER_START, SERVER_START + timedelta(hours=1),
        client=fake_mt5, max_rounds=6, pause=0.0,
    )
    assert len(res) == 10
    assert fake_mt5.counts["copy_rates_range"] == 3  # grow, grow, stable


@pytest.mark.unit
def test_issues_identical_request_arguments_every_round(fake_mt5):
    """The retry loop must repeat the IDENTICAL request (recorded args show no
    variation across rounds)."""
    tf = fake_mt5.timeframe_enum("M15")
    fake_mt5.script_rates("EURUSD", tf, [_rates(5), _rates(10), _rates(10)])
    fetch_range_until_stable(
        "EURUSD", tf, SERVER_START, SERVER_START + timedelta(hours=1),
        client=fake_mt5, max_rounds=6, pause=0.0,
    )
    recorded = _range_calls(fake_mt5)
    assert len(recorded) == 3
    assert all(kwargs == {} for _args, kwargs in recorded)
    assert len({args for args, _kwargs in recorded}) == 1  # no variation
    assert next(iter({args for args, _k in recorded})) == (
        "EURUSD", tf, SERVER_START, SERVER_START + timedelta(hours=1)
    )


@pytest.mark.unit
def test_none_with_minus4_is_retried_not_raised(fake_mt5):
    """None + code -4 is the documented not-ready signal: retry (call count
    increases) until data arrives — never a crash."""
    fake_mt5.error_code, fake_mt5.error_msg = -4, "No history"
    tf = fake_mt5.timeframe_enum("M15")
    fake_mt5.script_rates("EURUSD", tf, [None, None, _rates(5), _rates(5)])
    res = fetch_range_until_stable(
        "EURUSD", tf, SERVER_START, SERVER_START + timedelta(hours=1),
        client=fake_mt5, max_rounds=8, pause=0.0,
    )
    assert len(res) == 5
    assert fake_mt5.counts["copy_rates_range"] == 4  # 2 None rounds + 2 stable rounds


@pytest.mark.unit
def test_none_with_other_code_raises_immediately(fake_mt5):
    fake_mt5.error_code, fake_mt5.error_msg = -6, "Authorization failed"
    tf = fake_mt5.timeframe_enum("M15")
    fake_mt5.script_rates("EURUSD", tf, [None])
    with pytest.raises(MT5DataError, match="-6"):
        fetch_range_until_stable(
            "EURUSD", tf, SERVER_START, SERVER_START + timedelta(hours=1),
            client=fake_mt5, max_rounds=5, pause=0.0,
        )
    assert fake_mt5.counts["copy_rates_range"] == 1  # no retry on non-(-4) codes


@pytest.mark.unit
def test_rounds_exhausted_raises_stabilization_error(fake_mt5):
    """Persistent None/-4 across all rounds exhausts the loop -> MT5DataError
    mentioning stabilization."""
    fake_mt5.error_code, fake_mt5.error_msg = -4, "No history"
    tf = fake_mt5.timeframe_enum("M15")
    with pytest.raises(MT5DataError, match="stabiliz"):
        fetch_range_until_stable(
            "EURUSD", tf, SERVER_START, SERVER_START + timedelta(hours=1),
            client=fake_mt5, max_rounds=3, pause=0.0,
        )
    assert fake_mt5.counts["copy_rates_range"] == 3


# ---------------------------------------------------------------------------
# checkpoint-driven restart backfill (DATA-04)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_checkpoint_restart_backfills_exactly_missing_tail(tmp_path, fake_mt5, make_cfg):
    """Checkpoint at bar 9, file holds bars 0..9; the range fetch returns bars
    10..29 -> final file holds exactly 30 unique sorted rows and the checkpoint
    advanced to bar 29."""
    cfg = _backfill_cfg(make_cfg, tmp_path, symbols=("EURUSD",), timeframes=("M15",))
    fake_mt5.set_rates(
        "EURUSD", fake_mt5.timeframe_enum("M15"),
        _rates(20, start=SERVER_START + timedelta(minutes=15 * 10)),
    )
    conn = _connect(cfg)
    try:
        path = _bar_path(cfg)
        seed = _bars_df(10)  # bars 0..9
        bar_store.merge_and_write(seed, path, "M15")
        meta_store.update_checkpoint(
            conn, "EURUSD", "M15", seed["time_utc"].max().isoformat(),
            "2026-08-30T00:00:00Z",
        )

        added = backfill_symbol_timeframe(cfg, conn, "EURUSD", "M15", fake_mt5)

        assert added == 20
        df = pd.read_parquet(path)
        assert len(df) == 30
        assert df["time"].is_unique
        assert df["time"].is_monotonic_increasing
        assert meta_store.get_checkpoint(conn, "EURUSD", "M15") == (
            df["time_utc"].max().isoformat()
        )
    finally:
        conn.close()


@pytest.mark.unit
def test_second_consecutive_backfill_adds_zero_rows(tmp_path, fake_mt5, make_cfg):
    """Restart idempotency: a second consecutive backfill run yields the same
    row count, zero duplicates, and zero rows added."""
    cfg = _backfill_cfg(make_cfg, tmp_path, symbols=("EURUSD",), timeframes=("M15",))
    fake_mt5.set_rates(
        "EURUSD", fake_mt5.timeframe_enum("M15"),
        _rates(20, start=SERVER_START + timedelta(minutes=15 * 10)),
    )
    conn = _connect(cfg)
    try:
        path = _bar_path(cfg)
        seed = _bars_df(10)
        bar_store.merge_and_write(seed, path, "M15")
        meta_store.update_checkpoint(
            conn, "EURUSD", "M15", seed["time_utc"].max().isoformat(),
            "2026-08-30T00:00:00Z",
        )

        first = backfill_symbol_timeframe(cfg, conn, "EURUSD", "M15", fake_mt5)
        count_after_first = len(pd.read_parquet(path))
        checkpoint_after_first = meta_store.get_checkpoint(conn, "EURUSD", "M15")

        second = backfill_symbol_timeframe(cfg, conn, "EURUSD", "M15", fake_mt5)

        assert first == 20
        assert second == 0  # idempotent: nothing new
        df = pd.read_parquet(path)
        assert len(df) == count_after_first == 30
        assert df["time"].is_unique
        assert meta_store.get_checkpoint(conn, "EURUSD", "M15") == checkpoint_after_first
    finally:
        conn.close()


@pytest.mark.unit
def test_backfill_range_restores_injected_mid_history_gap(tmp_path, fake_mt5, make_cfg):
    """Bars 0..9 and 20..29 stored (no checkpoint); a backfill_range across the
    full span restores exactly 30 unique rows — gap closed, no duplicates."""
    cfg = _backfill_cfg(make_cfg, tmp_path, symbols=("EURUSD",), timeframes=("M15",))
    fake_mt5.set_rates("EURUSD", fake_mt5.timeframe_enum("M15"), _rates(30))
    conn = _connect(cfg)
    try:
        path = _bar_path(cfg)
        head = _bars_df(10)  # bars 0..9
        tail = _bars_df(10, start=SERVER_START + timedelta(minutes=15 * 20))  # bars 20..29
        bar_store.merge_and_write(head, path, "M15")
        bar_store.merge_and_write(tail, path, "M15")
        assert len(pd.read_parquet(path)) == 20  # gap of 10 bars present

        added = backfill_range(
            cfg, conn, "EURUSD", "M15",
            head["time_utc"].min().to_pydatetime(),
            tail["time_utc"].max().to_pydatetime(),
            fake_mt5,
        )

        assert added == 10
        df = pd.read_parquet(path)
        assert len(df) == 30
        assert df["time"].is_unique
        # fully contiguous 15-minute series
        assert (df["time"].diff().dropna() == pd.Timedelta(minutes=15)).all()
    finally:
        conn.close()


@pytest.mark.unit
def test_crash_between_write_and_checkpoint_converges(tmp_path, fake_mt5, make_cfg):
    """File already holds bars 0..29 but the checkpoint was left one bar behind
    (crash between write and checkpoint): an overlap refetch adds zero rows yet
    re-advances the checkpoint — converging to the same unique-row set."""
    cfg = _backfill_cfg(make_cfg, tmp_path, symbols=("EURUSD",), timeframes=("M15",))
    fake_mt5.set_rates(
        "EURUSD", fake_mt5.timeframe_enum("M15"),
        _rates(20, start=SERVER_START + timedelta(minutes=15 * 10)),
    )
    conn = _connect(cfg)
    try:
        path = _bar_path(cfg)
        full = _bars_df(30)  # bars 0..29 already written
        bar_store.merge_and_write(full, path, "M15")
        # checkpoint one bar behind (crash simulation)
        meta_store.update_checkpoint(
            conn, "EURUSD", "M15", full["time_utc"].iloc[-2].isoformat(),
            "2026-08-30T00:00:00Z",
        )

        added = backfill_symbol_timeframe(cfg, conn, "EURUSD", "M15", fake_mt5)

        assert added == 0  # overlap only — nothing new
        df = pd.read_parquet(path)
        assert len(df) == 30
        assert df["time"].is_unique
        # checkpoint caught up to the file's max bar
        assert meta_store.get_checkpoint(conn, "EURUSD", "M15") == (
            full["time_utc"].max().isoformat()
        )
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# forming-bar defensive trim
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_forming_bar_trimmed_before_merge_not_by_guard(tmp_path, fake_mt5, make_cfg):
    """With a fixed now_utc, a scripted inclusive-range response containing a
    row AT the current timeframe floor is trimmed by backfill_range BEFORE
    merge: the stored file holds only closed bars and merge_and_write's guard
    never trips (the control proves the guard would have rejected the frame)."""
    fixed_now = datetime(2026, 8, 28, 12, 0, tzinfo=UTC)  # aware -> strip path exercised
    cfg = _backfill_cfg(make_cfg, tmp_path, symbols=("EURUSD",), timeframes=("M15",))
    # bars 0..29 (closed) PLUS the forming bar opening exactly at the floor
    # (server wall 15:00 == true UTC 12:00 == fixed_now's M15 floor).
    scripted = np.concatenate([_rates(30), _rates(1, start=datetime(2026, 8, 28, 15, 0))])
    fake_mt5.set_rates("EURUSD", fake_mt5.timeframe_enum("M15"), scripted)
    conn = _connect(cfg)
    try:
        added = backfill_range(
            cfg, conn, "EURUSD", "M15",
            datetime(2026, 8, 27, 21, 0),  # bar 0 true-UTC open
            datetime(2026, 8, 28, 12, 0),  # current floor (inclusive fetch)
            fake_mt5,
            now_utc=fixed_now,
        )

        assert added == 30  # the forming 31st row was trimmed, not stored
        df = pd.read_parquet(_bar_path(cfg))
        assert len(df) == 30
        assert df["time"].is_unique
        assert df["time_utc"].max() < pd.Timestamp("2026-08-28 12:00:00")
    finally:
        conn.close()

    # Control: untrimmed, merge_and_write's guard itself rejects the frame —
    # so the trim (not the guard) is what removed the row above.
    with pytest.raises(ValueError, match="closed-bar invariant"):
        bar_store.merge_and_write(
            rates_to_dataframe(scripted, "EURUSD", OFFSET),
            tmp_path / "bars" / "CONTROL_M15.parquet",
            "M15",
            now_utc=fixed_now,
        )


# ---------------------------------------------------------------------------
# backfill_all + run_startup orchestration
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_backfill_all_covers_every_combo(tmp_path, fake_mt5, make_cfg):
    cfg = _backfill_cfg(
        make_cfg, tmp_path,
        symbols=("EURUSD", "GBPUSD"), timeframes=("M15", "H1"),
    )
    for sym in cfg.symbols:
        for tf in cfg.timeframes:
            fake_mt5.set_rates(
                sym, fake_mt5.timeframe_enum(tf), _rates(5, minutes=TIMEFRAME_MINUTES[tf])
            )
    conn = _connect(cfg)
    try:
        result = backfill_all(cfg, conn, fake_mt5)
    finally:
        conn.close()

    assert set(result) == {"EURUSD_M15", "EURUSD_H1", "GBPUSD_M15", "GBPUSD_H1"}
    assert all(rows == 5 for rows in result.values())
    for sym in cfg.symbols:
        for tf in cfg.timeframes:
            df = pd.read_parquet(_bar_path(cfg, sym, tf))
            assert len(df) == 5 and df["time"].is_unique


@pytest.mark.unit
def test_run_startup_health_then_backfill(tmp_path, fake_mt5, make_cfg, caplog):
    """run_startup: health check -> (tick unavailable -> advisory, no crash) ->
    backfill stored files."""
    cfg = _backfill_cfg(make_cfg, tmp_path, symbols=("EURUSD",), timeframes=("M15",))
    fake_mt5.set_rates("EURUSD", fake_mt5.timeframe_enum("M15"), _rates(5))
    conn = _connect(cfg)
    try:
        with caplog.at_level(logging.WARNING):
            run_startup(cfg, conn, fake_mt5)  # tick None -> MT5DataError -> advisory
    finally:
        conn.close()
    assert (_bar_path(cfg)).exists()
    assert any("offset validation unavailable" in r.message for r in caplog.records)


@pytest.mark.unit
def test_run_startup_warns_on_offset_drift_only_when_it_differs(
    tmp_path, fake_mt5, make_cfg, caplog
):
    """A freshly validated offset != configured -> drift warning; equal -> none."""
    cfg = _backfill_cfg(make_cfg, tmp_path, symbols=("EURUSD",), timeframes=("M15",))
    fake_mt5.set_rates("EURUSD", fake_mt5.timeframe_enum("M15"), _rates(5))
    now_naive = datetime.now(UTC).replace(tzinfo=None)
    conn = _connect(cfg)
    try:
        # drifting sample: server wall = UTC+2 -> validates as 2 vs configured 3
        fake_mt5.script_tick("EURUSD", SimpleNamespace(time=_epoch(now_naive + timedelta(hours=2))))
        with caplog.at_level(logging.WARNING):
            run_startup(cfg, conn, fake_mt5)
        assert any("differs from configured" in r.message for r in caplog.records)

        # matching sample: server wall = UTC+3 -> validates as 3 -> no drift warning
        caplog.clear()
        fake_mt5.script_tick("EURUSD", SimpleNamespace(time=_epoch(now_naive + timedelta(hours=3))))
        with caplog.at_level(logging.WARNING):
            run_startup(cfg, conn, fake_mt5)
        assert not any("differs from configured" in r.message for r in caplog.records)
    finally:
        conn.close()
