---
sketch: 005-final-consolidated
question: Do all four winning decisions compose into one coherent dashboard at full fidelity?
status: composed
winner: consolidated (001-D + 002-A + 003-B + 004-B)
themes: default (dark) + light, switchable — light loads by default
date: 2026-09-07
---

# 005 — FINAL consolidated mockup

Not a variant contest — a **consistency sketch** that composes the four accepted winners
into one page at production fidelity, as the reference to implement from.

## Composed from

| Region | Winner | What it contributes |
|--------|--------|--------------------|
| Shell, palette, themes | 001-D Neon Glass + Wide Desk | 1800px desk, compact 11-col table, chart contract (zone band, gutter labels ≥104px, gridlines), dark+light via `../themes/` |
| Navigation | 002-A underline tabs | Five tabs, per-tab compositions (History/Performance/Health/Settings) |
| Evidence rail | 003-B narrative-first | Agreement meter, cited hero quote ([E-#] chips flash receipts), refutation line |
| Honesty states | 004-B loud banner | Stale + LLM-down banners ("STATE — implication — recovery action"), dimmed content, ⌀ ML-only meter, gentle zero-state with countdown |

## Demo controls (bottom-right, sketch-only)

- **state**: populated · zero setups · MT5 stale · LLM down — exercises 004-B across the whole page
- **theme**: light · dark
- **width**: full · 1280 · 768

## Verified headlessly (2026-09-07)

- Tab switch, row→chart-header sync, cite-chip→receipt flash
- Stale: banner shows, content dims, chips go err, table gets "as of" caption
- LLM down: banner, ⌀ ML-ONLY badge, narrative replaced by llm_unavailable caption, Src column → ML
- Zero: 0 rows + gentle empty state + next-M15 countdown
- Theme swap both ways (body #06080F ↔ #EDF1F7, `html` color-scheme follows)

## Notes for implementation

- The demo state-switcher must NOT ship — real states come from collector/LLM health.
- History/Performance/Health/Settings pane copy is final enough to lift verbatim.
- `data-refresh` shows optimistic "Syncing… → ✓ Updated HH:MM:SS → resets".
