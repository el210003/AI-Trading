"""Structured-output contract for the LLM narrative (D-02/D-04).

``LLMNarrative`` is the pydantic single source of truth for the D-04 JSON
contract ``{verdict, confidence, reasoning, citations}`` — the same model is
used to (a) derive the strict ``json_schema`` response_format the provider
sends (RESEARCH Pattern 2 / Common Operation 2, via the openai SDK's
``type_to_response_format_param``) and (b) re-validate the returned JSON (no
drift between the two). None of its fields is a price level — the schema
cannot carry an entry/SL/TP level, so the D-02 guard is structural.

``FORBIDDEN_LEVEL_KEYS`` is the schema-level guard (D-02 / SC1): a frozenset of
price-level field names that must never survive as LLM-emitted citations. The
enforcement proof is mechanical — any cited key in this set is dropped, never
relied on prompt adherence.

``ALLOWED_CITATION_KEYS`` is the set of real evidence-object field keys that are
legal citation targets (D-05) — every key the citation check can verify against
the evidence. Reference-only level fields (entry/sl/tp/...) are deliberately
excluded because they are NOT legal citation targets.

Pure / MT5-free; the openai SDK is imported lazily inside
``narrative_response_format`` only, so importing this module has zero I/O and
no dependency on a live endpoint.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field

#: D-02 schema-level guard: any price-level field the LLM emits as a citation is
#: dropped (RESEARCH.md line 272). Never rely on prompt adherence alone (SC1).
FORBIDDEN_LEVEL_KEYS: frozenset[str] = frozenset(
    {
        "entry",
        "sl",
        "tp",
        "sl_price",
        "tp_price",
        "entry_price",
        "take_profit",
        "stop_loss",
    }
)

#: The set of evidence-object field keys that are legal citation targets (D-05).
#: Deliberately excludes the forbidden level fields. ``rr_at_decision`` and the
#: ML provenance keys (``score_source`` / ``artifact_version``) are cited against
#: the evidence object, so they are legal targets; ``p_win`` is the calibrated
#: headline the LLM comments on.
ALLOWED_CITATION_KEYS: frozenset[str] = frozenset(
    {
        "symbol",
        "timeframe",
        "direction",
        "zone_id",
        "zone_state",
        "event_id",
        "pool_id",
        "sweep_side",
        "bias_h1",
        "bias_h4",
        "p_win",
        "score_source",
        "artifact_version",
        "rr_at_decision",
    }
)


class LLMNarrative(BaseModel):
    """D-04 structured narrative contract.

    ``verdict`` is a hard ``Literal`` — a soft third value is structurally
    rejected. ``confidence`` is bounded to [0,1]; ``reasoning`` must be
    non-empty; ``citations`` is a list of evidence field keys the reasoning
    references (validated against the evidence object downstream).
    """

    verdict: Literal["confirm", "refute"]
    confidence: Annotated[float, Field(ge=0.0, le=1.0)]
    reasoning: str = Field(min_length=1)
    citations: list[str]


def narrative_response_format() -> dict:
    """Return the strict ``json_schema`` response_format param for the openai
    SDK derived from ``LLMNarrative`` (single source of truth, no drift).

    Produces ``{"type": "json_schema", "json_schema": {"schema": {...strict}},
    "name": "LLMNarrative", "strict": True}`` via the SDK's
    ``type_to_response_format_param`` (RESEARCH Common Operation 2). Imported
    lazily so the module stays I/O-free and endpoint-free at import time.
    """
    from openai.lib._parsing._completions import type_to_response_format_param

    return type_to_response_format_param(LLMNarrative)
