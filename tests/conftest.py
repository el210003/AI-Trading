"""Shared test fixtures: synthetic OHLC bar factory + fake MT5 client.

`make_bars` emits TF-aligned, OHLC-sane closed bars with the exact column
layout produced by `ai_trading.normalize.rates_to_dataframe`, so unit tests
never need a running MetaTrader 5 terminal (shared pattern #7).

`FakeMT5Client` exposes the same function surface as `ai_trading.mt5_client`
so collector/store code accepts either the real module or this fake. It
records every public-method call and scripts per-(symbol, timeframe) rate
responses — the hooks downstream plans (01-03) build on without extending
conftest.
"""

from collections import Counter, deque
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from ai_trading.config import Config
from ai_trading.normalize import COLUMNS, TIMEFRAME_MINUTES


def make_bars(
    symbol: str,
    timeframe: str,
    start: datetime,
    count: int,
    offset_hours: int = 3,
) -> pd.DataFrame:
    """Create `count` synthetic bars stepping by the timeframe minutes.

    `start` is a naive broker-server wall-clock datetime and is expected to be
    aligned to the timeframe grid. The raw ``time`` column keeps server wall
    time; ``time_utc = time - offset_hours`` (DATA-03 semantics).
    """
    step = TIMEFRAME_MINUTES[timeframe]
    times = [start + pd.Timedelta(minutes=step * i) for i in range(count)]
    opens = [1.10000 + 0.00010 * i for i in range(count)]
    closes = [open_ + 0.00005 for open_ in opens]
    highs = [max(open_, close_) + 0.00010 for open_, close_ in zip(opens, closes, strict=True)]
    lows = [min(open_, close_) - 0.00010 for open_, close_ in zip(opens, closes, strict=True)]

    df = pd.DataFrame(
        {
            "symbol": [symbol] * count,
            "time": times,
            "time_utc": [t - pd.Timedelta(hours=offset_hours) for t in times],
            "open": opens,
            "high": highs,
            "low": lows,
            "close": closes,
            "tick_volume": list(range(1, count + 1)),  # positive ints
            "spread": list(range(count)),  # non-negative ints
            "real_volume": [0] * count,
        }
    )
    return df[COLUMNS]


def _make_cfg(**overrides) -> Config:
    """Build a frozen Config directly (bypassing load_config/filesystem) with
    healthy defaults; pass keyword overrides per test."""

    defaults = {
        "symbols": ("EURUSD", "GBPUSD", "USDJPY"),
        "timeframes": ("M15", "H1", "H4"),
        "terminal_path": r"C:\FakeTerminals\terminal64.exe",
        "expected_server": "ICMarketsSC-Demo",
        "broker_offset_hours": 3,
        "validated_at": "2026-08-30T00:00:00Z",
        "bars_dir": Path("data/bars"),
        "meta_db": Path("data/meta/meta.sqlite"),
        "init_timeout_ms": 30000,
        "poll_delay_seconds": 3,
        "lookback_bars": 500,
        "min_maxbars": 100000,
        "backfill_max_rounds": 12,
        "backfill_pause_seconds": 0.7,
        "initial_backfill_days": 90,
    }
    return Config(**{**defaults, **overrides})


@pytest.fixture
def make_cfg():
    """Factory fixture returning the Config builder used by collector tests."""
    return _make_cfg


class _Unset:
    """Sentinel distinguishing 'terminal_info not scripted' from an explicit None."""


_UNSET = _Unset()

# Fake account healthy default — fake values, never real credentials.
DEFAULT_FAKE_ACCOUNT = SimpleNamespace(server="ICMarketsSC-Demo", login=12345678)


