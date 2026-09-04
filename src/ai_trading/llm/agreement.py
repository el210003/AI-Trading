"""ML↔LLM agreement flag (AI-06) — pure, NA-safe, config-thresholded.

``agreement_flag(verdict, confidence, p_win, cfg) -> (agreement, confidence)``
returns a 3-state ``agree | disagree | unclear`` plus the LLM confidence.

ML direction = ``confirm`` when ``p_win >= 0.5`` else ``refute``. Then, per
research Open Question 1 recommendation:

- ``confidence < cfg.llm_agree_min_confidence`` (default 0.6) → ``unclear``.
- ``verdict == ml_direction`` → ``agree``.
- else → ``disagree``.

NA-safe: a pandas-missing / NaN ``p_win`` is treated as ``unclear`` (mirrors
``candidates.bias_agrees`` NA discipline). The agreement is a derived view —
the raw verdict and confidence remain exposed on the pipeline result; this
function never hides them.

Pure: no I/O, no mutation.
"""

from __future__ import annotations

import pandas as pd


def agreement_flag(verdict: str, confidence: float, p_win, cfg) -> tuple[str, float]:
    """Return ``(agreement, confidence)``, a 3-state agree/disagree/unclear."""
    confidence = float(confidence)
    floor = float(cfg.llm_agree_min_confidence)
    if pd.isna(p_win):
        return ("unclear", confidence)
    ml_direction = "confirm" if float(p_win) >= 0.5 else "refute"
    if confidence < floor:
        return ("unclear", confidence)
    if verdict == ml_direction:
        return ("agree", confidence)
    return ("disagree", confidence)
