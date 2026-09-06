---
sketch: 003
name: evidence-detail
question: "How should the evidence trace read as trustworthy, not cluttered, in D?"
winner: "B"
tags: [evidence, trust, components, narrative, ml]
---

# Sketch 003: Evidence Detail

## Design Question

The core value is "transparent, reasoned evidence the user can trust and verify."
The v1 trace is a flat accordion (001 baseline). What composition makes the
ML probability, the LLM reasoning, and the underlying SMC evidence verify each
other at a glance without becoming noise?

## How to View

open .planning/sketches/003-evidence-detail/index.html

## Variants (same setup, same data, three readings)

- **A: Structured dossier (001 baseline)** — fixed-order collapsible sections, key-value facts, contributor bars; the honest filing-cabinet
- **B: Narrative-first** — ML P(win) ⇄ LLM CONFIRM agreement meter on top, the LLM narrative as a hero quote with inline [E-#] citation chips; one-line evidence receipts below (chip click highlights + scrolls to the receipt)
- **C: Evidence chain** — P(win) gauge ring, then a vertical stepper of the derivation order (HTF bias → zone tap → sweep+reclaim → decision bar), contributor waterfall to 0.72, LLM verdict as a footnote quote

## What to Look For

- **Verifiability**: can you check the LLM's claim against the raw numbers in 10 seconds? (B's chips, C's chain order)
- **Honesty under disagreement**: imagine verdict=refute / ⌀ ML-only — B's meter shows the split most loudly; C demotes the narrative
- **Clutter**: A is dense but flat; B front-loads prose; C orders everything
- Works in both themes; candlestick stays identical across variants (001 chart contract)

## Winner Notes (B — narrative-first)

- ML P(win) ⇄ LLM verdict agreement meter on top — the ML↔LLM relationship is the headline; it must also carry the ✗ DISAGREE (bear) and ⌀ ML-only (muted, no narrative line) states.
- LLM narrative rendered as hero quote; every claim carries a [E-#] citation chip; clicking a chip highlights + scrolls to its grounding receipt (works as st.markdown anchor links + session_state scroll in Streamlit).
- Evidence receipts are one-liners (icon, name, mono fact string) — the filing-cabinet kv detail of A becomes expandable secondary text if needed.
- Refutation line ("Refutation: H4 close below 1.08420") stays visible in the quote block — falsifiability is part of trust.
