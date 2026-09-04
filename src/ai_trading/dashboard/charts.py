"""Plotly chart builders for the Phase-6 dashboard (DASH-02 + DASH-05).

Pure functions (no Streamlit import) so the figure layout / overlay contract can
be unit-tested directly and rendered via ``st.plotly_chart``.

``candlestick_chart`` renders the DASH-02 contract from 06-UI-SPEC.md:
- ``go.Candlestick`` with bull/bear up/down colors,
- entry (accent) / SL (bear) / TP (bull) ``add_hline`` hover lines,
- sweep ``◇`` diamond markers on the touched bar (per the evidence object),
- PD-zone ``add_shape`` shaded bands drawn ``layer="below"`` at ~14% opacity,
- fixed ``height=520`` and ``margin=dict(l=8, r=8, t=24, b=8)`` and
  ``hovermode="x unified"``.

``equity_curve`` renders the DASH-05 cumulative-R running line (bull hue,
locked 360px height / margin / x-unified hover) from the
``data_layer.cumulative_r_curve`` frame.
"""

from __future__ import annotations

import json

import pandas as pd
import plotly.graph_objects as go

from ai_trading.dashboard import theme

#: PD-zone band opacity (UI-SPEC: ~14%).
_ZONE_OPACITY = 0.14

#: Candlestick / equity fixed layout (UI-SPEC Spacing Scale exceptions).
_CANDLE_LAYOUT = dict(height=520, margin=dict(l=8, r=8, t=24, b=8), hovermode="x unified")


def _field(row, key, default=None):
    """Safely read a field from a row (pandas Series or dict)."""
    if row is None:
        return default
    try:
        value = row.get(key)
    except AttributeError:
        return default
    if value is None:
        return default
    try:
        if pd.isna(value):
            return default
    except (TypeError, ValueError):
        pass
    return value


def _sweep_marker(bars: pd.DataFrame, sweep_side: str):
    """Map a sweep side onto a bar price for the diamond marker.

    ``low`` sweeps sit at the lowest low, ``high`` sweeps at the highest high of
    the visible frame; returns ``(time_utc, price)`` or ``None``.
    """
    if bars is None or bars.empty:
        return None
    if sweep_side == "low":
        idx = bars["low"].idxmin()
        return pd.Timestamp(bars.loc[idx, "time_utc"]), float(bars.loc[idx, "low"])
    if sweep_side == "high":
        idx = bars["high"].idxmax()
        return pd.Timestamp(bars.loc[idx, "time_utc"]), float(bars.loc[idx, "high"])
    return None


def _sweep_side(setup) -> str | None:
    """Read ``sweep_side`` from the persisted evidence object (or the row)."""
    evidence_json = _field(setup, "evidence_json")
    if evidence_json:
        try:
            evidence = json.loads(evidence_json)
        except (TypeError, ValueError):
            evidence = {}
        side = evidence.get("sweep_side")
        if side:
            return str(side)
    return _field(setup, "sweep_side")


def candlestick_chart(bars: pd.DataFrame, setup, zones: pd.DataFrame | None = None) -> go.Figure:
    """Build the DASH-02 candlestick figure for ``setup`` over ``bars``.

    ``bars`` is an M15 frame; ``zones`` (optional) is a frame carrying
    ``zone_range_high`` / ``zone_range_low`` / ``created_at`` used for the
    PD-zone ``add_shape`` bands. ``setup`` carries ``entry`` / ``sl_price`` /
    ``tp_price`` and the ``evidence_json`` sweep. Missing/empty inputs yield an
    empty figure (defensive — never raises).
    """
    if bars is None or bars.empty:
        return go.Figure()

    fig = go.Figure(
        data=[
            go.Candlestick(
                x=bars["time_utc"],
                open=bars["open"],
                high=bars["high"],
                low=bars["low"],
                close=bars["close"],
                increasing_line_color=theme.COLORS["bull"],
                decreasing_line_color=theme.COLORS["bear"],
                name="OHLC",
            )
        ]
    )

    # --- Entry / SL / TP hover lines (UI-SPEC: accent entry, bear SL, bull TP) ---
    entry = _field(setup, "entry")
    sl = _field(setup, "sl_price")
    tp = _field(setup, "tp_price")
    if entry is not None:
        fig.add_hline(y=float(entry), line_color=theme.COLORS["accent"],
                      line_width=1.5, annotation_text="Entry", name="entry")
    if sl is not None:
        fig.add_hline(y=float(sl), line_color=theme.COLORS["bear"],
                      line_width=1.5, annotation_text="SL", name="sl")
    if tp is not None:
        fig.add_hline(y=float(tp), line_color=theme.COLORS["bull"],
                      line_width=1.5, annotation_text="TP", name="tp")

    # --- Sweep ◇ marker from the evidence object ---
    sweep = _sweep_marker(bars, _sweep_side(setup))
    if sweep is not None:
        fig.add_trace(
            go.Scatter(
                x=[sweep[0]],
                y=[sweep[1]],
                mode="markers",
                marker=dict(symbol="diamond", size=10, color=theme.COLORS["accent"]),
                name="Sweep",
            )
        )

    # --- PD-zone shaded bands (layer="below", ~14% opacity) ---
    if zones is not None and not zones.empty:
        for _, zone in zones.iterrows():
            r_high = _field(zone, "zone_range_high")
            r_low = _field(zone, "zone_range_low")
            if r_high is None or r_low is None:
                continue
            fig.add_shape(
                type="rect",
                xref="x", yref="y",
                x0=bars["time_utc"].iloc[0],
                x1=bars["time_utc"].iloc[-1],
                y0=float(r_low), y1=float(r_high),
                layer="below",
                fillcolor=theme.COLORS["accent"],
                opacity=_ZONE_OPACITY,
                line=dict(width=0),
            )

    fig.update_layout(**_CANDLE_LAYOUT)
    fig.update_xaxes(rangeslider_visible=False)
    return fig


def equity_curve(data: pd.DataFrame | None = None, *, symbol: str | None = None) -> go.Figure:
    """DASH-05 cumulative-R equity curve (plan 06-03).

    ``data`` is the ``{time_utc, cum_r}`` frame from
    ``data_layer.cumulative_r_curve``; returns a ``go.Scatter`` cumulative-R
    running line (bull ``#26A69A``, per the UI-SPEC equity binding) at the
    locked 360px height / margin / ``x unified`` hovermode. ``symbol`` only
    names the trace for readability (aggregate vs per-symbol toggle). A
    missing/empty frame returns an empty figure (never raises).
    """
    fig = go.Figure()
    if data is not None and not data.empty:
        fig.add_trace(
            go.Scatter(
                x=data["time_utc"],
                y=data["cum_r"],
                mode="lines",
                line=dict(color=theme.COLORS["bull"], width=2),
                name=f"cumulative R ({symbol or 'all'})",
            )
        )
    fig.update_layout(height=360, margin=dict(l=8, r=8, t=24, b=8), hovermode="x unified")
    return fig
