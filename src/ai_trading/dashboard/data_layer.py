"""Defensive, UI-facing data layer for the Phase-6 dashboard (DASH-01/02/03).

The dashboard is a PURE READER: it never computes setup statistics or re-derives
an entry/SL/TP/zone level; it only reconstructs the persisted setup store and
bar files into the frames the views render. MT5-free by construction (no
MetaTrader5 import anywhere).

Threat mitigations (06-02 threat register):
- T-06-01 (paths): every derived path (data root / setups dir) resolves under
  ``cfg.bars_dir.parent`` via a resolve-under-root guard (mirrors
  ``backtest.runner._output_dirs``); a traversal raises ``ValueError``.
- T-06-03 (missing/empty store): ``load_setups`` / ``load_bars`` never raise on
  a missing or empty store — they return the schema-correct empty frame so the
  views render the Empty/Error state (``st.info``) instead of a traceback.
- T-06-06 (filter typing): ``apply_filters`` treats filter values as bounded /
  validated inputs (multiselect over known enum sets, min-prob is 0-100) and
  never trusts an unsanitized value to reach a query.

The label / color / percent helpers are the UI-SPEC honesty surface:
``p_win`` is always rendered beside its ``score_source`` tag and ``heuristic``
renders in the warning hue — never a bare probability.
"""

from __future__ import annotations

import os
from pathlib import Path

import pandas as pd

from ai_trading.backtest.stats import canonical_stats, stats_by_symbol_timeframe
from ai_trading.config import load_config
from ai_trading.dashboard import theme
from ai_trading.setup import store as setup_store
from ai_trading.stores.bar_store import bar_path, read_bars

__all__ = [
    "load_cfg",
    "config_path",
    "get_config",
    "data_root_guarded",
    "healthy_config",
    "setup_dir_guarded",
    "load_setups",
    "apply_filters",
    "load_bars",
    "status_label",
    "outcome_label",
    "agreement_label",
    "score_source_tag",
    "score_source_color",
    "direction_label",
    "pct",
    "history_frame",
    "performance_stats",
    "cumulative_r_curve",
]

#: ``all`` is the sidebar-direction sentinel that means "no direction filter".
_DIRECTION_ALL = "all"

_STR_DTYPE = pd.StringDtype()


def load_cfg(path="config.toml"):
    """Load the frozen ``Config`` from ``path`` (defaults to ``config.toml``)."""
    return load_config(Path(path))


def config_path() -> str:
    """Resolve the app's config path: ``AITRADING_CONFIG`` env var, then
    ``st.secrets['CONFIG_PATH']``, then ``config.toml``.

    The env var (and the secrets override) let the offline ``AppTest`` suites
    point the dashboard at a fixture config without touching the committed
    ``config.toml``.
    """
    env = os.environ.get("AITRADING_CONFIG")
    if env:
        return env
    try:
        import streamlit as st

        path = st.secrets.get("CONFIG_PATH", None)
        if path:
            return str(path)
    except Exception:  # noqa: BLE001 - outside a running script secret access may fail
        pass
    return "config.toml"


def get_config():
    """Return the dashboard's frozen ``Config`` (see ``config_path``)."""
    return load_cfg(config_path())


def data_root_guarded(cfg) -> Path:
    """The guarded ``data/`` root derived from ``cfg.bars_dir.parent``.

    Mirrors ``backtest.runner._output_dirs`` (ASVS V4 / threat T-06-01): the
    bars dir must resolve under the data root — traversal refused.
    """
    root = Path(cfg.bars_dir).parent
    root_resolved = root.resolve()
    bars_resolved = Path(cfg.bars_dir).resolve()
    if bars_resolved != root_resolved and root_resolved not in bars_resolved.parents:
        raise ValueError(
            f"bars dir {bars_resolved} must resolve under the data root "
            f"{root_resolved} (path traversal refused)"
        )
    return root


def healthy_config(cfg) -> Path:
    """Resolve-under-root guarded data root (alias of ``data_root_guarded``).

    Raised by the app to assert a config points at a sane, traversal-safe data
    root before any store read.
    """
    return data_root_guarded(cfg)


