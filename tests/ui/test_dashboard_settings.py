"""Streamlit AppTest suite for the LLM settings panel (SEED-004).

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
from _dashboard_fixtures import write_app_config  # noqa: E402
from streamlit.testing.v1 import AppTest  # noqa: E402

APP_PATH = str(_ROOT / "src" / "ai_trading" / "dashboard" / "app.py")


def _config_path(tmp_path) -> Path:
    return write_app_config(
        tmp_path / "config.toml",
        bars_dir=tmp_path / "data" / "bars",
        meta_db=tmp_path / "data" / "meta" / "meta.sqlite",
    )


@pytest.mark.streamlit
def test_settings_panel_renders_in_health_tab(tmp_path):
    config_path = _config_path(tmp_path)
    at = AppTest.from_file(APP_PATH)
    at.secrets["CONFIG_PATH"] = str(config_path)
    at.run()

    assert not at.exception
    assert len(at.toggle) >= 1  # llm_enabled toggle renders
    assert any("LLM Settings" in str(e.label) for e in at.expander)
    assert any("Base URL" in str(t.label) for t in at.text_input)


@pytest.mark.streamlit
def test_save_writes_local_overrides(tmp_path):
    config_path = _config_path(tmp_path)
    at = AppTest.from_file(APP_PATH)
    at.secrets["CONFIG_PATH"] = str(config_path)
    at.run()

    at.text_input(key="settings_llm_base_url").set_value("https://api.example.com/v1").run()
    at.text_input(key="settings_llm_model").set_value("panel-model").run()
    at.button(key="settings_llm_save").click().run()

    assert not at.exception
    assert any("Saved" in str(s.value) for s in at.success)
    local = config_path.parent / "config.local.toml"
    assert local.exists()
    text = local.read_text(encoding="utf-8")
    assert "https://api.example.com/v1" in text
    assert "panel-model" in text


@pytest.mark.streamlit
def test_invalid_save_renders_error_and_writes_nothing(tmp_path):
    config_path = _config_path(tmp_path)
    at = AppTest.from_file(APP_PATH)
    at.secrets["CONFIG_PATH"] = str(config_path)
    at.run()

    # Enable the LLM with an empty base URL -> fail-fast validation rejects.
    at.toggle(key="settings_llm_enabled").set_value(True).run()
    at.text_input(key="settings_llm_base_url").set_value("").run()
    at.button(key="settings_llm_save").click().run()

    assert not at.exception
    assert any("Save failed" in str(e.value) for e in at.error)
    local = config_path.parent / "config.local.toml"
    assert not local.exists()


@pytest.mark.streamlit
def test_write_only_key_field_does_not_display_stored_key(tmp_path):
    config_path = _config_path(tmp_path)
    config_path.parent.joinpath("config.local.toml").write_text(
        'llm_api_key = "stored-secret-1"\n', encoding="utf-8"
    )
    at = AppTest.from_file(APP_PATH)
    at.secrets["CONFIG_PATH"] = str(config_path)
    at.run()

    assert not at.exception
    key_input = at.text_input(key="settings_llm_api_key")
    assert key_input.value == ""  # write-only: the stored key is never displayed
