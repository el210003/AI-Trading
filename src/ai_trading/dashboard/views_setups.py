"""Setups tab view (DASH-01 table + DASH-02 chart + DASH-03 evidence trace).

The DASH-02 candlestick + DASH-03 evidence panel form the SINGLE visual anchor;
the table above is the navigation/selection surface. Honor the UI-SPEC honesty
rule: ``p_win`` always renders beside its ``score_source`` tag, ``heuristic``
in the warning hue, and a missing/empty store renders the Empty/Error state on
this view only (never a traceback).

MT5-free: only reads the persisted setup store + bar files via ``data_layer``.
"""

from __future__ import annotations

import json

import pandas as pd
import streamlit as st

from ai_trading.dashboard import charts, theme
from ai_trading.dashboard import data_layer as dl

#: UI-SPEC Copywriting contract.
EMPTY_STORE_COPY = (
    "The setup store is empty. Run the scheduled setup engine after an M15 bar "
    "close to populate setups, then refresh."
)
NO_MATCH_COPY = (
    "No setups match the current filters. Adjust the symbol, status, or date "
    "range — or wait for the next M15 bar close to generate fresh setups."
)
ERROR_COPY = (
    "Failed to load setups. The data store could not be read — check that the "
    "collector has run (data/bars) and the setup store is populated, then refresh."
)

_SYMBOL_OPTIONS = ("all", "long", "short")


def sidebar_filters() -> dict:
    """The global sidebar filter widgets (symbol/status/direction/min-prob/
    date) plus Reset Filters and Refresh, returning the filters dict.

    Reset Filters resets the widget state and ``st.rerun()``; Refresh re-queries
    the stores with ``st.rerun()`` (no ``@st.cache_data`` on this path — the
    UI-SPEC manual-refresh contract).
    """
    cfg = dl.get_config()
    setups = dl.load_setups(cfg)
    symbols = sorted(str(v) for v in setups["symbol"].dropna().unique()) if not setups.empty else []
    if not setups.empty:
        statuses = sorted(str(v) for v in setups["status"].dropna().unique())
    else:
        statuses = []

    with st.sidebar:
        st.markdown("**Filters**")
        sel_symbols = st.multiselect("Symbol", options=symbols, default=symbols, key="filt_symbols")
        sel_statuses = st.multiselect(
            "Status", options=statuses, default=statuses, key="filt_statuses"
        )
        direction = st.selectbox(
            "Direction", options=_SYMBOL_OPTIONS, index=0, key="filt_direction"
        )
        min_prob = st.slider("Min probability (%)", min_value=0, max_value=100, value=0,
                             key="filt_min_prob")
        picked = st.date_input("Date range", value=[], key="filt_dates")

        col_a, col_b = st.columns(2)
        with col_a:
            st.button("Reset Filters", on_click=_reset_filters, width="stretch")
        with col_b:
            if st.button("Refresh Setups", width="stretch", type="primary"):
                st.rerun()

    start_date = end_date = None
    if isinstance(picked, (list, tuple)) and len(picked) == 2:
        start_date, end_date = picked[0], picked[1]
    return {
        "symbols": sel_symbols,
        "statuses": sel_statuses,
        "direction": direction,
        "min_prob": int(min_prob),
        "start_date": start_date,
        "end_date": end_date,
    }


def _reset_filters() -> None:
    """Reset the sidebar filter widgets back to their defaults.

    Deletes the widget ``session_state`` keys inside an ``on_click`` callback so
    they re-initialize to the defaults on the next run (a widget key cannot be
    *set* after the widget is already instantiated in the same run).
    """
    for key in ("filt_symbols", "filt_statuses", "filt_direction", "filt_min_prob", "filt_dates"):
        st.session_state.pop(key, None)


def _build_display(frame: pd.DataFrame) -> pd.DataFrame:
    """Build the human-readable table frame (composite P(win) cell + status label)."""
    display = pd.DataFrame(
        {
            "Symbol": frame["symbol"],
            "Direction": frame["direction"].map(dl.direction_label),
            "Entry": frame["entry"].map(lambda v: _fmt_price(v)),
            "SL": frame["sl_price"].map(lambda v: _fmt_price(v)),
            "TP": frame["tp_price"].map(lambda v: _fmt_price(v)),
            "RR": frame["rr_at_decision"].map(lambda v: _fmt_rr(v)),
            "P(win)": [
                f"{dl.pct(p)} [{dl.score_source_tag(ss)}]"
                for p, ss in zip(frame["p_win"], frame["score_source"], strict=True)
            ],
            "Status": frame["status"].map(dl.status_label),
            "Created": frame["created_at"].map(lambda t: str(t)[:16]),
        }
    )
    return display


