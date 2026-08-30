"""Unit tests (DATA-05): history-availability discovery walk-back, gap
detection/classification, persistence, and queryability — all against
FakeMT5Client (no terminal).
"""

from __future__ import annotations

import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from ai_trading.history_report import (
    classify_gap,
    compute_gaps,
    discover_history_bounds,
    generate_report,
    get_report,
)
from ai_trading.normalize import rates_to_dataframe
from ai_trading.stores import meta_store

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

SERVER_START = datetime(2026, 8, 28, 0, 0)  # server wall, M15-aligned
OFFSET = 3
SYMBOL = "EURUSD"
TF = "M15"


def _epoch(naive_server_wall: datetime) -> int:
    return int(naive_server_wall.replace(tzinfo=UTC).timestamp())


def _rates(count: int, start: datetime = SERVER_START, minutes: int = 15) -> np.ndarray:
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


def _bars_df(count: int, start: datetime = SERVER_START) -> pd.DataFrame:
    return rates_to_dataframe(_rates(count, start), SYMBOL, OFFSET)


def _report_cfg(make_cfg, tmp_path, **overrides):
    return make_cfg(
        symbols=(SYMBOL,),
        timeframes=(TF,),
        bars_dir=tmp_path / "bars",
        meta_db=tmp_path / "meta" / "meta.sqlite",
        backfill_max_rounds=2,  # keep persistent-None walks fast
        backfill_pause_seconds=0.0,
        **overrides,
    )


def _script_discovery(fake, deques, error_code=-4):
    """Script the discovery walk: `deques` are popped in order per range call;
    once exhausted every call returns None with `error_code` (persistent)."""
    fake.error_code, fake.error_msg = error_code, "No history"
    fake.script_rates(SYMBOL, fake.timeframe_enum(TF), deques)


# ---------------------------------------------------------------------------
# discover_history_bounds (DATA-05 walk-back)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_discovery_stops_at_persistent_none_minus4_and_records_maxbars(
    tmp_path, fake_mt5, make_cfg
):
    """A persistent None/-4 below the scripted cutoff ends the walk; the result
    carries deduplicated bounds and the fake's terminal maxbars provenance."""
    cfg = _report_cfg(make_cfg, tmp_path)
    recent = _rates(10)  # window 1 (recent year)
    _script_discovery(fake_mt5, [recent, recent])  # window 2+ -> persistent None

    result = discover_history_bounds(cfg, SYMBOL, TF, fake_mt5)

    assert result["bar_count"] == 10
    assert result["terminal_maxbars"] == fake_mt5.maxbars  # provenance recorded
    assert result["fetched_at"]  # ISO now
    shift = pd.Timedelta(hours=OFFSET)
    expected_first = (pd.to_datetime(int(recent[0]["time"]), unit="s") - shift).isoformat()
    expected_last = (pd.to_datetime(int(recent[-1]["time"]), unit="s") - shift).isoformat()
    assert result["first_bar_utc"] == expected_first
    assert result["last_bar_utc"] == expected_last
    # 2 stable rounds for window 1 + exhausted rounds for window 2 (max_rounds=2)
    assert fake_mt5.counts["copy_rates_range"] == 4


@pytest.mark.unit
def test_discovery_accumulates_and_dedups_across_windows(tmp_path, fake_mt5, make_cfg):
    """Older windows extend the accumulated history; duplicates on raw time are
    deduplicated; the walk stops when a window adds zero new rows (the
    live-probed pre-history clamp / maxbars-cap signal)."""
    cfg = _report_cfg(make_cfg, tmp_path)
    recent = _rates(10)
    older = np.concatenate([_rates(10, start=SERVER_START - timedelta(days=365)), recent])
    _script_discovery(fake_mt5, [recent, recent, older, older, older])

    result = discover_history_bounds(cfg, SYMBOL, TF, fake_mt5)

    assert result["bar_count"] == 20  # 10 older + 10 recent, deduplicated
    assert result["terminal_maxbars"] == fake_mt5.maxbars
    expected_first = (
        pd.to_datetime(int(older[0]["time"]), unit="s") - pd.Timedelta(hours=OFFSET)
    ).isoformat()
    assert result["first_bar_utc"] == expected_first


# ---------------------------------------------------------------------------
# generate_report persistence + get_report queryability (no client)
# ---------------------------------------------------------------------------