class FakeMT5Client:
    """Test double with the same surface as ai_trading.mt5_client.

    Scriptable attributes:
    - init_ok: initialize() return value.
    - connected: terminal_info().connected.
    - terminal_info_value: explicit terminal_info() return (None forces the
      terminal_info()-is-None failure path); defaults to a healthy namespace
      reflecting `connected` and `maxbars`.
    - account: account_info() return (None forces the logged-out failure path).
    - select_ok: symbol_select() return value.
    - maxbars: terminal_info().maxbars.
    - error_code / error_msg: last_error() return pair (consulted whenever a
      fetch scripts a None response).
    - tick: symbol_info_tick() return (SimpleNamespace with .time epoch
      seconds, or None).

    Recording hooks (plan 01-03 builds on these without extending conftest):
    - every public method appends (method_name, (args, kwargs)) to `calls`
      and increments `counts[method_name]`, so tests assert exact arguments
      (e.g. start_pos on every rates fetch, identical copy_rates_range
      arguments across retry rounds).

    Response scripting for copy_rates_from_pos / copy_rates_range:
    - script_rates(symbol, timeframe, responses): FIFO deque — one entry
      popped per call, enabling grow-then-stable sequences and
      None-with-error-code-then-data scripts (a popped None is returned as
      None and the caller's last_error() consults error_code/error_msg).
    - set_rates(symbol, timeframe, rates): static fallback used when no deque
      is configured for the key.
    """

    def __init__(
        self,
        *,
        init_ok: bool = True,
        connected: bool = True,
        account=DEFAULT_FAKE_ACCOUNT,
        select_ok: bool = True,
        maxbars: int = 250000,
        error_code: int = -6,
        error_msg: str = "Authorization failed",
        terminal_info_value=_UNSET,
        tick=None,
    ):
        self.init_ok = init_ok
        self.connected = connected
        self.account = account
        self.select_ok = select_ok
        self.maxbars = maxbars
        self.error_code = error_code
        self.error_msg = error_msg
        self.tick = tick
        self.terminal_info_value = terminal_info_value
        self.calls: list[tuple[str, tuple[tuple, dict]]] = []
        self.counts: Counter[str] = Counter()
        self._rates_deques: dict[tuple[str, int], deque] = {}
        self._rates_static: dict[tuple[str, int], object] = {}
        self._scripted_ticks: dict[str, object] = {}
        self.shutdown_called = False

    # -- recording helper ----------------------------------------------------

    def _record(self, name: str, *args, **kwargs) -> None:
        self.calls.append((name, (args, kwargs)))
        self.counts[name] += 1

    # -- response scripting -------------------------------------------------

    def script_rates(self, symbol: str, timeframe: int, responses) -> None:
        """Queue per-(symbol, timeframe) responses; one popped per rates call."""
        self._rates_deques[(symbol, timeframe)] = deque(responses)

    def set_rates(self, symbol: str, timeframe: int, rates) -> None:
        """Static per-(symbol, timeframe) fallback value."""
        self._rates_static[(symbol, timeframe)] = rates

    def script_tick(self, symbol: str, tick) -> None:
        """Static per-symbol tick for symbol_info_tick()."""
        self._scripted_ticks[symbol] = tick

    def _next_rates(self, symbol: str, timeframe: int):
        key = (symbol, timeframe)
        queue = self._rates_deques.get(key)
        if queue:
            return queue.popleft()
        if key in self._rates_static:
            return self._rates_static[key]
        return None

    # -- same function surface as ai_trading.mt5_client ----------------------

    def initialize(self, path=None, timeout_ms=30000, **credentials):
        """Mirrors the real package's permissive initialize signature (it does
        accept login/password/server) ONLY so tests can prove those values
        never leak into raised messages — the adapter never forwards them."""
        self._record("initialize", path=path, timeout_ms=timeout_ms, **credentials)
        return self.init_ok

    def last_error(self):
        self._record("last_error")
        return (self.error_code, self.error_msg)

    def terminal_info(self):
        self._record("terminal_info")
        if self.terminal_info_value is not _UNSET:
            return self.terminal_info_value
        return SimpleNamespace(
            connected=self.connected, maxbars=self.maxbars, name="Fake MT5 Terminal"
        )

    def account_info(self):
        self._record("account_info")
        return self.account

    def symbol_select(self, symbol, enable=True):
        self._record("symbol_select", symbol, enable)
        return self.select_ok

    def copy_rates_from_pos(self, symbol, timeframe, start_pos, count):
        self._record("copy_rates_from_pos", symbol, timeframe, start_pos, count)
        return self._next_rates(symbol, timeframe)

    def copy_rates_range(self, symbol, timeframe, date_from, date_to):
        self._record("copy_rates_range", symbol, timeframe, date_from, date_to)
        return self._next_rates(symbol, timeframe)

    def symbol_info_tick(self, symbol):
        self._record("symbol_info_tick", symbol)
        if symbol in self._scripted_ticks:
            return self._scripted_ticks[symbol]
        return self.tick

    def shutdown(self):
        self._record("shutdown")
        self.shutdown_called = True

    def timeframe_enum(self, name):
        self._record("timeframe_enum", name)
        # Stable minute-based sentinels; unit tests only assert routing
        # consistency (start_pos/count), never the raw constant value.
        return TIMEFRAME_MINUTES[name]


@pytest.fixture
def fake_mt5() -> FakeMT5Client:
    """Healthy default fake: initialize ok, connected, account present,
    symbols selectable, maxbars well above min_maxbars."""
    return FakeMT5Client()
