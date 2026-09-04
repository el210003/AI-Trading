"""Performance tab view (DASH-05) — currently an empty-state stub.

Plan 06-03 fills the KPI cards (Win Rate / Profit Factor / Expectancy(R) /
Trades), the cumulative-R equity curve, and the per-symbol breakdown from the
``stats`` functions. This module only lets ``app.py`` import and run cleanly now.
"""

from __future__ import annotations

import streamlit as st

#: UI-SPEC empty-state copy for a not-yet-implemented panel.
_EMPTY_COPY = "No performance stats yet. They will appear here once setups have closed outcomes."


def render(filters: dict | None = None) -> None:
    """Render the Performance tab (empty-state until plan 06-03)."""
    st.info(_EMPTY_COPY)
