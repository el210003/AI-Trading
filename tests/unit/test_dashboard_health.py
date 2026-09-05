"""Pure unit tests for the dashboard Health data layer (DASH-06).

Exercises ``data_layer.health_status`` (per-feed last-bar times, MT5 heartbeat
freshness -> healthy/stale/disconnected, recent-errors recency window) and the
single-purpose meta readers (``collection_state_heartbeats`` /
``recent_bar_gaps``). Runs offline (no Streamlit, no MT5) against an isolated
temp data root.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pandas as pd
import pytest
from _dashboard_fixtures import dashboard_cfg

from ai_trading.dashboard import data_layer as dl
from ai_trading.stores import meta_store
from ai_trading.stores.bar_store import bar_path

NOW = datetime(2026, 8, 20, 12, 0, 0, tzinfo=UTC)


def _write_bars(cfg, symbol: str, timeframe: str, times) -> None:
    """Write a minimal bar parquet (with a ``time_utc`` column) at the canonical
    path so ``read_bars`` / ``health_status`` can read the last-bar time."""
    path = bar_path(cfg.bars_dir, symbol, timeframe)
    path.parent.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame(
        {
            "symbol": [symbol] * len(times),
            "time": list(times),
            "time_utc": list(times),
            "open": [1.0] * len(times),
            "high": [1.1] * len(times),
            "low": [0.9] * len(times),
            "close": [1.05] * len(times),
            "tick_volume": [1] * len(times),
            "spread": [1] * len(times),
            "real_volume": [0] * len(times),
        }
    )
    frame.to_parquet(path, index=False)


def _seed_heartbeat(cfg, symbol, timeframe, last_success_iso: str | None,
                    last_bar_iso: str = "2026-08-20T11:00:00") -> None:
    """Write a ``collection_state`` row (or a disconnected-state when None)."""
    if last_success_iso is None:
        return
    conn = meta_store.connect(cfg.meta_db)
    meta_store.update_checkpoint(conn, symbol, timeframe, last_bar_iso, last_success_iso)
    conn.close()


def _seed_gaps(cfg, detected_iso: str, count: int = 1, tag: str = "g") -> None:
    """Write ``count`` bar-gap rows detected at ``detected_iso`` using distinct
    ``gap_start`` keys (so separate seed calls never collide on the PK)."""
    conn = meta_store.connect(cfg.meta_db)
    gaps = [(f"{tag}-{i}", f"{tag}-{i}-end") for i in range(count)]
    meta_store.upsert_gaps(conn, "EURUSD", "M15", gaps, detected_iso)
    conn.close()


@pytest.mark.unit
def test_health_per_feed_last_bar_times(tmp_path):
    cfg = dashboard_cfg(tmp_path, symbols=("EURUSD", "GBPUSD"), timeframes=("M15",))
    _write_bars(cfg, "EURUSD", "M15", [pd.Timestamp("2026-08-19T10:00:00"),
                                      pd.Timestamp("2026-08-19T10:15:00")])
    # GBPUSD has no bar file -> no-data.
    status = dl.health_status(cfg, now=NOW)
    by_feed = {(f["symbol"], f["timeframe"]): f["last_bar_time"] for f in status["per_feed"]}
    assert by_feed[("EURUSD", "M15")] == pd.Timestamp("2026-08-19T10:15:00")
    assert by_feed[("GBPUSD", "M15")] is None


@pytest.mark.unit
def test_health_heartbeat_freshness_mapping(tmp_path):
    cfg = dashboard_cfg(tmp_path, symbols=("EURUSD",), timeframes=("M15",))
    # healthy: heartbeat within the fresh window (<= 20 min — comfortably above
    # the ~15.2-min worst-case inter-poll gap at the M15-close cadence).
    _seed_heartbeat(cfg, "EURUSD", "M15", (NOW - timedelta(minutes=15)).isoformat())
    assert dl.health_status(cfg, now=NOW)["mt5_status"] == "healthy"
    # stale: within the stale window (> 20 min, <= 30 min).
    cfg2 = dashboard_cfg(tmp_path / "stale", symbols=("EURUSD",), timeframes=("M15",))
    _seed_heartbeat(cfg2, "EURUSD", "M15", (NOW - timedelta(minutes=25)).isoformat())
    assert dl.health_status(cfg2, now=NOW)["mt5_status"] == "stale"
    # disconnected: heartbeat too old.
    cfg3 = dashboard_cfg(tmp_path / "disc", symbols=("EURUSD",), timeframes=("M15",))
    _seed_heartbeat(cfg3, "EURUSD", "M15", (NOW - timedelta(hours=2)).isoformat())
    assert dl.health_status(cfg3, now=NOW)["mt5_status"] == "disconnected"
    # disconnected: no heartbeat row at all.
    cfg4 = dashboard_cfg(tmp_path / "none", symbols=("EURUSD",), timeframes=("M15",))
    assert dl.health_status(cfg4, now=NOW)["mt5_status"] == "disconnected"


@pytest.mark.unit
def test_health_recent_errors_recency_window(tmp_path):
    cfg = dashboard_cfg(tmp_path, symbols=("EURUSD",), timeframes=("M15",))
    # 3 gaps within the 7-day window + 1 older gap -> recent_errors == 3.
    _seed_gaps(cfg, (NOW - timedelta(days=2)).isoformat(), count=3, tag="recent")
    _seed_gaps(cfg, (NOW - timedelta(days=30)).isoformat(), count=1, tag="old")
    status = dl.health_status(cfg, now=NOW)
    assert status["recent_errors"] == 3


@pytest.mark.unit
def test_health_empty_store_degrades_no_data(tmp_path):
    """T-06-03: a missing bar/meta store must never raise — it degrades to the
    no-data/disconnected state so the view renders the copy state."""
    cfg = dashboard_cfg(tmp_path, symbols=("EURUSD", "GBPUSD"), timeframes=("M15",))
    status = dl.health_status(cfg, now=NOW)
    assert status["mt5_status"] == "disconnected"
    assert status["recent_errors"] == 0
    assert all(f["last_bar_time"] is None for f in status["per_feed"])


@pytest.mark.unit
def test_recent_bar_gaps_direct(tmp_path):
    conn = meta_store.connect(tmp_path / "meta.sqlite")
    meta_store.upsert_gaps(conn, "EURUSD", "M15", [("a", "b"), ("c", "d")], NOW.isoformat())
    assert dl.recent_bar_gaps(conn, now=NOW) == 2
    assert dl.recent_bar_gaps(conn, days=0, now=NOW) == 2
    # Nothing beyond a zero-day window from the future start.
    assert dl.recent_bar_gaps(conn, days=1, now=NOW + timedelta(days=10)) == 0
    conn.close()
