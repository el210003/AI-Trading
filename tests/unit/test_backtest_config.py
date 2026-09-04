"""Unit tests for the Phase-3 backtest config knobs: frozen-Config extension,
_REQUIRED_KEYS fail-fast loading, and the validation rejection matrix.

Mirrors test_normalize_and_config.py structure (_write_config + _base_values +
parametrized rejections). No MT5 import anywhere.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ai_trading.config import Config, load_config


def _write_config(tmp: Path, values: dict, name: str = "config.toml") -> Path:
    def toml_value(val: object) -> str:
        # dict -> TOML inline table ("{ K = V }"); json.dumps alone emits JSON
        # object syntax ("K": V) which tomllib rejects (plan 03-01 fix).
        if isinstance(val, dict):
            return "{ " + ", ".join(f"{k} = {json.dumps(v)}" for k, v in val.items()) + " }"
        return json.dumps(val)

    lines = [f"{key} = {toml_value(val)}" for key, val in values.items()]
    path = tmp / name
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _base_values(tmp: Path, **overrides: object) -> dict:
    dummy_terminal = tmp / "terminal64.exe"
    if not dummy_terminal.exists():
        dummy_terminal.write_text("stub terminal for path validation", encoding="utf-8")
    values: dict = {
        "symbols": ["EURUSD"],
        "timeframes": ["M15", "H1", "H4"],
        "terminal_path": str(dummy_terminal),
        "expected_server": "",
        "broker_offset_hours": 3,
        "validated_at": "2026-08-30T00:00:00Z",
        "bars_dir": "data/bars",
        "meta_db": "data/meta/meta.sqlite",
        "init_timeout_ms": 30000,
        "poll_delay_seconds": 3,
        "lookback_bars": 500,
        "min_maxbars": 100000,
        "backfill_max_rounds": 12,
        "backfill_pause_seconds": 0.7,
        "initial_backfill_days": 90,
        # Phase-3 backtest knobs (same values as config.toml)
        "slippage_pips": 0.5,
        "slippage_pips_by_symbol": {},
        "default_spread_points": 20,
        "default_spread_points_by_symbol": {},
        "pip_size": {"EURUSD": 0.0001, "GBPUSD": 0.0001, "USDJPY": 0.01},
        "min_rr": 1.0,
        "time_barrier_bars": 96,
        "wf_train_days": 180,
        "wf_test_days": 30,
        "min_history_days": 30,
        "warmup_bars": 0,
        "htf_warmup_days": 30,
        # Phase-4 ML scoring knobs (same values as config.toml)
        "ml_feature_list_version": 1,
        "ml_calibration_method": "sigmoid",
        "ml_embargo_bars": 0,
        "ml_min_train_labels": 30,
        "ml_cal_train_days": 2,
        "ml_cal_test_days": 1,
        "ml_random_state": 42,
        "ml_n_estimators": 200,
        "ml_num_leaves": 7,
        "ml_min_data_in_leaf": 5,
        "ml_learning_rate": 0.1,
        "ml_retrain_enabled": False,
        "ml_retrain_interval_hours": 24,
        # Phase-5 LLM narrative knobs (same public values as config.toml).
        # llm_api_key is a credential that lives only in gitignored
        # config.local.toml; it is REQUIRED here because load_config treats
        # every llm_* key (including llm_api_key) as part of _REQUIRED_KEYS.
        "llm_enabled": False,
        "llm_base_url": "http://192.168.5.178:8000/v1",
        "llm_model": "deepseek-v4-flash-vision-exp",
        "llm_api_key": "",
        "llm_timeout_ms": 8000,
        "llm_max_tokens": 2048,
        "llm_top_n_contributors": 5,
        "llm_structured_mode": "json_schema",
        "llm_agree_min_confidence": 0.6,
        "llm_max_retries": 1,
    }
    values.update(overrides)
    return values


# ---------------------------------------------------------------------------
# Happy path: every new key loads onto the frozen Config
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_load_config_carries_backtest_knobs(tmp_path):
    path = _write_config(
        tmp_path,
        _base_values(
            tmp_path,
            slippage_pips_by_symbol={"EURUSD": 0.7},
            default_spread_points_by_symbol={"EURUSD": 30},
        ),
    )
    cfg = load_config(path)
    assert cfg.slippage_pips == 0.5
    assert cfg.slippage_pips_by_symbol == {"EURUSD": 0.7}
    assert cfg.default_spread_points == 20
    assert cfg.default_spread_points_by_symbol == {"EURUSD": 30}
    assert cfg.pip_size == {"EURUSD": 0.0001, "GBPUSD": 0.0001, "USDJPY": 0.01}
    assert cfg.min_rr == 1.0
    assert cfg.time_barrier_bars == 96
    assert cfg.wf_train_days == 180
    assert cfg.wf_test_days == 30
    assert cfg.min_history_days == 30
    assert cfg.warmup_bars == 0
    assert cfg.htf_warmup_days == 30
    assert cfg.ml_feature_list_version == 1
    assert cfg.ml_calibration_method == "sigmoid"
    assert cfg.ml_embargo_bars == 0
    assert cfg.ml_min_train_labels == 30
    assert cfg.ml_cal_train_days == 2
    assert cfg.ml_cal_test_days == 1
    assert cfg.ml_random_state == 42
    assert cfg.ml_n_estimators == 200
    assert cfg.ml_num_leaves == 7
    assert cfg.ml_min_data_in_leaf == 5
    assert cfg.ml_learning_rate == 0.1
    assert cfg.ml_retrain_enabled is False
    assert cfg.ml_retrain_interval_hours == 24


@pytest.mark.unit
def test_scalar_defaults_used_when_override_maps_empty(tmp_path):
    cfg = load_config(_write_config(tmp_path, _base_values(tmp_path)))
    assert cfg.slippage_pips_by_symbol == {}
    assert cfg.default_spread_points_by_symbol == {}


# ---------------------------------------------------------------------------
# Rejection matrix: every invalid knob raises ValueError naming the key
# ---------------------------------------------------------------------------

@pytest.mark.unit
@pytest.mark.parametrize(
    ("overrides", "key"),
    [
        ({"slippage_pips": -0.1}, "slippage_pips"),
        ({"min_rr": 0}, "min_rr"),
        ({"default_spread_points": -1}, "default_spread_points"),
        ({"pip_size": {"GBPUSD": 0.0001, "USDJPY": 0.01}}, "pip_size"),
        ({"pip_size": {"EURUSD": 0, "GBPUSD": 0.0001, "USDJPY": 0.01}}, "pip_size"),
        ({"slippage_pips_by_symbol": {"AUDUSD": 0.7}}, "slippage_pips_by_symbol"),
        ({"default_spread_points_by_symbol": {"EURUSD": -5}}, "default_spread_points_by_symbol"),
        ({"time_barrier_bars": 0}, "time_barrier_bars"),
        ({"wf_train_days": 0}, "wf_train_days"),
        ({"wf_test_days": -5}, "wf_test_days"),
        ({"min_history_days": 0}, "min_history_days"),
        ({"warmup_bars": -1}, "warmup_bars"),
        ({"htf_warmup_days": 0}, "htf_warmup_days"),
        ({"ml_embargo_bars": -1}, "ml_embargo_bars"),
        ({"ml_min_train_labels": 0}, "ml_min_train_labels"),
        ({"ml_feature_list_version": 0}, "ml_feature_list_version"),
        ({"ml_cal_train_days": 0}, "ml_cal_train_days"),
        ({"ml_cal_test_days": 0}, "ml_cal_test_days"),
        ({"ml_random_state": -1}, "ml_random_state"),
        ({"ml_n_estimators": 0}, "ml_n_estimators"),
        ({"ml_num_leaves": 0}, "ml_num_leaves"),
        ({"ml_min_data_in_leaf": 0}, "ml_min_data_in_leaf"),
        ({"ml_learning_rate": 0}, "ml_learning_rate"),
        ({"ml_retrain_interval_hours": 0}, "ml_retrain_interval_hours"),
    ],
)
def test_backtest_knob_rejections(tmp_path, overrides, key):
    path = _write_config(tmp_path, _base_values(tmp_path, **overrides))
    with pytest.raises(ValueError, match=key):
        load_config(path)


@pytest.mark.unit
def test_ml_calibration_method_rejects_outside_allowed_set(tmp_path):
    """ml_calibration_method outside {sigmoid, isotonic} refuses load naming
    the allowed set (T-04-04 fail-fast contract)."""
    path = _write_config(tmp_path, _base_values(tmp_path, ml_calibration_method="platt"))
    with pytest.raises(ValueError) as exc:
        load_config(path)
    msg = str(exc.value)
    assert "ml_calibration_method" in msg
    assert "sigmoid" in msg and "isotonic" in msg


@pytest.mark.unit
def test_ml_bool_not_accepted_as_int(tmp_path):
    """Bool-as-int for an ml integer knob is rejected via the _is_int
    discipline (T-04-04: a boolean ml_retrain_interval_hours must refuse)."""
    path = _write_config(tmp_path, _base_values(tmp_path, ml_retrain_interval_hours=True))
    with pytest.raises(ValueError, match="ml_retrain_interval_hours"):
        load_config(path)


@pytest.mark.unit
def test_missing_ml_key_raises_naming_key(tmp_path):
    """A missing ml_* TOML key refuses load naming the key (fail-fast)."""
    values = _base_values(tmp_path)
    del values["ml_n_estimators"]
    path = _write_config(tmp_path, values)
    with pytest.raises(ValueError, match="ml_n_estimators"):
        load_config(path)


@pytest.mark.unit
def test_missing_new_required_key_raises(tmp_path):
    values = _base_values(tmp_path)
    del values["default_spread_points"]
    path = _write_config(tmp_path, values)
    with pytest.raises(ValueError, match="default_spread_points"):
        load_config(path)


# ---------------------------------------------------------------------------
# Direct construction: dataclass defaults keep conftest._make_cfg valid
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_direct_construction_uses_dataclass_defaults(tmp_path):
    """Config(**{fifteen old keys only}) must construct cleanly with the 12
    Phase-3 fields falling back to their dataclass defaults — proves
    tests/conftest.py _make_cfg remains valid WITHOUT modifying conftest."""
    dummy_terminal = tmp_path / "terminal64.exe"
    dummy_terminal.write_text("stub", encoding="utf-8")
    cfg = Config(
        symbols=("EURUSD",),
        timeframes=("M15", "H1", "H4"),
        terminal_path=str(dummy_terminal),
        expected_server="ICMarketsSC-Demo",
        broker_offset_hours=3,
        validated_at="2026-08-30T00:00:00Z",
        bars_dir=Path("data/bars"),
        meta_db=Path("data/meta/meta.sqlite"),
        init_timeout_ms=30000,
        poll_delay_seconds=3,
        lookback_bars=500,
        min_maxbars=100000,
        backfill_max_rounds=12,
        backfill_pause_seconds=0.7,
        initial_backfill_days=90,
    )
    assert cfg.slippage_pips == 0.5
    assert cfg.slippage_pips_by_symbol == {}
    assert cfg.default_spread_points == 20
    assert cfg.default_spread_points_by_symbol == {}
    assert cfg.pip_size == {"EURUSD": 0.0001, "GBPUSD": 0.0001, "USDJPY": 0.01}
    assert cfg.min_rr == 1.0
    assert cfg.time_barrier_bars == 96
    assert cfg.wf_train_days == 180
    assert cfg.wf_test_days == 30
    assert cfg.min_history_days == 30
    assert cfg.warmup_bars == 0
    assert cfg.htf_warmup_days == 30
