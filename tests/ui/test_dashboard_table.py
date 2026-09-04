"""Streamlit AppTest suite for the DASH-01 setup table + filters.

Runs the ``views_setups.sidebar_filters`` + ``render_table`` path via
``AppTest.from_string`` against an isolated tmp store, asserting the table lists
the fixture setups, narrows on symbol/status/min-prob, renders the honest
``p_win`` + ``score_source`` composite cell, and that Reset Filters restores
defaults. Marked ``@pytest.mark.streamlit`` (offline, no MT5/LLM).
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT / "tests"))
sys.path.insert(0, str(_ROOT / "tests" / "unit"))

import pytest  # noqa: E402  (after sys.path fixture-bootstrap)
from _dashboard_fixtures import (  # noqa: E402
    make_unavailable_row,
    make_verified_row,
    write_app_config,
    write_setups,
)
from streamlit.testing.v1 import AppTest  # noqa: E402

_TABLE_CODE = (
    "import streamlit as st\n"
    "from ai_trading.dashboard import views_setups\n"
    "filters = views_setups.sidebar_filters()\n"
    "views_setups.render_table(filters)\n"
)


def _fixture_rows():
    return [
        make_verified_row(setup_id="eu1", symbol="EURUSD", direction="long", p_win=0.62,
                          status="pending", score_source="ml"),
        make_verified_row(setup_id="eu2", symbol="EURUSD", direction="short", p_win=0.58,
                          status="active", score_source="ml_llm"),
        make_verified_row(setup_id="gu1", symbol="GBPUSD", direction="long", p_win=0.72,
                          status="tp_hit", score_source="ml"),
        make_unavailable_row(setup_id="uj1", symbol="USDJPY", direction="long", p_win=0.30,
                             status="expired", score_source="heuristic"),
    ]


def _boot(tmp_path):
    write_setups(tmp_path, _fixture_rows())
    config_path = write_app_config(
        tmp_path / "config.toml",
        bars_dir=tmp_path / "data" / "bars",
        meta_db=tmp_path / "data" / "meta" / "meta.sqlite",
    )
    at = AppTest.from_string(_TABLE_CODE)
    at.secrets["CONFIG_PATH"] = str(config_path)
    at.run()
    assert not at.exception
    return at


def _symbols(at) -> list:
    return list(at.dataframe[0].value["Symbol"])


@pytest.mark.streamlit
def test_default_filters_list_all_fixture_setups(tmp_path):
    at = _boot(tmp_path)
    assert sorted(_symbols(at)) == sorted(["EURUSD", "EURUSD", "GBPUSD", "USDJPY"])


@pytest.mark.streamlit
def test_pwin_renders_with_score_source_tag(tmp_path):
    at = _boot(tmp_path)
    pwin = list(at.dataframe[0].value["P(win)"])
    # Honesty rule: tag sits in the same cell as the whole-percent probability.
    assert any("62% [ML]" in v for v in pwin)
    assert any("58% [ML+LLM]" in v for v in pwin)


@pytest.mark.streamlit
def test_symbol_filter_narrows_rows(tmp_path):
    at = _boot(tmp_path)
    at.sidebar.multiselect[0].set_value(["GBPUSD", "USDJPY"]).run()
    assert not at.exception
    assert sorted(_symbols(at)) == sorted(["GBPUSD", "USDJPY"])


@pytest.mark.streamlit
def test_status_filter_narrows_rows(tmp_path):
    at = _boot(tmp_path)
    at.sidebar.multiselect[1].set_value(["active"]).run()
    assert not at.exception
    assert _symbols(at) == ["EURUSD"]  # only the active setup (eu2)


@pytest.mark.streamlit
def test_min_prob_filter_narrows_rows(tmp_path):
    at = _boot(tmp_path)
    at.sidebar.slider[0].set_value(60).run()
    assert not at.exception
    assert sorted(_symbols(at)) == sorted(["EURUSD", "GBPUSD"])  # p_win >= 60%


@pytest.mark.streamlit
def test_reset_filters_restores_defaults(tmp_path):
    at = _boot(tmp_path)
    at.sidebar.multiselect[0].set_value(["EURUSD"]).run()
    assert not at.exception
    assert _symbols(at) == ["EURUSD", "EURUSD"]  # the two EURUSD setups
    # Click Reset Filters -> all rows return.
    at.sidebar.button[0].click().run()
    assert not at.exception
    assert sorted(_symbols(at)) == sorted(["EURUSD", "EURUSD", "GBPUSD", "USDJPY"])
