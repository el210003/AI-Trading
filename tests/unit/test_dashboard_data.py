"""Pure unit tests for the dashboard data layer (DASH-01 filter semantics,
T-06-03 empty-store defensive read, T-06-01 resolve-under-root guard, and the
UI-SPEC label / color / whole-percent honesty helpers).

Runs offline (no Streamlit, no MT5, no live model/LLM) against an isolated
temp data root and in-memory setup frames.
"""

from __future__ import annotations

import pandas as pd
import pytest
from _dashboard_fixtures import dashboard_cfg
from _setup_fixtures import SETUP_COLUMNS, make_setup_frame

from ai_trading.dashboard import data_layer as dl
from ai_trading.dashboard import theme


@pytest.mark.unit
def test_load_setups_missing_store_returns_schema_frame(tmp_path):
    """T-06-03: a missing store must never raise — it returns the schema-correct
    empty frame so the view renders the Empty state."""
    cfg = dashboard_cfg(tmp_path)
    setups = dl.load_setups(cfg)
    assert setups.empty
    assert list(setups.columns) == list(SETUP_COLUMNS)


@pytest.mark.unit
def test_load_bars_missing_file_returns_empty_frame(tmp_path):
    cfg = dashboard_cfg(tmp_path)
    bars = dl.load_bars(cfg, "EURUSD", "M15")
    assert bars.empty


@pytest.mark.unit
def test_apply_filters_symbol_status_direction(tmp_path):
    frame = make_setup_frame(
        [
            {"setup_id": "a", "symbol": "EURUSD", "status": "pending", "direction": "long"},
            {"setup_id": "b", "symbol": "GBPUSD", "status": "active", "direction": "short"},
            {"setup_id": "c", "symbol": "EURUSD", "status": "tp_hit", "direction": "long"},
            {"setup_id": "d", "symbol": "USDJPY", "status": "pending", "direction": "short"},
        ]
    )
    # symbol filter
    out = dl.apply_filters(frame, {"symbols": ["EURUSD"]})
    assert out["setup_id"].tolist() == ["a", "c"]
    # status filter
    out = dl.apply_filters(frame, {"statuses": ["pending"]})
    assert out["setup_id"].tolist() == ["a", "d"]
    # direction filter
    out = dl.apply_filters(frame, {"direction": "long"})
    assert out["setup_id"].tolist() == ["a", "c"]
    out = dl.apply_filters(frame, {"direction": "all"})
    assert len(out) == 4
    # combined
    out = dl.apply_filters(
        frame, {"symbols": ["EURUSD"], "statuses": ["pending"], "direction": "long"}
    )
    assert out["setup_id"].tolist() == ["a"]
    # no filters -> all (but sorted, see sort test)
    out = dl.apply_filters(frame, {}, sort_by=None)
    assert len(out) == 4


@pytest.mark.unit
def test_apply_filters_min_prob(tmp_path):
    frame = make_setup_frame(
        [
            {"setup_id": "hi", "p_win": 0.62, "score_source": "ml"},
            {"setup_id": "lo", "p_win": 0.30, "score_source": "ml"},
        ]
    )
    out = dl.apply_filters(frame, {"min_prob": 50})
    assert out["setup_id"].tolist() == ["hi"]
    out = dl.apply_filters(frame, {"min_prob": 0})
    assert len(out) == 2


@pytest.mark.unit
def test_apply_filters_date_range_inclusive(tmp_path):
    frame = make_setup_frame(
        [
            {"setup_id": "day1", "created_at": pd.Timestamp("2026-08-20T09:00:00")},
            {"setup_id": "day2", "created_at": pd.Timestamp("2026-08-21T09:00:00")},
            {"setup_id": "day3", "created_at": pd.Timestamp("2026-08-22T09:00:00")},
        ]
    )
    out = dl.apply_filters(
        frame,
        {"start_date": pd.Timestamp("2026-08-21"), "end_date": pd.Timestamp("2026-08-21")},
    )
    assert out["setup_id"].tolist() == ["day2"]


@pytest.mark.unit
def test_apply_filters_sort_newest_first(tmp_path):
    frame = make_setup_frame(
        [
            {"setup_id": "t1", "created_at": pd.Timestamp("2026-08-20T09:00:00")},
            {"setup_id": "t2", "created_at": pd.Timestamp("2026-08-21T09:00:00")},
            {"setup_id": "t3", "created_at": pd.Timestamp("2026-08-19T09:00:00")},
        ]
    )
    out = dl.apply_filters(frame, {}, sort_by="created_at", sort_desc=True)
    assert out["setup_id"].tolist() == ["t2", "t1", "t3"]
    out = dl.apply_filters(frame, {}, sort_by="created_at", sort_desc=False)
    assert out["setup_id"].tolist() == ["t3", "t1", "t2"]


@pytest.mark.unit
def test_status_and_outcome_label_mappings():
    assert dl.status_label("active") == "Active"
    assert dl.status_label("tp_hit") == "TP Hit"
    assert dl.status_label("sl_hit") == "SL Hit"
    assert dl.status_label("expired") == "Expired"
    assert dl.status_label("invalidated") == "Invalidated"
    assert dl.outcome_label("WIN") == "Win"
    assert dl.outcome_label("LOSS") == "Loss"
    assert dl.outcome_label("TIMEOUT") == "Timeout"
    assert dl.agreement_label("agree") == "Agree"
    assert dl.agreement_label("disagree") == "Disagree"
    assert dl.agreement_label("unclear") == "Unclear"


@pytest.mark.unit
def test_score_source_tag_and_color_honesty():
    assert dl.score_source_tag("ml") == "ML"
    assert dl.score_source_tag("ml_llm") == "ML+LLM"
    assert dl.score_source_tag("heuristic") == "Heuristic"
    # heuristic renders in the warning hue; ml/ml_llm in the muted neutral.
    assert dl.score_source_color("heuristic") == theme.COLORS["warning"]
    assert dl.score_source_color("ml") == theme.COLORS["muted"]
    assert dl.score_source_color("ml_llm") == theme.COLORS["muted"]


@pytest.mark.unit
def test_pct_whole_percent_formatter():
    assert dl.pct(0.58) == "58%"
    assert dl.pct(0.625) == "62%"
    assert dl.pct(0.0) == "0%"
    assert dl.pct(None) == "—"
    assert dl.pct(float("nan")) == "—"
    assert dl.pct("0.72") == "72%"


@pytest.mark.unit
def test_direction_and_verdict_labels():
    assert dl.direction_label("long") == "Long"
    assert dl.direction_label("short") == "Short"
    assert theme.VERDICT_LABELS["confirm"] == "Confirm"
    assert theme.VERDICT_LABELS["refute"] == "Refute"


@pytest.mark.unit
def test_setup_dir_guarded_escape_raises(tmp_path):
    """T-06-01: a setups dir that resolves outside the data root is refused.
    Uses a directory symlink to force the resolution mismatch; skips when
    symlinks are unavailable on the platform (Windows), matching the Phase-6
    store guard test convention."""
    data_root = tmp_path / "data"
    data_root.mkdir(parents=True, exist_ok=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    try:
        (data_root / "setups").symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("directory symlinks unavailable on this platform")
    cfg = dashboard_cfg(tmp_path)
    with pytest.raises(ValueError, match="path traversal refused"):
        dl.setup_dir_guarded(cfg)


@pytest.mark.unit
def test_healthy_config_returns_guarded_root(tmp_path):
    cfg = dashboard_cfg(tmp_path)
    root = dl.healthy_config(cfg)
    assert root.resolve() == (tmp_path / "data").resolve()
