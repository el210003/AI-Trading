# Degraded & Empty States

Validated decision from sketch **004 (winner B — loud banner)**; the ⌀ meter and
gentle zero-state live in `evidence-trust.md` / `shell-theme-navigation.md`.
Canonical demo: `sources/005-final-consolidated.html` — bottom-right toolbar
cycles states (sketch-only; real app derives state from collector/LLM health).

## Intensity policy (per-state, NOT uniform)

| State | Intensity | Treatment |
|-------|-----------|-----------|
| Zero setups | **Gentle** (information, not error) | Inline empty state in the table panel + next-M15 countdown; never a banner |
| MT5 disconnected | **LOUD** | Blinking dismissible banner + whole tab content dims (`.45`) and locks until acknowledged |
| LLM down | **LOUD** (but inline-metered) | Banner + dimmed content; evidence meter flips to ⌀ ML ONLY inline |

Rationale: trading on frozen data is the worst failure mode — quiet inline cues
(variant A) were judged insufficient. Zero-setups stays patient because it is a
signal too ("the detector is armed and watching, not idle").

## Banner copy convention (verbatim pattern)

`STATE — implication — recovery action`

- "MT5 TERMINAL DISCONNECTED — data frozen at Fri 20:45 UTC · relaunch the
  terminal to resume"
- "LLM PROVIDER DOWN — running ML-only; narratives disabled until provider
  responds"

Banner visual: warn/bear tinted panel, 1px semantic border at 55%, blinking `⚠`
(`blink 1s steps(2)`), 13px weight 700, dismiss button right-aligned.

## Supporting signals that must change together with state

- Topbar chips go `.err` (warn border + warn text) with frozen timestamps
  ("MT5 2d 4h", "LLM timeout"); dots shift ok→warn/bad.
- Table header gains an "as of Fri 20:45" count chip on stale; frozen data is
  always timestamped.
- Content dimming wraps the tab panes (`#panes.dimmed { opacity:.45;
  pointer-events:none }`) — banners sit ABOVE the dim, always live.
- Health tab reflects it too: feed rows → STALE chips, MT5 card →
  "Disconnected — last beat 2d 4h ago · DOWN", error feed gets a
  `mt5_connection` row with recovery hint.
- LLM-down: evidence meter ⌀ ML ONLY + `narrative_status=llm_unavailable ·
  reason=timeout` caption (lives inline with the setup, not in the banner).

## Zero-setups empty state

- `◇` glyph, headline "No setups this session", one honest paragraph, then a
  countdown pill: pulsing dot + mono `next M15 close in 07:12`.
- Table panel reports "0 rows"; no red, no error semantics anywhere.

## Never-silence rule (Phase 5 carry-over)

Fallbacks never fabricate: no invented narratives, no hidden retries. Every
degraded state names what is missing, what is still running, and what will
recover it.
