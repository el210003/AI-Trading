"""History tab view (DASH-04) — the lifecycle-outcome table for closed setups.

Renders every emitted setup's terminal outcome (``tp_hit``/``sl_hit``/
``expired``/``invalidated``) newest-first over ``data_layer.history_frame``,
with an optional outcome filter and the UI-SPEC status/outcome color binding
from ``theme``. A missing/empty store or a no-match filter renders the
UI-SPEC info/empty copy (never a traceback, threat T-06-03).

MT5-free: only reads the persisted setup store via ``data_layer``.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from ai_trading.dashboard import data_layer as dl
from ai_trading.dashboard import theme

#: UI-SPEC empty-state copy for the standalone History view.
_EMPTY_COPY = "No setup history yet. Setups will appear here once they close."
_NO_MATCH_COPY = "No history rows match the current filters."
_ERROR_COPY = (
    "Failed to load setup history. The data store could not be read — check that "
    "the collector has run (data/bars) and the setup store is populated, then refresh."
)

#: UI-SPEC outcome-filter options (All + the outcome badges).
_OUTCOME_OPTIONS = ("All", "WIN", "LOSS", "TIMEOUT", "invalidated")


def _fmt_price(value) -> str:
    """Price formatting helper (blank on missing)."""
    if value is None or pd.isna(value):
        return "—"
    return f"{float(value):.5f}"


def _fmt_r(value) -> str:
    """R formatting helper (blank on missing)."""
    if value is None or pd.isna(value):
        return "—"
    return f"{float(value):.2f}"


def _outcome_display_label(outcome) -> str:
    """Outcome badge -> human label (WIN->'Win', ..., invalidated->'Invalidated')."""
    if outcome in ("WIN", "LOSS", "TIMEOUT"):
        return dl.outcome_label(outcome)
    return dl.status_label(outcome)  # invalidated -> 'Invalidated'


def _outcome_color(outcome) -> str:
    """Outcome badge -> color (invalidated renders in the warning hue)."""
    if outcome in theme.OUTCOME_COLORS:
        return theme.OUTCOME_COLORS[outcome]
    if outcome == "invalidated":
        return theme.COLORS["warning"]
    return theme.COLORS["text"]


def _build_display(frame: pd.DataFrame) -> pd.DataFrame:
    """Build the human-readable History table frame (labels + composite P(win))."""
    return pd.DataFrame(
        {
            "Symbol": frame["symbol"],
            "Direction": frame["direction"].map(dl.direction_label),
            "Entry": frame["entry"].map(_fmt_price),
            "Outcome": frame["outcome"].map(_outcome_display_label),
            "R": frame["r"].map(_fmt_r),
            "P(win)": [
                f"{dl.pct(p)} [{dl.score_source_tag(ss)}]"
                for p, ss in zip(frame["p_win"], frame["score_source"].astype(str), strict=True)
            ],
            "Status": frame["status"].map(dl.status_label),
            "Closed": frame["closed_at"].map(lambda t: str(t)[:16]),
        }
    )


def _style(display: pd.DataFrame, frame: pd.DataFrame):
    """Color the Outcome + Status cells via the UI-SPEC binding (lines up by the
    shared filtered row position)."""
    outcome_colors = [_outcome_color(o) for o in frame["outcome"].tolist()]
    status_colors = [
        theme.STATUS_COLORS.get(s, theme.COLORS["text"]) for s in frame["status"].tolist()
    ]

    def _color_row(row: pd.Series) -> list:
        i = int(row.name)
        styles = []
        for col in display.columns:
            if col == "Outcome":
                styles.append(f"color: {outcome_colors[i]}")
            elif col == "Status":
                styles.append(f"color: {status_colors[i]}")
            else:
                styles.append("")
        return styles

    return display.style.apply(_color_row, axis=1)


def _column_config() -> dict:
    return {
        "Entry": st.column_config.TextColumn("Entry"),
        "Outcome": st.column_config.TextColumn("Outcome"),
        "R": st.column_config.TextColumn("R"),
        "P(win)": st.column_config.TextColumn("P(win)"),
        "Status": st.column_config.TextColumn("Status"),
        "Closed": st.column_config.TextColumn("Closed"),
    }


def render(filters: dict | None = None) -> None:
    """Render the History tab (DASH-04) — closed-setup lifecycle outcomes.

    Applies the global sidebar filters plus an optional outcome filter over
    ``data_layer.history_frame``; a missing/empty store renders the empty/error
    copy rather than raising.
    """
    try:
        cfg = dl.get_config()
        setups = dl.load_setups(cfg)
    except Exception:  # noqa: BLE001 - per-view robustness (only this tab)
        st.warning(_ERROR_COPY)
        return

    outcome = st.selectbox("Outcome", options=_OUTCOME_OPTIONS, key="hist_outcome")
    outcome_filter = None if outcome == "All" else outcome
    frame = dl.apply_filters(setups, filters or {}, sort_by=None)
    history = dl.history_frame(frame, outcome=outcome_filter)

    if history.empty:
        st.info(_EMPTY_COPY if setups.empty else _NO_MATCH_COPY)
        return

    display = _build_display(history)
    st.dataframe(
        _style(display, history),
        column_config=_column_config(),
        width="stretch",
        hide_index=True,
    )
