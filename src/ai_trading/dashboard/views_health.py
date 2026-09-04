"""Health strip + Health tab view (DASH-06).

The health strip is the persistent trust backdrop rendered at the top of every
tab. It reads last-persisted state (freshness of the latest M15 bar per feed)
so the dashboard stays MT5-free (research OQ4). Plan 06-03 fills the full
per-feed / MT5-status / error-count detail; this module provides the strip and
an empty-state detail view so ``app.py`` runs cleanly now.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from ai_trading.dashboard import data_layer as dl

#: UI-SPEC health-strip copy when no feed freshness is available yet.
_NO_FEED_COPY = "no bars yet"
_STRIP_EMPTY_COPY = "No health data yet. Feed freshness will appear here once bars are collected."


def render_health_strip() -> None:
    """The sticky 56px health strip rendered on every tab (DASH-06).

    Shows each configured feed's last M15 bar freshness (last-persisted state);
    a missing/empty store degrades to an info note rather than raising.
    """
    try:
        cfg = dl.get_config()
    except Exception:  # noqa: BLE001 - defensiveness: the strip never crashes the app
        st.warning(_STRIP_EMPTY_COPY)
        return
    symbols = list(getattr(cfg, "symbols", ()))
    if not symbols:
        st.info(_STRIP_EMPTY_COPY)
        return
    cols = st.columns(len(symbols))
    for col, symbol in zip(cols, symbols, strict=False):
        try:
            bars = dl.load_bars(cfg, symbol, "M15")
            if bars.empty:
                label = _NO_FEED_COPY
            else:
                last = pd.Timestamp(bars["time_utc"].max())
                label = f"{last:%Y-%m-%d %H:%M}"
        except Exception:  # noqa: BLE001
            label = _NO_FEED_COPY
        with col:
            st.markdown(f"**{symbol} M15**  \n{label}")


def render_detail(filters: dict | None = None) -> None:
    """Render the Health tab detail (empty-state until plan 06-03)."""
    render_health_strip()
    st.info(_STRIP_EMPTY_COPY)
