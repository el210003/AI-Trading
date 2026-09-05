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
    # ML scoring knobs (Phase 4) — same fail-fast contract: a typo'd or missing
    # ml_* key refuses load rather than silently changing training semantics.
    "ml_feature_list_version",
    "ml_calibration_method",
    "ml_embargo_bars",
    "ml_min_train_labels",
    "ml_cal_train_days",
    "ml_cal_test_days",
    "ml_random_state",
    "ml_n_estimators",
    "ml_num_leaves",
    "ml_min_data_in_leaf",
    "ml_learning_rate",
    "ml_retrain_enabled",
    "ml_retrain_interval_hours",
    # LLM narrative knobs (Phase 5) — same fail-fast contract: a typo'd or
    # missing llm_* key refuses load rather than silently changing the provider
    # or structured-output contract. llm_api_key is a credential (ASVS V14) and
    # lives only in gitignored config.local.toml, never committed config.toml.
    "llm_enabled",
    "llm_base_url",
    "llm_model",
    "llm_api_key",
    "llm_timeout_ms",
    "llm_max_tokens",
    "llm_top_n_contributors",
    "llm_structured_mode",
    "llm_agree_min_confidence",
    "llm_max_retries",
    # Setup-assembly / lifecycle knobs (Phase 6) — same fail-fast contract: a
    # typo'd or missing setup_* key refuses load rather than silently changing
    # the trigger-window or qualification semantics.
    "setup_trigger_window_bars",
    "setup_min_p_win",
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
    # ML scoring knobs (Phase 4). Fields carry defaults so direct construction
    # (tests/conftest.py _make_cfg) keeps working unchanged.
    ml_feature_list_version: int = 1
    ml_calibration_method: str = "sigmoid"
    ml_embargo_bars: int = 0
    ml_min_train_labels: int = 30
    ml_cal_train_days: int = 2
    ml_cal_test_days: int = 1
    ml_random_state: int = 42
    ml_n_estimators: int = 200
    ml_num_leaves: int = 7
    ml_min_data_in_leaf: int = 5
    ml_learning_rate: float = 0.1
    # Retrain schedule: ml_retrain_enabled / ml_retrain_interval_hours are
    # consumed by the Phase 6 scheduler. Phase 4 only validates them.
    ml_retrain_enabled: bool = False
    ml_retrain_interval_hours: int = 24
    # LLM narrative knobs (Phase 5). Fields carry defaults so direct
    # construction (tests/conftest.py _make_cfg) keeps working unchanged.
    # llm_api_key is a credential: it is never written to committed
    # config.toml, never repr'd (modules-importing-Config never print it), and
    # defaults to "" so offline (disabled) runs need no secret.
    llm_enabled: bool = False
    llm_base_url: str = "http://192.168.5.178:8000/v1"
    llm_model: str = "deepseek-v4-flash-vision-exp"
    llm_api_key: str = ""
    llm_timeout_ms: int = 8000
    llm_max_tokens: int = 2048
    llm_top_n_contributors: int = 5
    llm_structured_mode: str = "json_schema"
    llm_agree_min_confidence: float = 0.6
    llm_max_retries: int = 1
    # Setup-assembly / lifecycle knobs (Phase 6). Fields carry defaults so
    # direct construction (tests/conftest.py _make_cfg) keeps working.
    # setup_trigger_window_bars: D-04 pending-phase window in M15 bars (default
    #   8) before an untriggered setup expires.
    # setup_min_p_win: engine-side qualification floor; 0.0 = persist every
    #   detector-passing candidate (the dashboard's min-probability display
    #   filter is separate).
    setup_trigger_window_bars: int = 8
    setup_min_p_win: float = 0.0
    # Collect-only symbols (weekend data feed, e.g. crypto): setup_symbols
    # restricts which collected symbols the setup engine assembles/lifecycle-
    # resolves for. Empty (default, and absent in TOML) = every configured
    # symbol is setup-eligible — the v1 behavior.
    setup_symbols: tuple[str, ...] = ()

    @property
    def engine_symbols(self) -> tuple[str, ...]:
        """Symbols the setup engine (and the default backtest universe) works
        on: ``setup_symbols`` when set, else all collected ``symbols``."""
        return self.setup_symbols if self.setup_symbols else self.symbols


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
        ml_feature_list_version=raw["ml_feature_list_version"],
        ml_calibration_method=raw["ml_calibration_method"],
        ml_embargo_bars=raw["ml_embargo_bars"],
        ml_min_train_labels=raw["ml_min_train_labels"],
        ml_cal_train_days=raw["ml_cal_train_days"],
        ml_cal_test_days=raw["ml_cal_test_days"],
        ml_random_state=raw["ml_random_state"],
        ml_n_estimators=raw["ml_n_estimators"],
        ml_num_leaves=raw["ml_num_leaves"],
        ml_min_data_in_leaf=raw["ml_min_data_in_leaf"],
        ml_learning_rate=raw["ml_learning_rate"],
        ml_retrain_enabled=raw["ml_retrain_enabled"],
        ml_retrain_interval_hours=raw["ml_retrain_interval_hours"],
        llm_enabled=raw["llm_enabled"],
        llm_base_url=str(raw["llm_base_url"]),
        llm_model=str(raw["llm_model"]),
        llm_api_key=str(raw["llm_api_key"]),
        llm_timeout_ms=raw["llm_timeout_ms"],
        llm_max_tokens=raw["llm_max_tokens"],
        llm_top_n_contributors=raw["llm_top_n_contributors"],
        llm_structured_mode=str(raw["llm_structured_mode"]),
        llm_agree_min_confidence=raw["llm_agree_min_confidence"],
        llm_max_retries=raw["llm_max_retries"],
        setup_trigger_window_bars=raw["setup_trigger_window_bars"],
        setup_min_p_win=raw["setup_min_p_win"],
        setup_symbols=tuple(raw["setup_symbols"]) if "setup_symbols" in raw else (),
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

    # setup_symbols (optional collect-only split): every entry must pass the
    # symbol contract AND be a collected symbol — a setup symbol that is not
    # collected could never assemble.
    for sym in cfg.setup_symbols:
        if not isinstance(sym, str) or not _SYMBOL_RE.match(sym):
            raise ValueError(
                f"setup_symbols entry {sym!r} invalid: expected six uppercase letters "
                "(optionally .broker-suffix), e.g. EURUSD or EURUSD.a"
            )
    unknown_setup = [sym for sym in cfg.setup_symbols if sym not in cfg.symbols]
    if unknown_setup:
        raise ValueError(
            f"setup_symbols entries must be configured symbols (collected); "
            f"unknown: {', '.join(unknown_setup)}"
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
    # their pip size through the base name. Scoped to the engine universe: a
    # collect-only symbol (setup_symbols split) never enters the cost model.
    missing_pip = [
        sym
        for sym in cfg.engine_symbols
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

    # -- ML scoring knobs (Phase 4, AI-01..AI-04) ---------------------------
    # Fail-fast: a typo'd/out-of-domain ml_* key refuses load naming the field
    # and (where applicable) the allowed set. Reuses the _is_int/_is_number
    # discipline so bool-as-int is rejected.
    allowed_calibration = {"sigmoid", "isotonic"}
    if not _is_int(cfg.ml_feature_list_version) or cfg.ml_feature_list_version <= 0:
        raise ValueError(
            f"ml_feature_list_version must be a positive integer, "
            f"got {cfg.ml_feature_list_version!r}"
        )
    if cfg.ml_calibration_method not in allowed_calibration:
        raise ValueError(
            f"ml_calibration_method must be one of {sorted(allowed_calibration)}, "
            f"got {cfg.ml_calibration_method!r}"
        )
    if not _is_int(cfg.ml_embargo_bars) or cfg.ml_embargo_bars < 0:
        raise ValueError(
            f"ml_embargo_bars must be an integer >= 0 (0 = purge-only), got {cfg.ml_embargo_bars!r}"
        )
    if not _is_int(cfg.ml_min_train_labels) or cfg.ml_min_train_labels < 1:
        raise ValueError(
            f"ml_min_train_labels must be an integer >= 1, got {cfg.ml_min_train_labels!r}"
        )
    for name, value in (
        ("ml_cal_train_days", cfg.ml_cal_train_days),
        ("ml_cal_test_days", cfg.ml_cal_test_days),
    ):
        if not _is_int(value) or value <= 0:
            raise ValueError(f"{name} must be a positive integer, got {value!r}")
    if not _is_int(cfg.ml_random_state) or cfg.ml_random_state < 0:
        raise ValueError(
            f"ml_random_state must be an integer >= 0, got {cfg.ml_random_state!r}"
        )
    for name, value in (
        ("ml_n_estimators", cfg.ml_n_estimators),
        ("ml_num_leaves", cfg.ml_num_leaves),
        ("ml_min_data_in_leaf", cfg.ml_min_data_in_leaf),
    ):
        if not _is_int(value) or value <= 0:
            raise ValueError(f"{name} must be a positive integer, got {value!r}")
    if not _is_number(cfg.ml_learning_rate) or cfg.ml_learning_rate <= 0:
        raise ValueError(
            f"ml_learning_rate must be a number > 0, got {cfg.ml_learning_rate!r}"
        )
    if not isinstance(cfg.ml_retrain_enabled, bool):
        raise ValueError(
            f"ml_retrain_enabled must be a boolean, got {cfg.ml_retrain_enabled!r}"
        )
    if not _is_int(cfg.ml_retrain_interval_hours) or cfg.ml_retrain_interval_hours <= 0:
        raise ValueError(
            f"ml_retrain_interval_hours must be a positive integer, "
            f"got {cfg.ml_retrain_interval_hours!r}"
        )

    # -- LLM narrative knobs (Phase 5, AI-05..AI-07) ------------------------
    # Fail-fast: an out-of-domain llm_* key refuses load naming the field and
    # (where applicable) the allowed set. Reuses the _is_int/_is_number
    # discipline so bool-as-int is rejected. llm_structured_mode gates the
    # response_format the provider sends (RESEARCH Pitfall 4: some stacks
    # reject json_schema) — pydantic re-validation stays the authority.
    allowed_structured_mode = {"json_schema", "json_object", "none"}
    if not isinstance(cfg.llm_enabled, bool):
        raise ValueError(f"llm_enabled must be a boolean, got {cfg.llm_enabled!r}")
    if cfg.llm_structured_mode not in allowed_structured_mode:
        raise ValueError(
            f"llm_structured_mode must be one of {sorted(allowed_structured_mode)}, "
            f"got {cfg.llm_structured_mode!r}"
        )
    if not _is_int(cfg.llm_timeout_ms) or cfg.llm_timeout_ms <= 0:
        raise ValueError(
            f"llm_timeout_ms must be a positive integer, got {cfg.llm_timeout_ms!r}"
        )
    # Reasoning-model budget guard (RESEARCH Pitfall 1): the local vLLM serves a
    # reasoning model that burns max_tokens on chain-of-thought; below 2048 the
    # answer lands in content=None with finish_reason="length". Fail-fast here.
    if not _is_int(cfg.llm_max_tokens) or cfg.llm_max_tokens < 2048:
        raise ValueError(
            f"llm_max_tokens must be an integer >= 2048 (reasoning-model token "
            f"budget), got {cfg.llm_max_tokens!r}"
        )
    if not _is_int(cfg.llm_top_n_contributors) or cfg.llm_top_n_contributors < 1:
        raise ValueError(
            f"llm_top_n_contributors must be an integer >= 1, "
            f"got {cfg.llm_top_n_contributors!r}"
        )
    if not _is_number(cfg.llm_agree_min_confidence) or not 0 <= cfg.llm_agree_min_confidence <= 1:
        raise ValueError(
            f"llm_agree_min_confidence must be a number in [0,1], "
            f"got {cfg.llm_agree_min_confidence!r}"
        )
    if not _is_int(cfg.llm_max_retries) or cfg.llm_max_retries < 1:
        raise ValueError(
            f"llm_max_retries must be an integer >= 1, got {cfg.llm_max_retries!r}"
        )

    # -- Setup-assembly / lifecycle knobs (Phase 6, SETUP-01..04) ------------
    # setup_trigger_window_bars (D-04): the pending-phase window in M15 bars
    # before an untriggered setup expires; must be a positive int.
    # setup_min_p_win: engine-side qualification floor; must be a number in
    # [0,1] (0.0 = persist every detector-passing candidate).
    if not _is_int(cfg.setup_trigger_window_bars) or cfg.setup_trigger_window_bars <= 0:
        raise ValueError(
            f"setup_trigger_window_bars must be a positive integer, "
            f"got {cfg.setup_trigger_window_bars!r}"
        )
    if not _is_number(cfg.setup_min_p_win) or not 0 <= cfg.setup_min_p_win <= 1:
        raise ValueError(
            f"setup_min_p_win must be a number in [0,1], got {cfg.setup_min_p_win!r}"
        )
