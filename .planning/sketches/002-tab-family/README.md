---
sketch: 002
name: tab-family
question: "Do History/Performance/Health/Settings look native to Variant D — and which tab nav chrome fits a wide shell?"
winner: "A"
tags: [layout, navigation, consistency, tabs, dark, light]
---

# Sketch 002: Tab Family — Variant D consistency

## Design Question

Sketch 001 locked the Setups surface (winner D, Neon Glass + Wide Desk), but the
app has five tabs. Do History, Performance, Health and Settings carry the same
glass material in both themes — and does the underline tab strip still serve a
1800px-wide shell, or is a rail/segmented control a better anchor?

## How to View

open .planning/sketches/002-tab-family/index.html

## Variants (nav chrome — all render the SAME five tab panes)

- **A: Underline tabs (001 pattern)** — status-quo bottom-border tab strip; path of least resistance in Streamlit
- **B: Icon rail** — compact left icon rail with hover tooltips; keeps nav persistent while content uses full width
- **C: Segmented pills** — Binance-style floating segmented control with gradient-active pill

## What to Look For

- Which nav makes the wide 1800px canvas feel intentional rather than stretched
- Whether History / Performance (equity curve + per-symbol + caveat caption) / Health (feeds + heartbeat + recent errors) / Settings (LLM panel with WORKING theme switch, probe button, save toast) all read as one product in D material
- Settings tab doubles as the real theme switcher demo — flip Light there (or via toolbar) and walk all five tabs
- Small-sample honesty note + live-vs-backtest caveat survive the restyle

## Winner Notes (A)

- Underline tab strip (the 001 pattern) wins — Streamlit path of least resistance, familiar chrome; rail and segmented pills read as heavier than the content warrants.
- Setups pane must keep the full 001-D composition: compact table beside [chart + evidence trace] rail (user corrected the first build for dropping the candlestick and the evidence/description panel — both restored).
- Settings tab hosts the real theme switch (Dark/Light radios wired to the theme store) + connection probe + save toast; the rail shows the 5-section compact evidence trace with the agreement badge in the chart header.
- History: outcome pills + signed R column. Performance: KPI row + cumulative-R equity (drawdown wash, per-step win/loss dots, axis labels) + per-symbol table + small-sample honesty note + live-vs-backtest caption. Health: feed freshness chips, MT5 heartbeat card, recent bar-gap errors.
