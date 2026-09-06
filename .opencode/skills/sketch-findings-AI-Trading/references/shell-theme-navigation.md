# Shell, Theme & Navigation

Validated decisions from sketches **001 (winner D)** and **002 (winner A)**.
Canonical composite: `sources/005-final-consolidated.html` (light theme loads by default).

## Material & shell — "Neon Glass + Wide Desk" (001-D)

- Canvas: `max-width: min(1800px, 96vw)`, centered; content grid gives the table
  ~45% and the [chart + evidence] rail ~55% (`grid-template-columns: 1fr 1.15fr`).
- Panels: glass surface `var(--color-surface)`, 14px radius, 1px border,
  layered shadow `0 1px 2px rgba(16,24,40,.05), 0 8px 24px rgba(16,24,40,.06)`.
- Accents: cyan→violet `#0092C2 → #7C5CFF`; KPI cards carry a 3px gradient
  edge-bar on the left; brand logo is a gradient tile.
- KPI values: 30px mono, tabular numerals, `letter-spacing:-.5px`; deltas as
  soft tint pills (`color-mix(in srgb, <sem> 13%, transparent)`).
- Bullets/pills fully rounded (9999px); status pills = glyph + label + soft tint
  (`●active` cyan, `○pending` muted, `✓TP hit` bull, `✗SL hit` bear, `⌀/◌` warn).
- Semantic colors: bull `#0F8A7E`, bear `#D64545`, warn `#A87A00` — always used
  as `color-mix()` tints on text/borders, never full-bleed fills.
- Rejected: dense charcoal (too flat/low-trust), aurora gradient (gimmicky at
  data scale), icon rail + segmented nav (heavier than content warrants).

## Density (001-D)

- Setup table wins compact: 11 columns (Symbol, TF, Dir, Status, Entry, SL, TP,
  R:R, P(win), Src, Age) in tight cells, `font-variant-numeric: tabular-nums`,
  row height ~8px padding, scrollable `max-height: 380px`.
- Freed width goes to the chart rail — compact table + wide chart is the trade.
- Row states: hover = 8% accent tint; selected = 11% tint + inset 1px accent ring.
- Filter bar: rounded chips (multi-toggle), vertical `|` separators, P(win)≥
  range slider — all filters are chips, never dropdown-heavy.

## Chart contract (001-D review findings — hard rules)

- **PD-zone band**: dark theme needs fill opacity ≥ **.16** + **.55 dashed border**
  (thinner disappears); zone label in-plot, top-left of band.
- **Gridlines**: ≥ **.16 white** on dark / **.12 ink** on light; add **vertical
  dashed time lines** (every ~8 bars) and **in-plot price labels** on the right
  edge of each horizontal gridline.
- **Entry/SL/TP levels**: dashed 1.4px lines extending into a right **axis gutter
  ≥ 104px** (labels clip below ~56px); gutter labels = mono tabular text on soft
  color chips (12% tint rect behind text).
- Sweep marked with diamond glyph + in-plot price annotation.
- Caption line below chart: `Entry · SL · TP · R:R · P(win) [src]` in muted 11px.

## Themes (001 + 002)

- Ship BOTH dark and light, same token names; the app exposes the user choice
  (Settings tab = the real switcher).
- Dark (`sources/themes/default.css`): body `#06080F`; page background = radial
  accent glow over `--color-bg`.
- Light (`sources/themes/light.css`): body/page `#E9EDF3` / `#EDF1F7`; same
  component CSS via tokens; override per-variant token blocks if variants ever
  return.
- **Loading order is load-bearing**: theme `<link>` must come AFTER the inline
  `<style>` block, else equal-specificity component rules win and the theme
  doesn't apply. Hardcoded darks must be refactored to
  `--fill/--line/--bar/--hover/--zebra` + `color-mix()` so light can flip them.
- Toggle `html { color-scheme }` with the theme so native widgets follow.

## Navigation (002-A)

- **Underline tab strip** (2px accent underline, muted→accent text, 4px gap,
  bottom-border container) — Streamlit path of least resistance; persistent and
  familiar at 1800px.
- Five tabs: **Setups · History · Performance · Health · Settings**.
- Setups pane = the full 001-D composition (user corrected a build that dropped
  the candlestick or evidence rail — both are mandatory).
- History: outcome pills (WIN/LOSS/TIMEOUT) + signed R column + honesty caption.
- Performance: KPI row, cumulative-R equity (per-step win/loss dots, drawdown
  wash fill, axis labels), per-symbol table + small-sample honesty note
  ("n<30 — directional, not statistical") + live-vs-backtest fill-basis caption.
- Health: feed freshness rows (FRESH/STALE chips), MT5 heartbeat card, recent
  errors incl. bar-gaps and offset-drift rows.
- Settings: LLM provider panel + **theme radios live here** + connection probe
  with latency/JSON-extraction result + save toast.

## Streamlit mapping notes

- Everything is CSS-injection + plotly-template level; judge feel, not feasibility.
- Underline tabs map to `st.tabs` restyling; theme switch maps to the theme store
  + `.streamlit/config.toml` regeneration (supersedes Phase-6 locked `theme.py`
  palette via UI-SPEC v2).