def _fmt_price(value) -> str:
    """Price formatting helper (blank on missing)."""
    if value is None or pd.isna(value):
        return "—"
    return f"{float(value):.5f}"


def _fmt_rr(value) -> str:
    if value is None or pd.isna(value):
        return "—"
    return f"{float(value):.2f}"


def _style(display: pd.DataFrame, frame: pd.DataFrame):
    """Color the Status + P(win) cells via the UI-SPEC binding (status chip /
    score_source honesty hue). Lines up by parallel row position (both frames
    share the filtered, reset index)."""
    source_colors = [dl.score_source_color(ss) for ss in frame["score_source"].tolist()]
    status_colors = [
        theme.STATUS_COLORS.get(st, theme.COLORS["text"]) for st in frame["status"].tolist()
    ]

    def _color_row(row: pd.Series) -> list:
        i = int(row.name)
        styles = []
        for col in display.columns:
            if col == "P(win)":
                styles.append(f"color: {source_colors[i]}")
            elif col == "Status":
                styles.append(f"color: {status_colors[i]}")
            else:
                styles.append("")
        return styles

    return display.style.apply(_color_row, axis=1)


def _column_config() -> dict:
    return {
        "Entry": st.column_config.TextColumn("Entry"),
        "SL": st.column_config.TextColumn("SL"),
        "TP": st.column_config.TextColumn("TP"),
        "P(win)": st.column_config.TextColumn("P(win)"),
        "Status": st.column_config.TextColumn("Status"),
        "Created": st.column_config.TextColumn("Created"),
    }


def render_table(filters: dict):
    """Render the DASH-01 setup table; returns the selected setup row (or None).

    Renders the Empty state (``st.info``) when the store is empty and a
    no-match state when filters exclude everything — never a traceback.
    """
    try:
        cfg = dl.get_config()
        setups = dl.load_setups(cfg)
    except Exception:  # noqa: BLE001 - per-view robustness (only this tab)
        st.warning(ERROR_COPY)
        return None

    if setups.empty:
        st.info(EMPTY_STORE_COPY)
        return None

    frame = dl.apply_filters(setups, filters)
    if frame.empty:
        st.info(NO_MATCH_COPY)
        return None

    display = _build_display(frame)
    selected = st.dataframe(
        _style(display, frame),
        column_config=_column_config(),
        width="stretch",
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        key="setup_table",
    )
    if selected is not None and getattr(selected, "selection", None) is not None:
        rows = selected.selection.rows
        if rows:
            return frame.iloc[int(rows[0])]
    return None


def render(filters: dict) -> None:
    """The Setups tab focal view: table (navigation) + selected candlestick +
    evidence trace. When a setup is selected it becomes the single visual anchor
    (DASH-02 + DASH-03)."""
    selected = render_table(filters)
    if selected is not None:
        _render_chart(selected)
        render_evidence(selected)


def _render_chart(setup) -> None:
    """Render the DASH-02 candlestick for ``setup`` (focal anchor)."""
    cfg = dl.get_config()
    symbol = str(setup.get("symbol"))
    timeframe = str(setup.get("timeframe") or "M15")
    bars = dl.load_bars(cfg, symbol, timeframe)
    zones = pd.DataFrame(
        [
            {
                "zone_range_high": setup.get("zone_range_high"),
                "zone_range_low": setup.get("zone_range_low"),
                "created_at": setup.get("created_at"),
            }
        ]
    )
    fig = charts.candlestick_chart(bars, setup, zones)
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": True})


# --- DASH-03 Evidence trace --------------------------------------------------

def _decode_evidence(setup) -> dict:
    """Decode the persisted ``evidence_json`` defensively (T-06-02): a malformed
    or absent object degrades to ``{}`` / a degraded note, never a raise."""
    raw = setup.get("evidence_json")
    if not raw:
        return {}
    try:
        decoded = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    return decoded if isinstance(decoded, dict) else {}


def _narrative_citation_list(setup) -> list:
    """Parse ``narrative_citations`` (JSON string) into a list; malformed -> []."""
    raw = setup.get("narrative_citations")
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return []
    return list(parsed) if isinstance(parsed, list) else []


