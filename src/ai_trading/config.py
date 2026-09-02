"""Config loading + fail-fast validation (DATA-03: the validated broker offset
lives here and is the ONLY offset source for UTC math in normalize.py).

Pattern of record: RESEARCH.md "Don't Hand-Roll" config row + Security V5/V7/V14
— tomllib load of config.toml with gitignored config.local.toml overrides
shallow-merged (local wins), into a frozen dataclass that validates every
field at startup. Violations raise ValueError naming the offending field.
The full Config is never printed or repr'd (credential hygiene, V7).
"""

from __future__ import annotations

import logging
import os
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

# Six uppercase letters with an optional ".<broker-suffix>" (e.g. EURUSD.a).
# Deliberately wider than research assumption A5: plan 01-02 Task 1 writes
# human-confirmed suffixed names, and symbol_select still fails loudly later.
_SYMBOL_RE = re.compile(r"^[A-Z]{6}(\.[A-Za-z0-9]+)?$")
_ALLOWED_TIMEFRAMES = frozenset({"M15", "H1", "H4"})

_REQUIRED_KEYS = (
    "symbols",
    "timeframes",
    "terminal_path",
    "expected_server",
    "broker_offset_hours",
    "validated_at",
    "bars_dir",
    "meta_db",
    "init_timeout_ms",
    "poll_delay_seconds",
    "lookback_bars",
    "min_maxbars",
    "backfill_max_rounds",
    "backfill_pause_seconds",
    "initial_backfill_days",
    # Backtest / labeling knobs (Phase 3) — fail-fast: a typo'd or missing key
    # refuses load, same contract as every collector key above.
    "slippage_pips",
    "slippage_pips_by_symbol",
    "default_spread_points",
    "default_spread_points_by_symbol",
    "pip_size",
    "min_rr",
    "time_barrier_bars",
    "wf_train_days",
    "wf_test_days",
    "min_history_days",
    "warmup_bars",
    "htf_warmup_days",
)


@dataclass(frozen=True)
class Config:
    symbols: tuple[str, ...]
    timeframes: tuple[str, ...]
    terminal_path: str
    expected_server: str
    broker_offset_hours: int
    validated_at: str
    bars_dir: Path
    meta_db: Path
    init_timeout_ms: int
    poll_delay_seconds: float
    lookback_bars: int
    min_maxbars: int
    backfill_max_rounds: int
    backfill_pause_seconds: float
    initial_backfill_days: int
    # Backtest / labeling knobs (Phase 3). Fields carry defaults so direct
    # construction (tests/conftest.py _make_cfg) keeps working unchanged.
    slippage_pips: float = 0.5
    slippage_pips_by_symbol: dict[str, float] = field(default_factory=dict)
    default_spread_points: int = 20
    default_spread_points_by_symbol: dict[str, int] = field(default_factory=dict)
    pip_size: dict[str, float] = field(
        default_factory=lambda: {"EURUSD": 0.0001, "GBPUSD": 0.0001, "USDJPY": 0.01}
    )
    min_rr: float = 1.0
    time_barrier_bars: int = 96
    wf_train_days: int = 180
    wf_test_days: int = 30
    min_history_days: int = 30
    warmup_bars: int = 0
    htf_warmup_days: int = 30


def load_config(base: Path = Path("config.toml")) -> Config:
    """Load base TOML, shallow-merge the sibling config.local.toml (local wins),
    construct the frozen Config, and fail fast on any invalid value."""
    base = Path(base)
    if not base.exists():
        raise ValueError(f"config file not found: {base}")
    with open(base, "rb") as fh:
        raw: dict[str, Any] = tomllib.load(fh)

    local = base.parent / "config.local.toml"
    if local.exists():
        with open(local, "rb") as fh:
            raw = {**raw, **tomllib.load(fh)}  # shallow merge, local values win

    missing = [key for key in _REQUIRED_KEYS if key not in raw]
    if missing:
        raise ValueError(f"missing required config key(s): {', '.join(missing)}")

    cfg = Config(
        symbols=tuple(raw["symbols"]),
        timeframes=tuple(raw["timeframes"]),
        terminal_path=str(raw["terminal_path"]),
        expected_server=str(raw["expected_server"]),
        broker_offset_hours=raw["broker_offset_hours"],
        validated_at=str(raw["validated_at"]),
        bars_dir=Path(raw["bars_dir"]),
        meta_db=Path(raw["meta_db"]),
        init_timeout_ms=raw["init_timeout_ms"],
        poll_delay_seconds=raw["poll_delay_seconds"],
        lookback_bars=raw["lookback_bars"],
        min_maxbars=raw["min_maxbars"],
        backfill_max_rounds=raw["backfill_max_rounds"],
        backfill_pause_seconds=raw["backfill_pause_seconds"],
        initial_backfill_days=raw["initial_backfill_days"],
        slippage_pips=raw["slippage_pips"],
        slippage_pips_by_symbol=dict(raw["slippage_pips_by_symbol"]),
        default_spread_points=raw["default_spread_points"],
        default_spread_points_by_symbol=dict(raw["default_spread_points_by_symbol"]),
        pip_size=dict(raw["pip_size"]),
        min_rr=raw["min_rr"],
        time_barrier_bars=raw["time_barrier_bars"],
        wf_train_days=raw["wf_train_days"],
        wf_test_days=raw["wf_test_days"],
        min_history_days=raw["min_history_days"],
        warmup_bars=raw["warmup_bars"],
        htf_warmup_days=raw["htf_warmup_days"],
    )
    _validate(cfg)
    if not cfg.validated_at:
        # First empirical validation happens in plan 01-02; warn, do not fail.
        log.warning("broker offset not yet validated")
    return cfg


