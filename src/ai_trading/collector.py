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

import logging

from ai_trading import mt5_client
from ai_trading.mt5_client import MT5ConnectionError

log = logging.getLogger(__name__)


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
