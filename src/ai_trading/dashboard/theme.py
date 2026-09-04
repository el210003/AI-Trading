"""Locked Phase-6 dashboard theme constants — the SINGLE source of truth for
the 06-UI-SPEC.md palette and the status / outcome / agreement / score_source
color binding plus the enum-to-human display-label mapping.

Every view and plot imports its hex colors and labels from here; no hardcoded
hex or human label exists elsewhere in ``ai_trading.dashboard``. Values are
taken verbatim from 06-UI-SPEC.md (the approved visual contract) — do not
re-open style decisions by introducing ad hoc colors here.

``text``/``muted`` are included for the secondary-text and neutral-tag hues
(contrast-checked in the UI-SPEC). All numeric probability / price / R labels
should be rendered with ``font-variant-numeric: tabular-nums`` per the
typography contract (applied at the render site).

MT5-free; pure constants only.
"""

from __future__ import annotations

# --- Palette (UI-SPEC: dominant/secondary/accent + semantic set) -----------
COLORS: dict[str, str] = {
    "dominant": "#0B0F17",
    "secondary": "#141A26",
    "accent": "#00C7FF",
    "bull": "#26A69A",
    "bear": "#EF5350",
    "warning": "#E0A500",
    "destructive": "#E5484D",
    "text": "#E6EDF3",
    "muted": "#8B99AC",
}

# --- Status chip color binding (UI-SPEC color-binding table) ---------------
STATUS_COLORS: dict[str, str] = {
    "active": COLORS["accent"],          # ● active (live)
    "tp_hit": COLORS["bull"],            # ✓ TP hit
    "sl_hit": COLORS["bear"],            # ✗ SL hit
    "expired": COLORS["warning"],        # ⌀ expired
    "invalidated": COLORS["warning"],    # ◌ invalidated (structure break)
}

# --- Outcome badge color binding ------------------------------------------
OUTCOME_COLORS: dict[str, str] = {
    "WIN": COLORS["bull"],
    "LOSS": COLORS["bear"],
    "TIMEOUT": COLORS["warning"],
}

# --- Agreement flag chip color binding ------------------------------------
AGREEMENT_COLORS: dict[str, str] = {
    "agree": COLORS["bull"],       # ✓ ML↔LLM agree
    "disagree": COLORS["bear"],    # ✗ ML↔LLM disagree
    "unclear": COLORS["warning"],  # ⌀ unclear
}

# --- Direction color binding ----------------------------------------------
DIRECTION_COLORS: dict[str, str] = {
    "long": COLORS["bull"],
    "short": COLORS["bear"],
}

# --- score_source color binding (UI-SPEC honor the honesty rule) ----------
# ``heuristic`` renders in the warning hue (weaker evidence); ml / ml_llm in
# the neutral muted hue.
SCORE_SOURCE_COLORS: dict[str, str] = {
    "ml": COLORS["muted"],
    "ml_llm": COLORS["muted"],
    "heuristic": COLORS["warning"],
}

# --- Enum -> human display label (UI-SPEC Copywriting / wording contract) --
STATUS_LABELS: dict[str, str] = {
    "active": "Active",
    "tp_hit": "TP Hit",
    "sl_hit": "SL Hit",
    "expired": "Expired",
    "invalidated": "Invalidated",
}

OUTCOME_LABELS: dict[str, str] = {
    "WIN": "Win",
    "LOSS": "Loss",
    "TIMEOUT": "Timeout",
}

AGREEMENT_LABELS: dict[str, str] = {
    "agree": "Agree",
    "disagree": "Disagree",
    "unclear": "Unclear",
}

SCORE_SOURCE_LABELS: dict[str, str] = {
    "ml": "ML",
    "ml_llm": "ML+LLM",
    "heuristic": "Heuristic",
}

DIRECTION_LABELS: dict[str, str] = {
    "long": "Long",
    "short": "Short",
}

VERDICT_LABELS: dict[str, str] = {
    "confirm": "Confirm",
    "refute": "Refute",
}

# --- Status chip glyphs (UI-SPEC Component Inventory / indication) ---------
STATUS_GLYPHS: dict[str, str] = {
    "active": "●",
    "tp_hit": "✓",
    "sl_hit": "✗",
    "expired": "⌀",
    "invalidated": "◌",
}

# --- Metric labels (UI-SPEC DASH-05 metric-label contract) ------------------
METRIC_LABELS: dict[str, str] = {
    "win_rate": "Win Rate",
    "profit_factor": "Profit Factor",
    "expectancy_r": "Expectancy (R)",
    "trades": "Trades",
}
