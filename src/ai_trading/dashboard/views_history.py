"""History tab view (DASH-04) — currently an empty-state stub.

Plan 06-03 fills the real History table (symbol / direction / entry / outcome /
r_net / p_win / status / closed_at, newest-first) from the closed setup store.
This module only lets ``app.py`` import and run cleanly now.
"""

from __future__ import annotations

import streamlit as st

#: UI-SPEC empty-state copy for a view that has nothing to show yet.
_EMPTY_COPY = "No setup history yet. Setups will appear here once they close."


def render(filters: dict | None = None) -> None:
    """Render the History tab (empty-state until plan 06-03)."""
    st.info(_EMPTY_COPY)