def setup_dir_guarded(cfg) -> Path:
    """Path to the guarded ``data/setups`` directory (threat T-06-01): must
    resolve under the data root — traversal refused."""
    root = data_root_guarded(cfg)
    root_resolved = root.resolve()
    setups = root / "setups"
    resolved = setups.resolve()
    if resolved != root_resolved and root_resolved not in resolved.parents:
        raise ValueError(
            f"setup store directory {resolved} must resolve under the data root "
            f"{root_resolved} (path traversal refused)"
        )
    return setups


def load_setups(cfg) -> pd.DataFrame:
    """Read the setup store defensively (threat T-06-03): a missing or empty
    store returns the schema-correct empty frame (never raises) so the views
    render the Empty state. Anything read is already ``SETUP_COLUMNS``-shaped."""
    return setup_store.read_setups(cfg)


def load_bars(cfg, symbol: str, timeframe: str) -> pd.DataFrame:
    """Read a bar file defensively (threat T-06-03): missing file -> empty frame
    with the canonical normalize columns (never raises)."""
    return read_bars(bar_path(cfg.bars_dir, symbol, timeframe))


def apply_filters(setups: pd.DataFrame, filters: dict, *,
                  sort_by: str | None = "created_at", sort_desc: bool = True) -> pd.DataFrame:
    """Return a filtered (and sorted) copy of ``setups`` per UI-SPEC DASH-01.

    ``filters`` is a dict (as built by ``views_setups.sidebar_filters``):
    - ``symbols``: iterable of symbols (multiselect; empty/None = all).
    - ``statuses``: iterable of status enums (multiselect; empty/None = all).
    - ``direction``: "long" | "short" | "all" (selectbox).
    - ``min_prob``: whole percent in [0, 100] compared against the
      ``score_source``-tagged ``p_win`` (0.62 -> 62%).
    - ``start_date`` / ``end_date``: date bounds on ``created_at`` (end is
      inclusive of the whole end day).

    Sorting defaults to ``created_at`` newest-first; ``sort_by=None`` disables.
    Input is never mutated; returns a new frame.
    """
    df = setups
    symbols = filters.get("symbols")
    if symbols:
        df = df[df["symbol"].isin(symbols)]
    statuses = filters.get("statuses")
    if statuses:
        df = df[df["status"].isin(statuses)]
    direction = filters.get("direction")
    if direction and direction != _DIRECTION_ALL:
        df = df[df["direction"] == direction]
    min_prob = filters.get("min_prob")
    if min_prob is not None:
        try:
            floor = float(min_prob)
        except (TypeError, ValueError):
            floor = 0.0
        df = df[df["p_win"].notna() & (df["p_win"] * 100.0 >= floor)]
    start_date = filters.get("start_date")
    if start_date is not None:
        created = pd.to_datetime(df["created_at"], errors="coerce")
        df = df[created >= pd.Timestamp(start_date)]
    end_date = filters.get("end_date")
    if end_date is not None:
        created = pd.to_datetime(df["created_at"], errors="coerce")
        end_inclusive = pd.Timestamp(end_date) + pd.Timedelta(days=1) - pd.Timedelta(microseconds=1)
        df = df[created <= end_inclusive]
    if sort_by:
        df = df.sort_values(sort_by, ascending=not sort_desc)
    return df.reset_index(drop=True)


# --- UI-SPEC display-label / color / percent helpers (single source) --------

def status_label(status) -> str:
    """Enum -> human status label ('active' -> 'Active')."""
    return theme.STATUS_LABELS.get(status, str(status))


def outcome_label(outcome) -> str:
    """Enum -> human outcome label ('WIN' -> 'Win')."""
    return theme.OUTCOME_LABELS.get(outcome, str(outcome))


def agreement_label(agreement) -> str:
    """Enum -> human agreement label ('agree' -> 'Agree')."""
    return theme.AGREEMENT_LABELS.get(agreement, str(agreement))


def score_source_tag(score_source) -> str:
    """Enum -> human score_source tag ('ml_llm' -> 'ML+LLM')."""
    return theme.SCORE_SOURCE_LABELS.get(score_source, str(score_source))


def score_source_color(score_source) -> str:
    """score_source -> color (heuristic in the warning hue, per UI-SPEC)."""
    return theme.SCORE_SOURCE_COLORS.get(score_source, theme.COLORS["muted"])


