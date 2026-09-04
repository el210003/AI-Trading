"""Streamlit AppTest suite for the dashboard app shell (DASH-01/02/03).

Runs offline (<file> via ``streamlit.testing.v1.AppTest``) against an isolated
tmp data root — no MT5, no live LLM. Marked ``@pytest.mark.streamlit`` so it is
excluded from the default offline suite and selected via ``-m streamlit``.
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

APP_PATH = str(_ROOT / "src" / "ai_trading" / "dashboard" / "app.py")


def _config_path(tmp_path) -> Path:
    return write_app_config(
        tmp_path / "config.toml",
        bars_dir=tmp_path / "data" / "bars",
        meta_db=tmp_path / "data" / "meta" / "meta.sqlite",
    )


@pytest.mark.streamlit
def test_app_runs_with_four_tabs_and_health_strip(tmp_path):
    write_setups(tmp_path, [make_verified_row(), make_unavailable_row()])
    config_path = _config_path(tmp_path)
    at = AppTest.from_file(APP_PATH)
    at.secrets["CONFIG_PATH"] = str(config_path)
    at.run()

    assert not at.exception
    assert len(at.tabs) >= 4  # Setups / History / Performance / Health
    # The sticky health strip renders a per-feed freshness label.
    health_md = [m.value for m in at.markdown]
    assert any("M15" in str(v) for v in health_md)
    # The Setups table renders at least one row + a P(win) composite cell.
    assert len(at.dataframe) >= 1


@pytest.mark.streamlit
def test_missing_setup_store_renders_empty_state(tmp_path):
    """A missing/empty store renders the Empty state (no traceback), and the
    other tabs stay functional — only the affected view is suppressed."""
    config_path = _config_path(tmp_path)  # no setups written
    at = AppTest.from_file(APP_PATH)
    at.secrets["CONFIG_PATH"] = str(config_path)
    at.run()

    assert not at.exception
    assert len(at.tabs) >= 4
    # Empty-state copy is bound to the Setups view.
    infos = [i.value for i in at.info]
    assert any("setup store is empty" in str(v).lower() for v in infos)
