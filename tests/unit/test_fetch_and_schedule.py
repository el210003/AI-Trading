"""Unit tests (DATA-02/03): closed-bar fetch, poll scheduling, incremental
cycle, and empirical offset validation — all against FakeMT5Client (no
terminal). Proves the pos=1 invariant, write-then-checkpoint ordering,
checkpoint-filtered idempotency, and the offset-validation sign convention.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

import ai_trading.collector as collector_module
from ai_trading.collector import (
    fetch_closed_bars,
    offset_drift_detected,
    run_poll_cycle,
    seconds_until_next_close,
    validate_offset,
)
from ai_trading.mt5_client import MT5DataError
from ai_trading.normalize import COLUMNS, TIMEFRAME_MINUTES
from ai_trading.stores import bar_store, meta_store

SYMBOLS = ("EURUSD", "GBPUSD", "USDJPY")
TFS = ("M15", "H1", "H4")

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

# Aligned to every TF grid; safely in the past so the forming-bar guard passes.
SERVER_START = datetime(2026, 8, 28, 0, 0)
OFFSET = 3


def _epoch(naive_server_wall: datetime) -> int:
    return int(naive_server_wall.replace(tzinfo=UTC).timestamp())


def _rates_for(timeframe: str, count: int, start: datetime = SERVER_START) -> np.ndarray:
    step = TIMEFRAME_MINUTES[timeframe]
    rows = [
        (
            _epoch(start + timedelta(minutes=step * i)),
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


def _script_all_combos(fake, count: int = 5) -> None:
    for sym in SYMBOLS:
        for tf in TFS:
            fake.set_rates(sym, fake.timeframe_enum(tf), _rates_for(tf, count))


# ---------------------------------------------------------------------------
# fetch_closed_bars (DATA-02)
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_fetch_uses_start_pos_1_exactly(fake_mt5, make_cfg):
    """The invariant test: the forming bar at position 0 is never requested."""
    fake_mt5.set_rates("EURUSD", fake_mt5.timeframe_enum("M15"), _rates_for("M15", 3))
    cfg = make_cfg(lookback_bars=500)
    fetch_closed_bars(cfg, "EURUSD", "M15", fake_mt5)
    calls = [call for name, call in fake_mt5.calls if name == "copy_rates_from_pos"]
    tf_enum = fake_mt5.timeframe_enum("M15")
    assert calls == [(("EURUSD", tf_enum, 1, 500), {})]  # start_pos is literally 1


@pytest.mark.unit
def test_fetch_none_rates_raise_data_error_with_code(fake_mt5, make_cfg):
    fake_mt5.error_code, fake_mt5.error_msg = -4, "No history"
    with pytest.raises(MT5DataError) as excinfo:  # nothing scripted -> None
        fetch_closed_bars(make_cfg(), "EURUSD", "M15", fake_mt5)
    msg = str(excinfo.value)
    assert "-4" in msg and "No history" in msg  # last_error embedded, not silent skip
    assert "start_pos=1" in msg


@pytest.mark.unit
def test_fetch_empty_rates_raise_data_error(fake_mt5, make_cfg):
    fake_mt5.error_code, fake_mt5.error_msg = -4, "No history"
    fake_mt5.set_rates("EURUSD", fake_mt5.timeframe_enum("M15"), np.array([], dtype=RATES_DTYPE))
    with pytest.raises(MT5DataError):
        fetch_closed_bars(make_cfg(), "EURUSD", "M15", fake_mt5)


@pytest.mark.unit
def test_fetch_frame_columns_raw_time_and_utc(fake_mt5, make_cfg):
    fake_mt5.set_rates("EURUSD", fake_mt5.timeframe_enum("M15"), _rates_for("M15", 3))
    df = fetch_closed_bars(make_cfg(broker_offset_hours=OFFSET), "EURUSD", "M15", fake_mt5)
    assert list(df.columns) == COLUMNS
    assert (df["symbol"] == "EURUSD").all()
    assert df.loc[0, "time"] == pd.Timestamp("2026-08-28 00:00:00")  # raw preserved
    assert df.loc[0, "time_utc"] == pd.Timestamp("2026-08-27 21:00:00")  # time - offset
    assert df["time"].dt.tz is None and df["time_utc"].dt.tz is None


# ---------------------------------------------------------------------------
# seconds_until_next_close (DATA-02 scheduling)
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_boundary_returns_delay_only():
    boundary = datetime(2026, 8, 27, 12, 15)
    assert seconds_until_next_close("M15", boundary, 3) == 3.0


@pytest.mark.unit
def test_mid_interval_returns_remainder_plus_delay():
    mid = datetime(2026, 8, 27, 12, 7, 30)
    assert seconds_until_next_close("M15", mid, 3) == pytest.approx(7 * 60 + 30 + 3)


@pytest.mark.unit
def test_h1_boundary_and_mid_interval():
    assert seconds_until_next_close("H1", datetime(2026, 8, 27, 12, 0), 5) == 5.0
    assert seconds_until_next_close("H1", datetime(2026, 8, 27, 12, 30), 5) == 30 * 60 + 5


@pytest.mark.unit
def test_aware_now_utc_is_stripped():
    aware = datetime(2026, 8, 27, 12, 15, tzinfo=UTC)
    assert seconds_until_next_close("M15", aware, 3) == 3.0


@pytest.mark.unit
def test_minimum_zero_at_boundary_with_zero_delay():
    assert seconds_until_next_close("M15", datetime(2026, 8, 27, 12, 15), 0) == 0.0


# ---------------------------------------------------------------------------
# run_poll_cycle (DATA-02 incremental storage)
# ---------------------------------------------------------------------------

def _poll_cfg(make_cfg, tmp_path, **overrides):
    return make_cfg(
        bars_dir=tmp_path / "bars",
        meta_db=tmp_path / "meta" / "meta.sqlite",
        **overrides,
    )


@pytest.mark.unit
def test_poll_cycle_without_checkpoint_stores_all_rows(tmp_path, fake_mt5, make_cfg):
    _script_all_combos(fake_mt5)
    cfg = _poll_cfg(make_cfg, tmp_path)
    conn = meta_store.connect(cfg.meta_db)
    try:
        assert run_poll_cycle(cfg, conn, fake_mt5) == 9 * 5
    finally:
        conn.close()
    df = pd.read_parquet(bar_store.bar_path(cfg.bars_dir, "EURUSD", "M15"))
    assert len(df) == 5


@pytest.mark.unit
def test_poll_cycle_checkpoint_filter_update_and_idempotency(tmp_path, fake_mt5, make_cfg):
    """Pre-seeded checkpoint: only strictly-newer time_utc rows are stored;
    the checkpoint advances to the max stored time_utc; a second identical
    cycle stores 0 new rows."""
    _script_all_combos(fake_mt5)
    cfg = _poll_cfg(make_cfg, tmp_path)
    conn = meta_store.connect(cfg.meta_db)
    try:
        # seed checkpoint at the 3rd bar's time_utc (server 00:30 -> utc 21:30)
        meta_store.update_checkpoint(
            conn, "EURUSD", "M15", "2026-08-27T21:30:00", "2026-08-27T22:00:00Z"
        )
        stored = run_poll_cycle(cfg, conn, fake_mt5)
        assert stored == 2 + 8 * 5  # 2 new (21:45, 22:00) + 5 each for the other 8
        assert meta_store.get_checkpoint(conn, "EURUSD", "M15") == "2026-08-27T22:00:00"

        df = pd.read_parquet(bar_store.bar_path(cfg.bars_dir, "EURUSD", "M15"))
        assert list(df["time_utc"]) == [
            pd.Timestamp("2026-08-27 21:45:00"),
            pd.Timestamp("2026-08-27 22:00:00"),
        ]

        # second identical cycle: everything already <= checkpoint -> 0 new
        assert run_poll_cycle(cfg, conn, fake_mt5) == 0
        df2 = pd.read_parquet(bar_store.bar_path(cfg.bars_dir, "EURUSD", "M15"))
        assert len(df2) == 2  # file untouched
    finally:
        conn.close()


@pytest.mark.unit
def test_poll_cycle_writes_parquet_before_checkpoint(tmp_path, fake_mt5, make_cfg, monkeypatch):
    """Write-then-checkpoint ordering (Pattern 5) — the only restart state."""
    _script_all_combos(fake_mt5)
    cfg = _poll_cfg(make_cfg, tmp_path)
    events: list[str] = []
    real_write = collector_module.bar_store.merge_and_write
    real_checkpoint = collector_module.meta_store.update_checkpoint

    def spy_write(*args, **kwargs):
        events.append("write")
        return real_write(*args, **kwargs)

    def spy_checkpoint(*args, **kwargs):
        events.append("checkpoint")
        return real_checkpoint(*args, **kwargs)

    monkeypatch.setattr(collector_module.bar_store, "merge_and_write", spy_write)
    monkeypatch.setattr(collector_module.meta_store, "update_checkpoint", spy_checkpoint)

    conn = meta_store.connect(cfg.meta_db)
    try:
        run_poll_cycle(cfg, conn, fake_mt5)
    finally:
        conn.close()
    # strictly one write followed by one checkpoint per stored combo
    assert events == ["write", "checkpoint"] * 9


@pytest.mark.unit
def test_poll_cycle_propagates_fetch_failure_loudly(tmp_path, fake_mt5, make_cfg):
    """An unscripted (failing) combo raises MT5DataError — never a silent skip."""
    fake_mt5.set_rates("EURUSD", fake_mt5.timeframe_enum("M15"), _rates_for("M15", 5))
    fake_mt5.error_code, fake_mt5.error_msg = -4, "No history"
    cfg = _poll_cfg(make_cfg, tmp_path)
    conn = meta_store.connect(cfg.meta_db)
    try:
        with pytest.raises(MT5DataError):
            run_poll_cycle(cfg, conn, fake_mt5)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# validate_offset + offset_drift_detected (DATA-03)
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_validate_offset_server_ahead_three_returns_plus_three(fake_mt5, make_cfg):
    """Broker server wall = true UTC + 3h (active market: tick age ~seconds).
    The returned value MUST use the cfg.broker_offset_hours convention
    (hours to subtract to reach true UTC), so a UTC+3 broker validates as +3."""
    now = datetime.now(UTC).replace(tzinfo=None)
    server_wall = now + timedelta(hours=3)
    fake_mt5.script_tick("EURUSD", SimpleNamespace(time=_epoch(server_wall)))
    assert validate_offset(make_cfg(broker_offset_hours=3), "EURUSD", fake_mt5) == 3


@pytest.mark.unit
def test_validate_offset_stale_weekend_tick_poisons_estimate(fake_mt5, make_cfg):
    """A 36h-old weekend tick yields a huge-magnitude estimate — the documented
    reason validation is valid during ACTIVE market hours only."""
    now = datetime.now(UTC).replace(tzinfo=None)
    stale_server_wall = now - timedelta(hours=36)
    fake_mt5.script_tick("EURUSD", SimpleNamespace(time=_epoch(stale_server_wall)))
    assert validate_offset(make_cfg(), "EURUSD", fake_mt5) == -36  # implausible by magnitude


@pytest.mark.unit
def test_validate_offset_missing_tick_raises_data_error(fake_mt5, make_cfg):
    fake_mt5.error_code, fake_mt5.error_msg = -6, "Authorization failed"
    with pytest.raises(MT5DataError, match="-6"):
        validate_offset(make_cfg(), "EURUSD", fake_mt5)


@pytest.mark.unit
def test_offset_drift_detected_flags_any_mismatch(fake_mt5, make_cfg):
    cfg = make_cfg(broker_offset_hours=3)
    assert offset_drift_detected(cfg, 3) is False
    assert offset_drift_detected(cfg, 2) is True
    assert offset_drift_detected(cfg, -3) is True