def direction_label(direction) -> str:
    """Enum -> human direction label ('long' -> 'Long')."""
    return theme.DIRECTION_LABELS.get(direction, str(direction))


def pct(p) -> str:
    """Whole-percent formatter ('0.62' -> '62%'); non-finite -> '—'."""
    if p is None:
        return "—"
    try:
        value = float(p)
    except (TypeError, ValueError):
        return "—"
    if pd.isna(value):
        return "—"
    return f"{round(value * 100):d}%"


# --- History (DASH-04) --------------------------------------------------------

#: Exact output schema of ``history_frame`` (DASH-04 lifecycle-outcome table).
HISTORY_COLUMNS = (
    "symbol",
    "direction",
    "entry",
    "outcome",
    "r",
    "p_win",
    "score_source",
    "status",
    "closed_at",
)

#: Terminal setup statuses that belong on the History tab (the lifecycle
#: outcomes every emitted setup reaches, per DASH-04).
RESOLVED_STATUSES = ("tp_hit", "sl_hit", "expired", "invalidated")

#: Terminal status -> the outcome badge enum the History tab shows. ``invalidated``
#: is a structure break, never an entry, so it has NO WIN/LOSS/TIMEOUT outcome —
#: it keeps its own status (the UI renders it as its own chip, not a badge).
STATUS_OUTCOME = {
    "tp_hit": "WIN",
    "sl_hit": "LOSS",
    "expired": "TIMEOUT",
    "invalidated": "invalidated",
}


def _empty_history_frame() -> pd.DataFrame:
    """Empty frame with exactly ``HISTORY_COLUMNS`` and pinned dtypes."""
    data = {
        "symbol": pd.Series(dtype=_STR_DTYPE),
        "direction": pd.Series(dtype=_STR_DTYPE),
        "entry": pd.Series(dtype="float64"),
        "outcome": pd.Series(dtype=_STR_DTYPE),
        "r": pd.Series(dtype="float64"),
        "p_win": pd.Series(dtype="float64"),
        "score_source": pd.Series(dtype=_STR_DTYPE),
        "status": pd.Series(dtype=_STR_DTYPE),
        "closed_at": pd.Series(dtype="datetime64[ns]"),
    }
    return pd.DataFrame(data)[list(HISTORY_COLUMNS)]


def history_frame(setups: pd.DataFrame, *, outcome: str | None = None) -> pd.DataFrame:
    """DASH-04: every emitted setup's lifecycle outcome, sorted newest-first.

    Keeps only the terminal statuses (``tp_hit`` / ``sl_hit`` / ``expired`` plus
    the ``invalidated`` structural breaks) and derives the outcome badge enum via
    ``STATUS_OUTCOME`` — ``tp_hit``->``WIN``, ``sl_hit``->``LOSS``,
    ``expired``->``TIMEOUT``, ``invalidated`` kept as its own status (no
    WIN/LOSS). The ``r`` column prefers each setup's ``r_net`` (falling back to
    ``r_gross``) so the live-vs-backtest structural-R view stays consistent with
    the Performance panel. Sorts by ``closed_at`` descending (newest-first). A
    missing/empty store returns the schema-correct empty frame (T-06-03); the
    optional ``outcome`` badge narrows the rows to a single outcome.
    """
    if setups is None or setups.empty:
        return _empty_history_frame()
    resolved = setups[setups["status"].isin(RESOLVED_STATUSES)].copy()
    if resolved.empty:
        return _empty_history_frame()
    resolved["outcome"] = resolved["status"].map(STATUS_OUTCOME)
    resolved["r"] = resolved["r_net"].where(resolved["r_net"].notna(), resolved["r_gross"])
    if outcome is not None:
        resolved = resolved[resolved["outcome"] == outcome]
    sorted_frame = resolved.sort_values("closed_at", ascending=False, na_position="last")
    return sorted_frame[list(HISTORY_COLUMNS)].reset_index(drop=True)


# --- Performance (DASH-05) ---------------------------------------------------

#: Statuses whose R contributes to the Performance stats/equity (an entry was
#: taken; ``invalidated`` never entered so it is excluded).
PERF_OUTCOME_STATUSES = ("tp_hit", "sl_hit", "expired")

