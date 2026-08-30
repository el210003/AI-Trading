"""Live integration tests (marker: mt5) — REQUIRE a running, logged-in MT5
terminal at the configured terminal_path.

Excluded from the default `uv run pytest -q` run by the pyproject addopts
(`-m "not mt5"`); run explicitly via `uv run pytest -m mt5 -q`. When the
terminal is down (or the live config is unavailable) every test SKIPS with an
actionable message, so the suite still exits 0.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from ai_trading import mt5_client
from ai_trading.collector import backfill_symbol_timeframe, connect_and_verify, fetch_closed_bars
from ai_trading.config import load_config
from ai_trading.history_report import generate_report
from ai_trading.normalize import COLUMNS, assert_closed_bars
from ai_trading.stores import meta_store

pytestmark = [pytest.mark.mt5]


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


@pytest.fixture
def live_cfg():
    """Real config + initialized terminal; skips with an actionable message
    when the live config is unavailable or the terminal is unreachable."""
    try:
        cfg = load_config(_repo_root() / "config.toml")
    except ValueError as exc:
        pytest.skip(f"live MT5 config unavailable: {exc}")
    if not mt5_client.initialize(path=cfg.terminal_path, timeout_ms=cfg.init_timeout_ms):
        code, msg = mt5_client.last_error()
        pytest.skip(
            f"MT5 terminal not reachable at '{cfg.terminal_path}' [{code}: {msg}] — "
            "start and log in to the terminal to run the live integration tests"
        )
    return cfg


def test_connect_and_verify_live(live_cfg):
    """The 6-step health check passes against the real terminal."""
    connect_and_verify(live_cfg)


def test_fetch_closed_bars_live(live_cfg):
    """fetch_closed_bars returns COLUMNS-ordered closed bars for EURUSD M15."""
    df = fetch_closed_bars(live_cfg, "EURUSD", "M15", mt5_client)
    assert list(df.columns) == COLUMNS
    assert len(df) > 0
    assert_closed_bars(df, "M15", datetime.now(UTC))


def test_backfill_and_report_live(live_cfg):
    """backfill_symbol_timeframe then generate_report for EURUSD M15: a
    persisted history_bounds row exists afterwards."""
    narrow = replace(live_cfg, symbols=("EURUSD",), timeframes=("M15",))
    conn = meta_store.connect(Path(narrow.meta_db))
    try:
        added = backfill_symbol_timeframe(narrow, conn, "EURUSD", "M15", mt5_client)
        assert added >= 0

        generate_report(narrow, conn, mt5_client, discover=False)

        bounds = meta_store.get_history_bounds(conn, "EURUSD", "M15")
        assert bounds is not None
        assert bounds["bar_count"] > 0
        assert bounds["terminal_maxbars"] is not None
    finally:
        conn.close()
