"""Health strip + Health tab view (DASH-06) — pipeline freshness at a glance.

The health strip is the persistent trust backdrop rendered at the top of every
tab. It reads last-persisted state only (``data_layer.health_status``): the
last-bar time per (symbol, timeframe) feed, the MT5/collector status from the
meta ``collection_state`` heartbeat freshness, and a recent-errors count from
recent ``bar_gaps`` — the dashboard stays MT5-free (research OQ4 / DASH-06). A
missing/empty bar or meta store renders the UI-SPEC no-data / disconnected copy
(never a traceback, threat T-06-03).

MT5-free: only reads the persisted stores via ``data_layer``.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from ai_trading.dashboard import data_layer as dl

#: UI-SPEC health copy.
_NO_FEED_COPY = "no bars yet"
_STRIP_EMPTY_COPY = "No health data yet. Feed freshness will appear here once bars are collected."
_DISCONNECTED_COPY = "MT5 disconnected — inspect the running, logged-in terminal, then refresh."

#: Human labels + status glyphs reused from the theme contract (no HTML —
#: T-06-02 native widgets only).
_STATUS_LABELS = {"healthy": "connected", "stale": "stalled", "disconnected": "disconnected"}
_STATUS_GLYPHS = {"healthy": "●", "stale": "◌", "disconnected": "✗"}


def _fmt_time(value) -> str:
    """Format a last-bar timestamp label (blank on no-data)."""
    if value is None:
        return _NO_FEED_COPY
    return f"{value:%Y-%m-%d %H:%M}"


def _render_mt5_flag(status: dict) -> None:
    """Render the MT5/collector status chip (healthy/stale/disconnected)."""
    key = status.get("mt5_status", "disconnected")
    label = _STATUS_LABELS.get(key, key)
    glyph = _STATUS_GLYPHS.get(key, "●")
    st.markdown(f"**MT5** · {glyph} {label}")
    if key == "disconnected":
        st.caption(_DISCONNECTED_COPY)


def render_health_strip(cfg=None) -> None:
    """The sticky 56px health strip rendered on every tab (DASH-06).

    Shows each configured feed's last-bar time, the MT5/collector status, and the
    recent-errors count from ``data_layer.health_status``. A missing/empty store
    degrades to the no-data copy rather than raising. (The strip is compact; the
    full per-feed detail lives in ``render_detail`` on the Health tab.)
    """
    if cfg is None:
        try:
            cfg = dl.get_config()
        except Exception:  # noqa: BLE001 - the strip never crashes the app
            st.warning(_STRIP_EMPTY_COPY)
            return
    try:
        status = dl.health_status(cfg)
    except Exception:  # noqa: BLE001 - defensiveness: the strip never crashes the app
        st.warning(_STRIP_EMPTY_COPY)
        return

    feeds = status.get("per_feed", [])
    cols = st.columns(len(feeds) + 2)
    for col, feed in zip(cols, feeds, strict=False):
        with col:
            st.markdown(f"**{feed['symbol']} {feed['timeframe']}**  \n"
                        f"{_fmt_time(feed['last_bar_time'])}")
    with cols[len(feeds)]:
        _render_mt5_flag(status)
    with cols[len(feeds) + 1]:
        st.markdown(f"**Errors**  \n{status.get('recent_errors', 0)}")


def _render_feed_table(status: dict) -> None:
    """Render the Health tab per-feed freshness table."""
    feeds = status.get("per_feed", [])
    if not feeds:
        st.info(_STRIP_EMPTY_COPY)
        return
    display = pd.DataFrame(
        {
            "Symbol": [f["symbol"] for f in feeds],
            "Timeframe": [f["timeframe"] for f in feeds],
            "Last Bar": [_fmt_time(f["last_bar_time"]) for f in feeds],
        }
    )
    st.dataframe(display, width="stretch", hide_index=True)


def render_detail(filters: dict | None = None) -> None:
    """Render the Health tab detail (per-feed table + status + recent issues).

    A missing/empty store renders the empty/copy state (never a traceback).
    """
    try:
        cfg = dl.get_config()
    except Exception:  # noqa: BLE001 - per-view robustness (only this tab)
        st.warning(_STRIP_EMPTY_COPY)
        return
    try:
        status = dl.health_status(cfg)
    except Exception:  # noqa: BLE001
        st.warning(_STRIP_EMPTY_COPY)
        return

    st.subheader("Data Health")
    render_health_strip(cfg)
    st.subheader("Feed Freshness")
    _render_feed_table(status)
    st.subheader("Recent Issues")
    errors = status.get("recent_errors", 0)
    if errors:
        st.warning(f"{errors} data-quality gap(s) detected in the recent window.")
    else:
        st.caption("No recent data-quality gaps detected.")
