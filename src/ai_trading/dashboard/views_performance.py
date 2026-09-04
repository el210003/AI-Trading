"""Performance tab view (DASH-05) — the honest stats + equity surface.

Renders the KPI cards (Win Rate / Profit Factor / Expectancy (R)) plus a
trade-count caption, the per-symbol breakdown, and the cumulative-R equity
curve with a symbol toggle. All numbers come from the reused Phase-3
``stats`` functions via ``data_layer.performance_stats`` — no recomputed stat
math. A missing/empty store renders the UI-SPEC empty/copy state (never a
traceback). The live-vs-backtest caveat (D-01/D-04) is surfaced as a caption:
live is a trigger-filtered subset of the backtest universe.

MT5-free: only reads the persisted setup store via ``data_layer``.
"""

from __future__ import annotations

import math

import pandas as pd
import streamlit as st

from ai_trading.dashboard import charts, theme
from ai_trading.dashboard import data_layer as dl

#: UI-SPEC Copywriting contract.
_EMPTY_COPY = (
    "No performance stats yet. They will appear here once setups have closed "
    "outcomes (TP hit / SL hit / expired)."
)
_ERROR_COPY = (
    "Failed to load performance stats. The data store could not be read — check "
    "that the setup store is populated, then refresh."
)
_CAVEAT_COPY = (
    "Live is a trigger-filtered subset of the backtest universe (live limit-trigger "
    "fill vs the backtest next-open fill); R is structural (signals-only, no cost model)."
)

#: UI-SPEC DASH-05 metric labels.
_WIN_RATE_LABEL = theme.METRIC_LABELS["win_rate"]
_PROFIT_FACTOR_LABEL = theme.METRIC_LABELS["profit_factor"]
_EXPECTANCY_LABEL = theme.METRIC_LABELS["expectancy_r"]
_TRADES_LABEL = theme.METRIC_LABELS["trades"]


def _fmt_pct(value) -> str:
    """Whole-percent for the Win Rate KPI (fraction -> '%'); non-finite -> '—'."""
    if value is None or pd.isna(value):
        return "—"
    return f"{float(value) * 100:.0f}%"


def _fmt_2dp(value) -> str:
    if value is None or pd.isna(value):
        return "—"
    if isinstance(value, float) and math.isinf(value):
        return "∞"
    return f"{float(value):.2f}"


def _fmt_3dp(value) -> str:
    if value is None or pd.isna(value):
        return "—"
    if isinstance(value, float) and math.isinf(value):
        return "∞"
    return f"{float(value):.3f}"


def _aggregate_view(agg: dict) -> dict:
    """Flatten a canonical_stats aggregate into the display fields (net variant)."""
    wr = agg.get("win_rate")
    wr = float(wr) if wr is not None and not pd.isna(wr) else float("nan")
    pf = agg.get("profit_factor")
    pf = float(pf) if pf is not None and not pd.isna(pf) else float("nan")
    exp = agg.get("expectancy")
    exp = float(exp) if exp is not None and not pd.isna(exp) else float("nan")
    return {
        "trades": int(agg.get("trades") or 0),
        "win_rate": wr,
        "profit_factor": pf,
        "expectancy": exp,
    }


def _render_kpis(agg: dict) -> None:
    """Render the 3-up KPI cards + trade-count caption (UI-SPEC DASH-05)."""
    view = _aggregate_view(agg)
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric(_WIN_RATE_LABEL, _fmt_pct(view["win_rate"]))
    with col2:
        st.metric(_PROFIT_FACTOR_LABEL, _fmt_2dp(view["profit_factor"]))
    with col3:
        st.metric(_EXPECTANCY_LABEL, _fmt_3dp(view["expectancy"]))
    st.caption(f"{_TRADES_LABEL}: {view['trades']}")
    st.caption(_CAVEAT_COPY)


def _render_breakdown(stats_frame: pd.DataFrame) -> None:
    """Render the per-symbol breakdown (net variant of WR/PF/expectancy/trades)."""
    if stats_frame.empty:
        return
    display = pd.DataFrame(
        {
            "Symbol": stats_frame["symbol"],
            _TRADES_LABEL: stats_frame["trades"],
            _WIN_RATE_LABEL: stats_frame["net_win_rate"].map(_fmt_pct),
            _PROFIT_FACTOR_LABEL: stats_frame["net_profit_factor"].map(_fmt_2dp),
            _EXPECTANCY_LABEL: stats_frame["net_expectancy"].map(_fmt_3dp),
        }
    )
    st.subheader("Per Symbol")
    st.dataframe(display, width="stretch", hide_index=True)


def _render_equity(setups: pd.DataFrame, symbols: list) -> None:
    """Render the cumulative-R equity curve with a symbol toggle (aggregate vs
    per-symbol, per the UI-SPEC interaction contract)."""
    st.subheader("Equity Curve (cumulative R)")
    option = st.selectbox("Symbol", ["All"] + symbols, key="perf_symbol")
    symbol = None if option == "All" else option
    curve = dl.cumulative_r_curve(setups, symbol=symbol)
    fig = charts.equity_curve(curve, symbol=symbol)
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": True})


def render(filters: dict | None = None) -> None:
    """Render the Performance tab (DASH-05) — KPI cards + per-symbol breakdown +
    cumulative-R equity curve. An empty resolved set renders the UI-SPEC empty
    state rather than raising."""
    try:
        cfg = dl.get_config()
        setups = dl.load_setups(cfg)
    except Exception:  # noqa: BLE001 - per-view robustness (only this tab)
        st.warning(_ERROR_COPY)
        return

    result = dl.performance_stats(setups)
    if result["labels"].empty:
        st.info(_EMPTY_COPY)
        return

    _render_kpis(result["aggregate"])
    symbols = sorted(str(v) for v in result["stats"]["symbol"].dropna().unique())
    _render_breakdown(result["stats"])
    _render_equity(setups, symbols)
