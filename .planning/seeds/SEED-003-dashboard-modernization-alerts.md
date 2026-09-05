---
id: SEED-003
status: dormant
planted: 2026-09-05
planted_during: v1.0 milestone, Phase 6 (setups-dashboard) — final UAT check pending
trigger_when: v1.0 milestone closes (first /gsd-new-milestone planning)
scope: medium
---

# SEED-003: Dashboard modernization (UI-SPEC v2) + setup alerts

## Why This Matters

The v1 dashboard was built to a deliberately utilitarian locked spec (06-UI-SPEC
dark palette) — functional and verified, but visually a "demo". A signals
product's dashboard is the product surface; a modern, information-dense,
trust-signaling UI directly serves the core value (transparent, reasoned
evidence the user can trust). Separately, a signals system with no push
notification means the user must poll the dashboard — **setup alerts**
(Telegram/email on setup emission) close the loop and are arguably the
highest-value v2 feature after SEED-001/SEED-002.

## When to Surface

**Trigger:** the v1.0 milestone closes — surface during the first
`/gsd-new-milestone` planning session alongside SEED-001/SEED-002.

## Scope Estimate

**Medium** — one focused phase (sketch → UI-SPEC v2 → implement), plus a small
separable alerts feature.

Design levers identified 2026-09-05 (all Streamlit/plotly-native):

1. **KPI cards** — replace `st.metric` with custom HTML cards: rounded corners,
   soft shadows, gradient accents, delta chips vs backtest baseline, sparklines
2. **Table encoding** — `st.dataframe` `column_config`: P(win) as in-cell
   progress bar, R multiples as diverging bars, status as styled pills
3. **Typography/spacing** — proper font stack (Inter/IBM Plex), consistent
   spacing rhythm
4. **Charts** — shared plotly dark template; volume subplot + ATR band under
   the candlestick; gradient PD-zone fills; equity-curve drawdown shading;
   inline hover templates; probability gauge on the selected setup
5. **Behavior** — `st.fragment` auto-refresh Health strip (live heartbeat
   without full rerun); evidence trace as collapsible icon-headed sections;
   prominent ML↔LLM agreement badge
6. **Alerts (separable)** — Telegram/email push on new setup + lifecycle
   transitions; config-driven (`alert_*` knobs, credential in
   config.local.toml per ASVS V14); MT5-free, reads the setup store

Process note: the current palette is a LOCKED contract from Phase 6 that passed
human visual review — modernization is a UI-SPEC v2, not a tweak. Route:
`/gsd-sketch` (throwaway HTML mockups to pick a direction) → UI-SPEC v2 →
implementation phase.

## Breadcrumbs

- `.planning/phases/06-setups-dashboard/06-UI-SPEC.md` — the locked v1 contract to supersede
- `src/ai_trading/dashboard/theme.py` — palette/semantics module
- `src/ai_trading/dashboard/views_*.py` — the four tab views
- `src/ai_trading/dashboard/charts.py` — plotly chart builders (dark template target)
- `.streamlit/config.toml` — Streamlit theme config
- `src/ai_trading/setup/store.py` — the store an alerts watcher would poll
- `config.local.toml` — where alert credentials would live (ASVS V14)

## Notes

Planted 2026-09-05 from the user's request for a "more modern and beautiful"
dashboard plus the alerts suggestion from the same conversation. Depends on
nothing; composes with SEED-001 (7x24 setups make the alerts feature
meaningful around the clock).