def _seed_store_with_gap(cfg) -> pd.Timestamp:
    """Store bars 0..4 and 8..9 (server wall) — a 3-slot gap between them."""
    path = Path(cfg.bars_dir) / f"{SYMBOL}_{TF}.parquet"
    head = _bars_df(5)  # bars 0..4
    tail = _bars_df(2, start=SERVER_START + timedelta(minutes=15 * 8))  # bars 8..9
    from ai_trading.stores import bar_store

    bar_store.merge_and_write(head, path, TF)
    bar_store.merge_and_write(tail, path, TF)
    return head["time_utc"].min()


@pytest.mark.unit
def test_generate_report_persists_and_get_report_reads_without_client(
    tmp_path, fake_mt5, make_cfg
):
    """generate_report persists history_bounds + bar_gaps rows; get_report
    reconstructs the report from SQLite with NO client attached."""
    cfg = _report_cfg(make_cfg, tmp_path)
    stored_first = _seed_store_with_gap(cfg)
    discovered = _rates(10, start=SERVER_START - timedelta(days=30))
    _script_discovery(fake_mt5, [discovered, discovered])

    conn = meta_store.connect(cfg.meta_db)
    try:
        report = generate_report(cfg, conn, fake_mt5, discover=False)

        # persisted bounds carry the DISCOVERED (terminal-available) values
        row = meta_store.get_history_bounds(conn, SYMBOL, TF)
        assert row is not None
        assert row["bar_count"] == 10
        assert row["terminal_maxbars"] == fake_mt5.maxbars
        assert row["first_bar_utc"] == (
            pd.to_datetime(int(discovered[0]["time"]), unit="s") - pd.Timedelta(hours=OFFSET)
        ).isoformat()
        # persisted gaps: the single 3-slot hole (slot5 open -> slot8 open)
        gaps = meta_store.get_gaps(conn, SYMBOL, TF)
        assert gaps == [
            (
                (stored_first + pd.Timedelta(minutes=15 * 5)).isoformat(),
                (stored_first + pd.Timedelta(minutes=15 * 8)).isoformat(),
            )
        ]

        # queryability: reconstruct WITHOUT any client
        restored = get_report(cfg, conn)
        combo = restored["combos"][0]
        assert combo["symbol"] == SYMBOL and combo["timeframe"] == TF
        assert combo["available"]["bar_count"] == 10
        assert combo["available"]["terminal_maxbars"] == fake_mt5.maxbars
        assert combo["stored"]["count"] == 7
        assert combo["stored"]["first"] == stored_first.isoformat()
        assert len(combo["gaps"]) == 1
        assert combo["gaps"][0][2] == "review"  # 45-minute hole -> review
        # every report row carries terminal_maxbars
        assert all(c["terminal_maxbars"] == fake_mt5.maxbars for c in restored["combos"])
        assert all("terminal_maxbars" in c for c in report["combos"])
    finally:
        conn.close()


@pytest.mark.unit
def test_first_generation_prefers_discovered_depth_over_store_bounds(
    tmp_path, fake_mt5, make_cfg
):
    """With a Parquet file present but NO persisted history_bounds row,
    generate_report invokes discovery and the persisted row carries the
    DISCOVERED bounds — the store is not mistaken for available history."""
    cfg = _report_cfg(make_cfg, tmp_path)
    stored_first = _seed_store_with_gap(cfg)
    discovered = _rates(10, start=SERVER_START - timedelta(days=30))
    _script_discovery(fake_mt5, [discovered, discovered])

    conn = meta_store.connect(cfg.meta_db)
    try:
        generate_report(cfg, conn, fake_mt5, discover=False)

        assert fake_mt5.counts["copy_rates_range"] > 0  # discovery actually ran
        row = meta_store.get_history_bounds(conn, SYMBOL, TF)
        discovered_first = (
            pd.to_datetime(int(discovered[0]["time"]), unit="s") - pd.Timedelta(hours=OFFSET)
        ).isoformat()
        assert row["first_bar_utc"] == discovered_first
        assert row["first_bar_utc"] != stored_first.isoformat()  # not the store's
        assert row["bar_count"] == 10  # not the store's 7 rows
    finally:
        conn.close()


