---
name: sketch-findings-AI-Trading
description: Validated dashboard design decisions for AI-Trading (from the SEED-003 sketch cycle 2026-09) — Neon Glass + Wide Desk shell, dark+light themes, chart readability contract, narrative-first evidence panel, honest degraded-state policy. Load before UI-SPEC v2 or any dashboard implementation work.
---

# Sketch Findings — AI-Trading Dashboard Modernization

Design contracts validated interactively in browser sketches (user picked
winners 001-D, 002-A, 003-B, 004-B; 005 composes them into the canonical
reference). These are DECIDED — do not re-open the variant contests; refine
within these constraints.

## Start here

`sources/005-final-consolidated.html` — the complete final mockup: all five
tabs, both themes, all four honesty states (demo state-cycler bottom-right;
the cycler itself must NOT ship). Open it, resize it, flip it to dark.

## Decisions by area

| Area | Reference | Core decision |
|------|-----------|---------------|
| Shell, theme, nav | `references/shell-theme-navigation.md` | Variant D "Neon Glass + Wide Desk" (1800px, compact 11-col table, ~55% chart rail), underline tabs ×5, dark+light via token CSS with link-after-style loading rule, chart readability contract (zone fill ≥.16, gutter ≥104px, gridline α rules) |
| Evidence & trust | `references/evidence-trust.md` | Narrative-first panel: ML⇄LLM agreement meter headline, hero quote with [E-#] citation chips → one-line receipts, visible refutation line, expandable SHAP-style contributor breakdown summing to P(win) |
| Honest states | `references/honest-states.md` | Per-state intensity: gentle zero-setups + countdown; LOUD blinking banner + dimmed content for MT5-stale and LLM-down; banner copy = "STATE — implication — recovery action"; never-silence rule |

## Source sketches (history of each decision)

`sources/001-dashboard-shell.html` (A/B/C/D variants, D ★),
`sources/002-tab-family.html` (nav chrome A ★/B/C, all five panes),
`sources/003-evidence-detail.html` (evidence A/B ★/C),
`sources/004-honest-states.html` (state intensities A/B ★/C),
`sources/005-final-consolidated.html` (★ canonical),
`sources/themes/default.css` + `sources/themes/light.css` (token pair,
directly liftable).

## Scope note

These findings supersede the locked Phase-6 v1 palette
(`src/ai_trading/dashboard/theme.py`, `.streamlit/config.toml`) **via** UI-SPEC
v2 in the upcoming modernization phase (SEED-003) — not by ad-hoc edits.
