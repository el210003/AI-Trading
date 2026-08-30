"""Collector service: startup health check, closed-bar polling, and empirical
broker-offset validation (DATA-01/02/03).

Pattern of record:
- RESEARCH.md Code Example 1 (health-check sequence with actionable,
  credential-free errors — Shared Pattern 1 error taxonomy).
- RESEARCH.md Pattern 2 (closed-bar polling: fetch from start_pos=1, poll
  AFTER the timeframe boundary + fixed delay).
- RESEARCH.md Pattern 5 (checkpoint is the ONLY restart state; write-then-
  checkpoint ordering so a crash between the two merely refetches).
- RESEARCH.md Code Example 5 (empirical offset validation sketch).

The MetaTrader5 import lives ONLY in ai_trading.mt5_client (Shared Pattern 6);
`client` parameters accept the mt5_client module itself by default and any
object with the same function surface (tests inject FakeMT5Client).
"""

from __future__ import annotations

import argparse
import logging
import sys
import time as _time
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from ai_trading import mt5_client
from ai_trading.config import load_config
from ai_trading.mt5_client import MT5ConnectionError, MT5DataError
from ai_trading.normalize import TIMEFRAME_MINUTES, rates_to_dataframe
from ai_trading.stores import bar_store, meta_store

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# DATA-01: startup health check
# ---------------------------------------------------------------------------


def connect_and_verify(cfg, client=mt5_client) -> None:
    """DATA-01 startup health check against `client` (module or fake).

    Verifies, in order: initialize success, terminal_info().connected,
    account_info() non-None, expected_server match (when configured), and
    symbol_select True for every configured symbol. Every failure path raises
    MT5ConnectionError embedding the last_error code and an actionable remedy;
    no message ever contains credentials. After all checks pass, a terminal
    maxbars below cfg.min_maxbars logs a loud warning (Pitfall 2).
    """
    # (a) initialize — explicit path only (Pitfall 8: never auto-discover).
    if not client.initialize(path=cfg.terminal_path, timeout_ms=cfg.init_timeout_ms):
        code, msg = client.last_error()
        raise MT5ConnectionError(
            f"MT5 initialize failed [{code}: {msg}]. Is the terminal running at "
            f"'{cfg.terminal_path}' and logged in? (code {mt5_client.AUTH_FAILED} means "
            "the terminal is up but no account is authorized.)"
        )

    # (b) terminal connected to the broker server.
    info = client.terminal_info()
    if info is None or not info.connected:
        code, msg = client.last_error()
        raise MT5ConnectionError(
            f"Terminal not connected to the broker server (terminal_info().connected "
            f"is False or terminal_info() is None) [{code}: {msg}] — "
            "log in to the trade server."
        )

    # (c) account authorized.
    account = client.account_info()
    if account is None:
        code, msg = client.last_error()
        raise MT5ConnectionError(
            f"No trading account authorized [{code}: {msg}] — open the terminal and "
            "log in to the trade account (File > Login to Trade Account)."
        )

    # (d) wrong-feed guard (Pitfall 8: two MT5 installs exist on this machine).
    if cfg.expected_server and account.server != cfg.expected_server:
        raise MT5ConnectionError(
            f"Connected account server '{account.server}' does not match configured "
            f"expected_server '{cfg.expected_server}' — refusing to collect from the "
            "wrong terminal/account; fix terminal_path/expected_server in "
            "config.local.toml."
        )

    # (e) every configured symbol selectable in Market Watch.
    for sym in cfg.symbols:
        if not client.symbol_select(sym, True):
            code, msg = client.last_error()
            raise MT5ConnectionError(
                f"symbol_select('{sym}') failed [{code}: {msg}] — symbol not available "
                "on this broker; check Market Watch and whether the broker suffixes "
                "symbol names (e.g. EURUSD.a), then fix config symbols."
            )

    # (f) history-cap warning (Pitfall 2: "Max. bars in chart" silently bounds
    # every copy_rates result and would starve Phase 3 backtests).
    if info.maxbars < cfg.min_maxbars:
        log.warning(
            "terminal maxbars=%d is below min_maxbars=%d — history is capped; set "
            "Tools > Options > Charts > Max. bars in chart = Unlimited",
            info.maxbars,
            cfg.min_maxbars,
        )