@pytest.mark.unit
def test_plain_run_does_not_rediscover_or_clobber_persisted_row(
    tmp_path, fake_mt5, make_cfg
):
    """With a discovered row already persisted, a plain generate_report run
    neither re-discovers nor clobbers the row."""
    cfg = _report_cfg(make_cfg, tmp_path)
    _seed_store_with_gap(cfg)
    conn = meta_store.connect(cfg.meta_db)
    try:
        meta_store.upsert_history_bounds(
            conn, SYMBOL, TF,
            "2000-01-01T00:00:00", "2001-01-01T00:00:00",
            999, 12345, "2020-01-01T00:00:00Z",
        )

        generate_report(cfg, conn, fake_mt5, discover=False)

        assert fake_mt5.counts["copy_rates_range"] == 0  # no discovery calls
        row = meta_store.get_history_bounds(conn, SYMBOL, TF)
        assert row["bar_count"] == 999  # marker values untouched
        assert row["first_bar_utc"] == "2000-01-01T00:00:00"
        assert row["terminal_maxbars"] == 12345
        restored = get_report(cfg, conn)
        assert restored["combos"][0]["available"]["bar_count"] == 999
    finally:
        conn.close()


@pytest.mark.unit
def test_discover_flag_forces_rediscovery_and_refreshes_row(tmp_path, fake_mt5, make_cfg):
    cfg = _report_cfg(make_cfg, tmp_path)
    _seed_store_with_gap(cfg)
    discovered = _rates(10, start=SERVER_START - timedelta(days=30))
    _script_discovery(fake_mt5, [discovered, discovered])
    conn = meta_store.connect(cfg.meta_db)
    try:
        meta_store.upsert_history_bounds(
            conn, SYMBOL, TF,
            "2000-01-01T00:00:00", "2001-01-01T00:00:00",
            999, 12345, "2020-01-01T00:00:00Z",
        )

        generate_report(cfg, conn, fake_mt5, discover=True)

        assert fake_mt5.counts["copy_rates_range"] > 0  # forced re-discovery
        row = meta_store.get_history_bounds(conn, SYMBOL, TF)
        assert row["bar_count"] == 10  # refreshed with discovered depth
        assert row["terminal_maxbars"] == fake_mt5.maxbars
        assert row["first_bar_utc"] == (
            pd.to_datetime(int(discovered[0]["time"]), unit="s") - pd.Timedelta(hours=OFFSET)
        ).isoformat()
    finally:
        conn.close()


@pytest.mark.unit
def test_empty_store_handled_and_discovery_still_provides_available(
    tmp_path, fake_mt5, make_cfg
):
    """No Parquet file: empty stored bounds, empty gaps, no exception — and on
    first generation the available-depth record still comes from discovery."""
    cfg = _report_cfg(make_cfg, tmp_path)
    discovered = _rates(10, start=SERVER_START - timedelta(days=30))
    _script_discovery(fake_mt5, [discovered, discovered])

    conn = meta_store.connect(cfg.meta_db)
    try:
        report = generate_report(cfg, conn, fake_mt5, discover=False)
        combo = report["combos"][0]
        assert combo["stored"] == {"first": None, "last": None, "count": 0}
        assert combo["gaps"] == []
        assert combo["available"]["bar_count"] == 10
        assert combo["terminal_maxbars"] == fake_mt5.maxbars

        restored = get_report(cfg, conn)
        assert restored["combos"][0]["stored"]["count"] == 0
        assert restored["combos"][0]["available"]["bar_count"] == 10
    finally:
        conn.close()


@pytest.mark.unit
def test_discovery_yielding_nothing_falls_back_to_store_row(tmp_path, fake_mt5, make_cfg):
    """No persisted row + discovery serves nothing -> store-derived bounds are
    written so the queryable row exists."""
    cfg = _report_cfg(make_cfg, tmp_path)
    stored_first = _seed_store_with_gap(cfg)
    _script_discovery(fake_mt5, [])  # every window -> persistent None -> 0 bars

    conn = meta_store.connect(cfg.meta_db)
    try:
        report = generate_report(cfg, conn, fake_mt5, discover=False)
        row = meta_store.get_history_bounds(conn, SYMBOL, TF)
        assert row is not None  # the row exists (fallback)
        assert row["bar_count"] == 7  # store-derived, not discovery (0)
        assert row["first_bar_utc"] == stored_first.isoformat()
        assert report["combos"][0]["available"]["bar_count"] == 7
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# compute_gaps + classify_gap (Pitfall 6: report, never crash)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_compute_gaps_finds_injected_missing_slots_exactly(tmp_path):
    """An injected missing chunk of 10 consecutive M15 slots is reported as one
    gap with exact aligned start/end timestamps."""
    head = _bars_df(10)  # bars 0..9
    tail = _bars_df(10, start=SERVER_START + timedelta(minutes=15 * 20))  # bars 20..29
    df = pd.concat([head, tail], ignore_index=True)

    gaps = compute_gaps(df, TF)

    expected_start = head["time_utc"].min() + pd.Timedelta(minutes=15 * 10)
    expected_end = head["time_utc"].min() + pd.Timedelta(minutes=15 * 20)
    assert gaps == [(expected_start, expected_end)]
    assert gaps[0][0] == pd.Timestamp("2026-08-27 23:30:00")
    assert gaps[0][1] == pd.Timestamp("2026-08-28 02:00:00")


