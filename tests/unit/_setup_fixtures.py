"""Phase-6 setup test fixtures — local helper built over ``conftest`` /
``_backtest_fixtures`` via direct import, never extended (Phase 1/2 contract;
06-RESEARCH Wave-0 Gaps).

Helpers:
- ``setup_cfg``: frozen Config carrying the Phase-6 ``setup_*`` defaults (via
  ``_backtest_fixtures.bt_cfg`` / ``conftest._make_cfg``) so setup tests never
  depend on ``load_config`` or files on disk.
- ``make_setup_row``: a single-row record frame with exactly ``SETUP_COLUMNS``
  and the store's pinned dtypes (for store round-trip tests).
- ``make_setup_frame``: an N-row frame of ``make_setup_row``-style records.

All helpers return new frames / never mutate inputs.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from _backtest_fixtures import bt_cfg  # noqa: F401  (consumed, never extended)

from ai_trading.setup.store import SETUP_COLUMNS, _coerce

__all__ = ["setup_cfg", "make_setup_row", "make_setup_frame", "SETUP_COLUMNS"]


def setup_cfg(**overrides) -> Any:
    """Frozen Config carrying the Phase-6 ``setup_*`` defaults (and all
    Phase-3/4/5 defaults) via ``_backtest_fixtures.bt_cfg``; pass keyword
    overrides per test (never touches ``load_config``)."""
    defaults = {
        "setup_trigger_window_bars": 8,
        "setup_min_p_win": 0.0,
    }
    return bt_cfg(**{**defaults, **overrides})


def make_setup_row(**overrides) -> pd.DataFrame:
    """Return a one-row record frame with exactly ``SETUP_COLUMNS`` and the
    store's pinned dtypes. Defaults model a fresh pending long setup; pass
    keyword overrides per test."""
    row: dict[str, Any] = {
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
        "evidence_json": '{"symbol": "EURUSD"}',
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
    return _coerce(pd.DataFrame([row]))


def make_setup_frame(rows: list[dict]) -> pd.DataFrame:
    """Build an N-row setup frame from a list of row dicts (each merged over
    ``make_setup_row`` defaults)."""
    frames = [make_setup_row(**row) for row in rows]
    return _coerce(pd.concat(frames, ignore_index=True))