# ---------------------------------------------------------------------------
# DATA-02: closed-bar fetch + poll scheduling + incremental cycle
# ---------------------------------------------------------------------------


def fetch_closed_bars(cfg, symbol: str, timeframe: str, client=mt5_client) -> pd.DataFrame:
    """Fetch CLOSED bars for (symbol, timeframe) as the canonical bar frame.

    start_pos MUST be literally 1: position 0 is the still-forming bar and is
    never fetched or stored (research-verified; the project's look-ahead-safety
    root for this shared code path). Raises MT5DataError embedding the
    last_error code and message when the terminal returns None or an empty
    result — never a silent skip.
    """
    rates = client.copy_rates_from_pos(
        symbol, client.timeframe_enum(timeframe), 1, cfg.lookback_bars
    )
    if rates is None or len(rates) == 0:
        code, msg = client.last_error()
        raise MT5DataError(
            f"copy_rates_from_pos('{symbol}', {timeframe}, start_pos=1) returned "
            f"{'None' if rates is None else 'an empty result'} [{code}: {msg}] — "
            "check Market Watch visibility and history availability for this symbol."
        )
    return rates_to_dataframe(rates, symbol, cfg.broker_offset_hours)


def seconds_until_next_close(timeframe: str, now_utc: datetime, delay_seconds: int) -> float:
    """Seconds from `now_utc` until the next `timeframe` boundary closes plus
    `delay_seconds` (poll AFTER the bar closes — Pattern 2 boundary+delay
    discipline); minimum 0.

    Accepts naive-UTC or aware-UTC `now_utc` (aware is stripped, matching the
    normalize aware-then-strip rule for non-broker clocks).
    """
    period_seconds = TIMEFRAME_MINUTES[timeframe] * 60
    now = now_utc.replace(tzinfo=None) if now_utc.tzinfo is not None else now_utc
    # Fixed-epoch arithmetic (NOT naive .timestamp(), which applies the local
    # machine timezone): the naive clock is pure UTC wall arithmetic here.
    elapsed = (now - datetime(1970, 1, 1)).total_seconds()
    remainder = elapsed % period_seconds
    seconds_to_boundary = (period_seconds - remainder) % period_seconds
    return max(0.0, seconds_to_boundary + delay_seconds)


def run_poll_cycle(cfg, conn, client=mt5_client) -> int:
    """One incremental collection pass over every (symbol, timeframe) combo.

    For each combo: fetch closed bars, keep only rows whose time_utc is
    STRICTLY greater than the SQLite checkpoint (all rows when no checkpoint
    exists), skip when nothing is new, write Parquet via bar_store.merge_and_write,
    and ONLY after that write succeeds update the checkpoint with the max
    stored time_utc (write-then-checkpoint ordering, Pattern 5 — a crash
    between the two merely refetches). Returns the total number of new bar
    rows stored across all combos.
    """
    total_new = 0
    for symbol in cfg.symbols:
        for timeframe in cfg.timeframes:
            df = fetch_closed_bars(cfg, symbol, timeframe, client)

            checkpoint_iso = meta_store.get_checkpoint(conn, symbol, timeframe)
            if checkpoint_iso is not None:
                checkpoint_ts = pd.Timestamp(checkpoint_iso)
                df = df[df["time_utc"] > checkpoint_ts]
            if df.empty:
                continue

            path = bar_store.bar_path(Path(cfg.bars_dir), symbol, timeframe)
            bar_store.merge_and_write(df, path, timeframe)
            last_iso = df["time_utc"].max().isoformat()
            meta_store.update_checkpoint(
                conn, symbol, timeframe, last_iso, datetime.now(UTC).isoformat()
            )
            total_new += len(df)
            log.info(
                "stored %d new %s %s bar(s) (through %s)", len(df), symbol, timeframe, last_iso
            )
    return total_new


# ---------------------------------------------------------------------------
# DATA-03: empirical broker-offset validation
# ---------------------------------------------------------------------------


