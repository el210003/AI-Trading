"""Phase-6 dashboard test fixtures — local helpers built over the existing
``_setup_fixtures`` / ``conftest`` chain (direct import, never extended).
Consumed by ``test_dashboard_data.py`` (pure data-layer) and the Streamlit
``AppTest`` suites in ``tests/ui/``.

Helpers:
- ``dashboard_cfg``: frozen Config with ``bars_dir``/``meta_db`` under a tmp
  data root (so ``load_setups``/``load_bars`` read an isolated store).
- ``write_setups``: persist a setup frame into ``tmp_path/data/setups`` (via
  ``setup.store.upsert_setups``) and return the cfg.
- ``rich_evidence_json`` / ``make_verified_row`` / ``make_unavailable_row``:
  build a setup row whose ``evidence_json`` carries the full evidence object
  (top contributors, bias, zone, sweep) and either a verified narrative or the
  labeled ML-only fallback.
- ``write_app_config``: write a valid, loadable ``config.toml`` (with a real
  dummy terminal file) so ``AppTest`` can boot ``app.py`` offline.

All helpers return new structures / never mutate inputs.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
from _setup_fixtures import make_setup_frame, setup_cfg

from ai_trading.setup import store as setup_store

__all__ = [
    "dashboard_cfg",
    "write_setups",
    "rich_evidence_json",
    "make_verified_row",
    "make_unavailable_row",
    "write_app_config",
    "make_contributors",
]


def dashboard_cfg(tmp_path, **overrides) -> Any:
    """Frozen Config pointing ``bars_dir``/``meta_db`` under ``tmp_path`` so
    tests read an isolated runtime store (never ``config.toml`` on disk)."""
    data = tmp_path / "data"
    defaults = {
        "bars_dir": data / "bars",
        "meta_db": data / "meta" / "meta.sqlite",
    }
    return setup_cfg(**{**defaults, **overrides})


def write_setups(tmp_path, rows: list[dict]) -> Any:
    """Persist ``rows`` into ``tmp_path/data/setups/setups.parquet`` via the
    store's single write path and return the cfg for reads."""
    cfg = dashboard_cfg(tmp_path)
    setup_store.upsert_setups(cfg, make_setup_frame(rows))
    return cfg


def make_contributors() -> list[dict]:
    """A deterministic top-5 ``top_contributors`` list matching the
    ``serialize_evidence`` ``{feature, contribution, effect}`` shape."""
    return [
        {"feature": "swing_strength", "contribution": 0.18, "effect": "positive"},
        {"feature": "zone_quality", "contribution": -0.12, "effect": "negative"},
        {"feature": "atr_norm", "contribution": 0.09, "effect": "positive"},
        {"feature": "bias_h1_align", "contribution": 0.05, "effect": "positive"},
        {"feature": "vol_regime", "contribution": -0.03, "effect": "negative"},
    ]


def rich_evidence_json(*, p_win: float = 0.62, score_source: str = "ml") -> str:
    """A full evidence object as JSON (keys matching ``serialize_evidence``)."""
    evidence = {
        "symbol": "EURUSD",
        "timeframe": "M15",
        "direction": "long",
        "zone_id": "z-001",
        "zone_state": "mitigated",
        "event_id": "ev-001",
        "pool_id": "p-001",
        "sweep_side": "low",
        "bias_h1": "bullish",
        "bias_h4": "bullish",
        "entry": 1.10000,
        "sl": 1.09500,
        "tp": 1.12000,
        "rr_at_decision": 4.0,
        "sl_price": 1.09500,
        "tp_price": 1.12000,
        "p_win": p_win,
        "score_source": score_source,
        "artifact_version": 1,
        "top_contributors": make_contributors(),
    }
    return json.dumps(evidence)


def _base_row(**overrides) -> dict:
    """Common setup row defaults carrying a rich evidence object."""
    row = {
        "setup_id": "s-0001",
        "symbol": "EURUSD",
        "timeframe": "M15",
        "direction": "long",
        "entry": 1.10000,
        "sl_price": 1.09500,
        "tp_price": 1.12000,
        "rr_at_decision": 4.0,
        "entry_bar_idx": 36,
        "created_at": pd.Timestamp("2026-08-20T09:00:00"),
        "zone_id": "z-001",
        "event_id": "ev-001",
        "pool_id": "p-001",
        "zone_range_high": 1.10500,
        "zone_range_low": 1.09800,
        "zone_state": "mitigated",
        "bias_h1": "bullish",
        "bias_h4": "bullish",
        "p_win": 0.62,
        "score_source": "ml",
        "artifact_version": 1,
        "evidence_json": rich_evidence_json(),
        "narrative_status": "llm_unavailable",
        "narrative_reason": "llm_disabled",
        "narrative_verdict": pd.NA,
        "narrative_confidence": float("nan"),
        "narrative_reasoning": pd.NA,
        "narrative_citations": pd.NA,
        "agreement": pd.NA,
        "agreement_confidence": float("nan"),
        "status": "pending",
        "outcome": pd.NA,
        "trigger_time": pd.NaT,
        "trigger_bar_idx": float("nan"),
        "closed_at": pd.NaT,
        "exit_price": float("nan"),
        "exit_time": pd.NaT,
        "exit_idx": float("nan"),
        "r_gross": float("nan"),
        "r_raw": float("nan"),
        "r_net": float("nan"),
    }
    row.update(overrides)
    return row


