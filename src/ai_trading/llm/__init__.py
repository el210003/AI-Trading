"""LLM narrative layer (schema, provider, prompt, evidence, citations,
agreement, narrative, writer): MT5-free by design; import submodules
directly — this file stays a bare marker for Phase 5, with a small set of
convenience re-exports for the Phase 6 consumers.

Local-module imports remain the convention; these exports are additive and
never required (``import ai_trading.llm`` alone is still safe).
"""

from ai_trading.llm.agreement import agreement_flag
from ai_trading.llm.narrative import NarrativeResult, run_narrative_pipeline
from ai_trading.llm.provider import LLMProvider
from ai_trading.llm.schema import LLMNarrative

__all__ = [
    "LLMNarrative",
    "LLMProvider",
    "NarrativeResult",
    "agreement_flag",
    "run_narrative_pipeline",
]
