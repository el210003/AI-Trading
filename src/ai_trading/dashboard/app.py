"""Phase-6 Streamlit dashboard app shell.

Layout per the locked 06-UI-SPEC.md: a wide single-page app with a shared left
sidebar (global filters), a sticky 56px health strip rendered above the tab bar,
and four ``st.tabs`` (Setups / History / Performance / Health).  The Setups tab
is the DASH-01/02/03 focal surface; the other three render their empty-state
views until plan 06-03.

MT5-free: the dashboard only reads the persisted setup store + bar files via
``data_layer``; it never touches a live terminal.

Run offline: ``uv run streamlit run src/ai_trading/dashboard/app.py``
"""

import streamlit as st

st.set_page_config(layout="wide", page_title="SMC Setups")

from ai_trading.dashboard import (  # noqa: E402  (after set_page_config)
    views_health,
    views_history,
    views_performance,
    views_setups,
)

#: Shared sidebar filters apply globally across the Setups/History tabs.
filters = views_setups.sidebar_filters()

#: Sticky health strip — rendered first on every tab (DASH-06 trust backdrop).
views_health.render_health_strip()

tab_setups, tab_history, tab_perf, tab_health = st.tabs(
    ["Setups", "History", "Performance", "Health"]
)

with tab_setups:
    views_setups.render(filters)
with tab_history:
    views_history.render(filters)
with tab_perf:
    views_performance.render(filters)
with tab_health:
    views_health.render_detail(filters)


def main() -> None:
    """Module entry point used by ``st run`` (the script body runs top-down)."""
    return None


if __name__ == "__main__":
    main()