def validate_offset(cfg, symbol: str, client=mt5_client) -> int:
    """Empirically estimate the broker server offset (hours to SUBTRACT from
    server wall time to reach true UTC — same convention as
    cfg.broker_offset_hours / normalize.rates_to_dataframe).

    Per RESEARCH Code Example 5: the last tick's epoch decodes to broker
    server wall time; during ACTIVE market hours the tick age
    (now_utc - tick_server) is approximately -(broker offset) plus a few
    seconds of quote latency, so the offset estimate is
    ``round(-age_seconds / 3600)``.

    Caveats (documented per plan):
    - Valid during ACTIVE market hours ONLY (Mon-Fri) — weekend ticks are
      stale (hours-to-days old) and poison the estimate with a large wrong
      magnitude.
    - Minute-level ambiguity: the estimate must be cross-checked against
      bar-boundary alignment (H1 bars on exact hour boundaries in time_utc,
      M15 on quarter-hour boundaries) before persisting.
    """
    tick = client.symbol_info_tick(symbol)
    if tick is None:
        code, msg = client.last_error()
        raise MT5DataError(
            f"symbol_info_tick('{symbol}') returned None [{code}: {msg}] — cannot "
            "validate the broker offset without a quote."
        )
    tick_server = pd.to_datetime(tick.time, unit="s")  # naive server wall time
    age = datetime.now(UTC).replace(tzinfo=None) - tick_server
    # Sign note: server wall time runs AHEAD of true UTC by the broker offset,
    # so the tick age is approximately -offset during active hours. The
    # negation aligns the returned value with the cfg.broker_offset_hours
    # convention ("hours to subtract to reach true UTC") — RESEARCH Code
    # Example 5's sketch marks this step "adjusted"; the locked 01-01
    # normalize/config convention decides the sign.
    return round(-age.total_seconds() / 3600)


def offset_drift_detected(cfg, freshly_validated: int) -> bool:
    """True when a freshly validated offset differs from the configured one."""
    return freshly_validated != cfg.broker_offset_hours


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _poll_once_and_report(cfg) -> int:
    """Open the meta DB, run one poll cycle, close the DB, return new-row count."""
    conn = meta_store.connect(Path(cfg.meta_db))
    try:
        stored = run_poll_cycle(cfg, conn)
    finally:
        conn.close()
    log.info("poll cycle stored %d new bar row(s)", stored)
    return stored


def main(argv: list[str] | None = None) -> int:
    """Collector CLI: `uv run python -m ai_trading.collector --once [--config PATH]`.

    --once: connect_and_verify -> warn on offset drift against a fresh
    validate_offset sample -> one run_poll_cycle -> exit.
    Default (continuous): loop run_poll_cycle, sleeping via
    seconds_until_next_close("M15", ...) with drift-corrected recomputation
    from the current clock each iteration (processing time never accumulates).
    MT5ConnectionError logs the actionable message and exits nonzero.
    """
    parser = argparse.ArgumentParser(
        prog="ai_trading.collector",
        description="Closed-bar MT5 collector (health check + incremental Parquet storage).",
    )
    parser.add_argument(
        "--once", action="store_true", help="run one poll cycle and exit"
    )
    parser.add_argument(
        "--config", default="config.toml", help="path to config.toml (default: %(default)s)"
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )

    try:
        cfg = load_config(Path(args.config))
    except ValueError as exc:
        log.error("invalid configuration: %s", exc)
        return 2

    try:
        connect_and_verify(cfg)
    except MT5ConnectionError as exc:
        log.error("%s", exc)
        return 1

    # Offset drift advisory against a fresh empirical sample (DATA-03). The
    # authoritative validation is the human-confirmed checkpoint; a sample
    # that cannot be taken (e.g. no tick) must not block collection.
    try:
        fresh = validate_offset(cfg, cfg.symbols[0])
        if offset_drift_detected(cfg, fresh):
            log.warning(
                "freshly validated broker offset %d differs from configured "
                "broker_offset_hours %d — confirm and update config.local.toml",
                fresh,
                cfg.broker_offset_hours,
            )
    except MT5DataError as exc:
        log.warning("offset validation unavailable: %s", exc)

    if args.once:
        _poll_once_and_report(cfg)
        return 0

    log.info("continuous collection started (poll after each M15 close)")
    while True:
        _poll_once_and_report(cfg)
        sleep_seconds = seconds_until_next_close(
            "M15", datetime.now(UTC), cfg.poll_delay_seconds
        )
        log.info(
            "sleeping %.1fs until next M15 close + %ss delay",
            sleep_seconds,
            cfg.poll_delay_seconds,
        )
        _time.sleep(sleep_seconds)


if __name__ == "__main__":
    sys.exit(main())