def _is_int(value: object) -> bool:
    """True int (not bool) check — bool is a subclass of int in Python."""
    return isinstance(value, int) and not isinstance(value, bool)


def _base_symbol(symbol: str) -> str:
    """Strip the optional ``.broker-suffix`` from a configured symbol
    (``EURUSD.a`` -> ``EURUSD``); base names pass through unchanged."""
    return symbol.split(".", 1)[0]


def _validate(cfg: Config) -> None:
    if not cfg.symbols:
        raise ValueError("symbols must be a non-empty list")
    for sym in cfg.symbols:
        if not isinstance(sym, str) or not _SYMBOL_RE.match(sym):
            raise ValueError(
                f"symbols entry {sym!r} invalid: expected six uppercase letters "
                "(optionally .broker-suffix), e.g. EURUSD or EURUSD.a"
            )

    if not cfg.timeframes:
        raise ValueError("timeframes must be a non-empty list")
    bad_tfs = set(cfg.timeframes) - _ALLOWED_TIMEFRAMES
    if bad_tfs:
        raise ValueError(
            f"timeframes entries {sorted(bad_tfs)} not in allowed set {sorted(_ALLOWED_TIMEFRAMES)}"
        )

    if not _is_int(cfg.broker_offset_hours) or not -14 <= cfg.broker_offset_hours <= 14:
        raise ValueError(
            f"broker_offset_hours must be an int within -14..14, got {cfg.broker_offset_hours!r}"
        )

    # Pitfall 8: never let initialize() find its own terminal — require a real path.
    if not cfg.terminal_path:
        raise ValueError(
            "terminal_path must be set (config.local.toml override); refuse terminal auto-discovery"
        )
    if not os.path.exists(cfg.terminal_path):
        raise ValueError(f"terminal_path does not exist: {cfg.terminal_path!r}")

    for name, value in (
        ("min_maxbars", cfg.min_maxbars),
        ("lookback_bars", cfg.lookback_bars),
        ("initial_backfill_days", cfg.initial_backfill_days),
    ):
        if not _is_int(value) or value <= 0:
            raise ValueError(f"{name} must be a positive integer, got {value!r}")

    if cfg.poll_delay_seconds < 0:
        raise ValueError(f"poll_delay_seconds must be >= 0, got {cfg.poll_delay_seconds!r}")
    if not _is_int(cfg.backfill_max_rounds) or cfg.backfill_max_rounds < 2:
        raise ValueError(
            f"backfill_max_rounds must be an integer >= 2, got {cfg.backfill_max_rounds!r}"
        )
    if cfg.backfill_pause_seconds <= 0:
        raise ValueError(f"backfill_pause_seconds must be > 0, got {cfg.backfill_pause_seconds!r}")

    # -- Backtest / labeling knobs (Phase 3) --------------------------------
    # Numbers are checked as numeric-with-bound rather than strictly float so
    # integer TOML literals (e.g. slippage_pips = 1) load; bools are rejected
    # because bool is a subclass of int (same discipline as _is_int).

    def _is_number(value: object) -> bool:
        return isinstance(value, (int, float)) and not isinstance(value, bool)

    if not _is_number(cfg.slippage_pips) or cfg.slippage_pips < 0:
        raise ValueError(f"slippage_pips must be a number >= 0, got {cfg.slippage_pips!r}")
    if not _is_number(cfg.min_rr) or cfg.min_rr <= 0:
        raise ValueError(f"min_rr must be a number > 0, got {cfg.min_rr!r}")
    if not _is_int(cfg.default_spread_points) or cfg.default_spread_points < 0:
        raise ValueError(
            f"default_spread_points must be an integer >= 0, got {cfg.default_spread_points!r}"
        )

    if not isinstance(cfg.pip_size, dict):
        raise ValueError(f"pip_size must be a dict of symbol -> pip size, got {cfg.pip_size!r}")
    # Suffixed broker symbols (e.g. EURUSD.a, Phase 1 suffix contract) resolve
    # their pip size through the base name.
    missing_pip = [
        sym
        for sym in cfg.symbols
        if sym not in cfg.pip_size and _base_symbol(sym) not in cfg.pip_size
    ]
    if missing_pip:
        raise ValueError(
            f"pip_size must include every configured symbol; missing: {', '.join(missing_pip)}"
        )
    for sym, size in cfg.pip_size.items():
        if not _is_number(size) or size <= 0:
            raise ValueError(f"pip_size[{sym!r}] must be a number > 0, got {size!r}")

    for name, mapping in (
        ("slippage_pips_by_symbol", cfg.slippage_pips_by_symbol),
        ("default_spread_points_by_symbol", cfg.default_spread_points_by_symbol),
    ):
        if not isinstance(mapping, dict):
            raise ValueError(f"{name} must be a dict of symbol -> value, got {mapping!r}")
        for sym, value in mapping.items():
            if sym not in cfg.symbols and _base_symbol(sym) not in cfg.symbols:
                raise ValueError(f"{name} key {sym!r} is not a configured symbol")
            if not _is_number(value) or value < 0:
                raise ValueError(f"{name}[{sym!r}] must be a number >= 0, got {value!r}")

    for name, value in (
        ("time_barrier_bars", cfg.time_barrier_bars),
        ("wf_train_days", cfg.wf_train_days),
        ("wf_test_days", cfg.wf_test_days),
        ("min_history_days", cfg.min_history_days),
        ("htf_warmup_days", cfg.htf_warmup_days),
    ):
        if not _is_int(value) or value <= 0:
            raise ValueError(f"{name} must be a positive integer, got {value!r}")

    if not _is_int(cfg.warmup_bars) or cfg.warmup_bars < 0:
        raise ValueError(
            f"warmup_bars must be an integer >= 0 (0 = auto-compute), got {cfg.warmup_bars!r}"
        )