#: Status -> outcome badge enum fed into the reused ``stats`` functions.
PERF_OUTCOME = {
    "tp_hit": "WIN",
    "sl_hit": "LOSS",
    "expired": "TIMEOUT",
}

#: Label-like frame schema the reused ``stats_by_symbol_timeframe`` requires.
_LABEL_LIKE_COLUMNS = ("symbol", "timeframe", "outcome", "r_raw", "r_net")


def _empty_label_like_frame() -> pd.DataFrame:
    """Empty label-like frame with the exact ``stats`` input columns."""
    data = {
        "symbol": pd.Series(dtype=_STR_DTYPE),
        "timeframe": pd.Series(dtype=_STR_DTYPE),
        "outcome": pd.Series(dtype=_STR_DTYPE),
        "r_raw": pd.Series(dtype="float64"),
        "r_net": pd.Series(dtype="float64"),
    }
    return pd.DataFrame(data)[list(_LABEL_LIKE_COLUMNS)]


def performance_stats(setups: pd.DataFrame) -> dict:
    """DASH-05: honest WR/PF/expectancy/R from the resolved-setup trace.

    Builds a label-like frame (``symbol`` / ``timeframe`` / ``outcome`` /
    ``r_raw`` / ``r_net``) from the resolved setups with ``r_raw == r_net ==
    r_gross`` (the pinned A4 signals-only structural R basis) and outcome mapped
    ``tp_hit->WIN`` / ``sl_hit->LOSS`` / ``expired->TIMEOUT``. ``invalidated`` /
    ``pending`` / ``active`` are excluded. Reuses ``stats_by_symbol_timeframe``
    (per-symbol) and ``canonical_stats`` (whole-frame aggregate) so live-numbers
    agree with the backtest semantics. Returns ``{"labels", "stats",
    "aggregate"}``; a store with no resolved rows yields the schema-correct empty
    stats frame and a nan aggregate (never raises, T-06-03).
    """
    if setups is None or setups.empty:
        labels = _empty_label_like_frame()
    else:
        resolved = setups[setups["status"].isin(PERF_OUTCOME_STATUSES)]
        if resolved.empty:
            labels = _empty_label_like_frame()
        else:
            labels = pd.DataFrame(
                {
                    "symbol": resolved["symbol"].astype(_STR_DTYPE),
                    "timeframe": resolved["timeframe"].astype(_STR_DTYPE),
                    "outcome": resolved["status"].map(PERF_OUTCOME).astype(_STR_DTYPE),
                    "r_raw": resolved["r_gross"],
                    "r_net": resolved["r_gross"],
                }
            )[list(_LABEL_LIKE_COLUMNS)]
    stats = stats_by_symbol_timeframe(labels)
    aggregate = canonical_stats(labels, "r_net")
    return {"labels": labels, "stats": stats, "aggregate": aggregate}


def cumulative_r_curve(setups: pd.DataFrame, *, symbol: str | None = None) -> pd.DataFrame:
    """DASH-05 equity curve: sorted-by-``closed_at`` cumulative sums of ``r_gross``.

    Keeps the resolved outcomes (``tp_hit``/``sl_hit``/``expired``; structural
    breaks excluded), filters to ``symbol`` when given, sorts ascending by
    ``closed_at``, and returns a ``{time_utc, cum_r}`` frame (cumulative R for
    the running equity chart). A missing/empty store returns the schema-correct
    empty frame (never raises).
    """
    if setups is None or setups.empty:
        return _empty_curve_frame()
    resolved = setups[setups["status"].isin(PERF_OUTCOME_STATUSES)].copy()
    if symbol is not None:
        resolved = resolved[resolved["symbol"] == symbol]
    if resolved.empty:
        return _empty_curve_frame()
    resolved = resolved.sort_values("closed_at", ascending=True, na_position="last")
    curve = pd.DataFrame(
        {
            "time_utc": pd.to_datetime(resolved["closed_at"]),
            "cum_r": resolved["r_gross"].fillna(0.0).cumsum(),
        }
    )
    return curve.reset_index(drop=True)


def _empty_curve_frame() -> pd.DataFrame:
    """Empty equity-curve frame with the ``{time_utc, cum_r}`` schema."""
    return pd.DataFrame(
        {"time_utc": pd.Series(dtype="datetime64[ns]"), "cum_r": pd.Series(dtype="float64")}
    )
