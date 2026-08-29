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
from dataclasses import dataclass
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
    )
    _validate(cfg)
    if not cfg.validated_at:
        # First empirical validation happens in plan 01-02; warn, do not fail.
        log.warning("broker offset not yet validated")
    return cfg


def _is_int(value: object) -> bool:
    """True int (not bool) check — bool is a subclass of int in Python."""
    return isinstance(value, int) and not isinstance(value, bool)


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
