"""LLM settings panel (SEED-004) — runtime LLM configuration from the dashboard.

Rendered at the bottom of the Health tab (the pipeline-ops surface). Reads the
effective config via ``data_layer``; saves machine-local overrides to the
sibling ``config.local.toml`` through ``config_writer.update_local_overrides``
— validate-before-write, atomic replace, comments not preserved (caption says
so). The API key field is WRITE-ONLY: the stored key is never displayed or
echoed, and a blank field leaves the stored key untouched.

The Test-connection probe lists the served model ids (the ``llm_model``
authority) and times a minimal chat call. Engine/collector-side consumers that
re-load config per pass (``scheduler.refresh_cfg``) pick up a saved edit on the
next M15 cycle without a restart.

Defensive: every failure path renders an inline error — never a traceback
(T-06-03).
"""

from __future__ import annotations

import dataclasses

import streamlit as st

from ai_trading.config_writer import read_local_raw, update_local_overrides
from ai_trading.dashboard import data_layer as dl
from ai_trading.llm.provider import probe_endpoint

_MODES = ("json_schema", "json_object", "none")


def _key_is_set(base) -> bool:
    try:
        raw = read_local_raw(base)
    except Exception:  # noqa: BLE001 — a malformed local file still renders the panel
        return False
    return bool(str(raw.get("llm_api_key", "")).strip())


def _resolve_api_key(base, entered: str) -> str:
    """Blank key field = keep the stored key (write-only field contract)."""
    entered = entered.strip()
    if entered:
        return entered
    try:
        return str(read_local_raw(base).get("llm_api_key", ""))
    except Exception:  # noqa: BLE001
        return ""


def _run_probe(cfg, base, entered_key: str) -> None:
    """Run the endpoint probe and render the outcome inline."""
    key = _resolve_api_key(base, entered_key)
    with st.spinner("Probing endpoint..."):
        result = probe_endpoint(
            cfg.llm_base_url, key, cfg.llm_model, timeout_s=min(cfg.llm_timeout_ms / 1000, 30.0)
        )
    if result["ok"]:
        st.success(
            f"Endpoint OK — chat answered in {result['latency_ms']} ms; "
            f"{len(result['models'])} model(s) served."
        )
        if result["models"]:
            st.caption("Served models: " + ", ".join(result["models"]))
            if cfg.llm_model not in result["models"]:
                st.warning(
                    f"Configured model {cfg.llm_model!r} is NOT in the served list — "
                    "pick one above and save."
                )
        return
    st.error(f"Probe failed: {result['error']}")
    if result["models"]:
        st.caption("Models served (chat call failed): " + ", ".join(result["models"]))


def render_settings() -> None:
    """Render the LLM settings expander (bottom of the Health tab)."""
    try:
        cfg = dl.get_config()
        base = dl.config_path()
    except Exception:  # noqa: BLE001 — only this section degrades (T-06-03)
        st.caption("LLM settings unavailable (config failed to load).")
        return

    with st.expander("LLM Settings", expanded=False):
        st.caption(
            "Saves machine-local overrides to config.local.toml "
            "(validate-before-write, atomic; comments in that file are not "
            "preserved). The engine monitor picks up changes on the next M15 pass."
        )

        enabled = st.toggle(
            "LLM narrative enabled", value=bool(cfg.llm_enabled), key="settings_llm_enabled"
        )
        base_url = st.text_input(
            "Base URL", value=cfg.llm_base_url, key="settings_llm_base_url"
        )
        model = st.text_input("Model", value=cfg.llm_model, key="settings_llm_model")
        key_state = "set ✓" if _key_is_set(base) else "not set"
        api_key = st.text_input(
            "API key (write-only — blank keeps the stored key)",
            value="",
            type="password",
            key="settings_llm_api_key",
            placeholder=f"({key_state})",
        )
        col1, col2 = st.columns(2)
        with col1:
            timeout_ms = st.number_input(
                "Timeout (ms)", min_value=1000, max_value=600000,
                value=int(cfg.llm_timeout_ms), step=1000, key="settings_llm_timeout_ms",
            )
        with col2:
            max_tokens = st.number_input(
                "Max tokens (>= 2048)", min_value=2048, max_value=131072,
                value=int(cfg.llm_max_tokens), step=512, key="settings_llm_max_tokens",
            )
        structured_mode = st.selectbox(
            "Structured mode", _MODES,
            index=_MODES.index(cfg.llm_structured_mode)
            if cfg.llm_structured_mode in _MODES else 0,
            key="settings_llm_structured_mode",
        )

        b1, b2 = st.columns(2)
        with b1:
            if st.button("Test connection", key="settings_llm_test", width="stretch"):
                # Frozen Config: rebuild via replace (never setattr) — the
                # probe reflects the on-screen values, not the stored ones.
                probe_cfg = dataclasses.replace(
                    cfg, llm_base_url=base_url.strip(), llm_model=model.strip()
                )
                _run_probe(probe_cfg, base, api_key)
        with b2:
            save_clicked = st.button(
                "Save", type="primary", key="settings_llm_save", width="stretch"
            )

        if save_clicked:
            updates = {
                "llm_enabled": bool(enabled),
                "llm_base_url": base_url.strip(),
                "llm_model": model.strip(),
                "llm_timeout_ms": int(timeout_ms),
                "llm_max_tokens": int(max_tokens),
                "llm_structured_mode": structured_mode,
            }
            if api_key.strip():
                updates["llm_api_key"] = api_key.strip()
            try:
                update_local_overrides(base, updates)
            except Exception as exc:  # noqa: BLE001 — inline error, never a traceback
                st.error(f"Save failed — config unchanged. {exc}")
            else:
                st.success(
                    "Saved to config.local.toml. The engine monitor applies it on "
                    "its next pass; other consumers on restart."
                )
