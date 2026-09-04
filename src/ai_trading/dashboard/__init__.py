"""Phase-6 Streamlit dashboard package (DASH-01/02/03 + app shell).

Package layout:
- ``theme.py``: the locked 06-UI-SPEC palette + color-binding/source of truth.
- ``data_layer.py``: the defensive, pure-reader store/bars surface + label
  helpers the views consume (the testable data layer).
- ``charts.py``: plotly candlestick (entry/SL/TP + sweep + PD zones) + equity.
- ``views_setups.py`` / ``views_history.py`` / ``views_performance.py`` /
  ``views_health.py``: the four tab views (Setups is the DASH-01/02/03 focal
  view; the others are empty-state stubs until plan 06-03).
- ``app.py``: the ``st.set_page_config`` + health strip + ``st.tabs`` shell.

MT5-free by design: the dashboard only reads persisted stores.
"""

from __future__ import annotations

from ai_trading.dashboard import data_layer, theme  # noqa: F401
from ai_trading.dashboard.data_layer import (  # noqa: F401 (convenience re-exports)
    apply_filters,
    load_bars,
    load_cfg,
    load_setups,
    pct,
    score_source_color,
    score_source_tag,
    status_label,
)
from ai_trading.dashboard.theme import COLORS, STATUS_COLORS  # noqa: F401
