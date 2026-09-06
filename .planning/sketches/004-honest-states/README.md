---
sketch: 004
name: honest-states
question: "How loud should degraded states (zero setups / MT5 stale / LLM down) be in D?"
winner: "B"
tags: [states, empty, degraded, honesty, trust]
---

# Sketch 004: Honest States

## Design Question

A signals product loses trust through how it handles nothing/broken states, not
its happy path. Three degraded states matter: **zero setups** (no candidate —
information, not downtime), **MT5 disconnected** (frozen last-known data — must
never be acted on), **LLM unavailable** (ML-only fallback per Phase 5's
never-silence rule). How loud should each be in Variant D?

## How to View

open .planning/sketches/004-honest-states/index.html
Cycle the state pills under the tab bar in EVERY variant.

## Variants (same four states, three intensities)

- **A: Quiet inline** — strip chip turns warn, table becomes an informative empty state with next-M15 countdown, evidence meter flips to ⌀ ML ONLY; nothing shouts
- **B: Loud banner** — a blinking dismissible alert banner + the whole content dims behind it until acknowledged
- **C: Status hero** — a full "what happened / what to do" card (Open Health tab / Retry actions) with dimmed stale content

## What to Look For

- **Zero setups** should feel patient, not broken — all variants keep it gentle by design; compare the countdown treatment
- **MT5 stale** is the dangerous one: does A's quiet chip shout loudly enough to stop you trading on frozen data? (B/C argue yes)
- **LLM down**: meter → ⌀ ML ONLY with `narrative_status=llm_unavailable · reason=timeout` caption — probability stands alone, nothing invented
- A likely wins zero-setups/LLM-only, B/C likely win stale-feed → the real answer may be *per-state* intensity (cherry-pick)

## Winner Notes (B — loud banner)

- Degraded states get a blinking, dismissible alert banner + dimmed/locked content, per the user's explicit pick — trading on frozen data is the worst failure mode and quiet cues were judged insufficient.
- Zero-setups keeps the gentle inline empty state + next-M15 countdown even in B (it is information, not an error — the banner is reserved for stale-feed / LLM-down).
- Banner copy convention: STATE — implication — recovery action ("MT5 TERMINAL DISCONNECTED — data frozen at Fri 20:45 UTC · relaunch the terminal to resume"; "LLM PROVIDER DOWN — running ML-only; narratives disabled until provider responds").
- Evidence meter ⌀ ML ONLY state (badge + `narrative_status=llm_unavailable · reason=timeout` caption) is kept from A — it lives inline with the setup, not in the banner.
