# Evidence & Trust Surface

Validated decision from sketch **003 (winner B — narrative-first)**; the ML
contributor expansion was added in **005**. Canonical composite:
`sources/005-final-consolidated.html` (evidence panel in the Setups detail rail).

## Composition (top → bottom, one panel)

1. **Agreement meter** (headline — the ML↔LLM relationship is the hero):
   `ML P(win)` big mono number ⇄ link glyph ⇄ `LLM verdict`.
   - AGREE: `⇄` in bull, gradient link bar, `✓ ML↔LLM AGREE` badge (bull gradient pill).
   - DISAGREE: bear colors, `✗ DISAGREE` badge.
   - ML-only: `⌀` muted, `⌀ ML ONLY` outline badge, right side shows `⌀` +
     "LLM unavailable · timeout" — **no narrative line is invented**.
2. **Narrative hero quote** (LLM reasoning): 13.5px, line-height 1.7, 3px accent
   left border. Every claim carries an inline `[E-#]` citation chip (mono,
   10px, accent soft chip). Clicking a chip highlights + scrolls to its receipt.
   - **Refutation line stays visible inside the quote block**
     ("Refutation: H4 close below 1.08420") — falsifiability is part of trust.
3. **Evidence receipts** — one-liners: `icon | name | mono fact string`,
   hairline separators. Fixed five-section order: Market bias → PD zone →
   Liquidity sweep → ML contributors (→ Decision bar when present).
   - Facts are point-in-time values with sources, e.g.
     `pool 1.08420 (3 touches) · strength 0.82 · reclaimed 1 bar`.
   - Key-value dossiers (variant A) become expandable secondary text only.

## ML contributors — expandable breakdown (005)

The "ML contributors" receipt toggles open on click (▸ chevron rotates):

- SHAP-style **diverging bars** centered on a hairline; positive = bull bar
  right of center, negative = bear bar left; scale = |max contribution| ≈ 0.15.
- Rows: **Base rate (90d, point-in-time)** → one row per feature
  (`Liquidity sweep strength +0.14`, `H4 market bias position +0.11`,
  `PD-zone tap depth +0.07`, `Decision-bar close reclaim +0.03`,
  `Session (Asia) penalty −0.05`, `Spread penalty −0.03`) → **P(win) 0.72**
  bold total row.
- Contributions must sum to the displayed P(win) exactly; values mono,
  signed, tabular.
- Footnote: `Contributions vs base rate, same bars the model scored on ·
  model v<ver> @ <timestamp>` — point-in-time honesty, same model that scored.

## LLM-down degradation of this panel

- Quote replaced by caption: `narrative_status = llm_unavailable · reason =
  timeout (12s) — probability stands on its own; no narrative was invented to
  fill the gap. Auto-retry each cycle.`
- Meter → ⌀ ML ONLY; table `Src` column shows `ML` only.

## Streamlit mapping

- Citation chips → `st.markdown` anchor links + `session_state` scroll;
  receipt highlight = CSS flash animation (~1.2s accent-tint fade).
- Row selection syncs chart header + legend + evidence panel (single-source
  selected-setup state).