@pytest.mark.unit
def test_weekend_hole_classified_without_raising(tmp_path):
    """A synthetic Friday-close -> Sunday-open week yields ONE weekend-sized
    hole (~48h) classified without raising (Pitfall 6)."""
    # Friday session: true-UTC 00:00 -> 20:45 (server wall 03:00 -> 23:45)
    friday = rates_to_dataframe(_rates(84, start=datetime(2026, 8, 28, 3, 0)), SYMBOL, OFFSET)
    # Sunday reopen: true-UTC Sun 21:00 -> 22:45 (server wall Mon 00:00 -> 01:45)
    sunday = rates_to_dataframe(_rates(4, start=datetime(2026, 8, 31, 0, 0)), SYMBOL, OFFSET)
    df = pd.concat([friday, sunday], ignore_index=True)

    gaps = compute_gaps(df, TF)

    assert len(gaps) == 1
    gap_start, gap_end = gaps[0]
    assert gap_start == pd.Timestamp("2026-08-28 21:00:00")
    assert gap_end == pd.Timestamp("2026-08-30 21:00:00")
    span_hours = (gap_end - gap_start).total_seconds() / 3600.0
    assert 47 <= span_hours <= 49
    assert classify_gap(gap_start, gap_end) == "weekend"  # never raises


@pytest.mark.unit
def test_classify_gap_short_hole_is_review(tmp_path):
    assert classify_gap(
        pd.Timestamp("2026-08-27 22:15:00"), pd.Timestamp("2026-08-27 23:00:00")
    ) == "review"
    # a >47h block that does NOT cross the Sat-Sun window is still "review"
    assert classify_gap(
        pd.Timestamp("2026-08-25 00:00:00"), pd.Timestamp("2026-08-27 00:00:00")
    ) == "review"


@pytest.mark.unit
def test_compute_gaps_on_non_midnight_anchored_h4_lattice():
    """Regression (live-verified 2026-08-30): IC Markets H4 bars open on the
    21:00-UTC server-midnight anchor {1,5,9,13,17,21}-hour UTC grid, NOT the
    midnight-UTC lattice. The expected grid must anchor at the observed
    minimum so real H4 bars are not all misclassified as missing; the weekend
    hole (Fri 17:00 -> Sun 21:00 UTC) is the only gap."""
    # one trading week of H4 bars: Mon 00:00? no — bars at 1,5,9,13,17,21 UTC
    week_hours = [1, 5, 9, 13, 17, 21]
    opens = []
    for day_offset in (0, 1, 2, 3, 4):  # Mon..Fri
        base = pd.Timestamp("2026-08-24 00:00:00") + pd.Timedelta(days=day_offset)
        opens.extend(base + pd.Timedelta(hours=h) for h in week_hours)
    # skip the weekend; next week Monday bars too
    base = pd.Timestamp("2026-08-31 00:00:00")
    opens.extend(base + pd.Timedelta(hours=h) for h in week_hours[:2])  # Mon 01:00, 05:00
    df = _bars_df(len(opens), start=SERVER_START)
    df["time_utc"] = pd.DatetimeIndex(opens)
    df["time"] = df["time_utc"] + pd.Timedelta(hours=OFFSET)  # keep raw consistent

    gaps = compute_gaps(df, "H4")

    # one weekend hole expressed as its missing slots: Sat 01:00 (first missing
    # H4 slot after Fri 21:00) -> Mon 01:00 (next present bar's open)
    assert len(gaps) == 1
    assert gaps[0] == (
        pd.Timestamp("2026-08-29 01:00:00"), pd.Timestamp("2026-08-31 01:00:00")
    )
    assert classify_gap(*gaps[0]) == "weekend"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_cli_help_shows_config_and_discover():
    """`python -m ai_trading.history_report --help` exits 0 listing both flags."""
    proc = subprocess.run(
        [sys.executable, "-m", "ai_trading.history_report", "--help"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0
    assert "--config" in proc.stdout
    assert "--discover" in proc.stdout