def make_verified_row(**overrides) -> dict:
    """A setup row with a verified narrative (narrative_status='ok')."""
    row = _base_row(
        status="active",
        evidence_json=rich_evidence_json(score_source="ml_llm"),
        score_source="ml_llm",
        narrative_status="ok",
        narrative_reason=pd.NA,
        narrative_verdict="confirm",
        narrative_confidence=0.7,
        narrative_reasoning="H4 premium mitigates into the tapped zone; structure agrees.",
        narrative_citations=json.dumps(["symbol", "direction", "zone_id"]),
        agreement="agree",
        agreement_confidence=0.8,
    )
    row.update(overrides)
    return row


def make_unavailable_row(**overrides) -> dict:
    """A setup row with the labeled ML-only fallback narrative."""
    row = _base_row(
        status="pending",
        evidence_json=rich_evidence_json(score_source="ml"),
        score_source="ml",
        narrative_status="llm_unavailable",
        narrative_reason="timeout",
        narrative_verdict=pd.NA,
        narrative_confidence=float("nan"),
        narrative_reasoning=pd.NA,
        narrative_citations=pd.NA,
        agreement=pd.NA,
        agreement_confidence=float("nan"),
    )
    row.update(overrides)
    return row


def write_app_config(config_path: Path, *, bars_dir: Path, meta_db: Path,
                     symbols=("EURUSD", "GBPUSD", "USDJPY"),
                     terminal_file: Path | None = None) -> Path:
    """Write a valid, loadable ``config.toml`` (all ``_REQUIRED_KEYS`` present)
    plus a dummy terminal file (the config validation requires a real path).
    Returns the config path.
    """
    config_path = Path(config_path)
    if terminal_file is None:
        terminal_file = config_path.parent / "_fake_terminal64.exe"
    if not terminal_file.exists():
        terminal_file.write_bytes(b"# fake terminal for offline dashboard tests")

    pip_size = ", ".join(
        f"{sym} = {0.0001 if 'JPY' not in sym else 0.01}" for sym in symbols
    )
    symbol_list = ", ".join(f'"{sym}"' for sym in symbols)
    toml = f"""
symbols = [{symbol_list}]
timeframes = ["M15", "H1", "H4"]
terminal_path = "{str(terminal_file).replace(chr(92), '/')}"
expected_server = "ICMarketsSC-Demo"
broker_offset_hours = 3
validated_at = "2026-08-30T00:00:00Z"
bars_dir = "{str(bars_dir).replace(chr(92), '/')}"
meta_db = "{str(meta_db).replace(chr(92), '/')}"
init_timeout_ms = 30000
poll_delay_seconds = 3
lookback_bars = 500
min_maxbars = 100000
backfill_max_rounds = 12
backfill_pause_seconds = 0.7
initial_backfill_days = 90
slippage_pips = 0.5
slippage_pips_by_symbol = {{}}
default_spread_points = 20
default_spread_points_by_symbol = {{}}
pip_size = {{ {pip_size} }}
min_rr = 1.0
time_barrier_bars = 96
wf_train_days = 180
wf_test_days = 30
min_history_days = 30
warmup_bars = 0
htf_warmup_days = 30
ml_feature_list_version = 1
ml_calibration_method = "sigmoid"
ml_embargo_bars = 0
ml_min_train_labels = 30
ml_cal_train_days = 2
ml_cal_test_days = 1
ml_random_state = 42
ml_n_estimators = 200
ml_num_leaves = 7
ml_min_data_in_leaf = 5
ml_learning_rate = 0.1
ml_retrain_enabled = false
ml_retrain_interval_hours = 24
llm_enabled = false
llm_base_url = "http://192.168.5.178:8000/v1"
llm_model = "deepseek-v4-flash-vision-exp"
llm_api_key = ""
llm_timeout_ms = 60000
llm_max_tokens = 2048
llm_top_n_contributors = 5
llm_structured_mode = "json_schema"
llm_agree_min_confidence = 0.6
llm_max_retries = 1
setup_trigger_window_bars = 8
setup_min_p_win = 0.0
"""
    config_path.write_text(toml)
    return config_path
