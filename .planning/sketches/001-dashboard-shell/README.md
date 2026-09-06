---
sketch: 001
name: dashboard-shell
question: "Which bold trading-terminal direction makes the setups surface feel stunning?"
winner: "D"
tags: [dashboard, palette, layout, trading-terminal, dark, light]
---

# Sketch 001: Dashboard Shell — Bold Trading Terminal

## Design Question

The v1 dashboard is a utilitarian locked spec (06-UI-SPEC). Which bold
trading-terminal direction (brief: TradingView / Binance Pro) should the
modernized shell take — palette, material, density, and component treatment
across the full Setups surface (health strip, KPI cards, filters, setup
table, candlestick, evidence trace)?

## How to View

open .planning/sketches/001-dashboard-shell/index.html

## Variants

- **A: Neon Glass (Binance-like)** — near-black #05070D, glassy blurred panels, neon cyan glow accents, gradient KPI edge-bars, fully-rounded pills
- **B: Dense Charcoal (TradingView-like)** — #131722 charcoal, hairline borders, compact rows, inline stat-bar KPIs, squared pills, tabular numerals everywhere
- **C: Aurora Gradient Glow** — deep navy with cyan/violet aurora background, gradient-text KPI values, gradient-tinted glass cards, sticky detail rail
- **D: Neon Glass + Wide Desk ★ WINNER** — A's material on a wider canvas (min(1800px, 96vw)); compact monospace-numeral table (all 11 columns, tight cells) sized to content, chart + evidence rail takes the remaining ~55%

## Winner Notes (D)

- Both DARK and LIGHT themes selectable and tuned per variant (toolbar switcher; themes/default.css + themes/light.css). The real app should expose the same dark/light choice.
- Chart readability rules discovered in review: zone band needs fill >= .16 + .55 dashed border in dark; gridlines >= .16 white (dark) with in-plot price labels; vertical dashed time lines; Entry/SL/TP axis gutter >= 104px (clips otherwise) with monospace tabular labels on soft color chips.
- Table: compact density wins over airy spacing when the chart rail gets the freed width.

## What to Look For

- **Trust signal vs noise**: which treatment makes P(win) bars, contributor bars, and the ML↔LLM agreement badge read as authoritative?
- **Density**: B fits ~40% more rows on screen at the cost of breathing room — right trade-off for a signals desk?
- **Chart harmony**: how the candlestick's level lines (Entry/SL/TP), sweep diamond, and PD-zone band sit against each shell
- **Implementability in Streamlit**: all three are CSS-injection + plotly-template level in Streamlit — judge feel, not feasibility
- Toolbar (bottom-right): viewport widths + annotation mode; click table rows to see the detail panel sync; evidence sections collapse
