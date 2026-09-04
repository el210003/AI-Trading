"""DASH-02 candlestick chart tests: pure figure-build assertions (entry/SL/TP
hlines, sweep diamond, PD-zone bands, locked layout) plus an AppTest render of
the chart path. Marked ``@pytest.mark.streamlit`` (offline, no MT5/LLM).
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT / "tests"))
sys.path.insert(0, str(_ROOT / "tests" / "unit"))

import pandas as pd  # noqa: E402  (after sys.path fixture-bootstrap)
import pytest  # noqa: E402
from _dashboard_fixtures import make_unavailable_row, write_app_config  # noqa: E402
from conftest import make_bars  # noqa: E402
from streamlit.testing.v1 import AppTest  # noqa: E402

from ai_trading.dashboard import charts, theme  # noqa: E402


def _bars():
    return make_bars("EURUSD", "M15", pd.Timestamp("2026-08-20T00:00:00").to_pydatetime(), 60)


def _setup():
    # A setup row carrying the sweep from its evidence object.
    return make_unavailable_row()


def _zones(setup):
    return pd.DataFrame(
        [{
            "zone_range_high": setup["zone_range_high"],
            "zone_range_low": setup["zone_range_low"],
            "created_at": setup["created_at"],
        }]
    )


@pytest.mark.streamlit
def test_candlestick_has_entry_sl_tp_hlines_and_candles():
    fig = charts.candlestick_chart(_bars(), _setup(), _zones(_setup()))
    # Candlestick trace + sweep diamond trace.
    assert len(fig.data) >= 1
    assert any(t.type == "candlestick" for t in fig.data)
    annotations = [a.text for a in fig.layout.annotations]
    assert "Entry" in annotations
    assert "SL" in annotations
    assert "TP" in annotations


@pytest.mark.streamlit
def test_candlestick_sweep_diamond_present_when_evidence_has_sweep():
    fig = charts.candlestick_chart(_bars(), _setup(), _zones(_setup()))
    markers = [t.marker.symbol for t in fig.data if t.type == "scatter"]
    assert any("diamond" in str(m) for m in markers)
    # The sweep marker is colored with the accent.
    accent_marks = [
        t for t in fig.data
        if t.type == "scatter" and t.marker.color == theme.COLORS["accent"]
    ]
    assert accent_marks


@pytest.mark.streamlit
def test_candlestick_pd_zone_band_below_candles():
    fig = charts.candlestick_chart(_bars(), _setup(), _zones(_setup()))
    rects = [
        s for s in fig.layout.shapes
        if s.type == "rect" and s.layer == "below" and s.fillcolor == theme.COLORS["accent"]
    ]
    assert rects, "expected a PD-zone band drawn below the candles"


@pytest.mark.streamlit
def test_candlestick_layout_locked():
    fig = charts.candlestick_chart(_bars(), _setup(), _zones(_setup()))
    assert fig.layout.height == 520
    assert fig.layout.margin.l == 8
    assert fig.layout.margin.r == 8
    assert fig.layout.margin.t == 24
    assert fig.layout.margin.b == 8
    assert fig.layout.hovermode == "x unified"


@pytest.mark.streamlit
def test_candlestick_empty_bars_returns_empty_figure():
    fig = charts.candlestick_chart(pd.DataFrame(), _setup(), None)
    assert len(fig.data) == 0


@pytest.mark.streamlit
def test_render_chart_path_renders_plotly(tmp_path):
    """The chart view path (``_render_chart``) renders a plotly chart without
    raising against a fixture config."""
    config_path = write_app_config(
        tmp_path / "config.toml",
        bars_dir=tmp_path / "data" / "bars",
        meta_db=tmp_path / "data" / "meta" / "meta.sqlite",
    )
    code = (
        "import streamlit as st\n"
        "from ai_trading.dashboard import views_setups\n"
        "setup = {"
        "'symbol': 'EURUSD', 'timeframe': 'M15', 'entry': 1.10, "
        "'sl_price': 1.095, 'tp_price': 1.12, "
        "'zone_range_high': 1.105, 'zone_range_low': 1.098, "
        "'evidence_json': '{\"sweep_side\": \"low\"}'\n}\n"
        "views_setups._render_chart(setup)\n"
    )
    at = AppTest.from_string(code)
    at.secrets["CONFIG_PATH"] = str(config_path)
    at.run()
    assert not at.exception
    assert len(at.get("plotly_chart")) >= 1
