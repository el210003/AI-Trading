"""Prompt builder for the LLM narrative — PURE (D-03), MT5-free.

The prompt is built STRICTLY from the evidence object's field projection. No
raw OHLC/candle series, no recomputed SL/TP/entry/R:R values, no raw feature
arrays. The builder never reaches outside the passed ``evidence`` dict.

Level-field strip (D-02/D-03): the D-02 schema-level guard drops any level
field the LLM emits; the prompt proactively strips ``FORBIDDEN_LEVEL_KEYS``
from the serialized evidence so the model is not fed (or tempted to emit)
price levels. The full evidence object remains available to the citation check
in the narrative pipeline.

``build_prompt(evidence)`` returns ``(system_messages, user_messages)``, a
tuple of the system and user message dict lists the provider flattens into the
``chat.completions.create`` messages argument.
"""

from __future__ import annotations

import json

from ai_trading.llm.schema import FORBIDDEN_LEVEL_KEYS


def _evidence_projection(evidence: dict) -> dict:
    """Return a JSON-serializable copy of the evidence object minus the
    forbidden level fields (D-02/D-03). Only these fields reach the prompt."""
    return {
        key: value
        for key, value in evidence.items()
        if key not in FORBIDDEN_LEVEL_KEYS
    }


def build_prompt(evidence: dict) -> tuple[list[dict], list[dict]]:
    """Return ``(system_messages, user_messages)`` message dicts.

    The system message instructs the model to reason only from the provided
    structured evidence and return only the D-04 JSON contract; the user message
    embeds the evidence object's field projection. Both are dicts suitable for
    ``chat.completions.create`` messages.
    """
    system = [
        {
            "role": "system",
            "content": (
                "You are an evidence-grounded trading narrative assistant. "
                "Reason ONLY from the structured evidence object in the user "
                "message. Never invent prices, levels, or probabilities; never "
                "recompute or suggest entry, stop-loss, or take-profit levels. "
                'Return exactly one JSON object with fields: verdict ("confirm" '
                'or "refute"), confidence (a number in [0, 1]), reasoning (a '
                "short evidence-grounded paragraph), and citations (a list of "
                "keys from the evidence object that your reasoning references)."
            ),
        }
    ]
    user = [
        {
            "role": "user",
            "content": (
                "Here is the structured evidence object. Reason from these "
                "fields only:\n"
                + json.dumps(_evidence_projection(evidence), indent=2, sort_keys=True)
            ),
        }
    ]
    return system, user
