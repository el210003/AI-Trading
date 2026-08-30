"""Thin MT5 adapter — the ONLY module in the codebase that imports
MetaTrader5 (exactly once, at module top). Every other module goes through
this wrapper; tests inject a fake exposing the same function surface
(tests/conftest.py FakeMT5Client).

Pattern of record: RESEARCH.md Architecture Pattern 1 "Thin MT5 Adapter
(import-swap testability)". Importing this module does NOT connect to a
terminal — connection happens only in initialize().

Constants and error taxonomy per RESEARCH.md Code Example 1:
- AUTH_FAILED (-6): terminal is up but no account is authorized.
- NO_HISTORY (-4): no history / not ready yet (retry/stop-walk signal).
- AUTO_TRADING_DISABLED (-8): automated quoting/trading disabled.

Credential rule (ASVS V7, threat T-1-05): initialize keyword-argument values
must never be embedded in any exception message, log line, or repr. This
adapter's initialize deliberately exposes NO login/password/server parameters
at all — the terminal's saved credentials remain the authentication path.
"""

from __future__ import annotations

import MetaTrader5 as mt5

AUTH_FAILED = -6
NO_HISTORY = -4
AUTO_TRADING_DISABLED = -8

TIMEFRAME_ALIASES: dict[str, int] = {
    "M15": mt5.TIMEFRAME_M15,
    "H1": mt5.TIMEFRAME_H1,
    "H4": mt5.TIMEFRAME_H4,
}


class MT5ConnectionError(RuntimeError):
    """Connection/health-check failure (terminal state, account, server, symbol)."""


class MT5DataError(RuntimeError):
    """Data-fetch failure (copy_rates_* returned None/empty unexpectedly)."""


def initialize(path: str | None = None, timeout_ms: int = 30000) -> bool:
    """Connect to the terminal at `path` (Pitfall 8: never auto-discover).

    The path is passed to the underlying package only when non-empty.
    Deliberately accepts no credential parameters — terminal-saved credentials
    are the authentication path, and nothing here can leak them.
    """
    if path:
        return bool(mt5.initialize(path=path, timeout=timeout_ms))
    return bool(mt5.initialize(timeout=timeout_ms))


def last_error() -> tuple[int, str]:
    """(code, description) of the last MT5 API error."""
    code, description = mt5.last_error()
    return int(code), str(description)


def terminal_info():
    """Terminal state namedtuple-ish (connected, maxbars, ...) or None."""
    return mt5.terminal_info()


def account_info():
    """Authorized trade account info or None when logged out."""
    return mt5.account_info()


def symbol_select(symbol: str, enable: bool = True) -> bool:
    """Select a symbol in Market Watch (makes history/ticks available)."""
    return bool(mt5.symbol_select(symbol, enable))


def copy_rates_from_pos(symbol: str, timeframe: int, start_pos: int, count: int):
    """Bars counting back from `start_pos` (0 = still-forming bar — never use 0
    on the collection path). Returns a numpy structured array or None."""
    return mt5.copy_rates_from_pos(symbol, timeframe, start_pos, count)


def copy_rates_range(symbol: str, timeframe: int, date_from, date_to):
    """Bars in the inclusive [date_from, date_to] range, or None (code -4 when
    out of range / not yet downloaded)."""
    return mt5.copy_rates_range(symbol, timeframe, date_from, date_to)


def symbol_info_tick(symbol: str):
    """Last tick for `symbol` (.time = server pseudo-UTC epoch seconds) or None."""
    return mt5.symbol_info_tick(symbol)


def shutdown() -> None:
    """Close the connection to the terminal (no-op safe to call once)."""
    mt5.shutdown()


def timeframe_enum(name: str) -> int:
    """Map a config timeframe name ("M15"/"H1"/"H4") to the mt5.TIMEFRAME_* int."""
    try:
        return TIMEFRAME_ALIASES[name]
    except KeyError:
        raise ValueError(
            f"unknown timeframe {name!r}: expected one of {sorted(TIMEFRAME_ALIASES)}"
        ) from None
