"""Unit tests for the config writer (SEED-004) — validate-before-write atomic
config.local.toml editing — and the engine monitor's per-pass config reload
(``scheduler.refresh_cfg``). No MT5, no network."""

from __future__ import annotations

from pathlib import Path

import pytest
from test_backtest_config import _base_values
from test_backtest_config import _write_config as _write_toml

from ai_trading.config import load_config
from ai_trading.config_writer import local_path, read_local_raw, update_local_overrides
from ai_trading.setup.scheduler import refresh_cfg


def _write_base(tmp_path) -> Path:
    return _write_toml(tmp_path, _base_values(tmp_path))


def test_update_writes_and_loads(tmp_path):
    base = _write_base(tmp_path)
    update_local_overrides(
        base, {"llm_base_url": "https://api.example.com/v1", "llm_model": "test-model"}
    )
    cfg = load_config(base)
    assert cfg.llm_base_url == "https://api.example.com/v1"
    assert cfg.llm_model == "test-model"
    # No tmp residue after the atomic replace.
    assert not local_path(base).with_suffix(".toml.tmp").exists()


def test_update_merges_and_preserves_existing_keys(tmp_path):
    base = _write_base(tmp_path)
    update_local_overrides(base, {"llm_api_key": "secret-key-123"})
    update_local_overrides(base, {"llm_model": "next-model"})
    raw = read_local_raw(base)
    assert raw["llm_api_key"] == "secret-key-123"
    assert raw["llm_model"] == "next-model"


def test_invalid_update_rejected_file_untouched(tmp_path):
    base = _write_base(tmp_path)
    before = local_path(base).read_bytes() if local_path(base).exists() else b""
    with pytest.raises(ValueError, match="llm_max_tokens"):
        update_local_overrides(base, {"llm_max_tokens": 100})  # below the 2048 floor
    after = local_path(base).read_bytes() if local_path(base).exists() else b""
    assert before == after


def test_validation_error_never_contains_secret_value(tmp_path):
    base = _write_base(tmp_path)
    secret = "sk-very-secret-value-9876"
    with pytest.raises(ValueError) as excinfo:
        update_local_overrides(base, {"llm_api_key": secret, "llm_max_tokens": 100})
    assert secret not in str(excinfo.value)


def test_comments_not_preserved_header_added(tmp_path):
    base = _write_base(tmp_path)
    local = local_path(base)
    local.write_text(
        "# my precious hand-written note\nllm_model = \"hand-edited\"\n",
        encoding="utf-8",
    )
    update_local_overrides(base, {"llm_model": "panel-model"})
    text = local.read_text(encoding="utf-8")
    assert "my precious hand-written note" not in text
    assert "Managed by the dashboard LLM settings panel" in text
    assert load_config(base).llm_model == "panel-model"


def test_read_local_raw_empty_when_absent(tmp_path):
    base = _write_base(tmp_path)
    assert read_local_raw(base) == {}


# ---------------------------------------------------------------------------
# refresh_cfg: per-pass monitor reload with fail-safe fallback
# ---------------------------------------------------------------------------

def test_refresh_cfg_picks_up_local_edit(tmp_path):
    base = _write_base(tmp_path)
    cfg = load_config(base)
    update_local_overrides(base, {"llm_model": "reloaded-model"})
    refreshed = refresh_cfg(cfg, base)
    assert refreshed.llm_model == "reloaded-model"
    # The previous frozen cfg is untouched (reload returns a NEW Config).
    assert cfg.llm_model != "reloaded-model"


def test_refresh_cfg_keeps_previous_on_broken_config(tmp_path, caplog):
    base = _write_base(tmp_path)
    cfg = load_config(base)
    local_path(base).write_text(
        "this is not = valid toml {{{", encoding="utf-8"
    )
    with caplog.at_level("ERROR"):
        refreshed = refresh_cfg(cfg, base)
    assert refreshed is cfg
    assert "config reload failed" in caplog.text