def _sec_header(setup, evidence) -> None:
    """Section 1 — setup header (symbol · direction chip · entry/SL/TP + RR · time)."""
    symbol = evidence.get("symbol") or setup.get("symbol")
    direction = evidence.get("direction") or setup.get("direction")
    entry = _fmt_price(setup.get("entry"))
    sl = _fmt_price(setup.get("sl_price"))
    tp = _fmt_price(setup.get("tp_price"))
    rr = _fmt_rr(setup.get("rr_at_decision"))
    created = str(setup.get("created_at"))[:16]
    st.markdown(
        f"**1. Setup:** {symbol} · {dl.direction_label(direction)} · "
        f"Entry {entry} · SL {sl} · TP {tp} · RR {rr} · {created}"
    )


def _sec_bias(evidence) -> None:
    """Section 2 — bias & context (H1/H4 bias)."""
    h1 = evidence.get("bias_h1", "—")
    h4 = evidence.get("bias_h4", "—")
    st.markdown(f"**2. Bias & Context:** H1 {h1} · H4 {h4}")


def _sec_zone(setup) -> None:
    """Section 3 — tapped PD-zone + lifecycle state + boundaries band strip."""
    zone_id = setup.get("zone_id") or "—"
    state = setup.get("zone_state") or "—"
    lo = _fmt_price(setup.get("zone_range_low"))
    hi = _fmt_price(setup.get("zone_range_high"))
    st.markdown(f"**3. Zone:** {zone_id} · {state} · {lo} – {hi}")


def _sec_sweep(setup, evidence) -> None:
    """Section 4 — sweep event (event_id + pool_id + sweep level with ◇)."""
    event = evidence.get("event_id") or setup.get("event_id") or "—"
    pool = setup.get("pool_id") or "—"
    side = evidence.get("sweep_side") or "—"
    st.markdown(f"**4. Sweep:** ◇ {side} · event {event} · pool {pool}")


def _sec_ml(setup, evidence) -> None:
    """Section 5 — ML contributors (whole-percent p_win + top-N + score_source)."""
    score = setup.get("score_source")
    tag = dl.score_source_tag(score)
    pct = dl.pct(setup.get("p_win"))
    st.markdown(f"**5. ML Contributors:** P(win) {pct} [{tag}]")
    for c in evidence.get("top_contributors", []):
        sign = "+" if c.get("effect") == "positive" else "−"
        feature = c.get("feature", "?")
        contrib = c.get("contribution")
        try:
            value = f" {abs(float(contrib)):.2f}"
        except (TypeError, ValueError):
            value = ""
        st.markdown(f"- {sign}{value} {feature}")


def _sec_narrative(setup) -> None:
    """Section 6 — LLM narrative (verdict / confidence / agreement / reasoning /
    citations), with the honest ``⌀`` + reason fallback for an unavailable
    narrative (never blank, per the UI-SPEC honesty rule)."""
    status = setup.get("narrative_status")
    if status != "ok":
        reason = setup.get("narrative_reason") or str(status)
        st.markdown("**6. Narrative:**")
        st.warning(f"⌀ LLM narrative unavailable ({reason}) — ML-only evidence shown.")
        return
    verdict = setup.get("narrative_verdict") or "—"
    verdict_label = theme.VERDICT_LABELS.get(verdict, verdict)
    conf = setup.get("narrative_confidence")
    conf_s = f"{float(conf):.2f}" if conf is not None and not pd.isna(conf) else "—"
    agreement = setup.get("agreement")
    st.markdown(
        f"**6. Narrative:** {verdict_label} · confidence {conf_s} · "
        f"agreement {dl.agreement_label(agreement)}"
    )
    reasoning = setup.get("narrative_reasoning")
    if reasoning and not pd.isna(reasoning):
        st.markdown(str(reasoning))
    citations = _narrative_citation_list(setup)
    if citations:
        st.markdown(f"Citations: {', '.join(str(c) for c in citations)}")


def render_evidence(setup) -> None:
    """Render the full DASH-03 evidence trace in the fixed UI-SPEC order inside a
    bordered container. The persisted ``evidence_json`` object is untrusted
    display data (T-06-02): it is rendered only through native Streamlit widgets
    (``st.markdown`` without ``unsafe_allow_html``) — never injected as HTML.
    A malformed evidence object or an unavailable narrative degrades rather than
    raising.
    """
    evidence = _decode_evidence(setup)
    with st.container(border=True):
        st.markdown("### Evidence Trace")
        _sec_header(setup, evidence)
        _sec_bias(evidence)
        _sec_zone(setup)
        _sec_sweep(setup, evidence)
        _sec_ml(setup, evidence)
        _sec_narrative(setup)
